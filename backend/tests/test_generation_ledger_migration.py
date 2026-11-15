"""Transactional schema-local migration tests; parent STAB-007 harness only."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError

from app import db
from test_db_guard import assert_connection, prepare_runtime
from test_generation_ledger_schema import (
    TABLES, START, diagnostic, legacy, observation, product, request,
)


VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
OLD_TABLES = ("zodiac_signs", "prompt_versions", "forecasts", "generation_runs",
              "generation_items", "generation_attempts", "generation_jobs")


def migration(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate_to_0005():
    for name in ("0001_initial_schema", "0002_add_generation_attempts", "0003_prompt_pipeline",
                 "0004_variation_prompt", "0005_generation_jobs"):
        migration(name).upgrade()


@pytest.fixture
def schema_connection(app):
    # No env.py/config loading and no new database target. Every DDL statement
    # stays in one rollback-only schema transaction on the guarded test engine.
    with app.app_context(), db.engine.connect() as connection:
        assert_connection(connection, prepare_runtime())
        connection.rollback()
        with connection.begin() as transaction:
            schema = "ledger_migration_" + uuid4().hex
            connection.execute(sa.schema.CreateSchema(schema))
            quoted_schema = connection.dialect.identifier_preparer.quote(schema)
            connection.execute(sa.text(f"SET LOCAL search_path TO {quoted_schema}"))
            with Operations.context(MigrationContext.configure(connection)):
                yield connection
            transaction.rollback()


def history(connection):
    return {name: connection.execute(sa.text(
        f"SELECT row_to_json(t)::text FROM {name} t ORDER BY 1")).scalars().all()
        for name in OLD_TABLES}


def old_structure(connection):
    inspector = sa.inspect(connection)
    return {name: dict(
        columns=[(c["name"], str(c["type"]), c["nullable"], c["default"])
                 for c in inspector.get_columns(name)],
        pk=inspector.get_pk_constraint(name),
        fks=inspector.get_foreign_keys(name),
        uniques=inspector.get_unique_constraints(name),
        checks=inspector.get_check_constraints(name),
        indexes=inspector.get_indexes(name),
    ) for name in OLD_TABLES}


def test_fresh_migrations_create_empty_ledger_and_keep_reference_seeds(schema_connection):
    c = schema_connection
    migrate_to_0005()
    migration("0006_generation_ledger").upgrade()
    assert set(sa.inspect(c).get_table_names(schema=c.scalar(sa.text("SELECT current_schema()")))) == set(OLD_TABLES + TABLES)
    assert all(c.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0 for table in TABLES)
    assert c.scalar(sa.text("SELECT count(*) FROM zodiac_signs")) == 13
    assert c.scalar(sa.text("SELECT count(*) FROM prompt_versions WHERE key = 'daily-ru-v1'")) == 1
    p = product(c)
    observation(c, p["request_id"])


def test_upgrade_preserves_legacy_history_schema_and_never_backfills_requests(schema_connection):
    c = schema_connection
    migrate_to_0005()
    old = legacy(c)
    c.execute(sa.text("""
        UPDATE generation_jobs SET attempt_count = 3, started_at = :at,
            finished_at = :at, status = 'failed' WHERE id = :id
    """), {"at": START, "id": old["job_id"]})
    c.execute(sa.text("""
        INSERT INTO forecasts (sign_key, target_date, locale, forecast_type, text,
            status, source, generation_item_id, published_at)
        VALUES ('aries', '2026-11-17', 'ru', 'daily', 'historical published text',
            'published', 'stub', :item_id, :at)
    """), {"item_id": old["item_id"], "at": START})
    c.execute(sa.text("""
        UPDATE generation_attempts SET status = 'success',
            response_payload = '{"legacy": "not billing evidence"}'::jsonb
        WHERE id = :id
    """), {"id": old["legacy_attempt_id"]})
    before_rows, before_schema = history(c), old_structure(c)
    migration("0006_generation_ledger").upgrade()
    assert history(c) == before_rows
    assert old_structure(c) == before_schema
    assert all(c.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0 for table in TABLES)


def test_empty_downgrade_then_upgrade_preserves_old_tables(schema_connection):
    c = schema_connection
    migrate_to_0005()
    legacy(c)
    before_rows, before_schema = history(c), old_structure(c)
    module = migration("0006_generation_ledger")
    module.upgrade()
    module.downgrade()
    inspector = sa.inspect(c)
    assert not set(TABLES) & set(inspector.get_table_names(schema=c.scalar(sa.text("SELECT current_schema()"))))
    assert c.scalar(sa.text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                            "WHERE n.nspname=current_schema() AND p.proname LIKE 'generation_ledger_%'")) == 0
    assert history(c) == before_rows
    assert old_structure(c) == before_schema
    module.upgrade()
    assert all(sa.inspect(c).has_table(table) for table in TABLES)


@pytest.mark.parametrize("kind", ["execution_only", "diagnostic_request", "product_observation"])
def test_nonempty_downgrade_refuses_before_dropping_anything(schema_connection, kind):
    c = schema_connection
    migrate_to_0005()
    module = migration("0006_generation_ledger")
    module.upgrade()
    if kind == "execution_only":
        diagnostic(c)
    elif kind == "diagnostic_request":
        request(c, diagnostic(c))
    else:
        observation(c, product(c)["request_id"])
    before = {table: c.scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in TABLES}
    with pytest.raises(DBAPIError) as error:
        with c.begin_nested():
            module.downgrade()
    assert error.value.orig.sqlstate == "55000"
    assert "nonempty generation ledger" in str(error.value.orig)
    assert {table: c.scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in TABLES} == before
    assert c.scalar(sa.text("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                           "JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname=current_schema() AND NOT t.tgisinternal")) == 8


def test_mid_migration_failure_rolls_back_new_objects_and_preserves_history(schema_connection, monkeypatch):
    c = schema_connection
    migrate_to_0005()
    legacy(c)
    before_rows, before_schema = history(c), old_structure(c)
    module = migration("0006_generation_ledger")
    original_execute = module.op.execute

    def fail_trigger_creation(sql, *args, **kwargs):
        if str(sql).startswith("CREATE TRIGGER"):
            raise RuntimeError("injected migration failure")
        return original_execute(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module.op, "execute", fail_trigger_creation)
        with pytest.raises(RuntimeError, match="injected migration failure"):
            with c.begin_nested():
                module.upgrade()
    assert history(c) == before_rows
    assert old_structure(c) == before_schema
    assert not set(TABLES) & set(sa.inspect(c).get_table_names(schema=c.scalar(sa.text("SELECT current_schema()"))))
    assert c.scalar(sa.text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                            "WHERE n.nspname=current_schema() AND p.proname LIKE 'generation_ledger_%'")) == 0
    module.upgrade()  # Clean retry after the rolled-back failed DDL.


def test_insert_trigger_uses_own_schema_not_caller_search_path(schema_connection):
    c = schema_connection
    migrate_to_0005()
    module = migration("0006_generation_ledger")
    module.upgrade()
    old = legacy(c)
    schema = c.scalar(sa.text("SELECT current_schema()"))
    # public.generation_jobs has no matching fixture row. Unqualified trigger
    # lookups would either miss it or read unrelated public data.
    c.execute(sa.text("SET LOCAL search_path TO public"))
    qualified = c.dialect.identifier_preparer.quote(schema)
    e = uuid4()
    c.execute(sa.text(f"""
        INSERT INTO {qualified}.generation_executions
            (id, job_id, origin, deployment_mode, provider, target_date, locale,
             forecast_type, policy_version, lease_epoch, started_at)
        VALUES (:id, :job_id, 'queue_worker', 'production', 'openai',
            '2026-11-17', 'ru', 'daily', 'v1', 1, :at)
    """), {"id": e, "job_id": old["job_id"], "at": START})
    c.execute(sa.text(f"""
        INSERT INTO {qualified}.generation_execution_runs (execution_id, run_id, linked_at)
        VALUES (:e, :r, :at)
    """), {"e": e, "r": old["run_id"], "at": START})
    r = uuid4()
    c.execute(sa.text(f"""
        INSERT INTO {qualified}.generation_api_requests
            (id, execution_id, request_no, run_id, item_id, legacy_attempt_id,
             admission_scope, policy_version, admitted_at)
        VALUES (:id, :e, 1, :run_id, :item_id, :legacy_attempt_id, 'scope', 'v1', :at)
    """), old | {"id": r, "e": e, "at": START})
    c.execute(sa.text(f"""
        INSERT INTO {qualified}.generation_api_observations
            (id, request_id, observation_no, recorded_at, outcome, review_state)
        VALUES (:id, :r, 1, :at, 'unknown', 'requires_review')
    """), {"id": uuid4(), "r": r, "at": START})


def test_unsupported_dialect_fails_before_ddl(monkeypatch):
    from types import SimpleNamespace
    module = migration("0006_generation_ledger")
    monkeypatch.setattr(module.op, "get_bind", lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    monkeypatch.setattr(module, "_create_tables", lambda: pytest.fail("must reject before DDL"))
    for operation in (module.upgrade, module.downgrade):
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            operation()

"""Schema-local rollback-only migration tests; orchestrator STAB-007 only."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from test_generation_ledger_migration import (
    history, migrate_to_0005, migration, old_structure, schema_connection,
)
from test_generation_ledger_schema import TABLES, legacy, product


NAME = "0007_generation_scope_admission"
INDEX = "uq_generation_runs_active_package"


def migrate_to_0006():
    migrate_to_0005()
    migration("0006_generation_ledger").upgrade()


def runs(connection):
    return connection.execute(sa.text(
        "SELECT row_to_json(r)::text FROM generation_runs r ORDER BY id"
    )).scalars().all()


def ledger_rows(connection):
    return {table: connection.execute(sa.text(
        f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1"
    )).scalars().all() for table in TABLES}


def insert_run(connection, *, status="running", run_type="manual"):
    return connection.scalar(sa.text("""
        INSERT INTO generation_runs
            (run_type, target_date, locale, forecast_type, status)
        VALUES (:type, '2026-11-17', 'ru', 'daily', :status)
        RETURNING id
    """), {"type": run_type, "status": status})


def test_fresh_chain_adds_unique_running_scope_index(schema_connection):
    c = schema_connection
    migrate_to_0006()
    migration(NAME).upgrade()
    index = next(i for i in sa.inspect(c).get_indexes("generation_runs") if i["name"] == INDEX)
    assert index["unique"]
    assert index["column_names"] == ["target_date", "locale", "forecast_type"]
    assert "status" in str(index["dialect_options"]["postgresql_where"])
    assert "running" in str(index["dialect_options"]["postgresql_where"])
    insert_run(c)
    with pytest.raises(IntegrityError) as error:
        with c.begin_nested():
            insert_run(c, run_type="retry")
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == INDEX


def test_historical_final_runs_and_ledger_preserved(schema_connection):
    c = schema_connection
    migrate_to_0006()
    product(c)
    for status in ("success", "partial_failed", "failed", "interrupted"):
        insert_run(c, status=status, run_type="retry")
    before_history, before_ledger = history(c), ledger_rows(c)
    migration(NAME).upgrade()
    assert history(c) == before_history
    assert ledger_rows(c) == before_ledger


def test_conflicting_historical_running_rows_abort_without_mutation(schema_connection):
    c = schema_connection
    migrate_to_0006()
    legacy(c)
    insert_run(c, run_type="backfill")
    before_history, before_ledger = history(c), ledger_rows(c)
    before_structure = old_structure(c)
    with pytest.raises(RuntimeError, match="conflicting running package scopes"):
        with c.begin_nested():
            migration(NAME).upgrade()
    assert history(c) == before_history
    assert ledger_rows(c) == before_ledger
    assert old_structure(c) == before_structure
    assert INDEX not in {i["name"] for i in sa.inspect(c).get_indexes("generation_runs")}


def test_index_creation_failure_rolls_back_without_data_loss(schema_connection, monkeypatch):
    c = schema_connection
    migrate_to_0006()
    product(c)
    before_history, before_ledger = history(c), ledger_rows(c)
    module = migration(NAME)

    def fail_index(*args, **kwargs):
        raise RuntimeError("injected index failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.op, "create_index", fail_index)
        with pytest.raises(RuntimeError, match="injected index failure"):
            with c.begin_nested():
                module.upgrade()
    assert history(c) == before_history
    assert ledger_rows(c) == before_ledger
    module.upgrade()
    assert INDEX in {i["name"] for i in sa.inspect(c).get_indexes("generation_runs")}


def test_final_to_running_update_obeys_same_index(schema_connection):
    c = schema_connection
    migrate_to_0006()
    migration(NAME).upgrade()
    insert_run(c)
    final = insert_run(c, status="failed")
    before = runs(c)
    with pytest.raises(IntegrityError) as error:
        with c.begin_nested():
            c.execute(sa.text("UPDATE generation_runs SET status='running' WHERE id=:id"),
                      {"id": final})
    assert error.value.orig.diag.constraint_name == INDEX
    assert runs(c) == before


def test_downgrade_only_removes_index_preserves_history(schema_connection):
    c = schema_connection
    migrate_to_0006()
    product(c)
    module = migration(NAME)
    module.upgrade()
    before_history, before_ledger = history(c), ledger_rows(c)
    module.downgrade()
    assert INDEX not in {i["name"] for i in sa.inspect(c).get_indexes("generation_runs")}
    assert history(c) == before_history
    assert ledger_rows(c) == before_ledger


def test_upgrade_and_downgrade_restore_timeout_configuration(schema_connection):
    c = schema_connection
    migrate_to_0006()
    c.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    c.execute(sa.text("SET LOCAL statement_timeout = '3s'"))
    query = sa.text("SELECT current_setting('lock_timeout'), current_setting('statement_timeout')")
    before = tuple(c.execute(query).one())
    module = migration(NAME)
    module.upgrade()
    assert tuple(c.execute(query).one()) == before
    module.downgrade()
    assert tuple(c.execute(query).one()) == before


def test_migration_does_not_weaken_stricter_caller_timeouts(schema_connection, monkeypatch):
    c = schema_connection
    migrate_to_0006()
    c.execute(sa.text("SET LOCAL lock_timeout = '100ms'"))
    c.execute(sa.text("SET LOCAL statement_timeout = '200ms'"))
    module = migration(NAME)
    create_index = module.op.create_index

    def verify_then_create(*args, **kwargs):
        assert dict(c.execute(sa.text(
            "SELECT name, setting::int FROM pg_settings "
            "WHERE name IN ('lock_timeout', 'statement_timeout')"
        )).all()) == {"lock_timeout": 100, "statement_timeout": 200}
        return create_index(*args, **kwargs)

    monkeypatch.setattr(module.op, "create_index", verify_then_create)
    module.upgrade()


def test_unsupported_dialect_fails_before_ddl(monkeypatch):
    from types import SimpleNamespace
    module = migration(NAME)
    connection = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    monkeypatch.setattr(module.op, "get_bind", lambda: connection)
    for operation in (module.upgrade, module.downgrade):
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            operation()

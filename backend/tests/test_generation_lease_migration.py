"""Schema-local lease upgrade/constraint tests; orchestrator STAB-007 only."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from app.models import GenerationJob
from test_generation_ledger_migration import (
    OLD_TABLES, migrate_to_0005, migration, old_structure, schema_connection,
)
from test_generation_ledger_schema import execution, legacy, link, request, TABLES


LEASE_COLUMNS = (
    "lease_epoch", "lease_heartbeat_at", "lease_expires_at", "lease_deadline_at",
    "lease_ttl_seconds", "lease_heartbeat_interval_seconds",
)
NOW = datetime(2026, 11, 15, 23, 59, 55, tzinfo=timezone.utc)


def _prior(connection):
    migrate_to_0005()
    migration("0006_generation_ledger").upgrade()
    migration("0007_generation_scope_admission").upgrade()


def _old_rows(connection):
    result = {}
    for table in OLD_TABLES + TABLES:
        columns = [column["name"] for column in sa.inspect(connection).get_columns(table)
                   if column["name"] not in LEASE_COLUMNS or table != "generation_jobs"]
        rows = connection.execute(sa.text(f"SELECT {', '.join(columns)} FROM {table}"))
        result[table] = sorted((tuple(row) for row in rows), key=repr)
    return result


def _job(connection, *, status="queued"):
    return connection.scalar(sa.text("""
        INSERT INTO generation_jobs (job_type, status, target_date, provider, dedupe_key)
        VALUES ('manual', :status, '2026-11-16', 'stub', :dedupe) RETURNING id
    """), {"status": status, "dedupe": str(uuid4())})


def _claim(connection, job_id, *, timed=True):
    connection.execute(sa.text("""
        UPDATE generation_jobs SET status='running', lease_epoch=lease_epoch+1,
            locked_by='test-worker', locked_at=:now,
            lease_heartbeat_at=:heartbeat, lease_expires_at=:expiry,
            lease_deadline_at=:deadline, lease_ttl_seconds=:ttl,
            lease_heartbeat_interval_seconds=:interval
        WHERE id=:id
    """), dict(id=job_id, now=NOW, heartbeat=NOW if timed else None,
               expiry=NOW + timedelta(seconds=10) if timed else None,
               deadline=NOW + timedelta(seconds=25) if timed else None,
               ttl=10 if timed else None, interval=3 if timed else None))


def _reject(connection, sql, *, job_id, code="23514"):
    with pytest.raises(DBAPIError) as failure:
        with connection.begin_nested():
            connection.execute(sa.text(sql), {"id": job_id})
    assert failure.value.orig.sqlstate == code


def test_fresh_chain_and_historical_upgrade_do_not_fabricate_epochs(schema_connection):
    connection = schema_connection
    _prior(connection)
    old = legacy(connection)
    execution_id = execution(connection, origin="queue_worker", lease_epoch=None,
                             job_id=old["job_id"])
    link(connection, execution_id, old["run_id"])
    request(connection, execution_id, **{key: old[key] for key in
            ("run_id", "item_id", "legacy_attempt_id")})
    before = _old_rows(connection)
    module = migration("0008_generation_job_leases")
    assert module.down_revision == "0007_generation_scope_admission"
    module.upgrade()
    assert _old_rows(connection) == before
    row = connection.execute(sa.text("SELECT * FROM generation_jobs WHERE id=:id"),
                             {"id": old["job_id"]}).mappings().one()
    assert row["lease_epoch"] == 0
    assert all(row[name] is None for name in LEASE_COLUMNS if name != "lease_epoch")
    _claim(connection, old["job_id"], timed=False)
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"),
                             {"id": old["job_id"]}) == 1
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_executions WHERE id=:id"),
                             {"id": execution_id}) is None


@pytest.mark.parametrize("epoch", [1, 7])
@pytest.mark.parametrize("mode", ["production", "test"])
def test_positive_historical_epoch_refuses_upgrade_before_ddl(
        schema_connection, monkeypatch, epoch, mode):
    connection = schema_connection
    _prior(connection)
    old = legacy(connection)
    execution_id = execution(connection, origin="queue_worker", deployment_mode=mode,
                             lease_epoch=epoch, job_id=old["job_id"])
    link(connection, execution_id, old["run_id"])
    request(connection, execution_id, **{key: old[key] for key in
            ("run_id", "item_id", "legacy_attempt_id")})
    before = _old_rows(connection)
    before_schema = old_structure(connection)
    module = migration("0008_generation_job_leases")

    def unexpected_ddl(*args, **kwargs):
        pytest.fail("historical epoch preflight must precede every additive DDL")

    monkeypatch.setattr(module.op, "add_column", unexpected_ddl)
    settings_query = sa.text("SELECT current_setting('lock_timeout'), "
                             "current_setting('statement_timeout')")
    settings_before = tuple(connection.execute(settings_query).one())
    with pytest.raises(RuntimeError, match="positive job-linked historical lease epochs"):
        # A Core savepoint is immediate; rollback preserves the prior fixture
        # and restores SET LOCAL values without touching the outer transaction.
        with connection.begin_nested():
            module.upgrade()
    assert _old_rows(connection) == before
    assert old_structure(connection) == before_schema
    assert tuple(connection.execute(settings_query).one()) == settings_before
    assert connection.scalar(sa.text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid=p.pronamespace WHERE n.nspname=current_schema() "
        "AND p.proname='generation_job_lease_guard'")) == 0


@pytest.mark.parametrize("configured,expected", [
    ((0, 0), (5000, 15000)), ((100, 200), (100, 200)),
])
def test_migration_locks_both_history_sources_with_bounded_waits(
        schema_connection, monkeypatch, configured, expected):
    connection = schema_connection
    _prior(connection)
    for name, value in zip(("lock_timeout", "statement_timeout"), configured):
        connection.execute(sa.text("SELECT set_config(:name, :value, true)"),
                           {"name": name, "value": f"{value}ms"})
    module = migration("0008_generation_job_leases")
    add_column = module.op.add_column

    def checked_add_column(*args, **kwargs):
        assert dict(connection.execute(sa.text(
            "SELECT name, setting::int FROM pg_settings "
            "WHERE name IN ('lock_timeout', 'statement_timeout')"
        )).all()) == dict(zip(("lock_timeout", "statement_timeout"), expected))
        locked = set(connection.execute(sa.text("""
            SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid=l.relation
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE l.pid=pg_backend_pid() AND l.granted
              AND n.nspname=current_schema() AND l.mode='AccessExclusiveLock'
        """)).scalars())
        assert {"generation_jobs", "generation_executions"} <= locked
        return add_column(*args, **kwargs)

    monkeypatch.setattr(module.op, "add_column", checked_add_column)
    settings_query = sa.text("SELECT current_setting('lock_timeout'), "
                             "current_setting('statement_timeout')")
    before = tuple(connection.execute(settings_query).one())
    module.upgrade()
    assert tuple(connection.execute(settings_query).one()) == before
    module.downgrade()
    assert tuple(connection.execute(settings_query).one()) == before


def test_lease_columns_and_constraints_match_model_metadata(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    inspector = sa.inspect(connection)
    actual = {c["name"]: c for c in inspector.get_columns("generation_jobs")}
    for name in LEASE_COLUMNS:
        model = GenerationJob.__table__.c[name]
        assert actual[name]["type"].compile(dialect=connection.dialect) == model.type.compile(
            dialect=connection.dialect,
        )
        if name in {"lease_heartbeat_at", "lease_expires_at", "lease_deadline_at"}:
            assert actual[name]["type"].timezone is True
            assert model.type.timezone is True
        assert actual[name]["nullable"] == model.nullable
        if name == "lease_epoch":
            assert actual[name]["default"] in {"0", "'0'::bigint"}
            assert str(model.server_default.arg).strip("'") == "0"
        else:
            assert actual[name]["default"] is None and model.server_default is None
    checks = {c["name"] for c in inspector.get_check_constraints("generation_jobs")}
    model_checks = {c.name for c in GenerationJob.__table__.constraints
                    if isinstance(c, sa.CheckConstraint)}
    expected = {"ck_gen_job_lease_epoch", "ck_gen_job_lease_timing", "ck_gen_job_lease_owner"}
    assert expected <= checks and expected <= model_checks


@pytest.mark.parametrize("terminal", ["failed", "success", "partial_failed", "cancelled"])
@pytest.mark.parametrize("epoch_change", ["lease_epoch", "lease_epoch + 1"])
def test_terminal_cannot_reenter_running_without_new_queued_claim(schema_connection, terminal, epoch_change):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection)
    _claim(connection, job_id)
    connection.execute(sa.text("UPDATE generation_jobs SET status=:status WHERE id=:id"),
                       {"status": terminal, "id": job_id})
    _reject(connection, "UPDATE generation_jobs SET status='running', "
            f"lease_epoch={epoch_change} WHERE id=:id", job_id=job_id)
    connection.execute(sa.text("UPDATE generation_jobs SET status='queued' WHERE id=:id"), {"id": job_id})
    _claim(connection, job_id)
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"), {"id": job_id}) == 2


@pytest.mark.parametrize("assignment", [
    "lease_epoch=0", "lease_epoch=2", "locked_by='replacement'", "locked_by=NULL",
    "locked_at=locked_at + interval '1 second'", "locked_at=NULL",
    "lease_deadline_at=lease_deadline_at + interval '1 second'", "lease_ttl_seconds=11",
    "lease_heartbeat_interval_seconds=2", "lease_heartbeat_at=NULL",
    "lease_heartbeat_at=lease_heartbeat_at - interval '1 second'",
])
def test_same_epoch_identity_and_policy_cannot_be_replaced(schema_connection, assignment):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection)
    _claim(connection, job_id)
    _reject(connection, f"UPDATE generation_jobs SET {assignment} WHERE id=:id", job_id=job_id)


def test_claim_cannot_reuse_or_jump_epoch(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection)
    for increment in (0, 2):
        _reject(connection, "UPDATE generation_jobs SET status='running', "
                f"lease_epoch=lease_epoch+{increment}, locked_by='test-worker', "
                "locked_at=clock_timestamp() WHERE id=:id", job_id=job_id)
    _claim(connection, job_id)
    connection.execute(sa.text("UPDATE generation_jobs SET status='failed', locked_by=NULL, "
                               "locked_at=NULL WHERE id=:id"), {"id": job_id})
    connection.execute(sa.text("UPDATE generation_jobs SET status='queued' WHERE id=:id"), {"id": job_id})
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"), {"id": job_id}) == 1
    _claim(connection, job_id)
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"), {"id": job_id}) == 2


def test_legacy_running_insert_does_not_create_lease_authority(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection, status="running")
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"), {"id": job_id}) == 0
    _reject(connection, "UPDATE generation_jobs SET lease_epoch=1 WHERE id=:id", job_id=job_id)


def test_insert_cannot_fabricate_an_allocated_lease(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    with pytest.raises(DBAPIError) as failure:
        with connection.begin_nested():
            connection.execute(sa.text("""
                INSERT INTO generation_jobs
                    (job_type, status, target_date, provider, dedupe_key, lease_epoch,
                     locked_by, locked_at)
                VALUES ('manual', 'running', '2026-11-16', 'stub', :dedupe, 1,
                        'fabricated-owner', clock_timestamp())
            """), {"dedupe": str(uuid4())})
    assert failure.value.orig.sqlstate == "23514"
    assert connection.scalar(sa.text("SELECT count(*) FROM generation_jobs")) == 0


def test_rolled_back_claim_does_not_consume_committed_epoch(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection)
    with pytest.raises(RuntimeError, match="claim transaction failed"):
        with connection.begin_nested():
            _claim(connection, job_id)
            raise RuntimeError("claim transaction failed")
    row = connection.execute(sa.text("SELECT status, lease_epoch, locked_by FROM generation_jobs "
                                     "WHERE id=:id"), {"id": job_id}).one()
    assert row.status == "queued" and row.lease_epoch == 0 and row.locked_by is None
    _claim(connection, job_id)
    assert connection.scalar(sa.text("SELECT lease_epoch FROM generation_jobs WHERE id=:id"),
                             {"id": job_id}) == 1


@pytest.mark.parametrize("change", [
    "lease_heartbeat_at=NULL", "lease_expires_at=NULL", "lease_deadline_at=NULL",
    "lease_ttl_seconds=NULL", "lease_heartbeat_interval_seconds=NULL",
    "lease_ttl_seconds=0", "lease_heartbeat_interval_seconds=0",
    "lease_heartbeat_interval_seconds=10", "lease_expires_at=lease_heartbeat_at",
    "lease_expires_at=lease_deadline_at + interval '1 second'",
    "lease_deadline_at='infinity'::timestamptz",
])
def test_malformed_timing_tuple_is_rejected(schema_connection, change):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    job_id = _job(connection)
    _claim(connection, job_id)
    _reject(connection, f"UPDATE generation_jobs SET {change} WHERE id=:id", job_id=job_id)


def test_utc_instants_preserved_under_non_utc_session(schema_connection):
    connection = schema_connection
    _prior(connection)
    migration("0008_generation_job_leases").upgrade()
    connection.execute(sa.text("SET LOCAL timezone='America/New_York'"))
    job_id = _job(connection)
    _claim(connection, job_id)
    row = connection.execute(sa.text("SELECT lease_heartbeat_at, lease_expires_at "
                                     "FROM generation_jobs WHERE id=:id"), {"id": job_id}).one()
    assert row.lease_heartbeat_at == NOW
    assert row.lease_expires_at == NOW + timedelta(seconds=10)


def test_unused_downgrade_preserves_legacy_data(schema_connection):
    connection = schema_connection
    _prior(connection)
    legacy(connection)
    before = _old_rows(connection)
    module = migration("0008_generation_job_leases")
    module.upgrade()
    module.downgrade()
    assert not set(LEASE_COLUMNS) & {c["name"] for c in sa.inspect(connection).get_columns("generation_jobs")}
    assert _old_rows(connection) == before
    module.upgrade()


def test_allocated_epoch_prevents_destructive_downgrade(schema_connection):
    connection = schema_connection
    _prior(connection)
    module = migration("0008_generation_job_leases")
    module.upgrade()
    job_id = _job(connection)
    _claim(connection, job_id, timed=False)
    before = dict(connection.execute(sa.text("SELECT * FROM generation_jobs WHERE id=:id"),
                                     {"id": job_id}).mappings().one())
    with pytest.raises(DBAPIError) as failure:
        with connection.begin_nested():
            module.downgrade()
    assert failure.value.orig.sqlstate == "55000"
    assert dict(connection.execute(sa.text("SELECT * FROM generation_jobs WHERE id=:id"),
                                   {"id": job_id}).mappings().one()) == before
    assert set(LEASE_COLUMNS) <= {c["name"] for c in sa.inspect(connection).get_columns("generation_jobs")}


def test_failed_migration_rolls_back_additive_objects(schema_connection, monkeypatch):
    connection = schema_connection
    _prior(connection)
    legacy(connection)
    before = _old_rows(connection)
    module = migration("0008_generation_job_leases")
    original = module.op.execute

    def failed_execute(statement, *args, **kwargs):
        if str(statement).startswith("CREATE TRIGGER"):
            raise RuntimeError("injected lease migration failure")
        return original(statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module.op, "execute", failed_execute)
        with pytest.raises(RuntimeError, match="injected lease migration failure"):
            with connection.begin_nested():
                module.upgrade()
    assert _old_rows(connection) == before
    assert not set(LEASE_COLUMNS) & {c["name"] for c in sa.inspect(connection).get_columns("generation_jobs")}
    module.upgrade()

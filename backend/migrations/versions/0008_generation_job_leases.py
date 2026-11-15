"""Add lease epoch and opt-in bounded timing state (no automatic renewal).

Revision ID: 0008_generation_job_leases
Revises: 0007_generation_scope_admission

Prepared after parent design review; the orchestrator owns migration integration.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_generation_job_leases"
down_revision = "0007_generation_scope_admission"
branch_labels = None
depends_on = None


TIMING_CHECK = """
(
    lease_heartbeat_at IS NULL AND lease_expires_at IS NULL
    AND lease_deadline_at IS NULL AND lease_ttl_seconds IS NULL
    AND lease_heartbeat_interval_seconds IS NULL
) OR (
    lease_heartbeat_at IS NOT NULL AND lease_expires_at IS NOT NULL
    AND lease_deadline_at IS NOT NULL AND lease_ttl_seconds IS NOT NULL
    AND lease_heartbeat_interval_seconds IS NOT NULL
    AND lease_epoch > 0
    AND lease_heartbeat_interval_seconds > 0
    AND lease_ttl_seconds > lease_heartbeat_interval_seconds
    AND isfinite(lease_heartbeat_at) AND isfinite(lease_expires_at)
    AND isfinite(lease_deadline_at)
    AND lease_heartbeat_at < lease_expires_at
    AND lease_expires_at <= lease_deadline_at
    AND lease_expires_at <= lease_heartbeat_at + make_interval(secs => lease_ttl_seconds)
)
"""

OWNER_CHECK = """
lease_epoch = 0 OR status <> 'running' OR (
    locked_by IS NOT NULL AND length(btrim(locked_by)) > 0
    AND locked_at IS NOT NULL AND isfinite(locked_at)
)
"""

EPOCH_GUARD_SQL = """
CREATE FUNCTION generation_job_lease_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.lease_epoch <> 0 THEN
            RAISE EXCEPTION 'job lease epoch must start unallocated'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status = 'running' AND OLD.status <> 'running' AND OLD.status <> 'queued' THEN
        RAISE EXCEPTION 'job may enter running only through a queued claim'
            USING ERRCODE = '23514';
    END IF;

    IF OLD.status = 'queued' AND NEW.status = 'running' THEN
        IF OLD.lease_epoch = 9223372036854775807
           OR NEW.lease_epoch <> OLD.lease_epoch + 1 THEN
            RAISE EXCEPTION 'job claim requires the next lease epoch'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.lease_heartbeat_at IS NOT NULL AND (
            NEW.lease_heartbeat_at IS DISTINCT FROM NEW.locked_at
            OR NEW.lease_expires_at IS DISTINCT FROM
                NEW.locked_at + make_interval(secs => NEW.lease_ttl_seconds)
            OR NEW.lease_deadline_at < NEW.lease_expires_at
        ) THEN
            RAISE EXCEPTION 'job claim timing must begin at its lock timestamp'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF NEW.lease_epoch IS DISTINCT FROM OLD.lease_epoch THEN
            RAISE EXCEPTION 'job lease epoch may only advance on a new claim'
                USING ERRCODE = '23514';
        END IF;
        IF OLD.lease_epoch > 0 AND OLD.status = 'running' AND NEW.status = 'running'
           AND ROW(NEW.locked_by, NEW.locked_at)
               IS DISTINCT FROM ROW(OLD.locked_by, OLD.locked_at) THEN
            RAISE EXCEPTION 'job lease owner and claim time are fixed for its epoch'
                USING ERRCODE = '23514';
        END IF;
        IF ROW(NEW.lease_deadline_at, NEW.lease_ttl_seconds,
               NEW.lease_heartbeat_interval_seconds)
           IS DISTINCT FROM
           ROW(OLD.lease_deadline_at, OLD.lease_ttl_seconds,
               OLD.lease_heartbeat_interval_seconds) THEN
            RAISE EXCEPTION 'job lease policy is fixed for its epoch'
                USING ERRCODE = '23514';
        END IF;
        IF OLD.lease_heartbeat_at IS NOT NULL AND (
            NEW.lease_heartbeat_at IS NULL OR NEW.lease_expires_at IS NULL
            OR NEW.lease_heartbeat_at < OLD.lease_heartbeat_at
            OR NEW.lease_expires_at < OLD.lease_expires_at
        ) THEN
            RAISE EXCEPTION 'job lease timing cannot move backward within its epoch'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""


def _postgresql_connection():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Generation job leases require PostgreSQL.")
    return connection


def _bound_timeouts(connection):
    previous = connection.execute(sa.text(
        "SELECT name, setting::bigint, current_setting(name) FROM pg_settings "
        "WHERE name IN ('lock_timeout', 'statement_timeout')"
    )).all()
    limits = {"lock_timeout": 5000, "statement_timeout": 15000}
    for name, current_ms, _ in previous:
        timeout_ms = min(current_ms, limits[name]) if current_ms else limits[name]
        connection.execute(sa.text("SELECT set_config(:name, :value, true)"),
                           {"name": name, "value": f"{timeout_ms}ms"})
    return previous


def _restore_timeouts(connection, previous):
    for name, _, value in previous:
        connection.execute(sa.text("SELECT set_config(:name, :value, true)"),
                           {"name": name, "value": value})


def upgrade() -> None:
    connection = _postgresql_connection()
    previous = _bound_timeouts(connection)
    # 0006 permits positive job-linked snapshots, without allocating a job
    # epoch. Starting those jobs at zero could reuse historical authority.
    # Lock both sources before the check and retain locks through the DDL.
    connection.execute(sa.text(
        "LOCK TABLE generation_jobs, generation_executions IN ACCESS EXCLUSIVE MODE"
    ))
    if connection.scalar(sa.text("""
        SELECT EXISTS (SELECT 1 FROM generation_executions
                       WHERE job_id IS NOT NULL AND lease_epoch > 0)
    """)):
        # No inference/backfill or history mutation; the Alembic transaction
        # owner must roll back, as for 0007's historical-conflict refusal.
        raise RuntimeError(
            "Generation lease migration blocked: positive job-linked historical "
            "lease epochs exist. Authorized historical inspection/reconciliation "
            "is required; no schema or generation history has been changed."
        )
    op.add_column("generation_jobs", sa.Column(
        "lease_epoch", sa.BigInteger(), nullable=False, server_default="0"))
    for name in ("lease_heartbeat_at", "lease_expires_at", "lease_deadline_at"):
        op.add_column("generation_jobs", sa.Column(name, sa.DateTime(timezone=True)))
    for name in ("lease_ttl_seconds", "lease_heartbeat_interval_seconds"):
        op.add_column("generation_jobs", sa.Column(name, sa.Integer()))
    op.create_check_constraint("ck_gen_job_lease_epoch", "generation_jobs", "lease_epoch >= 0")
    op.create_check_constraint("ck_gen_job_lease_timing", "generation_jobs", TIMING_CHECK)
    op.create_check_constraint("ck_gen_job_lease_owner", "generation_jobs", OWNER_CHECK)
    op.execute(EPOCH_GUARD_SQL)
    op.execute("""CREATE TRIGGER trg_generation_job_lease_guard
        BEFORE INSERT OR UPDATE ON generation_jobs
        FOR EACH ROW EXECUTE FUNCTION generation_job_lease_guard()""")
    _restore_timeouts(connection, previous)


def downgrade() -> None:
    connection = _postgresql_connection()
    previous = _bound_timeouts(connection)
    # Serialize the refusal check with new claims before dropping any evidence.
    op.execute("LOCK TABLE generation_jobs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM generation_jobs WHERE lease_epoch > 0
                   OR lease_heartbeat_at IS NOT NULL OR lease_expires_at IS NOT NULL
                   OR lease_deadline_at IS NOT NULL OR lease_ttl_seconds IS NOT NULL
                   OR lease_heartbeat_interval_seconds IS NOT NULL) THEN
            RAISE EXCEPTION 'cannot downgrade allocated generation job leases'
                USING ERRCODE = '55000';
        END IF;
    END $$""")
    op.execute("DROP TRIGGER trg_generation_job_lease_guard ON generation_jobs")
    op.execute("DROP FUNCTION generation_job_lease_guard()")
    for name in ("ck_gen_job_lease_owner", "ck_gen_job_lease_timing", "ck_gen_job_lease_epoch"):
        op.drop_constraint(name, "generation_jobs", type_="check")
    for name in ("lease_heartbeat_interval_seconds", "lease_ttl_seconds", "lease_deadline_at",
                 "lease_expires_at", "lease_heartbeat_at", "lease_epoch"):
        op.drop_column("generation_jobs", name)
    _restore_timeouts(connection, previous)

"""Explicit-only bounded lease renewal; no heartbeat thread or recovery writer.

The caller supplies the identity captured at its committed claim. This helper
never derives a newer epoch from an ORM refresh and never uses the caller's
Session. Production remains blocked by the execution-start activation policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from .. import db
from .generation_execution_service import ExecutionStartError, require_execution_activation
from .generation_lease_policy import LeaseIdentity, LeaseTiming, plan_lease_renewal


# Match the existing readiness query-safety convention. These do not define a
# production lease policy or an end-to-end DNS/network wall-clock deadline.
CONNECT_TIMEOUT_SECONDS = 2
STATEMENT_TIMEOUT_MS = 1000
LOCK_TIMEOUT_MS = 1000


@dataclass(frozen=True)
class LeaseRenewalResult:
    status: str
    timing: LeaseTiming | None = None


def _renewal_engine(database_url):
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Lease renewal requires PostgreSQL with psycopg.")
    options = url.query.get("options", "")
    if not isinstance(options, str):
        raise ValueError("Invalid PostgreSQL startup options.")
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": (
                f"{options} -c statement_timeout={STATEMENT_TIMEOUT_MS}"
                f" -c lock_timeout={LOCK_TIMEOUT_MS}"
            ).strip(),
        },
        hide_parameters=True,
        echo=False,
    )


def _database_utcnow(connection):
    return connection.scalar(text("SELECT clock_timestamp()")).astimezone(timezone.utc)


def _renew_locked(connection, identity: LeaseIdentity, mode: str) -> LeaseRenewalResult:
    parameters = {"job_id": identity.job_id, "owner": identity.owner, "epoch": identity.epoch}
    row = connection.execute(text("""
        SELECT id, provider, target_date, locale, forecast_type, lease_heartbeat_at,
               lease_expires_at, lease_deadline_at, lease_ttl_seconds,
               lease_heartbeat_interval_seconds
        FROM generation_jobs
        WHERE id = :job_id AND status = 'running' AND locked_by = :owner
          AND lease_epoch = :epoch
        FOR UPDATE NOWAIT
    """), parameters).mappings().one_or_none()
    if row is None:
        return LeaseRenewalResult("lost")

    matched = connection.scalar(text("""
        SELECT 1 FROM generation_executions
        WHERE id = :execution_id AND job_id = :job_id AND lease_epoch = :epoch
          AND origin = 'queue_worker' AND deployment_mode = :mode
          AND provider = :provider AND target_date = :target_date
          AND locale = :locale AND forecast_type = :forecast_type
    """), {
        **parameters, "execution_id": identity.execution_id, "mode": mode,
        **{name: row[name] for name in ("provider", "target_date", "locale", "forecast_type")},
    })
    if matched is None:
        return LeaseRenewalResult("lost")

    timing_fields = (
        "lease_heartbeat_at", "lease_expires_at", "lease_deadline_at",
        "lease_ttl_seconds", "lease_heartbeat_interval_seconds",
    )
    if all(row[name] is None for name in timing_fields):
        return LeaseRenewalResult("disabled")
    # Partial/corrupt snapshots fail validation; no fallback or inferred policy.
    timing = LeaseTiming(*(row[name] for name in timing_fields))
    now = _database_utcnow(connection)
    plan = plan_lease_renewal(timing, now=now)
    if plan.status != "renewed":
        return LeaseRenewalResult(plan.status, timing)

    changed = connection.execute(text("""
        UPDATE generation_jobs
        SET lease_heartbeat_at = :now, lease_expires_at = :expires_at
        WHERE id = :job_id AND status = 'running' AND locked_by = :owner
          AND lease_epoch = :epoch AND lease_expires_at > :now
          AND lease_deadline_at > :now
        RETURNING id
    """), {**parameters, "now": now, "expires_at": plan.timing.expires_at}).scalar_one_or_none()
    if changed is None:
        return LeaseRenewalResult("lost")
    return LeaseRenewalResult("renewed", plan.timing)


def renew_generation_job_lease(identity: LeaseIdentity) -> LeaseRenewalResult:
    """Renew only a current nonproduction claim; never dispatch/requeue a job.

    A returned 'renewed' requires confirmed transaction exit. On commit or
    connection failure the result is 'unavailable', even if the commit outcome
    itself is uncertain. Such a result confers no new execution permission.
    """
    if not isinstance(identity, LeaseIdentity):
        raise TypeError("Lease renewal requires a captured LeaseIdentity.")
    try:
        mode = require_execution_activation()
    except ExecutionStartError:
        return LeaseRenewalResult("disabled")

    engine = None
    result = LeaseRenewalResult("unavailable")
    try:
        engine = _renewal_engine(db.engine.url)
        with engine.begin() as connection:
            result = _renew_locked(connection, identity, mode)
    except DBAPIError as exc:
        result = LeaseRenewalResult(
            "busy" if getattr(exc.orig, "sqlstate", None) in {"55P03", "40P01", "40001"}
            else "unavailable"
        )
    except Exception:
        # Sanitized operational result, not exception text or a false renewal.
        # BaseException-derived STAB-007 violations still escape to fail tests.
        result = LeaseRenewalResult("unavailable")
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                result = LeaseRenewalResult("unavailable")
    return result

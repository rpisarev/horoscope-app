"""Transaction-owned immutable execution starts, distinct from paid admission.

There is deliberately no production activation switch in this prerequisite.
Writers flush/execute in their supplied Session, never commit or roll it back.
"""
from __future__ import annotations

import os
import re
from datetime import date, timezone
from uuid import UUID, uuid5

from flask import current_app
from sqlalchemy import event, func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapper, Session
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.dml import UpdateBase

from ..models import GenerationExecution, GenerationExecutionRun, GenerationJob
from .generation_lease_policy import captured_lease_identity


EXECUTION_POLICY_VERSION = "execution-start-v1"
CLAIM_NAMESPACE = UUID("a44755ca-c33d-4d24-aea2-baf85381319f")
_WRITES_KEY = "generation_execution_caller_writes"


class ExecutionStartError(RuntimeError):
    retryable = False


class ExecutionAlreadyStarted(ExecutionStartError):
    pass


class GenerationClaimLost(ExecutionStartError):
    """A stale/missing claim must not enter a failure writer for its successor."""


def deployment_mode() -> str:
    mode = current_app.config.get("APP_DEPLOYMENT_MODE")
    if not isinstance(mode, str) or mode.strip().lower() not in {
        "development", "test", "production"
    }:
        raise ExecutionStartError("Execution requires a valid APP_DEPLOYMENT_MODE.")
    return mode.strip().lower()


def require_execution_activation() -> str:
    mode = deployment_mode()
    if mode == "production":
        raise ExecutionStartError(
            "Production execution is blocked pending atomic paid admission, "
            "complete fencing and the remaining STAB-015 rollout prerequisites."
        )
    return mode


def selected_provider_name(provider_name: str | None = None) -> str:
    """Use the same selection as the factory, not its returned text metadata."""
    return (provider_name or os.getenv("HOROSCOPE_PROVIDER") or "stub").strip().lower()


def claim_execution_id(job) -> UUID:
    # attempt_count is a correlation key only; never a fabricated lease epoch.
    if not isinstance(job.id, int) or job.id < 1 or not isinstance(
        job.attempt_count, int
    ) or isinstance(job.attempt_count, bool) or job.attempt_count < 1:
        raise ExecutionStartError("Execution requires a persisted, claimed job.")
    return uuid5(CLAIM_NAMESPACE, f"job:{job.id}:claim:{job.attempt_count}")


def _remember_flush(session, flush_context):
    if session.new or session.dirty or session.deleted:
        session.info[_WRITES_KEY] = True


def _remember_dml(state):
    # Text may contain DML or writable CTEs. Conservatively require its owner to
    # finish the transaction even for textual SELECT; do not try to parse SQL.
    if any(isinstance(node, (TextClause, UpdateBase))
           for node in visitors.iterate(state.statement)):
        state.session.info[_WRITES_KEY] = True


def _forget_writes(session, transaction):
    if transaction.parent is None:
        session.info.pop(_WRITES_KEY, None)


# Fake-module imports in pure policy tests must not register global listeners.
if (isinstance(GenerationExecution, type) and isinstance(
    inspect(GenerationExecution, raiseerr=False), Mapper
) and not getattr(Session, "_generation_execution_ownership_hooks_registered", False)):
    event.listen(Session, "after_flush", _remember_flush)
    event.listen(Session, "do_orm_execute", _remember_dml)
    event.listen(Session, "after_transaction_end", _forget_writes)
    Session._generation_execution_ownership_hooks_registered = True


def assert_autonomous_session_clean(session: Session) -> None:
    """Reject caller-owned ORM changes before autonomous lifecycle commits."""
    if (session.new or session.dirty or session.deleted
            or session.info.get(_WRITES_KEY)):
        raise ExecutionStartError(
            "Commit or roll back caller-owned writes before starting generation."
        )


def _database_utcnow(session: Session):
    return session.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)


def _require_postgresql(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise ExecutionStartError("Execution ledger writers require PostgreSQL.")


def record_execution_start(
    session: Session, *, execution_id: UUID, origin: str, provider: str,
    target_date: date, locale: str, forecast_type: str,
    job_id: int | None = None, lease_epoch: int | None = None,
) -> GenerationExecution:
    """Insert or exactly replay a start in the caller's transaction.

    Replaying the same UUID retains its original timestamp. A different snapshot
    is an error; ON CONFLICT never updates immutable history. Lease provenance is
    supplied by the claim allocator, not synthesized by this writer.
    """
    mode = require_execution_activation()
    _require_postgresql(session)
    if origin not in {"queue_worker", "dev_direct"}:
        raise ExecutionStartError("Unsupported lifecycle execution origin.")
    if not isinstance(execution_id, UUID):
        raise ExecutionStartError("Execution identity must be a UUID.")
    if not isinstance(provider, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", provider):
        raise ExecutionStartError("Execution requires canonical provider identity.")
    values = dict(
        id=execution_id, job_id=job_id, origin=origin, deployment_mode=mode,
        provider=provider, target_date=target_date, locale=locale,
        forecast_type=forecast_type, policy_version=EXECUTION_POLICY_VERSION,
        lease_epoch=lease_epoch,
    )
    with session.no_autoflush:
        session.execute(insert(GenerationExecution).values(
            **values, started_at=_database_utcnow(session)
        ).on_conflict_do_nothing(index_elements=[GenerationExecution.id]))
        row = session.get(GenerationExecution, execution_id, populate_existing=True)
    if row is None or any(getattr(row, key) != value for key, value in values.items()):
        raise ExecutionStartError("Execution identity replay does not match its snapshot.")
    return row


def link_execution_run(
    session: Session, *, execution_id: UUID, run_id: int,
) -> GenerationExecutionRun:
    """Append a link or exactly replay it; never rebind an existing execution."""
    _require_postgresql(session)
    with session.no_autoflush:
        session.execute(insert(GenerationExecutionRun).values(
            execution_id=execution_id, run_id=run_id,
            linked_at=_database_utcnow(session),
        ).on_conflict_do_nothing(index_elements=[GenerationExecutionRun.execution_id]))
        link = session.get(GenerationExecutionRun, execution_id, populate_existing=True)
    if link is None or link.run_id != run_id:
        raise ExecutionStartError("Execution identity is already linked to a different run.")
    return link


def unlinked_claim_execution(session: Session, job) -> GenerationExecution:
    """Require the exact committed claim snapshot before lifecycle dispatch."""
    identity = captured_lease_identity(job)
    row = session.get(GenerationExecution, identity.execution_id)
    if row is None or any((
        row.job_id != job.id, row.origin != "queue_worker",
        row.provider != job.provider, row.target_date != job.target_date,
        row.locale != job.locale, row.forecast_type != job.forecast_type,
        row.deployment_mode != deployment_mode(),
        row.lease_epoch != identity.epoch, row.job_id != identity.job_id,
    )):
        raise ExecutionStartError("No matching immutable execution for this claim.")
    if session.get(GenerationExecutionRun, identity.execution_id) is not None:
        raise ExecutionAlreadyStarted("This claim already started a generation run.")
    _require_current_execution_epoch(session, row)
    return row


def _require_current_execution_epoch(session: Session, execution: GenerationExecution) -> None:
    # Read scalars from PostgreSQL, not possibly stale ORM identity-map columns.
    # This is admission-time validation only; it does not fence later writers.
    if execution.lease_epoch is None or execution.lease_epoch <= 0:
        raise GenerationClaimLost("Queue execution has no allocated lease epoch.")
    current = session.execute(select(
        GenerationJob.lease_heartbeat_at, GenerationJob.lease_expires_at,
        GenerationJob.lease_deadline_at,
    ).where(
        GenerationJob.id == execution.job_id,
        GenerationJob.status == "running",
        GenerationJob.lease_epoch == execution.lease_epoch,
    )).one_or_none()
    if current is None:
        raise GenerationClaimLost("Queue execution lease ownership changed.")
    if current.lease_expires_at is not None:
        now = _database_utcnow(session)
        if (now < current.lease_heartbeat_at or now >= current.lease_expires_at
                or now >= current.lease_deadline_at):
            raise GenerationClaimLost("Queue execution timed lease is no longer valid.")


def require_unlinked_execution(
    session: Session, *, execution_id: UUID, provider: str,
    target_date: date, locale: str, forecast_type: str,
) -> GenerationExecution:
    row = session.get(GenerationExecution, execution_id)
    if row is None or any((
        row.origin != "queue_worker", row.provider != provider,
        row.target_date != target_date, row.locale != locale,
        row.forecast_type != forecast_type, row.deployment_mode != deployment_mode(),
    )):
        raise ExecutionStartError("Lifecycle execution does not match the admitted claim.")
    if session.get(GenerationExecutionRun, execution_id) is not None:
        raise ExecutionAlreadyStarted("This execution already started a generation run.")
    _require_current_execution_epoch(session, row)
    return row

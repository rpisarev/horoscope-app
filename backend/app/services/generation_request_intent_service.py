"""Transaction-owned ledger primitives, NOT paid admission or transport permits.

Caller must provide an active PostgreSQL Core transaction. No ORM autoflush,
outer commit/rollback, provider, publication, recovery or refund occurs here.
Future .03c must compose intent insertion with its atomic cap checks; current
application paid transport must remain unavailable until that chain is complete.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from ..models import GenerationApiObservation, GenerationApiRequest, GenerationExecution


EXECUTIONS = GenerationExecution.__table__
REQUESTS = GenerationApiRequest.__table__
OBSERVATIONS = GenerationApiObservation.__table__
LOCK_TIMEOUT_MS = 1000
STATEMENT_TIMEOUT_MS = 5000
MAX_OBSERVATIONS = 200


class RequestIntentError(RuntimeError):
    """Sanitized local protocol error, never permission to retry transport."""

    retryable = False


class RequestIntentConflict(RequestIntentError):
    pass


@dataclass(frozen=True)
class RequestIntentReceipt:
    id: UUID
    execution_id: UUID
    request_no: int
    admitted_at: datetime
    admission_day: date


@dataclass(frozen=True)
class RequestObservationReceipt:
    id: UUID
    request_id: UUID
    observation_no: int
    recorded_at: datetime


def _uuid(value: UUID, field: str) -> UUID:
    if not isinstance(value, UUID):
        raise RequestIntentError(f"{field} must be a UUID.")
    return value


def _positive(value: int | None, field: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int or value < 1:
        raise RequestIntentError(f"{field} must be a positive integer.")
    return value


def _text(value: str | None, field: str, maximum: int, *, nullable: bool = False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RequestIntentError(f"Invalid {field}.")
    # Reject controls rather than reflecting untrusted fields in diagnostics.
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise RequestIntentError(f"Invalid {field}.")
    return value


def _require_transaction(connection: Connection) -> None:
    if not isinstance(connection, Connection) or not connection.in_transaction():
        raise RequestIntentError("An active caller-owned Core transaction is required.")
    if connection.dialect.name != "postgresql":
        raise RequestIntentError("Ledger protocol requires PostgreSQL.")
    # SQLAlchemy can report a logical transaction even with DBAPI autocommit.
    if getattr(connection.connection.dbapi_connection, "autocommit", True) is not False:
        raise RequestIntentError("Ledger protocol rejects DBAPI autocommit.")


@contextmanager
def _bounded_operation(connection: Connection) -> Iterator[None]:
    _require_transaction(connection)
    # Connection.begin_nested emits the Core SAVEPOINT immediately, unlike a
    # lazy Session.begin_nested boundary. No ORM flush occurs. Error rollback
    # restores only this savepoint/settings; the outer owner decides next.
    with connection.begin_nested():
        previous = {
            name: connection.scalar(select(func.current_setting(name)))
            for name in ("lock_timeout", "statement_timeout")
        }
        for name, maximum in (("lock_timeout", LOCK_TIMEOUT_MS), ("statement_timeout", STATEMENT_TIMEOUT_MS)):
            prior_ms = int(connection.scalar(text("SELECT setting FROM pg_settings WHERE name = :name"), {"name": name}))
            effective = min(prior_ms, maximum) if prior_ms else maximum
            connection.execute(select(func.set_config(name, f"{effective}ms", True)))
        yield
        for name, value in previous.items():
            connection.execute(select(func.set_config(name, value, True)))


def _request_receipt(row) -> RequestIntentReceipt:
    return RequestIntentReceipt(**{field: row[field] for field in RequestIntentReceipt.__dataclass_fields__})


def _observation_receipt(row) -> RequestObservationReceipt:
    return RequestObservationReceipt(**{field: row[field] for field in RequestObservationReceipt.__dataclass_fields__})


def _exact_replay(row, fields: dict, message: str) -> None:
    if any(row[key] != value for key, value in fields.items()):
        raise RequestIntentConflict(message)


def insert_request_intent(
    connection: Connection,
    *,
    request_id: UUID,
    execution_id: UUID,
    request_no: int,
    run_id: int | None,
    item_id: int | None,
    legacy_attempt_id: int | None = None,
    admission_scope: str,
    policy_version: str,
) -> RequestIntentReceipt:
    """Insert/replay one intent in the owner's transaction, WITHOUT admission.

    Clock time is database-owned. A returned receipt may still be rolled back
    by the caller, and even a committed receipt never authorizes an HTTP call.
    Caller supplies the stable request ordinal; allocation/cap ownership is .03c.
    """
    fields = dict(
        id=_uuid(request_id, "request_id"),
        execution_id=_uuid(execution_id, "execution_id"),
        request_no=_positive(request_no, "request_no"),
        run_id=_positive(run_id, "run_id", nullable=True),
        item_id=_positive(item_id, "item_id", nullable=True),
        legacy_attempt_id=_positive(legacy_attempt_id, "legacy_attempt_id", nullable=True),
        admission_scope=_text(admission_scope, "admission_scope", 128),
        policy_version=_text(policy_version, "policy_version", 128),
    )
    try:
        with _bounded_operation(connection):
            execution = connection.execute(
                select(EXECUTIONS.c.id).where(EXECUTIONS.c.id == execution_id).with_for_update()
            ).first()
            if execution is None:
                raise RequestIntentError("Execution does not exist.")
            existing = connection.execute(select(REQUESTS).where(REQUESTS.c.id == request_id)).mappings().first()
            if existing is not None:
                _exact_replay(existing, fields, "Request identity has conflicting immutable fields.")
                return _request_receipt(existing)
            occupied = connection.execute(select(REQUESTS.c.id).where(
                REQUESTS.c.execution_id == execution_id, REQUESTS.c.request_no == request_no,
            )).first()
            if occupied is not None:
                raise RequestIntentConflict("Request ordinal already belongs to another identity.")
            row = connection.execute(REQUESTS.insert().values(
                **fields, admitted_at=func.clock_timestamp(),
            ).returning(*REQUESTS.c)).mappings().one()
            return _request_receipt(row)
    except IntegrityError as exc:
        # A different execution may race on the same UUID. Only identity-related
        # unique conflicts are normalized; FK/check/other integrity errors survive.
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if getattr(exc.orig, "sqlstate", None) == "23505" and name in {
            "generation_api_requests_pkey", "uq_gen_request_execution_no",
        }:
            raise RequestIntentConflict("Request identity or ordinal already exists.") from exc
        raise


def append_request_observation(
    connection: Connection,
    *,
    observation_id: UUID,
    request_id: UUID,
    outcome: str,
    evidence_code: str | None = None,
    provider_request_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    usage_source: str | None = None,
    model_name: str | None = None,
) -> RequestObservationReceipt:
    """Append exact evidence; never claim not_sent without a proof protocol.

    Caller must already have reliable evidence for succeeded/failed. No exception
    classifier or timestamp heuristic turns uncertainty into certainty here.
    Usage provenance and source extraction policy remain .02d responsibilities.
    """
    if not isinstance(outcome, str) or outcome not in {"unknown", "succeeded", "failed"}:
        raise RequestIntentError("Unsupported outcome; not_sent requires a future proof protocol.")
    for value in (input_tokens, output_tokens):
        if value is not None and (type(value) is not int or value < 0):
            raise RequestIntentError("Token usage must be a nonnegative integer or unknown.")
    if (input_tokens is not None or output_tokens is not None) and (usage_source is None or model_name is None):
        raise RequestIntentError("Known usage requires source and model provenance.")
    fields = dict(
        id=_uuid(observation_id, "observation_id"),
        request_id=_uuid(request_id, "request_id"),
        outcome=outcome,
        review_state="requires_review" if outcome == "unknown" else "recorded",
        evidence_code=_text(evidence_code, "evidence_code", 128, nullable=True),
        provider_request_id=_text(provider_request_id, "provider_request_id", 255, nullable=True),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usage_source=_text(usage_source, "usage_source", 128, nullable=True),
        model_name=_text(model_name, "model_name", 128, nullable=True),
    )
    try:
        with _bounded_operation(connection):
            request = connection.execute(select(REQUESTS.c.id).where(
                REQUESTS.c.id == request_id,
            ).with_for_update()).first()
            if request is None:
                raise RequestIntentError("Request intent does not exist.")
            existing = connection.execute(select(OBSERVATIONS).where(
                OBSERVATIONS.c.id == observation_id,
            )).mappings().first()
            if existing is not None:
                _exact_replay(existing, fields, "Observation identity has conflicting evidence.")
                return _observation_receipt(existing)
            ordinal = connection.scalar(select(func.coalesce(func.max(OBSERVATIONS.c.observation_no), 0)).where(
                OBSERVATIONS.c.request_id == request_id,
            )) + 1
            row = connection.execute(OBSERVATIONS.insert().values(
                **fields, observation_no=ordinal, recorded_at=func.clock_timestamp(),
            ).returning(*OBSERVATIONS.c)).mappings().one()
            return _observation_receipt(row)
    except IntegrityError as exc:
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if getattr(exc.orig, "sqlstate", None) == "23505" and name in {
            "generation_api_observations_pkey", "uq_gen_observation_request_no",
        }:
            raise RequestIntentConflict("Observation identity or ordinal already exists.") from exc
        raise


def read_request_evidence(connection: Connection, request_id: UUID, *, limit: int = 100) -> dict:
    """Bounded read; missing/truncated/conflicting evidence never grants recovery.

    Returns only ledger metadata, not provider bodies. No latest-row-wins rule:
    any recorded uncertainty still requires review until an authorized future
    resolution protocol exists. A successful provider outcome is not publication.
    """
    _uuid(request_id, "request_id")
    if type(limit) is not int or not 1 <= limit <= MAX_OBSERVATIONS:
        raise RequestIntentError(f"Observation limit must be between 1 and {MAX_OBSERVATIONS}.")
    with _bounded_operation(connection):
        request = connection.execute(select(REQUESTS.c.id).where(REQUESTS.c.id == request_id)).first()
        rows = connection.execute(select(OBSERVATIONS).where(
            OBSERVATIONS.c.request_id == request_id,
        ).order_by(OBSERVATIONS.c.observation_no).limit(limit + 1)).mappings().all() if request else []
        truncated = len(rows) > limit
        rows = rows[:limit]
        outcomes = {row["outcome"] for row in rows}
        conflicting_metadata = any(
            len({row[field] for row in rows if row[field] is not None}) > 1
            for field in ("provider_request_id", "input_tokens", "output_tokens", "usage_source", "model_name")
        )
        certain = (
            bool(rows)
            and not truncated
            and not conflicting_metadata
            and all(row["review_state"] == "recorded" for row in rows)
            and outcomes in ({"succeeded"}, {"failed"})
        )
        return {
            "request_id": str(request_id),
            "request_found": request is not None,
            "outcome": next(iter(outcomes)) if certain else "unknown",
            "review_state": "recorded" if certain else "requires_review",
            "truncated": truncated,
            "observations": [dict(row) for row in rows],
        }

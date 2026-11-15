from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from paid_execution_policy import require_paid_execution
from paid_admission_policy import require_paid_admission
from sqlalchemy import event, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapper, Session

from .. import db
from ..models import GenerationExecution, GenerationExecutionRun, GenerationJob, GenerationRun
from .generation_admission_service import (
    GenerationPackageScope, GenerationScopeBusy, package_scope_lock,
)
from ..providers.publication_policy import require_publication_provider
from ..providers.registry import PROVIDERS
from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .generation_execution_service import (
    ExecutionAlreadyStarted,
    assert_autonomous_session_clean,
    claim_execution_id,
    deployment_mode,
    record_execution_start,
    require_execution_activation,
    unlinked_claim_execution,
)
from .generation_service import (
    get_missing_forecast_signs,
    has_generation_coverage,
    run_daily_generation,
    run_retry_for_missing_forecasts,
)
from .sign_service import get_enabled_sign_keys


JOB_TYPE_MANUAL = "manual"
JOB_TYPE_BACKFILL = "backfill"
JOB_TYPE_RETRY_MISSING = "retry_missing"
JOB_TYPE_SCHEDULED = "scheduled"

SUPPORTED_JOB_TYPES = {
    JOB_TYPE_MANUAL,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_RETRY_MISSING,
    JOB_TYPE_SCHEDULED,
}

SUPPORTED_JOB_PROVIDERS = PROVIDERS.keys()

DEFAULT_OPENAI_MAX_BACKFILL_DAYS = 7
DEFAULT_OPENAI_MAX_JOBS_PER_RUN = 2
DEFAULT_OPENAI_MAX_JOBS_PER_DAY = 10

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_PARTIAL_FAILED = "partial_failed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

ACTIVE_JOB_STATUSES = {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}
ACTIVE_DEDUPE_CONSTRAINT = "uq_generation_jobs_active_dedupe_key"
# One additional write if the conflicting winner finishes before it is reloaded.
DEDUPE_WRITE_ATTEMPTS = 2
_JOB_WRITES_INFO_KEY = "generation_job_transaction_writes"
FINAL_JOB_STATUSES = {
    JOB_STATUS_SUCCESS,
    JOB_STATUS_PARTIAL_FAILED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELLED,
}

RUN_STATUS_TO_JOB_STATUS = {
    "success": JOB_STATUS_SUCCESS,
    "partial_failed": JOB_STATUS_PARTIAL_FAILED,
    "failed": JOB_STATUS_FAILED,
    "interrupted": JOB_STATUS_FAILED,
}


class GenerationJobValidationError(ValueError):
    pass


class _GenerationJobDedupeConflict(GenerationJobValidationError):
    pass


class GenerationJobProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobCreationResult:
    job: GenerationJob | None
    created: bool
    reason: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _normalize_job_type(job_type: str | None) -> str:
    value = (job_type or JOB_TYPE_BACKFILL).strip().lower()

    if value not in SUPPORTED_JOB_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_JOB_TYPES))
        raise GenerationJobValidationError(f"job_type must be one of: {allowed}.")

    return value


def _normalize_provider(provider: str | None) -> str:
    value = (provider or "stub").strip().lower()

    if value not in SUPPORTED_JOB_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_JOB_PROVIDERS))
        raise GenerationJobValidationError(f"provider must be one of: {allowed}.")

    return value


def _normalize_text(value: str | None, *, default: str, name: str) -> str:
    normalized = (value or default).strip()

    if not normalized:
        raise GenerationJobValidationError(f"{name} must not be empty.")

    return normalized


def _validate_int(
    value: int | None,
    *,
    default: int,
    min_value: int,
    max_value: int,
    name: str,
) -> int:
    if value is None:
        return default

    if isinstance(value, bool):
        raise GenerationJobValidationError(f"{name} must be an integer.")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GenerationJobValidationError(f"{name} must be an integer.") from exc

    if parsed < min_value or parsed > max_value:
        raise GenerationJobValidationError(
            f"{name} must be between {min_value} and {max_value}."
        )

    return parsed


def _env_int(
    name: str,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise GenerationJobValidationError(f"{name} must be an integer.") from exc

    if parsed < min_value or parsed > max_value:
        raise GenerationJobValidationError(
            f"{name} must be between {min_value} and {max_value}."
        )

    return parsed


def _resolve_openai_limit(
    value: int | None,
    *,
    env_name: str,
    default: int,
    min_value: int,
    max_value: int,
    name: str,
) -> int:
    if value is not None:
        return _validate_int(
            value,
            default=default,
            min_value=min_value,
            max_value=max_value,
            name=name,
        )

    return _env_int(
        env_name,
        default=default,
        min_value=min_value,
        max_value=max_value,
    )


def _enforce_openai_backfill_range_limit(
    *,
    provider: str,
    start_date: date,
    end_date: date,
    limit: int | None,
) -> None:
    if provider != "openai":
        return

    max_days = _env_int(
        "GENERATION_OPENAI_MAX_BACKFILL_DAYS",
        default=DEFAULT_OPENAI_MAX_BACKFILL_DAYS,
        min_value=1,
        max_value=10000,
    )

    requested_days = (end_date - start_date).days + 1
    if limit is not None:
        requested_days = min(requested_days, limit)

    if requested_days > max_days:
        raise GenerationJobValidationError(
            "OpenAI backfill range is too large: "
            f"requested {requested_days} day(s), max allowed is {max_days}. "
            "Use a smaller range or increase GENERATION_OPENAI_MAX_BACKFILL_DAYS "
            "explicitly."
        )


def count_openai_generation_jobs_started_today(
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = day_start + timedelta(days=1)

    return GenerationJob.query.filter(
        GenerationJob.provider == "openai",
        GenerationJob.started_at >= day_start,
        GenerationJob.started_at < next_day,
    ).count()


def normalize_signs(signs: Iterable[str] | None) -> list[str] | None:
    if signs is None:
        return None

    enabled_signs = get_enabled_sign_keys()
    enabled_set = set(enabled_signs)

    parsed: list[str] = []
    unknown: list[str] = []

    for raw_sign in signs:
        if not isinstance(raw_sign, str) or not raw_sign.strip():
            raise GenerationJobValidationError(
                "signs must contain non-empty strings only."
            )

        sign_key = raw_sign.strip().lower()

        if sign_key not in enabled_set:
            unknown.append(sign_key)
            continue

        if sign_key not in parsed:
            parsed.append(sign_key)

    if unknown:
        raise GenerationJobValidationError(
            "Unknown or disabled sign keys: "
            + ", ".join(sorted(set(unknown)))
            + "."
        )

    if not parsed:
        raise GenerationJobValidationError("signs must not be empty when provided.")

    return parsed


def build_generation_job_dedupe_key(
    *,
    job_type: str,
    target_date: date,
    locale: str,
    forecast_type: str,
    provider: str,
    signs: Iterable[str] | None,
) -> str:
    normalized_signs = sorted(signs) if signs is not None else None
    payload = {
        "job_type": job_type,
        "target_date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "provider": provider,
        "signs": normalized_signs,
    }
    raw_value = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def find_active_generation_job(
    *,
    job_type: str,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider: str = "stub",
    signs: Iterable[str] | None = None,
) -> GenerationJob | None:
    normalized_job_type = _normalize_job_type(job_type)
    normalized_provider = _normalize_provider(provider)
    normalized_locale = _normalize_text(locale, default=DEFAULT_LOCALE, name="locale")
    normalized_forecast_type = _normalize_text(
        forecast_type,
        default=DEFAULT_FORECAST_TYPE,
        name="forecast_type",
    )
    normalized_signs = normalize_signs(signs)

    dedupe_key = build_generation_job_dedupe_key(
        job_type=normalized_job_type,
        target_date=target_date,
        locale=normalized_locale,
        forecast_type=normalized_forecast_type,
        provider=normalized_provider,
        signs=normalized_signs,
    )

    return (
        GenerationJob.query.filter(
            GenerationJob.dedupe_key == dedupe_key,
            GenerationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(GenerationJob.created_at.asc(), GenerationJob.id.asc())
        .first()
    )


@contextmanager
def _job_write_session(*, commit: bool):
    if not commit:
        yield db.session()
        return

    # A Session.commit() cannot commit only a savepoint's writes. Use a private
    # transaction so even already-flushed caller writes remain caller-owned.
    bind = db.session.get_bind(mapper=GenerationJob)
    with Session(bind=bind.engine, expire_on_commit=False) as session:
        with session.begin():
            yield session


def _remember_job_writes(
    session: Session, flush_context, *, job_model: type = GenerationJob
) -> None:
    # Session.new/dirty clear after flush. Remember only job identities/keys for
    # the lifetime of this outer transaction, including released savepoints.
    changed = session.new | session.dirty | session.deleted
    touched = [job for job in changed if isinstance(job, job_model)]
    if not touched:
        return
    record = session.info.setdefault(_JOB_WRITES_INFO_KEY, {"ids": set(), "keys": set()})
    for job in touched:
        state = inspect(job)
        identity = state.identity or (state.dict.get("id"),)
        if identity[0] is not None:
            record["ids"].add(identity[0])
        key = state.dict.get("dedupe_key")
        if key is not None:
            record["keys"].add(key)
        record["keys"].update(state.attrs.dedupe_key.history.deleted)


def _forget_job_writes(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_JOB_WRITES_INFO_KEY, None)


# Standalone policy checks also import this module with fake model dependencies.
# Those imports must not leave process-wide Session hooks behind. A real hook
# captures its mapped class above instead of consulting mutable module globals.
if isinstance(GenerationJob, type) and isinstance(
    inspect(GenerationJob, raiseerr=False), Mapper
):
    event.listen(Session, "after_flush", _remember_job_writes)
    event.listen(Session, "after_transaction_end", _forget_job_writes)


def _check_job_edits(
    session: Session,
    *,
    job_id: int | None = None,
    dedupe_key: str | None = None,
    include_flushed: bool = False,
) -> None:
    message = "Commit pending changes to this generation job first, or use commit=False."
    with session.no_autoflush:
        for job in session.new | session.dirty | session.deleted:
            if not isinstance(job, GenerationJob):
                continue
            if (job_id is not None and job.id == job_id) or (
                dedupe_key is not None
                and (
                    job.dedupe_key == dedupe_key
                    or dedupe_key in inspect(job).attrs.dedupe_key.history.deleted
                )
            ):
                raise GenerationJobValidationError(message)
        record = session.info.get(_JOB_WRITES_INFO_KEY) if include_flushed else None
        if not record:
            return
        if job_id in record["ids"] or dedupe_key in record["keys"]:
            raise GenerationJobValidationError(message)
        # An expired object's key need not have been loaded during its flush.
        # Read scalar IDs in the caller transaction; do not refresh ORM state.
        if (
            dedupe_key is not None
            and record["ids"]
            and session.query(GenerationJob.id).filter(
                GenerationJob.id.in_(record["ids"]),
                GenerationJob.dedupe_key == dedupe_key,
            ).first() is not None
        ):
            raise GenerationJobValidationError(message)


def _active_job_for_key(session: Session, dedupe_key: str) -> GenerationJob | None:
    # Check before populate_existing: a duplicate lookup must never discard a
    # caller's unflushed priority/status/relationship edit under no_autoflush.
    _check_job_edits(session, dedupe_key=dedupe_key)
    with session.no_autoflush:
        return (
            session.query(GenerationJob)
            .filter(
                GenerationJob.dedupe_key == dedupe_key,
                GenerationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .populate_existing()
            .order_by(GenerationJob.created_at.asc(), GenerationJob.id.asc())
            .first()
        )


def _is_active_dedupe_conflict(session: Session, exc: IntegrityError) -> bool:
    original = exc.orig
    return (
        session.get_bind(mapper=GenerationJob).dialect.name == "postgresql"
        and getattr(original, "sqlstate", None) == "23505"
        and getattr(getattr(original, "diag", None), "constraint_name", None)
        == ACTIVE_DEDUPE_CONSTRAINT
    )


def _duplicate_job_error(job: GenerationJob | None) -> GenerationJobValidationError:
    if job is not None:
        return _GenerationJobDedupeConflict(
            f"Active generation job already exists: id={job.id}."
        )
    return _GenerationJobDedupeConflict(
        "Active generation job changed during deduplication; retry the request."
    )


def _check_caller_job_edits(job: GenerationJob) -> None:
    # Private transactions must not overwrite pending edits when their result is
    # attached back to the scoped session. Callers composing job writes use
    # commit=False; committed retries operate on committed job state.
    _check_job_edits(
        db.session(), job_id=job.id, dedupe_key=job.dedupe_key, include_flushed=True
    )


def _attach_job(job: GenerationJob, *, commit: bool) -> GenerationJob:
    if not commit:
        return job
    # load=False attaches the committed snapshot without flushing caller writes.
    _check_caller_job_edits(job)
    with db.session.no_autoflush:
        return db.session.merge(job, load=False)


def _insert_generation_job(
    session: Session, job: GenerationJob, *, skip_duplicate: bool, commit: bool
) -> tuple[GenerationJob, bool]:
    for attempt in range(DEDUPE_WRITE_ATTEMPTS):
        existing_job = _active_job_for_key(session, job.dedupe_key)
        if existing_job is not None:
            if not skip_duplicate:
                raise _duplicate_job_error(existing_job)
            if commit:
                _check_caller_job_edits(existing_job)
            return existing_job, False

        # begin_nested() unconditionally flushes pre-existing pending writes,
        # even under no_autoflush. Enter BEFORE adding our job and OUTSIDE the
        # catch, so a caller's pre-savepoint failure is never normalized here.
        savepoint = session.begin_nested()
        try:
            with savepoint:
                session.add(job)
                session.flush()
            return job, True
        except IntegrityError as exc:
            if not _is_active_dedupe_conflict(session, exc):
                raise
            existing_job = _active_job_for_key(session, job.dedupe_key)
            if existing_job is not None:
                if not skip_duplicate:
                    raise _duplicate_job_error(existing_job) from exc
                if commit:
                    _check_caller_job_edits(existing_job)
                return existing_job, False
            if attempt + 1 == DEDUPE_WRITE_ATTEMPTS:
                raise _duplicate_job_error(None) from exc

    raise AssertionError("Unreachable dedupe attempt limit")


def create_generation_job(
    *,
    job_type: str = JOB_TYPE_BACKFILL,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider: str = "stub",
    signs: Iterable[str] | None = None,
    max_attempts: int | None = None,
    max_retry_runs: int | None = None,
    max_job_attempts: int | None = None,
    priority: int | None = None,
    batch_id: str | None = None,
    created_by: str | None = None,
    allow_openai: bool = False,
    skip_duplicate: bool = True,
    commit: bool = True,
) -> tuple[GenerationJob, bool]:
    if not isinstance(target_date, date):
        raise GenerationJobValidationError("target_date must be a date object.")

    normalized_job_type = _normalize_job_type(job_type)
    normalized_provider = _normalize_provider(provider)
    normalized_locale = _normalize_text(locale, default=DEFAULT_LOCALE, name="locale")
    normalized_forecast_type = _normalize_text(
        forecast_type,
        default=DEFAULT_FORECAST_TYPE,
        name="forecast_type",
    )
    with db.session.no_autoflush:
        normalized_signs = normalize_signs(signs)

    if normalized_job_type == JOB_TYPE_RETRY_MISSING and normalized_signs is not None:
        raise GenerationJobValidationError(
            "signs are not supported for retry_missing jobs."
        )

    if normalized_provider == "openai" and not allow_openai:
        raise GenerationJobValidationError(
            "provider=openai requires explicit allow_openai=True at job creation."
        )

    normalized_max_attempts = _validate_int(
        max_attempts,
        default=3,
        min_value=1,
        max_value=10,
        name="max_attempts",
    )
    normalized_max_retry_runs = _validate_int(
        max_retry_runs,
        default=3,
        min_value=1,
        max_value=30,
        name="max_retry_runs",
    )
    normalized_max_job_attempts = _validate_int(
        max_job_attempts,
        default=1,
        min_value=1,
        max_value=10,
        name="max_job_attempts",
    )
    normalized_priority = _validate_int(
        priority,
        default=0,
        min_value=-1000,
        max_value=1000,
        name="priority",
    )

    dedupe_key = build_generation_job_dedupe_key(
        job_type=normalized_job_type,
        target_date=target_date,
        locale=normalized_locale,
        forecast_type=normalized_forecast_type,
        provider=normalized_provider,
        signs=normalized_signs,
    )

    if commit:
        _check_job_edits(db.session(), dedupe_key=dedupe_key, include_flushed=True)

    job = GenerationJob(
        job_type=normalized_job_type,
        status=JOB_STATUS_QUEUED,
        target_date=target_date,
        locale=normalized_locale,
        forecast_type=normalized_forecast_type,
        provider=normalized_provider,
        signs=normalized_signs,
        max_attempts=normalized_max_attempts,
        max_retry_runs=normalized_max_retry_runs,
        max_job_attempts=normalized_max_job_attempts,
        attempt_count=0,
        priority=normalized_priority,
        batch_id=batch_id,
        dedupe_key=dedupe_key,
        openai_allowed_at_creation=bool(allow_openai),
        created_by=created_by,
    )
    with _job_write_session(commit=commit) as session:
        job, created = _insert_generation_job(
            session, job, skip_duplicate=skip_duplicate, commit=commit
        )

    return _attach_job(job, commit=commit), created


def create_generation_jobs_for_range(
    *,
    start_date: date,
    end_date: date,
    job_type: str = JOB_TYPE_BACKFILL,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider: str = "stub",
    signs: Iterable[str] | None = None,
    max_attempts: int | None = None,
    max_retry_runs: int | None = None,
    max_job_attempts: int | None = None,
    priority: int | None = None,
    batch_id: str | None = None,
    created_by: str | None = "cli",
    allow_openai: bool = False,
    skip_covered: bool = False,
    skip_duplicate: bool = True,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise GenerationJobValidationError(
            "start_date and end_date must be date objects."
        )

    if end_date < start_date:
        raise GenerationJobValidationError("end_date must be greater than start_date.")

    normalized_job_type = _normalize_job_type(job_type)
    normalized_provider = _normalize_provider(provider)
    normalized_locale = _normalize_text(locale, default=DEFAULT_LOCALE, name="locale")
    normalized_forecast_type = _normalize_text(
        forecast_type,
        default=DEFAULT_FORECAST_TYPE,
        name="forecast_type",
    )
    normalized_signs = normalize_signs(signs)

    if limit is not None:
        limit = _validate_int(
            limit,
            default=0,
            min_value=1,
            max_value=10000,
            name="limit",
        )

    if normalized_provider == "openai" and not allow_openai:
        raise GenerationJobValidationError(
            "provider=openai requires explicit allow_openai=True at job creation."
        )

    _enforce_openai_backfill_range_limit(
        provider=normalized_provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    normalized_batch_id = batch_id

    if normalized_batch_id is None:
        normalized_batch_id = (
            f"{normalized_job_type}-"
            f"{start_date.isoformat()}-"
            f"{end_date.isoformat()}-"
            f"{normalized_provider}-"
            f"{uuid4().hex[:8]}"
        )

    items: list[dict[str, Any]] = []
    current = start_date
    processed_dates = 0
    created_count = 0
    duplicate_count = 0
    covered_count = 0
    dry_run_count = 0

    while current <= end_date:
        if limit is not None and processed_dates >= limit:
            break

        processed_dates += 1

        if skip_covered and has_generation_coverage(
            target_date=current,
            locale=normalized_locale,
            forecast_type=normalized_forecast_type,
            signs=normalized_signs,
        ):
            covered_count += 1
            items.append(
                {
                    "date": current.isoformat(),
                    "status": "skipped_covered",
                    "job_id": None,
                }
            )
            current += timedelta(days=1)
            continue

        existing_job = find_active_generation_job(
            job_type=normalized_job_type,
            target_date=current,
            locale=normalized_locale,
            forecast_type=normalized_forecast_type,
            provider=normalized_provider,
            signs=normalized_signs,
        )

        if existing_job is not None:
            duplicate_count += 1
            items.append(
                {
                    "date": current.isoformat(),
                    "status": "skipped_duplicate",
                    "job_id": existing_job.id,
                }
            )
            current += timedelta(days=1)
            continue

        if dry_run:
            dry_run_count += 1
            items.append(
                {
                    "date": current.isoformat(),
                    "status": "would_create",
                    "job_id": None,
                }
            )
            current += timedelta(days=1)
            continue

        job, created = create_generation_job(
            job_type=normalized_job_type,
            target_date=current,
            locale=normalized_locale,
            forecast_type=normalized_forecast_type,
            provider=normalized_provider,
            signs=normalized_signs,
            max_attempts=max_attempts,
            max_retry_runs=max_retry_runs,
            max_job_attempts=max_job_attempts,
            priority=priority,
            batch_id=normalized_batch_id,
            created_by=created_by,
            allow_openai=allow_openai,
            skip_duplicate=skip_duplicate,
            commit=True,
        )

        if created:
            created_count += 1
            status = "created"
        else:
            duplicate_count += 1
            status = "skipped_duplicate"

        items.append(
            {
                "date": current.isoformat(),
                "status": status,
                "job_id": job.id,
            }
        )

        current += timedelta(days=1)

    return {
        "batch_id": normalized_batch_id,
        "job_type": normalized_job_type,
        "provider": normalized_provider,
        "locale": normalized_locale,
        "forecast_type": normalized_forecast_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "processed_dates": processed_dates,
        "created_count": created_count,
        "duplicate_count": duplicate_count,
        "covered_count": covered_count,
        "dry_run_count": dry_run_count,
        "dry_run": dry_run,
        "items": items,
    }


def create_scheduled_generation_job(
    *,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider: str = "stub",
    max_attempts: int | None = None,
    max_retry_runs: int | None = None,
    max_job_attempts: int | None = None,
    priority: int | None = None,
    created_by: str | None = "scheduler",
    allow_openai: bool = False,
    skip_covered: bool = True,
) -> dict[str, Any]:
    """Create one scheduled queue job for a date without executing generation."""

    if skip_covered and has_generation_coverage(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    ):
        return {
            "job": None,
            "created": False,
            "reason": "already_covered",
            "date": target_date.isoformat(),
            "target_date": target_date.isoformat(),
            "locale": locale,
            "forecast_type": forecast_type,
            "provider": provider,
            "job_type": JOB_TYPE_SCHEDULED,
        }

    job, created = create_generation_job(
        job_type=JOB_TYPE_SCHEDULED,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        provider=provider,
        signs=None,
        max_attempts=max_attempts,
        max_retry_runs=max_retry_runs,
        max_job_attempts=max_job_attempts,
        priority=priority,
        batch_id=None,
        created_by=created_by,
        allow_openai=allow_openai,
        skip_duplicate=True,
        commit=True,
    )

    return {
        "job": serialize_generation_job(job),
        "created": created,
        "reason": None if created else "active_job_exists",
        "date": target_date.isoformat(),
        "target_date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "provider": provider,
        "job_type": JOB_TYPE_SCHEDULED,
    }


def create_scheduled_retry_missing_job(
    *,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider: str = "stub",
    max_attempts: int | None = None,
    max_retry_runs: int | None = None,
    max_job_attempts: int | None = None,
    priority: int | None = None,
    created_by: str | None = "scheduler",
    allow_openai: bool = False,
) -> dict[str, Any]:
    """Create one retry_missing queue job when at least one forecast is missing."""

    missing_signs = get_missing_forecast_signs(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    )

    if not missing_signs:
        return {
            "job": None,
            "created": False,
            "reason": "no_missing_forecasts",
            "missing_signs": [],
            "date": target_date.isoformat(),
            "target_date": target_date.isoformat(),
            "locale": locale,
            "forecast_type": forecast_type,
            "provider": provider,
            "job_type": JOB_TYPE_RETRY_MISSING,
        }

    job, created = create_generation_job(
        job_type=JOB_TYPE_RETRY_MISSING,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        provider=provider,
        signs=None,
        max_attempts=max_attempts,
        max_retry_runs=max_retry_runs,
        max_job_attempts=max_job_attempts,
        priority=priority,
        batch_id=None,
        created_by=created_by,
        allow_openai=allow_openai,
        skip_duplicate=True,
        commit=True,
    )

    return {
        "job": serialize_generation_job(job),
        "created": created,
        "reason": None if created else "active_job_exists",
        "missing_signs": missing_signs,
        "date": target_date.isoformat(),
        "target_date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "provider": provider,
        "job_type": JOB_TYPE_RETRY_MISSING,
    }


def get_generation_job(job_id: int) -> GenerationJob | None:
    return db.session.get(GenerationJob, job_id)


def list_generation_jobs(
    *,
    status: str | None = None,
    target_date: date | None = None,
    batch_id: str | None = None,
    provider: str | None = None,
    job_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_limit = _validate_int(
        limit,
        default=20,
        min_value=1,
        max_value=200,
        name="limit",
    )
    normalized_offset = _validate_int(
        offset,
        default=0,
        min_value=0,
        max_value=100000,
        name="offset",
    )

    query = GenerationJob.query

    if status:
        query = query.filter(GenerationJob.status == status)

    if target_date:
        query = query.filter(GenerationJob.target_date == target_date)

    if batch_id:
        query = query.filter(GenerationJob.batch_id == batch_id)

    if provider:
        query = query.filter(GenerationJob.provider == _normalize_provider(provider))

    if job_type:
        query = query.filter(GenerationJob.job_type == _normalize_job_type(job_type))

    total_count = query.count()
    jobs = (
        query.order_by(
            GenerationJob.priority.desc(),
            GenerationJob.created_at.asc(),
            GenerationJob.id.asc(),
        )
        .offset(normalized_offset)
        .limit(normalized_limit)
        .all()
    )

    return {
        "items": [serialize_generation_job(job) for job in jobs],
        "total_count": total_count,
        "limit": normalized_limit,
        "offset": normalized_offset,
    }


def get_generation_job_batch_status(*, batch_id: str) -> dict[str, Any] | None:
    normalized_batch_id = (batch_id or "").strip()
    if not normalized_batch_id:
        raise GenerationJobValidationError("batch_id must not be empty.")

    jobs = (
        GenerationJob.query.filter(GenerationJob.batch_id == normalized_batch_id)
        .order_by(
            GenerationJob.target_date.asc(),
            GenerationJob.priority.desc(),
            GenerationJob.created_at.asc(),
            GenerationJob.id.asc(),
        )
        .all()
    )

    if not jobs:
        return None

    known_statuses = [
        JOB_STATUS_QUEUED,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCESS,
        JOB_STATUS_PARTIAL_FAILED,
        JOB_STATUS_FAILED,
        JOB_STATUS_CANCELLED,
    ]
    status_counts: dict[str, int] = {status: 0 for status in known_statuses}
    provider_counts: dict[str, int] = {}
    job_type_counts: dict[str, int] = {}

    active_count = 0
    finished_count = 0
    failed_count = 0
    target_dates: list[date] = []

    for job in jobs:
        status_counts[job.status] = status_counts.get(job.status, 0) + 1
        provider_counts[job.provider] = provider_counts.get(job.provider, 0) + 1
        job_type_counts[job.job_type] = job_type_counts.get(job.job_type, 0) + 1
        target_dates.append(job.target_date)

        if job.status in ACTIVE_JOB_STATUSES:
            active_count += 1

        if job.status in FINAL_JOB_STATUSES:
            finished_count += 1

        if job.status in {JOB_STATUS_PARTIAL_FAILED, JOB_STATUS_FAILED}:
            failed_count += 1

    total_count = len(jobs)
    success_count = status_counts.get(JOB_STATUS_SUCCESS, 0)
    cancelled_count = status_counts.get(JOB_STATUS_CANCELLED, 0)

    return {
        "batch_id": normalized_batch_id,
        "total_count": total_count,
        "status_counts": status_counts,
        "provider_counts": dict(sorted(provider_counts.items())),
        "job_type_counts": dict(sorted(job_type_counts.items())),
        "target_date_min": min(target_dates).isoformat(),
        "target_date_max": max(target_dates).isoformat(),
        "active_count": active_count,
        "finished_count": finished_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "cancelled_count": cancelled_count,
        "progress_percent": round((finished_count / total_count) * 100, 2),
        "is_complete": active_count == 0,
        "has_failures": failed_count > 0,
        "items": [serialize_generation_job(job) for job in jobs],
    }


def cancel_generation_job_batch(*, batch_id: str) -> dict[str, Any] | None:
    normalized_batch_id = (batch_id or "").strip()
    if not normalized_batch_id:
        raise GenerationJobValidationError("batch_id must not be empty.")

    jobs = (
        GenerationJob.query.filter(GenerationJob.batch_id == normalized_batch_id)
        .order_by(
            GenerationJob.target_date.asc(),
            GenerationJob.priority.desc(),
            GenerationJob.created_at.asc(),
            GenerationJob.id.asc(),
        )
        .all()
    )

    if not jobs:
        return None

    now = utcnow()
    cancelled_count = 0
    skipped_status_counts: dict[str, int] = {}

    for job in jobs:
        if job.status == JOB_STATUS_QUEUED:
            job.status = JOB_STATUS_CANCELLED
            job.finished_at = now
            job.locked_at = None
            job.locked_by = None
            job.error_message = job.error_message or "Job was cancelled as part of batch cancel."
            cancelled_count += 1
            continue

        skipped_status_counts[job.status] = skipped_status_counts.get(job.status, 0) + 1

    if cancelled_count:
        db.session.commit()

    return {
        "batch_id": normalized_batch_id,
        "total_count": len(jobs),
        "cancelled_count": cancelled_count,
        "skipped_count": len(jobs) - cancelled_count,
        "skipped_status_counts": dict(sorted(skipped_status_counts.items())),
        "items": [serialize_generation_job(job) for job in jobs],
        "batch_status": get_generation_job_batch_status(batch_id=normalized_batch_id),
    }


def retry_failed_generation_job_batch(*, batch_id: str) -> dict[str, Any] | None:
    normalized_batch_id = (batch_id or "").strip()
    if not normalized_batch_id:
        raise GenerationJobValidationError("batch_id must not be empty.")

    retried_count = 0
    skipped_status_counts: dict[str, int] = {}

    with _job_write_session(commit=True) as session:
        jobs = (
            session.query(GenerationJob)
            .filter(GenerationJob.batch_id == normalized_batch_id)
            .order_by(
                GenerationJob.target_date.asc(),
                GenerationJob.priority.desc(),
                GenerationJob.created_at.asc(),
                GenerationJob.id.asc(),
            )
            .all()
        )
        if not jobs:
            return None

        for job in jobs:
            _check_caller_job_edits(job)
            if job.status in {JOB_STATUS_FAILED, JOB_STATUS_PARTIAL_FAILED}:
                try:
                    _requeue_job_with_dedupe(session, job)
                except _GenerationJobDedupeConflict:
                    # Savepoint rollback preserves status, links, timestamps and
                    # attempts. Other eligible batch members can still retry.
                    pass
                else:
                    retried_count += 1
                    continue

            skipped_status_counts[job.status] = skipped_status_counts.get(job.status, 0) + 1

    jobs = [_attach_job(job, commit=True) for job in jobs]
    with db.session.no_autoflush:
        batch_status = get_generation_job_batch_status(batch_id=normalized_batch_id)

    return {
        "batch_id": normalized_batch_id,
        "total_count": len(jobs),
        "retried_count": retried_count,
        "skipped_count": len(jobs) - retried_count,
        "skipped_status_counts": dict(sorted(skipped_status_counts.items())),
        "items": [serialize_generation_job(job) for job in jobs],
        "batch_status": batch_status,
    }


def cancel_generation_job(job_id: int) -> GenerationJob | None:
    job = db.session.get(GenerationJob, job_id)

    if job is None:
        return None

    if job.status == JOB_STATUS_RUNNING:
        raise GenerationJobValidationError(
            "Running jobs cannot be cancelled safely in this version."
        )

    if job.status in FINAL_JOB_STATUSES:
        return job

    job.status = JOB_STATUS_CANCELLED
    job.finished_at = utcnow()
    job.locked_at = None
    job.locked_by = None
    job.error_message = job.error_message or "Job was cancelled."
    db.session.commit()

    return job


def _requeue_job_with_dedupe(session: Session, job: GenerationJob) -> None:
    for attempt in range(DEDUPE_WRITE_ATTEMPTS):
        existing_job = _active_job_for_key(session, job.dedupe_key)
        if existing_job is not None:
            raise _duplicate_job_error(existing_job)

        savepoint = session.begin_nested()
        try:
            with savepoint:
                job.status = JOB_STATUS_QUEUED
                job.run_id = None
                job.error_message = None
                job.started_at = None
                job.finished_at = None
                job.locked_at = None
                job.locked_by = None
                session.flush()
            return
        except IntegrityError as exc:
            if not _is_active_dedupe_conflict(session, exc):
                raise
            existing_job = _active_job_for_key(session, job.dedupe_key)
            if existing_job is not None or attempt + 1 == DEDUPE_WRITE_ATTEMPTS:
                raise _duplicate_job_error(existing_job) from exc


def retry_generation_job(job_id: int) -> GenerationJob | None:
    _check_job_edits(db.session(), job_id=job_id, include_flushed=True)
    with _job_write_session(commit=True) as session:
        job = session.get(GenerationJob, job_id)

        if job is None:
            return None

        _check_caller_job_edits(job)
        if job.status not in {JOB_STATUS_FAILED, JOB_STATUS_PARTIAL_FAILED}:
            raise GenerationJobValidationError(
                "Only failed or partial_failed jobs can be queued for retry."
            )

        _requeue_job_with_dedupe(session, job)

    return _attach_job(job, commit=True)


def _should_use_skip_locked() -> bool:
    bind = db.session.get_bind()

    return bind is not None and bind.dialect.name == "postgresql"


def claim_next_generation_job(
    *,
    worker_id: str,
    exclude_providers: Iterable[str] | None = None,
) -> GenerationJob | None:
    assert_autonomous_session_clean(db.session())
    query = GenerationJob.query.filter(GenerationJob.status == JOB_STATUS_QUEUED)

    normalized_excluded_providers: list[str] = []
    for provider in exclude_providers or []:
        normalized_excluded_providers.append(_normalize_provider(provider))

    if normalized_excluded_providers:
        query = query.filter(~GenerationJob.provider.in_(normalized_excluded_providers))

    query = query.order_by(
        GenerationJob.priority.desc(),
        GenerationJob.created_at.asc(),
        GenerationJob.id.asc(),
    )

    if _should_use_skip_locked():
        query = query.with_for_update(skip_locked=True)

    job = query.first()
    if job is None:
        return None

    now = utcnow()
    job.status = JOB_STATUS_RUNNING
    job.locked_at = now
    job.locked_by = worker_id
    job.started_at = job.started_at or now
    job.attempt_count = (job.attempt_count or 0) + 1

    try:
        # Production claim auditing is retained, but no production ledger start
        # or transport is activated before real epochs/admission are available.
        if deployment_mode() != "production":
            db.session.flush()
            record_execution_start(
                db.session(), execution_id=claim_execution_id(job),
                origin="queue_worker", job_id=job.id, provider=job.provider,
                target_date=job.target_date, locale=job.locale,
                forecast_type=job.forecast_type,
            )
        db.session.commit()
    except BaseException:
        db.session.rollback()
        raise

    return job


def close_stale_running_jobs(*, stale_after_minutes: int = 60) -> int:
    assert_autonomous_session_clean(db.session())
    stale_after_minutes = _validate_int(
        stale_after_minutes,
        default=60,
        min_value=1,
        max_value=10080,
        name="stale_after_minutes",
    )

    cutoff = utcnow() - timedelta(minutes=stale_after_minutes)
    stale_jobs = (
        GenerationJob.query.filter(
            GenerationJob.status == JOB_STATUS_RUNNING,
            GenerationJob.locked_at < cutoff,
            # Even a claim with no run link is durable execution evidence, not
            # proof that reclaim is safe. Leave managed history for .04/.05.
            ~select(GenerationExecution.id).where(
                GenerationExecution.job_id == GenerationJob.id,
            ).exists(),
        )
        .order_by(GenerationJob.locked_at.asc(), GenerationJob.id.asc())
        .all()
    )

    closed_count = 0

    for job in stale_jobs:
        job.locked_at = None
        job.locked_by = None

        if (job.attempt_count or 0) < job.max_job_attempts:
            job.status = JOB_STATUS_QUEUED
            job.error_message = (
                job.error_message
                or f"Job lock expired after {stale_after_minutes} minutes; re-queued."
            )
        else:
            job.status = JOB_STATUS_FAILED
            job.finished_at = utcnow()
            job.error_message = (
                job.error_message
                or f"Job lock expired after {stale_after_minutes} minutes."
            )

        closed_count += 1

    if closed_count:
        db.session.commit()

    return closed_count


def process_generation_jobs(
    *,
    limit: int = 1,
    worker_id: str | None = None,
    allow_openai: bool = False,
    stale_after_hours: int = 2,
    max_openai_jobs_per_run: int | None = None,
    max_openai_jobs_per_day: int | None = None,
) -> dict[str, Any]:
    normalized_limit = _validate_int(
        limit,
        default=1,
        min_value=1,
        max_value=100,
        name="limit",
    )
    normalized_worker_id = worker_id or f"worker-{uuid4().hex[:8]}"
    normalized_max_openai_jobs_per_run = _resolve_openai_limit(
        max_openai_jobs_per_run,
        env_name="GENERATION_OPENAI_MAX_JOBS_PER_RUN",
        default=DEFAULT_OPENAI_MAX_JOBS_PER_RUN,
        min_value=1,
        max_value=10000,
        name="max_openai_jobs_per_run",
    )
    normalized_max_openai_jobs_per_day = _resolve_openai_limit(
        max_openai_jobs_per_day,
        env_name="GENERATION_OPENAI_MAX_JOBS_PER_DAY",
        default=DEFAULT_OPENAI_MAX_JOBS_PER_DAY,
        min_value=1,
        max_value=10000,
        name="max_openai_jobs_per_day",
    )

    processed_jobs: list[dict[str, Any]] = []
    processed_openai_count = 0
    openai_run_limit_reached = False
    openai_daily_limit_reached = False

    for _ in range(normalized_limit):
        exclude_providers: list[str] = []

        if allow_openai:
            if processed_openai_count >= normalized_max_openai_jobs_per_run:
                openai_run_limit_reached = True
                exclude_providers.append("openai")
            elif (
                count_openai_generation_jobs_started_today()
                >= normalized_max_openai_jobs_per_day
            ):
                openai_daily_limit_reached = True
                exclude_providers.append("openai")

        job = claim_next_generation_job(
            worker_id=normalized_worker_id,
            exclude_providers=exclude_providers,
        )
        if job is None:
            break

        job_provider = job.provider

        processed_jobs.append(
            process_claimed_generation_job(
                job,
                worker_id=normalized_worker_id,
                allow_openai=allow_openai,
                stale_after_hours=stale_after_hours,
            )
        )

        if job_provider == "openai":
            processed_openai_count += 1

    openai_started_today = count_openai_generation_jobs_started_today()
    openai_limit_reached = openai_run_limit_reached or openai_daily_limit_reached

    return {
        "worker_id": normalized_worker_id,
        "requested_limit": normalized_limit,
        "processed_count": len(processed_jobs),
        "jobs": processed_jobs,
        "openai_limit_reached": openai_limit_reached,
        "openai_limits": {
            "allow_openai": allow_openai,
            "max_jobs_per_run": normalized_max_openai_jobs_per_run,
            "max_jobs_per_day": normalized_max_openai_jobs_per_day,
            "processed_count": processed_openai_count,
            "started_count_today": openai_started_today,
            "run_limit_reached": openai_run_limit_reached,
            "daily_limit_reached": openai_daily_limit_reached,
            "limit_reached": openai_limit_reached,
        },
    }

def process_claimed_generation_job(
    job: GenerationJob,
    *,
    worker_id: str,
    allow_openai: bool = False,
    stale_after_hours: int = 2,
) -> dict[str, Any]:
    assert_autonomous_session_clean(db.session())
    if job.status != JOB_STATUS_RUNNING:
        raise GenerationJobProcessingError(
            f"Job id={job.id} is not running and cannot be processed."
        )

    if job.locked_by != worker_id:
        raise GenerationJobProcessingError(
            f"Job id={job.id} is locked by another worker."
        )

    claimed_job_id, claimed_attempt_count = job.id, job.attempt_count
    claimed_execution_id = claim_execution_id(job)
    claimed_scope = GenerationPackageScope(job.target_date, job.locale, job.forecast_type)

    # Inspect duplicate dispatch BEFORE mutable permission/configuration gates.
    # Changed paid/local/publication permission is not authority to fail another
    # invocation's linked execution. This guard never enters the failure writer.
    if db.session.get(GenerationExecutionRun, claimed_execution_id) is not None:
        raise ExecutionAlreadyStarted(
            "This claim already started a run; inspect its state without replay."
        )

    try:
        _ensure_provider_can_execute(job, allow_openai=allow_openai)
        require_execution_activation()
        unlinked_claim_execution(db.session(), job)

        if job.job_type == JOB_TYPE_RETRY_MISSING:
            run = _run_retry_missing_job(job, stale_after_hours=stale_after_hours)
        else:
            run = _run_standard_generation_job(job, stale_after_hours=stale_after_hours)

        if run is None:
            job.status = JOB_STATUS_SUCCESS
            job.run_id = None
            job.error_message = None
        else:
            job.run_id = run.id
            job.status = RUN_STATUS_TO_JOB_STATUS.get(run.status, JOB_STATUS_FAILED)
            job.error_message = run.error_message

            if run.status not in RUN_STATUS_TO_JOB_STATUS:
                job.error_message = (
                    job.error_message
                    or f"Generation run finished with unsupported status: {run.status}."
                )

        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        db.session.commit()

    except ExecutionAlreadyStarted:
        # A duplicate dispatch is not a failed new execution. Preserve the job,
        # its owner/locks/run and audit history for status inspection; no replay.
        raise
    except GenerationScopeBusy as exc:
        db.session.rollback()
        # This new failure path must not let an expired owner finalize a newer
        # claim. Epoch replaces/enriches the attempt identity in .04a; this is
        # deliberately not a claim of complete fencing of all existing writers.
        try:
            db.session.begin()
            with package_scope_lock(db.session(), scope=claimed_scope):
                # Another dispatch of this same claim may have linked its run
                # after our initial unlinked check. Serialize with that commit.
                if db.session.get(GenerationExecutionRun, claimed_execution_id) is not None:
                    raise ExecutionAlreadyStarted(
                        "This claim already started a run; inspect its state without replay."
                    )
                result = db.session.execute(update(GenerationJob).where(
                    GenerationJob.id == claimed_job_id,
                    GenerationJob.status == JOB_STATUS_RUNNING,
                    GenerationJob.locked_by == worker_id,
                    GenerationJob.attempt_count == claimed_attempt_count,
                    ~select(GenerationExecutionRun.execution_id).where(
                        GenerationExecutionRun.execution_id == claimed_execution_id,
                    ).exists(),
                ).values(
                    status=JOB_STATUS_FAILED, run_id=None,
                    error_message=f"{exc.code}: {exc}", finished_at=utcnow(),
                    locked_at=None, locked_by=None,
                ).execution_options(synchronize_session=False))
            db.session.commit()
        except GenerationScopeBusy as lock_error:
            db.session.rollback()
            raise GenerationJobProcessingError(
                "Generation admission is still in progress; claim retained for review."
            ) from lock_error
        except BaseException:
            db.session.rollback()
            raise
        if result.rowcount != 1:
            raise GenerationJobProcessingError(
                "Generation package was busy; job claim ownership changed."
            ) from exc
        job = db.session.get(GenerationJob, claimed_job_id, populate_existing=True)
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(GenerationJob, job.id)

        if job is None:
            raise

        job.status = JOB_STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = utcnow()
        job.locked_at = None
        job.locked_by = None
        db.session.commit()

    return serialize_generation_job(job)


def _ensure_provider_can_execute(
    job: GenerationJob,
    *,
    allow_openai: bool,
) -> None:
    require_paid_execution(job.provider)
    require_publication_provider(job.provider)
    if job.provider != "openai":
        require_paid_admission(job.provider)
        return

    if not allow_openai:
        raise GenerationJobProcessingError(
            "Refusing to process provider=openai job without explicit worker allow_openai."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise GenerationJobProcessingError(
            "OPENAI_API_KEY is missing; cannot process provider=openai job."
        )
    require_paid_admission(job.provider)


def _run_standard_generation_job(
    job: GenerationJob,
    *,
    stale_after_hours: int,
) -> GenerationRun:
    return run_daily_generation(
        target_date=job.target_date,
        run_type=job.job_type,
        locale=job.locale,
        forecast_type=job.forecast_type,
        provider_name=job.provider,
        signs=job.signs,
        max_attempts=job.max_attempts,
        stale_after_hours=stale_after_hours,
        execution_id=claim_execution_id(job),
    )


def _run_retry_missing_job(
    job: GenerationJob,
    *,
    stale_after_hours: int,
) -> GenerationRun | None:
    missing_signs = get_missing_forecast_signs(
        target_date=job.target_date,
        locale=job.locale,
        forecast_type=job.forecast_type,
    )

    if not missing_signs:
        return None

    run = run_retry_for_missing_forecasts(
        target_date=job.target_date,
        locale=job.locale,
        forecast_type=job.forecast_type,
        provider_name=job.provider,
        max_attempts=job.max_attempts,
        max_retry_runs=job.max_retry_runs,
        stale_after_hours=stale_after_hours,
        execution_id=claim_execution_id(job),
    )

    # None also means the retry-run cap was reached. Coverage may have changed
    # concurrently, so only report no-work success when nothing remains missing.
    if run is None and get_missing_forecast_signs(
        target_date=job.target_date,
        locale=job.locale,
        forecast_type=job.forecast_type,
    ):
        raise GenerationJobProcessingError(
            "Retry-missing generation returned no run while forecasts are still missing "
            "(retry run limit may have been reached)."
        )

    return run


def serialize_generation_job(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "date": job.target_date.isoformat(),
        "target_date": job.target_date.isoformat(),
        "locale": job.locale,
        "forecast_type": job.forecast_type,
        "provider": job.provider,
        "signs": job.signs,
        "max_attempts": job.max_attempts,
        "max_retry_runs": job.max_retry_runs,
        "max_job_attempts": job.max_job_attempts,
        "attempt_count": job.attempt_count,
        "priority": job.priority,
        "run_id": job.run_id,
        "batch_id": job.batch_id,
        "dedupe_key": job.dedupe_key,
        "openai_allowed_at_creation": job.openai_allowed_at_creation,
        "created_by": job.created_by,
        "error_message": job.error_message,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "locked_at": _iso(job.locked_at),
        "locked_by": job.locked_by,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }

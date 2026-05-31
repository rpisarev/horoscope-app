from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from .. import db
from ..models import GenerationJob, GenerationRun
from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
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

SUPPORTED_JOB_PROVIDERS = {"stub", "openai"}

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_PARTIAL_FAILED = "partial_failed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

ACTIVE_JOB_STATUSES = {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}
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

    existing_job = (
        GenerationJob.query.filter(
            GenerationJob.dedupe_key == dedupe_key,
            GenerationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(GenerationJob.created_at.asc(), GenerationJob.id.asc())
        .first()
    )

    if existing_job is not None:
        if skip_duplicate:
            return existing_job, False

        raise GenerationJobValidationError(
            f"Active generation job already exists: id={existing_job.id}."
        )

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
    db.session.add(job)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return job, True


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


def retry_generation_job(job_id: int) -> GenerationJob | None:
    job = db.session.get(GenerationJob, job_id)

    if job is None:
        return None

    if job.status not in {JOB_STATUS_FAILED, JOB_STATUS_PARTIAL_FAILED}:
        raise GenerationJobValidationError(
            "Only failed or partial_failed jobs can be queued for retry."
        )

    job.status = JOB_STATUS_QUEUED
    job.run_id = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.locked_at = None
    job.locked_by = None
    db.session.commit()

    return job


def _should_use_skip_locked() -> bool:
    bind = db.session.get_bind()

    return bind is not None and bind.dialect.name == "postgresql"


def claim_next_generation_job(*, worker_id: str) -> GenerationJob | None:
    query = GenerationJob.query.filter(GenerationJob.status == JOB_STATUS_QUEUED)

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
    db.session.commit()

    return job


def close_stale_running_jobs(*, stale_after_minutes: int = 60) -> int:
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
) -> dict[str, Any]:
    normalized_limit = _validate_int(
        limit,
        default=1,
        min_value=1,
        max_value=100,
        name="limit",
    )
    normalized_worker_id = worker_id or f"worker-{uuid4().hex[:8]}"

    processed_jobs: list[dict[str, Any]] = []

    for _ in range(normalized_limit):
        job = claim_next_generation_job(worker_id=normalized_worker_id)

        if job is None:
            break

        processed_jobs.append(
            process_claimed_generation_job(
                job,
                worker_id=normalized_worker_id,
                allow_openai=allow_openai,
                stale_after_hours=stale_after_hours,
            )
        )

    return {
        "worker_id": normalized_worker_id,
        "requested_limit": normalized_limit,
        "processed_count": len(processed_jobs),
        "jobs": processed_jobs,
    }


def process_claimed_generation_job(
    job: GenerationJob,
    *,
    worker_id: str,
    allow_openai: bool = False,
    stale_after_hours: int = 2,
) -> dict[str, Any]:
    if job.status != JOB_STATUS_RUNNING:
        raise GenerationJobProcessingError(
            f"Job id={job.id} is not running and cannot be processed."
        )

    if job.locked_by != worker_id:
        raise GenerationJobProcessingError(
            f"Job id={job.id} is locked by another worker."
        )

    try:
        _ensure_provider_can_execute(job, allow_openai=allow_openai)

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
    if job.provider != "openai":
        return

    if not allow_openai:
        raise GenerationJobProcessingError(
            "Refusing to process provider=openai job without explicit worker allow_openai."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise GenerationJobProcessingError(
            "OPENAI_API_KEY is missing; cannot process provider=openai job."
        )


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

    return run_retry_for_missing_forecasts(
        target_date=job.target_date,
        locale=job.locale,
        forecast_type=job.forecast_type,
        provider_name=job.provider,
        max_attempts=job.max_attempts,
        max_retry_runs=job.max_retry_runs,
        stale_after_hours=stale_after_hours,
    )


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
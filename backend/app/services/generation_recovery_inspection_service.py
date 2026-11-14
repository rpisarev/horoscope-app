"""Bounded evidence for one job; this module grants no recovery authority.

Only explicit projections on the shared read-only connection are used. In
particular, legacy attempt rows cannot prove transport-not-reached or billing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import Text, case, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from ..models import Forecast, GenerationAttempt, GenerationItem, GenerationJob, GenerationRun
from .generation_read_service import published_coverage, read_snapshot


MAX_ITEMS = 500
MAX_ATTEMPTS = 1000
MAX_SCOPE_SIGNS = 1000
MAX_SCOPE_BYTES = 65536
MAX_JOB_ID = 2**63 - 1
JOB_STATUSES = frozenset({"queued", "running", "success", "partial_failed", "failed", "cancelled"})
RUN_STATUSES = frozenset({"running", "success", "partial_failed", "failed", "interrupted"})
ITEM_STATUSES = frozenset({"pending", "running", "success", "skipped", "failed", "interrupted"})
ATTEMPT_STATUSES = frozenset({"running", "success", "failed", "failed_retryable"})
JOB_TYPES = frozenset({"manual", "scheduled", "backfill", "retry_missing"})
PROVIDERS = frozenset({"stub", "openai"})
LOCALES = frozenset({"ru", "uk", "en"})
FORECAST_TYPES = frozenset({"daily"})
SIGN_TOKEN = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")


class GenerationInspectionUnavailable(RuntimeError):
    """A safe boundary: never expose a database URL, SQL parameters or errors."""


def _enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else "unknown"


def _sign(value):
    # Scope identity is not free-form display text. Withhold suspicious legacy
    # metadata even if it happens to fit the database's string length constraint.
    if not isinstance(value, str) or not SIGN_TOKEN.fullmatch(value):
        return None
    if any(token in value for token in ("secret", "token", "password", "api_key")):
        return None
    return value


def _timestamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _validate_integer(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} is outside the supported positive integer range.")


def _response_present(model):
    # JSON null and empty raw text are not stored response evidence. The payload
    # itself, raw output and error strings are never returned from PostgreSQL.
    return or_(
        model.response_payload.is_not(None) & (cast(model.response_payload, Text) != "null"),
        model.raw_response.is_not(None) & (model.raw_response != ""),
    ).label("response_present")


def _read_job(connection, job_id):
    scope_size = func.octet_length(cast(GenerationJob.signs, Text))
    return connection.execute(select(
        GenerationJob.id, GenerationJob.job_type, GenerationJob.status,
        GenerationJob.target_date, GenerationJob.locale, GenerationJob.forecast_type,
        GenerationJob.provider, GenerationJob.run_id, GenerationJob.attempt_count,
        GenerationJob.max_attempts, GenerationJob.max_retry_runs, GenerationJob.max_job_attempts,
        GenerationJob.created_at, GenerationJob.updated_at, GenerationJob.started_at,
        GenerationJob.finished_at, GenerationJob.locked_at,
        (GenerationJob.locked_by.is_not(None) & (GenerationJob.locked_by != "")).label("owner_present"),
        case((scope_size <= MAX_SCOPE_BYTES, GenerationJob.signs), else_=None).label("signs"),
        (scope_size > MAX_SCOPE_BYTES).label("scope_oversized"),
    ).where(GenerationJob.id == job_id)).mappings().first()


def _read_run(connection, run_id):
    return connection.execute(select(
        GenerationRun.id, GenerationRun.run_type, GenerationRun.status,
        GenerationRun.target_date, GenerationRun.locale, GenerationRun.forecast_type,
        GenerationRun.total_items, GenerationRun.success_items, GenerationRun.failed_items,
        GenerationRun.skipped_items, GenerationRun.started_at, GenerationRun.finished_at,
    ).where(GenerationRun.id == run_id)).mappings().first()


def _counts(connection, model, run_id, statuses):
    # Normalize before GROUP BY so arbitrary metadata never becomes an unbounded
    # grouping or a secret-bearing dictionary key.
    status = case((model.status.in_(sorted(statuses)), model.status), else_="unknown")
    query = select(status.label("status"), func.count().label("count"))
    if model is GenerationAttempt:
        query = query.join(GenerationItem, GenerationItem.id == GenerationAttempt.item_id)
    query = query.where(GenerationItem.run_id == run_id).group_by(status)
    counts = {row["status"]: row["count"] for row in connection.execute(query).mappings()}
    return {"total": sum(counts.values()), "status_counts": dict(sorted(counts.items()))}


def _read_items(connection, run_id, limit):
    return connection.execute(select(
        GenerationItem.id, GenerationItem.sign_key, GenerationItem.target_date,
        GenerationItem.locale, GenerationItem.forecast_type, GenerationItem.status,
        GenerationItem.provider, GenerationItem.forecast_id,
        GenerationItem.started_at, GenerationItem.finished_at,
        _response_present(GenerationItem),
        Forecast.id.label("linked_forecast_id"), Forecast.status.label("forecast_status"),
        Forecast.sign_key.label("forecast_sign"), Forecast.target_date.label("forecast_date"),
        Forecast.locale.label("forecast_locale"), Forecast.forecast_type.label("forecast_type_link"),
        Forecast.generation_item_id.label("forecast_item_id"),
    ).outerjoin(Forecast, Forecast.id == GenerationItem.forecast_id)
        .where(GenerationItem.run_id == run_id).order_by(GenerationItem.id).limit(limit)).mappings().all()


def _read_attempts(connection, run_id, limit):
    return connection.execute(select(
        GenerationAttempt.id, GenerationAttempt.item_id, GenerationAttempt.attempt_no,
        GenerationAttempt.status, GenerationAttempt.provider,
        GenerationAttempt.started_at, GenerationAttempt.finished_at,
        _response_present(GenerationAttempt),
    ).join(GenerationItem, GenerationItem.id == GenerationAttempt.item_id)
        .where(GenerationItem.run_id == run_id)
        .order_by(GenerationAttempt.item_id, GenerationAttempt.attempt_no, GenerationAttempt.id)
        .limit(limit)).mappings().all()


def _scope_and_coverage(connection, job):
    signs = job["signs"]
    reason = None
    if job["scope_oversized"]:
        reason = "scope_bytes_limit"
    elif signs is not None and not isinstance(signs, list):
        reason = "malformed_sign_scope"
    elif isinstance(signs, list) and len(signs) > MAX_SCOPE_SIGNS:
        reason = "scope_sign_limit"
    elif signs is not None and any(not isinstance(sign, str) or not sign or len(sign) > 32 for sign in signs):
        reason = "malformed_sign_scope"
    scope = {
        "date": job["target_date"].isoformat(),
        "locale": _enum(job["locale"], LOCALES),
        "forecast_type": _enum(job["forecast_type"], FORECAST_TYPES),
        "scope_source": "unknown" if reason else ("enabled_metadata" if signs is None else "explicit_signs"),
        "metadata_state": "unavailable" if reason else ("current_reconstruction" if signs is None else "stored_explicit_scope"),
    }
    if reason:
        return scope, {**scope, "coverage_state": "unknown", "reason": reason,
                       "expected_signs": None, "published_signs": None, "missing_signs": None,
                       "expected_count": None, "published_count": None, "missing_count": None}, None
    # Sole coverage implementation: exact job scope, even for disabled historical
    # requested signs. None means CURRENT enabled metadata, not historical intent.
    raw = published_coverage(connection, target_date=job["target_date"], locale=job["locale"],
                             forecast_type=job["forecast_type"], signs=signs)
    coverage = {**raw, "locale": scope["locale"], "forecast_type": scope["forecast_type"]}
    coverage["redacted_sign_count"] = sum(_sign(sign) is None for sign in raw["expected_signs"])
    for key in ("expected_signs", "published_signs", "missing_signs"):
        # Null placeholders preserve list cardinality without exposing arbitrary text.
        coverage[key] = [_sign(sign) for sign in raw[key]]
    return scope, coverage, set(raw["expected_signs"])


def _matches_scope(row, job):
    return all(row[key] == job[key] for key in ("target_date", "locale", "forecast_type"))


def _item_report(row, job, expected, inconsistencies, observations):
    linked = row["linked_forecast_id"] is not None
    matches_forecast = linked and (
        row["sign_key"], row["target_date"], row["locale"], row["forecast_type"]
    ) == (row["forecast_sign"], row["forecast_date"], row["forecast_locale"], row["forecast_type_link"])
    matches_job = _matches_scope(row, job)
    if not matches_job:
        inconsistencies.add("item_outside_job_scope")
    if expected is not None and row["sign_key"] not in expected:
        if job["signs"] is None:
            observations.add("item_outside_current_enabled_scope")
        else:
            inconsistencies.add("item_outside_job_scope")
        matches_job = False
    if row["forecast_id"] is not None and not linked:
        inconsistencies.add("item_forecast_link_missing")
    if linked and not matches_forecast:
        inconsistencies.add("item_forecast_scope_mismatch")
    if row["status"] in {"success", "skipped"} and not linked:
        inconsistencies.add("completed_item_without_forecast_link")
    if linked and row["status"] in {"success", "skipped"} and row["forecast_status"] != "published":
        inconsistencies.add("completed_item_link_not_published")
    return {
        "id": row["id"], "sign": _sign(row["sign_key"]),
        "date": row["target_date"].isoformat(), "locale": _enum(row["locale"], LOCALES),
        "forecast_type": _enum(row["forecast_type"], FORECAST_TYPES),
        "status": _enum(row["status"], ITEM_STATUSES),
        "provider_metadata": _enum(row["provider"], PROVIDERS),
        "started_at": _timestamp(row["started_at"]), "finished_at": _timestamp(row["finished_at"]),
        "response_evidence": "present" if row["response_present"] else "absent",
        "matches_reported_scope": matches_job if expected is not None else None,
        "matches_job_scope": matches_job if expected is not None and job["signs"] is not None else None,
        "forecast_link": {
            "id": row["forecast_id"],
            "state": "linked" if linked else ("missing" if row["forecast_id"] is not None else "not_linked"),
            "status": _enum(row["forecast_status"], {"published", "draft"}) if linked else None,
            "matches_item_scope": matches_forecast if linked else None,
            "references_this_item": row["forecast_item_id"] == row["id"] if linked else None,
        },
    }


def _inspect(connection, job_id, now, item_limit, attempt_limit, stale_after_minutes):
    base = {"schema_version": 1, "read_only": True, "job_id": job_id}
    job = _read_job(connection, job_id)
    if job is None:
        return {**base, "outcome": "not_found"}
    inconsistencies = set()
    observations = set()
    unknowns = {
        "worker_liveness_not_established", "transport_send_and_billing_not_established",
        "legacy_attempt_history_may_be_incomplete", "publication_causality_not_established",
    }
    scope, coverage, expected = _scope_and_coverage(connection, job)
    if expected is None:
        unknowns.add("job_sign_scope_unavailable")
    if scope["scope_source"] == "enabled_metadata":
        unknowns.add("historical_enabled_sign_scope_not_recorded")
    if coverage.get("redacted_sign_count") or "unknown" in (scope["locale"], scope["forecast_type"]):
        unknowns.add("scope_display_metadata_redacted")
    if job["job_type"] == "retry_missing" and job["signs"] is not None:
        inconsistencies.add("retry_missing_job_has_explicit_signs")

    run = _read_run(connection, job["run_id"]) if job["run_id"] is not None else None
    run_report = {"id": job["run_id"], "link_state": "not_linked" if job["run_id"] is None else "missing",
                  "record": None}
    items = {"state": "unavailable", "total": None, "status_counts": None,
             "returned": 0, "truncated": False, "records": []}
    attempts = dict(items)
    if run is None:
        unknowns.add("run_evidence_unavailable")
        if job["run_id"] is not None:
            inconsistencies.add("linked_run_missing")
    else:
        if not _matches_scope(run, job):
            inconsistencies.add("job_run_scope_mismatch")
        run_report = {"id": run["id"], "link_state": "linked", "record": {
            "run_type": _enum(run["run_type"], JOB_TYPES | {"retry"}),
            "status": _enum(run["status"], RUN_STATUSES),
            "date": run["target_date"].isoformat(), "locale": _enum(run["locale"], LOCALES),
            "forecast_type": _enum(run["forecast_type"], FORECAST_TYPES),
            "started_at": _timestamp(run["started_at"]), "finished_at": _timestamp(run["finished_at"]),
            "stored_counts": {key: run[key] for key in ("total_items", "success_items", "failed_items", "skipped_items")},
        }}
        item_counts = _counts(connection, GenerationItem, run["id"], ITEM_STATUSES)
        attempt_counts = _counts(connection, GenerationAttempt, run["id"], ATTEMPT_STATUSES)
        item_rows = _read_items(connection, run["id"], item_limit)
        attempt_rows = _read_attempts(connection, run["id"], attempt_limit)
        items = {"state": "observed", **item_counts, "returned": len(item_rows),
                 "truncated": item_counts["total"] > len(item_rows),
                 "records": [_item_report(row, job, expected, inconsistencies, observations) for row in item_rows]}
        attempts = {"state": "observed", **attempt_counts, "returned": len(attempt_rows),
                    "truncated": attempt_counts["total"] > len(attempt_rows), "records": [{
                        "id": row["id"], "item_id": row["item_id"], "attempt_no": row["attempt_no"],
                        "status": _enum(row["status"], ATTEMPT_STATUSES),
                        "provider_metadata": _enum(row["provider"], PROVIDERS),
                        "started_at": _timestamp(row["started_at"]), "finished_at": _timestamp(row["finished_at"]),
                        "response_evidence": "present" if row["response_present"] else "absent",
                        "transport_outcome": "unknown",
                    } for row in attempt_rows]}
        counts = item_counts["status_counts"]
        observed_counts = (item_counts["total"], counts.get("success", 0),
                           counts.get("failed", 0) + counts.get("interrupted", 0), counts.get("skipped", 0))
        if tuple(run[key] for key in ("total_items", "success_items", "failed_items", "skipped_items")) != observed_counts:
            observations.add("stored_run_counters_differ_from_items")
        if counts.get("unknown") or attempt_counts["status_counts"].get("unknown"):
            unknowns.add("unrecognized_lifecycle_status")
        if attempt_counts["total"] == 0:
            unknowns.add("no_persisted_attempts_does_not_prove_unsent")
        if any(row["status"] == "running" or row["finished_at"] is None or not row["response_present"] for row in attempt_rows):
            unknowns.add("incomplete_attempt_evidence")
        if items["truncated"] or attempts["truncated"]:
            unknowns.add("detail_checks_limited_to_returned_rows")
        if run["status"] not in RUN_STATUSES:
            unknowns.add("unrecognized_run_status")
        if run["status"] == "running" and run["finished_at"] is not None:
            inconsistencies.add("running_run_has_finished_at")
        if job["status"] == "success" and run["status"] != "success":
            inconsistencies.add("successful_job_has_non_success_run")

    locked_at = _timestamp(job["locked_at"])
    age = (now - job["locked_at"]).total_seconds() if locked_at else None
    lock = {
        "owner_present": bool(job["owner_present"]), "owner_identity": "withheld",
        "locked_at": locked_at, "age_seconds": age,
        "age_state": "missing" if job["locked_at"] is None else "unknown",
        "stale_after_minutes": stale_after_minutes, "worker_liveness": "unknown",
    }
    if age is not None:
        lock["age_state"] = "future" if age < 0 else ("older_than_threshold" if age > stale_after_minutes * 60 else "within_threshold")
    if lock["age_state"] == "older_than_threshold":
        observations.add("lock_older_than_threshold_is_not_worker_death")
    if age is not None and age < 0:
        inconsistencies.add("lock_timestamp_in_future")
    if job["status"] == "running" and (not job["owner_present"] or job["locked_at"] is None):
        inconsistencies.add("running_job_has_incomplete_lock_metadata")
    if job["status"] == "running" and job["finished_at"] is not None:
        inconsistencies.add("running_job_has_finished_at")
    if job["status"] not in JOB_STATUSES or job["provider"] not in PROVIDERS:
        unknowns.add("unrecognized_job_metadata")
    if coverage["published_count"]:
        unfinished = job["status"] in {"queued", "running"} or job["finished_at"] is None or (
            run is not None and (run["status"] == "running" or run["finished_at"] is None)
        )
        if unfinished:
            observations.add("published_content_with_unfinished_lifecycle")
    if job["status"] == "success" and coverage["missing_count"]:
        observations.add("successful_job_with_current_missing_publication")

    return {
        **base, "outcome": "ok", "observed_at": _timestamp(now),
        "job": {
            "status": _enum(job["status"], JOB_STATUSES), "job_type": _enum(job["job_type"], JOB_TYPES),
            "provider": _enum(job["provider"], PROVIDERS), "run_id": job["run_id"],
            "claim_attempt_count": job["attempt_count"], "max_job_attempts": job["max_job_attempts"],
            "max_item_attempts": job["max_attempts"], "max_retry_runs": job["max_retry_runs"],
            **{key: _timestamp(job[key]) for key in ("created_at", "updated_at", "started_at", "finished_at")},
        },
        "scope": scope, "coverage": coverage, "run": run_report, "lock": lock,
        "items": items, "attempts": attempts, "observations": sorted(observations),
        "inconsistencies": sorted(inconsistencies), "unknowns": sorted(unknowns),
        "limits": {"items": item_limit, "attempts": attempt_limit, "scope_signs": MAX_SCOPE_SIGNS,
                   "scope_bytes": MAX_SCOPE_BYTES, "detail_checks": "returned_rows_only",
                   "history": "currently_linked_run_only"},
    }


def inspect_generation_job(
    job_id: int, *, now: datetime | None = None, item_limit: int = 100,
    attempt_limit: int = 200, stale_after_minutes: int = 60,
) -> dict:
    """Inspect one persisted job without touching any caller ORM transaction.

    ``outcome=ok`` means a report was produced, not healthy or safe to retry.
    Counts cover the currently linked run; detail checks cover returned rows.
    ``now`` must be timezone-aware when supplied, for reproducible lock ages.
    """
    _validate_integer(job_id, "job_id", MAX_JOB_ID)
    _validate_integer(item_limit, "item_limit", MAX_ITEMS)
    _validate_integer(attempt_limit, "attempt_limit", MAX_ATTEMPTS)
    _validate_integer(stale_after_minutes, "stale_after_minutes", 10080)
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime.")
    now = now.astimezone(timezone.utc)
    try:
        with read_snapshot() as connection:
            return _inspect(connection, job_id, now, item_limit, attempt_limit, stale_after_minutes)
    except (RuntimeError, SQLAlchemyError):
        raise GenerationInspectionUnavailable("Generation inspection is unavailable.") from None

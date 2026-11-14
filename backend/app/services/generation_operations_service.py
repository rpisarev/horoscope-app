"""Current publication and queue observations for a protected local operator.

This is a read report, not worker health, historical SLO evidence, or authority
to generate/recover anything. All database reads share a separate snapshot.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, func, select

from ..business_date import business_datetime
from ..models import GenerationJob, GenerationRun
from .generation_read_service import published_coverage, read_snapshot


DEADLINE_TIMEZONE = "Europe/Kyiv"
JOB_STATUSES = ("queued", "running", "failed", "partial_failed", "success", "cancelled")
RUN_STATUSES = frozenset(("running", "success", "partial_failed", "failed", "interrupted"))
SIGN_PATTERN = r"[a-z][a-z0-9_]{0,31}"
LOCALE_PATTERN = r"[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?"
FORECAST_TYPE_PATTERN = r"[a-z][a-z0-9_-]{0,31}"


def _display_identifier(value: str, pattern: str) -> str | None:
    """Withhold malformed/secret-like display metadata; never change SQL scope."""
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        return None
    normalized = value.lower().replace("-", "_")
    if any(token in normalized for token in ("secret", "token", "password", "api_key")):
        return None
    return value


def _validate_scope(locale: str, forecast_type: str) -> None:
    if (
        not isinstance(locale, str)
        or len(locale) > 8
        or re.fullmatch(LOCALE_PATTERN, locale) is None
        or not isinstance(forecast_type, str)
        or re.fullmatch(FORECAST_TYPE_PATTERN, forecast_type) is None
    ):
        raise ValueError("Invalid operations report scope")


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("Operational timestamp is not timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _deadline(
    coverage: dict, *, target_date: date, now: datetime, timezone_matches: bool,
) -> dict:
    due = datetime.combine(target_date, time(6), ZoneInfo(DEADLINE_TIMEZONE))
    reached = now >= due if timezone_matches else None
    if not timezone_matches:
        state = "timezone_mismatch"
    elif coverage["expected_count"] == 0:
        state = "empty_enabled_signs"
    elif coverage["coverage_state"] == "full":
        state = "full_current"
    elif reached:
        state = "missing_after_deadline"
    else:
        state = "pending"
    return {
        "timezone": DEADLINE_TIMEZONE,
        "local_time": "06:00:00",
        # A different product timezone needs an explicit policy mapping first.
        "at": _utc_iso(due) if timezone_matches else None,
        "reached": reached,
        "state": state,
        "historical_on_time": "unknown",
        "historical_evidence": "no_immutable_publication_and_enablement_history",
    }


def _oldest_observation(created_at: datetime | None, now: datetime) -> dict:
    if created_at is None:
        return {"created_at": None, "age_seconds": None, "state": "not_observed"}
    timestamp = _utc_iso(created_at)
    age = (now - created_at).total_seconds()
    return {
        "created_at": timestamp,
        "age_seconds": age if age >= 0 else None,
        "state": "observed" if age >= 0 else "future_timestamp",
    }


def _queue_summary(
    connection: Connection, *, locale: str, forecast_type: str, now: datetime,
) -> dict:
    # One aggregate row, including statuses outside the current known vocabulary.
    # Raw status/error/provider/owner/payload fields are never selected.
    active = GenerationJob.status.in_(("queued", "running"))
    row = connection.execute(select(
        func.count().label("total"),
        *(func.count().filter(GenerationJob.status == status).label(status)
          for status in JOB_STATUSES),
        func.min(GenerationJob.created_at)
        .filter(GenerationJob.status == "queued").label("oldest_queued"),
        func.min(GenerationJob.created_at).filter(active).label("oldest_active"),
    ).where(
        GenerationJob.locale == locale,
        GenerationJob.forecast_type == forecast_type,
    )).mappings().one()
    counts = {status: row[status] for status in JOB_STATUSES}
    counts["unknown"] = row["total"] - sum(counts.values())
    active_count = counts["queued"] + counts["running"]
    return {
        "scope": {
            "locale": _display_identifier(locale, LOCALE_PATTERN),
            "forecast_type": _display_identifier(forecast_type, FORECAST_TYPE_PATTERN),
            "target_dates": "all",
        },
        "counts_by_status": counts,
        "total_count": row["total"],
        "active_count": active_count,
        "observation": "active_jobs_observed" if active_count else "no_active_jobs_observed",
        "oldest_queued": _oldest_observation(row["oldest_queued"], now),
        "oldest_active": _oldest_observation(row["oldest_active"], now),
        "blocking_reason": "unknown",
    }


def _last_known_run(connection: Connection, *, locale: str, forecast_type: str) -> dict | None:
    # "Latest" means the latest persisted run timestamp, not highest ID alone.
    observed = func.greatest(
        GenerationRun.started_at, GenerationRun.finished_at, GenerationRun.created_at,
    )
    row = connection.execute(select(
        GenerationRun.id, GenerationRun.target_date, GenerationRun.status,
        GenerationRun.started_at, GenerationRun.finished_at, GenerationRun.created_at,
        observed.label("observed_at"),
    ).where(
        GenerationRun.locale == locale,
        GenerationRun.forecast_type == forecast_type,
    ).order_by(observed.desc().nulls_last(), GenerationRun.id.desc()).limit(1)).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "date": row["target_date"].isoformat(),
        "status": row["status"] if row["status"] in RUN_STATUSES else "unknown",
        "started_at": _utc_iso(row["started_at"]),
        "finished_at": _utc_iso(row["finished_at"]),
        "created_at": _utc_iso(row["created_at"]),
        "observed_at": _utc_iso(row["observed_at"]),
        "ordering": "greatest_started_finished_created_desc_id_desc",
    }


def build_generation_operations_report(
    *, locale: str = "ru", forecast_type: str = "daily", now: datetime | None = None,
) -> dict:
    """Observe today/tomorrow in APP_TIMEZONE; tests may inject an aware UTC clock.

    Call inside an application context. No date override, ORM session access,
    provider calls, queue mutation, or schema migration is part of this report.
    Database/configuration failures propagate to the CLI's sanitized boundary.
    """
    _validate_scope(locale, forecast_type)
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("Operations report requires an aware UTC instant")
    business_now = business_datetime(now)
    today = business_now.date()
    tomorrow = today + timedelta(days=1)
    business_zone = str(business_now.tzinfo)
    timezone_matches = business_zone == DEADLINE_TIMEZONE

    with read_snapshot() as connection:
        # None scope preserves enabled_metadata / empty_enabled_signs semantics.
        # Repeated metadata reads remain consistent in the same snapshot.
        coverage = {
            label: published_coverage(
                connection, target_date=day, locale=locale, forecast_type=forecast_type,
            )
            for label, day in (("today", today), ("tomorrow", tomorrow))
        }
        queue = _queue_summary(connection, locale=locale, forecast_type=forecast_type, now=now)
        last_run = _last_known_run(connection, locale=locale, forecast_type=forecast_type)

    conditions = []
    if coverage["today"]["expected_count"] == 0:
        conditions.append("empty_enabled_signs")
    if not timezone_matches:
        conditions.append("timezone_mismatch")
    for label, day in (("today", today), ("tomorrow", tomorrow)):
        raw = coverage[label]
        # Redact only the presentation copy, retaining list order/cardinality and
        # the shared reader's exact-scope counts and coverage/deadline decisions.
        displayed = dict(raw)
        for key in ("expected_signs", "published_signs", "missing_signs"):
            displayed[key] = [_display_identifier(sign, SIGN_PATTERN) for sign in raw[key]]
        displayed["redacted_sign_count"] = displayed["expected_signs"].count(None)
        displayed["locale"] = _display_identifier(raw["locale"], LOCALE_PATTERN)
        displayed["forecast_type"] = _display_identifier(raw["forecast_type"], FORECAST_TYPE_PATTERN)
        displayed["deadline"] = _deadline(raw, target_date=day, now=now, timezone_matches=timezone_matches)
        coverage[label] = displayed
    return {
        "schema_version": 1,
        "observed_at": _utc_iso(now),
        "scope": {
            "locale": _display_identifier(locale, LOCALE_PATTERN),
            "forecast_type": _display_identifier(forecast_type, FORECAST_TYPE_PATTERN),
            "business_timezone": business_zone,
            "business_date": today.isoformat(),
            "tomorrow_date": tomorrow.isoformat(),
        },
        "state": "configuration_issue" if conditions else coverage["today"]["deadline"]["state"],
        "configuration": {"state": "attention_required" if conditions else "ok", "conditions": conditions},
        "coverage": coverage,
        "queue": queue,
        "last_known_run": last_run,
        "signals": {
            "api_liveness": "unknown",
            "database_read": "ok",
            "database_readiness": "not_assessed",
            "worker_liveness": "unknown",
            "worker_progress": "unknown",
            "worker_pause": "unknown",
            "worker_evidence": "no_durable_heartbeat_or_pause_evidence",
            "provider_quota": "unknown",
        },
    }

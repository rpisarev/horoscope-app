from __future__ import annotations

import os
from datetime import date
from typing import Any, Mapping

from flask import current_app
from werkzeug.datastructures import MultiDict

from ..models import GenerationAttempt, GenerationItem, GenerationRun
from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .generation_service import (
    get_missing_forecast_signs,
    has_generation_coverage,
    run_daily_generation,
    run_retry_for_missing_forecasts,
)
from .sign_service import get_enabled_sign_keys
from .. import db


class AdminGenerationValidationError(ValueError):
    pass


SUPPORTED_ADMIN_PROVIDERS = {"stub", "openai"}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_date(value: str | None, *, required: bool = True) -> date | None:
    if not value:
        if required:
            raise AdminGenerationValidationError("date is required and must use YYYY-MM-DD format.")
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdminGenerationValidationError("date must use YYYY-MM-DD format.") from exc


def _parse_int(
    value: str | None,
    *,
    default: int,
    min_value: int,
    max_value: int,
    name: str,
) -> int:
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise AdminGenerationValidationError(f"{name} must be an integer.") from exc

    if parsed < min_value or parsed > max_value:
        raise AdminGenerationValidationError(
            f"{name} must be between {min_value} and {max_value}."
        )

    return parsed


def _parse_int_value(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
    name: str,
) -> int:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        raise AdminGenerationValidationError(f"{name} must be an integer.")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminGenerationValidationError(f"{name} must be an integer.") from exc

    if parsed < min_value or parsed > max_value:
        raise AdminGenerationValidationError(
            f"{name} must be between {min_value} and {max_value}."
        )

    return parsed


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _scope_from_args(args: MultiDict[str, str], *, require_date: bool = True) -> dict[str, Any]:
    return {
        "target_date": _parse_date(args.get("date"), required=require_date),
        "locale": args.get("locale", DEFAULT_LOCALE),
        "forecast_type": args.get("type", DEFAULT_FORECAST_TYPE),
    }


def _require_json_object(body: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(body, Mapping):
        raise AdminGenerationValidationError("JSON body must be an object.")
    return body


def _body_value(body: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = body.get(name)
        if value is not None:
            return value
    return default


def _parse_provider_name(value: Any) -> str:
    provider_name = str(value or "stub").strip().lower()
    if not provider_name:
        provider_name = "stub"

    if provider_name not in SUPPORTED_ADMIN_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_ADMIN_PROVIDERS))
        raise AdminGenerationValidationError(
            f"provider must be one of: {allowed}."
        )

    return provider_name


def _parse_signs(value: Any) -> list[str] | None:
    if value is None:
        return None

    if not isinstance(value, list):
        raise AdminGenerationValidationError("signs must be a list of sign keys.")

    if not value:
        raise AdminGenerationValidationError("signs must not be empty when provided.")

    enabled_signs = get_enabled_sign_keys()
    enabled_set = set(enabled_signs)

    parsed: list[str] = []
    unknown_signs: list[str] = []

    for raw_sign in value:
        if not isinstance(raw_sign, str) or not raw_sign.strip():
            raise AdminGenerationValidationError("signs must contain non-empty strings only.")

        sign_key = raw_sign.strip().lower()
        if sign_key not in enabled_set:
            unknown_signs.append(sign_key)
            continue

        if sign_key not in parsed:
            parsed.append(sign_key)

    if unknown_signs:
        raise AdminGenerationValidationError(
            "Unknown or disabled sign keys: " + ", ".join(sorted(set(unknown_signs))) + "."
        )

    return parsed


def _config_bool(name: str) -> bool:
    value = current_app.config.get(name)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _ensure_provider_is_allowed(*, provider_name: str, allow_openai: bool) -> None:
    if provider_name != "openai":
        return

    if not _config_bool("ADMIN_API_ALLOW_OPENAI"):
        raise AdminGenerationValidationError(
            "provider=openai is disabled for Admin API. "
            "Set ADMIN_API_ALLOW_OPENAI=1 to enable it explicitly."
        )

    if not allow_openai:
        raise AdminGenerationValidationError(
            "provider=openai requires allow_openai=true in the JSON body."
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise AdminGenerationValidationError(
            "OPENAI_API_KEY is missing. Configure it before running OpenAI generation."
        )


def _parse_generation_body(body: Mapping[str, Any]) -> dict[str, Any]:
    body = _require_json_object(body)

    target_date_value = _body_value(body, "date", "target_date")
    target_date = _parse_date(str(target_date_value) if target_date_value is not None else None)

    locale = str(body.get("locale") or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE
    forecast_type = (
        str(_body_value(body, "type", "forecast_type", default=DEFAULT_FORECAST_TYPE)).strip()
        or DEFAULT_FORECAST_TYPE
    )

    provider_name = _parse_provider_name(body.get("provider"))
    allow_openai = _parse_bool(body.get("allow_openai"))

    max_attempts = _parse_int_value(
        body.get("max_attempts"),
        default=3,
        min_value=1,
        max_value=10,
        name="max_attempts",
    )
    stale_after_hours = _parse_int_value(
        body.get("stale_after_hours"),
        default=2,
        min_value=1,
        max_value=168,
        name="stale_after_hours",
    )

    return {
        "target_date": target_date,
        "locale": locale,
        "forecast_type": forecast_type,
        "provider_name": provider_name,
        "allow_openai": allow_openai,
        "max_attempts": max_attempts,
        "stale_after_hours": stale_after_hours,
    }


def create_manual_generation_run(body: Mapping[str, Any]) -> dict[str, Any]:
    params = _parse_generation_body(body)
    signs = _parse_signs(body.get("signs"))

    _ensure_provider_is_allowed(
        provider_name=params["provider_name"],
        allow_openai=params["allow_openai"],
    )

    run = run_daily_generation(
        target_date=params["target_date"],
        run_type="manual",
        locale=params["locale"],
        forecast_type=params["forecast_type"],
        provider_name=params["provider_name"],
        signs=signs,
        max_attempts=params["max_attempts"],
        stale_after_hours=params["stale_after_hours"],
    )

    return {
        "run": get_generation_run_detail(run.id, MultiDict()) if run else None,
        "requested": {
            "date": params["target_date"].isoformat(),
            "target_date": params["target_date"].isoformat(),
            "locale": params["locale"],
            "forecast_type": params["forecast_type"],
            "provider": params["provider_name"],
            "signs": signs,
            "max_attempts": params["max_attempts"],
            "stale_after_hours": params["stale_after_hours"],
        },
    }


def retry_missing_generation(body: Mapping[str, Any]) -> dict[str, Any]:
    params = _parse_generation_body(body)

    if "signs" in body:
        raise AdminGenerationValidationError(
            "signs is not supported for retry-missing. "
            "This endpoint retries all currently missing forecasts for the selected date."
        )

    max_retry_runs = _parse_int_value(
        body.get("max_retry_runs"),
        default=3,
        min_value=1,
        max_value=30,
        name="max_retry_runs",
    )

    _ensure_provider_is_allowed(
        provider_name=params["provider_name"],
        allow_openai=params["allow_openai"],
    )

    missing_signs = get_missing_forecast_signs(
        target_date=params["target_date"],
        locale=params["locale"],
        forecast_type=params["forecast_type"],
    )

    if not missing_signs:
        return {
            "run": None,
            "reason": "no_missing_forecasts",
            "missing_signs": [],
            "retry_runs_count": GenerationRun.query.filter_by(
                run_type="retry",
                target_date=params["target_date"],
                locale=params["locale"],
                forecast_type=params["forecast_type"],
            ).count(),
            "max_retry_runs": max_retry_runs,
        }

    retry_runs_count = GenerationRun.query.filter_by(
        run_type="retry",
        target_date=params["target_date"],
        locale=params["locale"],
        forecast_type=params["forecast_type"],
    ).count()

    if retry_runs_count >= max_retry_runs:
        return {
            "run": None,
            "reason": "retry_run_limit_reached",
            "missing_signs": missing_signs,
            "retry_runs_count": retry_runs_count,
            "max_retry_runs": max_retry_runs,
        }

    run = run_retry_for_missing_forecasts(
        target_date=params["target_date"],
        locale=params["locale"],
        forecast_type=params["forecast_type"],
        provider_name=params["provider_name"],
        max_attempts=params["max_attempts"],
        max_retry_runs=max_retry_runs,
        stale_after_hours=params["stale_after_hours"],
    )

    return {
        "run": get_generation_run_detail(run.id, MultiDict()) if run else None,
        "reason": None if run else "retry_not_started",
        "missing_signs_before": missing_signs,
        "retry_runs_count_before": retry_runs_count,
        "max_retry_runs": max_retry_runs,
        "requested": {
            "date": params["target_date"].isoformat(),
            "target_date": params["target_date"].isoformat(),
            "locale": params["locale"],
            "forecast_type": params["forecast_type"],
            "provider": params["provider_name"],
            "max_attempts": params["max_attempts"],
            "stale_after_hours": params["stale_after_hours"],
        },
    }


def get_generation_coverage(args: MultiDict[str, str]) -> dict[str, Any]:
    scope = _scope_from_args(args, require_date=True)
    sign_keys = get_enabled_sign_keys()
    missing_signs = get_missing_forecast_signs(
        target_date=scope["target_date"],
        locale=scope["locale"],
        forecast_type=scope["forecast_type"],
        signs=sign_keys,
    )
    missing_set = set(missing_signs)
    published_signs = [sign_key for sign_key in sign_keys if sign_key not in missing_set]

    return {
        "date": scope["target_date"].isoformat(),
        "target_date": scope["target_date"].isoformat(),
        "locale": scope["locale"],
        "forecast_type": scope["forecast_type"],
        "total_signs": len(sign_keys),
        "published_count": len(published_signs),
        "missing_count": len(missing_signs),
        "published_signs": published_signs,
        "missing_signs": missing_signs,
        "has_coverage": has_generation_coverage(
            target_date=scope["target_date"],
            locale=scope["locale"],
            forecast_type=scope["forecast_type"],
            signs=sign_keys,
        ),
    }


def list_generation_runs(args: MultiDict[str, str]) -> dict[str, Any]:
    scope = _scope_from_args(args, require_date=False)
    limit = _parse_int(
        args.get("limit"),
        default=20,
        min_value=1,
        max_value=100,
        name="limit",
    )
    offset = _parse_int(
        args.get("offset"),
        default=0,
        min_value=0,
        max_value=10000,
        name="offset",
    )

    query = GenerationRun.query

    if scope["target_date"] is not None:
        query = query.filter(GenerationRun.target_date == scope["target_date"])

    if args.get("locale"):
        query = query.filter(GenerationRun.locale == scope["locale"])

    if args.get("type"):
        query = query.filter(GenerationRun.forecast_type == scope["forecast_type"])

    status = args.get("status")
    if status:
        query = query.filter(GenerationRun.status == status)

    run_type = args.get("run_type")
    if run_type:
        query = query.filter(GenerationRun.run_type == run_type)

    total_count = query.count()
    runs = (
        query.order_by(GenerationRun.started_at.desc(), GenerationRun.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "items": [serialize_generation_run(run) for run in runs],
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
    }


def get_generation_run_detail(run_id: int, args: MultiDict[str, str]) -> dict[str, Any] | None:
    run = db.session.get(GenerationRun, run_id)
    if run is None:
        return None

    include_payloads = _parse_bool(args.get("include_payloads"))
    items = (
        GenerationItem.query.filter_by(run_id=run.id)
        .order_by(GenerationItem.id.asc())
        .all()
    )

    payload = serialize_generation_run(run)
    payload["items"] = [
        serialize_generation_item(item, include_payloads=include_payloads)
        for item in items
    ]
    return payload


def get_generation_item_attempts(item_id: int, args: MultiDict[str, str]) -> dict[str, Any] | None:
    item = db.session.get(GenerationItem, item_id)
    if item is None:
        return None

    include_payloads = _parse_bool(args.get("include_payloads"))
    attempts = (
        GenerationAttempt.query.filter_by(item_id=item.id)
        .order_by(GenerationAttempt.attempt_no.asc(), GenerationAttempt.id.asc())
        .all()
    )

    return {
        "item": serialize_generation_item(item, include_payloads=False),
        "attempts": [
            serialize_generation_attempt(attempt, include_payloads=include_payloads)
            for attempt in attempts
        ],
    }


def serialize_generation_run(run: GenerationRun) -> dict[str, Any]:
    target_date = run.target_date.isoformat()
    return {
        "id": run.id,
        "run_type": run.run_type,
        "date": target_date,
        "target_date": target_date,
        "locale": run.locale,
        "forecast_type": run.forecast_type,
        "status": run.status,
        "total_items": run.total_items,
        "success_items": run.success_items,
        "failed_items": run.failed_items,
        "skipped_items": run.skipped_items,
        "error_message": run.error_message,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "created_at": _iso(run.created_at),
    }


def serialize_generation_item(
    item: GenerationItem,
    *,
    include_payloads: bool,
) -> dict[str, Any]:
    target_date = item.target_date.isoformat()
    payload = {
        "id": item.id,
        "run_id": item.run_id,
        "sign_key": item.sign_key,
        "date": target_date,
        "target_date": target_date,
        "locale": item.locale,
        "forecast_type": item.forecast_type,
        "status": item.status,
        "forecast_id": item.forecast_id,
        "prompt_version_id": item.prompt_version_id,
        "provider": item.provider,
        "model_name": item.model_name,
        "error_message": item.error_message,
        "started_at": _iso(item.started_at),
        "finished_at": _iso(item.finished_at),
        "created_at": _iso(item.created_at),
    }

    if include_payloads:
        payload.update(
            {
                "request_payload": item.request_payload,
                "response_payload": item.response_payload,
                "raw_response": item.raw_response,
            }
        )

    return payload


def serialize_generation_attempt(
    attempt: GenerationAttempt,
    *,
    include_payloads: bool,
) -> dict[str, Any]:
    payload = {
        "id": attempt.id,
        "item_id": attempt.item_id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "provider": attempt.provider,
        "model_name": attempt.model_name,
        "error_type": attempt.error_type,
        "error_message": attempt.error_message,
        "started_at": _iso(attempt.started_at),
        "finished_at": _iso(attempt.finished_at),
        "created_at": _iso(attempt.created_at),
    }

    if include_payloads:
        payload.update(
            {
                "request_payload": attempt.request_payload,
                "response_payload": attempt.response_payload,
                "raw_response": attempt.raw_response,
            }
        )

    return payload
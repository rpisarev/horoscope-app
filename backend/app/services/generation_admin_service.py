from __future__ import annotations

from datetime import date
from typing import Any

from werkzeug.datastructures import MultiDict

from ..models import GenerationAttempt, GenerationItem, GenerationRun
from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .generation_service import get_missing_forecast_signs, has_generation_coverage
from .sign_service import get_enabled_sign_keys


class AdminGenerationValidationError(ValueError):
    pass


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


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _scope_from_args(args: MultiDict[str, str], *, require_date: bool = True) -> dict[str, Any]:
    return {
        "target_date": _parse_date(args.get("date"), required=require_date),
        "locale": args.get("locale", DEFAULT_LOCALE),
        "forecast_type": args.get("type", DEFAULT_FORECAST_TYPE),
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
    run = GenerationRun.query.get(run_id)
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
    item = GenerationItem.query.get(item_id)
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
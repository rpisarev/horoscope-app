from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .forecast_service import get_published_forecast, save_forecast
from .prompt_service import get_prompt_version
from .sign_service import get_enabled_sign_keys
from .. import db
from ..models import Forecast, GenerationAttempt, GenerationItem, GenerationRun, PromptVersion
from ..providers import (
    GenerationProviderError,
    HoroscopeProvider,
    ProviderRequest,
    ProviderResult,
    get_horoscope_provider,
)

logger = logging.getLogger(__name__)

FINAL_RUN_STATUSES = {"success", "partial_failed", "failed", "interrupted"}
STALE_ITEM_STATUSES = {"pending", "running"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def close_stale_running_runs(stale_after_hours: int = 2) -> int:
    cutoff = utcnow() - timedelta(hours=stale_after_hours)
    stale_runs = (
        GenerationRun.query.filter(
            GenerationRun.status == "running",
            GenerationRun.started_at < cutoff,
        )
        .order_by(GenerationRun.started_at.asc())
        .all()
    )

    closed_count = 0
    for run in stale_runs:
        run.status = "interrupted"
        run.finished_at = utcnow()
        run.error_message = (
            run.error_message
            or f"Run was still running after {stale_after_hours} hours and was marked as interrupted."
        )

        for item in run.items:
            if item.status in STALE_ITEM_STATUSES:
                item.status = "interrupted"
                item.finished_at = utcnow()
                item.error_message = item.error_message or "Parent run was interrupted."

        _refresh_run_counters(run)
        closed_count += 1

    if closed_count:
        db.session.commit()

    return closed_count


def run_daily_generation(
    *,
    target_date: date,
    run_type: str = "scheduled",
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider_name: str | None = None,
    signs: Iterable[str] | None = None,
    max_attempts: int = 3,
    stale_after_hours: int = 2,
) -> GenerationRun:
    close_stale_running_runs(stale_after_hours=stale_after_hours)

    active_run = GenerationRun.query.filter_by(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        status="running",
    ).first()
    if active_run:
        logger.info(
            "Generation skipped: active run already exists for %s locale=%s type=%s run_id=%s",
            target_date.isoformat(),
            locale,
            forecast_type,
            active_run.id,
        )
        return active_run

    sign_keys = list(signs) if signs is not None else get_enabled_sign_keys()
    run = GenerationRun(
        run_type=run_type,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        status="running",
        total_items=len(sign_keys),
        success_items=0,
        failed_items=0,
        skipped_items=0,
    )
    db.session.add(run)
    db.session.commit()

    try:
        provider = get_horoscope_provider(provider_name)
        prompt_version = get_prompt_version(locale=locale, forecast_type=forecast_type)
        _validate_preflight(
            run=run,
            sign_keys=sign_keys,
            prompt_version=prompt_version,
            max_attempts=max_attempts,
        )
    except Exception as exc:
        _fail_run(run, exc)
        return run

    items = [
        GenerationItem(
            run_id=run.id,
            sign_key=sign_key,
            target_date=target_date,
            locale=locale,
            forecast_type=forecast_type,
            status="pending",
            provider=provider.name,
            model_name=provider.model_name,
            prompt_version_id=prompt_version.id if prompt_version else None,
        )
        for sign_key in sign_keys
    ]
    db.session.add_all(items)
    db.session.commit()

    item_ids = [item.id for item in items]
    for item_id in item_ids:
        item = db.session.get(GenerationItem, item_id)
        try:
            _process_generation_item(
                item=item,
                provider=provider,
                prompt_version=prompt_version,
                max_attempts=max_attempts,
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            item = db.session.get(GenerationItem, item_id)
            if item:
                _mark_item_failed(item, exc)
                db.session.commit()
            logger.exception("Generation item failed unexpectedly: item_id=%s", item_id)

    run = db.session.get(GenerationRun, run.id)
    _finalize_run(run)
    db.session.commit()
    return run


def run_retry_for_missing_forecasts(
    *,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    provider_name: str | None = None,
    max_attempts: int = 3,
    max_retry_runs: int = 3,
    stale_after_hours: int = 2,
) -> GenerationRun | None:
    retry_runs_count = GenerationRun.query.filter_by(
        run_type="retry",
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    ).count()

    if retry_runs_count >= max_retry_runs:
        logger.info(
            "Retry generation skipped for %s: retry run limit reached (%s).",
            target_date.isoformat(),
            max_retry_runs,
        )
        return None

    missing_signs = get_missing_forecast_signs(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    )
    if not missing_signs:
        return None

    return run_daily_generation(
        target_date=target_date,
        run_type="retry",
        locale=locale,
        forecast_type=forecast_type,
        provider_name=provider_name,
        signs=missing_signs,
        max_attempts=max_attempts,
        stale_after_hours=stale_after_hours,
    )


def has_generation_coverage(
    *,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    signs: Iterable[str] | None = None,
) -> bool:
    return not get_missing_forecast_signs(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        signs=signs,
    )


def get_missing_forecast_signs(
    *,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    signs: Iterable[str] | None = None,
) -> list[str]:
    sign_keys = list(signs) if signs is not None else get_enabled_sign_keys()
    if not sign_keys:
        return []

    published_rows = (
        db.session.query(Forecast.sign_key)
        .filter(
            Forecast.sign_key.in_(sign_keys),
            Forecast.target_date == target_date,
            Forecast.locale == locale,
            Forecast.forecast_type == forecast_type,
            Forecast.status == "published",
        )
        .all()
    )
    published = {row.sign_key for row in published_rows}
    return [sign_key for sign_key in sign_keys if sign_key not in published]


def _validate_preflight(
    *,
    run: GenerationRun,
    sign_keys: list[str],
    prompt_version: PromptVersion | None,
    max_attempts: int,
) -> None:
    if not sign_keys:
        raise ValueError("No enabled zodiac signs found for generation.")
    if not prompt_version:
        raise ValueError(
            f"No active prompt version found for locale={run.locale}, forecast_type={run.forecast_type}."
        )
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")


def _process_generation_item(
    *,
    item: GenerationItem,
    provider: HoroscopeProvider,
    prompt_version: PromptVersion | None,
    max_attempts: int,
) -> None:
    existing_forecast = get_published_forecast(
        sign=item.sign_key,
        day=item.target_date,
        locale=item.locale,
        forecast_type=item.forecast_type,
    )
    if existing_forecast:
        item.status = "skipped"
        item.forecast_id = existing_forecast.id
        item.prompt_version_id = existing_forecast.prompt_version_id
        item.provider = existing_forecast.source
        item.model_name = existing_forecast.model_name
        item.finished_at = utcnow()
        item.error_message = None
        return

    item.status = "running"
    item.started_at = item.started_at or utcnow()
    item.provider = provider.name
    item.model_name = provider.model_name
    item.prompt_version_id = prompt_version.id if prompt_version else None
    db.session.flush()

    last_error: Exception | None = None
    for attempt_no in range(1, max_attempts + 1):
        attempt = GenerationAttempt(
            item_id=item.id,
            attempt_no=attempt_no,
            status="running",
            provider=provider.name,
            model_name=provider.model_name,
            request_payload=_request_payload(item, prompt_version),
            started_at=utcnow(),
        )
        db.session.add(attempt)
        db.session.flush()

        try:
            result = provider.generate(
                ProviderRequest(
                    target_date=item.target_date,
                    locale=item.locale,
                    forecast_type=item.forecast_type,
                    prompt_version=prompt_version,
                )
            )
            _validate_provider_result(result)
            _mark_attempt_success(attempt, result)
            forecast = save_forecast(
                sign=item.sign_key,
                day=item.target_date,
                text=result.text,
                model_version=result.model_name or provider.model_name,
                locale=item.locale,
                forecast_type=item.forecast_type,
                title=result.title,
                payload=result.payload,
                status="published",
                source=result.provider or provider.name,
                prompt_version_key=prompt_version.key if prompt_version else None,
                generation_item_id=item.id,
                commit=False,
            )
            item.status = "success"
            item.forecast_id = forecast.id
            item.provider = result.provider or provider.name
            item.model_name = result.model_name or provider.model_name
            item.request_payload = result.request_payload
            item.response_payload = result.response_payload
            item.raw_response = result.raw_response
            item.error_message = None
            item.finished_at = utcnow()
            return
        except GenerationProviderError as exc:
            last_error = exc
            will_retry = exc.retryable and attempt_no < max_attempts
            _mark_attempt_failed(attempt, exc, retryable=will_retry)
            if not exc.retryable:
                break
        except Exception as exc:
            last_error = exc
            _mark_attempt_failed(attempt, exc, retryable=False)
            break

    item.status = "failed"
    item.error_message = str(last_error) if last_error else "Generation failed."
    item.finished_at = utcnow()


def _validate_provider_result(result: ProviderResult) -> None:
    if not result.text or not result.text.strip():
        raise GenerationProviderError("Provider returned an empty forecast text.", retryable=True)


def _request_payload(item: GenerationItem, prompt_version: PromptVersion | None) -> dict:
    return {
        "target_date": item.target_date.isoformat(),
        "locale": item.locale,
        "forecast_type": item.forecast_type,
        "prompt_version": prompt_version.key if prompt_version else None,
    }


def _mark_attempt_success(attempt: GenerationAttempt, result: ProviderResult) -> None:
    attempt.status = "success"
    attempt.provider = result.provider or attempt.provider
    attempt.model_name = result.model_name or attempt.model_name
    attempt.request_payload = result.request_payload or attempt.request_payload
    attempt.response_payload = result.response_payload
    attempt.raw_response = result.raw_response
    attempt.error_type = None
    attempt.error_message = None
    attempt.finished_at = utcnow()


def _mark_attempt_failed(
    attempt: GenerationAttempt,
    exc: Exception,
    *,
    retryable: bool,
) -> None:
    attempt.status = "failed_retryable" if retryable else "failed"
    attempt.error_type = exc.__class__.__name__
    attempt.error_message = str(exc)
    attempt.finished_at = utcnow()


def _mark_item_failed(item: GenerationItem, exc: Exception) -> None:
    item.status = "failed"
    item.error_message = str(exc)
    item.finished_at = utcnow()


def _fail_run(run: GenerationRun, exc: Exception) -> None:
    run.status = "failed"
    run.error_message = str(exc)
    run.finished_at = utcnow()
    _refresh_run_counters(run)
    db.session.commit()


def _finalize_run(run: GenerationRun) -> None:
    _refresh_run_counters(run)
    if run.failed_items == 0:
        run.status = "success"
    elif run.success_items + run.skipped_items > 0:
        run.status = "partial_failed"
    else:
        run.status = "failed"
    run.finished_at = utcnow()


def _refresh_run_counters(run: GenerationRun) -> None:
    statuses = [item.status for item in run.items]
    run.total_items = len(statuses)
    run.success_items = statuses.count("success")
    run.skipped_items = statuses.count("skipped")
    run.failed_items = len(
        [status for status in statuses if status in {"failed", "interrupted"}]
    )
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID, uuid4

from paid_execution_policy import require_paid_execution
from paid_admission_policy import require_paid_admission
from sqlalchemy import select

from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .forecast_service import get_published_forecast, save_forecast
from .forecast_validation_service import find_forbidden_forecast_terms
from .generation_admission_service import GenerationPackageScope, package_admission
from .generation_execution_service import (
    assert_autonomous_session_clean,
    link_execution_run,
    record_execution_start,
    require_execution_activation,
    require_unlinked_execution,
    selected_provider_name,
)
from .prompt_service import build_provider_request, get_prompt_version
from .sign_service import get_enabled_sign_keys
from .. import db
from ..models import (
    Forecast, GenerationAttempt, GenerationExecutionRun, GenerationItem,
    GenerationRun, PromptVersion,
)
from ..providers import (
    GenerationProviderError,
    HoroscopeProvider,
    ProviderResult,
    get_horoscope_provider,
)
from ..providers.publication_policy import require_publication_provider


logger = logging.getLogger(__name__)

FINAL_RUN_STATUSES = {"success", "partial_failed", "failed", "interrupted"}
STALE_ITEM_STATUSES = {"pending", "running"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def close_stale_running_runs(stale_after_hours: int = 2) -> int:
    assert_autonomous_session_clean(db.session())
    cutoff = utcnow() - timedelta(hours=stale_after_hours)
    stale_runs = (
        GenerationRun.query.filter(
            GenerationRun.status == "running",
            GenerationRun.started_at < cutoff,
            ~select(GenerationExecutionRun.execution_id).where(
                GenerationExecutionRun.run_id == GenerationRun.id,
            ).exists(),
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
    execution_id: UUID | None = None,
    _max_retry_runs: int | None = None,
) -> GenerationRun | None:
    assert_autonomous_session_clean(db.session())
    # Keep the legacy argument compatible, but age cannot release another run's
    # package. Recovery needs proof/fencing, not a reaper on generation startup.

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
    try:
        canonical_provider = selected_provider_name(provider_name)
        # Admission uses selected identity before factory access, never mutable
        # adapter/result metadata. This remains closed until atomic .03c exists.
        require_paid_execution(canonical_provider)
        require_paid_admission(canonical_provider)
        provider = get_horoscope_provider(canonical_provider)
        publication_provider = provider.name
        require_paid_execution(publication_provider)
        require_publication_provider(publication_provider)
        prompt_version = get_prompt_version(locale=locale, forecast_type=forecast_type)
        _validate_preflight(
            run=run,
            sign_keys=sign_keys,
            prompt_version=prompt_version,
            max_attempts=max_attempts,
        )
        require_execution_activation()
    except Exception as exc:
        db.session.add(run)
        _fail_run(run, exc)
        return run

    # The queue already durably recorded its claim. Direct callers get exactly
    # one new identity. A run and its immutable link commit together, before any
    # item/provider activity. A failure here is never an unrecorded-call fallback.
    no_work = False
    try:
        session = db.session()
        if session.get_transaction() is None:
            session.begin()
        with package_admission(session, scope=GenerationPackageScope(
            target_date, locale, forecast_type,
        )):
            if _max_retry_runs is not None:
                # Authoritative check uses a fresh READ COMMITTED snapshot under
                # the package lock, even if a prior contender already finalized.
                retry_count = GenerationRun.query.filter_by(
                    run_type="retry", target_date=target_date, locale=locale,
                    forecast_type=forecast_type,
                ).count()
                sign_keys = get_missing_forecast_signs(
                    target_date=target_date, locale=locale, forecast_type=forecast_type,
                )
                no_work = retry_count >= _max_retry_runs or not sign_keys
                run.total_items = len(sign_keys)
            if not no_work:
                if execution_id is None:
                    execution_id = uuid4()
                    record_execution_start(
                        session, execution_id=execution_id, origin="dev_direct",
                        provider=canonical_provider, target_date=target_date,
                        locale=locale, forecast_type=forecast_type,
                    )
                else:
                    require_unlinked_execution(
                        session, execution_id=execution_id, provider=canonical_provider,
                        target_date=target_date, locale=locale, forecast_type=forecast_type,
                    )
                session.add(run)
                session.flush()
                link_execution_run(session, execution_id=execution_id, run_id=run.id)
        db.session.commit()
    except BaseException:
        db.session.rollback()
        raise

    if no_work:
        return None

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
                publication_provider=publication_provider,
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
    execution_id: UUID | None = None,
) -> GenerationRun | None:
    assert_autonomous_session_clean(db.session())
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
        _max_retry_runs=max_retry_runs,
        **({"execution_id": execution_id} if execution_id is not None else {}),
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
    publication_provider: str,
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
        provider_request = build_provider_request(
            prompt_version=prompt_version,
            sign_key=item.sign_key,
            target_date=item.target_date,
            locale=item.locale,
            forecast_type=item.forecast_type,
        )

        attempt = GenerationAttempt(
            item_id=item.id,
            attempt_no=attempt_no,
            status="running",
            provider=provider.name,
            model_name=provider.model_name,
            request_payload=provider_request.to_payload(),
            started_at=utcnow(),
        )
        db.session.add(attempt)
        db.session.flush()

        try:
            result = provider.generate(provider_request)
            _record_provider_result_payload(attempt, result)
            _validate_provider_result(result, locale=item.locale)
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
                publication_provider=publication_provider,
                commit=False,
            )

            item.status = "success"
            item.forecast_id = forecast.id
            item.provider = result.provider or provider.name
            item.model_name = result.model_name or provider.model_name
            item.request_payload = result.request_payload or attempt.request_payload
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


def _record_provider_result_payload(
    attempt: GenerationAttempt,
    result: ProviderResult,
) -> None:
    attempt.provider = result.provider or attempt.provider
    attempt.model_name = result.model_name or attempt.model_name
    attempt.request_payload = result.request_payload or attempt.request_payload
    attempt.response_payload = result.response_payload
    attempt.raw_response = result.raw_response


def _validate_provider_result(result: ProviderResult, *, locale: str) -> None:
    if not result.text or not result.text.strip():
        raise GenerationProviderError("Provider returned an empty forecast text.", retryable=True)

    violations = find_forbidden_forecast_terms(result.text, locale=locale)
    if violations:
        terms = ", ".join(violation.term for violation in violations[:5])
        raise GenerationProviderError(
            "Provider returned forecast text with forbidden zodiac terms: " f"{terms}.",
            retryable=True,
        )


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

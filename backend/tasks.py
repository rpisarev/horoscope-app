import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.services import (
    DEFAULT_FORECAST_TYPE,
    DEFAULT_LOCALE,
    GenerationJobValidationError,
    close_stale_running_jobs,
    create_scheduled_generation_job,
    create_scheduled_retry_missing_job,
    has_generation_coverage,
    process_generation_jobs,
    run_daily_generation,
    run_retry_for_missing_forecasts,
)
from app.services.scheduler_target_policy_service import (
    DEFAULT_SCHEDULED_ROLLING_DAYS,
    DEFAULT_SCHEDULED_TARGET_POLICY,
    SchedulerTargetPolicyError,
    resolve_scheduler_target_dates,
)


def env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_int(
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value == "":
        return default

    try:
        value = int(raw_value)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid integer value for %s=%r. Using default=%s.",
            name,
            raw_value,
            default,
        )
        return default

    if min_value is not None and value < min_value:
        logging.getLogger(__name__).warning(
            "Value for %s=%s is below minimum=%s. Using default=%s.",
            name,
            value,
            min_value,
            default,
        )
        return default

    if max_value is not None and value > max_value:
        logging.getLogger(__name__).warning(
            "Value for %s=%s is above maximum=%s. Using default=%s.",
            name,
            value,
            max_value,
            default,
        )
        return default

    return value


APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Kyiv")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

SCHEDULE_HOUR = env_int("SCHEDULE_HOUR", 1, min_value=0, max_value=23)
SCHEDULE_MINUTE = env_int("SCHEDULE_MINUTE", 0, min_value=0, max_value=59)
RUN_NIGHTLY_ON_START = env_flag("RUN_NIGHTLY_ON_START", "0")

HOROSCOPE_PROVIDER = os.getenv("HOROSCOPE_PROVIDER", "stub")
GENERATION_MAX_ATTEMPTS = env_int(
    "GENERATION_MAX_ATTEMPTS",
    3,
    min_value=1,
    max_value=10,
)
GENERATION_STALE_HOURS = env_int(
    "GENERATION_STALE_HOURS",
    2,
    min_value=1,
    max_value=168,
)

GENERATION_SCHEDULER_USE_QUEUE = env_flag("GENERATION_SCHEDULER_USE_QUEUE", "0")
GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI = env_flag(
    "GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI",
    "0",
)
GENERATION_SCHEDULED_JOB_PRIORITY = env_int(
    "GENERATION_SCHEDULED_JOB_PRIORITY",
    100,
    min_value=-1000,
    max_value=1000,
)
GENERATION_SCHEDULED_RETRY_JOB_PRIORITY = env_int(
    "GENERATION_SCHEDULED_RETRY_JOB_PRIORITY",
    90,
    min_value=-1000,
    max_value=1000,
)

GENERATION_SCHEDULED_TARGET_POLICY = os.getenv(
    "GENERATION_SCHEDULED_TARGET_POLICY",
    DEFAULT_SCHEDULED_TARGET_POLICY,
)

GENERATION_SCHEDULED_ROLLING_DAYS = env_int(
    "GENERATION_SCHEDULED_ROLLING_DAYS",
    DEFAULT_SCHEDULED_ROLLING_DAYS,
    min_value=1,
    max_value=366,
)

RETRY_MISSING_ENABLED = env_flag("RETRY_MISSING_ENABLED", "1")
RETRY_INTERVAL_MINUTES = env_int(
    "RETRY_INTERVAL_MINUTES",
    30,
    min_value=1,
    max_value=1440,
)
RETRY_WINDOW_START_HOUR = env_int(
    "RETRY_WINDOW_START_HOUR",
    1,
    min_value=0,
    max_value=23,
)
RETRY_WINDOW_END_HOUR = env_int(
    "RETRY_WINDOW_END_HOUR",
    6,
    min_value=0,
    max_value=24,
)
MAX_RETRY_RUNS_PER_DAY = env_int(
    "MAX_RETRY_RUNS_PER_DAY",
    3,
    min_value=1,
    max_value=30,
)

GENERATION_JOB_WORKER_ENABLED = env_flag("GENERATION_JOB_WORKER_ENABLED", "0")
GENERATION_JOB_WORKER_INTERVAL_SECONDS = env_int(
    "GENERATION_JOB_WORKER_INTERVAL_SECONDS",
    60,
    min_value=5,
    max_value=86400,
)
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK = env_int(
    "GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK",
    1,
    min_value=1,
    max_value=100,
)
GENERATION_JOB_WORKER_ALLOW_OPENAI = env_flag(
    "GENERATION_JOB_WORKER_ALLOW_OPENAI",
    "0",
)
GENERATION_JOB_STALE_AFTER_MINUTES = env_int(
    "GENERATION_JOB_STALE_AFTER_MINUTES",
    60,
    min_value=1,
    max_value=10080,
)
GENERATION_JOB_WORKER_ID = os.getenv(
    "GENERATION_JOB_WORKER_ID",
    f"scheduler-{os.getenv('HOSTNAME', 'local')}",
)


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [scheduler] %(message)s",
)
logger = logging.getLogger(__name__)

app = create_app()
scheduler = BlockingScheduler(timezone=APP_TIMEZONE)


def current_app_datetime() -> datetime:
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def scheduled_target_dates():
    base_date = current_app_date()

    try:
        return resolve_scheduler_target_dates(
            base_date=base_date,
            policy=GENERATION_SCHEDULED_TARGET_POLICY,
            rolling_days=GENERATION_SCHEDULED_ROLLING_DAYS,
        )
    except SchedulerTargetPolicyError as exc:
        logger.warning(
            "Invalid scheduled target-date policy configuration: %s. "
            "Falling back to policy=%s rolling_days=%s.",
            exc,
            DEFAULT_SCHEDULED_TARGET_POLICY,
            DEFAULT_SCHEDULED_ROLLING_DAYS,
        )
        return resolve_scheduler_target_dates(
            base_date=base_date,
            policy=DEFAULT_SCHEDULED_TARGET_POLICY,
            rolling_days=DEFAULT_SCHEDULED_ROLLING_DAYS,
        )


def _scheduled_target_dates_payload(target_days):
    return [target_day.isoformat() for target_day in target_days]


def _summarize_scheduled_job_results(*, run_type: str, job_type: str, target_days, results):
    return {
        "run_type": run_type,
        "job_type": job_type,
        "target_policy": GENERATION_SCHEDULED_TARGET_POLICY,
        "rolling_days": GENERATION_SCHEDULED_ROLLING_DAYS,
        "target_dates": _scheduled_target_dates_payload(target_days),
        "total_count": len(results),
        "created_count": sum(1 for result in results if result.get("created")),
        "skipped_count": sum(
            1
            for result in results
            if not result.get("created") and not result.get("error")
        ),
        "error_count": sum(1 for result in results if result.get("error")),
        "results": results,
    }


def current_app_date():
    return current_app_datetime().date()


def retry_window_is_open() -> bool:
    now = current_app_datetime()
    current_hour = now.hour + now.minute / 60

    return RETRY_WINDOW_START_HOUR <= current_hour < RETRY_WINDOW_END_HOUR


def create_daily_forecast_job(run_type: str = "scheduled") -> dict | None:
    target_days = scheduled_target_dates()

    logger.info(
        "Creating daily forecast generation jobs for dates=%s provider=%s "
        "run_type=%s allow_openai=%s target_policy=%s rolling_days=%s",
        ",".join(_scheduled_target_dates_payload(target_days)),
        HOROSCOPE_PROVIDER,
        run_type,
        GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI,
        GENERATION_SCHEDULED_TARGET_POLICY,
        GENERATION_SCHEDULED_ROLLING_DAYS,
    )

    results = []

    with app.app_context():
        for target_day in target_days:
            try:
                result = create_scheduled_generation_job(
                    target_date=target_day,
                    locale=DEFAULT_LOCALE,
                    forecast_type=DEFAULT_FORECAST_TYPE,
                    provider=HOROSCOPE_PROVIDER,
                    max_attempts=GENERATION_MAX_ATTEMPTS,
                    max_retry_runs=MAX_RETRY_RUNS_PER_DAY,
                    max_job_attempts=1,
                    priority=GENERATION_SCHEDULED_JOB_PRIORITY,
                    created_by=f"scheduler:{run_type}",
                    allow_openai=GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI,
                    skip_covered=True,
                )
            except GenerationJobValidationError as exc:
                logger.error(
                    "Daily forecast generation job was not created for %s: %s",
                    target_day.isoformat(),
                    exc,
                )
                result = {
                    "job": None,
                    "created": False,
                    "reason": "validation_error",
                    "error": str(exc),
                    "date": target_day.isoformat(),
                    "target_date": target_day.isoformat(),
                    "locale": DEFAULT_LOCALE,
                    "forecast_type": DEFAULT_FORECAST_TYPE,
                    "provider": HOROSCOPE_PROVIDER,
                    "job_type": "scheduled",
                }

            logger.info(
                "Daily forecast generation job result for %s: created=%s reason=%s job_id=%s",
                target_day.isoformat(),
                result["created"],
                result["reason"],
                result["job"]["id"] if result["job"] else None,
            )
            results.append(result)

    summary = _summarize_scheduled_job_results(
        run_type=run_type,
        job_type="scheduled",
        target_days=target_days,
        results=results,
    )

    logger.info(
        "Daily forecast generation jobs summary: target_dates=%s created=%s skipped=%s errors=%s",
        ",".join(summary["target_dates"]),
        summary["created_count"],
        summary["skipped_count"],
        summary["error_count"],
    )

    return summary

def generate_daily_forecasts(run_type: str = "scheduled"):
    if GENERATION_SCHEDULER_USE_QUEUE:
        return create_daily_forecast_job(run_type=run_type)

    target_days = scheduled_target_dates()

    logger.info(
        "Starting daily forecast generation for dates=%s provider=%s run_type=%s "
        "target_policy=%s rolling_days=%s",
        ",".join(_scheduled_target_dates_payload(target_days)),
        HOROSCOPE_PROVIDER,
        run_type,
        GENERATION_SCHEDULED_TARGET_POLICY,
        GENERATION_SCHEDULED_ROLLING_DAYS,
    )

    runs = []

    with app.app_context():
        for target_day in target_days:
            run = run_daily_generation(
                target_date=target_day,
                run_type=run_type,
                locale=DEFAULT_LOCALE,
                forecast_type=DEFAULT_FORECAST_TYPE,
                provider_name=HOROSCOPE_PROVIDER,
                max_attempts=GENERATION_MAX_ATTEMPTS,
                stale_after_hours=GENERATION_STALE_HOURS,
            )

            logger.info(
                "Daily forecast generation finished for %s: run_id=%s status=%s "
                "total=%s success=%s skipped=%s failed=%s",
                target_day.isoformat(),
                run.id,
                run.status,
                run.total_items,
                run.success_items,
                run.skipped_items,
                run.failed_items,
            )

            runs.append(
                {
                    "date": target_day.isoformat(),
                    "target_date": target_day.isoformat(),
                    "run_id": run.id,
                    "status": run.status,
                    "total_items": run.total_items,
                    "success_items": run.success_items,
                    "skipped_items": run.skipped_items,
                    "failed_items": run.failed_items,
                }
            )

    return {
        "run_type": run_type,
        "target_policy": GENERATION_SCHEDULED_TARGET_POLICY,
        "rolling_days": GENERATION_SCHEDULED_ROLLING_DAYS,
        "target_dates": _scheduled_target_dates_payload(target_days),
        "run_count": len(runs),
        "runs": runs,
    }


def create_retry_missing_forecast_job() -> dict | None:
    target_days = scheduled_target_dates()

    logger.info(
        "Creating retry-missing generation jobs for dates=%s provider=%s "
        "allow_openai=%s target_policy=%s rolling_days=%s",
        ",".join(_scheduled_target_dates_payload(target_days)),
        HOROSCOPE_PROVIDER,
        GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI,
        GENERATION_SCHEDULED_TARGET_POLICY,
        GENERATION_SCHEDULED_ROLLING_DAYS,
    )

    results = []

    with app.app_context():
        for target_day in target_days:
            try:
                result = create_scheduled_retry_missing_job(
                    target_date=target_day,
                    locale=DEFAULT_LOCALE,
                    forecast_type=DEFAULT_FORECAST_TYPE,
                    provider=HOROSCOPE_PROVIDER,
                    max_attempts=GENERATION_MAX_ATTEMPTS,
                    max_retry_runs=MAX_RETRY_RUNS_PER_DAY,
                    max_job_attempts=1,
                    priority=GENERATION_SCHEDULED_RETRY_JOB_PRIORITY,
                    created_by="scheduler:retry_missing",
                    allow_openai=GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI,
                )
            except GenerationJobValidationError as exc:
                logger.error(
                    "Retry-missing generation job was not created for %s: %s",
                    target_day.isoformat(),
                    exc,
                )
                result = {
                    "job": None,
                    "created": False,
                    "reason": "validation_error",
                    "error": str(exc),
                    "missing_signs": [],
                    "date": target_day.isoformat(),
                    "target_date": target_day.isoformat(),
                    "locale": DEFAULT_LOCALE,
                    "forecast_type": DEFAULT_FORECAST_TYPE,
                    "provider": HOROSCOPE_PROVIDER,
                    "job_type": "retry_missing",
                }

            logger.info(
                "Retry-missing generation job result for %s: created=%s reason=%s "
                "missing=%s job_id=%s",
                target_day.isoformat(),
                result["created"],
                result["reason"],
                len(result["missing_signs"]),
                result["job"]["id"] if result["job"] else None,
            )
            results.append(result)

    summary = _summarize_scheduled_job_results(
        run_type="retry_missing",
        job_type="retry_missing",
        target_days=target_days,
        results=results,
    )

    logger.info(
        "Retry-missing generation jobs summary: target_dates=%s created=%s skipped=%s errors=%s",
        ",".join(summary["target_dates"]),
        summary["created_count"],
        summary["skipped_count"],
        summary["error_count"],
    )

    return summary


def retry_missing_forecasts():
    if not RETRY_MISSING_ENABLED:
        return None

    if not retry_window_is_open():
        return None

    if GENERATION_SCHEDULER_USE_QUEUE:
        return create_retry_missing_forecast_job()

    target_days = scheduled_target_dates()
    runs = []

    with app.app_context():
        for target_day in target_days:
            if has_generation_coverage(
                target_date=target_day,
                locale=DEFAULT_LOCALE,
                forecast_type=DEFAULT_FORECAST_TYPE,
            ):
                logger.info(
                    "Retry skipped for %s: all forecasts are already published.",
                    target_day,
                )
                runs.append(
                    {
                        "date": target_day.isoformat(),
                        "target_date": target_day.isoformat(),
                        "run_id": None,
                        "status": "skipped",
                        "reason": "already_covered",
                    }
                )
                continue

            run = run_retry_for_missing_forecasts(
                target_date=target_day,
                locale=DEFAULT_LOCALE,
                forecast_type=DEFAULT_FORECAST_TYPE,
                provider_name=HOROSCOPE_PROVIDER,
                max_attempts=GENERATION_MAX_ATTEMPTS,
                max_retry_runs=MAX_RETRY_RUNS_PER_DAY,
                stale_after_hours=GENERATION_STALE_HOURS,
            )

            if not run:
                logger.info("Retry skipped for %s: no retry run created.", target_day)
                runs.append(
                    {
                        "date": target_day.isoformat(),
                        "target_date": target_day.isoformat(),
                        "run_id": None,
                        "status": "skipped",
                        "reason": "no_retry_run_created",
                    }
                )
                continue

            logger.info(
                "Retry generation finished for %s: run_id=%s status=%s total=%s "
                "success=%s skipped=%s failed=%s",
                target_day.isoformat(),
                run.id,
                run.status,
                run.total_items,
                run.success_items,
                run.skipped_items,
                run.failed_items,
            )

            runs.append(
                {
                    "date": target_day.isoformat(),
                    "target_date": target_day.isoformat(),
                    "run_id": run.id,
                    "status": run.status,
                    "total_items": run.total_items,
                    "success_items": run.success_items,
                    "skipped_items": run.skipped_items,
                    "failed_items": run.failed_items,
                }
            )

    return {
        "run_type": "retry_missing",
        "target_policy": GENERATION_SCHEDULED_TARGET_POLICY,
        "rolling_days": GENERATION_SCHEDULED_ROLLING_DAYS,
        "target_dates": _scheduled_target_dates_payload(target_days),
        "run_count": len([run for run in runs if run.get("run_id") is not None]),
        "runs": runs,
    }

def process_queued_generation_jobs() -> dict | None:
    if not GENERATION_JOB_WORKER_ENABLED:
        logger.debug("Generation job worker is disabled.")
        return None

    logger.info(
        "Generation job worker tick started: worker_id=%s limit=%s allow_openai=%s",
        GENERATION_JOB_WORKER_ID,
        GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK,
        GENERATION_JOB_WORKER_ALLOW_OPENAI,
    )

    with app.app_context():
        stale_closed_count = close_stale_running_jobs(
            stale_after_minutes=GENERATION_JOB_STALE_AFTER_MINUTES,
        )
        result = process_generation_jobs(
            limit=GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK,
            worker_id=GENERATION_JOB_WORKER_ID,
            allow_openai=GENERATION_JOB_WORKER_ALLOW_OPENAI,
            stale_after_hours=GENERATION_STALE_HOURS,
        )

    result["stale_closed_count"] = stale_closed_count

    logger.info(
        "Generation job worker tick finished: worker_id=%s processed=%s stale_closed=%s",
        result["worker_id"],
        result["processed_count"],
        stale_closed_count,
    )

    return result


@scheduler.scheduled_job(
    "cron",
    hour=SCHEDULE_HOUR,
    minute=SCHEDULE_MINUTE,
    id="nightly_daily_forecasts",
)
def nightly() -> None:
    generate_daily_forecasts(run_type="scheduled")


if RETRY_MISSING_ENABLED:

    @scheduler.scheduled_job(
        "interval",
        minutes=RETRY_INTERVAL_MINUTES,
        id="retry_missing_daily_forecasts",
    )
    def retry_missing() -> None:
        retry_missing_forecasts()


if GENERATION_JOB_WORKER_ENABLED:

    @scheduler.scheduled_job(
        "interval",
        seconds=GENERATION_JOB_WORKER_INTERVAL_SECONDS,
        id="queued_generation_jobs_worker",
    )
    def queued_generation_jobs_worker() -> None:
        process_queued_generation_jobs()


if __name__ == "__main__":
    logger.info(
    "Scheduler starting. Timezone=%s, nightly=%02d:%02d, run_on_start=%s, "
    "provider=%s, scheduler_use_queue=%s, scheduled_jobs_allow_openai=%s, "
    "target_policy=%s, rolling_days=%s, "
    "queue_worker_enabled=%s, queue_interval_seconds=%s, "
    "queue_max_jobs_per_tick=%s, queue_allow_openai=%s",
    APP_TIMEZONE,
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    RUN_NIGHTLY_ON_START,
    HOROSCOPE_PROVIDER,
    GENERATION_SCHEDULER_USE_QUEUE,
    GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI,
    GENERATION_SCHEDULED_TARGET_POLICY,
    GENERATION_SCHEDULED_ROLLING_DAYS,
    GENERATION_JOB_WORKER_ENABLED,
    GENERATION_JOB_WORKER_INTERVAL_SECONDS,
    GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK,
    GENERATION_JOB_WORKER_ALLOW_OPENAI,
)

    if RUN_NIGHTLY_ON_START:
        generate_daily_forecasts(run_type="on_start")

    scheduler.start()
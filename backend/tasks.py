import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.services import (
    DEFAULT_FORECAST_TYPE,
    DEFAULT_LOCALE,
    has_generation_coverage,
    run_daily_generation,
    run_retry_for_missing_forecasts,
)

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Kyiv")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "1"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))
RUN_NIGHTLY_ON_START = os.getenv("RUN_NIGHTLY_ON_START", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

HOROSCOPE_PROVIDER = os.getenv("HOROSCOPE_PROVIDER", "stub")
GENERATION_MAX_ATTEMPTS = int(os.getenv("GENERATION_MAX_ATTEMPTS", "3"))
GENERATION_STALE_HOURS = int(os.getenv("GENERATION_STALE_HOURS", "2"))

RETRY_MISSING_ENABLED = os.getenv("RETRY_MISSING_ENABLED", "1").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RETRY_INTERVAL_MINUTES = int(os.getenv("RETRY_INTERVAL_MINUTES", "30"))
RETRY_WINDOW_START_HOUR = int(os.getenv("RETRY_WINDOW_START_HOUR", "1"))
RETRY_WINDOW_END_HOUR = int(os.getenv("RETRY_WINDOW_END_HOUR", "6"))
MAX_RETRY_RUNS_PER_DAY = int(os.getenv("MAX_RETRY_RUNS_PER_DAY", "3"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [scheduler] %(message)s",
)
logger = logging.getLogger(__name__)

app = create_app()
scheduler = BlockingScheduler(timezone=APP_TIMEZONE)


def current_app_datetime() -> datetime:
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def current_app_date():
    return current_app_datetime().date()


def retry_window_is_open() -> bool:
    now = current_app_datetime()
    current_hour = now.hour + now.minute / 60
    return RETRY_WINDOW_START_HOUR <= current_hour < RETRY_WINDOW_END_HOUR


def generate_daily_forecasts(run_type: str = "scheduled") -> None:
    target_day = current_app_date()
    logger.info(
        "Starting daily forecast generation for %s provider=%s run_type=%s",
        target_day.isoformat(),
        HOROSCOPE_PROVIDER,
        run_type,
    )
    with app.app_context():
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
            "Daily forecast generation finished: run_id=%s status=%s total=%s success=%s skipped=%s failed=%s",
            run.id,
            run.status,
            run.total_items,
            run.success_items,
            run.skipped_items,
            run.failed_items,
        )


def retry_missing_forecasts() -> None:
    if not RETRY_MISSING_ENABLED:
        return
    if not retry_window_is_open():
        return

    target_day = current_app_date()
    with app.app_context():
        if has_generation_coverage(
            target_date=target_day,
            locale=DEFAULT_LOCALE,
            forecast_type=DEFAULT_FORECAST_TYPE,
        ):
            logger.info("Retry skipped for %s: all forecasts are already published.", target_day)
            return

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
            return

        logger.info(
            "Retry generation finished: run_id=%s status=%s total=%s success=%s skipped=%s failed=%s",
            run.id,
            run.status,
            run.total_items,
            run.success_items,
            run.skipped_items,
            run.failed_items,
        )


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


if __name__ == "__main__":
    logger.info(
        "Scheduler starting. Timezone=%s, nightly=%02d:%02d, run_on_start=%s, provider=%s",
        APP_TIMEZONE,
        SCHEDULE_HOUR,
        SCHEDULE_MINUTE,
        RUN_NIGHTLY_ON_START,
        HOROSCOPE_PROVIDER,
    )
    if RUN_NIGHTLY_ON_START:
        generate_daily_forecasts(run_type="on_start")
    scheduler.start()
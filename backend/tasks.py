import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.services import SIGNS, generate_horoscope, save_forecast

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

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [scheduler] %(message)s",
)

logger = logging.getLogger(__name__)

app = create_app()
scheduler = BlockingScheduler(timezone=APP_TIMEZONE)


def current_app_date():
    return datetime.now(ZoneInfo(APP_TIMEZONE)).date()


def generate_daily_forecasts() -> None:
    target_day = current_app_date()

    logger.info("Starting daily forecast generation for %s", target_day.isoformat())

    with app.app_context():
        for sign in SIGNS:
            logger.info("Generating forecast for sign=%s date=%s", sign, target_day)
            text = generate_horoscope(sign, target_day)
            save_forecast(sign, target_day, text, model_version="stub")

    logger.info("Daily forecast generation finished for %s", target_day.isoformat())


@scheduler.scheduled_job(
    "cron",
    hour=SCHEDULE_HOUR,
    minute=SCHEDULE_MINUTE,
    id="nightly_daily_forecasts",
)
def nightly() -> None:
    generate_daily_forecasts()


if __name__ == "__main__":
    logger.info(
        "Scheduler starting. Timezone=%s, nightly=%02d:%02d, run_on_start=%s",
        APP_TIMEZONE,
        SCHEDULE_HOUR,
        SCHEDULE_MINUTE,
        RUN_NIGHTLY_ON_START,
    )

    if RUN_NIGHTLY_ON_START:
        generate_daily_forecasts()

    scheduler.start()
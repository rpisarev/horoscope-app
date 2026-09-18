"""Product calendar dates; operational timestamps remain UTC."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def business_timezone() -> ZoneInfo:
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def business_datetime(instant: datetime | None = None) -> datetime:
    """Convert an aware instant to the configured business timezone."""
    if instant is None:
        instant = datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Business time requires a timezone-aware instant")
    return instant.astimezone(business_timezone())


def business_today() -> date:
    return business_datetime().date()

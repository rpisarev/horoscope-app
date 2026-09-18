from datetime import date, datetime, timedelta, timezone
import importlib

import pytest

from app import db
from app import business_date
from app.models import Forecast
from app.services import save_forecast


@pytest.mark.parametrize("instant,expected,offset", [
    ("2026-01-15T21:59:59+00:00", "2026-01-15", 2),
    ("2026-01-15T22:00:00+00:00", "2026-01-16", 2),
    ("2026-07-15T20:59:59+00:00", "2026-07-15", 3),
    ("2026-07-15T21:00:00+00:00", "2026-07-16", 3),
    ("2026-03-29T00:59:59+00:00", "2026-03-29", 2),
    ("2026-03-29T01:00:00+00:00", "2026-03-29", 3),
    ("2026-10-25T00:59:59+00:00", "2026-10-25", 3),
    ("2026-10-25T01:00:00+00:00", "2026-10-25", 2),
])
def test_business_date_boundaries(app, monkeypatch, instant, expected, offset):
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "Europe/Kyiv")
    with app.app_context():
        result = business_date.business_datetime(datetime.fromisoformat(instant))
    assert result.date().isoformat() == expected
    assert result.utcoffset() == timedelta(hours=offset)


def test_business_timezone_is_configurable(app, monkeypatch):
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "America/New_York")
    with app.app_context():
        result = business_date.business_datetime(datetime(2026, 1, 1, 1, tzinfo=timezone.utc))
    assert result.date() == date(2025, 12, 31)


def test_business_datetime_rejects_naive_instants(app):
    with app.app_context(), pytest.raises(ValueError, match="timezone-aware"):
        business_date.business_datetime(datetime(2026, 1, 1))


@pytest.mark.parametrize("zone,expected_day", [
    ("Europe/Kyiv", "2027-01-01"),
    ("America/New_York", "2026-12-31"),
])
def test_meta_forecast_default_and_years_share_business_date(client, app, monkeypatch, zone, expected_day):
    # The UTC/server day is still December 31 when Kyiv has entered January 1.
    instant = datetime(2026, 12, 31, 22, 0, 1, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return instant

    class ServerDate(date):
        @classmethod
        def today(cls):
            raise AssertionError("Product dates must not use the server OS date")

    monkeypatch.setattr(business_date, "datetime", FrozenDateTime)
    monkeypatch.setattr("app.routes.date", ServerDate)
    monkeypatch.setitem(app.config, "APP_TIMEZONE", zone)

    response = client.get("/api/meta")
    assert response.status_code == 200
    assert response.get_json() == {"business_date": expected_day, "timezone": zone}
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/years").get_json() == list(range(2024, int(expected_day[:4]) + 1))

    with app.app_context():
        for day in (date(2026, 12, 31), date(2027, 1, 1)):
            save_forecast(sign="aries", day=day, text=day.isoformat())

    response = client.get("/api/forecast?sign=aries")
    assert response.status_code == 200
    assert response.get_json()["date"] == expected_day
    assert response.get_json()["text"] == expected_day

    # The ORM's default is a domain date, too; it must use the same clock.
    with app.app_context():
        forecast = Forecast(sign_key="taurus", text="Draft")
        db.session.add(forecast)
        db.session.flush()
        assert forecast.target_date.isoformat() == expected_day

    tasks = importlib.import_module("tasks")
    monkeypatch.setitem(tasks.app.config, "APP_TIMEZONE", zone)
    assert tasks.current_app_date().isoformat() == expected_day

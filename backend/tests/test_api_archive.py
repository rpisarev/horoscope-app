from datetime import date

import pytest

from app import db
from app.models import Forecast, ZodiacSign
from app.services import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE, SIGNS


def _create_forecast(
    *,
    sign_key: str,
    target_date: date,
    status: str = "published",
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> Forecast:
    forecast = Forecast(
        sign_key=sign_key,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        text=f"Test forecast for {sign_key} on {target_date.isoformat()}",
        status=status,
        source="test",
        model_name="test-model",
    )
    db.session.add(forecast)
    db.session.commit()

    return forecast


def _create_full_day(target_date: date) -> None:
    for sign_key in SIGNS:
        _create_forecast(sign_key=sign_key, target_date=target_date)


def test_archive_day_returns_published_forecasts_for_date(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_forecast(
        sign_key="gemini",
        target_date=date(2026, 6, 1),
        status="draft",
    )
    _create_forecast(
        sign_key="cancer",
        target_date=date(2026, 6, 1),
        locale="uk",
    )
    _create_forecast(
        sign_key="leo",
        target_date=date(2026, 6, 1),
        forecast_type="weekly",
    )

    response = client.get("/api/archive/day?date=2026-06-01")

    assert response.status_code == 200

    data = response.get_json()
    assert data["date"] == "2026-06-01"
    assert data["locale"] == "ru"
    assert data["forecast_type"] == "daily"
    assert data["expected_sign_count"] == 13
    assert data["forecast_count"] == 2
    assert data["missing_count"] == 11
    assert data["has_full_coverage"] is False
    assert [item["sign_key"] for item in data["forecasts"]] == ["aries", "taurus"]


def test_archive_day_returns_full_coverage_for_complete_day(client):
    _create_full_day(date(2026, 6, 2))

    response = client.get("/api/archive/day?date=2026-06-02")

    assert response.status_code == 200

    data = response.get_json()
    assert data["forecast_count"] == 13
    assert data["missing_count"] == 0
    assert data["has_full_coverage"] is True
    assert len(data["forecasts"]) == 13


def test_archive_month_returns_daily_coverage_for_calendar_month(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_full_day(date(2026, 6, 3))
    _create_forecast(sign_key="aries", target_date=date(2026, 7, 1))
    _create_forecast(
        sign_key="gemini",
        target_date=date(2026, 6, 4),
        status="draft",
    )

    response = client.get("/api/archive/month?year=2026&month=6")

    assert response.status_code == 200

    data = response.get_json()
    assert data["year"] == 2026
    assert data["month"] == 6
    assert data["locale"] == "ru"
    assert data["forecast_type"] == "daily"
    assert data["expected_sign_count"] == 13
    assert len(data["days"]) == 30
    assert set(data) == {"year", "month", "locale", "forecast_type", "expected_sign_count", "days"}
    assert all(set(day) == {"date", "forecast_count", "missing_count", "has_full_coverage"} for day in data["days"])

    days_by_date = {item["date"]: item for item in data["days"]}
    assert days_by_date["2026-06-01"] == {
        "date": "2026-06-01",
        "forecast_count": 2,
        "has_full_coverage": False,
        "missing_count": 11,
    }
    assert days_by_date["2026-06-02"] == {
        "date": "2026-06-02",
        "forecast_count": 0,
        "has_full_coverage": False,
        "missing_count": 13,
    }
    assert days_by_date["2026-06-03"] == {
        "date": "2026-06-03",
        "forecast_count": 13,
        "has_full_coverage": True,
        "missing_count": 0,
    }
    assert days_by_date["2026-06-04"]["forecast_count"] == 0


def test_archive_months_returns_year_month_summaries(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 1, 10))
    _create_forecast(sign_key="taurus", target_date=date(2026, 1, 10))
    _create_full_day(date(2026, 2, 1))
    _create_forecast(
        sign_key="gemini",
        target_date=date(2026, 3, 5),
        status="draft",
    )

    response = client.get("/api/archive/months?year=2026")

    assert response.status_code == 200

    data = response.get_json()
    assert data["year"] == 2026
    assert data["locale"] == "ru"
    assert data["forecast_type"] == "daily"
    assert data["expected_sign_count"] == 13
    assert len(data["months"]) == 12

    months_by_number = {item["month"]: item for item in data["months"]}
    assert months_by_number[1] == {
        "year": 2026,
        "month": 1,
        "days_in_month": 31,
        "forecast_count": 2,
        "covered_day_count": 1,
        "full_coverage_day_count": 0,
        "has_forecasts": True,
        "has_full_month_coverage": False,
    }
    assert months_by_number[2] == {
        "year": 2026,
        "month": 2,
        "days_in_month": 28,
        "forecast_count": 13,
        "covered_day_count": 1,
        "full_coverage_day_count": 1,
        "has_forecasts": True,
        "has_full_month_coverage": False,
    }
    assert months_by_number[3] == {
        "year": 2026,
        "month": 3,
        "days_in_month": 31,
        "forecast_count": 0,
        "covered_day_count": 0,
        "full_coverage_day_count": 0,
        "has_forecasts": False,
        "has_full_month_coverage": False,
    }


def test_archive_months_filters_by_locale_and_type(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 4, 1))
    _create_forecast(sign_key="taurus", target_date=date(2026, 4, 1), locale="uk")
    _create_forecast(sign_key="gemini", target_date=date(2026, 4, 1), forecast_type="weekly")

    uk_response = client.get("/api/archive/months?year=2026&locale=uk")
    weekly_response = client.get("/api/archive/months?year=2026&type=weekly")

    assert uk_response.status_code == 200
    assert weekly_response.status_code == 200

    uk_months = {item["month"]: item for item in uk_response.get_json()["months"]}
    weekly_months = {item["month"]: item for item in weekly_response.get_json()["months"]}

    assert uk_months[4]["forecast_count"] == 1
    assert weekly_months[4]["forecast_count"] == 1


def test_archive_endpoints_reject_bad_query_params(client):
    assert client.get("/api/archive/day?date=bad-date").status_code == 400
    assert client.get("/api/archive/month?year=2026&month=13").status_code == 400
    assert client.get("/api/archive/months?year=not-a-year").status_code == 400


def test_archive_month_sign_availability_supplements_aggregate_contract(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 9, 18))
    _create_forecast(sign_key="taurus", target_date=date(2026, 9, 19))
    _create_forecast(sign_key="aries", target_date=date(2026, 8, 31))
    _create_forecast(sign_key="aries", target_date=date(2026, 10, 1))

    aggregate = client.get("/api/archive/month?year=2026&month=9").get_json()
    response = client.get("/api/archive/month?year=2026&month=9&sign=aries")
    assert response.status_code == 200
    data = response.get_json()
    assert {day["date"] for day in data["days"] if day["has_forecast"]} == {"2026-09-18"}
    assert all(isinstance(day["has_forecast"], bool) for day in data["days"])
    assert data["days"][18]["has_forecast"] is False  # Only Taurus is published.
    assert data["days"][18]["forecast_count"] == 1
    assert {
        **data,
        "days": [{key: value for key, value in day.items() if key != "has_forecast"} for day in data["days"]],
    } == aggregate


@pytest.mark.parametrize("status", ["draft", "failed", "archived"])
def test_archive_month_selected_sign_must_be_published(client, status):
    _create_forecast(sign_key="aries", target_date=date(2026, 9, 18), status=status)
    _create_forecast(sign_key="taurus", target_date=date(2026, 9, 18))
    response = client.get("/api/archive/month?year=2026&month=9&sign=aries")
    assert response.status_code == 200
    data = response.get_json()
    day = data["days"][17]
    assert day["has_forecast"] is False
    assert day["forecast_count"] == 1
    assert day["missing_count"] == data["expected_sign_count"] - 1


@pytest.mark.parametrize("locale,forecast_type", [("uk", "daily"), ("ru", "weekly"), ("uk", "weekly")])
def test_archive_month_sign_availability_matches_locale_and_type(client, locale, forecast_type):
    for sign_key, day in [("aries", 18), ("taurus", 19)]:
        _create_forecast(sign_key=sign_key, target_date=date(2026, 9, day), locale=locale, forecast_type=forecast_type)

    default = client.get("/api/archive/month?year=2026&month=9&sign=aries").get_json()
    assert not any(day["has_forecast"] for day in default["days"])
    response = client.get(f"/api/archive/month?year=2026&month=9&sign=aries&locale={locale}&type={forecast_type}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"] == locale
    assert data["forecast_type"] == forecast_type
    assert {day["date"] for day in data["days"] if day["has_forecast"]} == {"2026-09-18"}
    assert data["days"][18]["forecast_count"] == 1


@pytest.mark.parametrize("sign", ["not-a-sign", "", "ARIES"])
def test_archive_month_rejects_unknown_or_empty_sign(client, sign):
    response = client.get(f"/api/archive/month?year=2026&month=9&sign={sign}")
    assert response.status_code == 400
    assert "Unknown or inactive sign" in response.get_data(as_text=True)


def test_archive_month_rejects_disabled_sign_even_with_published_forecast(client):
    _create_forecast(sign_key="aries", target_date=date(2026, 9, 18))
    sign = db.session.get(ZodiacSign, "aries")
    was_enabled = sign.is_enabled
    try:
        sign.is_enabled = False
        db.session.commit()
        response = client.get("/api/archive/month?year=2026&month=9&sign=aries")
        assert response.status_code == 400
        assert "Unknown or inactive sign" in response.get_data(as_text=True)
    finally:
        sign.is_enabled = was_enabled
        db.session.commit()


@pytest.mark.parametrize("active_keys", [{"aries"}, {"aries", "taurus"}])
def test_archive_month_counts_active_signs_dynamically_with_or_without_sign(client, active_keys):
    _create_forecast(sign_key="aries", target_date=date(2026, 9, 18))
    _create_forecast(sign_key="taurus", target_date=date(2026, 9, 18))
    signs = ZodiacSign.query.all()
    original_flags = {sign.key: sign.is_enabled for sign in signs}
    try:
        for sign in signs:
            sign.is_enabled = sign.key in active_keys
        db.session.commit()
        for suffix in ("", "&sign=aries"):
            response = client.get(f"/api/archive/month?year=2026&month=9{suffix}")
            assert response.status_code == 200
            data = response.get_json()
            assert data["expected_sign_count"] == len(active_keys)
            assert data["days"][17]["forecast_count"] == len(active_keys)
            assert data["days"][17]["missing_count"] == 0
            assert data["days"][17]["has_full_coverage"] is True
            assert data["days"][16]["missing_count"] == len(active_keys)
            if suffix:
                assert data["days"][17]["has_forecast"] is True
    finally:
        for sign in signs:
            sign.is_enabled = original_flags[sign.key]
        db.session.commit()

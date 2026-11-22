from datetime import date

import pytest

from app import db
from app.models import Forecast, ZodiacSign


def add_forecast(locale, day, text, *, status="published", sign="aries"):
    db.session.add(Forecast(
        sign_key=sign, target_date=date.fromisoformat(day), locale=locale,
        forecast_type="daily", text=text, status=status, source="test",
    ))


def test_forecast_reads_only_the_requested_publication(client):
    texts = {"en": "Today is quiet.", "uk": "Сьогодні спокійно.", "ru": "Сегодня спокойно."}
    for locale, text in texts.items():
        add_forecast(locale, "2026-11-22", text)
    add_forecast("en", "2026-11-23", "English only")
    add_forecast("uk", "2026-11-23", "Українська чернетка", status="draft")
    db.session.commit()

    for locale, text in texts.items():
        response = client.get("/api/forecast", query_string={
            "sign": "aries", "date": "2026-11-22", "locale": locale,
        })
        assert response.status_code == 200
        forecast = response.get_json()
        assert forecast["locale"] == locale
        assert forecast["text"] == forecast["forecast"] == text

    for locale in ("uk", "ru"):
        response = client.get("/api/forecast", query_string={
            "sign": "aries", "date": "2026-11-23", "locale": locale,
        })
        assert response.status_code == 404
        assert response.get_json() == {
            "error": "forecast_not_published", "message": "Forecast is not published",
        }


def test_month_latest_and_years_follow_each_languages_published_dates(client):
    dates = {
        "en": ("2026-11-22", "2027-01-01"),
        "uk": ("2026-11-23", "2028-01-01"),
        "ru": ("2026-11-24", "2029-01-01"),
    }
    for locale, (november_day, latest) in dates.items():
        add_forecast(locale, november_day, "Published in November")
        add_forecast(locale, latest, "Latest published")
        add_forecast(locale, "2031-11-25", "Later draft", status="draft")
        add_forecast(locale, "2032-11-26", "Later publication for Taurus", sign="taurus")
    db.session.commit()

    for locale, (november_day, latest) in dates.items():
        scope = {"sign": "aries", "locale": locale}
        month = client.get("/api/archive/month", query_string={
            **scope, "year": 2026, "month": 11, "include_latest": 1,
        })
        assert month.status_code == 200
        data = month.get_json()
        assert data["locale"] == locale
        assert [day["date"] for day in data["days"] if day["has_forecast"]] == [november_day]
        assert data["latest_published_date"] == latest

        years = client.get("/api/years", query_string=scope)
        assert years.status_code == 200
        assert years.get_json() == [2026, date.fromisoformat(latest).year]


@pytest.mark.parametrize(("name_en", "name_uk"), [
    ("Test English", "Тест українською"),
    (None, None),
])
def test_sign_metadata_identifies_the_language_of_legacy_fallbacks(client, name_en, name_uk):
    sign = db.session.get(ZodiacSign, "aries")
    old_names = sign.name_en, sign.name_uk
    try:
        sign.name_en, sign.name_uk = name_en, name_uk
        db.session.commit()
        for locale, requested_name in {"en": name_en, "uk": name_uk, "ru": sign.name_ru}.items():
            response = client.get("/api/signs/meta", query_string={"locale": locale})
            assert response.status_code == 200
            data = response.get_json()
            assert data["locale"] == locale
            item = next(row for row in data["items"] if row["key"] == sign.key)
            expected = {
                "key": sign.key, "name": requested_name or sign.name_ru,
                "sort_order": sign.sort_order, "is_active": True,
            }
            if requested_name is None:
                expected["name_locale"] = "ru"
            assert item == expected
    finally:
        sign.name_en, sign.name_uk = old_names
        db.session.commit()

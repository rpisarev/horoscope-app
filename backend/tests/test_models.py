from datetime import date

from app.models import Forecast, ZodiacSign


def test_forecast_to_dict_keeps_frontend_compatibility():
    forecast = Forecast(
        id=1,
        sign_key="aries",
        target_date=date(2026, 5, 12),
        locale="ru",
        forecast_type="daily",
        title="Test title",
        text="Test forecast text",
        payload={"mood": "calm"},
        status="published",
        source="stub",
        model_name="stub",
    )

    data = forecast.to_dict()

    assert data["id"] == 1
    assert data["sign"] == "aries"
    assert data["sign_key"] == "aries"
    assert data["day"] == "2026-05-12"
    assert data["date"] == "2026-05-12"
    assert data["text"] == "Test forecast text"
    assert data["forecast"] == "Test forecast text"
    assert data["model_version"] == "stub"
    assert data["model_name"] == "stub"
    assert data["payload"] == {"mood": "calm"}


def test_zodiac_sign_to_dict_formats_date_ranges():
    sign = ZodiacSign(
        key="aries",
        name_ru="Овен",
        name_uk="Овен",
        name_en="Aries",
        glyph="♈",
        start_month=4,
        start_day=19,
        end_month=5,
        end_day=14,
        sort_order=1,
        is_enabled=True,
    )

    data = sign.to_dict()

    assert data == {
        "key": "aries",
        "nameRu": "Овен",
        "nameUk": "Овен",
        "nameEn": "Aries",
        "glyph": "♈",
        "start": "04-19",
        "end": "05-14",
        "sortOrder": 1,
        "enabled": True,
    }
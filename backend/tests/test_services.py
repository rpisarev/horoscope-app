from datetime import date

from app.models import Forecast
from app.services import (
    DEFAULT_PROMPT_VERSION_KEY,
    SIGNS,
    generate_horoscope,
    get_forecast,
    save_forecast,
)


def test_signs_list_is_stable():
    assert len(SIGNS) == 13
    assert len(set(SIGNS)) == 13
    assert SIGNS[0] == "aries"
    assert SIGNS[-1] == "ophiuchus"
    assert "ophiuchus" in SIGNS


def test_generate_horoscope_returns_non_empty_placeholder_text():
    text = generate_horoscope("aries", date(2026, 5, 12))

    assert isinstance(text, str)
    assert text.strip()
    assert len(text) > 50


def test_save_forecast_creates_forecast(app):
    with app.app_context():
        forecast = save_forecast(
            sign="aries",
            day=date(2026, 5, 12),
            text="Initial forecast text",
            model_version="stub",
        )

        fetched = get_forecast("aries", date(2026, 5, 12))

        assert forecast.id is not None
        assert fetched is not None
        assert fetched.id == forecast.id
        assert fetched.text == "Initial forecast text"
        assert fetched.status == "published"
        assert fetched.source == "stub"
        assert fetched.model_name == "stub"
        assert fetched.published_at is not None
        assert fetched.prompt_version is not None
        assert fetched.prompt_version.key == DEFAULT_PROMPT_VERSION_KEY


def test_save_forecast_updates_existing_forecast_instead_of_creating_duplicate(app):
    with app.app_context():
        first = save_forecast(
            sign="aries",
            day=date(2026, 5, 12),
            text="Initial forecast text",
            model_version="stub",
        )

        second = save_forecast(
            sign="aries",
            day=date(2026, 5, 12),
            text="Updated forecast text",
            model_version="stub-v2",
        )

        count = Forecast.query.filter_by(
            sign_key="aries",
            target_date=date(2026, 5, 12),
            locale="ru",
            forecast_type="daily",
        ).count()

        assert first.id == second.id
        assert count == 1
        assert second.text == "Updated forecast text"
        assert second.model_name == "stub-v2"


def test_save_forecast_can_store_payload_and_title(app):
    with app.app_context():
        forecast = save_forecast(
            sign="taurus",
            day=date(2026, 6, 1),
            title="Daily Taurus",
            text="Forecast with payload",
            payload={"mood": "focused", "lucky_number": 7},
            model_version="stub",
        )

        assert forecast.title == "Daily Taurus"
        assert forecast.payload == {"mood": "focused", "lucky_number": 7}
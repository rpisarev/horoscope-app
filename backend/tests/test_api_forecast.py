from datetime import date
from unittest.mock import Mock

import pytest

from app import db, providers, routes, services
from app.models import Forecast, GenerationAttempt, GenerationItem, GenerationJob, GenerationRun
from app.services import forecast_service, generation_service, save_forecast


MISSING_RESPONSE = {
    "error": "forecast_not_published",
    "message": "Forecast is not published",
}


@pytest.mark.parametrize("source,model_name", [("openai", "saved-model"), ("stub", "stub")])
def test_forecast_endpoint_returns_published_forecast_with_compatible_aliases(
    client, app, source, model_name
):
    with app.app_context():
        stored = save_forecast(
            sign="aries", day=date(2026, 5, 12), text="Already published text",
            status="published", source=source, model_version=model_name,
        ).to_dict()

    for _ in range(2):
        response = client.get("/api/forecast?sign=aries&date=2026-05-12")
        assert response.status_code == 200
        data = response.get_json()
        assert data == stored
        assert data["sign"] == data["sign_key"] == "aries"
        assert data["day"] == data["date"] == "2026-05-12"
        assert data["text"] == data["forecast"] == "Already published text"
        assert data["model_version"] == data["model_name"] == model_name
        assert data["status"] == "published"
        assert data["source"] == source

    with app.app_context():
        assert Forecast.query.count() == 1


def test_missing_forecast_is_read_only_even_on_repeated_requests(client, app, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Public reads must not generate or save"))
    for module, names in [
        (routes, ["generate_horoscope", "save_forecast", "run_daily_generation"]),
        (services, ["generate_horoscope", "save_forecast", "run_daily_generation"]),
        (forecast_service, ["generate_horoscope", "save_forecast", "get_horoscope_provider"]),
        (generation_service, ["run_daily_generation", "get_horoscope_provider"]),
        (providers, ["get_horoscope_provider"]),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, forbidden, raising=False)

    with monkeypatch.context() as no_commit:
        no_commit.setattr(db.session, "commit", forbidden)
        for _ in range(2):
            response = client.get("/api/forecast?sign=aries&date=2026-05-12")
            assert response.status_code == 404
            assert response.get_json() == MISSING_RESPONSE
            with app.app_context():
                for model in (Forecast, GenerationJob, GenerationRun, GenerationItem, GenerationAttempt):
                    assert model.query.count() == 0

    forbidden.assert_not_called()


@pytest.mark.parametrize("status", ["draft", "failed", "archived"])
def test_forecast_endpoint_hides_non_published_forecast(client, app, status):
    with app.app_context():
        stored = save_forecast(
            sign="aries", day=date(2026, 5, 12), text="Private text", status=status,
        ).to_dict()

    response = client.get("/api/forecast?sign=aries&date=2026-05-12")
    assert response.status_code == 404
    assert response.get_json() == MISSING_RESPONSE
    with app.app_context():
        assert Forecast.query.one().to_dict() == stored


def test_forecast_endpoint_respects_locale_and_type(client, app):
    with app.app_context():
        save_forecast(
            sign="aries", day=date(2026, 5, 12), text="Scoped forecast",
            locale="uk", forecast_type="weekly",
        )

    assert client.get("/api/forecast?sign=aries&date=2026-05-12").status_code == 404
    assert client.get("/api/forecast?sign=aries&date=2026-05-12&locale=uk").status_code == 404
    response = client.get("/api/forecast?sign=aries&date=2026-05-12&locale=uk&type=weekly")
    assert response.status_code == 200
    assert response.get_json()["locale"] == "uk"
    assert response.get_json()["forecast_type"] == "weekly"


@pytest.mark.parametrize("query", [
    "date=2026-05-12", "sign=unknown&date=2026-05-12",
    "sign=aries&date=not-a-date", "sign=aries&date=2026-02-30",
])
def test_forecast_endpoint_keeps_invalid_input_validation(client, query):
    assert client.get(f"/api/forecast?{query}").status_code == 400

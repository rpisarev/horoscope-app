from datetime import date

from app.models import Forecast


def test_forecast_endpoint_creates_published_stub_forecast(client, app):
    response = client.get("/api/forecast?sign=aries&date=2026-05-12")

    assert response.status_code == 200

    data = response.get_json()

    assert data["id"] is not None
    assert data["sign"] == "aries"
    assert data["sign_key"] == "aries"
    assert data["day"] == "2026-05-12"
    assert data["date"] == "2026-05-12"
    assert data["locale"] == "ru"
    assert data["forecast_type"] == "daily"
    assert data["text"]
    assert data["forecast"] == data["text"]
    assert data["status"] == "published"
    assert data["source"] == "stub"
    assert data["model_version"] == "stub"
    assert data["model_name"] == "stub"
    assert data["prompt_version"] == "daily-ru-v1"

    with app.app_context():
        forecasts = Forecast.query.all()

    assert len(forecasts) == 1
    assert forecasts[0].sign_key == "aries"
    assert forecasts[0].status == "published"
    assert forecasts[0].published_at is not None


def test_forecast_endpoint_is_idempotent_for_same_sign_date(client, app):
    first_response = client.get("/api/forecast?sign=aries&date=2026-05-12")
    second_response = client.get("/api/forecast?sign=aries&date=2026-05-12")

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_data = first_response.get_json()
    second_data = second_response.get_json()

    assert first_data["id"] == second_data["id"]

    with app.app_context():
        count = Forecast.query.filter_by(
            sign_key="aries",
            target_date=date(2026, 5, 12),
            locale="ru",
            forecast_type="daily",
        ).count()

    assert count == 1


def test_forecast_endpoint_rejects_unknown_sign(client):
    response = client.get("/api/forecast?sign=unknown&date=2026-05-12")

    assert response.status_code == 400


def test_forecast_endpoint_rejects_bad_date(client):
    response = client.get("/api/forecast?sign=aries&date=not-a-date")

    assert response.status_code == 400
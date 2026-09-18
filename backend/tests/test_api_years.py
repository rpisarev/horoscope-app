from datetime import date

from app.services import save_forecast


def test_years_endpoint_returns_fallback_when_no_forecasts_exist(client, monkeypatch):
    monkeypatch.setattr("app.routes.business_today", lambda: date(2027, 1, 1))
    response = client.get("/api/years")

    assert response.status_code == 200

    data = response.get_json()

    assert data == [2024, 2025, 2026, 2027]


def test_years_endpoint_returns_years_from_published_forecasts(client, app):
    with app.app_context():
        save_forecast(sign="aries", day=date(2026, 5, 12), text="Published forecast")

    response = client.get("/api/years")

    assert response.status_code == 200
    assert response.get_json() == [2026]


def test_years_endpoint_filters_by_sign(client, app):
    with app.app_context():
        save_forecast(sign="aries", day=date(2026, 5, 12), text="Published forecast")
        save_forecast(sign="taurus", day=date(2027, 1, 3), text="Published forecast")

    aries_years_response = client.get("/api/years?sign=aries")
    taurus_years_response = client.get("/api/years?sign=taurus")

    assert aries_years_response.status_code == 200
    assert taurus_years_response.status_code == 200

    assert aries_years_response.get_json() == [2026]
    assert taurus_years_response.get_json() == [2027]


def test_years_endpoint_rejects_unknown_sign(client):
    response = client.get("/api/years?sign=unknown")

    assert response.status_code == 400
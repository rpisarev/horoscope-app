from datetime import date


def test_years_endpoint_returns_fallback_when_no_forecasts_exist(client):
    response = client.get("/api/years")

    assert response.status_code == 200

    data = response.get_json()

    assert isinstance(data, list)
    assert 2024 in data
    assert date.today().year in data
    assert all(isinstance(year, int) for year in data)


def test_years_endpoint_returns_years_from_published_forecasts(client):
    create_response = client.get("/api/forecast?sign=aries&date=2026-05-12")
    assert create_response.status_code == 200

    response = client.get("/api/years")

    assert response.status_code == 200
    assert response.get_json() == [2026]


def test_years_endpoint_filters_by_sign(client):
    aries_response = client.get("/api/forecast?sign=aries&date=2026-05-12")
    taurus_response = client.get("/api/forecast?sign=taurus&date=2027-01-03")

    assert aries_response.status_code == 200
    assert taurus_response.status_code == 200

    aries_years_response = client.get("/api/years?sign=aries")
    taurus_years_response = client.get("/api/years?sign=taurus")

    assert aries_years_response.status_code == 200
    assert taurus_years_response.status_code == 200

    assert aries_years_response.get_json() == [2026]
    assert taurus_years_response.get_json() == [2027]


def test_years_endpoint_rejects_unknown_sign(client):
    response = client.get("/api/years?sign=unknown")

    assert response.status_code == 400
from contextlib import contextmanager
from datetime import date, datetime, timezone

from app import db
from app.models import Forecast
from app.services import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE


@contextmanager
def _temporary_public_site_url(app, value: str):
    had_original_value = "PUBLIC_SITE_URL" in app.config
    original_value = app.config.get("PUBLIC_SITE_URL")

    app.config["PUBLIC_SITE_URL"] = value

    try:
        yield
    finally:
        if had_original_value:
            app.config["PUBLIC_SITE_URL"] = original_value
        else:
            app.config.pop("PUBLIC_SITE_URL", None)


def _create_forecast(
    *,
    sign_key: str,
    target_date: date,
    status: str = "published",
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    published_at: datetime | None = None,
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
        published_at=published_at,
    )
    db.session.add(forecast)
    db.session.commit()

    return forecast


def _paths(data):
    return [item["path"] for item in data["items"]]


def test_sitemap_urls_endpoint_returns_canonical_url_items(client, app):
    _create_forecast(
        sign_key="aries",
        target_date=date(2026, 6, 1),
        published_at=datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc),
    )
    _create_forecast(
        sign_key="taurus",
        target_date=date(2026, 6, 2),
        published_at=datetime(2026, 6, 2, 12, 30, tzinfo=timezone.utc),
    )
    _create_forecast(
        sign_key="gemini",
        target_date=date(2026, 6, 3),
        status="draft",
    )

    with _temporary_public_site_url(app, "https://example.com/"):
        response = client.get("/api/seo/sitemap/urls")

    assert response.status_code == 200

    data = response.get_json()
    assert data["site_url"] == "https://example.com"
    assert data["locale"] == "ru"
    assert data["forecast_type"] == "daily"
    assert data["from"] is None
    assert data["to"] is None
    assert data["include_home"] is True
    assert data["include_forecasts"] is True
    assert data["include_archive_months"] is True

    assert _paths(data) == [
        "/",
        "/horoscope/aries/2026-06-01",
        "/horoscope/taurus/2026-06-02",
        "/archive/aries/2026/06",
        "/archive/taurus/2026/06",
    ]

    assert data["items"][1] == {
        "type": "forecast",
        "loc": "https://example.com/horoscope/aries/2026-06-01",
        "path": "/horoscope/aries/2026-06-01",
        "lastmod": "2026-06-01T12:30:00+00:00",
        "sign_key": "aries",
        "date": "2026-06-01",
    }

    assert "/archive/aries/2026/06/01" not in _paths(data)


def test_sitemap_urls_endpoint_filters_by_query_params(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 5, 31))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="gemini", target_date=date(2026, 6, 30))
    _create_forecast(sign_key="cancer", target_date=date(2026, 7, 1))
    _create_forecast(sign_key="leo", target_date=date(2026, 6, 15), locale="uk")
    _create_forecast(sign_key="virgo", target_date=date(2026, 6, 16), forecast_type="weekly")

    with _temporary_public_site_url(app, "https://example.com"):
        response = client.get(
            "/api/seo/sitemap/urls"
            "?from=2026-06-01"
            "&to=2026-06-30"
            "&include_home=0"
        )

        uk_response = client.get(
            "/api/seo/sitemap/urls"
            "?locale=uk"
            "&include_home=0"
            "&include_archive_months=0"
        )
        weekly_response = client.get(
            "/api/seo/sitemap/urls"
            "?type=weekly"
            "&include_home=0"
            "&include_archive_months=0"
        )

    assert response.status_code == 200

    data = response.get_json()
    assert data["from"] == "2026-06-01"
    assert data["to"] == "2026-06-30"
    assert data["include_home"] is False

    assert _paths(data) == [
        "/horoscope/taurus/2026-06-01",
        "/horoscope/gemini/2026-06-30",
        "/archive/taurus/2026/06",
        "/archive/gemini/2026/06",
    ]

    assert uk_response.status_code == 200
    assert weekly_response.status_code == 200

    assert _paths(uk_response.get_json()) == ["/horoscope/leo/2026-06-15"]
    assert _paths(weekly_response.get_json()) == ["/horoscope/virgo/2026-06-16"]


def test_sitemap_urls_endpoint_respects_include_flags(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))

    with _temporary_public_site_url(app, "https://example.com"):
        response = client.get(
            "/api/seo/sitemap/urls"
            "?include_home=false"
            "&include_archive_months=false"
        )

        archive_only_response = client.get(
            "/api/seo/sitemap/urls"
            "?include_forecasts=false"
        )

    assert response.status_code == 200
    assert _paths(response.get_json()) == ["/horoscope/aries/2026-06-01"]

    assert archive_only_response.status_code == 200
    assert _paths(archive_only_response.get_json()) == ["/", "/archive/aries/2026/06"]


def test_sitemap_urls_endpoint_uses_localhost_default_site_url(client, app, monkeypatch):
    app.config.pop("PUBLIC_SITE_URL", None)
    monkeypatch.delenv("PUBLIC_SITE_URL", raising=False)

    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))

    response = client.get("/api/seo/sitemap/urls?include_home=0")

    assert response.status_code == 200

    data = response.get_json()
    assert data["site_url"] == "http://localhost:5173"
    assert data["items"][0]["loc"] == "http://localhost:5173/horoscope/aries/2026-06-01"


def test_sitemap_urls_endpoint_rejects_bad_query_params(client):
    assert client.get("/api/seo/sitemap/urls?from=bad-date").status_code == 400
    assert client.get("/api/seo/sitemap/urls?to=bad-date").status_code == 400
    assert (
        client.get("/api/seo/sitemap/urls?from=2026-06-02&to=2026-06-01").status_code
        == 400
    )
    assert client.get("/api/seo/sitemap/urls?include_home=maybe").status_code == 400
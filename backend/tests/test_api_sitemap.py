from contextlib import contextmanager
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

from app import db
from app.models import Forecast
from app.services import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE


SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


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


def _xml_root(response):
    return ET.fromstring(response.data.decode("utf-8"))


def _locs(response):
    root = _xml_root(response)
    return [node.text for node in root.findall("sm:url/sm:loc", SITEMAP_NAMESPACE)]


def test_sitemap_xml_endpoint_returns_xml_urlset(client, app):
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
        response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.content_type == "application/xml; charset=utf-8"
    assert response.data.decode("utf-8").startswith(
        '<?xml version="1.0" encoding="UTF-8"?>'
    )

    root = _xml_root(response)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"

    assert _locs(response) == [
        "https://example.com/",
        "https://example.com/horoscope/aries/2026-06-01",
        "https://example.com/horoscope/taurus/2026-06-02",
        "https://example.com/archive/aries/2026/06",
        "https://example.com/archive/taurus/2026/06",
    ]

    lastmods = [
        node.text
        for node in root.findall("sm:url/sm:lastmod", SITEMAP_NAMESPACE)
    ]
    assert "2026-06-01T12:30:00+00:00" in lastmods
    assert "2026-06-02T12:30:00+00:00" in lastmods


def test_sitemap_xml_endpoint_respects_query_params(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 5, 31))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="gemini", target_date=date(2026, 6, 30))
    _create_forecast(sign_key="cancer", target_date=date(2026, 7, 1))

    with _temporary_public_site_url(app, "https://example.com"):
        response = client.get(
            "/sitemap.xml"
            "?from=2026-06-01"
            "&to=2026-06-30"
            "&include_home=0"
            "&include_archive_months=0"
        )

    assert response.status_code == 200
    assert _locs(response) == [
        "https://example.com/horoscope/taurus/2026-06-01",
        "https://example.com/horoscope/gemini/2026-06-30",
    ]


def test_sitemap_xml_endpoint_escapes_xml_values(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))

    with _temporary_public_site_url(app, "https://example.com?x=1&y=2"):
        response = client.get(
                       "/sitemap.xml?include_home=0&include_archive_months=0"
            )

    assert response.status_code == 200

    xml_text = response.data.decode("utf-8")
    assert "https://example.com?x=1&amp;y=2/horoscope/aries/2026-06-01" in xml_text

    assert _locs(response) == [
        "https://example.com?x=1&y=2/horoscope/aries/2026-06-01"
    ]


def test_sitemap_xml_endpoint_rejects_bad_query_params(client):
    assert client.get("/sitemap.xml?from=bad-date").status_code == 400
    assert client.get("/sitemap.xml?to=bad-date").status_code == 400
    assert client.get("/sitemap.xml?include_home=maybe").status_code == 400
    assert client.get("/sitemap.xml?from=2026-06-02&to=2026-06-01").status_code == 400
from contextlib import contextmanager
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

from app import db
from app.models import Forecast
from app.services import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE


SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@contextmanager
def _temporary_config(app, **values):
    original_values = {}
    missing_keys = set()

    for key, value in values.items():
        if key in app.config:
            original_values[key] = app.config[key]
        else:
            missing_keys.add(key)

        app.config[key] = value

    try:
        yield
    finally:
        for key in values:
            if key in missing_keys:
                app.config.pop(key, None)
            else:
                app.config[key] = original_values[key]


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


def _sitemap_index_locs(response):
    root = _xml_root(response)
    return [
        node.text
        for node in root.findall("sm:sitemap/sm:loc", SITEMAP_NAMESPACE)
    ]


def _sitemap_url_locs(response):
    root = _xml_root(response)
    return [
        node.text
        for node in root.findall("sm:url/sm:loc", SITEMAP_NAMESPACE)
    ]


def test_sitemap_index_endpoint_returns_split_sitemap_documents(client, app):
    _create_forecast(
        sign_key="aries",
        target_date=date(2026, 6, 1),
        published_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
    )
    _create_forecast(
        sign_key="taurus",
        target_date=date(2026, 6, 2),
        published_at=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
    )
    _create_forecast(
        sign_key="gemini",
        target_date=date(2026, 6, 3),
        published_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
    )

    with _temporary_config(
        app,
        PUBLIC_SITE_URL="https://example.com",
        SITEMAP_CHUNK_SIZE=2,
    ):
        response = client.get("/sitemap-index.xml")

    assert response.status_code == 200
    assert response.content_type == "application/xml; charset=utf-8"

    root = _xml_root(response)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex"

    assert _sitemap_index_locs(response) == [
        "https://example.com/sitemaps/sitemap-1.xml",
        "https://example.com/sitemaps/sitemap-2.xml",
        "https://example.com/sitemaps/sitemap-3.xml",
        "https://example.com/sitemaps/sitemap-4.xml",
    ]

    lastmods = [
        node.text
        for node in root.findall("sm:sitemap/sm:lastmod", SITEMAP_NAMESPACE)
    ]
    assert lastmods == [
        "2026-06-01T10:00:00+00:00",
        "2026-06-03T10:00:00+00:00",
        "2026-06-02T10:00:00+00:00",
        "2026-06-03T10:00:00+00:00",
    ]


def test_split_sitemap_endpoint_returns_requested_chunk(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 2))
    _create_forecast(sign_key="gemini", target_date=date(2026, 6, 3))

    with _temporary_config(
        app,
        PUBLIC_SITE_URL="https://example.com",
        SITEMAP_CHUNK_SIZE=2,
    ):
        first_response = client.get("/sitemaps/sitemap-1.xml")
        second_response = client.get("/sitemaps/sitemap-2.xml")
        third_response = client.get("/sitemaps/sitemap-3.xml")
        fourth_response = client.get("/sitemaps/sitemap-4.xml")
        missing_response = client.get("/sitemaps/sitemap-5.xml")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 200
    assert fourth_response.status_code == 200
    assert missing_response.status_code == 404

    assert _sitemap_url_locs(first_response) == [
        "https://example.com/",
        "https://example.com/horoscope/aries/2026-06-01",
    ]
    assert _sitemap_url_locs(second_response) == [
        "https://example.com/horoscope/taurus/2026-06-02",
        "https://example.com/horoscope/gemini/2026-06-03",
    ]
    assert _sitemap_url_locs(third_response) == [
        "https://example.com/archive/aries/2026/06",
        "https://example.com/archive/taurus/2026/06",
    ]
    assert _sitemap_url_locs(fourth_response) == [
        "https://example.com/archive/gemini/2026/06",
    ]


def test_sitemap_documents_debug_endpoint_returns_document_metadata(client, app):
    _create_forecast(
        sign_key="aries",
        target_date=date(2026, 6, 1),
        published_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
    )
    _create_forecast(
        sign_key="taurus",
        target_date=date(2026, 6, 2),
        published_at=datetime(2026, 6, 2, 11, 0, tzinfo=timezone.utc),
    )

    with _temporary_config(
        app,
        PUBLIC_SITE_URL="https://example.com",
        SITEMAP_CHUNK_SIZE=2,
    ):
        response = client.get("/api/seo/sitemap/documents")

    assert response.status_code == 200

    data = response.get_json()
    assert data["site_url"] == "https://example.com"
    assert data["chunk_size"] == 2
    assert data["url_count"] == 5
    assert data["document_count"] == 3
    assert data["documents"] == [
        {
            "name": "sitemap-1.xml",
            "loc": "https://example.com/sitemaps/sitemap-1.xml",
            "path": "/sitemaps/sitemap-1.xml",
            "lastmod": "2026-06-01T10:00:00+00:00",
            "url_count": 2,
        },
        {
            "name": "sitemap-2.xml",
            "loc": "https://example.com/sitemaps/sitemap-2.xml",
            "path": "/sitemaps/sitemap-2.xml",
            "lastmod": "2026-06-02T11:00:00+00:00",
            "url_count": 2,
        },
        {
            "name": "sitemap-3.xml",
            "loc": "https://example.com/sitemaps/sitemap-3.xml",
            "path": "/sitemaps/sitemap-3.xml",
            "lastmod": "2026-06-02T11:00:00+00:00",
            "url_count": 1,
        },
    ]


def test_sitemap_index_respects_query_filters(client, app):
    _create_forecast(sign_key="aries", target_date=date(2026, 5, 31))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="gemini", target_date=date(2026, 6, 30))
    _create_forecast(sign_key="cancer", target_date=date(2026, 7, 1))

    with _temporary_config(
        app,
        PUBLIC_SITE_URL="https://example.com",
        SITEMAP_CHUNK_SIZE=2,
    ):
        index_response = client.get(
            "/sitemap-index.xml"
            "?from=2026-06-01"
            "&to=2026-06-30"
            "&include_home=0"
            "&include_archive_months=0"
        )
        first_chunk_response = client.get(
            "/sitemaps/sitemap-1.xml"
            "?from=2026-06-01"
            "&to=2026-06-30"
            "&include_home=0"
            "&include_archive_months=0"
        )

    assert index_response.status_code == 200
    assert first_chunk_response.status_code == 200

    assert _sitemap_index_locs(index_response) == [
        "https://example.com/sitemaps/sitemap-1.xml",
    ]
    assert _sitemap_url_locs(first_chunk_response) == [
        "https://example.com/horoscope/taurus/2026-06-01",
        "https://example.com/horoscope/gemini/2026-06-30",
    ]
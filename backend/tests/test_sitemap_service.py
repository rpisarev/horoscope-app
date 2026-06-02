from datetime import date, datetime, timezone

import pytest

from app import db
from app.models import Forecast, ZodiacSign
from app.services import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from app.services.sitemap_service import build_sitemap_entries, normalize_site_url


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


def _paths(entries):
    return [entry.path for entry in entries]


def _items(entries):
    return [entry.to_dict() for entry in entries]


def test_normalize_site_url_accepts_http_urls_and_removes_trailing_slash():
    assert normalize_site_url("https://example.com/") == "https://example.com"
    assert normalize_site_url("http://localhost:5173/") == "http://localhost:5173"


@pytest.mark.parametrize("site_url", ["", "   ", "example.com", "ftp://example.com"])
def test_normalize_site_url_rejects_bad_values(site_url):
    with pytest.raises(ValueError):
        normalize_site_url(site_url)


def test_build_sitemap_entries_returns_home_forecasts_and_archive_months(app):
    published_at = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)

    _create_forecast(
        sign_key="aries",
        target_date=date(2026, 6, 1),
        published_at=published_at,
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
    _create_forecast(
        sign_key="cancer",
        target_date=date(2026, 6, 4),
        locale="uk",
    )
    _create_forecast(
        sign_key="leo",
        target_date=date(2026, 6, 5),
        forecast_type="weekly",
    )

    entries = build_sitemap_entries(site_url="https://example.com/")

    assert _paths(entries) == [
        "/",
        "/horoscope/aries/2026-06-01",
        "/horoscope/taurus/2026-06-02",
        "/archive/aries/2026/06",
        "/archive/taurus/2026/06",
    ]

    items = _items(entries)
    assert items[0] == {
        "type": "home",
        "loc": "https://example.com/",
        "path": "/",
        "lastmod": None,
    }
    assert items[1] == {
        "type": "forecast",
        "loc": "https://example.com/horoscope/aries/2026-06-01",
        "path": "/horoscope/aries/2026-06-01",
        "lastmod": "2026-06-01T12:30:00+00:00",
        "sign_key": "aries",
        "date": "2026-06-01",
    }
    assert "/archive/aries/2026/06/01" not in _paths(entries)


def test_build_sitemap_entries_filters_by_date_range():
    _create_forecast(sign_key="aries", target_date=date(2026, 5, 31))
    _create_forecast(sign_key="taurus", target_date=date(2026, 6, 1))
    _create_forecast(sign_key="gemini", target_date=date(2026, 6, 30))
    _create_forecast(sign_key="cancer", target_date=date(2026, 7, 1))

    entries = build_sitemap_entries(
        site_url="https://example.com",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    assert _paths(entries) == [
        "/",
        "/horoscope/taurus/2026-06-01",
        "/horoscope/gemini/2026-06-30",
        "/archive/taurus/2026/06",
        "/archive/gemini/2026/06",
    ]


def test_build_sitemap_entries_respects_include_flags():
    _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))

    entries = build_sitemap_entries(
        site_url="https://example.com",
        include_home=False,
        include_archive_months=False,
    )

    assert _paths(entries) == ["/horoscope/aries/2026-06-01"]

    entries = build_sitemap_entries(
        site_url="https://example.com",
        include_forecasts=False,
    )

    assert _paths(entries) == ["/", "/archive/aries/2026/06"]


def test_build_sitemap_entries_ignores_inactive_signs():
    sign = db.session.get(ZodiacSign, "aries")
    assert sign is not None

    original_is_enabled = sign.is_enabled

    try:
        sign.is_enabled = False
        db.session.commit()

        _create_forecast(sign_key="aries", target_date=date(2026, 6, 1))

        entries = build_sitemap_entries(site_url="https://example.com")

        assert _paths(entries) == ["/"]
    finally:
        sign.is_enabled = original_is_enabled
        db.session.commit()


def test_build_sitemap_entries_rejects_invalid_date_range():
    with pytest.raises(ValueError):
        build_sitemap_entries(
            site_url="https://example.com",
            date_from=date(2026, 6, 2),
            date_to=date(2026, 6, 1),
        )
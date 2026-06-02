from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from app.models import Forecast, ZodiacSign


SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
DEFAULT_SITEMAP_CHUNK_SIZE = 50_000


@dataclass(frozen=True)
class SitemapEntry:
    type: str
    loc: str
    path: str
    lastmod: str | None
    sign_key: str | None = None
    date: str | None = None
    year: int | None = None
    month: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "loc": self.loc,
            "path": self.path,
            "lastmod": self.lastmod,
        }

        if self.sign_key is not None:
            data["sign_key"] = self.sign_key
        if self.date is not None:
            data["date"] = self.date
        if self.year is not None:
            data["year"] = self.year
        if self.month is not None:
            data["month"] = self.month

        return data


@dataclass(frozen=True)
class SitemapDocument:
    name: str
    loc: str
    path: str
    lastmod: str | None
    entries: list[SitemapEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "loc": self.loc,
            "path": self.path,
            "lastmod": self.lastmod,
            "url_count": len(self.entries),
        }


def normalize_site_url(site_url: str) -> str:
    normalized = site_url.strip().rstrip("/")

    if not normalized:
        raise ValueError("site_url must not be empty.")

    if not normalized.startswith(("http://", "https://")):
        raise ValueError("site_url must start with http:// or https://.")

    return normalized


def build_sitemap_entries(
    *,
    site_url: str,
    locale: str = "ru",
    forecast_type: str = "daily",
    date_from: date | None = None,
    date_to: date | None = None,
    include_home: bool = True,
    include_forecasts: bool = True,
    include_archive_months: bool = True,
) -> list[SitemapEntry]:
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be less than or equal to date_to.")

    normalized_site_url = normalize_site_url(site_url)
    entries: list[SitemapEntry] = []

    if include_home:
        entries.append(
            SitemapEntry(
                type="home",
                loc=_absolute_url(normalized_site_url, "/"),
                path="/",
                lastmod=None,
            )
        )

    forecasts = _published_forecasts(
        locale=locale,
        forecast_type=forecast_type,
        date_from=date_from,
        date_to=date_to,
    )

    if include_forecasts:
        entries.extend(
            _forecast_entries(
                site_url=normalized_site_url,
                forecasts=forecasts,
            )
        )

    if include_archive_months:
        entries.extend(
            _archive_month_entries(
                site_url=normalized_site_url,
                forecasts=forecasts,
            )
        )

    return entries


def build_sitemap_documents(
    *,
    site_url: str,
    entries: list[SitemapEntry],
    chunk_size: int = DEFAULT_SITEMAP_CHUNK_SIZE,
) -> list[SitemapDocument]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero.")

    normalized_site_url = normalize_site_url(site_url)
    documents: list[SitemapDocument] = []

    for index, start in enumerate(range(0, len(entries), chunk_size), start=1):
        chunk = entries[start : start + chunk_size]
        name = f"sitemap-{index}.xml"
        path = f"/sitemaps/{name}"

        documents.append(
            SitemapDocument(
                name=name,
                loc=_absolute_url(normalized_site_url, path),
                path=path,
                lastmod=_latest_entry_lastmod(chunk),
                entries=chunk,
            )
        )

    return documents


def render_sitemap_xml(entries: list[SitemapEntry]) -> str:
    ET.register_namespace("", SITEMAP_NAMESPACE)

    urlset = ET.Element(f"{{{SITEMAP_NAMESPACE}}}urlset")

    for entry in entries:
        url = ET.SubElement(urlset, f"{{{SITEMAP_NAMESPACE}}}url")

        loc = ET.SubElement(url, f"{{{SITEMAP_NAMESPACE}}}loc")
        loc.text = entry.loc

        if entry.lastmod:
            lastmod = ET.SubElement(url, f"{{{SITEMAP_NAMESPACE}}}lastmod")
            lastmod.text = entry.lastmod

    xml_body = ET.tostring(urlset, encoding="unicode", short_empty_elements=False)

    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}\n'


def render_sitemap_index_xml(documents: list[SitemapDocument]) -> str:
    ET.register_namespace("", SITEMAP_NAMESPACE)

    sitemapindex = ET.Element(f"{{{SITEMAP_NAMESPACE}}}sitemapindex")

    for document in documents:
        sitemap = ET.SubElement(sitemapindex, f"{{{SITEMAP_NAMESPACE}}}sitemap")

        loc = ET.SubElement(sitemap, f"{{{SITEMAP_NAMESPACE}}}loc")
        loc.text = document.loc

        if document.lastmod:
            lastmod = ET.SubElement(sitemap, f"{{{SITEMAP_NAMESPACE}}}lastmod")
            lastmod.text = document.lastmod

    xml_body = ET.tostring(
        sitemapindex,
        encoding="unicode",
        short_empty_elements=False,
    )

    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}\n'


def _published_forecasts(
    *,
    locale: str,
    forecast_type: str,
    date_from: date | None,
    date_to: date | None,
) -> list[Forecast]:
    query = (
        Forecast.query.join(ZodiacSign, Forecast.sign_key == ZodiacSign.key)
        .filter(
            Forecast.locale == locale,
            Forecast.forecast_type == forecast_type,
            Forecast.status == "published",
            ZodiacSign.is_enabled.is_(True),
        )
        .order_by(
            Forecast.target_date.asc(),
            ZodiacSign.sort_order.asc(),
            Forecast.sign_key.asc(),
        )
    )

    if date_from is not None:
        query = query.filter(Forecast.target_date >= date_from)

    if date_to is not None:
        query = query.filter(Forecast.target_date <= date_to)

    return query.all()


def _forecast_entries(
    *,
    site_url: str,
    forecasts: list[Forecast],
) -> list[SitemapEntry]:
    entries: list[SitemapEntry] = []

    for forecast in forecasts:
        target_date = forecast.target_date.isoformat()
        path = f"/horoscope/{forecast.sign_key}/{target_date}"

        entries.append(
            SitemapEntry(
                type="forecast",
                loc=_absolute_url(site_url, path),
                path=path,
                lastmod=_forecast_lastmod(forecast),
                sign_key=forecast.sign_key,
                date=target_date,
            )
        )

    return entries


def _archive_month_entries(
    *,
    site_url: str,
    forecasts: list[Forecast],
) -> list[SitemapEntry]:
    archive_months: dict[tuple[str, int, int], datetime | None] = {}
    sign_sort_order: dict[str, int] = {}

    for forecast in forecasts:
        if forecast.zodiac_sign:
            sign_sort_order[forecast.sign_key] = forecast.zodiac_sign.sort_order

        key = (
            forecast.sign_key,
            forecast.target_date.year,
            forecast.target_date.month,
        )
        current_lastmod = archive_months.get(key)
        forecast_lastmod = _forecast_lastmod_datetime(forecast)

        archive_months[key] = _max_datetime(current_lastmod, forecast_lastmod)

    entries: list[SitemapEntry] = []

    for sign_key, year, month in sorted(
        archive_months.keys(),
        key=lambda item: (
            item[1],
            item[2],
            sign_sort_order.get(item[0], 10_000),
            item[0],
        ),
    ):
        month_path_part = f"{month:02d}"
        path = f"/archive/{sign_key}/{year}/{month_path_part}"

        entries.append(
            SitemapEntry(
                type="archive_month",
                loc=_absolute_url(site_url, path),
                path=path,
                lastmod=_datetime_to_iso(archive_months[(sign_key, year, month)]),
                sign_key=sign_key,
                year=year,
                month=month,
            )
        )

    return entries


def _absolute_url(site_url: str, path: str) -> str:
    if path == "/":
        return f"{site_url}/"

    return f"{site_url}{path}"


def _forecast_lastmod(forecast: Forecast) -> str | None:
    return _datetime_to_iso(_forecast_lastmod_datetime(forecast))


def _forecast_lastmod_datetime(forecast: Forecast) -> datetime | None:
    for value in (
        forecast.published_at,
        forecast.updated_at,
        forecast.generated_at,
        forecast.created_at,
    ):
        normalized = _normalize_datetime(value)
        if normalized is not None:
            return normalized

    return None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _max_datetime(
    current_value: datetime | None,
    next_value: datetime | None,
) -> datetime | None:
    if current_value is None:
        return next_value

    if next_value is None:
        return current_value

    return max(current_value, next_value)


def _latest_entry_lastmod(entries: list[SitemapEntry]) -> str | None:
    values = [
        datetime.fromisoformat(entry.lastmod)
        for entry in entries
        if entry.lastmod is not None
    ]

    if not values:
        return None

    return max(values).isoformat()
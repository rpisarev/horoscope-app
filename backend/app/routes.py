import os
from calendar import monthrange
from datetime import date, timedelta

from flask import Blueprint, Response, abort, current_app, jsonify, request
from sqlalchemy import distinct, extract, func

from . import db
from .models import Forecast, ZodiacSign
from .services import (
    DEFAULT_FORECAST_TYPE,
    DEFAULT_LOCALE,
    SIGNS,
    generate_horoscope,
    get_forecast,
    save_forecast,
)
from .services.sitemap_service import (
    DEFAULT_SITEMAP_CHUNK_SIZE,
    build_sitemap_documents,
    build_sitemap_entries,
    render_sitemap_index_xml,
    render_sitemap_xml,
)

bp = Blueprint("api", __name__)
site_bp = Blueprint("site", __name__)


def _localized_sign_name(sign: ZodiacSign, locale: str) -> str:
    if locale == "uk" and sign.name_uk:
        return sign.name_uk
    if locale == "en" and sign.name_en:
        return sign.name_en

    return sign.name_ru


def _parse_int_arg(name: str, *, min_value: int, max_value: int) -> int:
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        abort(400, f"Missing required query parameter '{name}'")

    try:
        value = int(raw_value)
    except ValueError:
        abort(400, f"Bad {name} format, expected integer")

    if value < min_value or value > max_value:
        abort(400, f"Bad {name} value, expected {min_value}..{max_value}")

    return value


def _parse_date_arg(name: str) -> date:
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        abort(400, f"Missing required query parameter '{name}'")

    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        abort(400, f"Bad {name} format, expected YYYY-MM-DD")


def _parse_optional_date_arg(name: str) -> date | None:
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return None

    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        abort(400, f"Bad {name} format, expected YYYY-MM-DD")


def _parse_bool_arg(name: str, *, default: bool) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    abort(400, f"Bad {name} format, expected boolean")


def _public_site_url() -> str:
    return (
        current_app.config.get("PUBLIC_SITE_URL")
        or os.getenv("PUBLIC_SITE_URL")
        or "http://localhost:5173"
    )


def _sitemap_chunk_size() -> int:
    raw_value = (
        current_app.config.get("SITEMAP_CHUNK_SIZE")
        or os.getenv("SITEMAP_CHUNK_SIZE")
        or DEFAULT_SITEMAP_CHUNK_SIZE
    )

    try:
        chunk_size = int(raw_value)
    except (TypeError, ValueError):
        abort(500, "Bad SITEMAP_CHUNK_SIZE config value")

    if chunk_size < 1 or chunk_size > DEFAULT_SITEMAP_CHUNK_SIZE:
        abort(500, f"Bad SITEMAP_CHUNK_SIZE config value, expected 1..{DEFAULT_SITEMAP_CHUNK_SIZE}")

    return chunk_size


def _build_sitemap_entries_from_request():
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)
    date_from = _parse_optional_date_arg("from")
    date_to = _parse_optional_date_arg("to")

    if date_from and date_to and date_from > date_to:
        abort(400, "Bad date range, 'from' must be less than or equal to 'to'")

    include_home = _parse_bool_arg("include_home", default=True)
    include_forecasts = _parse_bool_arg("include_forecasts", default=True)
    include_archive_months = _parse_bool_arg("include_archive_months", default=True)

    entries = build_sitemap_entries(
        site_url=_public_site_url(),
        locale=locale,
        forecast_type=forecast_type,
        date_from=date_from,
        date_to=date_to,
        include_home=include_home,
        include_forecasts=include_forecasts,
        include_archive_months=include_archive_months,
    )

    return {
        "site_url": _public_site_url().strip().rstrip("/"),
        "locale": locale,
        "forecast_type": forecast_type,
        "from": date_from,
        "to": date_to,
        "include_home": include_home,
        "include_forecasts": include_forecasts,
        "include_archive_months": include_archive_months,
        "entries": entries,
    }


def _build_sitemap_documents_from_request():
    sitemap_data = _build_sitemap_entries_from_request()
    documents = build_sitemap_documents(
        site_url=_public_site_url(),
        entries=sitemap_data["entries"],
        chunk_size=_sitemap_chunk_size(),
    )

    return {
        **sitemap_data,
        "documents": documents,
    }


def _active_sign_count() -> int:
    return ZodiacSign.query.filter_by(is_enabled=True).count()


def _month_bounds(year: int, month: int) -> tuple[date, date, int]:
    days_in_month = monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = start_date + timedelta(days=days_in_month)

    return start_date, end_date, days_in_month


def _published_archive_counts(
    *,
    start_date: date,
    end_date: date,
    locale: str,
    forecast_type: str,
) -> dict[date, int]:
    rows = (
        db.session.query(
            Forecast.target_date.label("target_date"),
            func.count(distinct(Forecast.sign_key)).label("forecast_count"),
        )
        .join(ZodiacSign, Forecast.sign_key == ZodiacSign.key)
        .filter(
            Forecast.target_date >= start_date,
            Forecast.target_date < end_date,
            Forecast.locale == locale,
            Forecast.forecast_type == forecast_type,
            Forecast.status == "published",
            ZodiacSign.is_enabled.is_(True),
        )
        .group_by(Forecast.target_date)
        .all()
    )

    return {row.target_date: int(row.forecast_count) for row in rows}


def _archive_day_summary(
    *,
    target_date: date,
    forecast_count: int,
    expected_sign_count: int,
) -> dict:
    missing_count = max(expected_sign_count - forecast_count, 0)

    return {
        "date": target_date.isoformat(),
        "forecast_count": forecast_count,
        "has_full_coverage": expected_sign_count > 0
        and forecast_count >= expected_sign_count,
        "missing_count": missing_count,
    }


@site_bp.route("/sitemap.xml")
def sitemap_xml():
    sitemap_data = _build_sitemap_entries_from_request()
    xml = render_sitemap_xml(sitemap_data["entries"])

    return Response(xml, content_type="application/xml; charset=utf-8")


@site_bp.route("/sitemap-index.xml")
def sitemap_index_xml():
    sitemap_data = _build_sitemap_documents_from_request()
    xml = render_sitemap_index_xml(sitemap_data["documents"])

    return Response(xml, content_type="application/xml; charset=utf-8")


@site_bp.route("/sitemaps/<filename>")
def split_sitemap_xml(filename: str):
    sitemap_data = _build_sitemap_documents_from_request()

    for document in sitemap_data["documents"]:
        if document.name == filename:
            xml = render_sitemap_xml(document.entries)
            return Response(xml, content_type="application/xml; charset=utf-8")

    abort(404, f"Unknown sitemap file '{filename}'")


@bp.route("/forecast")
def forecast():
    sign = request.args.get("sign")
    day_str = request.args.get("date")
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)

    if sign not in SIGNS:
        abort(400, f"Unknown sign '{sign}'")

    if day_str:
        try:
            target_day = date.fromisoformat(day_str)
        except ValueError:
            abort(400, "Bad date format, expected YYYY-MM-DD")
    else:
        target_day = date.today()

    fc = get_forecast(
        sign=sign,
        day=target_day,
        locale=locale,
        forecast_type=forecast_type,
    )

    if not fc:
        text = generate_horoscope(sign, target_day)
        fc = save_forecast(
            sign=sign,
            day=target_day,
            text=text,
            model_version="stub",
            locale=locale,
            forecast_type=forecast_type,
            status="published",
            source="stub",
        )

    return jsonify(fc.to_dict())


@bp.route("/signs")
def signs():
    # Keep the current frontend-compatible response shape for now.
    return jsonify(SIGNS)


@bp.route("/signs/meta")
def signs_meta():
    locale = request.args.get("locale", DEFAULT_LOCALE)

    rows = (
        ZodiacSign.query.filter_by(is_enabled=True)
        .order_by(ZodiacSign.sort_order.asc())
        .all()
    )

    return jsonify(
        {
            "locale": locale,
            "items": [
                {
                    "key": sign.key,
                    "name": _localized_sign_name(sign, locale),
                    "sort_order": sign.sort_order,
                    "is_active": bool(sign.is_enabled),
                }
                for sign in rows
            ],
        }
    )


@bp.route("/archive/day")
def archive_day():
    target_day = _parse_date_arg("date")
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)
    expected_sign_count = _active_sign_count()

    forecasts = (
        Forecast.query.join(ZodiacSign, Forecast.sign_key == ZodiacSign.key)
        .filter(
            Forecast.target_date == target_day,
            Forecast.locale == locale,
            Forecast.forecast_type == forecast_type,
            Forecast.status == "published",
            ZodiacSign.is_enabled.is_(True),
        )
        .order_by(ZodiacSign.sort_order.asc())
        .all()
    )

    summary = _archive_day_summary(
        target_date=target_day,
        forecast_count=len(forecasts),
        expected_sign_count=expected_sign_count,
    )

    return jsonify(
        {
            "date": target_day.isoformat(),
            "locale": locale,
            "forecast_type": forecast_type,
            "expected_sign_count": expected_sign_count,
            **summary,
            "forecasts": [forecast.to_dict() for forecast in forecasts],
        }
    )


@bp.route("/archive/month")
def archive_month():
    year = _parse_int_arg("year", min_value=1, max_value=9999)
    month = _parse_int_arg("month", min_value=1, max_value=12)
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)
    expected_sign_count = _active_sign_count()

    start_date, end_date, days_in_month = _month_bounds(year, month)
    counts_by_date = _published_archive_counts(
        start_date=start_date,
        end_date=end_date,
        locale=locale,
        forecast_type=forecast_type,
    )

    days = [
        _archive_day_summary(
            target_date=start_date + timedelta(days=offset),
            forecast_count=counts_by_date.get(start_date + timedelta(days=offset), 0),
            expected_sign_count=expected_sign_count,
        )
        for offset in range(days_in_month)
    ]

    return jsonify(
        {
            "year": year,
            "month": month,
            "locale": locale,
            "forecast_type": forecast_type,
            "expected_sign_count": expected_sign_count,
            "days": days,
        }
    )


@bp.route("/archive/months")
def archive_months():
    year = _parse_int_arg("year", min_value=1, max_value=9999)
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)
    expected_sign_count = _active_sign_count()

    start_date = date(year, 1, 1)
    end_date = date(year + 1, 1, 1) if year < 9999 else date(9999, 12, 31)
    if year == 9999:
        end_date = end_date + timedelta(days=1)

    counts_by_date = _published_archive_counts(
        start_date=start_date,
        end_date=end_date,
        locale=locale,
        forecast_type=forecast_type,
    )

    months = []
    for month in range(1, 13):
        month_start, _, days_in_month = _month_bounds(year, month)
        month_dates = [month_start + timedelta(days=offset) for offset in range(days_in_month)]
        month_counts = [counts_by_date.get(day, 0) for day in month_dates]
        forecast_count = sum(month_counts)
        covered_day_count = sum(1 for count in month_counts if count > 0)
        full_coverage_day_count = sum(
            1
            for count in month_counts
            if expected_sign_count > 0 and count >= expected_sign_count
        )

        months.append(
            {
                "year": year,
                "month": month,
                "days_in_month": days_in_month,
                "forecast_count": forecast_count,
                "covered_day_count": covered_day_count,
                "full_coverage_day_count": full_coverage_day_count,
                "has_forecasts": forecast_count > 0,
                "has_full_month_coverage": full_coverage_day_count == days_in_month,
            }
        )

    return jsonify(
        {
            "year": year,
            "locale": locale,
            "forecast_type": forecast_type,
            "expected_sign_count": expected_sign_count,
            "months": months,
        }
    )


@bp.route("/seo/sitemap/urls")
def sitemap_urls():
    sitemap_data = _build_sitemap_entries_from_request()

    return jsonify(
        {
            "site_url": sitemap_data["site_url"],
            "locale": sitemap_data["locale"],
            "forecast_type": sitemap_data["forecast_type"],
            "from": sitemap_data["from"].isoformat() if sitemap_data["from"] else None,
            "to": sitemap_data["to"].isoformat() if sitemap_data["to"] else None,
            "include_home": sitemap_data["include_home"],
            "include_forecasts": sitemap_data["include_forecasts"],
            "include_archive_months": sitemap_data["include_archive_months"],
            "items": [entry.to_dict() for entry in sitemap_data["entries"]],
        }
    )


@bp.route("/seo/sitemap/documents")
def sitemap_documents():
    sitemap_data = _build_sitemap_documents_from_request()

    return jsonify(
        {
            "site_url": sitemap_data["site_url"],
            "locale": sitemap_data["locale"],
            "forecast_type": sitemap_data["forecast_type"],
            "chunk_size": _sitemap_chunk_size(),
            "url_count": len(sitemap_data["entries"]),
            "document_count": len(sitemap_data["documents"]),
            "documents": [document.to_dict() for document in sitemap_data["documents"]],
        }
    )


@bp.route("/years")
def years():
    sign = request.args.get("sign")
    locale = request.args.get("locale", DEFAULT_LOCALE)
    forecast_type = request.args.get("type", DEFAULT_FORECAST_TYPE)

    query = db.session.query(
        extract("year", Forecast.target_date).label("year")
    ).filter(
        Forecast.locale == locale,
        Forecast.forecast_type == forecast_type,
        Forecast.status == "published",
    )

    if sign:
        if sign not in SIGNS:
            abort(400, f"Unknown sign '{sign}'")
        query = query.filter(Forecast.sign_key == sign)

    rows = query.distinct().order_by("year").all()
    forecast_years = sorted({int(row.year) for row in rows if row.year is not None})

    if not forecast_years:
        start_year = 2024
        current_year = date.today().year
        forecast_years = list(range(start_year, current_year + 1))

    return jsonify(forecast_years)
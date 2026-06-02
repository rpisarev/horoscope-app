from datetime import date

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import extract

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


bp = Blueprint("api", __name__)


def _localized_sign_name(sign: ZodiacSign, locale: str) -> str:
    if locale == "uk" and sign.name_uk:
        return sign.name_uk
    if locale == "en" and sign.name_en:
        return sign.name_en

    return sign.name_ru


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
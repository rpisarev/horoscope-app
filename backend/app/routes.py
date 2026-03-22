from flask import Blueprint, request, abort, jsonify
from datetime import datetime, date
from .models import Forecast
from .services import SIGNS, generate_horoscope, save_forecast

bp = Blueprint("api", __name__, url_prefix='/api')

@bp.route("/forecast")
def forecast():
    sign = request.args.get("sign")
    day_str = request.args.get("date")

    if sign not in SIGNS:
        abort(400, f"Unknown sign '{{sign}}'")

    day = None
    if day_str:
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            abort(400, "Bad date format, expected YYYY-MM-DD")
    else:
        day = date.today()

    fc = Forecast.query.filter_by(sign=sign, day=day).first()
    if not fc:
        text = generate_horoscope(sign, day)
        save_forecast(sign, day, text)
        fc = Forecast.query.filter_by(sign=sign, day=day).first()

    return jsonify(fc.to_dict())

@bp.route("/signs")
def signs():
    from .services import SIGNS
    return jsonify(SIGNS)

@bp.route('/years')
def years():
    start_year = 2024
    current_year = datetime.utcnow().year
    forecasts_years = list(range(start_year, current_year + 1))
    return jsonify(forecasts_years)

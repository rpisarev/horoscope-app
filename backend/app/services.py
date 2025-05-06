from datetime import date
from .models import Forecast
from . import db

SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces", "ophiuchus"
]

def generate_horoscope(sign: str, day: date) -> str:
    """Placeholder generator. Replace with real LLM call."""
    return f"Для {sign.capitalize()} цей день ({day.isoformat()}) обіцяє успіх і нові можливості."

def save_forecast(sign: str, day: date, text: str, model_version: str = "stub"):
    fc = Forecast.query.filter_by(sign=sign, day=day).first()
    if fc:
        fc.text = text
        fc.model_version = model_version
    else:
        fc = Forecast(sign=sign, day=day, text=text, model_version=model_version)
        db.session.add(fc)
    db.session.commit()

from __future__ import annotations

from datetime import date, datetime, timezone

from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE
from .prompt_service import get_prompt_version
from .. import db
from ..models import Forecast
from ..providers import ProviderRequest, get_horoscope_provider


def get_forecast(
    sign: str,
    day: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> Forecast | None:
    return Forecast.query.filter_by(
        sign_key=sign,
        target_date=day,
        locale=locale,
        forecast_type=forecast_type,
    ).first()


def get_published_forecast(
    sign: str,
    day: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> Forecast | None:
    return Forecast.query.filter_by(
        sign_key=sign,
        target_date=day,
        locale=locale,
        forecast_type=forecast_type,
        status="published",
    ).first()


def generate_horoscope(sign: str, day: date) -> str:
    """
    Backward-compatible generator used by the current API fallback.

    The sign argument is intentionally ignored here. Sign keys are important
    for DB routing and frontend display, but the generated text itself is
    sign-agnostic by product design.
    """
    prompt_version = get_prompt_version()
    provider = get_horoscope_provider("stub")
    result = provider.generate(
        ProviderRequest(
            target_date=day,
            locale=DEFAULT_LOCALE,
            forecast_type=DEFAULT_FORECAST_TYPE,
            prompt_version=prompt_version,
        )
    )
    return result.text


def save_forecast(
    sign: str,
    day: date,
    text: str,
    model_version: str = "stub",
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
    title: str | None = None,
    payload: dict | None = None,
    status: str = "published",
    source: str = "stub",
    prompt_version_key: str | None = None,
    generation_item_id: int | None = None,
    commit: bool = True,
) -> Forecast:
    now = datetime.now(timezone.utc)
    prompt_version = get_prompt_version(
        prompt_version_key,
        locale=locale,
        forecast_type=forecast_type,
    )
    fc = get_forecast(
        sign=sign,
        day=day,
        locale=locale,
        forecast_type=forecast_type,
    )

    if fc:
        fc.title = title
        fc.text = text
        fc.payload = payload
        fc.status = status
        fc.source = source
        fc.model_name = model_version
        fc.prompt_version = prompt_version
        fc.generation_item_id = generation_item_id
        fc.generated_at = now
        if status == "published" and fc.published_at is None:
            fc.published_at = now
    else:
        fc = Forecast(
            sign_key=sign,
            target_date=day,
            locale=locale,
            forecast_type=forecast_type,
            title=title,
            text=text,
            payload=payload,
            status=status,
            source=source,
            model_name=model_version,
            prompt_version=prompt_version,
            generation_item_id=generation_item_id,
            generated_at=now,
            published_at=now if status == "published" else None,
        )
        db.session.add(fc)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return fc
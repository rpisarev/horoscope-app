from datetime import date, datetime, timezone

from . import db
from .models import Forecast, PromptVersion


DEFAULT_LOCALE = "ru"
DEFAULT_FORECAST_TYPE = "daily"
DEFAULT_PROMPT_VERSION_KEY = "daily-ru-v1"


ZODIAC_SIGNS = [
    {
        "key": "aries",
        "name_ru": "Овен",
        "name_uk": "Овен",
        "name_en": "Aries",
        "glyph": "♈",
        "start": "04-19",
        "end": "05-14",
        "sort_order": 1,
    },
    {
        "key": "taurus",
        "name_ru": "Телец",
        "name_uk": "Телець",
        "name_en": "Taurus",
        "glyph": "♉",
        "start": "05-15",
        "end": "06-21",
        "sort_order": 2,
    },
    {
        "key": "gemini",
        "name_ru": "Близнецы",
        "name_uk": "Близнюки",
        "name_en": "Gemini",
        "glyph": "♊",
        "start": "06-22",
        "end": "07-20",
        "sort_order": 3,
    },
    {
        "key": "cancer",
        "name_ru": "Рак",
        "name_uk": "Рак",
        "name_en": "Cancer",
        "glyph": "♋",
        "start": "07-21",
        "end": "08-10",
        "sort_order": 4,
    },
    {
        "key": "leo",
        "name_ru": "Лев",
        "name_uk": "Лев",
        "name_en": "Leo",
        "glyph": "♌",
        "start": "08-11",
        "end": "09-16",
        "sort_order": 5,
    },
    {
        "key": "virgo",
        "name_ru": "Дева",
        "name_uk": "Діва",
        "name_en": "Virgo",
        "glyph": "♍",
        "start": "09-17",
        "end": "10-31",
        "sort_order": 6,
    },
    {
        "key": "libra",
        "name_ru": "Весы",
        "name_uk": "Терези",
        "name_en": "Libra",
        "glyph": "♎",
        "start": "11-01",
        "end": "11-23",
        "sort_order": 7,
    },
    {
        "key": "scorpio",
        "name_ru": "Скорпион",
        "name_uk": "Скорпіон",
        "name_en": "Scorpio",
        "glyph": "♏",
        "start": "11-24",
        "end": "11-30",
        "sort_order": 8,
    },
    {
        "key": "sagittarius",
        "name_ru": "Стрелец",
        "name_uk": "Стрілець",
        "name_en": "Sagittarius",
        "glyph": "♐",
        "start": "12-19",
        "end": "01-19",
        "sort_order": 9,
    },
    {
        "key": "capricorn",
        "name_ru": "Козерог",
        "name_uk": "Козеріг",
        "name_en": "Capricorn",
        "glyph": "♑",
        "start": "01-20",
        "end": "02-16",
        "sort_order": 10,
    },
    {
        "key": "aquarius",
        "name_ru": "Водолей",
        "name_uk": "Водолій",
        "name_en": "Aquarius",
        "glyph": "♒",
        "start": "02-17",
        "end": "03-11",
        "sort_order": 11,
    },
    {
        "key": "pisces",
        "name_ru": "Рыбы",
        "name_uk": "Риби",
        "name_en": "Pisces",
        "glyph": "♓",
        "start": "03-12",
        "end": "04-18",
        "sort_order": 12,
    },
    {
        "key": "ophiuchus",
        "name_ru": "Змееносец",
        "name_uk": "Змієносець",
        "name_en": "Ophiuchus",
        "glyph": "⛎",
        "start": "12-01",
        "end": "12-18",
        "sort_order": 13,
    },
]


SIGNS = [sign["key"] for sign in ZODIAC_SIGNS]


def generate_horoscope(sign: str, day: date) -> str:
    """Placeholder generator. Replace with a real LLM call later."""
    return (
        f"Для {sign.capitalize()} этот день ({day.isoformat()}) "
        "обещает новые возможности, спокойные решения и полезные совпадения."
    )


def get_prompt_version(prompt_version_key: str | None = None) -> PromptVersion | None:
    key = prompt_version_key or DEFAULT_PROMPT_VERSION_KEY

    prompt_version = PromptVersion.query.filter_by(key=key).first()
    if prompt_version:
        return prompt_version

    return PromptVersion.query.filter_by(
        locale=DEFAULT_LOCALE,
        forecast_type=DEFAULT_FORECAST_TYPE,
        is_active=True,
    ).first()


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
) -> Forecast:
    now = datetime.now(timezone.utc)
    prompt_version = get_prompt_version(prompt_version_key)

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

    db.session.commit()
    return fc
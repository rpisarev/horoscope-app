"""add variation prompt

Revision ID: 0004_variation_prompt
Revises: 0003_prompt_pipeline
Create Date: 2026-05-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0004_variation_prompt"
down_revision = "0003_prompt_pipeline"
branch_labels = None
depends_on = None


VARIATION_SYSTEM_PROMPT = """
Ты пишешь короткие ежедневные персональные прогнозы для сайта гороскопов.

Цель:
дать живой, личный и пригодный для публикации текст на день, а не набор универсальных советов.

Всегда соблюдай:
- Пиши на русском языке.
- Обращайся к читателю на Вы / Вам / Ваш.
- Не называй знак зодиака, дату, астрологические термины и представителей знака.
- Не обещай судьбоносный исход, гарантированную удачу, деньги или любовь.
- Один прогноз должен держаться на одном главном нерве дня, а не на наборе тем.
- Показывай 1–2 конкретных проявления дня, но не превращай текст в список.
- Совет должен быть встроен в наблюдение, а не звучать как команда.
- Избегай канцелярита, офисного productivity tone, эзотерической перегруженности и одинаковых концовок.
- Если тема не про работу, не своди текст к задачам, документам, фактам, дедлайнам и завершению дел.
- Если в запросе есть avoid, не используй эти мотивы ни как основную тему, ни как образ, ни как финальный ход, ни как заголовок.
- Не начинай шаблонно с «Сегодня…».
- Не завершай прогноз словами и конструкциями: «к вечеру», «к концу дня», «к исходу дня», «вечером», «перед сном», «ранним сном», «лечь пораньше», «останется ощущение», «появится ощущение», «станет легче дышать».
- Финальное предложение должно завершать мысль дня, а не подводить итог времени суток.
- Не злоупотребляй словами: ощущение, мягче, тише, дышать, пространство, бережный, собранность.
- В одном прогнозе используй не больше одного абстрактного слова из этого ряда, если можно заменить его конкретной сценой.
- Не формулируй прогноз как прямую инструкцию. Избегай частых повелительных конструкций вроде «сделайте», «возьмите», «посмотрите», «постарайтесь». Лучше писать через возможность дня: «может помочь», «будет уместно», «хорошо сработает», «Вам подойдёт».

В каждом запросе будет указан профиль запуска:
theme, mood, tone, composition, opening_move, concrete_zone, ending_energy, sentence_style, avoid.

Следуй именно профилю запуска.
Не выбирай самый безопасный общий сюжет, если задана конкретная тема.

Формат ответа:
верни только JSON по заданной схеме:
- title: короткий небанальный заголовок или null
- text: готовый текст прогноза из 4–5 предложений
""".strip()


VARIATION_USER_PROMPT_TEMPLATE = """
Сгенерируй один ежедневный персональный прогноз.

Профиль этого запуска:
- theme: {prompt_variation_theme}
- mood: {prompt_variation_mood}
- tone: {prompt_variation_tone}
- composition: {prompt_variation_composition}
- opening_move: {prompt_variation_opening_move}
- concrete_zone: {prompt_variation_concrete_zone}
- ending_energy: {prompt_variation_ending_energy}
- sentence_style: {prompt_variation_sentence_style}
- avoid: {prompt_variation_avoid}

Требования:
- Пиши на {output_language}.
- Используй {address_style}.
- Длина текста: {sentence_count} предложений.
- Следуй профилю запуска, но не повторяй его формулировки дословно.
- Держи один основной фокус от начала до конца.
- Прояви тему через concrete_zone.
- Соблюдай sentence_style.
- Не перечисляй темы подряд.
- Не делай текст похожим на инструкцию, чеклист или список советов.
- Не привязывай текст к конкретному знаку зодиака или конкретной дате.
- Не используй мотивы и слова из avoid.
- Сделай ритм и синтаксис живыми, без шаблонного начала.
- Если тема не про работу, не возвращайся к сюжетам про документы, факты, точность, дедлайны, завершение старого и отложенные дела.
- Финальное предложение должно быть конкретным и тематическим, а не итогом про вечер, сон или общее ощущение.
""".strip()


VARIATION_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "text": {"type": "string"},
    },
}


SIGN_AGNOSTIC_SYSTEM_PROMPT = (
    "Ты пишешь короткие ежедневные персональные прогнозы в спокойном, "
    "доброжелательном стиле.\n"
    "Текст должен обращаться к читателю напрямую "
    "и уважительно. Не называй конкретные знаки зодиака и не используй "
    "формулировки про представителей знака.\n"
    "Не упоминай дату и не объясняй, "
    "что текст универсальный."
)

SIGN_AGNOSTIC_USER_PROMPT_TEMPLATE = (
    "Напиши короткий ежедневный прогноз для читателя.\n"
    "Требования:\n"
    "- язык: {output_language};\n"
    "- объем: {sentence_count} предложений;\n"
    "- обращение: {address_style};\n"
    "- без markdown, списков и нумерации;\n"
    "- не называй знак зодиака;\n"
    "- не используй фразы: представители знака, люди этого знака, "
    "для вашего знака;\n"
    "- не упоминай дату;\n"
    "- текст должен звучать как личный прогноз, обращенный напрямую к человеку.\n"
    "Верни только JSON согласно схеме."
)

SIGN_AGNOSTIC_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "text": {"type": "string"},
    },
}


def _json_type():
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())

    return sa.JSON()


def upgrade() -> None:
    _update_daily_ru_v1_prompt(
        system_prompt=VARIATION_SYSTEM_PROMPT,
        user_prompt_template=VARIATION_USER_PROMPT_TEMPLATE,
        output_schema=VARIATION_OUTPUT_SCHEMA,
        model_name="gpt-5.4-mini",
    )


def downgrade() -> None:
    _update_daily_ru_v1_prompt(
        system_prompt=SIGN_AGNOSTIC_SYSTEM_PROMPT,
        user_prompt_template=SIGN_AGNOSTIC_USER_PROMPT_TEMPLATE,
        output_schema=SIGN_AGNOSTIC_OUTPUT_SCHEMA,
        model_name=None,
    )


def _update_daily_ru_v1_prompt(
    *,
    system_prompt: str,
    user_prompt_template: str,
    output_schema: dict,
    model_name: str | None,
) -> None:
    statement = sa.text(
        """
        UPDATE prompt_versions
        SET system_prompt = :system_prompt,
            user_prompt_template = :user_prompt_template,
            output_schema = :output_schema,
            model_name = :model_name,
            updated_at = CURRENT_TIMESTAMP
        WHERE key = 'daily-ru-v1'
        """
    ).bindparams(
        sa.bindparam("system_prompt", value=system_prompt, type_=sa.Text()),
        sa.bindparam("user_prompt_template", value=user_prompt_template, type_=sa.Text()),
        sa.bindparam("output_schema", value=output_schema, type_=_json_type()),
        sa.bindparam("model_name", value=model_name, type_=sa.String()),
    )

    op.execute(statement)
"""refine sign-agnostic prompt pipeline

Revision ID: 0003_prompt_pipeline
Revises: 0002_add_generation_attempts
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_prompt_pipeline"
down_revision = "0002_add_generation_attempts"
branch_labels = None
depends_on = None


SIGN_AGNOSTIC_SYSTEM_PROMPT = (
    "Ты пишешь короткие ежедневные персональные прогнозы в спокойном, "
    "доброжелательном стиле. Текст должен обращаться к читателю напрямую "
    "и уважительно. Не называй конкретные знаки зодиака и не используй "
    "формулировки про представителей знака. Не упоминай дату и не объясняй, "
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

PREVIOUS_SYSTEM_PROMPT = (
    "Ты пишешь короткие ежедневные прогнозы в спокойном, позитивном стиле. "
    "Не упоминай знаки зодиака. "
    "Обращайся к читателю только напрямую: Вы, Вам, Вас."
)

PREVIOUS_USER_PROMPT_TEMPLATE = (
    "Составь короткий ежедневный прогноз на дату {date}. "
    "Текст должен быть универсальным и не зависеть от знака зодиака. "
    "Не называй и не подразумевай конкретный знак. "
    "Используй обращения Вы, Вам, Вас."
)

PREVIOUS_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "properties": {
        "title": {"type": "string"},
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
        system_prompt=SIGN_AGNOSTIC_SYSTEM_PROMPT,
        user_prompt_template=SIGN_AGNOSTIC_USER_PROMPT_TEMPLATE,
        output_schema=SIGN_AGNOSTIC_OUTPUT_SCHEMA,
    )


def downgrade() -> None:
    _update_daily_ru_v1_prompt(
        system_prompt=PREVIOUS_SYSTEM_PROMPT,
        user_prompt_template=PREVIOUS_USER_PROMPT_TEMPLATE,
        output_schema=PREVIOUS_OUTPUT_SCHEMA,
    )


def _update_daily_ru_v1_prompt(
    *,
    system_prompt: str,
    user_prompt_template: str,
    output_schema: dict,
) -> None:
    statement = sa.text(
        """
        UPDATE prompt_versions
        SET
            system_prompt = :system_prompt,
            user_prompt_template = :user_prompt_template,
            output_schema = :output_schema,
            updated_at = CURRENT_TIMESTAMP
        WHERE key = 'daily-ru-v1'
        """
    ).bindparams(
        sa.bindparam("system_prompt", value=system_prompt, type_=sa.Text()),
        sa.bindparam("user_prompt_template", value=user_prompt_template, type_=sa.Text()),
        sa.bindparam("output_schema", value=output_schema, type_=_json_type()),
    )

    op.execute(statement)
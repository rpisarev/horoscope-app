"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zodiac_signs",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name_ru", sa.String(length=64), nullable=False),
        sa.Column("name_uk", sa.String(length=64), nullable=True),
        sa.Column("name_en", sa.String(length=64), nullable=True),
        sa.Column("glyph", sa.String(length=8), nullable=True),
        sa.Column("start_month", sa.SmallInteger(), nullable=True),
        sa.Column("start_day", sa.SmallInteger(), nullable=True),
        sa.Column("end_month", sa.SmallInteger(), nullable=True),
        sa.Column("end_day", sa.SmallInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("sort_order", name="uq_zodiac_signs_sort_order"),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("forecast_type", sa.String(length=32), nullable=False, server_default="daily"),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt_template", sa.Text(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_prompt_versions_key"),
    )

    op.create_table(
        "forecasts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sign_key", sa.String(length=32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("forecast_type", sa.String(length=32), nullable=False, server_default="daily"),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="stub"),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_version_id", sa.BigInteger(), nullable=True),
        sa.Column("generation_item_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], name="fk_forecasts_prompt_version_id_prompt_versions"),
        sa.ForeignKeyConstraint(["sign_key"], ["zodiac_signs.key"], name="fk_forecasts_sign_key_zodiac_signs"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sign_key", "target_date", "locale", "forecast_type", name="uq_forecasts_sign_date_locale_type"),
    )

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("forecast_type", sa.String(length=32), nullable=False, server_default="daily"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "generation_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("sign_key", sa.String(length=32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("forecast_type", sa.String(length=32), nullable=False, server_default="daily"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("forecast_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_version_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["forecast_id"], ["forecasts.id"], name="fk_generation_items_forecast_id_forecasts"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], name="fk_generation_items_prompt_version_id_prompt_versions"),
        sa.ForeignKeyConstraint(["run_id"], ["generation_runs.id"], name="fk_generation_items_run_id_generation_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sign_key"], ["zodiac_signs.key"], name="fk_generation_items_sign_key_zodiac_signs"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "fk_forecasts_generation_item_id_generation_items",
        "forecasts",
        "generation_items",
        ["generation_item_id"],
        ["id"],
    )

    op.create_index("ix_forecasts_sign_key", "forecasts", ["sign_key"])
    op.create_index("ix_forecasts_target_date", "forecasts", ["target_date"])
    op.create_index("ix_forecasts_status", "forecasts", ["status"])
    op.create_index("ix_generation_runs_status", "generation_runs", ["status"])
    op.create_index("ix_generation_runs_target_date", "generation_runs", ["target_date"])
    op.create_index("ix_generation_items_run_id", "generation_items", ["run_id"])
    op.create_index("ix_generation_items_status", "generation_items", ["status"])
    op.create_index("ix_generation_items_sign_date", "generation_items", ["sign_key", "target_date"])

    zodiac_signs_table = sa.table(
        "zodiac_signs",
        sa.column("key", sa.String),
        sa.column("name_ru", sa.String),
        sa.column("name_uk", sa.String),
        sa.column("name_en", sa.String),
        sa.column("glyph", sa.String),
        sa.column("start_month", sa.SmallInteger),
        sa.column("start_day", sa.SmallInteger),
        sa.column("end_month", sa.SmallInteger),
        sa.column("end_day", sa.SmallInteger),
        sa.column("sort_order", sa.SmallInteger),
        sa.column("is_enabled", sa.Boolean),
    )

    op.bulk_insert(
        zodiac_signs_table,
        [
            {"key": "aries", "name_ru": "Овен", "name_uk": "Овен", "name_en": "Aries", "glyph": "♈", "start_month": 4, "start_day": 19, "end_month": 5, "end_day": 14, "sort_order": 1, "is_enabled": True},
            {"key": "taurus", "name_ru": "Телец", "name_uk": "Телець", "name_en": "Taurus", "glyph": "♉", "start_month": 5, "start_day": 15, "end_month": 6, "end_day": 21, "sort_order": 2, "is_enabled": True},
            {"key": "gemini", "name_ru": "Близнецы", "name_uk": "Близнюки", "name_en": "Gemini", "glyph": "♊", "start_month": 6, "start_day": 22, "end_month": 7, "end_day": 20, "sort_order": 3, "is_enabled": True},
            {"key": "cancer", "name_ru": "Рак", "name_uk": "Рак", "name_en": "Cancer", "glyph": "♋", "start_month": 7, "start_day": 21, "end_month": 8, "end_day": 10, "sort_order": 4, "is_enabled": True},
            {"key": "leo", "name_ru": "Лев", "name_uk": "Лев", "name_en": "Leo", "glyph": "♌", "start_month": 8, "start_day": 11, "end_month": 9, "end_day": 16, "sort_order": 5, "is_enabled": True},
            {"key": "virgo", "name_ru": "Дева", "name_uk": "Діва", "name_en": "Virgo", "glyph": "♍", "start_month": 9, "start_day": 17, "end_month": 10, "end_day": 31, "sort_order": 6, "is_enabled": True},
            {"key": "libra", "name_ru": "Весы", "name_uk": "Терези", "name_en": "Libra", "glyph": "♎", "start_month": 11, "start_day": 1, "end_month": 11, "end_day": 23, "sort_order": 7, "is_enabled": True},
            {"key": "scorpio", "name_ru": "Скорпион", "name_uk": "Скорпіон", "name_en": "Scorpio", "glyph": "♏", "start_month": 11, "start_day": 24, "end_month": 11, "end_day": 30, "sort_order": 8, "is_enabled": True},
            {"key": "sagittarius", "name_ru": "Стрелец", "name_uk": "Стрілець", "name_en": "Sagittarius", "glyph": "♐", "start_month": 12, "start_day": 19, "end_month": 1, "end_day": 19, "sort_order": 9, "is_enabled": True},
            {"key": "capricorn", "name_ru": "Козерог", "name_uk": "Козеріг", "name_en": "Capricorn", "glyph": "♑", "start_month": 1, "start_day": 20, "end_month": 2, "end_day": 16, "sort_order": 10, "is_enabled": True},
            {"key": "aquarius", "name_ru": "Водолей", "name_uk": "Водолій", "name_en": "Aquarius", "glyph": "♒", "start_month": 2, "start_day": 17, "end_month": 3, "end_day": 11, "sort_order": 11, "is_enabled": True},
            {"key": "pisces", "name_ru": "Рыбы", "name_uk": "Риби", "name_en": "Pisces", "glyph": "♓", "start_month": 3, "start_day": 12, "end_month": 4, "end_day": 18, "sort_order": 12, "is_enabled": True},
            {"key": "ophiuchus", "name_ru": "Змееносец", "name_uk": "Змієносець", "name_en": "Ophiuchus", "glyph": "⛎", "start_month": 12, "start_day": 1, "end_month": 12, "end_day": 18, "sort_order": 13, "is_enabled": True},
        ],
    )

    prompt_versions_table = sa.table(
        "prompt_versions",
        sa.column("key", sa.String),
        sa.column("locale", sa.String),
        sa.column("forecast_type", sa.String),
        sa.column("system_prompt", sa.Text),
        sa.column("user_prompt_template", sa.Text),
        sa.column("output_schema", postgresql.JSONB),
        sa.column("model_name", sa.String),
        sa.column("is_active", sa.Boolean),
    )

    op.bulk_insert(
        prompt_versions_table,
        [
            {
                "key": "daily-ru-v1",
                "locale": "ru",
                "forecast_type": "daily",
                "system_prompt": "Ты пишешь короткие ежедневные гороскопы в спокойном, позитивном стиле.",
                "user_prompt_template": "Составь ежедневный гороскоп для знака {sign} на дату {date}.",
                "output_schema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                    },
                },
                "model_name": "stub",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_constraint("fk_forecasts_generation_item_id_generation_items", "forecasts", type_="foreignkey")

    op.drop_index("ix_generation_items_sign_date", table_name="generation_items")
    op.drop_index("ix_generation_items_status", table_name="generation_items")
    op.drop_index("ix_generation_items_run_id", table_name="generation_items")
    op.drop_index("ix_generation_runs_target_date", table_name="generation_runs")
    op.drop_index("ix_generation_runs_status", table_name="generation_runs")
    op.drop_index("ix_forecasts_status", table_name="forecasts")
    op.drop_index("ix_forecasts_target_date", table_name="forecasts")
    op.drop_index("ix_forecasts_sign_key", table_name="forecasts")

    op.drop_table("generation_items")
    op.drop_table("generation_runs")
    op.drop_table("forecasts")
    op.drop_table("prompt_versions")
    op.drop_table("zodiac_signs")
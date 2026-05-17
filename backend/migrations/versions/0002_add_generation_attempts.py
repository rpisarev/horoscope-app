"""add generation attempts

Revision ID: 0002_add_generation_attempts
Revises: 0001_initial_schema
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_add_generation_attempts"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


SIGN_AGNOSTIC_SYSTEM_PROMPT = (
    "Ты пишешь короткие ежедневные прогнозы в спокойном, позитивном стиле. "
    "Не упоминай знаки зодиака. "
    "Обращайся к читателю только напрямую: Вы, Вам, Вас."
)

SIGN_AGNOSTIC_USER_PROMPT_TEMPLATE = (
    "Составь короткий ежедневный прогноз на дату {date}. "
    "Текст должен быть универсальным и не зависеть от знака зодиака. "
    "Не называй и не подразумевай конкретный знак. "
    "Используй обращения Вы, Вам, Вас."
)


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_type()

    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("request_payload", json_type, nullable=True),
        sa.Column("response_payload", json_type, nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["generation_items.id"],
            name="fk_generation_attempts_item_id_generation_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id",
            "attempt_no",
            name="uq_generation_attempts_item_attempt_no",
        ),
    )
    op.create_index("ix_generation_attempts_item_id", "generation_attempts", ["item_id"])
    op.create_index("ix_generation_attempts_status", "generation_attempts", ["status"])
    op.create_index(
        "ix_generation_attempts_item_status",
        "generation_attempts",
        ["item_id", "status"],
    )

    op.execute(
        sa.text(
            """
            UPDATE prompt_versions
            SET
                system_prompt = :system_prompt,
                user_prompt_template = :user_prompt_template,
                updated_at = now()
            WHERE key = 'daily-ru-v1'
            """
        ).bindparams(
            system_prompt=SIGN_AGNOSTIC_SYSTEM_PROMPT,
            user_prompt_template=SIGN_AGNOSTIC_USER_PROMPT_TEMPLATE,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE prompt_versions
            SET
                system_prompt = 'Ты пишешь короткие ежедневные гороскопы в спокойном, позитивном стиле.',
                user_prompt_template = 'Составь ежедневный гороскоп для знака {sign} на дату {date}.',
                updated_at = now()
            WHERE key = 'daily-ru-v1'
            """
        )
    )

    op.drop_index("ix_generation_attempts_item_status", table_name="generation_attempts")
    op.drop_index("ix_generation_attempts_status", table_name="generation_attempts")
    op.drop_index("ix_generation_attempts_item_id", table_name="generation_attempts")
    op.drop_table("generation_attempts")
"""add generation jobs queue

Revision ID: 0005_generation_jobs
Revises: 0004_variation_prompt
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0005_generation_jobs"
down_revision = "0004_variation_prompt"
branch_labels = None
depends_on = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "locale",
            sa.String(length=8),
            server_default="ru",
            nullable=False,
        ),
        sa.Column(
            "forecast_type",
            sa.String(length=32),
            server_default="daily",
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=64),
            server_default="stub",
            nullable=False,
        ),
        sa.Column("signs", _json_type(), nullable=True),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "max_retry_runs",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "max_job_attempts",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("batch_id", sa.String(length=128), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column(
            "openai_allowed_at_creation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["generation_runs.id"],
            name="fk_generation_jobs_run_id_generation_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_generation_jobs_job_type",
        "generation_jobs",
        ["job_type"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_status",
        "generation_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_target_date",
        "generation_jobs",
        ["target_date"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_run_id",
        "generation_jobs",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_batch_id",
        "generation_jobs",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_locked_at",
        "generation_jobs",
        ["locked_at"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_status_priority_created",
        "generation_jobs",
        ["status", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_scope",
        "generation_jobs",
        ["target_date", "locale", "forecast_type", "provider"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_batch_status",
        "generation_jobs",
        ["batch_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_generation_jobs_active_dedupe_key",
        "generation_jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_active_dedupe_key", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_batch_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_scope", table_name="generation_jobs")
    op.drop_index(
        "ix_generation_jobs_status_priority_created",
        table_name="generation_jobs",
    )
    op.drop_index("ix_generation_jobs_locked_at", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_batch_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_run_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_target_date", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_job_type", table_name="generation_jobs")
    op.drop_table("generation_jobs")
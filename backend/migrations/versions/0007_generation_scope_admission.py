"""Enforce one running generation run per package; preserve historical rows.

Revision ID: 0007_generation_scope_admission
Revises: 0006_generation_ledger
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_generation_scope_admission"
down_revision = "0006_generation_ledger"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_generation_runs_active_package"


def _postgresql_connection():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Generation scope admission requires PostgreSQL.")
    return connection


def _bound_timeouts(connection):
    previous = connection.execute(sa.text(
        "SELECT name, setting::bigint, current_setting(name) FROM pg_settings "
        "WHERE name IN ('lock_timeout', 'statement_timeout')"
    )).all()
    limits = {"lock_timeout": 5000, "statement_timeout": 15000}
    for name, current_ms, _ in previous:
        timeout_ms = min(current_ms, limits[name]) if current_ms else limits[name]
        connection.execute(sa.text("SELECT set_config(:name, :value, true)"),
                           {"name": name, "value": f"{timeout_ms}ms"})
    return previous


def _restore_timeouts(connection, previous):
    for name, _, value in previous:
        connection.execute(sa.text("SELECT set_config(:name, :value, true)"),
                           {"name": name, "value": value})


def upgrade():
    connection = _postgresql_connection()
    previous = _bound_timeouts(connection)
    # DDL is transactional. Exclude writers between the historical conflict
    # check and index creation; no concurrent-index partial states are produced.
    connection.execute(sa.text("LOCK TABLE generation_runs IN SHARE ROW EXCLUSIVE MODE"))
    conflicts = connection.execute(sa.text("""
        SELECT count(*) AS active_count
        FROM generation_runs
        WHERE status = 'running'
        GROUP BY target_date, locale, forecast_type
        HAVING count(*) > 1
        LIMIT 5
    """)).all()
    if conflicts:
        # Do not guess a winner, expose row contents, rewrite statuses or delete
        # history. Rollback is the Alembic transaction owner's responsibility.
        raise RuntimeError(
            "Generation scope admission migration blocked: conflicting running "
            f"package scopes exist (sampled groups: {len(conflicts)}, maximum 5). "
            "Authorized historical inspection/reconciliation is required; "
            "no generation history has been changed."
        )
    op.create_index(
        INDEX_NAME, "generation_runs", ["target_date", "locale", "forecast_type"],
        unique=True, postgresql_where=sa.text("status = 'running'"),
    )
    _restore_timeouts(connection, previous)


def downgrade():
    connection = _postgresql_connection()
    previous = _bound_timeouts(connection)
    op.drop_index(INDEX_NAME, table_name="generation_runs")
    _restore_timeouts(connection, previous)

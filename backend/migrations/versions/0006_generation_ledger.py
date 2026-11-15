"""Add immutable execution and paid-request ledger storage (no writers).

Revision ID: 0006_generation_ledger
Revises: 0005_generation_jobs
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_generation_ledger"
down_revision = "0005_generation_jobs"
branch_labels = None
depends_on = None


LEDGER_TABLES = (
    "generation_executions",
    "generation_execution_runs",
    "generation_api_requests",
    "generation_api_observations",
)


REJECT_MUTATION_SQL = """
CREATE FUNCTION generation_ledger_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'generation ledger rows are append-only'
        USING ERRCODE = '55000';
END;
$$
"""


# Snapshot-time checks only. FOR SHARE blocks other transactions from changing
# referenced legacy rows until this INSERT transaction ends; the same transaction
# can still change them. This is not ongoing fencing of their future writers.
# TG_TABLE_SCHEMA prevents caller search_path from redirecting these lookups.
VALIDATE_INSERT_SQL = """
CREATE FUNCTION generation_ledger_validate_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    execution_row record;
    job_row record;
    run_row record;
    link_row record;
    item_row record;
    attempt_row record;
    request_row record;
BEGIN
    IF TG_TABLE_NAME = 'generation_executions' THEN
        IF NEW.job_id IS NOT NULL THEN
            EXECUTE format('SELECT id, provider, target_date, locale, forecast_type '
                           'FROM %I.generation_jobs WHERE id = $1 FOR SHARE',
                           TG_TABLE_SCHEMA) INTO job_row USING NEW.job_id;
            IF job_row.id IS NULL THEN
                RAISE EXCEPTION 'ledger job does not exist' USING ERRCODE = '23503';
            END IF;
            IF ROW(NEW.provider, NEW.target_date, NEW.locale, NEW.forecast_type)
                IS DISTINCT FROM
                ROW(job_row.provider, job_row.target_date, job_row.locale, job_row.forecast_type)
            THEN
                RAISE EXCEPTION 'ledger job snapshot mismatch' USING ERRCODE = '23514';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME IN ('generation_execution_runs', 'generation_api_requests') THEN
        EXECUTE format('SELECT id, origin, target_date, locale, forecast_type, started_at '
                       'FROM %I.generation_executions WHERE id = $1 FOR SHARE',
                       TG_TABLE_SCHEMA) INTO execution_row USING NEW.execution_id;
        IF execution_row.id IS NULL THEN
            RAISE EXCEPTION 'ledger execution does not exist' USING ERRCODE = '23503';
        END IF;
        IF TG_TABLE_NAME = 'generation_execution_runs' THEN
            EXECUTE format('SELECT id, target_date, locale, forecast_type '
                           'FROM %I.generation_runs WHERE id = $1 FOR SHARE',
                           TG_TABLE_SCHEMA) INTO run_row USING NEW.run_id;
            IF run_row.id IS NULL THEN
                RAISE EXCEPTION 'ledger run does not exist' USING ERRCODE = '23503';
            END IF;
            IF execution_row.origin = 'dev_diagnostic'
                OR NEW.linked_at < execution_row.started_at
                OR ROW(run_row.target_date, run_row.locale, run_row.forecast_type)
                    IS DISTINCT FROM
                    ROW(execution_row.target_date, execution_row.locale, execution_row.forecast_type)
            THEN
                RAISE EXCEPTION 'ledger run link mismatch' USING ERRCODE = '23514';
            END IF;
        ELSE
            IF NEW.admitted_at < execution_row.started_at THEN
                RAISE EXCEPTION 'ledger admission precedes execution' USING ERRCODE = '23514';
            END IF;
            IF execution_row.origin = 'dev_diagnostic' THEN
                IF NEW.run_id IS NOT NULL OR NEW.item_id IS NOT NULL
                    OR NEW.legacy_attempt_id IS NOT NULL THEN
                    RAISE EXCEPTION 'diagnostic request cannot have product links'
                        USING ERRCODE = '23514';
                END IF;
            ELSE
                IF NEW.run_id IS NULL OR NEW.item_id IS NULL THEN
                    RAISE EXCEPTION 'product request requires run and item'
                        USING ERRCODE = '23514';
                END IF;
                EXECUTE format('SELECT execution_id, linked_at FROM %I.generation_execution_runs '
                               'WHERE execution_id = $1 AND run_id = $2 FOR SHARE',
                               TG_TABLE_SCHEMA) INTO link_row USING NEW.execution_id, NEW.run_id;
                IF link_row.execution_id IS NULL THEN
                    RAISE EXCEPTION 'ledger execution/run link does not exist'
                        USING ERRCODE = '23503';
                END IF;
                EXECUTE format('SELECT id, run_id, target_date, locale, forecast_type '
                               'FROM %I.generation_items WHERE id = $1 FOR SHARE',
                               TG_TABLE_SCHEMA) INTO item_row USING NEW.item_id;
                IF item_row.id IS NULL THEN
                    RAISE EXCEPTION 'ledger item does not exist' USING ERRCODE = '23503';
                END IF;
                IF NEW.admitted_at < link_row.linked_at
                    OR item_row.run_id IS DISTINCT FROM NEW.run_id
                    OR ROW(item_row.target_date, item_row.locale, item_row.forecast_type)
                        IS DISTINCT FROM
                        ROW(execution_row.target_date, execution_row.locale, execution_row.forecast_type)
                THEN
                    RAISE EXCEPTION 'ledger request/item snapshot mismatch'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.legacy_attempt_id IS NOT NULL THEN
                    EXECUTE format('SELECT id, item_id FROM %I.generation_attempts WHERE id = $1 FOR SHARE',
                                   TG_TABLE_SCHEMA) INTO attempt_row USING NEW.legacy_attempt_id;
                    IF attempt_row.id IS NULL THEN
                        RAISE EXCEPTION 'ledger legacy attempt does not exist'
                            USING ERRCODE = '23503';
                    END IF;
                    IF attempt_row.item_id IS DISTINCT FROM NEW.item_id THEN
                        RAISE EXCEPTION 'ledger legacy attempt/item mismatch'
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'generation_api_observations' THEN
        EXECUTE format('SELECT id, admitted_at FROM %I.generation_api_requests WHERE id = $1 FOR SHARE',
                       TG_TABLE_SCHEMA) INTO request_row USING NEW.request_id;
        IF request_row.id IS NULL THEN
            RAISE EXCEPTION 'ledger request does not exist' USING ERRCODE = '23503';
        END IF;
        IF NEW.recorded_at < request_row.admitted_at THEN
            RAISE EXCEPTION 'ledger observation precedes admission' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""


def _require_postgresql():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Generation ledger requires PostgreSQL enforcement")


def upgrade():
    _require_postgresql()
    _create_tables()
    op.execute(REJECT_MUTATION_SQL)
    op.execute(VALIDATE_INSERT_SQL)
    for table in LEDGER_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION generation_ledger_reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_insert BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION generation_ledger_validate_insert()"
        )


def downgrade():
    _require_postgresql()
    # Hold all four tables against concurrent INSERT before testing emptiness.
    # The exception precedes all DROP statements, including in offline SQL.
    op.execute("LOCK TABLE " + ", ".join(LEDGER_TABLES) + " IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM generation_executions)
                OR EXISTS (SELECT 1 FROM generation_execution_runs)
                OR EXISTS (SELECT 1 FROM generation_api_requests)
                OR EXISTS (SELECT 1 FROM generation_api_observations)
            THEN
                RAISE EXCEPTION 'refusing downgrade of nonempty generation ledger'
                    USING ERRCODE = '55000';
            END IF;
        END $$
    """)
    for table in reversed(LEDGER_TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION generation_ledger_validate_insert()")
    op.execute("DROP FUNCTION generation_ledger_reject_mutation()")


def _create_tables():
    op.create_table(
        'generation_executions',
        sa.Column('id', sa.Uuid, primary_key=True),
        sa.Column('job_id', sa.BigInteger, sa.ForeignKey('generation_jobs.id', name='fk_gen_exec_job', ondelete='RESTRICT')),
        sa.Column('origin', sa.String(32), nullable=False),
        sa.Column('deployment_mode', sa.String(16), nullable=False),
        sa.Column('provider', sa.String(64), nullable=False),
        sa.Column('target_date', sa.Date),
        sa.Column('locale', sa.String(8)),
        sa.Column('forecast_type', sa.String(32)),
        sa.Column('policy_version', sa.String(128), nullable=False),
        sa.Column('lease_epoch', sa.BigInteger),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("origin IN ('queue_worker', 'dev_direct', 'dev_diagnostic')", name='ck_gen_exec_origin'),
        sa.CheckConstraint("deployment_mode IN ('production', 'development', 'test')", name='ck_gen_exec_mode'),
        sa.CheckConstraint("(origin = 'queue_worker' AND job_id IS NOT NULL) OR (origin <> 'queue_worker' AND job_id IS NULL)", name='ck_gen_exec_job_origin'),
        sa.CheckConstraint("deployment_mode <> 'production' OR (origin = 'queue_worker' AND lease_epoch IS NOT NULL)", name='ck_gen_exec_production'),
        sa.CheckConstraint('lease_epoch > 0', name='ck_gen_exec_epoch'),
        sa.CheckConstraint("provider ~ '^[a-z][a-z0-9_]*$'", name='ck_gen_exec_provider'),
        sa.CheckConstraint('length(btrim(policy_version)) > 0', name='ck_gen_exec_policy'),
        sa.CheckConstraint("(origin = 'dev_diagnostic' AND target_date IS NULL AND locale IS NULL AND forecast_type IS NULL) OR (origin <> 'dev_diagnostic' AND target_date IS NOT NULL AND locale IS NOT NULL AND forecast_type IS NOT NULL)", name='ck_gen_exec_scope'),
        sa.CheckConstraint('length(btrim(locale)) > 0 AND length(btrim(forecast_type)) > 0', name='ck_gen_exec_scope_text'),
    )
    op.create_index('ix_gen_exec_job_started', 'generation_executions', ['job_id', 'started_at'], unique=False)
    op.create_index('ix_gen_exec_scope_started', 'generation_executions', ['target_date', 'locale', 'forecast_type', 'started_at'], unique=False)

    op.create_table(
        'generation_execution_runs',
        sa.Column('execution_id', sa.Uuid, sa.ForeignKey('generation_executions.id', name='fk_gen_exec_run_execution', ondelete='RESTRICT'), primary_key=True),
        sa.Column('run_id', sa.BigInteger, sa.ForeignKey('generation_runs.id', name='fk_gen_exec_run_run', ondelete='RESTRICT'), nullable=False),
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('execution_id', 'run_id', name='uq_gen_exec_run_pair'),
    )
    op.create_index('ix_gen_exec_run_run', 'generation_execution_runs', ['run_id'], unique=False)

    op.create_table(
        'generation_api_requests',
        sa.Column('id', sa.Uuid, primary_key=True),
        sa.Column('execution_id', sa.Uuid, sa.ForeignKey('generation_executions.id', name='fk_gen_request_execution', ondelete='RESTRICT'), nullable=False),
        sa.Column('request_no', sa.Integer, nullable=False),
        sa.Column('run_id', sa.BigInteger),
        sa.Column('item_id', sa.BigInteger, sa.ForeignKey('generation_items.id', name='fk_gen_request_item', ondelete='RESTRICT')),
        sa.Column('legacy_attempt_id', sa.BigInteger, sa.ForeignKey('generation_attempts.id', name='fk_gen_request_legacy_attempt', ondelete='RESTRICT')),
        sa.Column('admission_scope', sa.String(128), nullable=False),
        sa.Column('policy_version', sa.String(128), nullable=False),
        sa.Column('admitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('admission_day', sa.Date, sa.Computed("(admitted_at AT TIME ZONE 'UTC')::date", persisted=True), nullable=False),
        sa.ForeignKeyConstraint(['execution_id', 'run_id'], ['generation_execution_runs.execution_id', 'generation_execution_runs.run_id'], name='fk_gen_request_execution_run', ondelete='RESTRICT'),
        sa.UniqueConstraint('execution_id', 'request_no', name='uq_gen_request_execution_no'),
        sa.CheckConstraint('request_no > 0', name='ck_gen_request_no'),
        sa.CheckConstraint('length(btrim(admission_scope)) > 0', name='ck_gen_request_scope'),
        sa.CheckConstraint('length(btrim(policy_version)) > 0', name='ck_gen_request_policy'),
        sa.CheckConstraint('(run_id IS NULL AND item_id IS NULL AND legacy_attempt_id IS NULL) OR (run_id IS NOT NULL AND item_id IS NOT NULL)', name='ck_gen_request_links'),
    )
    op.create_index('ix_gen_request_scope_day', 'generation_api_requests', ['admission_scope', 'admission_day', 'admitted_at'], unique=False)
    op.create_index('ix_gen_request_item', 'generation_api_requests', ['item_id'], unique=False)
    op.create_index('ix_gen_request_legacy_attempt', 'generation_api_requests', ['legacy_attempt_id'], unique=False)

    op.create_table(
        'generation_api_observations',
        sa.Column('id', sa.Uuid, primary_key=True),
        sa.Column('request_id', sa.Uuid, sa.ForeignKey('generation_api_requests.id', name='fk_gen_observation_request', ondelete='RESTRICT'), nullable=False),
        sa.Column('observation_no', sa.Integer, nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('outcome', sa.String(16), nullable=False),
        sa.Column('review_state', sa.String(32), nullable=False),
        sa.Column('evidence_code', sa.String(128)),
        sa.Column('provider_request_id', sa.String(255)),
        sa.Column('input_tokens', sa.BigInteger),
        sa.Column('output_tokens', sa.BigInteger),
        sa.Column('usage_source', sa.String(128)),
        sa.Column('model_name', sa.String(128)),
        sa.UniqueConstraint('request_id', 'observation_no', name='uq_gen_observation_request_no'),
        sa.CheckConstraint('observation_no > 0', name='ck_gen_observation_no'),
        sa.CheckConstraint("outcome IN ('unknown', 'succeeded', 'failed', 'not_sent')", name='ck_gen_observation_outcome'),
        sa.CheckConstraint("review_state IN ('requires_review', 'recorded')", name='ck_gen_observation_review'),
        sa.CheckConstraint("outcome <> 'unknown' OR review_state = 'requires_review'", name='ck_gen_observation_unknown'),
        sa.CheckConstraint("outcome <> 'not_sent' OR evidence_code IS NOT NULL", name='ck_gen_observation_not_sent'),
        sa.CheckConstraint('length(btrim(evidence_code)) > 0 AND length(btrim(usage_source)) > 0 AND length(btrim(model_name)) > 0 AND length(btrim(provider_request_id)) > 0', name='ck_gen_observation_text'),
        sa.CheckConstraint('input_tokens >= 0 AND output_tokens >= 0', name='ck_gen_observation_tokens'),
        sa.CheckConstraint("outcome <> 'not_sent' OR ((input_tokens IS NULL OR input_tokens = 0) AND (output_tokens IS NULL OR output_tokens = 0))", name='ck_gen_observation_not_sent_usage'),
        sa.CheckConstraint('(input_tokens IS NULL AND output_tokens IS NULL) OR (usage_source IS NOT NULL AND model_name IS NOT NULL)', name='ck_gen_observation_usage_source'),
    )

from sqlalchemy import Computed, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB

from . import db
from .business_date import business_today


json_type = JSONB().with_variant(db.JSON(), "sqlite")


def _iso(value):
    if value is None:
        return None
    return value.isoformat()


class TimestampMixin:
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ZodiacSign(TimestampMixin, db.Model):
    __tablename__ = "zodiac_signs"

    key = db.Column(db.String(32), primary_key=True)
    name_ru = db.Column(db.String(64), nullable=False)
    name_uk = db.Column(db.String(64), nullable=True)
    name_en = db.Column(db.String(64), nullable=True)
    glyph = db.Column(db.String(8), nullable=True)
    start_month = db.Column(db.SmallInteger, nullable=True)
    start_day = db.Column(db.SmallInteger, nullable=True)
    end_month = db.Column(db.SmallInteger, nullable=True)
    end_day = db.Column(db.SmallInteger, nullable=True)
    sort_order = db.Column(db.SmallInteger, nullable=False, unique=True)
    is_enabled = db.Column(db.Boolean, nullable=False, server_default=db.text("true"))

    forecasts = db.relationship("Forecast", back_populates="zodiac_sign")

    def to_dict(self):
        return {
            "key": self.key,
            "nameRu": self.name_ru,
            "nameUk": self.name_uk,
            "nameEn": self.name_en,
            "glyph": self.glyph,
            "start": (
                f"{self.start_month:02d}-{self.start_day:02d}"
                if self.start_month and self.start_day
                else None
            ),
            "end": (
                f"{self.end_month:02d}-{self.end_day:02d}"
                if self.end_month and self.end_day
                else None
            ),
            "sortOrder": self.sort_order,
            "enabled": self.is_enabled,
        }


class PromptVersion(TimestampMixin, db.Model):
    __tablename__ = "prompt_versions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    key = db.Column(db.String(64), nullable=False, unique=True)
    locale = db.Column(db.String(8), nullable=False, server_default="ru")
    forecast_type = db.Column(db.String(32), nullable=False, server_default="daily")
    system_prompt = db.Column(db.Text, nullable=False)
    user_prompt_template = db.Column(db.Text, nullable=False)
    output_schema = db.Column(json_type, nullable=True)
    model_name = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.text("false"))

    forecasts = db.relationship(
        "Forecast",
        back_populates="prompt_version",
        foreign_keys="Forecast.prompt_version_id",
    )


class Forecast(TimestampMixin, db.Model):
    __tablename__ = "forecasts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    sign_key = db.Column(
        db.String(32),
        db.ForeignKey("zodiac_signs.key", name="fk_forecasts_sign_key_zodiac_signs"),
        nullable=False,
        index=True,
    )
    target_date = db.Column(db.Date, nullable=False, default=business_today, index=True)
    locale = db.Column(db.String(8), nullable=False, server_default="ru")
    forecast_type = db.Column(db.String(32), nullable=False, server_default="daily")
    title = db.Column(db.String(255), nullable=True)
    text = db.Column(db.Text, nullable=False)
    payload = db.Column(json_type, nullable=True)
    status = db.Column(db.String(32), nullable=False, server_default="draft", index=True)
    source = db.Column(db.String(32), nullable=False, server_default="stub")
    model_name = db.Column(db.String(128), nullable=True)
    prompt_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "prompt_versions.id",
            name="fk_forecasts_prompt_version_id_prompt_versions",
        ),
        nullable=True,
    )
    generation_item_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "generation_items.id",
            name="fk_forecasts_generation_item_id_generation_items",
        ),
        nullable=True,
    )
    generated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    zodiac_sign = db.relationship("ZodiacSign", back_populates="forecasts")
    prompt_version = db.relationship(
        "PromptVersion",
        back_populates="forecasts",
        foreign_keys=[prompt_version_id],
    )
    generation_item = db.relationship(
        "GenerationItem",
        foreign_keys=[generation_item_id],
        post_update=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sign_key",
            "target_date",
            "locale",
            "forecast_type",
            name="uq_forecasts_sign_date_locale_type",
        ),
    )

    def to_dict(self):
        target_date = self.target_date.isoformat()

        return {
            "id": self.id,
            "sign": self.sign_key,
            "sign_key": self.sign_key,
            "day": target_date,
            "date": target_date,
            "locale": self.locale,
            "forecast_type": self.forecast_type,
            "title": self.title,
            "text": self.text,
            "forecast": self.text,
            "payload": self.payload,
            "status": self.status,
            "source": self.source,
            "model_version": self.model_name,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version.key if self.prompt_version else None,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "generated_at": _iso(self.generated_at),
            "published_at": _iso(self.published_at),
        }


class GenerationRun(db.Model):
    __tablename__ = "generation_runs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    run_type = db.Column(db.String(32), nullable=False)
    target_date = db.Column(db.Date, nullable=False, index=True)
    locale = db.Column(db.String(8), nullable=False, server_default="ru")
    forecast_type = db.Column(db.String(32), nullable=False, server_default="daily")
    status = db.Column(db.String(32), nullable=False, server_default="running", index=True)
    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    total_items = db.Column(db.Integer, nullable=False, server_default="0")
    success_items = db.Column(db.Integer, nullable=False, server_default="0")
    failed_items = db.Column(db.Integer, nullable=False, server_default="0")
    skipped_items = db.Column(db.Integer, nullable=False, server_default="0")
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    items = db.relationship(
        "GenerationItem",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    jobs = db.relationship(
        "GenerationJob",
        back_populates="run",
        foreign_keys="GenerationJob.run_id",
    )

    __table_args__ = (
        db.Index(
            "uq_generation_runs_active_package", "target_date", "locale", "forecast_type",
            unique=True, postgresql_where=db.text("status = 'running'"),
        ),
    )


class GenerationJob(db.Model):
    __tablename__ = "generation_jobs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(32), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, server_default="queued", index=True)
    target_date = db.Column(db.Date, nullable=False, index=True)
    locale = db.Column(db.String(8), nullable=False, server_default="ru")
    forecast_type = db.Column(db.String(32), nullable=False, server_default="daily")
    provider = db.Column(db.String(64), nullable=False, server_default="stub")
    signs = db.Column(json_type, nullable=True)
    max_attempts = db.Column(db.Integer, nullable=False, server_default="3")
    max_retry_runs = db.Column(db.Integer, nullable=False, server_default="3")
    max_job_attempts = db.Column(db.Integer, nullable=False, server_default="1")
    attempt_count = db.Column(db.Integer, nullable=False, server_default="0")
    priority = db.Column(db.Integer, nullable=False, server_default="0")
    run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "generation_runs.id",
            name="fk_generation_jobs_run_id_generation_runs",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    batch_id = db.Column(db.String(128), nullable=True, index=True)
    dedupe_key = db.Column(db.String(128), nullable=False)
    openai_allowed_at_creation = db.Column(
        db.Boolean,
        nullable=False,
        server_default=db.text("false"),
    )
    created_by = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    locked_by = db.Column(db.String(128), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    run = db.relationship(
        "GenerationRun",
        back_populates="jobs",
        foreign_keys=[run_id],
    )

    __table_args__ = (
        db.Index(
            "ix_generation_jobs_status_priority_created",
            "status",
            "priority",
            "created_at",
        ),
        db.Index(
            "ix_generation_jobs_scope",
            "target_date",
            "locale",
            "forecast_type",
            "provider",
        ),
        db.Index(
            "ix_generation_jobs_batch_status",
            "batch_id",
            "status",
        ),
    )

    def to_dict(self):
        target_date = self.target_date.isoformat()

        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "date": target_date,
            "target_date": target_date,
            "locale": self.locale,
            "forecast_type": self.forecast_type,
            "provider": self.provider,
            "signs": self.signs,
            "max_attempts": self.max_attempts,
            "max_retry_runs": self.max_retry_runs,
            "max_job_attempts": self.max_job_attempts,
            "attempt_count": self.attempt_count,
            "priority": self.priority,
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "dedupe_key": self.dedupe_key,
            "openai_allowed_at_creation": self.openai_allowed_at_creation,
            "created_by": self.created_by,
            "error_message": self.error_message,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "locked_at": _iso(self.locked_at),
            "locked_by": self.locked_by,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class GenerationItem(db.Model):
    __tablename__ = "generation_items"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "generation_runs.id",
            name="fk_generation_items_run_id_generation_runs",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    sign_key = db.Column(
        db.String(32),
        db.ForeignKey(
            "zodiac_signs.key",
            name="fk_generation_items_sign_key_zodiac_signs",
        ),
        nullable=False,
    )
    target_date = db.Column(db.Date, nullable=False)
    locale = db.Column(db.String(8), nullable=False, server_default="ru")
    forecast_type = db.Column(db.String(32), nullable=False, server_default="daily")
    status = db.Column(db.String(32), nullable=False, server_default="pending", index=True)
    forecast_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "forecasts.id",
            name="fk_generation_items_forecast_id_forecasts",
        ),
        nullable=True,
    )
    prompt_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "prompt_versions.id",
            name="fk_generation_items_prompt_version_id_prompt_versions",
        ),
        nullable=True,
    )
    provider = db.Column(db.String(64), nullable=True)
    model_name = db.Column(db.String(128), nullable=True)
    request_payload = db.Column(json_type, nullable=True)
    response_payload = db.Column(json_type, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run = db.relationship("GenerationRun", back_populates="items")
    zodiac_sign = db.relationship("ZodiacSign")
    prompt_version = db.relationship("PromptVersion", foreign_keys=[prompt_version_id])
    forecast = db.relationship("Forecast", foreign_keys=[forecast_id])
    attempts = db.relationship(
        "GenerationAttempt",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="GenerationAttempt.attempt_no",
    )

    __table_args__ = (
        db.Index("ix_generation_items_sign_date", "sign_key", "target_date"),
    )


class GenerationAttempt(db.Model):
    __tablename__ = "generation_attempts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    item_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "generation_items.id",
            name="fk_generation_attempts_item_id_generation_items",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    attempt_no = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, server_default="running", index=True)
    provider = db.Column(db.String(64), nullable=False)
    model_name = db.Column(db.String(128), nullable=True)
    request_payload = db.Column(json_type, nullable=True)
    response_payload = db.Column(json_type, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    error_type = db.Column(db.String(128), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    item = db.relationship("GenerationItem", back_populates="attempts")

    __table_args__ = (
        db.UniqueConstraint(
            "item_id",
            "attempt_no",
            name="uq_generation_attempts_item_attempt_no",
        ),
        db.Index("ix_generation_attempts_item_status", "item_id", "status"),
    )


# PostgreSQL migration 0006 enforces append-only DML and insertion-time
# cross-table coherence. Execution-start writers are separate from paid admission.
class GenerationExecution(db.Model):
    __tablename__ = "generation_executions"

    id = db.Column(Uuid, primary_key=True)
    job_id = db.Column(db.BigInteger, db.ForeignKey(
        "generation_jobs.id", name="fk_gen_exec_job", ondelete="RESTRICT"))
    origin = db.Column(db.String(32), nullable=False)
    deployment_mode = db.Column(db.String(16), nullable=False)
    provider = db.Column(db.String(64), nullable=False)
    target_date = db.Column(db.Date)
    locale = db.Column(db.String(8))
    forecast_type = db.Column(db.String(32))
    policy_version = db.Column(db.String(128), nullable=False)
    lease_epoch = db.Column(db.BigInteger)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "origin IN ('queue_worker', 'dev_direct', 'dev_diagnostic')",
            name="ck_gen_exec_origin"),
        db.CheckConstraint(
            "deployment_mode IN ('production', 'development', 'test')",
            name="ck_gen_exec_mode"),
        db.CheckConstraint(
            "(origin = 'queue_worker' AND job_id IS NOT NULL) OR "
            "(origin <> 'queue_worker' AND job_id IS NULL)",
            name="ck_gen_exec_job_origin"),
        db.CheckConstraint(
            "deployment_mode <> 'production' OR "
            "(origin = 'queue_worker' AND lease_epoch IS NOT NULL)",
            name="ck_gen_exec_production"),
        db.CheckConstraint("lease_epoch > 0", name="ck_gen_exec_epoch"),
        db.CheckConstraint("provider ~ '^[a-z][a-z0-9_]*$'", name="ck_gen_exec_provider"),
        db.CheckConstraint("length(btrim(policy_version)) > 0", name="ck_gen_exec_policy"),
        db.CheckConstraint(
            "(origin = 'dev_diagnostic' AND target_date IS NULL AND locale IS NULL "
            "AND forecast_type IS NULL) OR (origin <> 'dev_diagnostic' AND "
            "target_date IS NOT NULL AND locale IS NOT NULL AND forecast_type IS NOT NULL)",
            name="ck_gen_exec_scope"),
        db.CheckConstraint(
            "length(btrim(locale)) > 0 AND length(btrim(forecast_type)) > 0",
            name="ck_gen_exec_scope_text"),
        db.Index("ix_gen_exec_job_started", "job_id", "started_at"),
        db.Index("ix_gen_exec_scope_started", "target_date", "locale", "forecast_type", "started_at"),
    )


class GenerationExecutionRun(db.Model):
    __tablename__ = "generation_execution_runs"

    execution_id = db.Column(Uuid, db.ForeignKey(
        "generation_executions.id", name="fk_gen_exec_run_execution", ondelete="RESTRICT"),
        primary_key=True)
    run_id = db.Column(db.BigInteger, db.ForeignKey(
        "generation_runs.id", name="fk_gen_exec_run_run", ondelete="RESTRICT"), nullable=False)
    linked_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("execution_id", "run_id", name="uq_gen_exec_run_pair"),
        db.Index("ix_gen_exec_run_run", "run_id"),
    )


class GenerationApiRequest(db.Model):
    __tablename__ = "generation_api_requests"

    id = db.Column(Uuid, primary_key=True)
    execution_id = db.Column(Uuid, db.ForeignKey(
        "generation_executions.id", name="fk_gen_request_execution", ondelete="RESTRICT"),
        nullable=False)
    request_no = db.Column(db.Integer, nullable=False)
    run_id = db.Column(db.BigInteger)
    item_id = db.Column(db.BigInteger, db.ForeignKey(
        "generation_items.id", name="fk_gen_request_item", ondelete="RESTRICT"))
    legacy_attempt_id = db.Column(db.BigInteger, db.ForeignKey(
        "generation_attempts.id", name="fk_gen_request_legacy_attempt", ondelete="RESTRICT"))
    admission_scope = db.Column(db.String(128), nullable=False)
    policy_version = db.Column(db.String(128), nullable=False)
    admitted_at = db.Column(db.DateTime(timezone=True), nullable=False)
    admission_day = db.Column(db.Date, Computed(
        "(admitted_at AT TIME ZONE 'UTC')::date", persisted=True), nullable=False)

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["execution_id", "run_id"],
            ["generation_execution_runs.execution_id", "generation_execution_runs.run_id"],
            name="fk_gen_request_execution_run", ondelete="RESTRICT"),
        db.UniqueConstraint("execution_id", "request_no", name="uq_gen_request_execution_no"),
        db.CheckConstraint("request_no > 0", name="ck_gen_request_no"),
        db.CheckConstraint("length(btrim(admission_scope)) > 0", name="ck_gen_request_scope"),
        db.CheckConstraint("length(btrim(policy_version)) > 0", name="ck_gen_request_policy"),
        db.CheckConstraint(
            "(run_id IS NULL AND item_id IS NULL AND legacy_attempt_id IS NULL) OR "
            "(run_id IS NOT NULL AND item_id IS NOT NULL)", name="ck_gen_request_links"),
        db.Index("ix_gen_request_scope_day", "admission_scope", "admission_day", "admitted_at"),
        db.Index("ix_gen_request_item", "item_id"),
        db.Index("ix_gen_request_legacy_attempt", "legacy_attempt_id"),
    )


class GenerationApiObservation(db.Model):
    __tablename__ = "generation_api_observations"

    id = db.Column(Uuid, primary_key=True)
    request_id = db.Column(Uuid, db.ForeignKey(
        "generation_api_requests.id", name="fk_gen_observation_request", ondelete="RESTRICT"),
        nullable=False)
    observation_no = db.Column(db.Integer, nullable=False)
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False)
    outcome = db.Column(db.String(16), nullable=False)
    review_state = db.Column(db.String(32), nullable=False)
    evidence_code = db.Column(db.String(128))
    provider_request_id = db.Column(db.String(255))
    input_tokens = db.Column(db.BigInteger)
    output_tokens = db.Column(db.BigInteger)
    usage_source = db.Column(db.String(128))
    model_name = db.Column(db.String(128))

    __table_args__ = (
        db.UniqueConstraint("request_id", "observation_no", name="uq_gen_observation_request_no"),
        db.CheckConstraint("observation_no > 0", name="ck_gen_observation_no"),
        db.CheckConstraint(
            "outcome IN ('unknown', 'succeeded', 'failed', 'not_sent')",
            name="ck_gen_observation_outcome"),
        db.CheckConstraint(
            "review_state IN ('requires_review', 'recorded')", name="ck_gen_observation_review"),
        db.CheckConstraint(
            "outcome <> 'unknown' OR review_state = 'requires_review'",
            name="ck_gen_observation_unknown"),
        db.CheckConstraint(
            "outcome <> 'not_sent' OR evidence_code IS NOT NULL",
            name="ck_gen_observation_not_sent"),
        db.CheckConstraint(
            "length(btrim(evidence_code)) > 0 AND length(btrim(usage_source)) > 0 "
            "AND length(btrim(model_name)) > 0 AND length(btrim(provider_request_id)) > 0",
            name="ck_gen_observation_text"),
        db.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="ck_gen_observation_tokens"),
        db.CheckConstraint(
            "outcome <> 'not_sent' OR ((input_tokens IS NULL OR input_tokens = 0) "
            "AND (output_tokens IS NULL OR output_tokens = 0))",
            name="ck_gen_observation_not_sent_usage"),
        db.CheckConstraint(
            "(input_tokens IS NULL AND output_tokens IS NULL) OR "
            "(usage_source IS NOT NULL AND model_name IS NOT NULL)",
            name="ck_gen_observation_usage_source"),
    )

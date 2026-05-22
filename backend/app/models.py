from datetime import date

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from . import db


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
    target_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
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
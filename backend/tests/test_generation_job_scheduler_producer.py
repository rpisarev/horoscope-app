from datetime import date

import pytest

from app.models import GenerationJob
from app.services import SIGNS, save_forecast
from app.services.generation_job_service import (
    JOB_TYPE_RETRY_MISSING,
    JOB_TYPE_SCHEDULED,
    GenerationJobValidationError,
    create_scheduled_generation_job,
    create_scheduled_retry_missing_job,
)


def test_create_scheduled_generation_job_creates_queued_job(app):
    target_day = date(2026, 6, 20)

    with app.app_context():
        result = create_scheduled_generation_job(
            target_date=target_day,
            provider="stub",
            max_attempts=1,
            priority=100,
        )

        assert result["created"] is True
        assert result["reason"] is None
        assert result["job"]["job_type"] == JOB_TYPE_SCHEDULED
        assert result["job"]["status"] == "queued"
        assert result["job"]["date"] == "2026-06-20"
        assert result["job"]["provider"] == "stub"
        assert result["job"]["priority"] == 100
        assert result["job"]["created_by"] == "scheduler"

        assert GenerationJob.query.count() == 1


def test_create_scheduled_generation_job_skips_covered_date(app):
    target_day = date(2026, 6, 20)

    with app.app_context():
        for sign_key in SIGNS:
            save_forecast(
                sign=sign_key,
                day=target_day,
                text=f"Existing forecast for {sign_key}.",
                model_version="stub",
                source="stub",
                status="published",
            )

        result = create_scheduled_generation_job(
            target_date=target_day,
            provider="stub",
            skip_covered=True,
        )

        assert result["created"] is False
        assert result["reason"] == "already_covered"
        assert result["job"] is None
        assert GenerationJob.query.count() == 0


def test_create_scheduled_generation_job_reuses_active_duplicate(app):
    target_day = date(2026, 6, 20)

    with app.app_context():
        first_result = create_scheduled_generation_job(
            target_date=target_day,
            provider="stub",
        )
        second_result = create_scheduled_generation_job(
            target_date=target_day,
            provider="stub",
        )

        assert first_result["created"] is True
        assert second_result["created"] is False
        assert second_result["reason"] == "active_job_exists"
        assert second_result["job"]["id"] == first_result["job"]["id"]
        assert GenerationJob.query.count() == 1


def test_create_scheduled_generation_job_requires_openai_creation_allow(app):
    with app.app_context():
        with pytest.raises(GenerationJobValidationError):
            create_scheduled_generation_job(
                target_date=date(2026, 6, 20),
                provider="openai",
                allow_openai=False,
            )


def test_create_scheduled_generation_job_allows_openai_with_explicit_flag(app):
    with app.app_context():
        result = create_scheduled_generation_job(
            target_date=date(2026, 6, 20),
            provider="openai",
            allow_openai=True,
        )

        assert result["created"] is True
        assert result["job"]["provider"] == "openai"
        assert result["job"]["openai_allowed_at_creation"] is True


def test_create_scheduled_retry_missing_job_creates_job_when_forecasts_missing(app):
    with app.app_context():
        result = create_scheduled_retry_missing_job(
            target_date=date(2026, 6, 20),
            provider="stub",
            max_attempts=1,
            max_retry_runs=3,
            priority=90,
        )

        assert result["created"] is True
        assert result["reason"] is None
        assert result["job"]["job_type"] == JOB_TYPE_RETRY_MISSING
        assert result["job"]["status"] == "queued"
        assert result["job"]["priority"] == 90
        assert len(result["missing_signs"]) == len(SIGNS)

        assert GenerationJob.query.count() == 1


def test_create_scheduled_retry_missing_job_skips_when_nothing_missing(app):
    target_day = date(2026, 6, 20)

    with app.app_context():
        for sign_key in SIGNS:
            save_forecast(
                sign=sign_key,
                day=target_day,
                text=f"Existing forecast for {sign_key}.",
                model_version="stub",
                source="stub",
                status="published",
            )

        result = create_scheduled_retry_missing_job(
            target_date=target_day,
            provider="stub",
        )

        assert result["created"] is False
        assert result["reason"] == "no_missing_forecasts"
        assert result["missing_signs"] == []
        assert result["job"] is None
        assert GenerationJob.query.count() == 0


def test_create_scheduled_retry_missing_job_reuses_active_duplicate(app):
    target_day = date(2026, 6, 20)

    with app.app_context():
        first_result = create_scheduled_retry_missing_job(
            target_date=target_day,
            provider="stub",
        )
        second_result = create_scheduled_retry_missing_job(
            target_date=target_day,
            provider="stub",
        )

        assert first_result["created"] is True
        assert second_result["created"] is False
        assert second_result["reason"] == "active_job_exists"
        assert second_result["job"]["id"] == first_result["job"]["id"]
        assert GenerationJob.query.count() == 1
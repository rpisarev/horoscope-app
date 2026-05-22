from datetime import date, timedelta

import pytest

from app import db
from app.models import Forecast, GenerationJob, GenerationRun
from app.services import SIGNS, save_forecast
from app.services.generation_job_service import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SUCCESS,
    JOB_TYPE_BACKFILL,
    JOB_TYPE_RETRY_MISSING,
    GenerationJobProcessingError,
    GenerationJobValidationError,
    cancel_generation_job,
    claim_next_generation_job,
    close_stale_running_jobs,
    create_generation_job,
    create_generation_jobs_for_range,
    find_active_generation_job,
    process_generation_jobs,
    retry_generation_job,
)


def test_create_generation_job_creates_queued_job(app):
    target_day = date(2026, 6, 15)

    with app.app_context():
        job, created = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries", "taurus", "aries"],
            priority=10,
            created_by="test",
        )

        assert created is True
        assert job.id is not None
        assert job.status == JOB_STATUS_QUEUED
        assert job.job_type == JOB_TYPE_BACKFILL
        assert job.target_date == target_day
        assert job.provider == "stub"
        assert job.signs == ["aries", "taurus"]
        assert job.priority == 10
        assert job.created_by == "test"
        assert job.dedupe_key


def test_create_generation_job_reuses_active_duplicate(app):
    target_day = date(2026, 6, 15)

    with app.app_context():
        first_job, first_created = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries", "taurus"],
        )
        second_job, second_created = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["taurus", "aries"],
        )

        assert first_created is True
        assert second_created is False
        assert second_job.id == first_job.id


def test_create_generation_job_can_reject_active_duplicate(app):
    target_day = date(2026, 6, 15)

    with app.app_context():
        create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries"],
        )

        with pytest.raises(GenerationJobValidationError):
            create_generation_job(
                job_type=JOB_TYPE_BACKFILL,
                target_date=target_day,
                provider="stub",
                signs=["aries"],
                skip_duplicate=False,
            )


def test_create_generation_job_requires_explicit_openai_allow(app):
    with app.app_context():
        with pytest.raises(GenerationJobValidationError):
            create_generation_job(
                job_type=JOB_TYPE_BACKFILL,
                target_date=date(2026, 6, 15),
                provider="openai",
            )


def test_create_generation_job_allows_openai_creation_with_explicit_flag(app):
    with app.app_context():
        job, created = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 15),
            provider="openai",
            allow_openai=True,
        )

        assert created is True
        assert job.provider == "openai"
        assert job.openai_allowed_at_creation is True


def test_retry_missing_job_rejects_sign_subset(app):
    with app.app_context():
        with pytest.raises(GenerationJobValidationError):
            create_generation_job(
                job_type=JOB_TYPE_RETRY_MISSING,
                target_date=date(2026, 6, 15),
                provider="stub",
                signs=["aries"],
            )


def test_find_active_generation_job_returns_queued_or_running_only(app):
    target_day = date(2026, 6, 15)

    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries"],
        )

        found_job = find_active_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries"],
        )

        assert found_job.id == job.id

        job.status = JOB_STATUS_SUCCESS
        db.session.commit()

        assert (
            find_active_generation_job(
                job_type=JOB_TYPE_BACKFILL,
                target_date=target_day,
                provider="stub",
                signs=["aries"],
            )
            is None
        )


def test_create_generation_jobs_for_range_dry_run(app):
    with app.app_context():
        result = create_generation_jobs_for_range(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            provider="stub",
            dry_run=True,
        )

        assert result["processed_dates"] == 3
        assert result["created_count"] == 0
        assert result["dry_run_count"] == 3
        assert GenerationJob.query.count() == 0


def test_create_generation_jobs_for_range_creates_jobs(app):
    with app.app_context():
        result = create_generation_jobs_for_range(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            provider="stub",
            created_by="test",
        )

        assert result["processed_dates"] == 3
        assert result["created_count"] == 3
        assert GenerationJob.query.count() == 3

        batch_ids = {job.batch_id for job in GenerationJob.query.all()}
        assert batch_ids == {result["batch_id"]}


def test_create_generation_jobs_for_range_can_skip_covered_dates(app):
    covered_day = date(2026, 6, 1)

    with app.app_context():
        for sign_key in SIGNS:
            save_forecast(
                sign=sign_key,
                day=covered_day,
                text=f"Existing forecast for {sign_key}.",
                model_version="stub",
                source="stub",
                status="published",
            )

        result = create_generation_jobs_for_range(
            start_date=covered_day,
            end_date=covered_day + timedelta(days=1),
            provider="stub",
            skip_covered=True,
        )

        assert result["processed_dates"] == 2
        assert result["covered_count"] == 1
        assert result["created_count"] == 1
        assert GenerationJob.query.count() == 1


def test_claim_next_generation_job_respects_priority(app):
    with app.app_context():
        low_job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 1),
            provider="stub",
            priority=1,
        )
        high_job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 2),
            provider="stub",
            priority=10,
        )

        claimed_job = claim_next_generation_job(worker_id="test-worker")

        assert claimed_job.id == high_job.id
        assert claimed_job.locked_by == "test-worker"
        assert claimed_job.status == "running"

        low_job = db.session.get(GenerationJob, low_job.id)
        assert low_job.status == JOB_STATUS_QUEUED


def test_cancel_generation_job_marks_queued_job_cancelled(app):
    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 1),
            provider="stub",
        )

        cancelled_job = cancel_generation_job(job.id)

        assert cancelled_job.status == JOB_STATUS_CANCELLED
        assert cancelled_job.finished_at is not None


def test_retry_generation_job_requeues_failed_job(app):
    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 1),
            provider="stub",
        )
        job.status = JOB_STATUS_FAILED
        job.error_message = "Failed once."
        job.finished_at = job.created_at
        db.session.commit()

        retried_job = retry_generation_job(job.id)

        assert retried_job.status == JOB_STATUS_QUEUED
        assert retried_job.error_message is None
        assert retried_job.finished_at is None


def test_close_stale_running_jobs_marks_expired_job_failed(app):
    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 1),
            provider="stub",
            max_job_attempts=1,
        )
        claimed_job = claim_next_generation_job(worker_id="test-worker")
        claimed_job.locked_at = claimed_job.locked_at - timedelta(minutes=120)
        db.session.commit()

        closed_count = close_stale_running_jobs(stale_after_minutes=60)

        assert closed_count == 1

        expired_job = db.session.get(GenerationJob, job.id)
        assert expired_job.status == JOB_STATUS_FAILED
        assert expired_job.finished_at is not None


def test_process_generation_jobs_runs_stub_job(app):
    target_day = date(2026, 6, 15)

    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=target_day,
            provider="stub",
            signs=["aries"],
            max_attempts=1,
        )

        result = process_generation_jobs(limit=1, worker_id="test-worker")

        assert result["processed_count"] == 1
        assert result["jobs"][0]["id"] == job.id
        assert result["jobs"][0]["status"] == JOB_STATUS_SUCCESS

        processed_job = db.session.get(GenerationJob, job.id)
        assert processed_job.run_id is not None
        assert processed_job.status == JOB_STATUS_SUCCESS

        run = db.session.get(GenerationRun, processed_job.run_id)
        assert run.status == "success"
        assert run.total_items == 1
        assert run.success_items == 1

        forecasts = Forecast.query.filter_by(
            target_date=target_day,
            sign_key="aries",
            status="published",
        ).all()
        assert len(forecasts) == 1


def test_process_generation_jobs_rejects_openai_without_worker_allow(app):
    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 15),
            provider="openai",
            allow_openai=True,
        )

        result = process_generation_jobs(
            limit=1,
            worker_id="test-worker",
            allow_openai=False,
        )

        assert result["processed_count"] == 1

        failed_job = db.session.get(GenerationJob, job.id)
        assert failed_job.status == JOB_STATUS_FAILED
        assert "provider=openai" in failed_job.error_message


def test_process_claimed_generation_job_requires_lock_owner(app):
    with app.app_context():
        job, _ = create_generation_job(
            job_type=JOB_TYPE_BACKFILL,
            target_date=date(2026, 6, 15),
            provider="stub",
        )
        claimed_job = claim_next_generation_job(worker_id="worker-a")

        from app.services.generation_job_service import process_claimed_generation_job

        with pytest.raises(GenerationJobProcessingError):
            process_claimed_generation_job(
                claimed_job,
                worker_id="worker-b",
            )
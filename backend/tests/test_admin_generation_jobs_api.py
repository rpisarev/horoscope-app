from datetime import date

import pytest

from app import db
from app.models import GenerationJob, GenerationRun


ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def reset_admin_api_config(app):
    app.config.update(
        ADMIN_API_ENABLED=False,
        ADMIN_API_TOKEN=None,
        ADMIN_API_ALLOW_OPENAI=False,
    )
    yield
    app.config.update(
        ADMIN_API_ENABLED=False,
        ADMIN_API_TOKEN=None,
        ADMIN_API_ALLOW_OPENAI=False,
    )


def _enable_admin_api(app, *, token: str = ADMIN_TOKEN) -> None:
    app.config.update(
        ADMIN_API_ENABLED=True,
        ADMIN_API_TOKEN=token,
    )


def _admin_headers(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_create_single_generation_job(app, client):
    _enable_admin_api(app)

    response = client.post(
        "/api/admin/generation/jobs",
        json={
            "date": "2026-06-15",
            "provider": "stub",
            "job_type": "manual",
            "signs": ["aries", "taurus", "aries"],
            "max_attempts": 1,
            "priority": 7,
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["created"] is True
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["job_type"] == "manual"
    assert payload["job"]["date"] == "2026-06-15"
    assert payload["job"]["provider"] == "stub"
    assert payload["job"]["signs"] == ["aries", "taurus"]
    assert payload["job"]["priority"] == 7

    with app.app_context():
        assert GenerationJob.query.count() == 1


def test_admin_single_generation_job_reuses_active_duplicate(app, client):
    _enable_admin_api(app)

    body = {
        "date": "2026-06-15",
        "provider": "stub",
        "job_type": "manual",
        "signs": ["aries"],
    }

    first_response = client.post(
        "/api/admin/generation/jobs",
        json=body,
        headers=_admin_headers(),
    )
    second_response = client.post(
        "/api/admin/generation/jobs",
        json=body,
        headers=_admin_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_payload = first_response.get_json()
    second_payload = second_response.get_json()

    assert first_payload["created"] is True
    assert second_payload["created"] is False
    assert second_payload["job"]["id"] == first_payload["job"]["id"]

    with app.app_context():
        assert GenerationJob.query.count() == 1


def test_admin_create_job_rejects_openai_without_double_allow(app, client):
    _enable_admin_api(app)
    app.config.update(ADMIN_API_ALLOW_OPENAI=True)

    response = client.post(
        "/api/admin/generation/jobs",
        json={
            "date": "2026-06-15",
            "provider": "openai",
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "bad_admin_generation_request"
    assert "allow_openai=true" in response.get_json()["error"]["message"]


def test_admin_create_job_rejects_openai_when_admin_gate_disabled(app, client):
    _enable_admin_api(app)
    app.config.update(ADMIN_API_ALLOW_OPENAI=False)

    response = client.post(
        "/api/admin/generation/jobs",
        json={
            "date": "2026-06-15",
            "provider": "openai",
            "allow_openai": True,
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "bad_admin_generation_request"
    assert "disabled for Admin API" in response.get_json()["error"]["message"]


def test_admin_can_create_backfill_jobs_for_range(app, client):
    _enable_admin_api(app)

    response = client.post(
        "/api/admin/generation/jobs/backfill",
        json={
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "provider": "stub",
            "max_attempts": 1,
            "priority": 3,
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["processed_dates"] == 3
    assert payload["created_count"] == 3
    assert payload["duplicate_count"] == 0
    assert payload["provider"] == "stub"
    assert payload["job_type"] == "backfill"

    with app.app_context():
        assert GenerationJob.query.count() == 3


def test_admin_backfill_dry_run_does_not_create_jobs(app, client):
    _enable_admin_api(app)

    response = client.post(
        "/api/admin/generation/jobs/backfill",
        json={
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "provider": "stub",
            "dry_run": True,
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["processed_dates"] == 3
    assert payload["created_count"] == 0
    assert payload["dry_run_count"] == 3
    assert payload["dry_run"] is True

    with app.app_context():
        assert GenerationJob.query.count() == 0


def test_admin_backfill_can_create_retry_missing_jobs(app, client):
    _enable_admin_api(app)

    response = client.post(
        "/api/admin/generation/jobs/backfill",
        json={
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "provider": "stub",
            "retry_missing": True,
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["processed_dates"] == 2
    assert payload["created_count"] == 2
    assert payload["job_type"] == "retry_missing"

    with app.app_context():
        assert {job.job_type for job in GenerationJob.query.all()} == {"retry_missing"}


def test_admin_list_generation_jobs_filters_by_status(app, client):
    _enable_admin_api(app)

    with app.app_context():
        queued_job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            dedupe_key="queued-job",
        )
        failed_job = GenerationJob(
            job_type="backfill",
            status="failed",
            target_date=date(2026, 6, 2),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            dedupe_key="failed-job",
        )
        db.session.add_all([queued_job, failed_job])
        db.session.commit()

    response = client.get(
        "/api/admin/generation/jobs?status=queued",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["status"] == "queued"
    assert payload["items"][0]["date"] == "2026-06-01"


def test_admin_get_generation_job_batch_status(app, client):
    _enable_admin_api(app)

    with app.app_context():
        jobs = [
            GenerationJob(
                job_type="backfill",
                status="queued",
                target_date=date(2026, 6, 1),
                locale="ru",
                forecast_type="daily",
                provider="stub",
                batch_id="batch-status-test",
                dedupe_key="batch-status-test-queued",
            ),
            GenerationJob(
                job_type="backfill",
                status="success",
                target_date=date(2026, 6, 2),
                locale="ru",
                forecast_type="daily",
                provider="stub",
                batch_id="batch-status-test",
                dedupe_key="batch-status-test-success",
            ),
            GenerationJob(
                job_type="backfill",
                status="failed",
                target_date=date(2026, 6, 3),
                locale="ru",
                forecast_type="daily",
                provider="stub",
                batch_id="batch-status-test",
                dedupe_key="batch-status-test-failed",
                error_message="Failed once.",
            ),
        ]

        db.session.add_all(jobs)
        db.session.commit()

    response = client.get(
        "/api/admin/generation/jobs/batches/batch-status-test",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["batch_id"] == "batch-status-test"
    assert payload["total_count"] == 3
    assert payload["status_counts"]["queued"] == 1
    assert payload["status_counts"]["running"] == 0
    assert payload["status_counts"]["success"] == 1
    assert payload["status_counts"]["partial_failed"] == 0
    assert payload["status_counts"]["failed"] == 1
    assert payload["status_counts"]["cancelled"] == 0
    assert payload["provider_counts"] == {"stub": 3}
    assert payload["job_type_counts"] == {"backfill": 3}
    assert payload["target_date_min"] == "2026-06-01"
    assert payload["target_date_max"] == "2026-06-03"
    assert payload["active_count"] == 1
    assert payload["finished_count"] == 2
    assert payload["success_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["cancelled_count"] == 0
    assert payload["progress_percent"] == 66.67
    assert payload["is_complete"] is False
    assert payload["has_failures"] is True
    assert [item["date"] for item in payload["items"]] == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
    ]


def test_admin_can_cancel_generation_job_batch(app, client):
    _enable_admin_api(app)

    with app.app_context():
        queued_job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-cancel-test",
            dedupe_key="batch-cancel-test-queued",
        )
        running_job = GenerationJob(
            job_type="backfill",
            status="running",
            target_date=date(2026, 6, 2),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-cancel-test",
            dedupe_key="batch-cancel-test-running",
            locked_by="test-worker",
        )
        success_job = GenerationJob(
            job_type="backfill",
            status="success",
            target_date=date(2026, 6, 3),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-cancel-test",
            dedupe_key="batch-cancel-test-success",
        )
        other_batch_job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 4),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="other-batch",
            dedupe_key="batch-cancel-test-other-batch",
        )

        db.session.add_all([queued_job, running_job, success_job, other_batch_job])
        db.session.commit()

        queued_job_id = queued_job.id
        running_job_id = running_job.id
        success_job_id = success_job.id
        other_batch_job_id = other_batch_job.id

    response = client.post(
        "/api/admin/generation/jobs/batches/batch-cancel-test/cancel",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["batch_id"] == "batch-cancel-test"
    assert payload["total_count"] == 3
    assert payload["cancelled_count"] == 1
    assert payload["skipped_count"] == 2
    assert payload["skipped_status_counts"] == {
        "running": 1,
        "success": 1,
    }
    assert payload["batch_status"]["status_counts"]["cancelled"] == 1
    assert payload["batch_status"]["status_counts"]["running"] == 1
    assert payload["batch_status"]["status_counts"]["success"] == 1

    with app.app_context():
        assert db.session.get(GenerationJob, queued_job_id).status == "cancelled"
        assert db.session.get(GenerationJob, running_job_id).status == "running"
        assert db.session.get(GenerationJob, success_job_id).status == "success"
        assert db.session.get(GenerationJob, other_batch_job_id).status == "queued"


def test_admin_can_retry_failed_generation_job_batch(app, client):
    _enable_admin_api(app)

    with app.app_context():
        failed_job = GenerationJob(
            job_type="backfill",
            status="failed",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-retry-failed-test",
            dedupe_key="batch-retry-failed-test-failed",
            error_message="Failed once.",
        )
        partial_failed_job = GenerationJob(
            job_type="backfill",
            status="partial_failed",
            target_date=date(2026, 6, 2),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-retry-failed-test",
            dedupe_key="batch-retry-failed-test-partial-failed",
            error_message="Partial failure.",
        )
        success_job = GenerationJob(
            job_type="backfill",
            status="success",
            target_date=date(2026, 6, 3),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-retry-failed-test",
            dedupe_key="batch-retry-failed-test-success",
        )
        queued_job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 4),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            batch_id="batch-retry-failed-test",
            dedupe_key="batch-retry-failed-test-queued",
        )

        db.session.add_all([failed_job, partial_failed_job, success_job, queued_job])
        db.session.commit()

        failed_job_id = failed_job.id
        partial_failed_job_id = partial_failed_job.id
        success_job_id = success_job.id
        queued_job_id = queued_job.id

    response = client.post(
        "/api/admin/generation/jobs/batches/batch-retry-failed-test/retry-failed",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["batch_id"] == "batch-retry-failed-test"
    assert payload["total_count"] == 4
    assert payload["retried_count"] == 2
    assert payload["skipped_count"] == 2
    assert payload["skipped_status_counts"] == {
        "queued": 1,
        "success": 1,
    }
    assert payload["batch_status"]["status_counts"]["queued"] == 3
    assert payload["batch_status"]["status_counts"]["failed"] == 0
    assert payload["batch_status"]["status_counts"]["partial_failed"] == 0
    assert payload["batch_status"]["status_counts"]["success"] == 1
    assert payload["batch_status"]["has_failures"] is False

    with app.app_context():
        failed_job = db.session.get(GenerationJob, failed_job_id)
        partial_failed_job = db.session.get(GenerationJob, partial_failed_job_id)
        success_job = db.session.get(GenerationJob, success_job_id)
        queued_job = db.session.get(GenerationJob, queued_job_id)

        assert failed_job.status == "queued"
        assert failed_job.error_message is None
        assert failed_job.run_id is None

        assert partial_failed_job.status == "queued"
        assert partial_failed_job.error_message is None
        assert partial_failed_job.run_id is None

        assert success_job.status == "success"
        assert queued_job.status == "queued"


def test_admin_generation_job_batch_actions_return_404_for_unknown_batch(app, client):
    _enable_admin_api(app)

    for endpoint in [
        "/api/admin/generation/jobs/batches/missing-batch/cancel",
        "/api/admin/generation/jobs/batches/missing-batch/retry-failed",
    ]:
        response = client.post(endpoint, headers=_admin_headers())

        assert response.status_code == 404
        assert response.get_json()["error"]["code"] == "generation_job_batch_not_found"


def test_admin_generation_job_batch_status_returns_404_for_unknown_batch(
    app,
    client,
):
    _enable_admin_api(app)

    response = client.get(
        "/api/admin/generation/jobs/batches/missing-batch",
        headers=_admin_headers(),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "generation_job_batch_not_found"


def test_admin_get_generation_job_detail_includes_run_summary(app, client):
    _enable_admin_api(app)

    with app.app_context():
        run = GenerationRun(
            run_type="backfill",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            status="success",
            total_items=1,
            success_items=1,
            failed_items=0,
            skipped_items=0,
        )
        db.session.add(run)
        db.session.flush()

        job = GenerationJob(
            job_type="backfill",
            status="success",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            run_id=run.id,
            dedupe_key="job-with-run",
        )
        db.session.add(job)
        db.session.commit()

        job_id = job.id
        run_id = run.id

    response = client.get(
        f"/api/admin/generation/jobs/{job_id}",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["id"] == job_id
    assert payload["run_id"] == run_id
    assert payload["run"]["id"] == run_id
    assert payload["run"]["status"] == "success"


def test_admin_generation_job_detail_returns_404_for_unknown_id(app, client):
    _enable_admin_api(app)

    response = client.get(
        "/api/admin/generation/jobs/999999",
        headers=_admin_headers(),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "generation_job_not_found"


def test_admin_can_cancel_queued_generation_job(app, client):
    _enable_admin_api(app)

    with app.app_context():
        job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            dedupe_key="cancel-job",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    response = client.post(
        f"/api/admin/generation/jobs/{job_id}/cancel",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["job"]["id"] == job_id
    assert payload["job"]["status"] == "cancelled"

    with app.app_context():
        cancelled_job = db.session.get(GenerationJob, job_id)
        assert cancelled_job.status == "cancelled"


def test_admin_cancel_generation_job_returns_404_for_unknown_id(app, client):
    _enable_admin_api(app)

    response = client.post(
        "/api/admin/generation/jobs/999999/cancel",
        headers=_admin_headers(),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "generation_job_not_found"


def test_admin_can_retry_failed_generation_job(app, client):
    _enable_admin_api(app)

    with app.app_context():
        job = GenerationJob(
            job_type="backfill",
            status="failed",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            dedupe_key="retry-job",
            error_message="Failed once.",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    response = client.post(
        f"/api/admin/generation/jobs/{job_id}/retry",
        headers=_admin_headers(),
    )

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["job"]["id"] == job_id
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["error_message"] is None

    with app.app_context():
        retried_job = db.session.get(GenerationJob, job_id)
        assert retried_job.status == "queued"
        assert retried_job.error_message is None


def test_admin_retry_generation_job_rejects_non_failed_job(app, client):
    _enable_admin_api(app)

    with app.app_context():
        job = GenerationJob(
            job_type="backfill",
            status="queued",
            target_date=date(2026, 6, 1),
            locale="ru",
            forecast_type="daily",
            provider="stub",
            dedupe_key="queued-job",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    response = client.post(
        f"/api/admin/generation/jobs/{job_id}/retry",
        headers=_admin_headers(),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "bad_admin_generation_request"
    assert "Only failed or partial_failed jobs" in response.get_json()["error"]["message"]
"""DB regressions for the orchestrator's serial disposable-database verification.

Do not include this file in the host's pure unittest command. Existing conftest
owns DB isolation; every paid transport below is forbidden or replaced by a fake.
"""

from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from app import db
from app.models import (
    Forecast, GenerationApiRequest, GenerationAttempt, GenerationExecution,
    GenerationItem, GenerationJob, GenerationRun,
)
import app.services.generation_service as lifecycle
import app.services.generation_job_service as jobs
from app.providers import OpenAIHoroscopeProvider, ProviderResult
from app.providers.registry import PROVIDERS, ProviderDefinition
from app.services.generation_job_service import create_generation_job, process_generation_jobs
from app.services.generation_service import run_daily_generation


DAY = date(2026, 11, 14)
SETTING = "GENERATION_PAID_EXECUTION_ENABLED"


@pytest.fixture(autouse=True)
def forbid_paid_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Paid-execution lifecycle tests must never call HTTP/OpenAI")

    monkeypatch.setenv(SETTING, "0")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-fake-key")
    monkeypatch.setattr(OpenAIHoroscopeProvider, "generate", forbidden)
    monkeypatch.setattr(OpenAIHoroscopeProvider, "_get_client", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)


def assert_no_generation_work():
    assert GenerationItem.query.count() == 0
    assert GenerationAttempt.query.count() == 0
    assert Forecast.query.count() == 0


@pytest.mark.parametrize("setting", [None, "0", "invalid"])
def test_disabled_lifecycle_records_failed_run_without_items_or_attempts(app, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, setting)

    with app.app_context():
        run = run_daily_generation(target_date=DAY, provider_name="openai", signs=["aries"])
        persisted = db.session.get(GenerationRun, run.id)
        assert persisted.status == "failed"
        assert "Paid execution denied" in persisted.error_message
        assert SETTING in persisted.error_message
        assert persisted.finished_at is not None
        assert persisted.total_items == 0
        assert GenerationRun.query.count() == 1
        assert_no_generation_work()


def create_paid_job():
    job, created = create_generation_job(
        job_type="manual", target_date=DAY, provider="openai", signs=["aries"],
        max_attempts=1, allow_openai=True,
    )
    assert created
    return job


def test_disabled_queue_consumes_claim_but_creates_no_run_or_provider_attempt(app):
    with app.app_context():
        job = create_paid_job()
        result = process_generation_jobs(limit=1, worker_id="paid-policy-test", allow_openai=True)
        persisted = db.session.get(GenerationJob, job.id)
        assert result["processed_count"] == 1
        assert persisted.status == "failed"
        assert "Paid execution denied" in persisted.error_message
        assert persisted.attempt_count == 1
        assert persisted.started_at is not None
        assert persisted.finished_at is not None
        assert persisted.locked_at is None
        assert persisted.locked_by is None
        assert persisted.run_id is None
        assert GenerationRun.query.count() == 0
        assert_no_generation_work()


def test_enabled_worker_with_local_auth_runs_fake_provider_lifecycle(app, monkeypatch):
    calls = []

    class FakePaidProvider:
        name = "openai"
        model_name = "fake-paid-model"

        def generate(self, request):
            calls.append(request)
            return ProviderResult(
                text="Спокойный разговор поможет увидеть привычное дело иначе.",
                provider=self.name, model_name=self.model_name,
            )

    monkeypatch.setenv(SETTING, "1")
    monkeypatch.setitem(PROVIDERS, "openai", ProviderDefinition(FakePaidProvider, False, True))
    # Explicit test-only admission mocks: all HTTP/real adapter entry points are
    # forbidden by the fixture and the registry contains only this fake.
    monkeypatch.setattr(lifecycle, "require_paid_admission", lambda _: None)
    monkeypatch.setattr(jobs, "require_paid_admission", lambda _: None)
    with app.app_context():
        job = create_paid_job()
        process_generation_jobs(limit=1, worker_id="paid-policy-test", allow_openai=True)
        persisted = db.session.get(GenerationJob, job.id)
        assert persisted.status == "success"
        assert persisted.run_id is not None
        assert db.session.get(GenerationRun, persisted.run_id).status == "success"
        assert GenerationItem.query.one().status == "success"
        assert GenerationAttempt.query.one().status == "success"
        assert Forecast.query.one().source == "openai"
        assert len(calls) == 1


def test_enabled_worker_still_denies_missing_local_authorization(app, monkeypatch):
    monkeypatch.setenv(SETTING, "1")
    with app.app_context():
        job = create_paid_job()
        process_generation_jobs(limit=1, worker_id="paid-policy-test", allow_openai=False)
        persisted = db.session.get(GenerationJob, job.id)
        assert persisted.status == "failed"
        assert "worker allow_openai" in persisted.error_message
        assert persisted.run_id is None
        assert persisted.attempt_count == 1
        assert GenerationRun.query.count() == 0
        assert_no_generation_work()


@pytest.mark.parametrize("provider_name", ["openai", " OPENAI ", None])
def test_enabled_lifecycle_admission_denial_precedes_factory_and_creates_no_intent(app, monkeypatch, provider_name):
    monkeypatch.setenv(SETTING, "1")
    monkeypatch.setenv("HOROSCOPE_PROVIDER", "openai")
    factory = Mock(side_effect=AssertionError("Denied canonical provider must not reach factory"))
    monkeypatch.setattr(lifecycle, "get_horoscope_provider", factory)
    with app.app_context():
        run = run_daily_generation(target_date=DAY, provider_name=provider_name, signs=["aries"])
        assert run.status == "failed"
        assert "atomic request admission" in run.error_message
        assert run.total_items == 0
        assert GenerationExecution.query.count() == 0
        assert GenerationApiRequest.query.count() == 0
        assert_no_generation_work()
    factory.assert_not_called()


def test_enabled_worker_admission_denial_preserves_claim_history_without_intent(app, monkeypatch):
    monkeypatch.setenv(SETTING, "1")
    dispatch = Mock(side_effect=AssertionError("Denied worker must not dispatch lifecycle"))
    monkeypatch.setattr(jobs, "_run_standard_generation_job", dispatch)
    with app.app_context():
        job = create_paid_job()
        result = process_generation_jobs(limit=1, worker_id="admission-test", allow_openai=True)
        persisted = db.session.get(GenerationJob, job.id)
        assert result["processed_count"] == 1
        assert persisted.status == "failed"
        assert "atomic request admission" in persisted.error_message
        assert persisted.attempt_count == 1
        assert persisted.run_id is None
        assert GenerationExecution.query.count() == 1
        assert GenerationExecution.query.one().job_id == job.id
        assert GenerationRun.query.count() == 0
        assert GenerationApiRequest.query.count() == 0
        assert_no_generation_work()
    dispatch.assert_not_called()

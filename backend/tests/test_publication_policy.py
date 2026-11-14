from datetime import date

import pytest

from app import create_app, db
from app.config import Config
from app.models import Forecast, GenerationAttempt, GenerationItem, GenerationRun
from app.providers import ProviderResult
from app.providers.openai_provider import OpenAIHoroscopeProvider
from app.providers.publication_policy import PublicationPolicyError, require_publication_provider
from app.providers.registry import PROVIDERS, ProviderDefinition
from app.providers.stub import StubHoroscopeProvider
from app.services import generation_service, save_forecast
from app.services.generation_job_service import (
    create_generation_job,
    process_generation_jobs,
    retry_generation_job,
)


DAY = date(2026, 9, 28)


@pytest.fixture(autouse=True)
def no_paid_generation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Publication policy tests must never call OpenAI")

    monkeypatch.setattr(OpenAIHoroscopeProvider, "generate", forbidden)


def production(app, monkeypatch, allowed="openai"):
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", "production")
    monkeypatch.setitem(app.config, "PRODUCTION_PUBLICATION_PROVIDERS", allowed)


def forbid_stub_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Forbidden provider must be rejected before generation")

    monkeypatch.setattr(StubHoroscopeProvider, "generate", forbidden)


@pytest.mark.parametrize("mode", ["development", "test"])
def test_local_stub_generation_still_publishes(app, monkeypatch, mode):
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", mode)
    run = generation_service.run_daily_generation(
        target_date=DAY, provider_name="stub", signs=["aries"]
    )
    assert run.status == "success"
    forecast = Forecast.query.one()
    assert (forecast.status, forecast.source, forecast.model_name) == ("published", "stub", "stub")
    assert forecast.generation_item_id is not None


@pytest.mark.parametrize("allowed", ["openai", "stub,openai"])
def test_production_stub_fails_before_call_without_overwriting_existing(app, monkeypatch, allowed):
    existing = save_forecast("aries", DAY, "Existing published local forecast")
    before = existing.to_dict()
    production(app, monkeypatch, allowed)
    forbid_stub_call(monkeypatch)
    run = generation_service.run_daily_generation(
        target_date=DAY, provider_name="stub", signs=["aries", "taurus"]
    )
    assert run.status == "failed"
    assert "forbids provider 'stub' in production" in run.error_message
    assert run.finished_at is not None
    assert GenerationItem.query.count() == GenerationAttempt.query.count() == 0
    assert Forecast.query.count() == 1
    db.session.refresh(existing)
    assert existing.to_dict() == before


@pytest.mark.parametrize("identity", [None, "stub", "unknown"])
def test_production_persistence_requires_execution_identity_not_source(app, monkeypatch, identity):
    production(app, monkeypatch)
    with pytest.raises(PublicationPolicyError):
        save_forecast(
            "aries", DAY, "Claiming OpenAI cannot authorize a stub",
            source="openai", model_version="gpt-test", publication_provider=identity,
        )
    assert Forecast.query.count() == 0


def test_rejected_persistence_does_not_mutate_existing_row(app, monkeypatch):
    existing = save_forecast("aries", DAY, "Keep this forecast")
    before = existing.to_dict()
    production(app, monkeypatch)
    with pytest.raises(PublicationPolicyError):
        save_forecast("aries", DAY, "Replacement", publication_provider="stub")
    # Also check the in-memory row before any rollback can hide a mutation.
    assert existing.to_dict() == before
    db.session.commit()
    db.session.refresh(existing)
    assert existing.to_dict() == before


def test_generic_draft_persistence_remains_available_in_production(app, monkeypatch):
    production(app, monkeypatch)
    forecast = save_forecast("aries", DAY, "Editorial draft", status="draft", source="manual")
    assert forecast.status == "draft"
    assert forecast.published_at is None


@pytest.mark.parametrize("job_type", ["manual", "scheduled", "retry_missing", "backfill"])
def test_worker_rechecks_persisted_stub_jobs_and_retries(app, monkeypatch, job_type):
    job, _ = create_generation_job(target_date=DAY, job_type=job_type, provider="stub")
    production(app, monkeypatch)
    forbid_stub_call(monkeypatch)
    for attempt in range(2):
        if attempt:
            retry_generation_job(job.id)
        process_generation_jobs(limit=1, worker_id="publication-test")
        db.session.refresh(job)
        assert job.status == "failed"
        assert job.provider == "stub"
        assert "forbids provider 'stub' in production" in job.error_message
        assert job.finished_at is not None
        assert Forecast.query.count() == 0


def test_direct_retry_missing_obeys_policy(app, monkeypatch):
    production(app, monkeypatch)
    forbid_stub_call(monkeypatch)
    run = generation_service.run_retry_for_missing_forecasts(target_date=DAY, provider_name="stub")
    assert run.status == "failed"
    assert "Publication policy" in run.error_message
    assert Forecast.query.count() == 0


def test_direct_scheduler_obeys_shared_policy(app, monkeypatch):
    import tasks

    production(app, monkeypatch)
    forbid_stub_call(monkeypatch)
    monkeypatch.setattr(tasks, "app", app)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULER_USE_QUEUE", False)
    monkeypatch.setattr(tasks, "HOROSCOPE_PROVIDER", "stub")
    monkeypatch.setattr(tasks, "scheduled_target_dates", lambda: [DAY])
    result = tasks.generate_daily_forecasts()
    assert result["runs"][0]["status"] == "failed"
    assert "Publication policy" in GenerationRun.query.one().error_message
    assert Forecast.query.count() == 0


def test_immediate_admin_reports_failed_run(app, client, monkeypatch):
    production(app, monkeypatch)
    forbid_stub_call(monkeypatch)
    monkeypatch.setitem(app.config, "ADMIN_API_ENABLED", True)
    monkeypatch.setitem(app.config, "ADMIN_API_TOKEN", "publication-test")
    response = client.post(
        "/api/admin/generation/runs",
        headers={"Authorization": "Bearer publication-test"},
        json={"date": DAY.isoformat(), "provider": "stub", "signs": ["aries"]},
    )
    assert response.status_code == 200  # Existing API reports execution through run status.
    run = response.get_json()["run"]
    assert run["status"] == "failed"
    assert "Publication policy" in run["error_message"]
    assert Forecast.query.count() == 0


def test_package_cli_reports_policy_failure(app, monkeypatch, capsys):
    from utils import generate_forecast_package

    production(app, monkeypatch)
    forbid_stub_call(monkeypatch)
    monkeypatch.setattr("app.create_app", lambda: app)
    monkeypatch.setattr(generate_forecast_package, "load_local_env", lambda: None)
    monkeypatch.setattr("sys.argv", ["generate_forecast_package.py", "--date", DAY.isoformat(), "--provider", "stub"])
    generate_forecast_package.main()
    assert "Publication policy" in capsys.readouterr().out
    assert GenerationRun.query.one().status == "failed"
    assert Forecast.query.count() == 0


class RealTestProvider:
    name = "future-real"
    model_name = "model-family:version"

    def generate(self, request):
        return ProviderResult(
            text="Спокойный день поможет завершить начатые дела.",
            provider=self.name, model_name=self.model_name,
        )


@pytest.mark.parametrize("provider_name", ["openai", "future-real"])
def test_approved_real_capability_is_not_openai_specific(app, monkeypatch, provider_name):
    class Adapter(RealTestProvider):
        name = provider_name

    monkeypatch.setitem(PROVIDERS, provider_name, ProviderDefinition(Adapter, False, True))
    production(app, monkeypatch, provider_name)
    run = generation_service.run_daily_generation(
        target_date=DAY, provider_name=provider_name, signs=["aries"]
    )
    assert run.status == "success"
    assert Forecast.query.one().source == provider_name
    assert Forecast.query.one().model_name == "model-family:version"


def test_builtin_capabilities_and_unapproved_real_provider(app, monkeypatch):
    assert PROVIDERS["stub"].development_only
    assert not PROVIDERS["stub"].production_publication_capable
    assert not PROVIDERS["openai"].development_only
    assert PROVIDERS["openai"].production_publication_capable
    monkeypatch.setitem(PROVIDERS, "future-real", ProviderDefinition(RealTestProvider, False, True))
    production(app, monkeypatch)
    with pytest.raises(PublicationPolicyError):
        require_publication_provider("future-real")
    monkeypatch.setitem(app.config, "PRODUCTION_PUBLICATION_PROVIDERS", "")
    with pytest.raises(PublicationPolicyError):
        require_publication_provider("openai")


def test_persistence_rechecks_policy_changed_during_generation(app, monkeypatch):
    class ChangingPolicyProvider(RealTestProvider):
        def generate(self, request):
            result = super().generate(request)
            monkeypatch.setitem(app.config, "PRODUCTION_PUBLICATION_PROVIDERS", "")
            return result

    monkeypatch.setitem(PROVIDERS, "future-real", ProviderDefinition(ChangingPolicyProvider, False, True))
    production(app, monkeypatch, "future-real")
    run = generation_service.run_daily_generation(
        target_date=DAY, provider_name="future-real", signs=["aries"]
    )
    assert run.status == "failed"
    assert "Publication policy" in GenerationItem.query.one().error_message
    assert GenerationAttempt.query.one().status == "failed"
    assert Forecast.query.count() == 0


def test_final_guard_uses_captured_adapter_identity_not_result_metadata(app, monkeypatch):
    class MisleadingStub(StubHoroscopeProvider):
        def generate(self, request):
            # Start locally, then require production policy at persistence.
            production(app, monkeypatch)
            self.name = "openai"
            return ProviderResult(text="Спокойный день.", provider="openai", model_name="gpt-test")

    monkeypatch.setitem(PROVIDERS, "stub", ProviderDefinition(MisleadingStub, True, False))
    run = generation_service.run_daily_generation(target_date=DAY, provider_name="stub", signs=["aries"])
    assert run.status == "failed"
    assert "forbids provider 'stub'" in GenerationItem.query.one().error_message
    assert Forecast.query.count() == 0


def test_defaults_preserve_local_development(monkeypatch):
    import runpy
    import app.config as config_module

    monkeypatch.delenv("APP_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("PRODUCTION_PUBLICATION_PROVIDERS", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    defaults = runpy.run_path(config_module.__file__)["Config"]
    assert defaults.APP_DEPLOYMENT_MODE == "development"
    assert defaults.PRODUCTION_PUBLICATION_PROVIDERS == "openai"


@pytest.mark.parametrize("mode", ["", "prod", "staging", None])
def test_invalid_mode_fails_at_startup_and_publication(app, monkeypatch, mode):
    monkeypatch.setattr(Config, "APP_DEPLOYMENT_MODE", mode)
    with pytest.raises(PublicationPolicyError, match="APP_DEPLOYMENT_MODE"):
        create_app()
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", mode)
    with pytest.raises(PublicationPolicyError, match="APP_DEPLOYMENT_MODE"):
        save_forecast("aries", DAY, "Must not publish")
    assert Forecast.query.count() == 0


def test_unknown_allowlist_provider_fails_configuration(app, monkeypatch):
    monkeypatch.setattr(Config, "PRODUCTION_PUBLICATION_PROVIDERS", "typo")
    with pytest.raises(PublicationPolicyError, match="Unknown PRODUCTION_PUBLICATION_PROVIDERS"):
        create_app()

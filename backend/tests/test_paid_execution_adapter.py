"""Final transport-boundary regressions; no real SDK or network requests."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.models import Forecast, GenerationAttempt, GenerationItem
from app.providers import OpenAIHoroscopeProvider, ProviderRequest
import app.services.generation_service as generation_service
from paid_execution_policy import PaidExecutionDenied

SETTING = "GENERATION_PAID_EXECUTION_ENABLED"


@pytest.fixture(autouse=True)
def deny_real_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Adapter gate tests must never perform real HTTP")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def request():
    return ProviderRequest(
        target_date=date(2026, 11, 14), locale="ru", forecast_type="daily",
        messages=[{"role": "user", "content": "Return a short forecast."}],
    )


def fake_client():
    return SimpleNamespace(responses=SimpleNamespace(
        create=Mock(side_effect=AssertionError("Unexpected transport"))
    ))


@pytest.mark.parametrize("setting", [None, "0", "invalid", "true", " 1"])
def test_direct_adapter_denied_before_client_use_even_with_spoofed_name(
    app, monkeypatch, setting
):
    if setting is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, setting)
    # Neither a Flask config snapshot nor mutable adapter metadata may enable it.
    monkeypatch.setitem(app.config, SETTING, True)
    client = fake_client()
    provider = OpenAIHoroscopeProvider(api_key="test-key", client=client)
    provider.name = "stub"
    get_client = Mock(side_effect=AssertionError("Unexpected client access"))
    monkeypatch.setattr(provider, "_get_client", get_client)
    with pytest.raises(PaidExecutionDenied) as error:
        provider.generate(request())
    assert error.value.retryable is False
    get_client.assert_not_called()
    client.responses.create.assert_not_called()


def switching_provider(monkeypatch):
    monkeypatch.setenv(SETTING, "1")
    client = fake_client()
    provider = OpenAIHoroscopeProvider(api_key="test-key", client=client)
    def get_client():
        monkeypatch.setenv(SETTING, "0")
        return client
    monkeypatch.setattr(provider, "_get_client", get_client)
    return provider, client


def test_adapter_rechecks_gate_immediately_before_sdk_request(monkeypatch):
    provider, client = switching_provider(monkeypatch)
    with pytest.raises(PaidExecutionDenied):
        provider.generate(request())
    client.responses.create.assert_not_called()


def test_post_preflight_denial_records_one_honest_nonretryable_attempt(app, monkeypatch):
    provider, client = switching_provider(monkeypatch)
    monkeypatch.setattr(generation_service, "get_horoscope_provider", lambda _: provider)
    with app.app_context():
        run = generation_service.run_daily_generation(
            target_date=date(2026, 11, 14), provider_name="openai",
            signs=["aries"], max_attempts=3,
        )
        assert run.status == "failed"
        assert run.failed_items == 1
        item = GenerationItem.query.one()
        attempt = GenerationAttempt.query.one()
        assert item.status == "failed"
        assert item.forecast_id is None
        assert attempt.status == "failed"
        assert attempt.error_type == "PaidExecutionDenied"
        assert attempt.finished_at is not None
        assert "Paid execution denied" in attempt.error_message
        assert Forecast.query.count() == 0
    client.responses.create.assert_not_called()

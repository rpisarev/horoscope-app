import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.providers import GenerationProviderError, OpenAIHoroscopeProvider, ProviderRequest
from app.providers.factory import get_horoscope_provider
from app.providers.openai_provider import _is_retryable_openai_error


SAFE_FORECAST_TEXT = (
    "Вас ждет спокойный и продуктивный день. "
    "Вам будет проще сосредоточиться на главном и не распыляться. "
    "Ваше внимание к деталям поможет избежать лишней суеты. "
    "Вечером стоит выбрать отдых, который действительно восстанавливает силы."
)


class FakeOpenAIResponse:
    def __init__(self, output_text=None, payload=None):
        self.output_text = output_text
        self._payload = payload or {
            "id": "resp_test",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": output_text,
                        }
                    ],
                }
            ],
        }

    def model_dump(self, mode="json"):
        return self._payload


class FakeResponsesResource:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.responses = FakeResponsesResource(response)


def _prompt_version(model_name="stub"):
    return SimpleNamespace(
        key="daily-ru-v1",
        model_name=model_name,
    )


def _provider_request(
    *,
    output_schema=None,
    model_name="stub",
    messages=None,
):
    target_day = date(2026, 5, 13)

    return ProviderRequest(
        target_date=target_day,
        locale="ru",
        forecast_type="daily",
        prompt_version=_prompt_version(model_name=model_name),
        messages=messages
        or [
            {
                "role": "system",
                "content": (
                    "Ты пишешь короткие ежедневные персональные прогнозы. "
                    "Не называй конкретные знаки зодиака и не упоминай дату."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Напиши короткий ежедневный прогноз для читателя. "
                    "Верни только JSON согласно схеме."
                ),
            },
        ],
        output_schema=output_schema
        or {
            "type": "object",
            "required": ["text"],
            "additionalProperties": False,
            "properties": {
                "title": {"type": ["string", "null"]},
                "text": {"type": "string"},
            },
        },
        metadata={
            "sign_key": "aries",
            "target_date": target_day.isoformat(),
            "locale": "ru",
            "forecast_type": "daily",
            "prompt_version": "daily-ru-v1",
        },
        prompt_variables={
            "locale": "ru",
            "forecast_type": "daily",
            "output_language": "русский",
            "address_style": "уважительное обращение на Вы",
            "sentence_count": "4-5",
        },
    )


def test_factory_returns_openai_provider(monkeypatch):
    monkeypatch.setenv("HOROSCOPE_PROVIDER", "openai")

    provider = get_horoscope_provider()

    assert isinstance(provider, OpenAIHoroscopeProvider)
    assert provider.name == "openai"


def test_openai_provider_requires_api_key_without_injected_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = OpenAIHoroscopeProvider(api_key=None, client=None)

    with pytest.raises(GenerationProviderError, match="OPENAI_API_KEY") as exc_info:
        provider.generate(_provider_request())

    assert exc_info.value.retryable is False


def test_openai_provider_generates_provider_result_from_structured_response(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    response_body = {
        "title": None,
        "text": SAFE_FORECAST_TEXT,
    }
    fake_response = FakeOpenAIResponse(output_text=json.dumps(response_body))
    fake_client = FakeOpenAIClient(fake_response)

    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-test",
        client=fake_client,
    )

    result = provider.generate(_provider_request(model_name="stub"))

    assert result.provider == "openai"
    assert result.model_name == "gpt-test"
    assert result.title is None
    assert result.text == SAFE_FORECAST_TEXT
    assert result.payload == response_body
    assert result.raw_response == json.dumps(response_body)

    assert len(fake_client.responses.calls) == 1

    openai_call = fake_client.responses.calls[0]

    assert openai_call["model"] == "gpt-test"
    assert openai_call["max_output_tokens"] == 500
    assert "Ты пишешь короткие" in openai_call["instructions"]
    assert "Напиши короткий" in openai_call["input"]

    text_format = openai_call["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "horoscope_forecast"
    assert text_format["strict"] is True
    assert text_format["schema"]["type"] == "object"
    assert text_format["schema"]["additionalProperties"] is False
    assert text_format["schema"]["required"] == ["text", "title"]

    request_payload = result.request_payload

    assert request_payload["provider_request"]["metadata"]["sign_key"] == "aries"
    assert request_payload["provider_request"]["metadata"]["target_date"] == "2026-05-13"
    assert request_payload["openai_request"]["model"] == "gpt-test"

    serialized_request_payload = json.dumps(request_payload, ensure_ascii=False).lower()

    assert "test-key" not in serialized_request_payload
    assert "api_key" not in serialized_request_payload

    provider_facing_text = (
        openai_call["instructions"] + "\n" + openai_call["input"]
    ).lower()

    assert "aries" not in provider_facing_text
    assert "овен" not in provider_facing_text
    assert "2026-05-13" not in provider_facing_text


def test_openai_provider_uses_env_model_before_prompt_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-env-model")

    response_body = {
        "title": "Тестовый заголовок",
        "text": SAFE_FORECAST_TEXT,
    }
    fake_client = FakeOpenAIClient(
        FakeOpenAIResponse(output_text=json.dumps(response_body))
    )

    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-provider-default",
        client=fake_client,
    )

    result = provider.generate(_provider_request(model_name="gpt-prompt-model"))

    assert result.model_name == "gpt-env-model"
    assert result.title == "Тестовый заголовок"
    assert fake_client.responses.calls[0]["model"] == "gpt-env-model"


def test_openai_provider_rejects_malformed_json_as_retryable(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    fake_client = FakeOpenAIClient(FakeOpenAIResponse(output_text="not-json"))
    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-test",
        client=fake_client,
    )

    with pytest.raises(GenerationProviderError, match="malformed JSON") as exc_info:
        provider.generate(_provider_request())

    assert exc_info.value.retryable is True


def test_openai_provider_rejects_empty_text_as_retryable(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    fake_client = FakeOpenAIClient(
        FakeOpenAIResponse(output_text=json.dumps({"title": None, "text": ""}))
    )
    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-test",
        client=fake_client,
    )

    with pytest.raises(GenerationProviderError, match="non-empty text") as exc_info:
        provider.generate(_provider_request())

    assert exc_info.value.retryable is True


def test_openai_provider_rejects_refusal_as_non_retryable(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    refusal_payload = {
        "id": "resp_refusal",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "refusal",
                        "refusal": "Cannot comply with this request.",
                    }
                ],
            }
        ],
    }
    fake_client = FakeOpenAIClient(
        FakeOpenAIResponse(output_text=None, payload=refusal_payload)
    )
    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-test",
        client=fake_client,
    )

    with pytest.raises(GenerationProviderError, match="refused") as exc_info:
        provider.generate(_provider_request())

    assert exc_info.value.retryable is False


def test_openai_provider_rejects_invalid_output_schema_as_non_retryable(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    fake_client = FakeOpenAIClient(
        FakeOpenAIResponse(output_text=json.dumps({"text": SAFE_FORECAST_TEXT}))
    )
    provider = OpenAIHoroscopeProvider(
        api_key="test-key",
        model_name="gpt-test",
        client=fake_client,
    )

    with pytest.raises(GenerationProviderError, match="type='object'") as exc_info:
        provider.generate(
            _provider_request(
                output_schema={
                    "type": "array",
                    "items": {"type": "string"},
                }
            )
        )

    assert exc_info.value.retryable is False
    assert fake_client.responses.calls == []


def test_openai_error_classification():
    assert (
        _is_retryable_openai_error(error_name="APIConnectionError", status_code=None)
        is True
    )
    assert (
        _is_retryable_openai_error(error_name="APITimeoutError", status_code=None)
        is True
    )
    assert _is_retryable_openai_error(error_name="RateLimitError", status_code=429) is True
    assert (
        _is_retryable_openai_error(error_name="InternalServerError", status_code=500)
        is True
    )
    assert (
        _is_retryable_openai_error(error_name="AuthenticationError", status_code=401)
        is False
    )
    assert (
        _is_retryable_openai_error(error_name="PermissionDeniedError", status_code=403)
        is False
    )
    assert (
        _is_retryable_openai_error(error_name="BadRequestError", status_code=400)
        is False
    )
    assert (
        _is_retryable_openai_error(error_name="UnexpectedOpenAIError", status_code=503)
        is True
    )
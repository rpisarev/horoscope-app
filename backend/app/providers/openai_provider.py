from __future__ import annotations

import copy
import json
import os
from typing import Any

from openai import OpenAI, OpenAIError

from .base import GenerationProviderError, ProviderRequest, ProviderResult

DEFAULT_OPENAI_MODEL = "gpt-5.2"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 500

RETRYABLE_OPENAI_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
}

NON_RETRYABLE_OPENAI_ERROR_NAMES = {
    "AuthenticationError",
    "PermissionDeniedError",
    "BadRequestError",
    "NotFoundError",
    "UnprocessableEntityError",
}

FALLBACK_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "text"],
    "properties": {
        "title": {"type": ["string", "null"]},
        "text": {"type": "string"},
    },
}


class OpenAIHoroscopeProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.model_name = (
            model_name
            or os.getenv("OPENAI_MODEL")
            or DEFAULT_OPENAI_MODEL
        ).strip()
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _get_float_env("OPENAI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else _get_int_env("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
        )
        self._client = client

    def generate(self, request: ProviderRequest) -> ProviderResult:
        if not self.api_key and self._client is None:
            raise GenerationProviderError(
                "OPENAI_API_KEY is required when HOROSCOPE_PROVIDER=openai.",
                retryable=False,
            )

        effective_model = self._resolve_model_name(request)
        instructions, input_text = _split_messages(request.messages)
        text_format = _build_text_format(request.output_schema)

        openai_request_payload = {
            "model": effective_model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": text_format,
            },
        }

        try:
            response = self._get_client().responses.create(**openai_request_payload)
        except OpenAIError as exc:
            raise _to_generation_provider_error(exc) from exc

        response_payload = _response_to_payload(response)
        refusal = _extract_refusal(response_payload)
        if refusal:
            raise GenerationProviderError(
                f"OpenAI refused to generate a forecast: {refusal}",
                retryable=False,
            )

        raw_text = _extract_output_text(response, response_payload)
        parsed_payload = _parse_json_response(raw_text)

        forecast_text = str(parsed_payload.get("text") or "").strip()
        if not forecast_text:
            raise GenerationProviderError(
                "OpenAI returned a structured response without non-empty text.",
                retryable=True,
            )

        title_value = parsed_payload.get("title")
        title = str(title_value).strip() if title_value not in (None, "") else None

        return ProviderResult(
            title=title,
            text=forecast_text,
            payload=parsed_payload,
            request_payload={
                "provider_request": request.to_payload(),
                "openai_request": openai_request_payload,
            },
            response_payload={
                "parsed": parsed_payload,
                "openai_response": response_payload,
            },
            raw_response=raw_text,
            provider=self.name,
            model_name=effective_model,
        )

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
            )
        return self._client

    def _resolve_model_name(self, request: ProviderRequest) -> str:
        env_model = os.getenv("OPENAI_MODEL")
        if env_model and env_model.strip():
            return env_model.strip()

        prompt_model = getattr(request.prompt_version, "model_name", None)
        if prompt_model and str(prompt_model).strip().lower() != "stub":
            return str(prompt_model).strip()

        return self.model_name


def _split_messages(messages: list[dict[str, str]]) -> tuple[str, str]:
    system_parts: list[str] = []
    input_parts: list[str] = []

    for message in messages:
        role = (message.get("role") or "user").strip().lower()
        content = (message.get("content") or "").strip()

        if not content:
            continue

        if role in {"system", "developer"}:
            system_parts.append(content)
        else:
            input_parts.append(content)

    instructions = "\n\n".join(system_parts).strip()
    input_text = "\n\n".join(input_parts).strip()

    if not input_text:
        input_text = "Generate the forecast according to the instructions."

    return instructions, input_text


def _build_text_format(output_schema: dict[str, Any] | None) -> dict[str, Any]:
    schema = _normalize_output_schema(output_schema)

    return {
        "type": "json_schema",
        "name": "horoscope_forecast",
        "strict": True,
        "schema": schema,
    }


def _normalize_output_schema(output_schema: dict[str, Any] | None) -> dict[str, Any]:
    schema = copy.deepcopy(output_schema or FALLBACK_OUTPUT_SCHEMA)

    if not isinstance(schema, dict):
        raise GenerationProviderError(
            "Prompt output_schema must be a JSON object schema.",
            retryable=False,
        )

    if schema.get("type") != "object":
        raise GenerationProviderError(
            "Prompt output_schema must have type='object'.",
            retryable=False,
        )

    properties = schema.get("properties")
    if not isinstance(properties, dict) or "text" not in properties:
        raise GenerationProviderError(
            "Prompt output_schema must define a 'text' property.",
            retryable=False,
        )

    schema["additionalProperties"] = False

    # Strict structured outputs work best when every declared field is required.
    # Optional values should be represented as nullable fields.
    schema["required"] = sorted(properties.keys())

    title_schema = properties.get("title")
    if isinstance(title_schema, dict):
        field_type = title_schema.get("type")
        if field_type == "string":
            title_schema["type"] = ["string", "null"]

    return schema


def _parse_json_response(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        preview = raw_text[:300].replace("\n", "\\n")
        raise GenerationProviderError(
            f"OpenAI returned malformed JSON: {preview}",
            retryable=True,
        ) from exc

    if not isinstance(parsed, dict):
        raise GenerationProviderError(
            "OpenAI returned JSON, but it was not an object.",
            retryable=True,
        )

    return parsed


def _extract_output_text(response: Any, response_payload: dict[str, Any]) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    collected: list[str] = []
    output_items = response_payload.get("output") or []

    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict):
                continue

            content_items = item.get("content") or []
            if not isinstance(content_items, list):
                continue

            for content in content_items:
                if not isinstance(content, dict):
                    continue

                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    collected.append(text.strip())

    if collected:
        return "\n".join(collected).strip()

    raise GenerationProviderError(
        "OpenAI response did not contain output_text.",
        retryable=True,
    )


def _extract_refusal(response_payload: dict[str, Any]) -> str | None:
    output_items = response_payload.get("output") or []

    if not isinstance(output_items, list):
        return None

    for item in output_items:
        if not isinstance(item, dict):
            continue

        content_items = item.get("content") or []
        if not isinstance(content_items, list):
            continue

        for content in content_items:
            if not isinstance(content, dict):
                continue

            refusal = content.get("refusal")
            if isinstance(refusal, str) and refusal.strip():
                return refusal.strip()

            if content.get("type") == "refusal":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

    return None


def _response_to_payload(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")

    if isinstance(response, dict):
        return response

    return {
        "repr": repr(response),
    }


def _to_generation_provider_error(exc: OpenAIError) -> GenerationProviderError:
    error_name = exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)

    retryable = _is_retryable_openai_error(
        error_name=error_name,
        status_code=status_code,
    )

    return GenerationProviderError(
        f"OpenAI provider error [{error_name}]: {exc}",
        retryable=retryable,
    )


def _is_retryable_openai_error(
    *,
    error_name: str,
    status_code: int | None,
) -> bool:
    if error_name in RETRYABLE_OPENAI_ERROR_NAMES:
        return True

    if error_name in NON_RETRYABLE_OPENAI_ERROR_NAMES:
        return False

    if status_code is not None:
        return status_code in {408, 409, 429} or status_code >= 500

    return True


def _get_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise GenerationProviderError(
            f"{name} must be a number.",
            retryable=False,
        ) from exc

    if value <= 0:
        raise GenerationProviderError(
            f"{name} must be greater than 0.",
            retryable=False,
        )

    return value


def _get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise GenerationProviderError(
            f"{name} must be an integer.",
            retryable=False,
        ) from exc

    if value <= 0:
        raise GenerationProviderError(
            f"{name} must be greater than 0.",
            retryable=False,
        )

    return value
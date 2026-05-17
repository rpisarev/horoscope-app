from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from string import Formatter
from typing import Any

from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE, DEFAULT_PROMPT_VERSION_KEY
from ..models import PromptVersion
from ..providers.base import ProviderRequest


SUPPORTED_PROMPT_VARIABLES = frozenset(
    {
        "locale",
        "forecast_type",
        "output_language",
        "address_style",
        "sentence_count",
    }
)

OUTPUT_LANGUAGE_BY_LOCALE = {
    "ru": "русский",
}

ADDRESS_STYLE_BY_LOCALE = {
    "ru": "уважительное обращение на Вы с формами Вас, Вам, Ваш, Ваши",
}

SENTENCE_COUNT_BY_FORECAST_TYPE = {
    "daily": "4-5",
}


class PromptRenderingError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_version: PromptVersion
    system_prompt: str
    user_prompt: str
    messages: list[dict[str, str]]
    output_schema: dict[str, Any] | None
    model_name: str | None
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_request_payload(self) -> dict[str, Any]:
        return {
            "prompt_version": self.prompt_version.key,
            "model_name": self.model_name,
            "messages": self.messages,
            "output_schema": self.output_schema,
            "prompt_variables": self.variables,
            "metadata": self.metadata,
        }


def get_prompt_version(
    prompt_version_key: str | None = None,
    *,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> PromptVersion | None:
    if prompt_version_key:
        prompt_version = PromptVersion.query.filter_by(key=prompt_version_key).first()
        if prompt_version:
            return prompt_version

    active_prompt_version = PromptVersion.query.filter_by(
        locale=locale,
        forecast_type=forecast_type,
        is_active=True,
    ).first()

    if active_prompt_version:
        return active_prompt_version

    return PromptVersion.query.filter_by(
        key=DEFAULT_PROMPT_VERSION_KEY,
    ).first()


def build_prompt_variables(
    *,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> dict[str, Any]:
    return {
        "locale": locale,
        "forecast_type": forecast_type,
        "output_language": OUTPUT_LANGUAGE_BY_LOCALE.get(locale, locale),
        "address_style": ADDRESS_STYLE_BY_LOCALE.get(locale, "direct respectful address"),
        "sentence_count": SENTENCE_COUNT_BY_FORECAST_TYPE.get(forecast_type, "4-5"),
    }


def render_prompt_template(template: str, variables: dict[str, Any]) -> str:
    _validate_template_variables(template)

    try:
        rendered = template.format(**variables)
    except KeyError as exc:
        field_name = str(exc).strip("'")
        raise PromptRenderingError(
            f"Prompt template contains unsupported placeholder: {field_name}"
        ) from exc

    rendered = rendered.strip()
    if not rendered:
        raise PromptRenderingError("Rendered prompt is empty.")

    return rendered


def build_rendered_prompt(
    *,
    prompt_version: PromptVersion | None,
    sign_key: str,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> RenderedPrompt:
    if not prompt_version:
        raise PromptRenderingError("Prompt version is required.")

    system_prompt = (prompt_version.system_prompt or "").strip()
    if not system_prompt:
        raise PromptRenderingError("System prompt is empty.")

    variables = build_prompt_variables(locale=locale, forecast_type=forecast_type)
    user_prompt = render_prompt_template(prompt_version.user_prompt_template, variables)

    metadata = {
        "sign_key": sign_key,
        "target_date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "prompt_version": prompt_version.key,
    }

    return RenderedPrompt(
        prompt_version=prompt_version,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        output_schema=prompt_version.output_schema,
        model_name=prompt_version.model_name,
        variables=variables,
        metadata=metadata,
    )


def build_provider_request(
    *,
    prompt_version: PromptVersion | None,
    sign_key: str,
    target_date: date,
    locale: str = DEFAULT_LOCALE,
    forecast_type: str = DEFAULT_FORECAST_TYPE,
) -> ProviderRequest:
    rendered_prompt = build_rendered_prompt(
        prompt_version=prompt_version,
        sign_key=sign_key,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    )

    return ProviderRequest(
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
        prompt_version=prompt_version,
        messages=rendered_prompt.messages,
        output_schema=rendered_prompt.output_schema,
        metadata=rendered_prompt.metadata,
        prompt_variables=rendered_prompt.variables,
    )


def _validate_template_variables(template: str) -> None:
    formatter = Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if not field_name:
            continue

        root_field_name = field_name.split(".", 1)[0].split("[", 1)[0]
        if root_field_name not in SUPPORTED_PROMPT_VARIABLES:
            raise PromptRenderingError(
                f"Prompt template contains unsupported placeholder: {root_field_name}"
            )
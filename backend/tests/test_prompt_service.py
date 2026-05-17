from datetime import date

import pytest

from app.models import PromptVersion
from app.services.prompt_service import (
    PromptRenderingError,
    build_provider_request,
    build_rendered_prompt,
    build_prompt_variables,
    get_prompt_version,
    render_prompt_template,
)


def _message_content(messages):
    return "\n".join(message["content"] for message in messages)


def test_build_prompt_variables_are_sign_and_date_agnostic():
    variables = build_prompt_variables(locale="ru", forecast_type="daily")

    assert variables["output_language"] == "русский"
    assert "Вы" in variables["address_style"]
    assert variables["sentence_count"] == "4-5"
    assert "sign" not in variables
    assert "date" not in variables
    assert "target_date" not in variables


def test_render_prompt_template_accepts_only_supported_placeholders():
    rendered = render_prompt_template(
        "Язык: {output_language}. Объем: {sentence_count}.",
        {
            "output_language": "русский",
            "sentence_count": "4-5",
        },
    )

    assert rendered == "Язык: русский. Объем: 4-5."


@pytest.mark.parametrize("placeholder", ["sign", "sign_key", "date", "target_date"])
def test_render_prompt_template_rejects_sign_and_date_placeholders(placeholder):
    with pytest.raises(PromptRenderingError, match="unsupported placeholder"):
        render_prompt_template(
            f"Unsupported {{{placeholder}}}",
            build_prompt_variables(locale="ru", forecast_type="daily"),
        )


def test_build_rendered_prompt_does_not_expose_sign_or_date_in_messages(app):
    target_day = date(2026, 5, 13)

    with app.app_context():
        prompt_version = get_prompt_version(locale="ru", forecast_type="daily")
        rendered = build_rendered_prompt(
            prompt_version=prompt_version,
            sign_key="aries",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
        )

    content = _message_content(rendered.messages).lower()

    assert rendered.prompt_version.key == "daily-ru-v1"
    assert rendered.messages[0]["role"] == "system"
    assert rendered.messages[1]["role"] == "user"
    assert "aries" not in content
    assert "овен" not in content
    assert target_day.isoformat() not in content
    assert "{sign" not in content
    assert "{date" not in content
    assert rendered.metadata["sign_key"] == "aries"
    assert rendered.metadata["target_date"] == target_day.isoformat()


def test_build_rendered_prompt_rejects_legacy_sign_template():
    prompt_version = PromptVersion(
        key="legacy",
        locale="ru",
        forecast_type="daily",
        system_prompt="System prompt",
        user_prompt_template="Составь гороскоп для знака {sign} на дату {date}.",
        output_schema={"type": "object"},
        model_name="stub",
        is_active=True,
    )

    with pytest.raises(PromptRenderingError, match="unsupported placeholder"):
        build_rendered_prompt(
            prompt_version=prompt_version,
            sign_key="aries",
            target_date=date(2026, 5, 13),
            locale="ru",
            forecast_type="daily",
        )


def test_build_provider_request_keeps_sign_and_date_only_as_metadata(app):
    target_day = date(2026, 5, 13)

    with app.app_context():
        prompt_version = get_prompt_version(locale="ru", forecast_type="daily")
        request = build_provider_request(
            prompt_version=prompt_version,
            sign_key="taurus",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
        )

    payload = request.to_payload()
    content = _message_content(payload["messages"]).lower()

    assert payload["prompt_version"] == "daily-ru-v1"
    assert payload["metadata"]["sign_key"] == "taurus"
    assert payload["metadata"]["target_date"] == target_day.isoformat()
    assert payload["target_date"] == target_day.isoformat()
    assert "taurus" not in content
    assert "телец" not in content
    assert target_day.isoformat() not in content
    assert payload["output_schema"]["required"] == ["text"]
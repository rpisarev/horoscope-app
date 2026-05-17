from __future__ import annotations

from .constants import DEFAULT_FORECAST_TYPE, DEFAULT_LOCALE, DEFAULT_PROMPT_VERSION_KEY
from ..models import PromptVersion


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
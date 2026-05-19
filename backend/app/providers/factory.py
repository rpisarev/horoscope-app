from __future__ import annotations

import os

from .base import GenerationProviderError, HoroscopeProvider
from .openai_provider import OpenAIHoroscopeProvider
from .stub import StubHoroscopeProvider


def get_horoscope_provider(provider_name: str | None = None) -> HoroscopeProvider:
    name = (provider_name or os.getenv("HOROSCOPE_PROVIDER") or "stub").strip().lower()

    if name == "stub":
        return StubHoroscopeProvider()

    if name == "openai":
        return OpenAIHoroscopeProvider()

    if name in {"local", "local-llm", "local_llm"}:
        raise GenerationProviderError(
            f"Horoscope provider '{name}' is configured but not implemented yet.",
            retryable=False,
        )

    raise GenerationProviderError(
        f"Unknown horoscope provider '{name}'.",
        retryable=False,
    )
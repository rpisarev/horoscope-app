from __future__ import annotations

import os

from .base import GenerationProviderError, HoroscopeProvider
from .registry import PROVIDERS


def get_horoscope_provider(provider_name: str | None = None) -> HoroscopeProvider:
    name = (provider_name or os.getenv("HOROSCOPE_PROVIDER") or "stub").strip().lower()

    if name in PROVIDERS:
        return PROVIDERS[name].factory()

    if name in {"local", "local-llm", "local_llm"}:
        raise GenerationProviderError(
            f"Horoscope provider '{name}' is configured but not implemented yet.",
            retryable=False,
        )

    raise GenerationProviderError(
        f"Unknown horoscope provider '{name}'.",
        retryable=False,
    )

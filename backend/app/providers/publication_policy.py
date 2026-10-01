from __future__ import annotations

from typing import Mapping, Any

from flask import current_app

from .base import GenerationProviderError
from .registry import PROVIDERS


class PublicationPolicyError(GenerationProviderError):
    """A non-retryable publication authorization/configuration failure."""


def publication_settings(config: Mapping[str, Any]) -> tuple[str, frozenset[str]]:
    mode = config.get("APP_DEPLOYMENT_MODE")
    if not isinstance(mode, str) or mode.strip().lower() not in {
        "development", "test", "production"
    }:
        raise PublicationPolicyError(
            "APP_DEPLOYMENT_MODE must be development, test, or production."
        )

    raw_providers = config.get("PRODUCTION_PUBLICATION_PROVIDERS")
    if not isinstance(raw_providers, str):
        raise PublicationPolicyError(
            "PRODUCTION_PUBLICATION_PROVIDERS must be a comma-separated provider list."
        )
    allowed = frozenset(name.strip().lower() for name in raw_providers.split(",") if name.strip())
    unknown = allowed.difference(PROVIDERS)
    if unknown:
        raise PublicationPolicyError(
            "Unknown PRODUCTION_PUBLICATION_PROVIDERS: " + ", ".join(sorted(unknown))
        )
    return mode.strip().lower(), allowed


def require_publication_provider(provider_name: str | None) -> None:
    mode, allowed = publication_settings(current_app.config)
    if mode != "production":
        return

    # This identity must come from the caller's selected execution adapter,
    # never from ProviderResult.provider or a forecast's source/model fields.
    definition = PROVIDERS.get(provider_name)
    if (
        definition is None
        or definition.development_only
        or not definition.production_publication_capable
        or provider_name not in allowed
    ):
        raise PublicationPolicyError(
            f"Publication policy forbids provider {provider_name!r} in production; "
            "an explicitly identified, approved real provider is required."
        )

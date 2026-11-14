from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import HoroscopeProvider
from .openai_provider import OpenAIHoroscopeProvider
from .stub import StubHoroscopeProvider


@dataclass(frozen=True)
class ProviderDefinition:
    factory: Callable[[], HoroscopeProvider]
    development_only: bool
    production_publication_capable: bool


# Registry keys are provider identities, independent of model names.
PROVIDERS = {
    "stub": ProviderDefinition(StubHoroscopeProvider, True, False),
    "openai": ProviderDefinition(OpenAIHoroscopeProvider, False, True),
}

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


class GenerationProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderRequest:
    target_date: date
    locale: str
    forecast_type: str
    prompt_version: Any | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date.isoformat(),
            "locale": self.locale,
            "forecast_type": self.forecast_type,
            "prompt_version": self.prompt_version.key if self.prompt_version else None,
        }


@dataclass(frozen=True)
class ProviderResult:
    text: str
    title: str | None = None
    payload: dict[str, Any] | None = None
    request_payload: dict[str, Any] = field(default_factory=dict)
    response_payload: dict[str, Any] = field(default_factory=dict)
    raw_response: str | None = None
    provider: str = "unknown"
    model_name: str | None = None


class HoroscopeProvider(Protocol):
    name: str
    model_name: str

    def generate(self, request: ProviderRequest) -> ProviderResult:
        ...
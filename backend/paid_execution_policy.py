"""Process-wide paid-execution gate, independent of Flask and provider adapters.

Importing this module never loads dotenv, application configuration, or an SDK.
The process environment is authoritative at each execution boundary; a Flask
configuration snapshot or a caller's local opt-in cannot override a denial.
"""

from __future__ import annotations

import os


PAID_EXECUTION_ENV = "GENERATION_PAID_EXECUTION_ENABLED"
PAID_PROVIDERS = frozenset({"openai"})


class PaidExecutionDenied(RuntimeError):
    """A nonretryable denial before paid transport is permitted."""

    retryable = False


def paid_execution_enabled() -> bool:
    """Only the exact string '1' enables paid execution; all else denies."""
    return os.environ.get(PAID_EXECUTION_ENV) == "1"


def require_paid_execution(provider_name: str | None) -> None:
    """Require the global opt-in for a known paid execution provider.

    Callers supply selected execution identity, never returned source/model
    metadata. Paid adapters must use their literal canonical provider identity.
    Stub and unregistered development fakes retain their existing behavior;
    provider selection and publication authorization remain separate policies.
    """
    name = (provider_name or "").strip().lower()
    if name in PAID_PROVIDERS and not paid_execution_enabled():
        raise PaidExecutionDenied(
            f"Paid execution denied for provider={name}: "
            f"{PAID_EXECUTION_ENV} must be exactly '1'. "
            "Local OpenAI opt-ins cannot override this global gate."
        )

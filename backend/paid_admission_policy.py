"""Temporary fail-closed boundary while atomic paid admission is unavailable.

No Flask, dotenv, database or SDK imports. This module never grants transport
authority: SAFE-001 opt-in remains independently necessary, never sufficient.
"""

from paid_execution_policy import PAID_PROVIDERS, PaidExecutionDenied, require_paid_execution


class PaidAdmissionUnavailable(PaidExecutionDenied):
    """Nonretryable denial; request reservation/admission is not implemented."""

    code = "paid_admission_unavailable"


def require_paid_admission(provider_name: str | None) -> None:
    """Check SAFE-001 first, then deny every known paid provider unconditionally.

    There is deliberately no environment, caller-context or test-mode override.
    Paid adapters must pass their literal canonical identity at the boundary.
    """
    require_paid_execution(provider_name)
    name = (provider_name or "").strip().lower()
    if name in PAID_PROVIDERS:
        raise PaidAdmissionUnavailable(
            "Paid execution unavailable: atomic request admission is not implemented."
        )

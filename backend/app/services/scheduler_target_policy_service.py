from __future__ import annotations

from datetime import date, timedelta

SCHEDULER_TARGET_POLICY_TODAY = "today"
SCHEDULER_TARGET_POLICY_TOMORROW = "tomorrow"
SCHEDULER_TARGET_POLICY_TODAY_AND_TOMORROW = "today_and_tomorrow"
SCHEDULER_TARGET_POLICY_ROLLING = "rolling"

DEFAULT_SCHEDULED_TARGET_POLICY = SCHEDULER_TARGET_POLICY_TODAY_AND_TOMORROW
DEFAULT_SCHEDULED_ROLLING_DAYS = 2

SUPPORTED_SCHEDULER_TARGET_POLICIES = {
    SCHEDULER_TARGET_POLICY_TODAY,
    SCHEDULER_TARGET_POLICY_TOMORROW,
    SCHEDULER_TARGET_POLICY_TODAY_AND_TOMORROW,
    SCHEDULER_TARGET_POLICY_ROLLING,
}


class SchedulerTargetPolicyError(ValueError):
    pass


def normalize_scheduler_target_policy(policy: str | None) -> str:
    normalized = (policy or DEFAULT_SCHEDULED_TARGET_POLICY).strip().lower()
    normalized = normalized.replace("-", "_")

    if normalized not in SUPPORTED_SCHEDULER_TARGET_POLICIES:
        supported = ", ".join(sorted(SUPPORTED_SCHEDULER_TARGET_POLICIES))
        raise SchedulerTargetPolicyError(
            f"Unsupported scheduler target policy: {policy!r}. "
            f"Supported policies: {supported}."
        )

    return normalized


def validate_scheduled_rolling_days(rolling_days: int | None) -> int:
    if rolling_days is None:
        return DEFAULT_SCHEDULED_ROLLING_DAYS

    try:
        parsed = int(rolling_days)
    except (TypeError, ValueError) as exc:
        raise SchedulerTargetPolicyError(
            "GENERATION_SCHEDULED_ROLLING_DAYS must be an integer."
        ) from exc

    if parsed < 1 or parsed > 366:
        raise SchedulerTargetPolicyError(
            "GENERATION_SCHEDULED_ROLLING_DAYS must be between 1 and 366."
        )

    return parsed


def resolve_scheduler_target_dates(
    *,
    base_date: date,
    policy: str | None = None,
    rolling_days: int | None = None,
) -> list[date]:
    normalized_policy = normalize_scheduler_target_policy(policy)
    normalized_rolling_days = validate_scheduled_rolling_days(rolling_days)

    if normalized_policy == SCHEDULER_TARGET_POLICY_TODAY:
        return [base_date]

    if normalized_policy == SCHEDULER_TARGET_POLICY_TOMORROW:
        return [base_date + timedelta(days=1)]

    if normalized_policy == SCHEDULER_TARGET_POLICY_TODAY_AND_TOMORROW:
        return [
            base_date,
            base_date + timedelta(days=1),
        ]

    if normalized_policy == SCHEDULER_TARGET_POLICY_ROLLING:
        return [
            base_date + timedelta(days=offset)
            for offset in range(normalized_rolling_days)
        ]

    raise SchedulerTargetPolicyError(
        f"Unsupported scheduler target policy: {normalized_policy!r}."
    )
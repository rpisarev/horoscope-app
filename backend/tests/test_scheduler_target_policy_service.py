from datetime import date

import pytest

from app.services.scheduler_target_policy_service import (
    DEFAULT_SCHEDULED_ROLLING_DAYS,
    DEFAULT_SCHEDULED_TARGET_POLICY,
    SchedulerTargetPolicyError,
    normalize_scheduler_target_policy,
    resolve_scheduler_target_dates,
    validate_scheduled_rolling_days,
)


def test_default_scheduler_target_policy_is_today_and_tomorrow():
    assert DEFAULT_SCHEDULED_TARGET_POLICY == "today_and_tomorrow"
    assert DEFAULT_SCHEDULED_ROLLING_DAYS == 2


def test_normalize_scheduler_target_policy_accepts_dash_alias():
    assert normalize_scheduler_target_policy("today-and-tomorrow") == "today_and_tomorrow"


def test_resolve_scheduler_target_dates_defaults_to_today_and_tomorrow():
    assert resolve_scheduler_target_dates(base_date=date(2026, 6, 1)) == [
        date(2026, 6, 1),
        date(2026, 6, 2),
    ]


def test_resolve_scheduler_target_dates_today():
    assert resolve_scheduler_target_dates(
        base_date=date(2026, 6, 1),
        policy="today",
    ) == [date(2026, 6, 1)]


def test_resolve_scheduler_target_dates_tomorrow():
    assert resolve_scheduler_target_dates(
        base_date=date(2026, 6, 1),
        policy="tomorrow",
    ) == [date(2026, 6, 2)]


def test_resolve_scheduler_target_dates_today_and_tomorrow():
    assert resolve_scheduler_target_dates(
        base_date=date(2026, 6, 1),
        policy="today_and_tomorrow",
    ) == [
        date(2026, 6, 1),
        date(2026, 6, 2),
    ]


def test_resolve_scheduler_target_dates_rolling():
    assert resolve_scheduler_target_dates(
        base_date=date(2026, 6, 1),
        policy="rolling",
        rolling_days=4,
    ) == [
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
        date(2026, 6, 4),
    ]


def test_resolve_scheduler_target_dates_rejects_unknown_policy():
    with pytest.raises(SchedulerTargetPolicyError) as exc_info:
        resolve_scheduler_target_dates(
            base_date=date(2026, 6, 1),
            policy="next_week",
        )

    assert "Unsupported scheduler target policy" in str(exc_info.value)


@pytest.mark.parametrize("rolling_days", [0, -1, 367])
def test_validate_scheduled_rolling_days_rejects_out_of_range_values(rolling_days):
    with pytest.raises(SchedulerTargetPolicyError):
        validate_scheduled_rolling_days(rolling_days)


def test_validate_scheduled_rolling_days_uses_default_for_none():
    assert validate_scheduled_rolling_days(None) == DEFAULT_SCHEDULED_ROLLING_DAYS
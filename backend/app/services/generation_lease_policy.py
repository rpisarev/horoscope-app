"""Pure lease timing primitives; no database, provider or background activity.

These helpers do not confer ownership or paid-execution authority. Database
renewal must independently compare the captured owner/epoch and running status.
There is deliberately no default timing policy or process-environment reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID


MAX_POLICY_SECONDS = 2_147_483_647  # PostgreSQL integer storage bound, not an SLO.
MAX_LEASE_EPOCH = 9_223_372_036_854_775_807


class LeasePolicyError(ValueError):
    """A malformed policy or timing snapshot cannot authorize lease renewal."""


def _positive_integer(value: int, *, maximum: int, name: str) -> None:
    if type(value) is not int or not 0 < value <= maximum:
        raise LeasePolicyError(f"{name} must be a positive bounded integer.")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LeasePolicyError("Lease times must be timezone-aware instants.")
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise LeasePolicyError("Lease time is outside the supported range.") from exc


def _plus_seconds(value: datetime, seconds: int) -> datetime:
    try:
        return value + timedelta(seconds=seconds)
    except OverflowError as exc:
        raise LeasePolicyError("Lease deadline is outside the supported range.") from exc


@dataclass(frozen=True)
class LeasePolicy:
    interval_seconds: int
    ttl_seconds: int
    max_duration_seconds: int

    def __post_init__(self) -> None:
        for name in ("interval_seconds", "ttl_seconds", "max_duration_seconds"):
            _positive_integer(getattr(self, name), maximum=MAX_POLICY_SECONDS, name=name)
        if not self.interval_seconds < self.ttl_seconds <= self.max_duration_seconds:
            raise LeasePolicyError("Lease policy requires interval < TTL <= duration.")


@dataclass(frozen=True)
class LeaseIdentity:
    """Captured at committed claim; never reconstruct epoch from a refreshed job."""

    job_id: int
    owner: str
    epoch: int
    execution_id: UUID

    def __post_init__(self) -> None:
        _positive_integer(self.job_id, maximum=MAX_LEASE_EPOCH, name="job_id")
        _positive_integer(self.epoch, maximum=MAX_LEASE_EPOCH, name="epoch")
        if not isinstance(self.owner, str) or not self.owner.strip() or len(self.owner) > 128:
            raise LeasePolicyError("Lease owner must be a nonempty bounded identifier.")
        if not isinstance(self.execution_id, UUID):
            raise LeasePolicyError("Lease execution identity must be a UUID.")


def captured_lease_identity(job) -> LeaseIdentity:
    """Read the unmapped claim handle, never reconstruct it from mutable columns."""
    identity = vars(job).get("_generation_lease_identity")
    if not isinstance(identity, LeaseIdentity):
        raise LeasePolicyError("Supply the lease identity captured at the committed claim.")
    return identity


@dataclass(frozen=True)
class LeaseTiming:
    heartbeat_at: datetime
    expires_at: datetime
    deadline_at: datetime
    ttl_seconds: int
    interval_seconds: int

    def __post_init__(self) -> None:
        for name in ("heartbeat_at", "expires_at", "deadline_at"):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        _positive_integer(self.ttl_seconds, maximum=MAX_POLICY_SECONDS, name="ttl_seconds")
        _positive_integer(self.interval_seconds, maximum=MAX_POLICY_SECONDS, name="interval_seconds")
        if not self.interval_seconds < self.ttl_seconds:
            raise LeasePolicyError("Lease interval must be less than TTL.")
        if not self.heartbeat_at < self.expires_at <= self.deadline_at:
            raise LeasePolicyError("Lease timing requires heartbeat < expiry <= deadline.")
        if self.expires_at - self.heartbeat_at > timedelta(seconds=self.ttl_seconds):
            raise LeasePolicyError("Lease expiry cannot exceed the stored TTL.")


@dataclass(frozen=True)
class RenewalPlan:
    status: str
    timing: LeaseTiming


def initial_lease_timing(policy: LeasePolicy, *, now: datetime) -> LeaseTiming:
    """Use a DB-clock instant under the claim lock; tests may supply a fake instant."""
    current = _utc(now)
    return LeaseTiming(
        heartbeat_at=current,
        expires_at=_plus_seconds(current, policy.ttl_seconds),
        deadline_at=_plus_seconds(current, policy.max_duration_seconds),
        ttl_seconds=policy.ttl_seconds,
        interval_seconds=policy.interval_seconds,
    )


def plan_lease_renewal(timing: LeaseTiming, *, now: datetime) -> RenewalPlan:
    """Calculate only; a 'renewed' plan is not evidence of a durable DB renewal."""
    current = _utc(now)
    if current < timing.heartbeat_at:
        return RenewalPlan("clock_regressed", timing)
    if current >= timing.deadline_at:
        return RenewalPlan("deadline", timing)
    if current >= timing.expires_at:
        return RenewalPlan("expired", timing)
    if current - timing.heartbeat_at < timedelta(seconds=timing.interval_seconds):
        return RenewalPlan("not_due", timing)

    # Compare the remaining duration before addition to avoid overflowing when
    # a valid snapshot is close to datetime.max and the deadline is nearer.
    remaining = timing.deadline_at - current
    expires_at = (
        timing.deadline_at
        if remaining <= timedelta(seconds=timing.ttl_seconds)
        else _plus_seconds(current, timing.ttl_seconds)
    )
    return RenewalPlan(
        "renewed",
        LeaseTiming(
            heartbeat_at=current,
            expires_at=expires_at,
            deadline_at=timing.deadline_at,
            ttl_seconds=timing.ttl_seconds,
            interval_seconds=timing.interval_seconds,
        ),
    )

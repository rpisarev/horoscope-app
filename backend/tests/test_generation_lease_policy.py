"""Database-free unit tests; the parent also runs these under STAB-007."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import socket
import sys
import unittest
from unittest.mock import patch
from uuid import UUID


_MODULE_PATH = Path(__file__).resolve().parents[1] / "app/services/generation_lease_policy.py"
_SPEC = importlib.util.spec_from_file_location("lease_policy_standalone_tests", _MODULE_PATH)
lease = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = lease
_SPEC.loader.exec_module(lease)


class LeasePolicyTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket", "create_connection", "getaddrinfo"):
            guard = patch.object(socket, name, side_effect=AssertionError("Network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.now = datetime(2026, 11, 15, 23, 59, 55, tzinfo=timezone.utc)
        # Fixture numbers exercise boundaries, not production recommendations.
        self.policy = lease.LeasePolicy(interval_seconds=3, ttl_seconds=10, max_duration_seconds=25)
        self.timing = lease.initial_lease_timing(self.policy, now=self.now)

    def test_initial_timing_crosses_utc_midnight_without_reset(self):
        self.assertEqual(self.timing.heartbeat_at, self.now)
        self.assertEqual(self.timing.expires_at, self.now + timedelta(seconds=10))
        self.assertEqual(self.timing.deadline_at, self.now + timedelta(seconds=25))
        self.assertEqual(self.timing.expires_at.day, 16)

    def test_policy_rejects_nonpositive_nonintegral_or_overflow_values(self):
        for field in ("interval_seconds", "ttl_seconds", "max_duration_seconds"):
            for bad in (0, -1, True, False, 1.5, "3", None, float("inf"), 2**31):
                with self.subTest(field=field, bad=bad):
                    values = dict(interval_seconds=3, ttl_seconds=10, max_duration_seconds=25)
                    values[field] = bad
                    with self.assertRaises(lease.LeasePolicyError):
                        lease.LeasePolicy(**values)

    def test_invalid_policy_relationships(self):
        for values in ((10, 10, 25), (11, 10, 25), (3, 10, 9)):
            with self.subTest(values=values), self.assertRaises(lease.LeasePolicyError):
                lease.LeasePolicy(*values)

    def test_duration_may_equal_ttl(self):
        timing = lease.initial_lease_timing(lease.LeasePolicy(3, 10, 10), now=self.now)
        self.assertEqual(timing.expires_at, timing.deadline_at)

    def test_no_policy_default(self):
        with self.assertRaises(TypeError):
            lease.LeasePolicy()

    def test_naive_times_rejected(self):
        naive = self.now.replace(tzinfo=None)
        with self.assertRaises(lease.LeasePolicyError):
            lease.initial_lease_timing(self.policy, now=naive)
        with self.assertRaises(lease.LeasePolicyError):
            lease.plan_lease_renewal(self.timing, now=naive)

    def test_non_datetime_rejected(self):
        with self.assertRaises(lease.LeasePolicyError):
            lease.initial_lease_timing(self.policy, now="2026-11-15")

    def test_non_utc_aware_instants_are_normalized(self):
        shifted = self.now.astimezone(timezone(timedelta(hours=2)))
        timing = lease.initial_lease_timing(self.policy, now=shifted)
        self.assertEqual(timing, self.timing)
        self.assertIs(timing.heartbeat_at.tzinfo, timezone.utc)

    def test_renewal_uses_instant_not_local_wall_clock(self):
        shifted = (self.now + timedelta(seconds=3)).astimezone(timezone(timedelta(hours=-5)))
        plan = lease.plan_lease_renewal(self.timing, now=shifted)
        self.assertEqual(plan.status, "renewed")
        self.assertEqual(plan.timing.heartbeat_at, self.now + timedelta(seconds=3))

    def test_early_repeated_calls_do_not_extend_ttl(self):
        for seconds in (0, 1, 2, 2.999):
            with self.subTest(seconds=seconds):
                plan = lease.plan_lease_renewal(self.timing, now=self.now + timedelta(seconds=seconds))
                self.assertEqual(plan.status, "not_due")
                self.assertIs(plan.timing, self.timing)

    def test_renewal_at_exact_cadence_extends_only_expiry(self):
        plan = lease.plan_lease_renewal(self.timing, now=self.now + timedelta(seconds=3))
        self.assertEqual(plan.status, "renewed")
        self.assertEqual(plan.timing.expires_at, self.now + timedelta(seconds=13))
        self.assertEqual(plan.timing.deadline_at, self.timing.deadline_at)
        self.assertEqual(plan.timing.ttl_seconds, self.policy.ttl_seconds)

    def test_renewal_just_before_expiry(self):
        plan = lease.plan_lease_renewal(self.timing, now=self.now + timedelta(seconds=9.999))
        self.assertEqual(plan.status, "renewed")

    def test_equality_and_later_are_expired(self):
        for seconds in (10, 11):
            with self.subTest(seconds=seconds):
                plan = lease.plan_lease_renewal(self.timing, now=self.now + timedelta(seconds=seconds))
                self.assertEqual(plan.status, "expired")
                self.assertIs(plan.timing, self.timing)

    def test_renewal_cannot_extend_overall_deadline(self):
        timing = self.timing
        for seconds in (3, 6, 9, 12, 15, 18, 21, 24):
            plan = lease.plan_lease_renewal(timing, now=self.now + timedelta(seconds=seconds))
            self.assertEqual(plan.status, "renewed")
            self.assertEqual(plan.timing.deadline_at, self.timing.deadline_at)
            self.assertLessEqual(plan.timing.expires_at, self.timing.deadline_at)
            timing = plan.timing
        self.assertEqual(timing.expires_at, self.timing.deadline_at)
        final = lease.plan_lease_renewal(timing, now=self.timing.deadline_at)
        self.assertEqual(final.status, "deadline")
        self.assertIs(final.timing, timing)

    def test_forward_clock_jump_reports_deadline_not_recovery(self):
        plan = lease.plan_lease_renewal(self.timing, now=self.now + timedelta(days=1))
        self.assertEqual(plan.status, "deadline")
        self.assertIs(plan.timing, self.timing)

    def test_clock_regression_does_not_extend_or_shrink(self):
        plan = lease.plan_lease_renewal(self.timing, now=self.now - timedelta(microseconds=1))
        self.assertEqual(plan.status, "clock_regressed")
        self.assertIs(plan.timing, self.timing)

    def test_timing_snapshot_rejects_inconsistent_order_or_ttl(self):
        for heartbeat, expiry, deadline, ttl, interval in (
            (0, 0, 25, 10, 3), (0, -1, 25, 10, 3),
            (0, 10, 9, 10, 3), (0, 11, 25, 10, 3),
            (0, 10, 25, 10, 10), (0, 10, 25, 0, 3),
        ):
            with self.subTest(values=(heartbeat, expiry, deadline, ttl, interval)):
                with self.assertRaises(lease.LeasePolicyError):
                    lease.LeaseTiming(
                        self.now + timedelta(seconds=heartbeat),
                        self.now + timedelta(seconds=expiry),
                        self.now + timedelta(seconds=deadline), ttl, interval,
                    )

    def test_initial_deadline_overflow_fails_closed(self):
        with self.assertRaises(lease.LeasePolicyError):
            lease.initial_lease_timing(self.policy, now=datetime.max.replace(tzinfo=timezone.utc))

    def test_bounded_renewal_near_datetime_max_does_not_overflow(self):
        deadline = datetime.max.replace(tzinfo=timezone.utc)
        timing = lease.LeaseTiming(deadline - timedelta(seconds=8), deadline, deadline, 10, 3)
        plan = lease.plan_lease_renewal(timing, now=deadline - timedelta(seconds=3))
        self.assertEqual(plan.status, "renewed")
        self.assertEqual(plan.timing.expires_at, deadline)

    def test_identity_is_immutable_and_epoch_cannot_be_zero(self):
        identity = lease.LeaseIdentity(1, "same-worker", 1, UUID(int=1))
        with self.assertRaises(FrozenInstanceError):
            identity.epoch = 2
        for bad in (0, -1, True, 2**63):
            with self.subTest(epoch=bad), self.assertRaises(lease.LeasePolicyError):
                lease.LeaseIdentity(1, "same-worker", bad, UUID(int=1))

    def test_identity_rejects_missing_owner_or_execution(self):
        for owner in ("", " ", "x" * 129, None):
            with self.subTest(owner=owner), self.assertRaises(lease.LeasePolicyError):
                lease.LeaseIdentity(1, owner, 1, UUID(int=1))
        with self.assertRaises(lease.LeasePolicyError):
            lease.LeaseIdentity(1, "worker", 1, None)

    def test_reused_worker_id_does_not_make_new_epoch_same_identity(self):
        old = lease.LeaseIdentity(1, "same-worker", 1, UUID(int=1))
        new = lease.LeaseIdentity(1, "same-worker", 2, UUID(int=2))
        self.assertNotEqual(old, new)

    def test_captured_identity_is_not_reconstructed_from_mutable_columns(self):
        old = lease.LeaseIdentity(1, "same-worker", 1, UUID(int=1))
        job = SimpleNamespace(_generation_lease_identity=old, lease_epoch=99,
                              locked_by="replacement", attempt_count=99)
        self.assertIs(lease.captured_lease_identity(job), old)

    def test_missing_capture_does_not_fall_back_to_live_row(self):
        job = SimpleNamespace(id=1, lease_epoch=1, locked_by="worker", attempt_count=1)
        with self.assertRaises(lease.LeasePolicyError):
            lease.captured_lease_identity(job)


if __name__ == "__main__":
    unittest.main()

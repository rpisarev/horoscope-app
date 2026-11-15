"""Prepared PostgreSQL renewal regressions; parent-only STAB-007 verification."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import db
from app.models import GenerationExecution, GenerationJob, GenerationRun
from app.services import generation_lease_service as leases
from app.services import generation_job_service as jobs
from app.services.generation_execution_service import claim_execution_id, record_execution_start
from app.services.generation_execution_service import ExecutionStartError, GenerationClaimLost
from app.services.generation_lease_policy import (
    LeaseIdentity, LeasePolicy, LeasePolicyError, captured_lease_identity, initial_lease_timing,
)


NOW = datetime(2026, 11, 15, 23, 59, 55, tzinfo=timezone.utc)
POLICY = LeasePolicy(interval_seconds=3, ttl_seconds=10, max_duration_seconds=25)
WAIT_SECONDS = 5


@pytest.fixture
def lease_environment(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(leases, "_database_utcnow", lambda connection: NOW + timedelta(seconds=3))
        yield app, db.engine


def _claim(session, job_id, *, now=NOW, owner="same-worker", timed=True):
    """Explicit fixture transition; never automatic reclaim or provider work."""
    row = session.execute(text("SELECT * FROM generation_jobs WHERE id=:id FOR UPDATE"),
                          {"id": job_id}).mappings().one()
    assert row["status"] == "queued"
    epoch = row["lease_epoch"] + 1
    attempt = row["attempt_count"] + 1
    timing = initial_lease_timing(POLICY, now=now) if timed else None
    session.execute(text("""
        UPDATE generation_jobs SET status='running', locked_by=:owner, locked_at=:now,
            lease_epoch=:epoch, attempt_count=:attempt,
            lease_heartbeat_at=:heartbeat, lease_expires_at=:expires,
            lease_deadline_at=:deadline, lease_ttl_seconds=:ttl,
            lease_heartbeat_interval_seconds=:interval
        WHERE id=:id
    """), dict(id=job_id, owner=owner, now=now, epoch=epoch, attempt=attempt,
               heartbeat=timing.heartbeat_at if timing else None,
               expires=timing.expires_at if timing else None,
               deadline=timing.deadline_at if timing else None,
               ttl=timing.ttl_seconds if timing else None,
               interval=timing.interval_seconds if timing else None))
    execution_id = claim_execution_id(SimpleNamespace(id=job_id, attempt_count=attempt))
    record_execution_start(
        session, execution_id=execution_id, origin="queue_worker", provider="stub",
        target_date=row["target_date"], locale=row["locale"],
        forecast_type=row["forecast_type"], job_id=job_id, lease_epoch=epoch,
    )
    return LeaseIdentity(job_id, owner, epoch, execution_id)


def _claimed(engine, *, timed=True):
    with Session(engine) as session, session.begin():
        job = GenerationJob(job_type="manual", status="queued", provider="stub",
                            target_date=date(2026, 11, 16), locale="ru", forecast_type="daily",
                            dedupe_key=str(uuid4()))
        session.add(job)
        session.flush()
        identity = _claim(session, job.id, timed=timed)
    return identity


def _snapshot(engine, job_id):
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT * FROM generation_jobs WHERE id=:id"),
                                       {"id": job_id}).mappings().one())


def test_current_owner_renews_without_changing_claim_identity(lease_environment):
    _, engine = lease_environment
    identity = _claimed(engine)
    before = _snapshot(engine, identity.job_id)
    result = leases.renew_generation_job_lease(identity)
    assert result.status == "renewed"
    after = _snapshot(engine, identity.job_id)
    assert after["lease_heartbeat_at"] == NOW + timedelta(seconds=3)
    assert after["lease_expires_at"] == NOW + timedelta(seconds=13)
    for key in before:
        if key not in {"lease_heartbeat_at", "lease_expires_at"}:
            assert after[key] == before[key], key


@pytest.mark.parametrize("kind", ["owner", "epoch", "execution", "missing_job"])
def test_wrong_identity_cannot_renew(lease_environment, kind):
    _, engine = lease_environment
    original = _claimed(engine)
    before = _snapshot(engine, original.job_id)
    invalid = LeaseIdentity(
        original.job_id + (1 if kind == "missing_job" else 0),
        "other-worker" if kind == "owner" else original.owner,
        original.epoch + (1 if kind == "epoch" else 0),
        uuid4() if kind == "execution" else original.execution_id,
    )
    assert leases.renew_generation_job_lease(invalid).status == "lost"
    assert _snapshot(engine, original.job_id) == before


@pytest.mark.parametrize("mode", ["production", "", "invalid", None])
def test_production_or_invalid_mode_denied_before_connection(lease_environment, monkeypatch, mode):
    app, engine = lease_environment
    identity = _claimed(engine)
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", mode)
    monkeypatch.setattr(leases, "_renewal_engine", lambda *args: pytest.fail("DB not expected"))
    assert leases.renew_generation_job_lease(identity).status == "disabled"


def test_timing_disabled_by_default_cannot_be_inferred(lease_environment):
    _, engine = lease_environment
    identity = _claimed(engine, timed=False)
    before = _snapshot(engine, identity.job_id)
    assert leases.renew_generation_job_lease(identity).status == "disabled"
    assert _snapshot(engine, identity.job_id) == before


@pytest.mark.parametrize("seconds,expected", [(-1, "clock_regressed"), (0, "not_due"),
                                            (2, "not_due"), (10, "expired"),
                                            (11, "expired"), (25, "deadline")])
def test_time_boundaries_are_fail_closed_without_writes(lease_environment, monkeypatch, seconds, expected):
    _, engine = lease_environment
    identity = _claimed(engine)
    before = _snapshot(engine, identity.job_id)
    monkeypatch.setattr(leases, "_database_utcnow", lambda connection: NOW + timedelta(seconds=seconds))
    assert leases.renew_generation_job_lease(identity).status == expected
    assert _snapshot(engine, identity.job_id) == before


def test_long_execution_cannot_extend_fixed_deadline(lease_environment, monkeypatch):
    _, engine = lease_environment
    identity = _claimed(engine)
    for seconds in (3, 6, 9, 12, 15, 18, 21, 24):
        monkeypatch.setattr(leases, "_database_utcnow", lambda connection, at=seconds: NOW + timedelta(seconds=at))
        result = leases.renew_generation_job_lease(identity)
        assert result.status == "renewed"
        assert result.timing.deadline_at == NOW + timedelta(seconds=25)
    monkeypatch.setattr(leases, "_database_utcnow", lambda connection: NOW + timedelta(seconds=25))
    assert leases.renew_generation_job_lease(identity).status == "deadline"


def test_caller_pending_and_flushed_writes_stay_caller_owned(lease_environment):
    _, engine = lease_environment
    identity = _claimed(engine)
    pending = GenerationRun(run_type="manual", status="success", target_date=date(2026, 12, 1))
    db.session.add(pending)
    assert leases.renew_generation_job_lease(identity).status == "renewed"
    assert pending in db.session.new and pending.id is None
    db.session.flush()
    run_id = pending.id
    assert leases.renew_generation_job_lease(identity).status == "not_due"
    with Session(engine) as observer:
        assert observer.get(GenerationRun, run_id) is None
    db.session.rollback()
    with Session(engine) as observer:
        assert observer.get(GenerationRun, run_id) is None
    assert _snapshot(engine, identity.job_id)["lease_expires_at"] == NOW + timedelta(seconds=13)


def test_caller_row_lock_returns_busy_without_ending_caller_transaction(lease_environment):
    _, engine = lease_environment
    identity = _claimed(engine)
    with Session(engine) as caller, caller.begin():
        caller.execute(text("SELECT id FROM generation_jobs WHERE id=:id FOR UPDATE"),
                       {"id": identity.job_id})
        assert leases.renew_generation_job_lease(identity).status == "busy"
        assert caller.in_transaction()
    assert leases.renew_generation_job_lease(identity).status == "renewed"


def test_takeover_with_reused_worker_id_rejects_old_identity(lease_environment, monkeypatch):
    _, engine = lease_environment
    old = _claimed(engine)
    with Session(engine) as session, session.begin():
        # Authorized fixture transition only; no runtime recovery action is added.
        session.execute(text("UPDATE generation_jobs SET status='failed', locked_by=NULL, "
                             "locked_at=NULL WHERE id=:id"), {"id": old.job_id})
        session.execute(text("UPDATE generation_jobs SET status='queued' WHERE id=:id"),
                        {"id": old.job_id})
        new = _claim(session, old.job_id, now=NOW + timedelta(seconds=11), owner=old.owner)
        assert leases.renew_generation_job_lease(old).status == "busy"
    assert new.epoch == old.epoch + 1 and new.execution_id != old.execution_id
    before = _snapshot(engine, old.job_id)
    assert leases.renew_generation_job_lease(old).status == "lost"
    assert _snapshot(engine, old.job_id) == before
    monkeypatch.setattr(leases, "_database_utcnow", lambda connection: NOW + timedelta(seconds=14))
    assert leases.renew_generation_job_lease(new).status == "renewed"
    with Session(engine) as session:
        assert set(session.scalars(select(GenerationExecution.id)).all()) == {old.execution_id, new.execution_id}


def test_renewal_lock_prevents_takeover_from_using_old_expiry(lease_environment, monkeypatch):
    app, engine = lease_environment
    identity = _claimed(engine)
    acquired, release = Event(), Event()
    result = {}

    def clock_after_lock(connection):
        acquired.set()
        assert release.wait(WAIT_SECONDS)
        return NOW + timedelta(seconds=3)

    def worker():
        try:
            with app.app_context():
                result["renewal"] = leases.renew_generation_job_lease(identity)
        except BaseException as exc:
            result["error"] = exc

    monkeypatch.setattr(leases, "_database_utcnow", clock_after_lock)
    thread = Thread(target=worker)
    thread.start()
    try:
        assert acquired.wait(WAIT_SECONDS)
        with Session(engine) as contender, contender.begin():
            with pytest.raises(DBAPIError) as failure:
                with contender.begin_nested():
                    contender.execute(text("SELECT id FROM generation_jobs WHERE id=:id FOR UPDATE NOWAIT"),
                                      {"id": identity.job_id})
            assert failure.value.orig.sqlstate == "55P03"
    finally:
        release.set()
        thread.join(WAIT_SECONDS)
    assert not thread.is_alive()
    assert "error" not in result
    assert result["renewal"].status == "renewed"
    with Session(engine) as contender, contender.begin():
        row = contender.execute(text("SELECT lease_expires_at FROM generation_jobs "
                                     "WHERE id=:id FOR UPDATE"), {"id": identity.job_id}).one()
        assert row.lease_expires_at > NOW + timedelta(seconds=11)


def test_error_after_update_rolls_back_without_leaking_details(lease_environment, monkeypatch):
    _, engine = lease_environment
    identity = _claimed(engine)
    before = _snapshot(engine, identity.job_id)
    original = leases._renew_locked

    def fail_after_update(*args):
        assert original(*args).status == "renewed"
        raise RuntimeError("secret-dsn-must-not-escape")

    monkeypatch.setattr(leases, "_renew_locked", fail_after_update)
    result = leases.renew_generation_job_lease(identity)
    assert result.status == "unavailable" and result.timing is None
    assert "secret" not in repr(result)
    assert _snapshot(engine, identity.job_id) == before


def test_ambiguous_commit_is_unavailable_even_if_write_committed(lease_environment, monkeypatch):
    _, engine = lease_environment
    identity = _claimed(engine)
    original_factory = leases._renewal_engine

    class AmbiguousCommit:
        def __init__(self, url):
            self.engine = original_factory(url)

        @contextmanager
        def begin(self):
            with self.engine.begin() as connection:
                yield connection
            raise RuntimeError("simulated lost commit acknowledgement")

        def dispose(self):
            self.engine.dispose()

    monkeypatch.setattr(leases, "_renewal_engine", AmbiguousCommit)
    result = leases.renew_generation_job_lease(identity)
    assert result.status == "unavailable" and result.timing is None
    assert _snapshot(engine, identity.job_id)["lease_expires_at"] == NOW + timedelta(seconds=13)


def test_connection_failure_is_sanitized_unavailable(lease_environment, monkeypatch):
    _, engine = lease_environment
    identity = _claimed(engine)

    def failed_engine(url):
        raise RuntimeError("password connection-string SQL must not escape")

    monkeypatch.setattr(leases, "_renewal_engine", failed_engine)
    result = leases.renew_generation_job_lease(identity)
    assert result.status == "unavailable" and result.timing is None
    assert "password" not in repr(result)


def test_network_guard_baseexception_cannot_be_converted_to_operational_result(lease_environment, monkeypatch):
    class GuardViolation(BaseException):
        pass

    def forbidden_connection(url):
        raise GuardViolation("unexpected transport")

    monkeypatch.setattr(leases, "_renewal_engine", forbidden_connection)
    identity = LeaseIdentity(1, "fixture-owner", 1, uuid4())
    with pytest.raises(GuardViolation):
        leases.renew_generation_job_lease(identity)


def test_real_claim_commits_epoch_and_start_then_explicitly_renews(lease_environment, monkeypatch):
    _, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16), signs=["aries"])
    monkeypatch.setattr(jobs, "_claim_utcnow", lambda: NOW)
    claimed = jobs.claim_next_generation_job(worker_id="real-claim", lease_policy=POLICY)
    assert isinstance(claimed, GenerationJob)
    identity = captured_lease_identity(claimed)
    with Session(engine) as observer:
        row = observer.get(GenerationJob, identity.job_id)
        execution = observer.get(GenerationExecution, identity.execution_id)
        assert row.lease_epoch == execution.lease_epoch == identity.epoch == 1
        assert row.locked_at == row.lease_heartbeat_at == NOW
        assert execution.origin == "queue_worker" and execution.provider == "stub"
    assert leases.renew_generation_job_lease(identity).status == "renewed"
    assert _snapshot(engine, identity.job_id)["lease_expires_at"] == NOW + timedelta(seconds=13)


def test_real_claim_default_has_identity_without_timing_activation(lease_environment):
    _, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    claimed = jobs.claim_next_generation_job(worker_id="default")
    identity = captured_lease_identity(claimed)
    assert identity.epoch == 1
    row = _snapshot(engine, identity.job_id)
    assert all(row[name] is None for name in (
        "lease_heartbeat_at", "lease_expires_at", "lease_deadline_at",
        "lease_ttl_seconds", "lease_heartbeat_interval_seconds",
    ))
    assert leases.renew_generation_job_lease(identity).status == "disabled"


def test_retry_in_same_session_keeps_old_handle_and_denies_old_dispatch(lease_environment, monkeypatch):
    _, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    first = jobs.claim_next_generation_job(worker_id="reused")
    old = captured_lease_identity(first)
    first.status = "failed"
    db.session.commit()
    jobs.retry_generation_job(old.job_id)
    second = jobs.claim_next_generation_job(worker_id="reused")
    new = captured_lease_identity(second)
    assert first is not second
    assert captured_lease_identity(first) is old
    assert new.epoch == old.epoch + 1 and new.execution_id != old.execution_id
    before = _snapshot(engine, old.job_id)
    monkeypatch.setattr(jobs, "_run_standard_generation_job", lambda *a, **k: pytest.fail("Stale dispatch"))
    with pytest.raises(GenerationClaimLost):
        jobs.process_claimed_generation_job(first, worker_id="reused")
    assert _snapshot(engine, old.job_id) == before
    with Session(engine) as observer:
        assert observer.get(GenerationExecution, old.execution_id).lease_epoch == old.epoch
        assert observer.get(GenerationExecution, new.execution_id).lease_epoch == new.epoch


def test_reloaded_job_requires_explicit_original_handoff(lease_environment, monkeypatch):
    _, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    claimed = jobs.claim_next_generation_job(worker_id="handoff")
    identity = captured_lease_identity(claimed)
    db.session.remove()
    fresh = db.session.get(GenerationJob, identity.job_id)
    before = _snapshot(engine, identity.job_id)
    with pytest.raises(LeasePolicyError, match="captured"):
        jobs.process_claimed_generation_job(fresh, worker_id="handoff")
    assert _snapshot(engine, identity.job_id) == before
    monkeypatch.setattr(jobs, "_run_standard_generation_job", lambda *a, **k: None)
    result = jobs.process_claimed_generation_job(fresh, worker_id="handoff", lease_identity=identity)
    assert result["status"] == "success"


def test_expired_timed_claim_cannot_begin_dispatch(lease_environment, monkeypatch):
    _, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    monkeypatch.setattr(jobs, "_claim_utcnow", lambda: NOW)
    claimed = jobs.claim_next_generation_job(worker_id="expired", lease_policy=POLICY)
    identity = captured_lease_identity(claimed)
    before = _snapshot(engine, identity.job_id)
    monkeypatch.setattr(jobs, "_claim_utcnow", lambda: NOW + timedelta(seconds=10))
    monkeypatch.setattr(jobs, "_ensure_provider_can_execute", lambda *a, **k: pytest.fail("No preflight dispatch"))
    with pytest.raises(GenerationClaimLost, match="timed lease"):
        jobs.process_claimed_generation_job(claimed, worker_id="expired")
    assert _snapshot(engine, identity.job_id) == before


@pytest.mark.parametrize("ambiguous", [False, True])
def test_failed_claim_commit_never_returns_or_attaches_authority(lease_environment, monkeypatch, ambiguous):
    _, engine = lease_environment
    created, _ = jobs.create_generation_job(target_date=date(2026, 11, 16))
    job_id = created.id
    session = db.session()
    original_commit = session.commit

    def failed_commit():
        if ambiguous:
            original_commit()
        raise RuntimeError("claim commit not acknowledged")

    with monkeypatch.context() as patch:
        patch.setattr(session, "commit", failed_commit)
        with pytest.raises(RuntimeError, match="not acknowledged"):
            jobs.claim_next_generation_job(worker_id="commit-failure")
    assert "_generation_lease_identity" not in vars(created)
    row = _snapshot(engine, job_id)
    assert row["lease_epoch"] == int(ambiguous)
    assert row["status"] == ("running" if ambiguous else "queued")
    with Session(engine) as observer:
        assert len(observer.scalars(select(GenerationExecution)).all()) == int(ambiguous)


@pytest.mark.parametrize("provider", ["openai", " OpenAI "])
def test_legacy_paid_jobs_never_enter_age_only_cleanup(lease_environment, provider):
    _, engine = lease_environment
    row = GenerationJob(job_type="manual", status="running", provider=provider,
                        target_date=date(2026, 11, 16), dedupe_key=str(uuid4()),
                        locked_by="legacy", locked_at=NOW - timedelta(days=1),
                        max_job_attempts=3, attempt_count=1)
    db.session.add(row)
    db.session.commit()
    job_id = row.id
    before = _snapshot(engine, job_id)
    assert before["lease_epoch"] == 0
    assert jobs.close_stale_running_jobs(stale_after_minutes=1) == 0
    assert _snapshot(engine, job_id) == before


def test_production_positive_epoch_does_not_activate_ledger_or_timing(lease_environment, monkeypatch):
    app, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", "production")
    with pytest.raises(ExecutionStartError, match="Production execution is blocked"):
        jobs.claim_next_generation_job(worker_id="production", lease_policy=POLICY)
    assert GenerationJob.query.one().lease_epoch == 0
    claimed = jobs.claim_next_generation_job(worker_id="production")
    identity = captured_lease_identity(claimed)
    assert identity.epoch == 1
    assert GenerationExecution.query.count() == 0
    assert leases.renew_generation_job_lease(identity).status == "disabled"


def test_two_claimers_allocate_only_one_epoch_and_execution(lease_environment, monkeypatch):
    app, engine = lease_environment
    jobs.create_generation_job(target_date=date(2026, 11, 16))
    acquired, release = Event(), Event()
    outcomes = {}

    def held_clock():
        acquired.set()
        assert release.wait(WAIT_SECONDS)
        return NOW

    def owner():
        try:
            with app.app_context():
                row = jobs.claim_next_generation_job(worker_id="first")
                outcomes["identity"] = captured_lease_identity(row)
        except BaseException as exc:
            outcomes["error"] = exc

    monkeypatch.setattr(jobs, "_claim_utcnow", held_clock)
    thread = Thread(target=owner)
    thread.start()
    try:
        assert acquired.wait(WAIT_SECONDS)
        assert jobs.claim_next_generation_job(worker_id="second") is None
    finally:
        release.set()
        thread.join(WAIT_SECONDS)
    assert not thread.is_alive() and "error" not in outcomes
    with Session(engine) as observer:
        row = observer.get(GenerationJob, outcomes["identity"].job_id)
        assert row.lease_epoch == row.attempt_count == 1
        assert len(observer.scalars(select(GenerationExecution)).all()) == 1

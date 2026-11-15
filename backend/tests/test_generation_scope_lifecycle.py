"""Integrated admission paths; fake providers, serialized STAB-007 only."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from threading import Event, Thread, current_thread
from unittest.mock import Mock

import pytest
from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from app import db
from app.models import (
    Forecast, GenerationAttempt, GenerationExecution, GenerationExecutionRun,
    GenerationItem, GenerationJob, GenerationRun,
)
from app.providers import GenerationProviderError, ProviderResult
from app.services import generation_execution_service as executions
from app.services import generation_job_service as jobs
from app.services import generation_service as lifecycle
from app.services.forecast_service import save_forecast
from app.services.generation_admission_service import GenerationPackageScope, GenerationScopeBusy


DAY = date(2026, 11, 17)
SCOPE = GenerationPackageScope(DAY, "ru", "daily")
WAIT_SECONDS = 8


def install_provider(monkeypatch, callback):
    class Fake:
        model_name = "scope-fake"

        def __init__(self, name):
            self.name = name

        def generate(self, request):
            return callback(self.name, request)

    monkeypatch.setattr(lifecycle, "get_horoscope_provider", lambda name=None: Fake(name or "stub"))


def success():
    return ProviderResult(text="Спокойный день поможет завершить начатые дела.", provider="stub",
                          model_name="scope-fake")


def job_snapshot(session, job_id):
    row = session.get(GenerationJob, job_id, populate_existing=True)
    return {column.name: getattr(row, column.name) for column in GenerationJob.__table__.columns}


@pytest.mark.parametrize("winner_entry,loser_entry,loser_provider,loser_signs,loser_type", [
    ("direct", "direct", "stub", ["aries"], "manual"),
    ("direct", "direct", "otherfake", ["aries", "taurus"], "backfill"),
    ("direct", "direct", "stub", ["taurus"], "retry"),
    ("direct", "queue", "stub", ["aries", "taurus"], "backfill"),
    ("queue", "direct", "stub", ["aries"], "manual"),
    ("queue", "queue", "stub", ["aries", "taurus"], "backfill"),
])
def test_concurrent_entrypoints_admit_one_package(
    app, monkeypatch, winner_entry, loser_entry, loser_provider, loser_signs, loser_type,
):
    provider_entered, finish_provider = Event(), Event()
    calls, results = [], []
    engine = db.engine

    def provider(name, request):
        assert current_thread().name == "scope-owner", "losing caller reached provider"
        calls.append((name, request))
        # Admission transaction is already committed. Its advisory lock must
        # not span this simulated external request.
        with Session(engine) as observer, observer.begin():
            assert observer.scalar(select(func.pg_try_advisory_xact_lock(SCOPE.lock_key()))) is True
        provider_entered.set()
        assert finish_provider.wait(WAIT_SECONDS)
        return success()

    install_provider(monkeypatch, provider)

    def winner():
        try:
            with app.app_context():
                if winner_entry == "queue":
                    jobs.create_generation_job(target_date=DAY, job_type="scheduled", signs=["aries"])
                    claimed = jobs.claim_next_generation_job(worker_id="scope-owner")
                    result = jobs.process_claimed_generation_job(claimed, worker_id="scope-owner")
                    results.append(result["status"])
                else:
                    run = lifecycle.run_daily_generation(target_date=DAY, provider_name="stub",
                                                         signs=["aries"], run_type="scheduled")
                    results.append(run.status)
        except BaseException as exc:
            results.append(exc)
            provider_entered.set()

    thread = Thread(target=winner, name="scope-owner")
    thread.start()
    try:
        assert provider_entered.wait(WAIT_SECONDS)
        assert not results, results
        if loser_entry == "queue":
            losing_job, _ = jobs.create_generation_job(target_date=DAY, job_type=loser_type,
                                                       provider=loser_provider, signs=loser_signs)
            claimed = jobs.claim_next_generation_job(worker_id="scope-loser")
            assert claimed.id == losing_job.id
            result = jobs.process_claimed_generation_job(claimed, worker_id="scope-loser")
            assert result["status"] == "failed"
            assert result["run_id"] is None
            assert result["error_message"].startswith("generation_scope_busy:")
            assert GenerationExecutionRun.query.count() == 1
        else:
            with pytest.raises(GenerationScopeBusy):
                lifecycle.run_daily_generation(target_date=DAY, provider_name=loser_provider,
                                               signs=loser_signs, run_type=loser_type)
        assert GenerationRun.query.count() == 1
        assert GenerationRun.query.one().status == "running"
        assert len(calls) == 1
    finally:
        finish_provider.set()
        thread.join(WAIT_SECONDS + 2)
    assert not thread.is_alive()
    assert results == ["success"], results
    db.session.expire_all()
    assert GenerationRun.query.one().status == "success"
    assert Forecast.query.count() == 1
    assert len(calls) == 1


def test_managed_run_is_not_reaped_or_replaced_by_age(app, monkeypatch):
    class Crash(BaseException):
        pass

    def crash(**kwargs):
        raise Crash()

    provider = Mock(return_value=success())
    install_provider(monkeypatch, provider)
    monkeypatch.setattr(lifecycle, "_process_generation_item", crash)
    with pytest.raises(Crash):
        lifecycle.run_daily_generation(target_date=DAY, signs=["aries"], provider_name="stub")
    run = GenerationRun.query.one()
    run.started_at = datetime.now(timezone.utc) - timedelta(hours=10)
    db.session.commit()
    original = (run.id, run.status, run.finished_at)
    assert lifecycle.close_stale_running_runs(stale_after_hours=1) == 0
    with pytest.raises(GenerationScopeBusy):
        lifecycle.run_daily_generation(target_date=DAY, signs=["taurus"], stale_after_hours=1)
    db.session.refresh(run)
    assert (run.id, run.status, run.finished_at) == original
    assert GenerationExecution.query.count() == GenerationExecutionRun.query.count() == 1
    assert GenerationItem.query.one().status == "pending"
    provider.assert_not_called()


def test_legacy_unmanaged_run_not_automatically_reaped_during_new_generation(app, monkeypatch):
    legacy = GenerationRun(run_type="manual", target_date=DAY, status="running",
                           started_at=datetime.now(timezone.utc) - timedelta(hours=10))
    db.session.add(legacy)
    db.session.commit()
    provider = Mock(return_value=success())
    install_provider(monkeypatch, provider)
    with pytest.raises(GenerationScopeBusy):
        lifecycle.run_daily_generation(target_date=DAY, signs=["aries"], stale_after_hours=1)
    db.session.refresh(legacy)
    assert legacy.status == "running"
    assert GenerationExecution.query.count() == 0
    provider.assert_not_called()
    # Explicit legacy cleanup remains compatible; no automatic caller invokes it.
    assert lifecycle.close_stale_running_runs(stale_after_hours=1) == 1


def test_legacy_unmanaged_job_stale_cleanup_remains_available(app):
    # Historical epoch-zero row, not a new queued->running lease allocation.
    job = GenerationJob(job_type="manual", target_date=DAY, provider="stub",
                        dedupe_key="legacy-unmanaged", max_job_attempts=1,
                        status="running", locked_by="legacy-owner", attempt_count=1,
                        locked_at=datetime.now(timezone.utc) - timedelta(hours=10))
    db.session.add(job)
    db.session.commit()
    assert jobs.close_stale_running_jobs(stale_after_minutes=60) == 1
    db.session.refresh(job)
    assert job.status == "failed"
    assert GenerationExecution.query.count() == 0


def test_retry_cap_rechecked_after_fast_winner_finishes(app, monkeypatch):
    before_admission, winner_finished = Event(), Event()
    outcomes, calls = [], []
    original_admission = lifecycle.package_admission
    monkeypatch.setattr(lifecycle, "get_enabled_sign_keys", lambda: ["aries"])

    @contextmanager
    def delayed_admission(session, *, scope):
        if current_thread().name == "late-retry":
            before_admission.set()
            assert winner_finished.wait(WAIT_SECONDS)
        with original_admission(session, scope=scope):
            yield

    def failed_provider(name, request):
        calls.append(request)
        raise GenerationProviderError("fake permanent failure", retryable=False)

    monkeypatch.setattr(lifecycle, "package_admission", delayed_admission)
    install_provider(monkeypatch, failed_provider)

    def contender():
        try:
            with app.app_context():
                outcomes.append(lifecycle.run_retry_for_missing_forecasts(
                    target_date=DAY, provider_name="stub", max_retry_runs=1, max_attempts=1,
                ))
        except BaseException as exc:
            outcomes.append(exc)
            before_admission.set()

    thread = Thread(target=contender, name="late-retry")
    thread.start()
    try:
        assert before_admission.wait(WAIT_SECONDS)
        assert not outcomes
        first = lifecycle.run_retry_for_missing_forecasts(target_date=DAY, provider_name="stub",
                                                          max_retry_runs=1, max_attempts=1)
        assert first.status == "failed"
    finally:
        winner_finished.set()
        thread.join(WAIT_SECONDS + 2)
    assert not thread.is_alive()
    assert outcomes == [None], outcomes
    assert GenerationRun.query.count() == GenerationExecution.query.count() == 1
    assert GenerationAttempt.query.count() == len(calls) == 1


@pytest.mark.parametrize("changed", [
    {"locked_by": "new-owner"}, {"attempt_count": 2}, {"status": "queued"},
])
def test_busy_job_disposition_rejects_lost_claim_authority(app, monkeypatch, changed):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"])
    claimed = jobs.claim_next_generation_job(worker_id="same-worker")
    job_id = job.id
    engine = db.engine

    def lose_ownership(*args, **kwargs):
        with Session(engine) as competitor, competitor.begin():
            if "locked_by" in changed:
                # Fixture-only authorized turnover; in-place owner substitution
                # is now rejected by the lease identity trigger.
                competitor.execute(update(GenerationJob).where(GenerationJob.id == job_id).values(status="failed"))
                competitor.execute(update(GenerationJob).where(GenerationJob.id == job_id).values(status="queued"))
                competitor.execute(update(GenerationJob).where(GenerationJob.id == job_id).values(
                    status="running", lease_epoch=GenerationJob.lease_epoch + 1,
                    attempt_count=GenerationJob.attempt_count + 1,
                    locked_at=func.clock_timestamp(), **changed,
                ))
            else:
                competitor.execute(update(GenerationJob).where(GenerationJob.id == job_id).values(**changed))
        raise GenerationScopeBusy(SCOPE)

    monkeypatch.setattr(jobs, "_run_standard_generation_job", lose_ownership)
    with pytest.raises(jobs.GenerationJobProcessingError, match="ownership changed"):
        jobs.process_claimed_generation_job(claimed, worker_id="same-worker")
    with Session(engine) as observer:
        stored = observer.get(GenerationJob, job_id)
        assert all(getattr(stored, key) == value for key, value in changed.items())
        assert stored.finished_at is None and stored.error_message is None
        assert stored.run_id is None


@pytest.mark.parametrize("changed_gate", [None, "global", "local", "publication"])
def test_duplicate_linked_dispatch_does_not_mutate_active_owner(app, monkeypatch, changed_gate):
    entered, release = Event(), Event()
    outcomes, calls = [], []
    jobs.create_generation_job(target_date=DAY, signs=["aries"])
    claimed = jobs.claim_next_generation_job(worker_id="same-worker")
    lease_identity = jobs.captured_lease_identity(claimed)
    job_id = claimed.id
    engine = db.engine

    def provider(name, request):
        calls.append(request)
        entered.set()
        assert release.wait(WAIT_SECONDS)
        return success()

    install_provider(monkeypatch, provider)

    def original_dispatch():
        try:
            with app.app_context():
                row = db.session.get(GenerationJob, job_id)
                outcomes.append(jobs.process_claimed_generation_job(
                    row, worker_id="same-worker", lease_identity=lease_identity,
                )["status"])
        except BaseException as exc:
            outcomes.append(exc)
            entered.set()

    thread = Thread(target=original_dispatch)
    thread.start()
    try:
        assert entered.wait(WAIT_SECONDS)
        assert not outcomes, outcomes
        with Session(engine) as observer:
            before = job_snapshot(observer, job_id)
            before_run = observer.scalar(select(GenerationExecutionRun.run_id))
        denied = Mock(side_effect=RuntimeError("changed permission denied"))
        if changed_gate is not None:
            # Keep the original in-flight fake provider/publication unaffected;
            # only the duplicate worker's gate would deny if it were reached.
            target = {
                "global": "require_paid_execution", "local": "_ensure_provider_can_execute",
                "publication": "require_publication_provider",
            }[changed_gate]
            monkeypatch.setattr(jobs, target, denied)
        with pytest.raises(executions.ExecutionAlreadyStarted, match="already started"):
            jobs.process_claimed_generation_job(claimed, worker_id="same-worker")
        denied.assert_not_called()
        with Session(engine) as observer:
            assert job_snapshot(observer, job_id) == before
            assert observer.scalar(select(GenerationExecutionRun.run_id)) == before_run
            assert observer.get(GenerationRun, before_run).status == "running"
        assert len(calls) == 1
    finally:
        release.set()
        thread.join(WAIT_SECONDS + 2)
    assert not thread.is_alive()
    assert outcomes == ["success"], outcomes
    assert len(calls) == 1


def test_run_and_link_failure_roll_back_and_release_package(app, monkeypatch):
    provider = Mock(return_value=success())
    install_provider(monkeypatch, provider)
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle, "link_execution_run", Mock(side_effect=RuntimeError("link failure")))
        with pytest.raises(RuntimeError, match="link failure"):
            lifecycle.run_daily_generation(target_date=DAY, signs=["aries"])
    assert GenerationRun.query.count() == GenerationExecution.query.count() == 0
    provider.assert_not_called()
    assert lifecycle.run_daily_generation(target_date=DAY, signs=["aries"]).status == "success"


def test_duplicate_before_link_commit_keeps_original_claim_intact(app, monkeypatch):
    before_link, finish_link = Event(), Event()
    outcomes, calls = [], []
    original_link = lifecycle.link_execution_run
    engine = db.engine
    jobs.create_generation_job(target_date=DAY, signs=["aries"])
    claimed = jobs.claim_next_generation_job(worker_id="same-worker")
    lease_identity = jobs.captured_lease_identity(claimed)
    job_id = claimed.id
    with Session(engine) as observer:
        before = job_snapshot(observer, job_id)

    def delayed_link(*args, **kwargs):
        if current_thread().name == "first-dispatch":
            before_link.set()
            assert finish_link.wait(WAIT_SECONDS)
        return original_link(*args, **kwargs)

    def provider(name, request):
        calls.append(request)
        return success()

    monkeypatch.setattr(lifecycle, "link_execution_run", delayed_link)
    install_provider(monkeypatch, provider)

    def first_dispatch():
        try:
            with app.app_context():
                row = db.session.get(GenerationJob, job_id)
                outcomes.append(jobs.process_claimed_generation_job(
                    row, worker_id="same-worker", lease_identity=lease_identity,
                )["status"])
        except BaseException as exc:
            outcomes.append(exc)
            before_link.set()

    thread = Thread(target=first_dispatch, name="first-dispatch")
    thread.start()
    try:
        assert before_link.wait(WAIT_SECONDS)
        assert not outcomes, outcomes
        with pytest.raises(jobs.GenerationJobProcessingError, match="claim retained for review"):
            jobs.process_claimed_generation_job(claimed, worker_id="same-worker")
        with Session(engine) as observer:
            assert job_snapshot(observer, job_id) == before
            assert observer.scalar(select(func.count()).select_from(GenerationExecutionRun)) == 0
        assert calls == []
    finally:
        finish_link.set()
        thread.join(WAIT_SECONDS + 2)
    assert not thread.is_alive()
    assert outcomes == ["success"], outcomes
    assert len(calls) == 1


def test_published_forecast_is_preserved_after_admission(app, monkeypatch):
    existing = save_forecast(sign="aries", day=DAY, text="Existing published text", source="stub")
    original = (existing.id, existing.text, existing.generated_at, existing.published_at)
    provider = Mock(return_value=success())
    install_provider(monkeypatch, provider)
    run = lifecycle.run_daily_generation(target_date=DAY, signs=["aries", "taurus"])
    db.session.refresh(existing)
    assert (existing.id, existing.text, existing.generated_at, existing.published_at) == original
    assert run.status == "success" and run.skipped_items == 1 and run.success_items == 1
    assert provider.call_count == 1


def test_model_index_matches_postgresql_metadata(app):
    expected = next(i for i in GenerationRun.__table__.indexes
                    if i.name == "uq_generation_runs_active_package")
    actual = next(i for i in inspect(db.engine).get_indexes("generation_runs")
                  if i["name"] == expected.name)
    assert actual["unique"] == expected.unique is True
    assert actual["column_names"] == [column.name for column in expected.columns]
    assert "running" in str(actual["dialect_options"]["postgresql_where"])

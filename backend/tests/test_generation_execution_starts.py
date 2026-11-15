""".02b regressions: orchestrator runs only via the STAB-007 PostgreSQL harness."""
import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.orm import Session

from app import db
from app.models import (
    Forecast, GenerationAttempt, GenerationExecution, GenerationExecutionRun,
    GenerationItem, GenerationJob, GenerationRun,
)
from app.providers import ProviderResult
from app.services import generation_execution_service as ledger
from app.services import generation_job_service as jobs
from app.services import generation_service as lifecycle


DAY = date(2026, 11, 17)
SCOPE = dict(target_date=DAY, locale="ru", forecast_type="daily")


def start(session, **overrides):
    values = dict(execution_id=uuid4(), origin="dev_direct", provider="stub", **SCOPE)
    return ledger.record_execution_start(session, **(values | overrides))


def run_row(**overrides):
    return GenerationRun(**(dict(run_type="manual", status="success", **SCOPE) | overrides))


@pytest.fixture(autouse=True)
def bounded_transactions(app):
    def bound(connection):
        connection.exec_driver_sql("SET LOCAL lock_timeout = '2000ms'")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
    event.listen(db.engine, "begin", bound)
    try:
        yield
    finally:
        event.remove(db.engine, "begin", bound)


@pytest.fixture
def fake_provider(monkeypatch):
    calls = []
    class Fake:
        name = "stub"
        model_name = "fake_model"
        def generate(self, request):
            calls.append(request)
            return ProviderResult(
                text="Спокойный день поможет завершить начатые дела.",
                provider="untrusted_response", model_name="untrusted_model",
            )
    monkeypatch.setattr(lifecycle, "get_horoscope_provider", lambda name=None: Fake())
    return calls


def test_writer_replay_preserves_timestamp_and_does_not_commit_caller(app):
    session = db.session()
    caller = run_row(error_message="caller-owned")
    session.add(caller)
    row = start(session)
    original = row.started_at
    again = start(session, execution_id=row.id)
    assert again.id == row.id and again.started_at == original
    assert caller in session.new  # no implicit flush of unrelated pending writes
    with Session(db.engine) as observer:
        assert observer.scalar(select(GenerationExecution.id)) is None
        assert observer.scalar(select(GenerationRun.id)) is None
    session.rollback()
    assert GenerationExecution.query.count() == 0


@pytest.mark.parametrize("changed", [
    {"provider": "openai"}, {"target_date": DAY + timedelta(days=1)},
    {"locale": "uk"}, {"forecast_type": "weekly"},
    {"lease_epoch": 1},
])
def test_writer_rejects_conflicting_uuid_snapshot(app, changed):
    row = start(db.session())
    db.session.commit()
    with pytest.raises(ledger.ExecutionStartError, match="snapshot"):
        start(db.session(), execution_id=row.id, **changed)
    db.session.rollback()
    assert GenerationExecution.query.one().provider == "stub"


def test_link_replay_rejects_rebinding_and_preserves_existing(app):
    row = start(db.session())
    first, second = run_row(), run_row()
    db.session.add_all([first, second])
    db.session.flush()
    link = ledger.link_execution_run(db.session(), execution_id=row.id, run_id=first.id)
    linked_at = link.linked_at
    db.session.commit()
    assert ledger.link_execution_run(
        db.session(), execution_id=row.id, run_id=first.id,
    ).linked_at == linked_at
    with pytest.raises(ledger.ExecutionStartError, match="different run"):
        ledger.link_execution_run(db.session(), execution_id=row.id, run_id=second.id)
    db.session.rollback()
    assert GenerationExecutionRun.query.one().run_id == first.id


def test_utc_rollover_uses_database_time_not_job_or_target_date(app, monkeypatch):
    # Clock seam is private and test-only; runtime API accepts no timestamp.
    before = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)
    after = before + timedelta(seconds=2)
    clock = Mock(side_effect=[before, after])
    monkeypatch.setattr(ledger, "_database_utcnow", clock)
    first = start(db.session())
    second = start(db.session())
    db.session.commit()
    assert first.started_at == before and second.started_at == after
    assert first.target_date == second.target_date == DAY
    assert first.started_at.date() != second.started_at.date()


def test_database_utc_clock_is_used_in_runtime(app):
    lower = db.session.scalar(select(func.clock_timestamp()))
    row = start(db.session())
    upper = db.session.scalar(select(func.clock_timestamp()))
    assert lower <= row.started_at <= upper
    assert row.started_at.utcoffset() == timedelta(0)


def test_direct_execution_and_run_link_commit_before_fake_provider(app, fake_provider):
    run = lifecycle.run_daily_generation(target_date=DAY, provider_name=" STUB ", signs=["aries"])
    assert run.status == "success" and len(fake_provider) == 1
    row = GenerationExecution.query.one()
    assert row.origin == "dev_direct" and row.provider == "stub"
    assert row.job_id is None and row.lease_epoch is None
    assert row.deployment_mode == "test"
    assert GenerationExecutionRun.query.one().run_id == run.id
    assert Forecast.query.one().source == "untrusted_response"


def test_preflight_denial_records_failed_run_not_execution(app, monkeypatch):
    monkeypatch.setenv("GENERATION_PAID_EXECUTION_ENABLED", "0")
    transport = Mock(side_effect=AssertionError("No provider call"))
    monkeypatch.setattr(lifecycle, "get_horoscope_provider", lambda name: type("Fake", (), {
        "name": "openai", "model_name": "fake", "generate": transport,
    })())
    run = lifecycle.run_daily_generation(target_date=DAY, provider_name="openai", signs=["aries"])
    assert run.status == "failed" and "Paid execution denied" in run.error_message
    assert GenerationExecution.query.count() == GenerationExecutionRun.query.count() == 0
    assert GenerationItem.query.count() == GenerationAttempt.query.count() == 0
    transport.assert_not_called()


@pytest.mark.parametrize("provider", ["openai", "future-real"])
def test_production_capability_does_not_activate_execution(app, monkeypatch, provider):
    from app.providers.registry import PROVIDERS, ProviderDefinition
    transport = Mock(side_effect=AssertionError("Production transport forbidden"))
    class Fake:
        name = provider
        model_name = "fake"
        generate = transport
    monkeypatch.setitem(PROVIDERS, provider, ProviderDefinition(Fake, False, True))
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", "production")
    monkeypatch.setitem(app.config, "PRODUCTION_PUBLICATION_PROVIDERS", provider)
    monkeypatch.setenv("GENERATION_PAID_EXECUTION_ENABLED", "1")
    # Reach .02b's independent production activation boundary using only the
    # explicitly registered fake above; real transport is forbidden by the spy.
    monkeypatch.setattr(lifecycle, "require_paid_admission", lambda _: None)
    run = lifecycle.run_daily_generation(target_date=DAY, provider_name=provider, signs=["aries"])
    assert run.status == "failed" and "Production execution is blocked" in run.error_message
    assert GenerationExecution.query.count() == GenerationItem.query.count() == 0
    assert GenerationAttempt.query.count() == Forecast.query.count() == 0
    transport.assert_not_called()


def test_claim_and_execution_are_one_commit_and_dispatch_does_not_double_record(app, fake_provider):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"])
    claimed = jobs.claim_next_generation_job(worker_id="worker")
    identity = ledger.claim_execution_id(claimed)
    with Session(db.engine) as observer:
        assert observer.get(GenerationJob, job.id).status == "running"
        assert observer.get(GenerationExecution, identity).job_id == job.id
        assert observer.get(GenerationExecutionRun, identity) is None
    result = jobs.process_claimed_generation_job(claimed, worker_id="worker")
    assert result["status"] == "success" and len(fake_provider) == 1
    assert GenerationExecution.query.count() == 1
    assert GenerationExecution.query.one().origin == "queue_worker"
    assert GenerationExecutionRun.query.one().execution_id == identity


def test_denied_queue_claim_is_execution_evidence_not_provider_attempt(app, monkeypatch):
    monkeypatch.setenv("GENERATION_PAID_EXECUTION_ENABLED", "0")
    job, _ = jobs.create_generation_job(target_date=DAY, provider="openai", allow_openai=True)
    claimed = jobs.claim_next_generation_job(worker_id="worker")
    result = jobs.process_claimed_generation_job(claimed, worker_id="worker", allow_openai=True)
    assert result["status"] == "failed"
    assert GenerationExecution.query.one().job_id == job.id
    assert GenerationExecutionRun.query.count() == GenerationRun.query.count() == 0
    assert GenerationAttempt.query.count() == 0


def test_manual_retry_preserves_execution_history(app, monkeypatch, fake_provider):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"])
    first = jobs.claim_next_generation_job(worker_id="worker")
    identity = ledger.claim_execution_id(first)
    first.status = "failed"
    db.session.commit()
    jobs.retry_generation_job(job.id)
    second = jobs.claim_next_generation_job(worker_id="worker")
    assert ledger.claim_execution_id(second) != identity
    assert GenerationExecution.query.count() == 2
    assert db.session.get(GenerationExecution, identity).started_at is not None
    result = jobs.process_claimed_generation_job(second, worker_id="worker")
    assert result["status"] == "success" and len(fake_provider) == 1


def test_stale_claim_keeps_history_without_automatic_managed_reclaim(app, fake_provider):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"], max_job_attempts=2)
    first = jobs.claim_next_generation_job(worker_id="same-worker")
    identity = ledger.claim_execution_id(first)
    first.locked_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db.session.commit()
    # .03b intentionally tightens .02b's former age-only reclaim behavior.
    # A committed start without a run link does not prove transport was absent.
    assert jobs.close_stale_running_jobs(stale_after_minutes=60) == 0
    assert jobs.claim_next_generation_job(worker_id="same-worker") is None
    assert GenerationExecution.query.count() == 1
    assert db.session.get(GenerationExecution, identity).job_id == job.id
    assert db.session.get(GenerationJob, job.id).status == "running"
    assert fake_provider == []


def test_repeated_linked_claim_never_dispatches_again(app, fake_provider):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"])
    claimed = jobs.claim_next_generation_job(worker_id="worker")
    identity = ledger.claim_execution_id(claimed)
    completed = lifecycle.run_daily_generation(
        target_date=DAY, signs=["aries"], provider_name="stub", execution_id=identity,
    )
    assert completed.status == "success" and len(fake_provider) == 1
    # Simulates a crash before worker finalization: job still running/owned.
    before = jobs.serialize_generation_job(claimed)
    with pytest.raises(ledger.ExecutionAlreadyStarted, match="already started"):
        jobs.process_claimed_generation_job(claimed, worker_id="worker")
    db.session.refresh(claimed)
    assert jobs.serialize_generation_job(claimed) == before
    assert len(fake_provider) == 1 and GenerationRun.query.count() == 1
    assert GenerationExecution.query.count() == 1


@pytest.mark.parametrize("mode", ["pending", "flushed", "core", "text", "text_select", "cte"])
@pytest.mark.parametrize("entry", ["direct", "claim", "process"])
def test_autonomous_entry_rejects_caller_writes_without_commit_or_rollback(app, monkeypatch, mode, entry):
    job, _ = jobs.create_generation_job(target_date=DAY, signs=["aries"])
    if entry == "process":
        job = jobs.claim_next_generation_job(worker_id="worker")
    unrelated = run_row(error_message="before")
    db.session.add(unrelated)
    db.session.commit()
    if mode in {"pending", "flushed"}:
        unrelated.error_message = "owned"
        if mode == "flushed":
            db.session.flush()
    elif mode == "core":
        db.session.execute(update(GenerationRun).where(GenerationRun.id == unrelated.id).values(error_message="owned"))
    elif mode == "text":
        db.session.execute(text("UPDATE generation_runs SET error_message = 'owned' WHERE id = :id"), {"id": unrelated.id})
    elif mode == "text_select":
        db.session.execute(text("SELECT 1"))
    else:
        cte = update(GenerationRun).where(GenerationRun.id == unrelated.id).values(error_message="owned").returning(GenerationRun.id).cte("changed")
        db.session.execute(select(cte.c.id))
    session = db.session()
    commit, rollback = Mock(wraps=session.commit), Mock(wraps=session.rollback)
    monkeypatch.setattr(session, "commit", commit)
    monkeypatch.setattr(session, "rollback", rollback)
    with pytest.raises(ledger.ExecutionStartError, match="caller-owned"):
        if entry == "direct":
            lifecycle.run_daily_generation(target_date=DAY, signs=["aries"])
        elif entry == "claim":
            jobs.claim_next_generation_job(worker_id="worker")
        else:
            jobs.process_claimed_generation_job(job, worker_id="worker")
    commit.assert_not_called()
    rollback.assert_not_called()
    assert session.in_transaction()
    with Session(db.engine) as observer:
        assert observer.get(GenerationRun, unrelated.id).error_message == "before"
    session.rollback()


@pytest.mark.parametrize("entry", ["direct", "claim"])
def test_failed_start_commit_never_reaches_transport(app, monkeypatch, fake_provider, entry):
    if entry == "claim":
        jobs.create_generation_job(target_date=DAY, signs=["aries"])
    def fail_commit():
        raise RuntimeError("simulated commit failure")
    monkeypatch.setattr(db.session(), "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failure"):
        if entry == "direct":
            lifecycle.run_daily_generation(target_date=DAY, signs=["aries"])
        else:
            jobs.claim_next_generation_job(worker_id="worker")
    assert fake_provider == []
    assert GenerationExecution.query.count() == GenerationExecutionRun.query.count() == 0
    assert GenerationRun.query.count() == 0
    if entry == "claim":
        assert GenerationJob.query.one().status == "queued"


def test_crash_after_start_commit_preserves_start_and_link(app, monkeypatch, fake_provider):
    class Crash(BaseException):
        pass
    def crash(**kwargs):
        raise Crash()
    monkeypatch.setattr(lifecycle, "_process_generation_item", crash)
    with pytest.raises(Crash):
        lifecycle.run_daily_generation(target_date=DAY, signs=["aries"])
    db.session.remove()
    assert GenerationExecution.query.count() == GenerationExecutionRun.query.count() == 1
    assert GenerationRun.query.one().status == "running"
    assert GenerationAttempt.query.count() == 0 and fake_provider == []


def test_legacy_rows_not_backfilled(app, fake_provider):
    old = run_row(target_date=DAY - timedelta(days=1), error_message="legacy")
    db.session.add(old)
    db.session.commit()
    old_id, old_started = old.id, old.started_at
    lifecycle.run_daily_generation(target_date=DAY, signs=["aries"])
    db.session.refresh(old)
    assert (old.id, old.started_at, old.error_message) == (old_id, old_started, "legacy")
    assert GenerationExecution.query.count() == 1
    assert GenerationExecutionRun.query.one().run_id != old.id


def test_stub_text_helper_has_start_without_publication_or_run(app):
    from app.services.forecast_service import generate_horoscope
    assert generate_horoscope("aries", DAY)
    assert GenerationExecution.query.one().origin == "dev_direct"
    assert GenerationExecutionRun.query.count() == GenerationRun.query.count() == 0
    assert Forecast.query.count() == 0


@pytest.mark.parametrize("fake_model", [Mock, lambda: type("Unmapped", (), {})])
def test_fake_model_import_leaves_no_execution_hooks(monkeypatch, fake_model):
    prefix = "_execution_fake_import"
    for suffix in ("", ".models", ".services"):
        module = ModuleType(prefix + suffix)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, module.__name__, module)
    sys.modules[prefix + ".models"].GenerationExecution = fake_model()
    sys.modules[prefix + ".models"].GenerationExecutionRun = Mock()
    name = prefix + ".services.generation_execution_service"
    spec = importlib.util.spec_from_file_location(name, ledger.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    for event_name, callback in (
        ("after_flush", "_remember_flush"), ("do_orm_execute", "_remember_dml"),
        ("after_transaction_end", "_forget_writes"),
    ):
        assert not event.contains(Session, event_name, getattr(module, callback))
    real = run_row()
    db.session.add(real)
    db.session.flush()
    assert real.id is not None
    db.session.rollback()


def test_writer_rejects_unsupported_dialect_without_sql(app):
    session = Mock()
    session.get_bind.return_value.dialect.name = "sqlite"
    with pytest.raises(ledger.ExecutionStartError, match="PostgreSQL"):
        start(session)
    session.execute.assert_not_called()


def test_real_mapped_alias_import_does_not_duplicate_global_hooks(app, monkeypatch):
    prefix = "_execution_mapped_alias"
    for suffix in ("", ".services"):
        module = ModuleType(prefix + suffix)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(sys.modules, prefix + ".models", sys.modules["app.models"])
    name = prefix + ".services.generation_execution_service"
    spec = importlib.util.spec_from_file_location(name, ledger.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    for event_name, callback in (
        ("after_flush", "_remember_flush"), ("do_orm_execute", "_remember_dml"),
        ("after_transaction_end", "_forget_writes"),
    ):
        assert event.contains(Session, event_name, getattr(ledger, callback))
        assert not event.contains(Session, event_name, getattr(module, callback))

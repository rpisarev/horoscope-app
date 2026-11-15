"""PostgreSQL regressions; run only through the serialized disposable harness."""

import importlib.util
import sys
from datetime import date, datetime, timezone
from threading import Barrier, Event, Thread, local
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app import db
from app.models import GenerationJob, GenerationRun
from app.services import generation_job_service as jobs


DAY = date(2026, 6, 15)
WAIT_SECONDS = 8


@pytest.fixture
def sessions(app, monkeypatch):
    # Capture the guarded test engine in app context. Each contender receives an
    # independent Session; no Flask scoped session or connection crosses threads.
    with app.app_context():
        engine = db.engine
    assert engine.dialect.name == "postgresql", "Requires the disposable PostgreSQL harness"
    registry = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(db, "session", registry)
    try:
        yield engine, registry
    finally:
        registry.remove()


def _create(**kwargs):
    return jobs.create_generation_job(target_date=DAY, provider="stub", **kwargs)


@pytest.mark.parametrize("fake_model", ["mock", "unmapped_class"])
def test_fake_model_import_leaves_no_hooks_before_real_flush(sessions, monkeypatch, fake_model):
    engine, registry = sessions
    prefix = "_dedupe_fake_models_regression"
    module = None
    hooks = (("after_flush", "_remember_job_writes"), ("after_transaction_end", "_forget_job_writes"))
    try:
        with monkeypatch.context() as patch:
            for suffix in ("", ".services", ".providers", ".models"):
                dependency = ModuleType(prefix + suffix)
                dependency.__path__ = []
                patch.setitem(sys.modules, dependency.__name__, dependency)
            sys.modules[prefix].db = SimpleNamespace(session=Mock())
            models = sys.modules[prefix + ".models"]
            models.GenerationJob = Mock() if fake_model == "mock" else type("UnmappedJob", (), {})
            models.GenerationRun = Mock()
            models.GenerationExecution = Mock()
            models.GenerationExecutionRun = Mock()
            for suffix in (
                ".providers.publication_policy", ".providers.registry",
                ".services.constants", ".services.generation_service", ".services.sign_service",
                ".services.generation_execution_service",
                ".services.generation_admission_service",
            ):
                patch.setitem(sys.modules, prefix + suffix, sys.modules["app" + suffix])
            name = prefix + ".services.generation_job_service"
            spec = importlib.util.spec_from_file_location(name, jobs.__file__)
            module = importlib.util.module_from_spec(spec)
            patch.setitem(sys.modules, name, module)
            spec.loader.exec_module(module)
            registered = [
                event.contains(Session, name, getattr(module, callback))
                for name, callback in hooks
            ]

        # Reproduce the suite order: the fake namespace is gone, then an
        # unrelated real ORM flush must succeed without a leaked fake listener.
        assert prefix not in sys.modules
        row = _run(error_message="real flush after fake-model import")
        registry.add(row)
        registry.flush()
        assert row.id is not None
        assert registered == [False, False]
        registry.rollback()
        with Session(engine) as observer:
            assert observer.scalars(select(GenerationRun)).all() == []
    finally:
        # Even on the unfixed implementation this regression must not poison
        # later tests or the fixture's cleanup with its own imported listeners.
        if module is not None:
            for name, callback in hooks:
                listener = getattr(module, callback, None)
                if listener is not None and event.contains(Session, name, listener):
                    event.remove(Session, name, listener)
        registry.rollback()


def test_real_flush_listener_keeps_captured_mapped_class(sessions, monkeypatch):
    _, registry = sessions
    assert event.contains(Session, "after_flush", jobs._remember_job_writes)
    assert event.contains(Session, "after_transaction_end", jobs._forget_job_writes)
    job = GenerationJob(
        job_type="backfill", status="queued", target_date=DAY,
        locale="ru", forecast_type="daily", provider="stub", dedupe_key="captured-model",
    )
    registry.add(job)
    with monkeypatch.context() as patch:
        patch.setattr(jobs, "GenerationJob", Mock())
        registry.flush()
    record = registry.info[jobs._JOB_WRITES_INFO_KEY]
    assert record["ids"] == {job.id}
    assert record["keys"] == {"captured-model"}
    registry.rollback()
    assert jobs._JOB_WRITES_INFO_KEY not in registry.info


def _race(
    sessions, loser_action, *, commit, finalize=False, rounds=1, retry=False,
    expected_conflicts=None,
):
    """Both prechecks see no active row, then PostgreSQL arbitrates the write.

    The designated winner inserts before the loser executes INSERT/UPDATE, but
    cannot commit until the loser reaches that statement. For finalization races
    the real 23505 is held in handle_error until the winner commits final status.
    No sleeps, polling, provider execution, third observer, or daemon threads.
    """
    engine, registry = sessions
    roles = local()
    barrier = Barrier(2, timeout=WAIT_SECONDS)
    inserted = [Event() for _ in range(rounds)]
    loser_writing = [Event() for _ in range(rounds)]
    conflicted = [Event() for _ in range(rounds)]
    finalized = [Event() for _ in range(rounds)]
    writes = {"winner": 0, "loser": 0}
    conflicts = []
    outcomes = {}

    def bounded_transaction(connection):
        if getattr(roles, "name", None):
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout = '4000ms'")

    def before_write(connection, cursor, statement, parameters, context, executemany):
        role = getattr(roles, "name", None)
        prefix = "UPDATE generation_jobs" if role == "loser" and retry else "INSERT INTO generation_jobs"
        if role is None or not statement.startswith(prefix):
            return
        index = writes[role]
        writes[role] += 1
        if finalize and rounds == 1 and role == "loser" and index == 1:
            return  # The winner is final; the one allowed retry has no competitor.
        assert index < rounds, "Dedupe exceeded its bounded write attempts"
        barrier.wait()
        if role == "loser":
            assert inserted[index].wait(WAIT_SECONDS), "Winner did not insert"
            loser_writing[index].set()

    def after_write(connection, cursor, statement, parameters, context, executemany):
        if getattr(roles, "name", None) == "winner" and statement.startswith("INSERT INTO generation_jobs"):
            index = writes["winner"] - 1
            inserted[index].set()
            assert loser_writing[index].wait(WAIT_SECONDS), "Loser did not attempt write"

    def on_error(context):
        if getattr(roles, "name", None) != "loser":
            return
        original = context.original_exception
        conflicts.append((
            getattr(original, "sqlstate", None),
            getattr(getattr(original, "diag", None), "constraint_name", None),
        ))
        if finalize:
            index = len(conflicts) - 1
            conflicted[index].set()
            assert finalized[index].wait(WAIT_SECONDS), "Winner did not finalize"

    def winner_action():
        ids = []
        for index in range(rounds):
            job, created = _create(commit=commit)
            assert created
            if not commit:
                registry.commit()
            ids.append(job.id)
            if finalize:
                assert conflicted[index].wait(WAIT_SECONDS), "Expected real unique violation"
                job.status = jobs.JOB_STATUS_SUCCESS
                registry.commit()
                finalized[index].set()
        return ids

    def run(role, action):
        roles.name = role
        try:
            outcomes[role] = (True, action())
        except BaseException as exc:
            outcomes[role] = (False, exc)
        finally:
            # remove() closes/rolls back even when a barrier/assertion fails.
            registry.remove()
            roles.name = None

    listeners = [
        ("begin", bounded_transaction),
        ("before_cursor_execute", before_write),
        ("after_cursor_execute", after_write),
        ("handle_error", on_error),
    ]
    threads = [
        Thread(target=run, args=("winner", winner_action)),
        Thread(target=run, args=("loser", loser_action)),
    ]
    for name, callback in listeners:
        event.listen(engine, name, callback)
    started = []
    try:
        for thread in threads:
            thread.start()
            started.append(thread)
        for thread in started:
            thread.join(WAIT_SECONDS + 2)
    finally:
        barrier.abort()
        for signal in inserted + loser_writing + conflicted + finalized:
            signal.set()
        for thread in started:
            thread.join(WAIT_SECONDS + 2)
        for name, callback in listeners:
            event.remove(engine, name, callback)
    assert all(not thread.is_alive() for thread in started), "DB timeout/thread cleanup failed"
    for ok, result in outcomes.values():
        if not ok:
            raise result
    assert len(outcomes) == 2
    conflict_count = rounds if expected_conflicts is None else expected_conflicts
    assert conflicts == [("23505", jobs.ACTIVE_DEDUPE_CONSTRAINT)] * conflict_count
    return outcomes["winner"][1], outcomes["loser"][1], writes


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("skip_duplicate", [True, False])
def test_two_session_exact_key_conflict(sessions, commit, skip_duplicate):
    engine, registry = sessions

    def loser():
        if skip_duplicate:
            job, created = _create(commit=commit, skip_duplicate=True)
            assert not created
            assert job.status in jobs.ACTIVE_JOB_STATUSES
            result = job.id
        else:
            with pytest.raises(jobs.GenerationJobValidationError, match="Active generation job already exists: id="):
                _create(commit=commit, skip_duplicate=False)
            result = None
        assert registry().is_active
        return result

    winner_ids, duplicate_id, writes = _race(sessions, loser, commit=commit)
    assert duplicate_id == (winner_ids[0] if skip_duplicate else None)
    assert writes == {"winner": 1, "loser": 1}
    with Session(engine) as observer:
        rows = observer.scalars(select(GenerationJob)).all()
        assert [(row.id, row.status) for row in rows] == [(winner_ids[0], "queued")]


@pytest.mark.parametrize("commit", [True, False])
def test_two_session_different_keys_both_create(sessions, commit):
    engine, registry = sessions

    def loser():
        job, created = jobs.create_generation_job(target_date=date(2026, 6, 16), commit=commit)
        assert created
        if not commit:
            registry.commit()
        return job.id

    winner_ids, other_id, _ = _race(sessions, loser, commit=commit, expected_conflicts=0)
    assert other_id not in winner_ids
    with Session(engine) as observer:
        assert len(observer.scalars(select(GenerationJob)).all()) == 2


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("skip_duplicate", [True, False])
def test_winner_finalizes_before_reload_allows_one_new_insert(sessions, commit, skip_duplicate):
    engine, registry = sessions

    def loser():
        job, created = _create(commit=commit, skip_duplicate=skip_duplicate)
        assert created
        assert job.status == "queued"
        if not commit:
            registry.commit()
        return job.id

    winner_ids, new_id, writes = _race(sessions, loser, commit=commit, finalize=True)
    assert new_id not in winner_ids
    with Session(engine) as observer:
        rows = observer.scalars(select(GenerationJob).order_by(GenerationJob.id)).all()
        assert [(row.id, row.status) for row in rows] == [
            (winner_ids[0], "success"), (new_id, "queued")
        ]
    assert writes == {"winner": 1, "loser": 2}


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("skip_duplicate", [True, False])
def test_repeated_winner_finalization_is_bounded(sessions, commit, skip_duplicate):
    def loser():
        with pytest.raises(jobs.GenerationJobValidationError, match="changed during deduplication"):
            _create(commit=commit, skip_duplicate=skip_duplicate)

    _, _, writes = _race(sessions, loser, commit=commit, finalize=True, rounds=2)
    assert writes == {"winner": 2, "loser": 2}


def _run(**kwargs):
    # These are unrelated/history rows for transaction ownership tests, not
    # concurrent active package executions under .03b's new invariant.
    return GenerationRun(**(dict(run_type="manual", target_date=DAY, status="failed") | kwargs))


def _hide_first_precheck(monkeypatch):
    original = jobs._active_job_for_key
    calls = []

    def lookup(session, key):
        calls.append(key)
        if len(calls) == 1:
            return None
        return original(session, key)

    monkeypatch.setattr(jobs, "_active_job_for_key", lookup)
    return calls


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("skip_duplicate", [True, False])
@pytest.mark.parametrize("flushed", [True, False])
def test_conflict_preserves_all_unrelated_caller_writes(sessions, monkeypatch, commit, skip_duplicate, flushed):
    engine, registry = sessions
    winner, _ = _create()
    edited, deleted = _run(error_message="original"), _run(error_message="delete me")
    registry.add_all([edited, deleted])
    registry.commit()
    edited_id, deleted_id = edited.id, deleted.id
    # Delete cascades can load relationships and autoflush. Do that before
    # staging the writes whose unflushed state this test must preserve.
    registry.delete(deleted)
    pending = _run(error_message="new")
    registry.add(pending)
    edited.error_message = "caller edit"
    if flushed:
        registry.flush()
    else:
        assert pending in registry.new
        assert edited in registry.dirty
        assert deleted in registry.deleted
    parent = registry().get_transaction()
    calls = _hide_first_precheck(monkeypatch)

    if skip_duplicate:
        duplicate, created = _create(commit=commit)
        assert duplicate.id == winner.id and not created
    else:
        with pytest.raises(jobs.GenerationJobValidationError, match="already exists"):
            _create(commit=commit, skip_duplicate=False)
    assert len(calls) == 2  # Real INSERT conflict, then reload.
    assert registry().get_transaction() is parent
    assert parent.is_active
    assert edited.error_message == "caller edit"
    if commit and not flushed:
        assert pending in registry.new
        assert edited in registry.dirty
        assert deleted in registry.deleted
    with Session(engine) as observer:
        assert observer.get(GenerationRun, edited_id).error_message == "original"
        assert observer.get(GenerationRun, deleted_id) is not None
        assert len(observer.scalars(select(GenerationRun)).all()) == 2
    registry.commit()
    with Session(engine) as observer:
        assert observer.get(GenerationRun, pending.id).error_message == "new"
        assert observer.get(GenerationRun, edited_id).error_message == "caller edit"
        assert observer.get(GenerationRun, deleted_id) is None


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("flushed", [True, False])
def test_creation_commit_ownership_and_attached_result(sessions, commit, flushed):
    engine, registry = sessions
    pending = _run(error_message="caller owned")
    registry.add(pending)
    if flushed:
        registry.flush()
    parent = registry().get_transaction()
    job, created = _create(commit=commit, signs=["aries"])
    assert created and job in registry()
    assert registry().get_transaction() is parent
    with Session(engine) as observer:
        assert observer.scalars(select(GenerationRun)).all() == []
        assert (observer.get(GenerationJob, job.id) is not None) is commit
    job_id = job.id
    registry.rollback()
    with Session(engine) as observer:
        assert observer.scalars(select(GenerationRun)).all() == []
        assert (observer.get(GenerationJob, job_id) is not None) is commit
    if commit:
        job.status = "success"
        registry.commit()
        with Session(engine) as observer:
            assert observer.get(GenerationJob, job_id).status == "success"


@pytest.mark.parametrize("commit", [True, False])
def test_unrelated_unique_violation_propagates_without_losing_parent(sessions, commit):
    engine, registry = sessions
    existing, _ = _create()
    pending = _run(error_message="parent")
    registry.add(pending)

    def force_pk_conflict(mapper, connection, target):
        if target.created_by == "force-pk-conflict":
            target.id = existing.id

    event.listen(GenerationJob, "before_insert", force_pk_conflict)
    try:
        with pytest.raises(IntegrityError) as error:
            jobs.create_generation_job(target_date=date(2026, 6, 16), commit=commit, created_by="force-pk-conflict")
    finally:
        event.remove(GenerationJob, "before_insert", force_pk_conflict)
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "generation_jobs_pkey"
    assert registry().is_active
    with Session(engine) as observer:
        assert observer.scalars(select(GenerationRun)).all() == []
    registry.commit()
    with Session(engine) as observer:
        assert observer.get(GenerationRun, pending.id).error_message == "parent"


def test_begin_nested_parent_flush_failure_is_not_normalized(sessions, monkeypatch):
    _, registry = sessions
    first = _run()
    registry.add(first)
    registry.commit()
    duplicate = _run(id=first.id)
    registry.expunge(first)
    registry.add(duplicate)

    def unexpected_normalization(*args):
        pytest.fail("A failure before the savepoint must not reach the dedupe handler")

    monkeypatch.setattr(jobs, "_is_active_dedupe_conflict", unexpected_normalization)
    with pytest.raises(IntegrityError) as error:
        _create(commit=False)
    assert error.value.orig.diag.constraint_name == "generation_runs_pkey"
    registry.rollback()  # The caller owns recovery of its own invalid pending write.


@pytest.mark.parametrize("sqlstate,constraint,dialect,expected", [
    ("23505", "uq_generation_jobs_active_dedupe_key", "postgresql", True),
    ("23503", "uq_generation_jobs_active_dedupe_key", "postgresql", False),
    ("23505", "generation_jobs_pkey", "postgresql", False),
    ("23505", None, "postgresql", False),
    (None, "uq_generation_jobs_active_dedupe_key", "postgresql", False),
    ("23505", "uq_generation_jobs_active_dedupe_key", "sqlite", False),
])
def test_only_exact_postgres_constraint_is_normalized(sqlstate, constraint, dialect, expected):
    original = Exception("Active generation job already exists")
    original.sqlstate = sqlstate
    original.diag = SimpleNamespace(constraint_name=constraint)
    session = SimpleNamespace(get_bind=lambda **kwargs: SimpleNamespace(dialect=SimpleNamespace(name=dialect)))
    assert jobs._is_active_dedupe_conflict(session, IntegrityError(None, None, original)) is expected


def _failed_job(registry, *, status="failed", batch_id="retry-batch", target_date=DAY):
    job, _ = jobs.create_generation_job(target_date=target_date, batch_id=batch_id)
    run = _run()
    registry.add(run)
    registry.flush()
    job.status = status
    job.run_id = run.id
    job.error_message = "original failure"
    job.attempt_count = 3
    job.started_at = job.finished_at = job.locked_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    job.locked_by = "previous-worker"
    registry.commit()
    return job


def _failure_snapshot(job):
    return {name: getattr(job, name) for name in (
        "status", "run_id", "error_message", "attempt_count", "started_at",
        "finished_at", "locked_at", "locked_by",
    )}


@pytest.mark.parametrize("status", ["failed", "partial_failed"])
@pytest.mark.parametrize("raced", [False, True])
def test_single_retry_collision_retains_failed_job(sessions, monkeypatch, status, raced):
    engine, registry = sessions
    failed = _failed_job(registry, status=status)
    expected = _failure_snapshot(failed)
    active, _ = _create()
    if raced:
        _hide_first_precheck(monkeypatch)
    pending = _run(error_message="caller pending")
    registry.add(pending)
    with pytest.raises(jobs.GenerationJobValidationError, match=f"already exists: id={active.id}"):
        jobs.retry_generation_job(failed.id)
    assert pending in registry.new
    with Session(engine) as observer:
        assert _failure_snapshot(observer.get(GenerationJob, failed.id)) == expected
        assert observer.get(GenerationJob, active.id).status == "queued"


@pytest.mark.parametrize("batch", [False, True])
def test_two_session_retry_collision(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    failed_id = failed.id
    expected = _failure_snapshot(failed)
    registry.remove()

    def loser():
        if batch:
            result = jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
            assert result["retried_count"] == 0
            assert result["skipped_count"] == 1
            assert result["skipped_status_counts"] == {"failed": 1}
        else:
            with pytest.raises(jobs.GenerationJobValidationError, match="already exists"):
                jobs.retry_generation_job(failed_id)

    _race(sessions, loser, commit=True, retry=True)
    with Session(engine) as observer:
        assert _failure_snapshot(observer.get(GenerationJob, failed_id)) == expected


@pytest.mark.parametrize("raced", [False, True])
def test_batch_retry_skips_collision_and_commits_other_members(sessions, monkeypatch, raced):
    engine, registry = sessions
    failed = _failed_job(registry)
    expected = _failure_snapshot(failed)
    active, _ = _create()
    other = _failed_job(registry, status="partial_failed", target_date=date(2026, 6, 16))
    pending = _run(error_message="parent")
    registry.add(pending)
    registry.flush()
    parent = registry().get_transaction()
    if raced:
        _hide_first_precheck(monkeypatch)
    result = jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
    assert registry().get_transaction() is parent
    assert result["retried_count"] == 1
    assert result["skipped_count"] == 1
    assert result["skipped_status_counts"] == {"failed": 1}
    assert result["batch_status"]["status_counts"]["failed"] == 1
    assert result["batch_status"]["status_counts"]["queued"] == 1
    with Session(engine) as observer:
        assert observer.get(GenerationRun, pending.id) is None
        assert _failure_snapshot(observer.get(GenerationJob, failed.id)) == expected
        retried = observer.get(GenerationJob, other.id)
        assert retried.status == "queued" and retried.attempt_count == 3
        assert all(getattr(retried, name) is None for name in (
            "run_id", "error_message", "started_at", "finished_at", "locked_at", "locked_by"
        ))
        assert observer.get(GenerationJob, active.id).status == "queued"


@pytest.mark.parametrize("batch", [False, True])
def test_successful_retry_preserves_unrelated_pending_work(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    pending = _run(error_message="parent")
    registry.add(pending)
    if batch:
        result = jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
        assert result["retried_count"] == 1
    else:
        assert jobs.retry_generation_job(failed.id).status == "queued"
    assert pending in registry.new
    with Session(engine) as observer:
        assert observer.get(GenerationJob, failed.id).status == "queued"
    registry.rollback()


@pytest.mark.parametrize("batch", [False, True])
def test_retry_does_not_overwrite_pending_edits_to_same_job(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    failed.error_message = "uncommitted caller edit"
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        if batch:
            jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
        else:
            jobs.retry_generation_job(failed.id)
    assert failed.error_message == "uncommitted caller edit"
    with Session(engine) as observer:
        assert observer.get(GenerationJob, failed.id).error_message == "original failure"


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("skip_duplicate", [True, False])
def test_duplicate_lookup_preserves_pending_priority_edit(sessions, commit, skip_duplicate):
    engine, registry = sessions
    duplicate, _ = _create()
    duplicate.priority = 73
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        _create(commit=commit, skip_duplicate=skip_duplicate)
    assert duplicate.priority == 73
    assert duplicate in registry.dirty
    with Session(engine) as observer:
        assert observer.get(GenerationJob, duplicate.id).priority == 0
    registry.commit()
    with Session(engine) as observer:
        assert observer.get(GenerationJob, duplicate.id).priority == 73


def test_private_creation_rejects_callers_flushed_same_key_insert(sessions):
    engine, registry = sessions
    staged, created = _create(commit=False)
    assert created and staged not in registry.new
    parent = registry().get_transaction()
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        _create(commit=True)
    assert registry().get_transaction() is parent and parent.is_active
    with Session(engine) as observer:
        assert observer.get(GenerationJob, staged.id) is None
    registry.commit()
    reused, created = _create(commit=True)
    assert reused.id == staged.id and not created


def test_job_write_tracking_survives_savepoint_rollback_until_outer_end(sessions):
    engine, registry = sessions
    caller_savepoint = registry.begin_nested()
    staged, _ = _create(commit=False)
    staged_id = staged.id
    caller_savepoint.rollback()
    parent = registry().get_transaction()
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        _create(commit=True)
    assert parent.is_active
    with Session(engine) as observer:
        assert observer.get(GenerationJob, staged_id) is None
    registry.rollback()
    replacement, created = _create(commit=True)
    assert created
    with Session(engine) as observer:
        assert observer.get(GenerationJob, replacement.id).status == "queued"


@pytest.mark.parametrize("expire_key", [True, False])
def test_private_creation_rejects_callers_flushed_same_key_update(sessions, expire_key):
    engine, registry = sessions
    staged, _ = _create()
    if expire_key:
        registry.expire(staged, ["dedupe_key"])
    staged.priority = 43
    registry.flush()
    assert staged not in registry.dirty
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        _create(commit=True)
    assert staged.priority == 43
    with Session(engine) as observer:
        assert observer.get(GenerationJob, staged.id).priority == 0
    registry.rollback()
    reused, created = _create(commit=True)
    assert reused.priority == 0 and not created


@pytest.mark.parametrize("batch", [True, False])
@pytest.mark.parametrize("delete", [True, False])
def test_private_retry_rejects_callers_flushed_target_write(sessions, batch, delete):
    engine, registry = sessions
    staged = _failed_job(registry)
    job_id = staged.id
    if delete:
        registry.delete(staged)
    else:
        staged.error_message = "flushed caller edit"
    registry.flush()
    parent = registry().get_transaction()
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        if batch:
            jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
        else:
            jobs.retry_generation_job(job_id)
    assert registry().get_transaction() is parent and parent.is_active
    with Session(engine) as observer:
        stored = observer.get(GenerationJob, job_id)
        assert stored.status == "failed" and stored.error_message == "original failure"


@pytest.mark.parametrize("batch", [True, False])
def test_private_retry_rejects_callers_flushed_active_duplicate(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    active, created = _create(commit=False)
    assert created and active.id != failed.id
    with pytest.raises(jobs.GenerationJobValidationError, match="Commit pending changes"):
        if batch:
            jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
        else:
            jobs.retry_generation_job(failed.id)
    with Session(engine) as observer:
        assert observer.get(GenerationJob, failed.id).status == "failed"
        assert observer.get(GenerationJob, active.id) is None
    registry.rollback()


@pytest.mark.parametrize("commit", [True, False])
def test_different_key_caller_job_write_is_preserved(sessions, commit):
    engine, registry = sessions
    unrelated, _ = jobs.create_generation_job(target_date=date(2026, 6, 16))
    unrelated.priority = 99
    registry.flush()
    created_job, created = _create(commit=commit)
    assert created and unrelated.priority == 99
    with Session(engine) as observer:
        assert observer.get(GenerationJob, unrelated.id).priority == 0
        assert (observer.get(GenerationJob, created_job.id) is not None) is commit
    registry.commit()
    with Session(engine) as observer:
        assert observer.get(GenerationJob, unrelated.id).priority == 99


@pytest.mark.parametrize("batch", [False, True])
def test_two_session_retry_winner_finalizes_before_reload(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    failed_id = failed.id
    registry.remove()

    def loser():
        if batch:
            result = jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
            assert result["retried_count"] == 1
            assert result["skipped_count"] == 0
        else:
            assert jobs.retry_generation_job(failed_id).status == "queued"

    _, _, writes = _race(sessions, loser, commit=True, retry=True, finalize=True)
    assert writes == {"winner": 1, "loser": 2}
    with Session(engine) as observer:
        assert observer.get(GenerationJob, failed_id).status == "queued"


@pytest.mark.parametrize("batch", [False, True])
def test_retry_unrelated_integrity_error_propagates(sessions, batch):
    engine, registry = sessions
    failed = _failed_job(registry)
    expected = _failure_snapshot(failed)
    pending = _run(error_message="caller pending")
    registry.add(pending)

    def force_foreign_key_error(mapper, connection, target):
        if target.id == failed.id and target.status == "queued":
            target.run_id = -1

    event.listen(GenerationJob, "before_update", force_foreign_key_error)
    try:
        with pytest.raises(IntegrityError) as error:
            if batch:
                jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
            else:
                jobs.retry_generation_job(failed.id)
    finally:
        event.remove(GenerationJob, "before_update", force_foreign_key_error)
    assert error.value.orig.sqlstate == "23503"
    assert error.value.orig.diag.constraint_name == "fk_generation_jobs_run_id_generation_runs"
    assert pending in registry.new
    with Session(engine) as observer:
        assert _failure_snapshot(observer.get(GenerationJob, failed.id)) == expected


def test_batch_with_two_failed_members_of_same_key_retries_one(sessions):
    engine, registry = sessions
    first = _failed_job(registry)
    second = _failed_job(registry, status="partial_failed")
    expected = _failure_snapshot(second)
    result = jobs.retry_failed_generation_job_batch(batch_id="retry-batch")
    assert result["retried_count"] == 1
    assert result["skipped_count"] == 1
    assert result["skipped_status_counts"] == {"partial_failed": 1}
    with Session(engine) as observer:
        assert observer.get(GenerationJob, first.id).status == "queued"
        assert _failure_snapshot(observer.get(GenerationJob, second.id)) == expected


@pytest.mark.parametrize("batch", [False, True])
def test_admin_retry_collision_keeps_existing_response_contract(app, client, batch):
    with app.app_context():
        failed = _failed_job(db.session)
        failed_id = failed.id
        _create()
    old = {key: app.config[key] for key in ("ADMIN_API_ENABLED", "ADMIN_API_TOKEN")}
    app.config.update(ADMIN_API_ENABLED=True, ADMIN_API_TOKEN="test-admin-token")
    path = (
        "/api/admin/generation/jobs/batches/retry-batch/retry-failed"
        if batch else f"/api/admin/generation/jobs/{failed_id}/retry"
    )
    try:
        response = client.post(path, headers={"Authorization": "Bearer test-admin-token"})
    finally:
        app.config.update(old)
    if batch:
        assert response.status_code == 200
        assert response.get_json()["retried_count"] == 0
        assert response.get_json()["skipped_status_counts"] == {"failed": 1}
    else:
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "bad_admin_generation_request"

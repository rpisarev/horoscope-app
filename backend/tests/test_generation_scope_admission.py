"""Admission-boundary regressions; run only through orchestrator STAB-007."""

from datetime import date, timedelta
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app import db
from app.models import GenerationRun
from app.services import generation_admission_service as admission


DAY = date(2026, 11, 17)
SCOPE = admission.GenerationPackageScope(DAY, "ru", "daily")
WAIT_SECONDS = 8


@pytest.fixture
def engine(app):
    with app.app_context():
        yield db.engine


def new_run(scope=SCOPE, **fields):
    return GenerationRun(**{
        "target_date": scope.target_date,
        "locale": scope.locale,
        "forecast_type": scope.forecast_type,
        "run_type": "manual",
        "status": "running",
        **fields,
    })


def retry_count(session):
    return session.scalar(select(func.count()).select_from(GenerationRun).where(
        GenerationRun.target_date == SCOPE.target_date,
        GenerationRun.locale == SCOPE.locale,
        GenerationRun.forecast_type == SCOPE.forecast_type,
        GenerationRun.run_type == "retry",
    ))


def test_lock_key_is_deterministic_exact_scope_only():
    assert SCOPE.lock_key() == admission.GenerationPackageScope(DAY, "ru", "daily").lock_key()
    variants = [
        admission.GenerationPackageScope(DAY + timedelta(days=1), "ru", "daily"),
        admission.GenerationPackageScope(DAY, "uk", "daily"),
        admission.GenerationPackageScope(DAY, "ru", "weekly"),
        admission.GenerationPackageScope(DAY, "RU", "daily"),
        admission.GenerationPackageScope(DAY, "ru ", "daily"),
    ]
    assert len({SCOPE.lock_key(), *(scope.lock_key() for scope in variants)}) == 6
    assert -(2**63) <= SCOPE.lock_key() < 2**63


@pytest.mark.parametrize("changes", [
    {"target_date": "2026-11-17"}, {"locale": ""}, {"locale": None},
    {"forecast_type": " "}, {"forecast_type": None},
])
def test_invalid_scope_is_rejected_before_database(changes):
    with pytest.raises(ValueError):
        admission.GenerationPackageScope(**{
            "target_date": DAY, "locale": "ru", "forecast_type": "daily", **changes,
        })


def test_unsupported_dialect_is_rejected_without_queries():
    session = Mock(new=set(), dirty=set(), deleted=set())
    session.get_transaction.return_value = SimpleNamespace(is_active=True)
    connection = Mock(dialect=SimpleNamespace(name="sqlite"))
    session.connection.return_value = connection
    with pytest.raises(admission.GenerationAdmissionConfigurationError, match="PostgreSQL"):
        with admission.package_admission(session, scope=SCOPE):
            pytest.fail("unsupported admission entered")
    connection.execute.assert_not_called()
    session.begin_nested.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_missing_caller_transaction_is_rejected_without_autobegin(engine):
    with Session(engine) as session:
        assert session.get_transaction() is None
        with pytest.raises(admission.GenerationAdmissionConfigurationError,
                           match="active caller-owned transaction"):
            with admission.package_admission(session, scope=SCOPE):
                pytest.fail("missing transaction admitted")
        assert session.get_transaction() is None
        assert not session.in_transaction()


@pytest.mark.parametrize("mode", ["sqlalchemy_option", "raw_dbapi"])
def test_dbapi_autocommit_rejected_even_when_read_committed_is_reported(engine, mode):
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        previous = raw.autocommit
        try:
            if mode == "sqlalchemy_option":
                connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            else:
                raw.autocommit = True
            assert raw.autocommit is True
            assert connection.get_isolation_level() == "READ COMMITTED"
            with Session(bind=connection) as session, session.begin():
                transaction = session.get_transaction()
                with pytest.raises(admission.GenerationAdmissionConfigurationError,
                                   match="autocommit to be disabled"):
                    with admission.package_admission(session, scope=SCOPE):
                        pytest.fail("autocommit admitted")
                assert session.get_transaction() is transaction
                assert transaction.is_active
                assert not session.in_nested_transaction()
        finally:
            if mode == "raw_dbapi":
                raw.autocommit = previous


@pytest.mark.parametrize("value", [True, None, "false", 0])
def test_unverified_dbapi_autocommit_fails_before_isolation_queries(value):
    session = Mock(new=set(), dirty=set(), deleted=set())
    session.get_transaction.return_value = SimpleNamespace(is_active=True)
    connection = Mock(dialect=SimpleNamespace(name="postgresql"))
    connection.connection = SimpleNamespace(driver_connection=SimpleNamespace(autocommit=value))
    session.connection.return_value = connection
    with pytest.raises(admission.GenerationAdmissionConfigurationError, match="autocommit"):
        with admission.package_admission(session, scope=SCOPE):
            pytest.fail("unverified DBAPI state admitted")
    connection.get_isolation_level.assert_not_called()
    connection.execute.assert_not_called()
    session.begin_nested.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE", "READ UNCOMMITTED"])
def test_non_read_committed_isolation_rejected_without_mutation(engine, isolation):
    with engine.connect().execution_options(isolation_level=isolation) as connection:
        with Session(bind=connection) as session:
            # Establish an old transaction snapshot before admission.
            assert retry_count(session) == 0
            transaction = session.get_transaction()
            with pytest.raises(admission.GenerationAdmissionConfigurationError,
                               match="READ COMMITTED"):
                with admission.package_admission(session, scope=SCOPE):
                    pytest.fail("unsupported snapshot entered admission")
            assert session.get_transaction() is transaction
            assert transaction.is_active
            assert session.scalar(select(func.count()).select_from(GenerationRun)) == 0


def test_repeatable_read_stale_retry_snapshot_cannot_admit(engine):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as stale:
            assert retry_count(stale) == 0
            with Session(engine) as winner, winner.begin():
                with admission.package_admission(winner, scope=SCOPE):
                    winner.add(new_run(run_type="retry", status="success"))
            assert retry_count(stale) == 0, "adversarial old snapshot must be real"
            with pytest.raises(admission.GenerationAdmissionConfigurationError):
                with admission.package_admission(stale, scope=SCOPE):
                    pytest.fail("old retry snapshot admitted")
    with Session(engine) as observer:
        assert retry_count(observer) == 1


def test_read_committed_retry_count_is_rechecked_after_package_lock(engine):
    with Session(engine) as contender:
        assert retry_count(contender) == 0  # Advisory earlier observation.
        with Session(engine) as winner, winner.begin():
            with admission.package_admission(winner, scope=SCOPE):
                winner.add(new_run(run_type="retry", status="success"))
        with admission.package_admission(contender, scope=SCOPE):
            assert retry_count(contender) == 1  # Final admission authority.
        contender.commit()
    with Session(engine) as observer:
        assert retry_count(observer) == 1


def test_pending_caller_work_is_rejected_without_implicit_flush(engine):
    with Session(engine) as session:
        unrelated = new_run(status="success")
        session.add(unrelated)
        transaction = session.get_transaction()
        with pytest.raises(admission.GenerationAdmissionConfigurationError, match="flushed"):
            with admission.package_admission(session, scope=SCOPE):
                pytest.fail("unflushed transaction entered admission")
        assert unrelated in session.new
        assert unrelated.id is None
        assert session.get_transaction() is transaction
        assert transaction.is_active
        with Session(engine) as observer:
            assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 0


def test_success_does_not_commit_unrelated_flushed_outer_work(engine):
    with Session(engine) as session:
        unrelated = new_run(status="success", error_message="caller-owned")
        session.add(unrelated)
        session.flush()
        transaction = session.get_transaction()
        with admission.package_admission(session, scope=SCOPE):
            admitted = new_run()
            session.add(admitted)
        assert admitted.id is not None
        assert session.get_transaction() is transaction
        with Session(engine) as observer:
            assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 0
        session.rollback()
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 0


def test_busy_preserves_unrelated_flushed_outer_work(engine):
    with Session(engine) as winner, winner.begin():
        winner.add(new_run())
    with Session(engine) as session:
        unrelated = new_run(status="success", error_message="caller-owned")
        session.add(unrelated)
        session.flush()
        transaction = session.get_transaction()
        with pytest.raises(admission.GenerationScopeBusy):
            with admission.package_admission(session, scope=SCOPE):
                pytest.fail("already active admitted")
        assert session.get_transaction() is transaction
        assert transaction.is_active
        assert session.get(GenerationRun, unrelated.id).error_message == "caller-owned"
        with Session(engine) as observer:
            assert observer.get(GenerationRun, unrelated.id) is None
        session.commit()
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 2


@pytest.mark.parametrize("phase", ["uncommitted_admission", "committed_running"])
def test_two_sessions_have_one_active_package_and_nonblocking_loser(engine, phase):
    admitted = Event()
    release = Event()
    outcomes = []

    def winner():
        try:
            with Session(engine) as session:
                session.begin()
                with admission.package_admission(session, scope=SCOPE):
                    session.add(new_run())
                    session.flush()
                    if phase == "uncommitted_admission":
                        admitted.set()
                        assert release.wait(WAIT_SECONDS)
                session.commit()
                if phase == "committed_running":
                    admitted.set()
                    assert release.wait(WAIT_SECONDS)
            outcomes.append("completed")
        except BaseException as exc:
            outcomes.append(exc)
            admitted.set()

    thread = Thread(target=winner)
    thread.start()
    try:
        assert admitted.wait(WAIT_SECONDS)
        assert not outcomes, outcomes
        with Session(engine) as contender:
            contender.begin()
            with pytest.raises(admission.GenerationScopeBusy) as error:
                with admission.package_admission(contender, scope=SCOPE):
                    pytest.fail("loser entered run/provider boundary")
            assert error.value.retryable is False
            assert error.value.code == "generation_scope_busy"
            assert contender.is_active
        # Different package does not wait for the first provider/transaction.
        other = admission.GenerationPackageScope(DAY + timedelta(days=1), "ru", "daily")
        with Session(engine) as unrelated, unrelated.begin():
            with admission.package_admission(unrelated, scope=other):
                unrelated.add(new_run(other))
    finally:
        release.set()
        thread.join(WAIT_SECONDS + 2)
    assert not thread.is_alive()
    assert outcomes == ["completed"], outcomes
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(GenerationRun).where(
            GenerationRun.target_date == DAY, GenerationRun.status == "running",
        )) == 1


def test_raw_writer_bypassing_advisory_is_normalized_by_named_index(engine):
    with Session(engine) as contender:
        contender.begin()
        with pytest.raises(admission.GenerationScopeBusy):
            with admission.package_admission(contender, scope=SCOPE):
                # Both initial observations were empty. This writer deliberately
                # ignores the advisory lock; only PostgreSQL index can arbitrate.
                with Session(engine) as raw, raw.begin():
                    raw.add(new_run())
                contender.add(new_run(run_type="backfill"))
        assert contender.is_active
        assert contender.scalar(select(func.count()).select_from(GenerationRun)) == 1


def test_finalized_winner_does_not_trigger_automatic_replacement(engine, monkeypatch):
    original = admission._is_active_package_conflict
    winner_id = []

    def finalize_before_normalization(exc):
        assert original(exc)
        with Session(engine) as winner, winner.begin():
            winner.get(GenerationRun, winner_id[0]).status = "success"
        return True

    monkeypatch.setattr(admission, "_is_active_package_conflict", finalize_before_normalization)
    with Session(engine) as contender:
        contender.begin()
        with pytest.raises(admission.GenerationScopeBusy):
            with admission.package_admission(contender, scope=SCOPE):
                with Session(engine) as raw, raw.begin():
                    run = new_run()
                    raw.add(run)
                    raw.flush()
                    winner_id.append(run.id)
                contender.add(new_run())
        assert contender.is_active
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 1
        assert observer.get(GenerationRun, winner_id[0]).status == "success"


def test_unrelated_integrity_error_propagates_and_outer_transaction_survives(engine):
    with Session(engine) as session:
        session.begin()
        with pytest.raises(IntegrityError) as error:
            with admission.package_admission(session, scope=SCOPE):
                session.add(new_run(run_type=None))
        assert error.value.orig.sqlstate == "23502"
        assert session.is_active
        assert session.scalar(select(func.count()).select_from(GenerationRun)) == 0


def test_raw_uncommitted_competitor_has_bounded_wait_and_no_outer_rollback(engine, monkeypatch):
    monkeypatch.setattr(admission, "ADMISSION_LOCK_TIMEOUT_MS", 100)
    with Session(engine) as raw:
        raw.add(new_run())
        raw.flush()  # Hold the unique-index competitor until the tested timeout.
        with Session(engine) as contender:
            contender.begin()
            with pytest.raises(OperationalError) as error:
                with admission.package_admission(contender, scope=SCOPE):
                    contender.add(new_run())
            assert error.value.orig.sqlstate == "55P03"
            assert contender.is_active
            assert contender.scalar(select(func.count()).select_from(GenerationRun)) == 0
        raw.rollback()


def test_timeout_settings_restore_on_success_and_busy(engine):
    with Session(engine) as session:
        connection = session.connection()
        connection.execute(text("SET LOCAL lock_timeout = '7s'"))
        connection.execute(text("SET LOCAL statement_timeout = '12s'"))
        query = text("SELECT current_setting('lock_timeout'), current_setting('statement_timeout')")
        before = tuple(connection.execute(query).one())
        with admission.package_admission(session, scope=SCOPE):
            assert tuple(connection.execute(query).one()) != before
            session.add(new_run())
        assert tuple(connection.execute(query).one()) == before
        with pytest.raises(admission.GenerationScopeBusy):
            with admission.package_admission(session, scope=SCOPE):
                pytest.fail("same active scope admitted twice")
        assert tuple(connection.execute(query).one()) == before
        assert session.is_active


def test_stricter_caller_timeout_is_not_weakened(engine):
    with Session(engine) as session:
        connection = session.connection()
        connection.execute(text("SET LOCAL lock_timeout = '100ms'"))
        connection.execute(text("SET LOCAL statement_timeout = '200ms'"))
        with admission.package_admission(session, scope=SCOPE):
            assert dict(connection.execute(text(
                "SELECT name, setting::int FROM pg_settings "
                "WHERE name IN ('lock_timeout', 'statement_timeout')"
            )).all()) == {"lock_timeout": 100, "statement_timeout": 200}


@pytest.mark.parametrize("field,value", [
    ("target_date", DAY + timedelta(days=1)), ("locale", "uk"),
    ("forecast_type", "weekly"),
])
def test_distinct_package_field_is_not_excluded(engine, field, value):
    scope = admission.GenerationPackageScope(**{
        "target_date": DAY, "locale": "ru", "forecast_type": "daily", field: value,
    })
    with Session(engine) as first:
        first.begin()
        with admission.package_admission(first, scope=SCOPE):
            first.add(new_run())
        with Session(engine) as second, second.begin():
            with admission.package_admission(second, scope=scope):
                second.add(new_run(scope))
        first.commit()
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(GenerationRun)) == 2

"""Protocol storage only; orchestrator runs through the STAB-007 harness.

The fake boundary scenarios below are NOT end-to-end paid admission tests.
No runtime paid transport is enabled or SDK client constructed by these tests.
Application imports and PostgreSQL connections require the guarded test harness.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timezone
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.models import (
    GenerationApiObservation, GenerationApiRequest, GenerationAttempt,
    Forecast, GenerationExecution, GenerationExecutionRun, GenerationItem, GenerationRun,
)
from app.services.generation_request_intent_service import (
    MAX_OBSERVATIONS, RequestIntentConflict, RequestIntentError,
    append_request_observation, insert_request_intent, read_request_evidence,
)


@pytest.fixture
def connection(app):
    with app.app_context(), db.engine.connect() as connection:
        yield connection
        connection.rollback()


def _insert(connection, model, **fields):
    return connection.execute(model.__table__.insert().values(**fields).returning(*model.__table__.primary_key)).scalar_one()


def _execution(connection, *, product=False, target_date=None):
    scope = dict(target_date=target_date or date(2026, 11, 17), locale="ru", forecast_type="daily")
    started_at = connection.scalar(sa.select(sa.func.clock_timestamp()))
    execution_id = _insert(connection, GenerationExecution,
        id=uuid4(), origin="dev_direct" if product else "dev_diagnostic",
        deployment_mode="test", provider="openai", policy_version="execution-test",
        started_at=started_at,
        **(scope if product else dict(target_date=None, locale=None, forecast_type=None)),
    )
    links = dict(run_id=None, item_id=None, legacy_attempt_id=None)
    if product:
        links["run_id"] = _insert(connection, GenerationRun, run_type="manual", **scope)
        _insert(connection, GenerationExecutionRun, execution_id=execution_id,
                run_id=links["run_id"], linked_at=started_at)
        links["item_id"] = _insert(connection, GenerationItem, run_id=links["run_id"],
                                   sign_key="aries", **scope)
        links["legacy_attempt_id"] = _insert(connection, GenerationAttempt,
            item_id=links["item_id"], attempt_no=1, provider="openai")
    return dict(execution_id=execution_id, **links)


def _intent_fields(connection, *, product=False, target_date=None):
    return dict(request_id=uuid4(), request_no=1,
                admission_scope="unit-shared-account", policy_version="intent-test",
                **_execution(connection, product=product, target_date=target_date))


def _inject_commit_fault(monkeypatch, connection, *, after_commit):
    """Inject at the real SQLAlchemy-to-DBAPI boundary, on this connection only."""
    original = connection.dialect.do_commit
    target = connection.connection.dbapi_connection
    injected = []

    def faulty_commit(dbapi_connection):
        raw = getattr(dbapi_connection, "dbapi_connection", dbapi_connection)
        if raw is target and not injected:
            injected.append(True)
            if after_commit:
                original(dbapi_connection)
            raise psycopg.OperationalError("simulated commit acknowledgement failure")
        return original(dbapi_connection)

    monkeypatch.setattr(connection.dialect, "do_commit", faulty_commit)
    return injected


def _race_different_parents(engine, table_name, operations):
    """Both contenders pass replay lookup before racing on the same UUID PK."""
    barrier = Barrier(2)

    def before_insert(conn, cursor, statement, parameters, context, executemany):
        compiled = getattr(context, "compiled", None)
        clause = getattr(compiled, "statement", None)
        if getattr(clause, "is_insert", False) and clause.table.name == table_name:
            barrier.wait(timeout=5)

    def contender(operation):
        with engine.connect() as connection, connection.begin():
            marker = _execution(connection)["execution_id"]
            try:
                operation(connection)
                outcome, code = "inserted", None
            except RequestIntentConflict as error:
                # Prove the real PostgreSQL unique-conflict branch ran, rather
                # than the earlier Python replay mismatch branch.
                assert isinstance(error.__cause__, IntegrityError)
                code = error.__cause__.orig.sqlstate
                assert code == "23505"
                outcome = "conflict"
            assert connection.scalar(sa.select(sa.literal(1))) == 1
            assert connection.scalar(sa.select(GenerationExecution.id).where(
                GenerationExecution.id == marker)) == marker
            return outcome, marker, code

    sa.event.listen(engine, "before_cursor_execute", before_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contender, operation) for operation in operations]
            return [future.result(timeout=10) for future in futures]
    finally:
        sa.event.remove(engine, "before_cursor_execute", before_insert)


def test_request_requires_explicit_transaction(connection):
    assert not connection.in_transaction()
    with pytest.raises(RequestIntentError, match="active caller-owned"):
        insert_request_intent(connection, request_id=uuid4(), execution_id=uuid4(),
                              request_no=1, run_id=None, item_id=None,
                              admission_scope="unit", policy_version="test")
    assert not connection.in_transaction()


def test_request_receipt_does_not_commit_parent_or_authorize_transport(connection):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
    transaction = connection.begin()
    receipt = insert_request_intent(connection, **fields)
    assert receipt.execution_id == fields["execution_id"]
    assert receipt.id != receipt.execution_id
    assert connection.in_transaction()
    transaction.rollback()
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 0
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationAttempt)) == 1


@pytest.mark.parametrize("field,value", [
    ("policy_version", "other"), ("admission_scope", "another-account"), ("request_no", 2),
])
def test_request_replay_is_exact_and_does_not_abort_unrelated_work(connection, field, value):
    with connection.begin():
        fields = _intent_fields(connection)
        receipt = insert_request_intent(connection, **fields)
        assert insert_request_intent(connection, **fields) == receipt
        unrelated = _execution(connection)
        with pytest.raises(RequestIntentConflict):
            insert_request_intent(connection, **(fields | {field: value}))
        assert connection.scalar(sa.select(GenerationExecution.id).where(
            GenerationExecution.id == unrelated["execution_id"])) is not None
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1


@pytest.mark.parametrize("field", ["execution_id", "run_id", "item_id", "legacy_attempt_id"])
def test_request_replay_rejects_every_link_change(connection, field):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
        # Distinct package scope also remains valid after .03b's active-run index.
        replacement = _intent_fields(connection, product=True, target_date=date(2026, 11, 18))
        original = insert_request_intent(connection, **fields)
        with pytest.raises(RequestIntentConflict):
            insert_request_intent(connection, **(fields | {field: replacement[field]}))
        assert insert_request_intent(connection, **fields) == original


def test_core_primitive_does_not_flush_unrelated_orm_objects(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        with Session(bind=connection) as caller:
            unrelated = GenerationRun(run_type="manual", target_date=date(2026, 11, 18),
                                      locale="ru", forecast_type="daily")
            caller.add(unrelated)
            assert unrelated.id is None
            insert_request_intent(connection, **fields)
            assert unrelated.id is None
            assert unrelated in caller.new
            assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationRun)) == 0
            caller.expunge(unrelated)


def test_retry_has_new_identity_and_ordinal(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        first = insert_request_intent(connection, **fields)
        with pytest.raises(RequestIntentConflict):
            insert_request_intent(connection, **(fields | {"request_id": uuid4()}))
        second = insert_request_intent(connection, **(fields | {"request_id": uuid4(), "request_no": 2}))
        assert second.id != first.id
        assert second.execution_id == first.execution_id
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 2


def test_concurrent_request_replay_has_one_row(connection, app):
    with connection.begin():
        fields = _intent_fields(connection)
    with app.app_context():
        engine = db.engine
    barrier = Barrier(2)

    def replay():
        with engine.connect() as contender, contender.begin():
            barrier.wait(timeout=5)
            return insert_request_intent(contender, **fields)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(replay) for _ in range(2)]
        receipts = [future.result(timeout=10) for future in futures]
    assert receipts[0] == receipts[1]
    with connection.begin():
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1


def test_request_uuid_race_across_executions_normalizes_real_23505(connection, app):
    with connection.begin():
        fields = [_intent_fields(connection), _intent_fields(connection)]
        fields[1]["request_id"] = fields[0]["request_id"]
    with app.app_context():
        engine = db.engine
    results = _race_different_parents(engine, "generation_api_requests", [
        lambda contender, values=values: insert_request_intent(contender, **values)
        for values in fields
    ])
    assert sorted(result[0] for result in results) == ["conflict", "inserted"]
    with connection.begin():
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1
        markers = [result[1] for result in results]
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationExecution).where(
            GenerationExecution.id.in_(markers))) == 2


def test_observation_uuid_race_across_requests_normalizes_real_23505(connection, app):
    with connection.begin():
        fields = _intent_fields(connection)
        first = insert_request_intent(connection, **fields)
        second = insert_request_intent(connection, **(fields | {"request_id": uuid4(), "request_no": 2}))
    with app.app_context():
        engine = db.engine
    observation_id = uuid4()
    results = _race_different_parents(engine, "generation_api_observations", [
        lambda contender, request_id=request.id: append_request_observation(contender,
            observation_id=observation_id, request_id=request_id, outcome="unknown")
        for request in (first, second)
    ])
    assert sorted(result[0] for result in results) == ["conflict", "inserted"]
    with connection.begin():
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 1
        markers = [result[1] for result in results]
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationExecution).where(
            GenerationExecution.id.in_(markers))) == 2


@pytest.mark.parametrize("same_identity", [False, True])
def test_concurrent_observations_serialize_sequence_and_replay(connection, app, same_identity):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
    with app.app_context():
        engine = db.engine
    barrier = Barrier(2)
    common_id = uuid4()

    def append():
        with engine.connect() as contender, contender.begin():
            barrier.wait(timeout=5)
            return append_request_observation(contender,
                observation_id=common_id if same_identity else uuid4(),
                request_id=request.id, outcome="unknown")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(append) for _ in range(2)]
        receipts = [future.result(timeout=10) for future in futures]
    assert sorted(receipt.observation_no for receipt in receipts) == ([1, 1] if same_identity else [1, 2])
    with connection.begin():
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == (1 if same_identity else 2)


def test_unrelated_integrity_error_propagates_and_parent_is_usable(connection):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
        with pytest.raises(IntegrityError):
            insert_request_intent(connection, **(fields | {"legacy_attempt_id": 9223372036854775807}))
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationAttempt)) == 1
        assert insert_request_intent(connection, **fields).id == fields["request_id"]


def test_missing_observation_before_and_after_fake_dispatch_is_unknown(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        receipt = insert_request_intent(connection, **fields)
    calls = []
    with connection.begin():
        before = read_request_evidence(connection, receipt.id)
    calls.append(receipt.id)  # deterministic fake external boundary only
    with connection.begin():
        after = read_request_evidence(connection, receipt.id)
    assert before == after
    assert after["outcome"] == "unknown"
    assert after["review_state"] == "requires_review"
    assert len(calls) == 1  # No production coordinator is exercised here.


@pytest.mark.parametrize("commit_reached", [False, True])
def test_commit_boundary_fault_preserves_only_actual_durable_intent(connection, commit_reached):
    """Synthetic owner fault, not an application dispatch/admission guarantee."""
    with connection.begin():
        fields = _intent_fields(connection)
    class CommitBoundaryFault(RuntimeError):
        pass

    with pytest.raises(CommitBoundaryFault):
        with connection.begin():
            insert_request_intent(connection, **fields)
            if not commit_reached:
                raise CommitBoundaryFault("Crash before commit")
        # Models a lost acknowledgement after actual commit. Never infer from
        # this synthetic coordinator that runtime .03c is already implemented.
        raise CommitBoundaryFault("Commit outcome not acknowledged by owner")
    with connection.begin():
        report = read_request_evidence(connection, fields["request_id"])
        assert report["request_found"] is commit_reached
        assert report["outcome"] == "unknown"
        assert report["review_state"] == "requires_review"
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == int(commit_reached)
        if commit_reached:
            replay = insert_request_intent(connection, **fields)
            assert replay.id == fields["request_id"]
            assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1
    # This checks durable storage state only. Runtime dispatch and cap admission
    # are deliberately absent; the STAB-007 harness independently blocks network.


@pytest.mark.parametrize("after_commit", [False, True])
def test_dbapi_intent_commit_fault_never_dispatches(connection, app, monkeypatch, after_commit):
    """Manual composition exercises actual commit errors, not a runtime coordinator."""
    with connection.begin():
        fields = _intent_fields(connection)
    with app.app_context():
        engine = db.engine
    transport = Mock(side_effect=AssertionError("Unexpected dispatch after failed acknowledgement"))
    with engine.connect() as owner:
        with monkeypatch.context() as patch:
            injected = _inject_commit_fault(patch, owner, after_commit=after_commit)
            with pytest.raises(DBAPIError):
                with owner.begin():
                    insert_request_intent(owner, **fields)
                transport()  # unreachable on a failed commit acknowledgement
            assert injected == [True]
        # Discard the fault-injected connection. Before-commit failure must roll
        # back server state; after-commit failure cannot roll back its history.
        owner.invalidate()
        owner.rollback()
    with engine.connect() as observer, observer.begin():
        report = read_request_evidence(observer, fields["request_id"])
        assert report["request_found"] is after_commit
        assert report["outcome"] == "unknown"
        assert report["review_state"] == "requires_review"
    transport.assert_not_called()


def test_independent_observer_sees_intent_before_fake_timeout_without_resend(connection, app):
    """Explicit manual protocol composition; paid runtime remains blocked."""
    with connection.begin():
        fields = _intent_fields(connection)
    with app.app_context():
        engine = db.engine
    with engine.connect() as owner:
        transaction = owner.begin()
        receipt = insert_request_intent(owner, **fields)
        with engine.connect() as observer, observer.begin():
            assert not read_request_evidence(observer, receipt.id)["request_found"]
        transaction.commit()

        def fake_timeout():
            assert not owner.in_transaction()
            with engine.connect() as observer, observer.begin():
                report = read_request_evidence(observer, receipt.id)
                assert report["request_found"]
                assert report["outcome"] == "unknown"
            raise TimeoutError("fake uncertain remote outcome")

        transport = Mock(side_effect=fake_timeout)
        with pytest.raises(TimeoutError):
            transport()
        with owner.begin():
            append_request_observation(owner, observation_id=uuid4(), request_id=receipt.id,
                outcome="unknown", evidence_code="transport_timeout")
        with owner.begin():
            assert insert_request_intent(owner, **fields) == receipt
            assert read_request_evidence(owner, receipt.id)["review_state"] == "requires_review"
        transport.assert_called_once()


def test_injected_observation_insert_failure_keeps_intent_and_outer_transaction(connection, app, monkeypatch):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
    with app.app_context():
        engine = db.engine
    transport = Mock(return_value="fake completed response")
    transport()
    with engine.connect() as owner, owner.begin():
        original = owner.dialect.do_execute
        target = owner.connection.dbapi_connection
        injected = []

        def failing_insert(cursor, statement, parameters, context=None):
            clause = getattr(getattr(context, "compiled", None), "statement", None)
            if (cursor.connection is target and getattr(clause, "is_insert", False)
                    and clause.table.name == "generation_api_observations"):
                injected.append(True)
                raise psycopg.OperationalError("simulated observation INSERT failure")
            return original(cursor, statement, parameters, context)

        with monkeypatch.context() as patch:
            patch.setattr(owner.dialect, "do_execute", failing_insert)
            with pytest.raises(DBAPIError):
                append_request_observation(owner, observation_id=uuid4(), request_id=request.id,
                    outcome="succeeded", evidence_code="fake_completed_response")
        assert injected == [True]
        assert owner.scalar(sa.select(sa.literal(1))) == 1
        report = read_request_evidence(owner, request.id)
        assert report["request_found"]
        assert report["outcome"] == "unknown"
        assert report["observations"] == []
    transport.assert_called_once()


@pytest.mark.parametrize("after_commit", [False, True])
def test_injected_observation_commit_failure_never_resends(connection, app, monkeypatch, after_commit):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
    with app.app_context():
        engine = db.engine
    transport = Mock(return_value="fake completed response")
    transport()
    with engine.connect() as owner:
        with monkeypatch.context() as patch:
            injected = _inject_commit_fault(patch, owner, after_commit=after_commit)
            with pytest.raises(DBAPIError):
                with owner.begin():
                    append_request_observation(owner, observation_id=uuid4(), request_id=request.id,
                        outcome="succeeded", evidence_code="fake_completed_response")
            assert injected == [True]
        owner.invalidate()
        owner.rollback()
    with engine.connect() as observer, observer.begin():
        report = read_request_evidence(observer, request.id)
        assert report["request_found"]
        assert report["outcome"] == ("succeeded" if after_commit else "unknown")
        assert len(report["observations"]) == int(after_commit)
        assert observer.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1
    transport.assert_called_once()


def test_already_published_item_skips_stub_transport_and_request_reservation(app, monkeypatch):
    import app.services.generation_service as lifecycle
    from app.providers.stub import StubHoroscopeProvider

    provider = StubHoroscopeProvider()
    transport = Mock(side_effect=AssertionError("Published item must not call provider"))
    monkeypatch.setattr(provider, "generate", transport)
    monkeypatch.setattr(lifecycle, "get_horoscope_provider", lambda name=None: provider)
    day = date(2026, 11, 17)
    with app.app_context():
        forecast = Forecast(sign_key="aries", target_date=day, locale="ru",
                            forecast_type="daily", status="published", text="Preserved published content")
        db.session.add(forecast)
        db.session.commit()
        identity = forecast.id
        run = lifecycle.run_daily_generation(target_date=day, provider_name="stub", signs=["aries"])
        assert run.status == "success"
        assert run.skipped_items == 1
        assert db.session.query(GenerationApiRequest).count() == 0
        assert db.session.query(GenerationAttempt).count() == 0
        assert db.session.get(Forecast, identity).text == "Preserved published content"
    transport.assert_not_called()


def test_unknown_usage_and_observation_exact_replay(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        fields = dict(observation_id=uuid4(), request_id=request.id, outcome="unknown",
                      evidence_code="transport_timeout", input_tokens=10,
                      usage_source="fake-response", model_name="fake-model")
        first = append_request_observation(connection, **fields)
        assert append_request_observation(connection, **fields) == first
        with pytest.raises(RequestIntentConflict):
            append_request_observation(connection, **(fields | {"input_tokens": 11}))
        evidence = read_request_evidence(connection, request.id)
        assert evidence["review_state"] == "requires_review"
        assert evidence["observations"][0]["input_tokens"] == 10
        assert evidence["observations"][0]["output_tokens"] is None


@pytest.mark.parametrize("changes", [
    {"outcome": "succeeded"}, {"evidence_code": "different"},
    {"provider_request_id": "different"}, {"input_tokens": 11},
    {"output_tokens": 4}, {"usage_source": "different"}, {"model_name": "different"},
])
def test_observation_replay_rejects_changed_evidence(connection, changes):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        fields = dict(observation_id=uuid4(), request_id=request.id, outcome="unknown",
            evidence_code="timeout", provider_request_id="fake-request", input_tokens=10,
            output_tokens=3, usage_source="fake-response", model_name="fake-model")
        original = append_request_observation(connection, **fields)
        with pytest.raises(RequestIntentConflict):
            append_request_observation(connection, **(fields | changes))
        assert append_request_observation(connection, **fields) == original
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 1


def test_observation_identity_cannot_be_rebound_to_another_request(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        first = insert_request_intent(connection, **fields)
        second = insert_request_intent(connection, **(fields | {"request_id": uuid4(), "request_no": 2}))
        evidence = dict(observation_id=uuid4(), request_id=first.id, outcome="unknown")
        original = append_request_observation(connection, **evidence)
        with pytest.raises(RequestIntentConflict):
            append_request_observation(connection, **(evidence | {"request_id": second.id}))
        assert append_request_observation(connection, **evidence) == original


@pytest.mark.parametrize("changes", [
    {"outcome": "not_sent", "evidence_code": "guessed"},
    {"outcome": "success"}, {"outcome": []}, {"input_tokens": -1}, {"input_tokens": True},
    {"input_tokens": 1}, {"evidence_code": "raw\nmessage"},
])
def test_invalid_or_unsupported_evidence_is_rejected_without_writes(connection, changes):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        with pytest.raises(RequestIntentError):
            append_request_observation(connection, **(dict(observation_id=uuid4(),
                request_id=request.id, outcome="unknown") | changes))
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 0


def test_observation_rollback_preserves_intent(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
    transaction = connection.begin()
    append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
                               outcome="succeeded", evidence_code="fake_completed_response")
    transaction.rollback()
    with connection.begin():
        evidence = read_request_evidence(connection, request.id)
        assert evidence["request_found"]
        assert evidence["outcome"] == "unknown"
        assert evidence["observations"] == []


def test_later_legacy_rollback_preserves_recorded_provider_outcome(connection):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
        request = insert_request_intent(connection, **fields)
    with connection.begin():
        append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
            outcome="succeeded", evidence_code="fake_completed_response")
    with pytest.raises(RuntimeError, match="legacy persistence failed"):
        with connection.begin():
            connection.execute(GenerationItem.__table__.update().where(
                GenerationItem.id == fields["item_id"]).values(status="success"))
            raise RuntimeError("legacy persistence failed")
    with connection.begin():
        assert connection.scalar(sa.select(GenerationItem.status).where(
            GenerationItem.id == fields["item_id"])) == "pending"
        report = read_request_evidence(connection, request.id)
        assert report["outcome"] == "succeeded"  # provider evidence, not publication
        assert report["observations"][0]["evidence_code"] == "fake_completed_response"


def test_recorded_unknown_is_not_resolved_automatically_by_later_success(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        for outcome in ("unknown", "succeeded"):
            append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
                                       outcome=outcome, evidence_code="independent_evidence")
        report = read_request_evidence(connection, request.id)
        assert report["outcome"] == "unknown"
        assert report["review_state"] == "requires_review"
        assert len(report["observations"]) == 2


@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
@pytest.mark.parametrize("later_recorded", [False, True])
def test_schema_valid_explicit_review_is_never_downgraded(connection, outcome, later_recorded):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        # The schema permits known outcomes that still need operator review.
        # Insert directly: the current convenience writer derives review_state.
        observation_id = _insert(connection, GenerationApiObservation,
            id=uuid4(), request_id=request.id, observation_no=1,
            recorded_at=sa.func.clock_timestamp(), outcome=outcome,
            review_state="requires_review", evidence_code="operator_review_required")
        if later_recorded:
            append_request_observation(connection, observation_id=uuid4(),
                request_id=request.id, outcome=outcome, evidence_code="later_evidence")
        report = read_request_evidence(connection, request.id)
        assert report["outcome"] == "unknown"
        assert report["review_state"] == "requires_review"
        assert report["observations"][0]["id"] == observation_id
        assert report["observations"][0]["outcome"] == outcome
        assert report["observations"][0]["review_state"] == "requires_review"
        assert len(report["observations"]) == (2 if later_recorded else 1)


def test_conflicting_observations_are_not_latest_wins(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        for outcome in ("failed", "succeeded"):
            append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
                                       outcome=outcome, evidence_code="fake_response")
        evidence = read_request_evidence(connection, request.id)
        assert [row["observation_no"] for row in evidence["observations"]] == [1, 2]
        assert evidence["outcome"] == "unknown"
        assert evidence["review_state"] == "requires_review"


def test_conflicting_usage_also_requires_review(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        for tokens in (10, 11):
            append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
                outcome="succeeded", input_tokens=tokens, usage_source="fake", model_name="fake")
        evidence = read_request_evidence(connection, request.id)
        assert evidence["outcome"] == "unknown"
        assert evidence["review_state"] == "requires_review"


def test_missing_request_cannot_acquire_an_observation(connection):
    with connection.begin():
        with pytest.raises(RequestIntentError, match="does not exist"):
            append_request_observation(connection, observation_id=uuid4(), request_id=uuid4(), outcome="unknown")
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 0


def test_read_is_bounded_and_truncation_cannot_prove_certainty(connection):
    with connection.begin():
        request = insert_request_intent(connection, **_intent_fields(connection))
        for _ in range(3):
            append_request_observation(connection, observation_id=uuid4(), request_id=request.id,
                                       outcome="succeeded", evidence_code="fake_response")
        report = read_request_evidence(connection, request.id, limit=2)
        assert len(report["observations"]) == 2
        assert report["truncated"]
        assert report["outcome"] == "unknown"
        assert read_request_evidence(connection, uuid4())["review_state"] == "requires_review"
        for limit in (0, -1, MAX_OBSERVATIONS + 1, True):
            with pytest.raises(RequestIntentError):
                read_request_evidence(connection, request.id, limit=limit)


def test_writers_restore_parent_timeout_settings(connection):
    with connection.begin():
        connection.execute(sa.text("SET LOCAL lock_timeout = '400ms'"))
        connection.execute(sa.text("SET LOCAL statement_timeout = '700ms'"))
        request = insert_request_intent(connection, **_intent_fields(connection))
        append_request_observation(connection, observation_id=uuid4(), request_id=request.id, outcome="unknown")
        assert connection.scalar(sa.text("SHOW lock_timeout")) == "400ms"
        assert connection.scalar(sa.text("SHOW statement_timeout")) == "700ms"


def test_core_savepoint_precedes_timeout_changes_and_dml(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        sa.event.listen(connection, "before_cursor_execute", capture)
        try:
            insert_request_intent(connection, **fields)
        finally:
            sa.event.remove(connection, "before_cursor_execute", capture)
        savepoint = next(i for i, sql in enumerate(statements) if sql.startswith("savepoint "))
        timeout_change = next(i for i, sql in enumerate(statements) if "set_config(" in sql)
        insert = next(i for i, sql in enumerate(statements) if sql.startswith("insert into generation_api_requests"))
        assert savepoint < timeout_change < insert
        assert any(sql.startswith("release savepoint ") for sql in statements)


def test_operation_rollback_restores_timeouts_and_keeps_unrelated_writes(connection):
    with connection.begin():
        fields = _intent_fields(connection)
        insert_request_intent(connection, **fields)
        marker = _execution(connection)["execution_id"]
        connection.execute(sa.text("SET LOCAL lock_timeout = '250ms'"))
        connection.execute(sa.text("SET LOCAL statement_timeout = '600ms'"))
        with pytest.raises(RequestIntentConflict):
            insert_request_intent(connection, **(fields | {"policy_version": "conflict"}))
        assert connection.scalar(sa.text("SHOW lock_timeout")) == "250ms"
        assert connection.scalar(sa.text("SHOW statement_timeout")) == "600ms"
        assert connection.scalar(sa.select(GenerationExecution.id).where(GenerationExecution.id == marker)) == marker
        assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1


def test_uncommitted_parent_execution_lock_times_out_without_outer_rollback(connection, app):
    with connection.begin():
        fields = _intent_fields(connection)
    with app.app_context(), db.engine.connect() as holder:
        with holder.begin():
            holder.execute(sa.select(GenerationExecution.id).where(
                GenerationExecution.id == fields["execution_id"]).with_for_update()).one()
            with connection.begin():
                with pytest.raises(DBAPIError) as caught:
                    insert_request_intent(connection, **fields)
                assert caught.value.orig.sqlstate == "55P03"
                assert connection.scalar(sa.select(sa.literal(1))) == 1
                assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 0


def test_uncommitted_item_update_cannot_deadlock_private_intent(connection, app):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
    with app.app_context(), db.engine.connect() as holder:
        with holder.begin():
            holder.execute(GenerationItem.__table__.update().where(
                GenerationItem.id == fields["item_id"]).values(status="running"))
            with connection.begin():
                with pytest.raises(DBAPIError) as caught:
                    insert_request_intent(connection, **fields)
                assert caught.value.orig.sqlstate == "55P03"
                assert connection.scalar(sa.select(sa.literal(1))) == 1
                assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 0


def test_private_intent_rejects_uncommitted_legacy_attempt(connection, app):
    with connection.begin():
        fields = _intent_fields(connection, product=True)
    with app.app_context(), db.engine.connect() as holder:
        with holder.begin():
            attempt_id = _insert(holder, GenerationAttempt,
                item_id=fields["item_id"], attempt_no=2, provider="openai")
            with connection.begin():
                with pytest.raises(IntegrityError) as caught:
                    insert_request_intent(connection, **(fields | {"legacy_attempt_id": attempt_id}))
                assert caught.value.orig.sqlstate == "23503"
                assert connection.scalar(sa.select(sa.literal(1))) == 1


def test_autocommit_is_rejected_even_with_sqlalchemy_logical_transaction(app):
    with app.app_context(), db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with connection.begin():
            with pytest.raises(RequestIntentError, match="autocommit"):
                insert_request_intent(connection, request_id=uuid4(), execution_id=uuid4(),
                    request_no=1, run_id=None, item_id=None,
                    admission_scope="unit", policy_version="test")


def test_db_owned_admission_day_ignores_session_timezone(connection):
    with connection.begin():
        connection.execute(sa.text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
        receipt = insert_request_intent(connection, **_intent_fields(connection))
        assert receipt.admission_day == receipt.admitted_at.astimezone(timezone.utc).date()
        assert receipt.admitted_at.tzinfo is not None

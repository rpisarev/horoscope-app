"""Storage contract tests. Execute only through the STAB-007 disposable harness."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import db
from app.models import (
    GenerationApiObservation, GenerationApiRequest, GenerationAttempt,
    GenerationExecution, GenerationExecutionRun, GenerationItem, GenerationJob,
    GenerationRun,
)
from test_db_guard import assert_connection, prepare_runtime


MODELS = (GenerationExecution, GenerationExecutionRun, GenerationApiRequest, GenerationApiObservation)
TABLES = tuple(model.__tablename__ for model in MODELS)
START = datetime(2026, 11, 15, 23, 59, 58, tzinfo=timezone.utc)
SCOPE = dict(target_date=date(2026, 11, 17), locale="ru", forecast_type="daily")


def insert(connection, model, **values):
    table = model.__table__
    return connection.execute(table.insert().values(**values).returning(*table.primary_key)).scalar_one()


def legacy(connection, **scope):
    fields = SCOPE | scope
    run_id = insert(connection, GenerationRun, run_type="daily", **fields)
    item_id = insert(connection, GenerationItem, run_id=run_id, sign_key="aries", **fields)
    attempt_id = insert(connection, GenerationAttempt, item_id=item_id, attempt_no=1, provider="openai")
    job_id = insert(connection, GenerationJob, job_type="manual", provider="openai",
                    dedupe_key=str(uuid4()), run_id=run_id, **fields)
    return dict(run_id=run_id, item_id=item_id, legacy_attempt_id=attempt_id, job_id=job_id)


def execution(connection, **changes):
    fields = dict(id=uuid4(), origin="dev_direct", deployment_mode="test", provider="openai",
                  policy_version="execution-v1", started_at=START, **SCOPE)
    return insert(connection, GenerationExecution, **(fields | changes))


def link(connection, execution_id, run_id, **changes):
    return insert(connection, GenerationExecutionRun, **(dict(
        execution_id=execution_id, run_id=run_id, linked_at=START) | changes))


def request(connection, execution_id, **changes):
    fields = dict(id=uuid4(), execution_id=execution_id, request_no=1,
                  admission_scope="shared-account-v1", policy_version="admission-v1",
                  admitted_at=START + timedelta(seconds=1))
    return insert(connection, GenerationApiRequest, **(fields | changes))


def observation(connection, request_id, **changes):
    fields = dict(id=uuid4(), request_id=request_id, observation_no=1,
                  recorded_at=START + timedelta(seconds=2), outcome="unknown",
                  review_state="requires_review")
    return insert(connection, GenerationApiObservation, **(fields | changes))


def diagnostic(connection):
    return execution(connection, origin="dev_diagnostic", target_date=None, locale=None,
                     forecast_type=None)


def product(connection):
    old = legacy(connection)
    execution_id = execution(connection, origin="queue_worker", deployment_mode="production",
                             lease_epoch=7, job_id=old["job_id"])
    link(connection, execution_id, old["run_id"])
    request_id = request(connection, execution_id, **{k: old[k] for k in
                         ("run_id", "item_id", "legacy_attempt_id")})
    return old | dict(execution_id=execution_id, request_id=request_id)


@pytest.fixture
def connection(app):
    with app.app_context(), db.engine.connect() as connection:
        assert_connection(connection, prepare_runtime())
        connection.rollback()
        yield connection
        connection.rollback()


def reject(connection, operation, code="23514"):
    with pytest.raises(DBAPIError) as error:
        with connection.begin_nested():
            operation()
    assert error.value.orig.sqlstate == code


def test_ledger_model_database_parity(connection):
    inspector = sa.inspect(connection)
    metadata = sa.MetaData()
    for model in MODELS:
        model.__table__.to_metadata(metadata)
    # Minimal legacy target columns resolve the new FKs without copying the
    # unrelated forecasts/items cycle into Alembic's table sorter. All new
    # tables/constraints remain complete; old structure is tested separately.
    targets = {}
    for model in MODELS:
        for foreign_key in model.__table__.foreign_keys:
            column = foreign_key.column
            if column.table.name not in TABLES:
                targets.setdefault(column.table.name, {})[column.name] = column
    for name, columns in targets.items():
        sa.Table(name, metadata, *(sa.Column(column.name, column.type.copy(),
                 primary_key=column.primary_key) for column in columns.values()))
    context = MigrationContext.configure(connection, opts={
        "compare_type": True, "compare_server_default": True,
        "include_object": lambda obj, name, kind, reflected, compare_to:
            (name if kind == "table" else getattr(getattr(obj, "table", None), "name", None)) in TABLES,
    })
    assert compare_metadata(context, metadata) == []
    for model in MODELS:
        table = model.__table__
        reflected_columns = {col["name"]: col for col in inspector.get_columns(table.name)}
        assert set(reflected_columns) == set(table.columns.keys())
        for column in table.columns:
            actual = reflected_columns[column.name]
            assert actual["nullable"] == column.nullable
            assert str(actual["type"].compile(dialect=connection.dialect)) == str(
                column.type.compile(dialect=connection.dialect))
            if column.computed is not None:
                assert actual["computed"]["persisted"] is True
                assert "UTC" in actual["computed"]["sqltext"]
            else:
                assert actual["default"] is None
        assert set(inspector.get_pk_constraint(table.name)["constrained_columns"]) == {
            col.name for col in table.primary_key}
        assert {c["name"] for c in inspector.get_check_constraints(table.name)} == {
            c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}
        assert {(c["name"], tuple(c["column_names"])) for c in inspector.get_unique_constraints(table.name)} == {
            (c.name, tuple(col.name for col in c.columns)) for c in table.constraints
            if isinstance(c, sa.UniqueConstraint)}
        assert {(i["name"], tuple(i["column_names"])) for i in inspector.get_indexes(table.name)
                if not i.get("duplicates_constraint")} == {
            (i.name, tuple(col.name for col in i.columns)) for i in table.indexes}
        assert {(fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"],
                 tuple(fk["referred_columns"]), fk["options"].get("ondelete"))
                for fk in inspector.get_foreign_keys(table.name)} == {
            (fk.name, tuple(col.name for col in fk.columns), fk.referred_table.name,
             tuple(element.column.name for element in fk.elements), "RESTRICT")
            for fk in table.foreign_key_constraints}
    triggers = connection.execute(sa.text("""
        SELECT c.relname, count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal AND n.nspname = current_schema()
        AND c.relname IN ('generation_executions', 'generation_execution_runs',
                         'generation_api_requests', 'generation_api_observations')
        GROUP BY c.relname
    """)).all()
    assert dict(triggers) == dict.fromkeys(TABLES, 2)


def test_start_before_run_and_multiple_executions_can_link_same_run(connection):
    first = execution(connection)
    connection.commit()  # Start survives even though no run has been created.
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationExecutionRun)) == 0
    old = legacy(connection)
    link(connection, first, old["run_id"])
    second = execution(connection)
    link(connection, second, old["run_id"])
    reject(connection, lambda: link(connection, first, old["run_id"]), "23505")
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationExecutionRun)) == 2


@pytest.mark.parametrize("changes", [
    {"origin": "queue_worker"}, {"origin": "invalid"}, {"deployment_mode": "invalid"},
    {"deployment_mode": "production"}, {"provider": "OpenAI"}, {"provider": ""},
    {"lease_epoch": 0}, {"lease_epoch": -1}, {"policy_version": " "},
    {"locale": ""}, {"target_date": None}, {"origin": "dev_diagnostic"},
])
def test_invalid_execution_constraints(connection, changes):
    reject(connection, lambda: execution(connection, **changes))


def test_production_requires_real_epoch_and_diagnostics_are_not_production(connection):
    old = legacy(connection)
    reject(connection, lambda: execution(connection, origin="queue_worker",
        deployment_mode="production", job_id=old["job_id"]))
    reject(connection, lambda: execution(connection, origin="dev_diagnostic",
        deployment_mode="production", target_date=None, locale=None, forecast_type=None, lease_epoch=1))
    execution(connection, origin="queue_worker", deployment_mode="production",
              job_id=old["job_id"], lease_epoch=1)


def test_foreign_keys_and_job_scope_provider_are_validated(connection):
    old = legacy(connection)
    reject(connection, lambda: execution(connection, job_id=999999, origin="queue_worker"), "23503")
    reject(connection, lambda: execution(connection, job_id=old["job_id"], origin="dev_direct"))
    for changes in ({"provider": "stub"}, {"target_date": date(2026, 12, 1)},
                    {"locale": "uk"}, {"forecast_type": "weekly"}):
        reject(connection, lambda: execution(connection, job_id=old["job_id"],
                                              origin="queue_worker", **changes))
    reject(connection, lambda: link(connection, uuid4(), old["run_id"]), "23503")
    reject(connection, lambda: link(connection, execution(connection), 999999), "23503")
    reject(connection, lambda: request(connection, uuid4()), "23503")
    reject(connection, lambda: observation(connection, uuid4()), "23503")


def test_link_scope_diagnostic_and_timestamp_constraints(connection):
    old = legacy(connection)
    reject(connection, lambda: link(connection, diagnostic(connection), old["run_id"]))
    e = execution(connection)
    reject(connection, lambda: link(connection, e, old["run_id"], linked_at=START - timedelta(seconds=1)))
    for field, value in (("target_date", date(2026, 12, 1)), ("locale", "uk"), ("forecast_type", "weekly")):
        reject(connection, lambda: link(connection, execution(connection, **{field: value}), old["run_id"]))


def test_product_request_requires_coherent_execution_run_item_and_legacy_attempt(connection):
    old = legacy(connection)
    # Two historical runs for one package remain valid; only one may be active.
    # Keep all cross-run linkage assertions unchanged.
    connection.execute(sa.update(GenerationRun).where(
        GenerationRun.id == old["run_id"],
    ).values(status="failed"))
    other = legacy(connection)
    e = execution(connection)
    reject(connection, lambda: request(connection, e))
    reject(connection, lambda: request(connection, e, run_id=old["run_id"], item_id=old["item_id"]), "23503")
    link(connection, e, old["run_id"])
    for fields, code in [
        ({"run_id": other["run_id"], "item_id": other["item_id"]}, "23503"),
        ({"run_id": old["run_id"], "item_id": other["item_id"]}, "23514"),
        ({"run_id": old["run_id"], "item_id": 999999}, "23503"),
        ({"run_id": old["run_id"], "item_id": old["item_id"], "legacy_attempt_id": other["legacy_attempt_id"]}, "23514"),
        ({"run_id": old["run_id"], "item_id": old["item_id"], "legacy_attempt_id": 999999}, "23503"),
    ]:
        reject(connection, lambda: request(connection, e, **fields), code)
    request(connection, e, run_id=old["run_id"], item_id=old["item_id"])
    for field, value in (("target_date", date(2026, 12, 1)), ("locale", "uk"), ("forecast_type", "weekly")):
        with connection.begin_nested() as savepoint:
            connection.execute(sa.update(GenerationItem).where(GenerationItem.id == old["item_id"]).values(**{field: value}))
            reject(connection, lambda: request(connection, e, request_no=2,
                run_id=old["run_id"], item_id=old["item_id"]))
            savepoint.rollback()


def test_diagnostic_links_and_chronology(connection):
    e = diagnostic(connection)
    old = legacy(connection)
    reject(connection, lambda: request(connection, e, run_id=old["run_id"], item_id=old["item_id"]))
    reject(connection, lambda: request(connection, e, legacy_attempt_id=old["legacy_attempt_id"]))
    reject(connection, lambda: request(connection, e, admitted_at=START - timedelta(seconds=1)))
    r = request(connection, e)
    reject(connection, lambda: observation(connection, r, recorded_at=START))
    prod = execution(connection)
    link(connection, prod, old["run_id"], linked_at=START + timedelta(seconds=3))
    reject(connection, lambda: request(connection, prod, run_id=old["run_id"], item_id=old["item_id"]))


def test_request_identity_and_ordinals_count_admissions_not_jobs(connection):
    p = product(connection)
    values = {k: p[k] for k in ("run_id", "item_id", "legacy_attempt_id")}
    request(connection, p["execution_id"], request_no=2, **values)
    reject(connection, lambda: request(connection, p["execution_id"], **values), "23505")
    reject(connection, lambda: request(connection, p["execution_id"], id=p["request_id"], request_no=3, **values), "23505")
    for no in (0, -1):
        reject(connection, lambda: request(connection, p["execution_id"], request_no=no, **values))
    for field in ("admission_scope", "policy_version"):
        reject(connection, lambda: request(connection, p["execution_id"], request_no=3, **values, **{field: " "}))
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 2
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationExecution)) == 1
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationJob)) == 1


def test_admission_day_is_generated_utc_across_midnight_not_target_or_session_date(connection):
    connection.execute(sa.text("SET LOCAL TIME ZONE 'Pacific/Honolulu'"))
    e = diagnostic(connection)
    request(connection, e)
    request(connection, e, request_no=2, admitted_at=datetime.fromisoformat("2026-11-16T02:00:00+02:00"))
    rows = connection.execute(sa.select(GenerationApiRequest.admission_day,
        GenerationApiRequest.admitted_at).order_by(GenerationApiRequest.request_no)).all()
    assert [r.admission_day for r in rows] == [date(2026, 11, 15), date(2026, 11, 16)]
    assert [r.admitted_at.astimezone(timezone.utc).date() for r in rows] == [r.admission_day for r in rows]
    reject(connection, lambda: request(connection, e, request_no=3, admission_day=date(2000, 1, 1)), "428C9")


def test_unknown_missing_outcome_usage_and_multiple_observations_are_independent(connection):
    r = request(connection, diagnostic(connection))
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 0
    observation(connection, r)
    observation(connection, r, observation_no=2, input_tokens=123, usage_source="provider-v1", model_name="model-v1")
    observation(connection, r, observation_no=3, outcome="succeeded", review_state="recorded",
                input_tokens=0, output_tokens=12, usage_source="provider-v1", model_name="model-v1")
    observation(connection, r, observation_no=4, outcome="unknown")
    observation(connection, r, observation_no=5, outcome="not_sent", review_state="recorded",
                evidence_code="test-protocol-proof")
    rows = connection.execute(sa.select(GenerationApiObservation.__table__).order_by(
        GenerationApiObservation.observation_no)).mappings().all()
    assert rows[0]["input_tokens"] is None and rows[0]["output_tokens"] is None
    assert rows[1]["outcome"] == "unknown" and rows[1]["input_tokens"] == 123 and rows[1]["output_tokens"] is None
    assert rows[2]["input_tokens"] == 0
    assert rows[3]["review_state"] == "requires_review"
    # Neither missing/unknown nor a recorded not_sent observation removes admission.
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1


@pytest.mark.parametrize("changes", [
    {"observation_no": 0}, {"outcome": "invented"}, {"review_state": "approved"},
    {"review_state": "recorded"}, {"outcome": "not_sent"},
    {"evidence_code": " "}, {"provider_request_id": ""},
    {"input_tokens": -1, "usage_source": "provider", "model_name": "model"},
    {"output_tokens": -1, "usage_source": "provider", "model_name": "model"},
    {"input_tokens": 0}, {"output_tokens": 1, "usage_source": "provider"},
    {"input_tokens": 1, "usage_source": "", "model_name": "model"},
    {"input_tokens": 1, "usage_source": "provider", "model_name": ""},
])
def test_observation_constraints(connection, changes):
    r = request(connection, diagnostic(connection))
    reject(connection, lambda: observation(connection, r, **changes))


@pytest.mark.parametrize("usage", [{"input_tokens": 1}, {"output_tokens": 1}])
def test_not_sent_observation_rejects_positive_usage(connection, usage):
    r = request(connection, diagnostic(connection))
    with pytest.raises(DBAPIError) as error:
        with connection.begin_nested():
            observation(connection, r, outcome="not_sent", review_state="recorded",
                        evidence_code="test-protocol-proof", usage_source="provider-v1",
                        model_name="model-v1", **usage)
    assert error.value.orig.sqlstate == "23514"
    assert error.value.orig.diag.constraint_name == "ck_gen_observation_not_sent_usage"


@pytest.mark.parametrize("input_tokens,output_tokens", [(None, None), (0, None), (None, 0), (0, 0)])
def test_not_sent_observation_allows_unknown_or_explicit_zero_usage(connection, input_tokens, output_tokens):
    r = request(connection, diagnostic(connection))
    provenance = {} if input_tokens is None and output_tokens is None else {
        "usage_source": "provider-v1", "model_name": "model-v1"}
    observation(connection, r, outcome="not_sent", review_state="recorded",
                evidence_code="test-protocol-proof", input_tokens=input_tokens,
                output_tokens=output_tokens, **provenance)
    assert connection.execute(sa.select(GenerationApiObservation.input_tokens,
        GenerationApiObservation.output_tokens)).one() == (input_tokens, output_tokens)


def test_observation_uniqueness_and_failed_insert_leave_prior_history(connection):
    r = request(connection, diagnostic(connection))
    o = observation(connection, r)
    reject(connection, lambda: observation(connection, r), "23505")
    reject(connection, lambda: observation(connection, r, id=o, observation_no=2), "23505")
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 1


@pytest.mark.parametrize("model,key", [(GenerationExecution, "id"), (GenerationExecutionRun, "execution_id"),
                                     (GenerationApiRequest, "id"), (GenerationApiObservation, "id")])
def test_raw_update_delete_even_noop_rejected(connection, model, key):
    p = product(connection)
    observation(connection, p["request_id"])
    table = model.__table__
    reject(connection, lambda: connection.execute(table.update().values({key: table.c[key]})), "55000")
    reject(connection, lambda: connection.execute(table.delete()), "55000")
    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 1


def test_orm_update_and_delete_use_database_immutability(connection):
    e = diagnostic(connection)
    connection.commit()
    with Session(bind=connection) as session:
        row = session.get(GenerationExecution, e)
        row.started_at += timedelta(seconds=1)
        with pytest.raises(DBAPIError) as error:
            session.flush()
        assert error.value.orig.sqlstate == "55000"
        session.rollback()
        row = session.get(GenerationExecution, e)
        session.delete(row)
        with pytest.raises(DBAPIError) as error:
            session.flush()
        assert error.value.orig.sqlstate == "55000"
        session.rollback()


def test_legacy_deletes_restricted_but_later_mutations_do_not_rewrite_snapshots(connection):
    p = product(connection)
    for model, ident in ((GenerationJob, p["job_id"]), (GenerationRun, p["run_id"]),
                         (GenerationItem, p["item_id"]), (GenerationAttempt, p["legacy_attempt_id"])):
        reject(connection, lambda: connection.execute(sa.delete(model).where(model.id == ident)), "23503")
    connection.execute(sa.update(GenerationJob).where(GenerationJob.id == p["job_id"]).values(
        run_id=None, started_at=None, attempt_count=0, provider="stub"))
    connection.execute(sa.update(GenerationRun).where(GenerationRun.id == p["run_id"]).values(locale="uk"))
    connection.execute(sa.update(GenerationItem).where(GenerationItem.id == p["item_id"]).values(locale="uk"))
    assert connection.scalar(sa.select(GenerationExecution.provider)) == "openai"
    assert connection.scalar(sa.select(GenerationExecution.locale)) == "ru"
    assert connection.scalar(sa.select(GenerationExecutionRun.run_id)) == p["run_id"]


def test_observation_rollback_preserves_committed_intent(connection):
    r = request(connection, diagnostic(connection))
    connection.commit()
    observation(connection, r, outcome="succeeded", review_state="recorded")
    connection.rollback()  # Simulated failed result transaction, never a transport call.
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiRequest)) == 1
    assert connection.scalar(sa.select(sa.func.count()).select_from(GenerationApiObservation)) == 0
    observation(connection, r)
    connection.commit()


def test_shared_fixture_truncate_cascade_cleans_standalone_diagnostic_rows(connection):
    p = product(connection)
    observation(connection, p["request_id"])
    observation(connection, request(connection, diagnostic(connection)))
    connection.commit()
    # Exact legacy cleanup set; revalidate same connection immediately before mutation.
    assert_connection(connection, prepare_runtime())
    connection.execute(sa.text("TRUNCATE generation_attempts, forecasts, generation_items, "
                               "generation_jobs, generation_runs RESTART IDENTITY CASCADE"))
    assert all(connection.scalar(sa.text(f"SELECT count(*) FROM {name}")) == 0 for name in TABLES)
    connection.commit()

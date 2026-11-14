"""Disposable-harness tests; never run directly against development data."""

from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from app import db
from app.models import Forecast, GenerationAttempt, GenerationItem, GenerationJob, GenerationRun, ZodiacSign
from app.services import generation_recovery_inspection_service as inspection
from utils import generation_job_inspect as cli


DAY = date(2026, 11, 14)
NOW = datetime(2026, 11, 15, 10, tzinfo=timezone.utc)
SECRET = "postgresql://operator:secret-password@private-host/db?token=hidden"


@pytest.fixture
def package(app):
    """Persist complete/partial/failed/crashed histories without generation."""
    def make(*, status="success", run_status=None, item_statuses=("success", "success"),
             published=("aries", "taurus"), signs=("aries", "taurus"), link_run=True,
             attempt_status="success", response=True, stale=False):
        run_status = status if run_status is None else run_status
        run = GenerationRun(
            run_type="manual", target_date=DAY, locale="ru", forecast_type="daily",
            status=run_status, started_at=NOW - timedelta(hours=3),
            finished_at=None if run_status == "running" else NOW - timedelta(hours=1),
            total_items=len(item_statuses), success_items=item_statuses.count("success"),
            failed_items=item_statuses.count("failed") + item_statuses.count("interrupted"),
            skipped_items=item_statuses.count("skipped"), error_message=SECRET,
        )
        db.session.add(run)
        db.session.flush()
        job = GenerationJob(
            job_type="manual", status=status, target_date=DAY, locale="ru", forecast_type="daily",
            provider="stub", signs=None if signs is None else list(signs),
            run_id=run.id if link_run else None, attempt_count=1, max_job_attempts=2,
            max_attempts=3, max_retry_runs=3, dedupe_key="fixture-dedupe",
            locked_at=NOW - timedelta(hours=3 if stale else 0, minutes=5),
            locked_by=SECRET, created_by=SECRET[:64], batch_id=SECRET,
            started_at=NOW - timedelta(hours=3),
            finished_at=None if status in {"queued", "running"} else NOW - timedelta(hours=1),
            error_message=SECRET,
        )
        db.session.add(job)
        made_items = []
        made_attempts = []
        for sign, item_status in zip(("aries", "taurus"), item_statuses):
            item = GenerationItem(
                run_id=run.id, sign_key=sign, target_date=DAY, locale="ru", forecast_type="daily",
                status=item_status, provider="stub", model_name=SECRET,
                request_payload={"secret": SECRET}, response_payload={"secret": SECRET} if response else None,
                raw_response=SECRET if response else None, error_message=SECRET,
                started_at=NOW - timedelta(hours=2),
                finished_at=None if item_status in {"pending", "running"} else NOW - timedelta(hours=1),
            )
            db.session.add(item)
            db.session.flush()
            attempt = GenerationAttempt(
                item_id=item.id, attempt_no=1, provider="stub", status=attempt_status,
                model_name=SECRET, request_payload={"secret": SECRET},
                response_payload={"secret": SECRET} if response else None,
                raw_response=SECRET if response else None, error_type=SECRET, error_message=SECRET,
                started_at=NOW - timedelta(hours=2),
                finished_at=None if attempt_status == "running" else NOW - timedelta(hours=1),
            )
            db.session.add(attempt)
            made_items.append(item)
            made_attempts.append(attempt)
            if sign in published:
                forecast = Forecast(
                    sign_key=sign, target_date=DAY, locale="ru", forecast_type="daily", text=SECRET,
                    title=SECRET, payload={"secret": SECRET}, status="published", source="stub",
                    model_name=SECRET, generation_item_id=item.id, published_at=NOW - timedelta(hours=1),
                )
                db.session.add(forecast)
                db.session.flush()
                item.forecast_id = forecast.id
        db.session.commit()
        # Load identities before mutation-forbidden guards; expire_on_commit is on.
        return SimpleNamespace(job_id=job.id, run_id=run.id,
                               item_ids=[item.id for item in made_items],
                               attempt_ids=[attempt.id for attempt in made_attempts])
    return make


def report(package, **kwargs):
    return inspection.inspect_generation_job(package.job_id, now=NOW, **kwargs)


def test_complete_report_is_deterministic_and_content_free(app, package):
    fixture = package()
    first = report(fixture)
    assert first == report(fixture)
    assert first["schema_version"] == 1
    assert first["outcome"] == "ok" and first["read_only"] is True
    assert first["coverage"]["coverage_state"] == "full"
    assert first["coverage"]["published_signs"] == ["aries", "taurus"]
    assert first["items"]["status_counts"] == {"success": 2}
    assert first["attempts"]["total"] == 2
    assert first["job"]["claim_attempt_count"] == 1
    assert first["run"]["record"]["stored_counts"]["success_items"] == 2
    assert first["lock"]["owner_present"] is True
    assert first["inconsistencies"] == []
    encoded = json.dumps(first, sort_keys=True)
    for forbidden in (SECRET, "secret-password", "private-host", "raw_response", "request_payload",
                      "response_payload", "error_message", "error_type", "model_name", "dedupe_key"):
        assert forbidden not in encoded
    assert {row["transport_outcome"] for row in first["attempts"]["records"]} == {"unknown"}


@pytest.mark.parametrize("status,item_statuses,published,coverage_state", [
    ("partial_failed", ("success", "failed"), ("aries",), "partial"),
    ("failed", ("failed", "failed"), (), "none"),
])
def test_partial_and_failed_are_separate_from_publication(
    app, package, status, item_statuses, published, coverage_state,
):
    result = report(package(status=status, item_statuses=item_statuses, published=published,
                            attempt_status="failed", response=False))
    assert result["job"]["status"] == status
    assert result["coverage"]["coverage_state"] == coverage_state
    assert result["coverage"]["missing_count"] == 2 - len(published)
    assert result["attempts"]["status_counts"] == {"failed": 2}
    assert all(row["response_evidence"] == "absent" for row in result["attempts"]["records"])
    assert "incomplete_attempt_evidence" in result["unknowns"]


def test_unlinked_run_is_unknown_even_if_matching_run_exists(app, package):
    result = report(package(status="running", run_status="running", link_run=False))
    assert result["run"] == {"id": None, "link_state": "not_linked", "record": None}
    assert result["items"]["total"] is None
    assert result["attempts"]["total"] is None
    assert result["coverage"]["published_count"] == 2
    assert "run_evidence_unavailable" in result["unknowns"]
    assert "published_content_with_unfinished_lifecycle" in result["observations"]


def test_dangling_legacy_run_link_does_not_invent_history(app, package, monkeypatch):
    fixture = package()
    # Current FK prevents this fixture; simulate a missing legacy link at its
    # read boundary without disabling constraints or changing shared schema.
    monkeypatch.setattr(inspection, "_read_run", Mock(return_value=None))
    result = report(fixture)
    assert result["run"]["id"] == fixture.run_id
    assert result["run"]["link_state"] == "missing"
    assert result["attempts"]["total"] is None
    assert "linked_run_missing" in result["inconsistencies"]


def test_stale_lock_and_unknown_attempt_are_not_proof_of_worker_death_or_unsent(app, package):
    fixture = package(status="running", item_statuses=("running", "pending"), published=(),
                      attempt_status="running", response=False, stale=True)
    result = report(fixture)
    assert result["lock"]["age_state"] == "older_than_threshold"
    assert result["lock"]["worker_liveness"] == "unknown"
    assert result["attempts"]["status_counts"] == {"running": 2}
    assert "lock_older_than_threshold_is_not_worker_death" in result["observations"]
    assert "incomplete_attempt_evidence" in result["unknowns"]
    assert all(row["transport_outcome"] == "unknown" for row in result["attempts"]["records"])
    assert not any(key in result for key in ("safe_retry", "requeue", "refund", "cancel", "cleanup"))


def test_published_but_unfinished_job_and_run_remain_visible(app, package):
    result = report(package(status="running", run_status="running"))
    assert result["coverage"]["coverage_state"] == "full"
    assert result["job"]["status"] == result["run"]["record"]["status"] == "running"
    assert "published_content_with_unfinished_lifecycle" in result["observations"]


def test_no_persisted_attempts_are_not_zero_remote_requests(app, package):
    result = report(package(status="failed", item_statuses=(), published=()))
    assert result["items"]["total"] == result["attempts"]["total"] == 0
    assert "no_persisted_attempts_does_not_prove_unsent" in result["unknowns"]


def test_detail_limits_keep_exact_full_run_counts(app, package):
    fixture = package()
    result = report(fixture, item_limit=1, attempt_limit=1)
    for section in ("items", "attempts"):
        assert result[section]["total"] == 2
        assert result[section]["returned"] == 1
        assert result[section]["truncated"] is True
    assert result["items"]["records"][0]["id"] == fixture.item_ids[0]
    assert "detail_checks_limited_to_returned_rows" in result["unknowns"]


@pytest.mark.parametrize("signs,reason", [
    ({"token": SECRET}, "malformed_sign_scope"), ("aries", "malformed_sign_scope"),
    ([None], "malformed_sign_scope"), ([123], "malformed_sign_scope"),
    ([[]], "malformed_sign_scope"), (["x" * 33], "malformed_sign_scope"),
    (["aries"] * 1001, "scope_sign_limit"), ([SECRET * 2000], "scope_bytes_limit"),
])
def test_malformed_scope_is_unknown_without_fallback_or_secret_output(app, package, signs, reason):
    fixture = package()
    db.session.get(GenerationJob, fixture.job_id).signs = signs
    db.session.commit()
    result = report(fixture)
    assert result["coverage"]["coverage_state"] == "unknown"
    assert result["coverage"]["reason"] == reason
    assert result["coverage"]["expected_count"] is None
    assert SECRET not in json.dumps(result)


def test_scope_metadata_and_unknown_statuses_are_redacted(app, package):
    fixture = package()
    job = db.session.get(GenerationJob, fixture.job_id)
    job.signs = ["api_key_private", "aries"]
    job.provider = "secret-provider-token"
    job.status = "secret-status-token"
    job.locale = "secret"
    job.forecast_type = "secret-forecast-token"
    attempt = db.session.get(GenerationAttempt, fixture.attempt_ids[0])
    attempt.status = "secret-attempt-token"
    attempt.provider = "secret-provider-token"
    db.session.commit()
    result = report(fixture)
    assert result["job"]["status"] == result["job"]["provider"] == "unknown"
    assert result["coverage"]["expected_signs"] == [None, "aries"]
    assert result["coverage"]["redacted_sign_count"] == 1
    assert result["coverage"]["locale"] == result["coverage"]["forecast_type"] == "unknown"
    assert result["attempts"]["status_counts"] == {"success": 1, "unknown": 1}
    assert "private" not in json.dumps(result)
    assert "secret" not in json.dumps(result)


def test_disabled_explicit_signs_still_count_and_reference_data_is_restored(app, package):
    fixture = package()
    sign = db.session.get(ZodiacSign, "taurus")
    previous = sign.is_enabled
    try:
        sign.is_enabled = False
        db.session.commit()
        result = report(fixture)
        assert result["coverage"]["expected_signs"] == ["aries", "taurus"]
        assert result["coverage"]["published_count"] == 2
    finally:
        db.session.rollback()
        db.session.get(ZodiacSign, "taurus").is_enabled = previous
        db.session.commit()


def test_enabled_scope_uses_current_metadata_and_empty_does_not_fallback(app, package):
    fixture = package(signs=None)
    original = dict(db.session.execute(select(ZodiacSign.key, ZodiacSign.is_enabled)).all())
    try:
        for sign in db.session.scalars(select(ZodiacSign)):
            sign.is_enabled = sign.key == "taurus"
        db.session.commit()
        result = report(fixture)
        assert result["coverage"]["scope_source"] == "enabled_metadata"
        assert result["coverage"]["expected_signs"] == ["taurus"]
        assert result["scope"]["metadata_state"] == "current_reconstruction"
        assert "historical_enabled_sign_scope_not_recorded" in result["unknowns"]
        assert "item_outside_current_enabled_scope" in result["observations"]
        assert "item_outside_job_scope" not in result["inconsistencies"]
        assert result["items"]["records"][0]["matches_job_scope"] is None
        db.session.get(ZodiacSign, "taurus").is_enabled = False
        db.session.commit()
        result = report(fixture)
        assert result["coverage"]["coverage_state"] == "empty_enabled_signs"
        assert result["coverage"]["expected_count"] == 0
        assert result["coverage"]["published_count"] == 0
    finally:
        db.session.rollback()
        for sign in db.session.scalars(select(ZodiacSign)):
            sign.is_enabled = original[sign.key]
        db.session.commit()


def test_empty_explicit_scope_is_not_full_or_enabled_fallback(app, package):
    result = report(package(signs=()))
    assert result["coverage"]["scope_source"] == "explicit_signs"
    assert result["coverage"]["coverage_state"] == "empty_scope"
    assert result["coverage"]["expected_signs"] == []


def test_publication_is_exact_date_locale_type_and_published_only(app, package):
    fixture = package(published=("aries",))
    db.session.add_all([
        Forecast(sign_key="taurus", target_date=DAY, locale="ru", forecast_type="daily", text=SECRET, status="draft"),
        Forecast(sign_key="taurus", target_date=DAY, locale="uk", forecast_type="daily", text=SECRET, status="published"),
        Forecast(sign_key="taurus", target_date=DAY + timedelta(days=1), locale="ru", forecast_type="daily", text=SECRET, status="published"),
        Forecast(sign_key="taurus", target_date=DAY, locale="ru", forecast_type="weekly", text=SECRET, status="published"),
    ])
    db.session.commit()
    result = report(fixture)
    assert result["coverage"]["missing_signs"] == ["taurus"]
    assert "successful_job_with_current_missing_publication" in result["observations"]


def test_existing_divergent_links_are_reported_without_repair(app, package):
    fixture = package()
    run = db.session.get(GenerationRun, fixture.run_id)
    run.target_date = DAY + timedelta(days=1)
    run.total_items = 99
    first = db.session.get(GenerationItem, fixture.item_ids[0])
    second = db.session.get(GenerationItem, fixture.item_ids[1])
    first.forecast_id = second.forecast_id
    second.forecast_id = None
    db.session.commit()
    result = report(fixture)
    assert set(result["inconsistencies"]) >= {
        "job_run_scope_mismatch", "item_forecast_scope_mismatch", "completed_item_without_forecast_link",
    }
    assert "stored_run_counters_differ_from_items" in result["observations"]
    assert db.session.get(GenerationRun, fixture.run_id).total_items == 99


def test_snapshot_cannot_flush_commit_rollback_or_call_generation(app, package, monkeypatch):
    fixture = package()
    session = db.session()
    job = session.get(GenerationJob, fixture.job_id)
    # Create the flushed write before adding pending ORM state: session.execute
    # may autoflush, which would invalidate the fixture before inspection starts.
    session.execute(text("UPDATE generation_runs SET total_items = 77 WHERE id = :id"), {"id": fixture.run_id})
    job.status = "failed"  # Uncommitted caller edit must remain invisible to report.
    pending = GenerationRun(run_type="manual", target_date=DAY, status="running")
    session.add(pending)
    assert pending in session.new and pending.id is None
    assert job in session.dirty
    transaction = session.get_transaction()
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith(("SELECT", "SHOW"))
        statements.append(statement)

    with monkeypatch.context() as patch:
        for method in ("flush", "commit", "rollback"):
            patch.setattr(session, method, Mock(side_effect=AssertionError("caller session changed")))
        for module, method in (
            ("app.services.generation_service", "run_daily_generation"),
            ("app.services.generation_service", "close_stale_running_runs"),
            ("app.services.generation_job_service", "claim_next_generation_job"),
            ("app.services.generation_job_service", "close_stale_running_jobs"),
            ("app.providers", "get_horoscope_provider"),
        ):
            patch.setattr(f"{module}.{method}", Mock(side_effect=AssertionError("mutating path called")))
        event.listen(Engine, "before_cursor_execute", observe)
        try:
            result = report(fixture)
        finally:
            event.remove(Engine, "before_cursor_execute", observe)
        assert result["job"]["status"] == "success"
        assert result["run"]["record"]["stored_counts"]["total_items"] == 2
        assert pending in session.new and pending.id is None
        assert job in session.dirty and job.status == "failed"
        assert session.get_transaction() is transaction and transaction.is_active
    assert statements
    # Full ORM/entity projections would retrieve forbidden contents. Boolean
    # presence expressions may mention payload columns, but must not select them.
    assert not any("generation_jobs.error_message" in query for query in statements)
    assert not any("generation_attempts.request_payload" in query for query in statements)
    assert not any("forecasts.text" in query for query in statements)
    assert session.execute(text("SELECT total_items FROM generation_runs WHERE id = :id"), {"id": fixture.run_id}).scalar_one() == 77
    session.rollback()


def test_missing_job_is_not_successful_inspection(app):
    assert inspection.inspect_generation_job(100000, now=NOW) == {
        "schema_version": 1, "read_only": True, "job_id": 100000, "outcome": "not_found",
    }


@pytest.mark.parametrize("value", [0, -1, True, "1", None, 2**63])
def test_invalid_job_ids_never_open_a_snapshot(app, monkeypatch, value):
    snapshot = Mock(side_effect=AssertionError("invalid input reached DB"))
    monkeypatch.setattr(inspection, "read_snapshot", snapshot)
    with pytest.raises(ValueError):
        inspection.inspect_generation_job(value)
    snapshot.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"item_limit": 0}, {"item_limit": 501}, {"attempt_limit": 1001},
    {"stale_after_minutes": 10081}, {"now": datetime(2026, 1, 1)},
])
def test_invalid_options_never_open_snapshot(app, monkeypatch, kwargs):
    snapshot = Mock()
    monkeypatch.setattr(inspection, "read_snapshot", snapshot)
    with pytest.raises(ValueError):
        inspection.inspect_generation_job(1, **kwargs)
    snapshot.assert_not_called()


@pytest.mark.parametrize("error", [RuntimeError(SECRET), OperationalError("SELECT secret", {}, Exception(SECRET))])
@pytest.mark.parametrize("phase", ["connect", "query", "close"])
def test_service_failures_are_sanitized(app, monkeypatch, error, phase):
    @contextmanager
    def snapshot():
        if phase == "connect":
            raise error
        yield Mock()
        if phase == "close":
            raise error
    monkeypatch.setattr(inspection, "read_snapshot", snapshot)
    monkeypatch.setattr(inspection, "_inspect", Mock(side_effect=error) if phase == "query" else Mock(return_value={}))
    with pytest.raises(inspection.GenerationInspectionUnavailable) as raised:
        inspection.inspect_generation_job(1, now=NOW)
    assert str(raised.value) == "Generation inspection is unavailable."
    assert SECRET not in str(raised.value)
    assert raised.value.__suppress_context__ is True


@pytest.fixture
def cli_runtime(monkeypatch):
    create = Mock(return_value=SimpleNamespace(app_context=nullcontext))
    inspect = Mock(return_value={"schema_version": 1, "read_only": True, "outcome": "ok", "job_id": 7})
    monkeypatch.setattr("app.create_app", create)
    monkeypatch.setattr(inspection, "inspect_generation_job", inspect)
    # No actual dotenv or environment credentials, including __main__ execution.
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setattr("dotenv.load_dotenv", Mock(side_effect=AssertionError("dotenv must not load")))
    return SimpleNamespace(create=create, inspect=inspect)


def invoke_cli(monkeypatch, argv, as_script):
    if not as_script:
        return cli.main(argv)
    monkeypatch.setattr(sys, "argv", [cli.__file__, *argv])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(cli.__file__, run_name="__main__")
    return raised.value.code


@pytest.mark.parametrize("as_script", [False, True])
@pytest.mark.parametrize("outcome,expected", [("ok", 0), ("not_found", 3)])
def test_cli_json_and_exit_contract(monkeypatch, cli_runtime, capsys, as_script, outcome, expected):
    cli_runtime.inspect.return_value["outcome"] = outcome
    args = ["--job-id", "7", "--item-limit", "1", "--attempt-limit", "2", "--stale-after-minutes", "30"]
    assert invoke_cli(monkeypatch, args, as_script) == expected
    output = capsys.readouterr()
    assert output.out == json.dumps(cli_runtime.inspect.return_value, sort_keys=True) + "\n"
    assert output.err == ""
    cli_runtime.inspect.assert_called_once_with(7, item_limit=1, attempt_limit=2, stale_after_minutes=30)


@pytest.mark.parametrize("as_script", [False, True])
@pytest.mark.parametrize("args", [
    [], ["--job-id", "0"], ["--job-id", "-1"], ["--job-id", SECRET],
    ["--job-id", "9223372036854775808"], ["--job-id", "1", "--job-id=2"],
    ["--job-id", "1", "--item-limit", "501"], ["--job-id", "1", "--attempt-limit", "0"],
    ["--job-id", "1", "--stale-after-minutes", "0"], ["--job-id", "1", "--cancel"],
    ["--job", "1"], ["--job-id", "1", "2"],
])
def test_cli_invalid_input_is_safe_and_does_not_create_app(monkeypatch, cli_runtime, capsys, as_script, args):
    if as_script:
        assert invoke_cli(monkeypatch, args, True) == 2
    else:
        with pytest.raises(SystemExit) as raised:
            cli.main(args)
        assert raised.value.code == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["outcome"] == "invalid_input"
    assert SECRET not in output.out and output.err == ""
    cli_runtime.create.assert_not_called()
    cli_runtime.inspect.assert_not_called()


@pytest.mark.parametrize("as_script", [False, True])
@pytest.mark.parametrize("failure_point", ["create", "inspect"])
@pytest.mark.parametrize("error", [RuntimeError(SECRET), OperationalError("SQL", {}, Exception(SECRET)), ValueError(SECRET)])
def test_cli_failures_never_print_original_exceptions(
    monkeypatch, cli_runtime, capsys, as_script, failure_point, error,
):
    getattr(cli_runtime, failure_point).side_effect = error
    assert invoke_cli(monkeypatch, ["--job-id", "7"], as_script) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "schema_version": 1, "read_only": True, "outcome": "unavailable",
        "job_id": 7, "error": "inspection_unavailable",
    }
    assert output.err == "" and SECRET not in output.out


@pytest.mark.parametrize("disabled", [None, "0", "1"])
def test_config_dotenv_opt_out_with_pinned_loader(monkeypatch, disabled):
    # Execute only configuration with a fake loader, never a real .env file.
    # runpy avoids reloading the live app's Config or opening a connection.
    loader = Mock(return_value=False)
    monkeypatch.setattr("dotenv.load_dotenv", loader)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test_runner:dummy@test-db:5432/horoscope_test")
    monkeypatch.delenv("POSTGRES_PASSWORD_FILE", raising=False)
    if disabled is None:
        monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    else:
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", disabled)
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app" / "config.py"))
    assert namespace["Config"].SQLALCHEMY_DATABASE_URI.startswith("postgresql+psycopg://test_runner:dummy@")
    assert loader.call_count == (0 if disabled == "1" else 1)


def test_cli_sets_dotenv_opt_out_before_app_creation(monkeypatch, cli_runtime, capsys):
    import os

    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    def configured_app():
        assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
        return SimpleNamespace(app_context=nullcontext)
    cli_runtime.create.side_effect = configured_app
    assert cli.main(["--job-id", "7"]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "ok"

"""Run only via the orchestrator-owned disposable PostgreSQL test harness."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from itertools import count
import json
import runpy
from unittest.mock import Mock

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

from app import db
from app.models import Forecast, GenerationJob, GenerationRun, ZodiacSign
from app.services import generation_operations_service as operations
from app.services.generation_recovery_inspection_service import inspect_generation_job
from utils import generation_operations_report as cli


TODAY = date(2026, 1, 15)
NOW = datetime(2026, 1, 15, 4, tzinfo=timezone.utc)
SECRET = "private-payload-test-sentinel"
_JOB_IDS = count(1)


@pytest.fixture
def operations_scope(app, monkeypatch):
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "Europe/Kyiv")
    original = list(db.session.execute(select(ZodiacSign.key, ZodiacSign.is_enabled)))
    try:
        db.session.execute(update(ZodiacSign).values(is_enabled=False))
        db.session.execute(update(ZodiacSign).where(
            ZodiacSign.key.in_(("aries", "taurus")),
        ).values(is_enabled=True))
        db.session.commit()  # The independent read snapshot sees committed fixtures.
        yield
    finally:
        # Reference rows are NOT covered by conftest's mutable-table truncation.
        db.session.rollback()
        for key, enabled in original:
            db.session.execute(update(ZodiacSign).where(
                ZodiacSign.key == key,
            ).values(is_enabled=enabled))
        db.session.commit()
        db.session.expire_all()


def add_forecast(sign="aries", day=TODAY, **values):
    fields = dict(
        sign_key=sign, target_date=day, locale="ru", forecast_type="daily",
        status="published", text=SECRET, payload={"private": SECRET}, source="stub",
    )
    fields.update(values)
    row = Forecast(**fields)
    db.session.add(row)
    db.session.commit()
    return row


def add_job(status="queued", *, age=60, **values):
    fields = dict(
        job_type="manual", target_date=TODAY, locale="ru", forecast_type="daily",
        status=status, provider="openai", dedupe_key=f"operations-{next(_JOB_IDS)}",
        created_at=NOW - timedelta(seconds=age), error_message=SECRET,
        locked_by=SECRET, created_by=SECRET,
    )
    fields.update(values)
    row = GenerationJob(**fields)
    db.session.add(row)
    db.session.commit()
    return row


def add_run(status="success", *, started=NOW, **values):
    fields = dict(
        run_type="manual", target_date=TODAY, locale="ru", forecast_type="daily",
        status=status, started_at=started, created_at=started, error_message=SECRET,
    )
    fields.update(values)
    row = GenerationRun(**fields)
    db.session.add(row)
    db.session.commit()
    return row


def test_recovery_and_operations_share_enabled_coverage_contract(operations_scope):
    add_forecast("aries")
    job_id = add_job(signs=None).id
    recovery = inspect_generation_job(job_id, now=NOW)
    aggregate = operations.build_generation_operations_report(now=NOW)
    for key in ("date", "locale", "forecast_type", "expected_signs", "published_signs",
                "missing_signs", "expected_count", "published_count", "missing_count",
                "coverage_state"):
        assert recovery["coverage"][key] == aggregate["coverage"]["today"][key]


def test_historical_job_scope_and_current_enabled_scope_remain_distinct(operations_scope):
    add_forecast("aries")
    job_id = add_job(signs=["aries", "taurus"]).id
    db.session.execute(update(ZodiacSign).where(
        ZodiacSign.key == "taurus",
    ).values(is_enabled=False))
    db.session.commit()
    recovery = inspect_generation_job(job_id, now=NOW)
    aggregate = operations.build_generation_operations_report(now=NOW)
    assert recovery["coverage"]["expected_signs"] == ["aries", "taurus"]
    assert recovery["coverage"]["missing_signs"] == ["taurus"]
    assert recovery["coverage"]["coverage_state"] == "partial"
    assert aggregate["coverage"]["today"]["expected_signs"] == ["aries"]
    assert aggregate["coverage"]["today"]["coverage_state"] == "full"


@pytest.mark.parametrize("day,utc_hour", [
    (date(2026, 1, 15), 4), (date(2026, 7, 15), 3),
    (date(2026, 3, 29), 3), (date(2026, 10, 25), 4),
])
@pytest.mark.parametrize("seconds,state", [
    (-1, "pending"), (0, "missing_after_deadline"), (1, "missing_after_deadline"),
])
def test_deadline_before_at_after_winter_summer_and_dst(
    operations_scope, day, utc_hour, seconds, state,
):
    due = datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=utc_hour)
    report = operations.build_generation_operations_report(now=due + timedelta(seconds=seconds))
    current = report["coverage"]["today"]
    assert report["state"] == state
    assert current["date"] == day.isoformat()
    assert current["coverage_state"] == "none"
    assert current["missing_signs"] == ["aries", "taurus"]
    assert current["deadline"]["at"] == due.isoformat()
    assert current["deadline"]["reached"] is (seconds >= 0)
    assert current["deadline"]["historical_on_time"] == "unknown"
    assert report["coverage"]["tomorrow"]["deadline"]["state"] == "pending"


@pytest.mark.parametrize("instant,today,tomorrow,hours", [
    ("2026-01-31T22:00:00+00:00", "2026-02-01", "2026-02-02", 24),
    ("2026-12-31T22:00:00+00:00", "2027-01-01", "2027-01-02", 24),
    ("2028-02-28T22:00:00+00:00", "2028-02-29", "2028-03-01", 24),
    ("2026-03-28T03:00:00+00:00", "2026-03-28", "2026-03-29", 23),
    ("2026-10-24T03:00:00+00:00", "2026-10-24", "2026-10-25", 25),
])
def test_business_calendar_rollover_and_dst_deadline_interval(
    operations_scope, instant, today, tomorrow, hours,
):
    now = datetime.fromisoformat(instant)
    report = operations.build_generation_operations_report(now=now)
    assert report["scope"]["business_date"] == today
    assert report["scope"]["tomorrow_date"] == tomorrow
    first, second = (report["coverage"][label] for label in ("today", "tomorrow"))
    assert first["date"] == today
    assert second["date"] == tomorrow
    assert (
        datetime.fromisoformat(second["deadline"]["at"])
        - datetime.fromisoformat(first["deadline"]["at"])
    ) == timedelta(hours=hours)


@pytest.mark.parametrize("instant", ["2026-03-29T00:59:59+00:00", "2026-03-29T01:00:00+00:00",
                                     "2026-10-25T00:59:59+00:00", "2026-10-25T01:00:00+00:00"])
def test_dst_clock_change_does_not_shift_product_day(operations_scope, instant):
    now = datetime.fromisoformat(instant)
    report = operations.build_generation_operations_report(now=now)
    assert report["scope"]["business_date"] == instant[:10]
    assert report["state"] == "pending"


@pytest.mark.parametrize("signs,state", [([], "none"), (["aries"], "partial"),
                                         (["aries", "taurus"], "full")])
def test_enabled_metadata_and_published_only_current_coverage(operations_scope, signs, state):
    for sign in signs:
        add_forecast(sign)
    add_forecast("gemini")  # Disabled metadata must not count.
    add_forecast("aries", locale="uk")
    add_forecast("taurus", forecast_type="weekly")
    add_forecast("aries", day=TODAY + timedelta(days=1), status="draft")
    report = operations.build_generation_operations_report(now=NOW)
    current = report["coverage"]["today"]
    assert current["scope_source"] == "enabled_metadata"
    assert current["expected_signs"] == ["aries", "taurus"]
    assert current["expected_count"] == 2
    assert current["coverage_state"] == state
    assert current["published_signs"] == signs
    assert current["published_count"] == len(signs)
    assert current["missing_count"] == 2 - len(signs)
    assert report["coverage"]["tomorrow"]["published_count"] == 0
    assert SECRET not in json.dumps(report)


def test_today_tomorrow_are_independent_and_locale_type_are_exact(operations_scope):
    for sign in ("aries", "taurus"):
        add_forecast(sign, day=TODAY + timedelta(days=1), locale="uk", forecast_type="weekly")
    add_forecast(locale="uk", forecast_type="weekly")
    add_forecast("taurus")
    report = operations.build_generation_operations_report(now=NOW, locale="uk", forecast_type="weekly")
    assert report["coverage"]["today"]["coverage_state"] == "partial"
    assert report["coverage"]["tomorrow"]["coverage_state"] == "full"
    assert report["state"] == "missing_after_deadline"
    assert report["coverage"]["tomorrow"]["deadline"]["state"] == "full_current"
    assert report["scope"]["locale"] == "uk"
    assert report["scope"]["forecast_type"] == "weekly"


@pytest.mark.parametrize("published_at", [NOW - timedelta(days=1), NOW + timedelta(hours=4), None])
def test_full_now_never_fabricates_historical_on_time(operations_scope, published_at):
    for sign in ("aries", "taurus"):
        add_forecast(sign, published_at=published_at)
    report = operations.build_generation_operations_report(now=NOW + timedelta(hours=6))
    assert report["state"] == "full_current"
    assert report["coverage"]["today"]["deadline"]["historical_on_time"] == "unknown"


def test_withdrawal_changes_current_coverage_without_reconstructing_history(operations_scope):
    add_forecast("aries", published_at=NOW - timedelta(hours=1))
    withdrawn = add_forecast("taurus", published_at=NOW - timedelta(hours=1))
    assert operations.build_generation_operations_report(now=NOW)["state"] == "full_current"
    withdrawn.status = "draft"
    db.session.commit()
    report = operations.build_generation_operations_report(now=NOW + timedelta(seconds=1))
    assert report["state"] == "missing_after_deadline"
    assert report["coverage"]["today"]["missing_signs"] == ["taurus"]
    assert report["coverage"]["today"]["deadline"]["historical_on_time"] == "unknown"


def test_zero_enabled_is_configuration_condition_without_static_fallback(operations_scope, monkeypatch):
    add_forecast()
    db.session.execute(update(ZodiacSign).values(is_enabled=False))
    db.session.commit()
    monkeypatch.setattr("app.services.sign_service.get_enabled_sign_keys", Mock(
        side_effect=AssertionError("Legacy fallback must not be called"),
    ))
    report = operations.build_generation_operations_report(now=NOW)
    assert report["state"] == "configuration_issue"
    assert report["configuration"]["conditions"] == ["empty_enabled_signs"]
    for scope in report["coverage"].values():
        assert scope["coverage_state"] == "empty_enabled_signs"
        assert scope["expected_count"] == scope["published_count"] == scope["missing_count"] == 0
        assert scope["expected_signs"] == []
        assert scope["deadline"]["state"] == "empty_enabled_signs"


@pytest.mark.parametrize("zone,day", [("America/New_York", "2025-12-31"), ("UTC", "2026-01-01")])
def test_timezone_override_keeps_backend_date_and_exposes_mismatch(operations_scope, app, monkeypatch, zone, day):
    monkeypatch.setitem(app.config, "APP_TIMEZONE", zone)
    report = operations.build_generation_operations_report(now=datetime(2026, 1, 1, 1, tzinfo=timezone.utc))
    assert report["scope"]["business_date"] == day
    assert report["scope"]["business_timezone"] == zone
    assert report["state"] == "configuration_issue"
    assert report["configuration"]["conditions"] == ["timezone_mismatch"]
    for coverage in report["coverage"].values():
        assert coverage["deadline"]["state"] == "timezone_mismatch"
        assert coverage["deadline"]["at"] is None
        assert coverage["deadline"]["reached"] is None
        assert coverage["deadline"]["timezone"] == "Europe/Kyiv"


def test_empty_queue_and_missing_run_do_not_imply_healthy_worker_or_full_content(operations_scope):
    report = operations.build_generation_operations_report(now=NOW)
    assert report["queue"]["total_count"] == report["queue"]["active_count"] == 0
    assert report["queue"]["observation"] == "no_active_jobs_observed"
    assert report["queue"]["oldest_queued"] == {"created_at": None, "age_seconds": None, "state": "not_observed"}
    assert report["last_known_run"] is None
    assert report["state"] == "missing_after_deadline"
    assert report["signals"]["worker_liveness"] == "unknown"
    assert report["signals"]["worker_progress"] == "unknown"
    assert report["signals"]["worker_pause"] == "unknown"
    assert report["signals"]["database_readiness"] == "not_assessed"
    assert report["signals"]["api_liveness"] == "unknown"


def test_scoped_queue_counts_oldest_age_and_blocked_jobs_have_no_health_inference(operations_scope):
    # A failed OpenAI job and old queued/running jobs do not prove a cause or health.
    add_job("queued", age=120)
    add_job("queued", age=30, target_date=TODAY - timedelta(days=30))
    add_job("running", age=3600, target_date=TODAY + timedelta(days=1))
    for status in ("failed", "partial_failed", "success", "cancelled", "unrecognized-private-status"):
        add_job(status, age=7200)
    add_job("queued", age=86400, locale="uk")
    add_job("queued", age=86400, forecast_type="weekly")
    report = operations.build_generation_operations_report(now=NOW)
    queue = report["queue"]
    assert queue["scope"] == {"locale": "ru", "forecast_type": "daily", "target_dates": "all"}
    assert queue["counts_by_status"] == {
        "queued": 2, "running": 1, "failed": 1, "partial_failed": 1,
        "success": 1, "cancelled": 1, "unknown": 1,
    }
    assert queue["total_count"] == 8
    assert queue["active_count"] == 3
    assert queue["oldest_queued"]["age_seconds"] == 120
    assert queue["oldest_active"]["age_seconds"] == 3600
    assert queue["blocking_reason"] == "unknown"
    assert report["signals"]["worker_pause"] == "unknown"
    assert report["signals"]["provider_quota"] == "unknown"
    assert SECRET not in json.dumps(report)
    assert "unrecognized-private-status" not in json.dumps(report)
    other = operations.build_generation_operations_report(now=NOW, locale="uk")
    assert other["queue"]["total_count"] == 1


def test_future_queue_timestamp_does_not_fabricate_negative_age(operations_scope):
    add_job(age=-60)
    oldest = operations.build_generation_operations_report(now=NOW)["queue"]["oldest_queued"]
    assert oldest["age_seconds"] is None
    assert oldest["state"] == "future_timestamp"


def test_last_run_orders_by_latest_timestamp_then_id_and_scope(operations_scope):
    add_run("running", started=NOW - timedelta(hours=2))
    latest = add_run("failed", started=NOW - timedelta(hours=1), finished_at=NOW)
    latest_id = latest.id
    add_run("success", started=NOW - timedelta(minutes=30))  # Larger ID, earlier last event.
    add_run("success", started=NOW + timedelta(hours=1), locale="uk")
    add_run("success", started=NOW + timedelta(hours=1), forecast_type="weekly")
    report = operations.build_generation_operations_report(now=NOW)
    assert report["last_known_run"]["id"] == latest_id
    assert report["last_known_run"]["status"] == "failed"
    assert report["last_known_run"]["observed_at"] == NOW.isoformat()
    tied = add_run("interrupted", started=NOW)
    tied_id = tied.id
    assert operations.build_generation_operations_report(now=NOW)["last_known_run"]["id"] == tied_id
    assert SECRET not in json.dumps(report)


def test_unknown_run_status_is_redacted(operations_scope):
    add_run(SECRET)
    report = operations.build_generation_operations_report(now=NOW)
    assert report["last_known_run"]["status"] == "unknown"
    assert SECRET not in json.dumps(report)


def test_successful_run_does_not_mask_missing_content(operations_scope):
    add_run("success", finished_at=NOW)
    report = operations.build_generation_operations_report(now=NOW)
    assert report["last_known_run"]["status"] == "success"
    assert report["state"] == "missing_after_deadline"


def test_report_has_fixed_safe_selects_no_provider_or_session_mutation(operations_scope, monkeypatch):
    add_forecast()
    add_job()
    add_run()
    statements = []

    def inspect_statement(conn, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().lower().startswith(("select", "show"))
        if context.compiled is not None:
            assert context.compiled.statement.is_select
            statements.append(statement)

    def forbidden(*args, **kwargs):
        raise AssertionError("Read report reached generation or caller session mutation")

    event.listen(Engine, "before_cursor_execute", inspect_statement)
    try:
        with monkeypatch.context() as patch:
            for method in ("flush", "commit", "rollback"):
                patch.setattr(db.session, method, forbidden)
            for target in (
                "app.providers.factory.get_horoscope_provider",
                "app.providers.openai_provider.OpenAIHoroscopeProvider.generate",
                "app.providers.stub.StubHoroscopeProvider.generate",
                "app.services.generation_service.run_daily_generation",
                "app.services.generation_service.close_stale_running_runs",
                "app.services.generation_job_service.process_generation_jobs",
                "app.services.generation_job_service.claim_next_generation_job",
                "app.services.generation_job_service.close_stale_running_jobs",
                "app.services.forecast_service.save_forecast",
            ):
                patch.setattr(target, forbidden)
            report = operations.build_generation_operations_report(now=NOW)
    finally:
        event.remove(Engine, "before_cursor_execute", inspect_statement)
    assert len(statements) == 6  # Two enabled reads, two coverage reads, queue, latest run.
    for sql in statements:
        for private in ("payload", "error_message", "locked_by", "created_by", "forecasts.text"):
            assert private not in sql.lower()
    assert SECRET not in json.dumps(report)


def test_report_leaves_pending_caller_state_and_transaction_untouched(operations_scope, monkeypatch):
    sign = db.session.get(ZodiacSign, "taurus")
    sign.is_enabled = False  # Must not leak into the independent read snapshot.
    pending = Forecast(sign_key="aries", target_date=TODAY, text=SECRET, status="published")
    db.session.add(pending)
    session = db.session()
    transaction = session.get_transaction()
    with monkeypatch.context() as patch:
        for method in ("flush", "commit", "rollback"):
            patch.setattr(session, method, Mock(side_effect=AssertionError("Caller mutation")))
        report = operations.build_generation_operations_report(now=NOW)
        assert session.get_transaction() is transaction
        assert pending in session.new
        assert sign in session.dirty
        assert sign.is_enabled is False
    assert report["coverage"]["today"]["expected_count"] == 2
    assert report["coverage"]["today"]["published_count"] == 0
    db.session.rollback()


@pytest.mark.parametrize("kwargs", [
    {"now": datetime(2026, 1, 15)},
    {"now": datetime(2026, 1, 15, tzinfo=timezone(timedelta(hours=2)))},
    {"locale": ""}, {"locale": "x"}, {"locale": "../../secret"},
    {"forecast_type": ""}, {"forecast_type": "x" * 33}, {"forecast_type": "private value"},
])
def test_invalid_scope_or_non_utc_clock_rejected_before_read(app, monkeypatch, kwargs):
    snapshot = Mock(side_effect=AssertionError("Invalid input reached database"))
    monkeypatch.setattr(operations, "read_snapshot", snapshot)
    with pytest.raises(ValueError):
        operations.build_generation_operations_report(**kwargs)
    snapshot.assert_not_called()


def test_default_clock_is_utc_and_business_helper_is_authority(operations_scope, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return NOW

    monkeypatch.setattr(operations, "datetime", FrozenDateTime)
    authority = Mock(wraps=operations.business_datetime)
    monkeypatch.setattr(operations, "business_datetime", authority)
    report = operations.build_generation_operations_report()
    authority.assert_called_once_with(NOW)
    assert report["observed_at"] == NOW.isoformat()


@pytest.mark.parametrize("state,exit_code", [("full_current", 0), ("pending", 0),
                                          ("missing_after_deadline", 1), ("configuration_issue", 3)])
def test_cli_json_and_exit_contract(monkeypatch, capsys, state, exit_code):
    read = Mock(return_value={"schema_version": 1, "state": state})
    monkeypatch.setattr(cli, "_read_report", read)
    assert cli.main(["--locale", "uk", "--forecast-type", "weekly"]) == exit_code
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == read.return_value
    read.assert_called_once_with(locale="uk", forecast_type="weekly")


def test_cli_default_wiring_and_main_guard(app, monkeypatch, capsys):
    factory = Mock(return_value=app)
    build = Mock(return_value={"schema_version": 1, "state": "pending"})
    monkeypatch.setattr("app.create_app", factory)
    monkeypatch.setattr(operations, "build_generation_operations_report", build)
    monkeypatch.setattr("sys.argv", [cli.__file__])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(cli.__file__, run_name="__main__")
    assert raised.value.code == 0
    build.assert_called_once_with(locale="ru", forecast_type="daily")
    factory.assert_called_once_with()
    assert json.loads(capsys.readouterr().out)["state"] == "pending"


@pytest.mark.parametrize("arguments", [["--date", "2026-01-15"], ["--now", "2026-01-15"],
                                      ["--provider", SECRET], ["--locale"]])
def test_cli_rejects_date_clock_or_execution_flags_without_echo(monkeypatch, capsys, arguments):
    read = Mock(side_effect=AssertionError("Invalid CLI reached app"))
    monkeypatch.setattr(cli, "_read_report", read)
    assert cli.main(arguments) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["error"]["code"] == "invalid_arguments"
    assert output.err == ""
    assert SECRET not in output.out
    read.assert_not_called()


@pytest.mark.parametrize("error,code", [
    (RuntimeError(SECRET), "report_unavailable"),
    (OperationalError("SELECT private", {}, Exception(SECRET)), "report_unavailable"),
    (ProgrammingError("SELECT private", {}, Exception(SECRET)), "report_unavailable"),
    (ValueError(SECRET), "invalid_configuration_or_scope"),
    (KeyError(SECRET), "invalid_configuration_or_scope"),
    (OSError(SECRET), "report_unavailable"),
])
def test_cli_sanitizes_read_and_startup_failures(monkeypatch, capsys, error, code):
    monkeypatch.setattr(cli, "_read_report", Mock(side_effect=error))
    assert cli.main([]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"schema_version": 1, "state": "unavailable", "error": {"code": code}}
    assert output.err == ""
    assert SECRET not in output.out
    assert "SELECT" not in output.out


def test_cli_sanitizes_failure_from_actual_snapshot_boundary(app, monkeypatch, capsys):
    @contextmanager
    def unavailable():
        raise OperationalError("postgresql://private", {}, Exception(SECRET))
        yield  # pragma: no cover

    monkeypatch.setattr("app.create_app", lambda: app)
    monkeypatch.setattr(operations, "read_snapshot", unavailable)
    assert cli.main([]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["error"]["code"] == "report_unavailable"
    assert SECRET not in output.out
    assert "postgresql" not in output.out
    assert output.err == ""

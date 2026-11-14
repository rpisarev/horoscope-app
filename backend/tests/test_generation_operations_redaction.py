"""Display redaction; run only in the orchestrator's disposable DB harness."""

from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import delete, func, select, update

from app import db
from app.models import Forecast, GenerationJob, GenerationRun, ZodiacSign
from app.services import generation_operations_service as operations
from utils import generation_operations_report as cli


DAY = date(2026, 1, 15)
NOW = datetime(2026, 1, 15, 4, tzinfo=timezone.utc)
NEW_SIGNS = (
    "api_key_private", "secret_one", "secret_two", "bad sign", "TOKEN",
    "password_private", "safe_custom_17",
)
EXPECTED_DISPLAY = ["aries", None, None, None, None, None, None, "safe_custom_17"]


@pytest.fixture
def redaction_scope(app, monkeypatch):
    monkeypatch.setitem(app.config, "APP_TIMEZONE", "Europe/Kyiv")
    original = list(db.session.execute(select(ZodiacSign.key, ZodiacSign.is_enabled)))
    next_order = db.session.execute(select(func.max(ZodiacSign.sort_order))).scalar_one() + 1
    try:
        db.session.execute(update(ZodiacSign).values(is_enabled=False))
        db.session.execute(update(ZodiacSign).where(ZodiacSign.key == "aries").values(is_enabled=True))
        db.session.add_all([
            ZodiacSign(key=key, name_ru="Fixture", sort_order=next_order + index, is_enabled=True)
            for index, key in enumerate(NEW_SIGNS)
        ])
        db.session.commit()  # Independent snapshots require committed fixtures.
        yield
    finally:
        # Conftest does not truncate reference metadata. Remove dependent fixture
        # forecasts before new signs, and restore every original enablement value.
        db.session.rollback()
        db.session.execute(delete(Forecast).where(Forecast.sign_key.in_(NEW_SIGNS)))
        db.session.execute(delete(ZodiacSign).where(ZodiacSign.key.in_(NEW_SIGNS)))
        for key, enabled in original:
            db.session.execute(update(ZodiacSign).where(ZodiacSign.key == key).values(is_enabled=enabled))
        db.session.commit()
        db.session.expire_all()


def forecast(sign, *, day=DAY, locale="ru", forecast_type="daily"):
    return Forecast(
        sign_key=sign, target_date=day, locale=locale, forecast_type=forecast_type,
        text="Fixture", status="published", source="stub",
    )


def test_malformed_signs_use_placeholders_without_losing_coverage(redaction_scope):
    db.session.add_all([
        forecast(key) for key in ("aries", "api_key_private", "secret_one", "safe_custom_17")
    ])
    db.session.add_all([
        forecast(key, day=DAY + timedelta(days=1)) for key in ("aries", *NEW_SIGNS)
    ])
    db.session.commit()

    report = operations.build_generation_operations_report(now=NOW)
    current = report["coverage"]["today"]
    assert current["expected_signs"] == EXPECTED_DISPLAY
    assert current["published_signs"] == ["aries", None, None, "safe_custom_17"]
    assert current["missing_signs"] == [None, None, None, None]
    assert current["redacted_sign_count"] == 6
    assert current["expected_count"] == 8
    assert current["published_count"] == current["missing_count"] == 4
    assert current["coverage_state"] == "partial"
    assert report["state"] == "missing_after_deadline"

    tomorrow = report["coverage"]["tomorrow"]
    assert tomorrow["expected_signs"] == tomorrow["published_signs"] == EXPECTED_DISPLAY
    assert tomorrow["missing_signs"] == []
    assert tomorrow["expected_count"] == tomorrow["published_count"] == 8
    assert tomorrow["missing_count"] == 0
    assert tomorrow["redacted_sign_count"] == 6
    assert tomorrow["coverage_state"] == "full"
    assert tomorrow["deadline"]["state"] == "full_current"
    for coverage in report["coverage"].values():
        for field in ("expected", "published", "missing"):
            assert len(coverage[f"{field}_signs"]) == coverage[f"{field}_count"]
    rendered = json.dumps(report)
    for secret in NEW_SIGNS[:-1]:
        assert secret not in rendered


@pytest.mark.parametrize("locale,forecast_type,shown_locale,shown_type", [
    ("ru", "secret-token", "ru", None),
    ("ru", "password_backup", "ru", None),
    ("ru", "api_key_private", "ru", None),
    ("ru", "api-key-private", "ru", None),
    ("api_KEY", "daily", None, "daily"),
    ("ru", "daily", "ru", "daily"),
    ("uk", "custom-type", "uk", "custom-type"),
])
def test_scope_redaction_preserves_exact_coverage_queue_and_run_queries(
    redaction_scope, locale, forecast_type, shown_locale, shown_type,
):
    selected_run = GenerationRun(
        run_type="manual", target_date=DAY, locale=locale, forecast_type=forecast_type,
        status="success", started_at=NOW, created_at=NOW,
    )
    # Another scope has more coverage/jobs and a more recent run. Display nulls
    # must never become SQL wildcards or trigger a fallback to the other scope.
    excluded_type = "excluded-type"
    db.session.add_all([
        forecast("aries", locale=locale, forecast_type=forecast_type),
        *[forecast(key, locale=locale, forecast_type=excluded_type) for key in ("aries", *NEW_SIGNS)],
        GenerationJob(
            job_type="manual", target_date=DAY, locale=locale, forecast_type=forecast_type,
            status="queued", provider="stub", dedupe_key="redaction-selected", created_at=NOW,
        ),
        GenerationJob(
            job_type="manual", target_date=DAY, locale=locale, forecast_type=excluded_type,
            status="running", provider="stub", dedupe_key="redaction-excluded", created_at=NOW,
        ),
        selected_run,
        GenerationRun(
            run_type="manual", target_date=DAY, locale=locale, forecast_type=excluded_type,
            status="failed", started_at=NOW + timedelta(seconds=1), created_at=NOW,
        ),
    ])
    db.session.commit()
    selected_run_id = selected_run.id

    report = operations.build_generation_operations_report(
        now=NOW, locale=locale, forecast_type=forecast_type,
    )
    for scope in (report["scope"], report["queue"]["scope"], *report["coverage"].values()):
        assert scope["locale"] == shown_locale
        assert scope["forecast_type"] == shown_type
    assert report["coverage"]["today"]["published_count"] == 1
    assert report["coverage"]["today"]["missing_count"] == 7
    assert report["coverage"]["tomorrow"]["published_count"] == 0
    assert report["queue"]["total_count"] == 1
    assert report["queue"]["counts_by_status"]["queued"] == 1
    assert report["queue"]["counts_by_status"]["running"] == 0
    assert report["last_known_run"]["id"] == selected_run_id
    assert report["last_known_run"]["status"] == "success"
    if shown_locale is None:
        assert locale not in json.dumps(report)
    if shown_type is None:
        assert forecast_type not in json.dumps(report)


def test_cli_renders_only_redacted_metadata_and_retains_coverage_exit(
    redaction_scope, monkeypatch, capsys,
):
    db.session.add_all([forecast(key, forecast_type="secret-token") for key in ("aries", *NEW_SIGNS)])
    db.session.commit()
    monkeypatch.setattr(cli, "_read_report", lambda **scope: operations.build_generation_operations_report(
        now=NOW, **scope,
    ))
    assert cli.main(["--forecast-type", "secret-token"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "secret-token" not in output.out
    for value in NEW_SIGNS[:-1]:
        assert value not in output.out
    report = json.loads(output.out)
    assert report["state"] == "full_current"
    assert report["coverage"]["today"]["published_signs"] == EXPECTED_DISPLAY
    assert report["coverage"]["today"]["published_count"] == 8
    assert report["coverage"]["today"]["redacted_sign_count"] == 6


@pytest.mark.parametrize("previous", [None, "0", ""])
def test_cli_disables_dotenv_before_app_factory(monkeypatch, previous):
    if previous is None:
        monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    else:
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", previous)

    def fake_app_factory():
        assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
        return SimpleNamespace(app_context=nullcontext)

    payload = {"schema_version": 1, "state": "pending"}
    build = Mock(return_value=payload)
    factory = Mock(side_effect=fake_app_factory)
    monkeypatch.setattr("app.create_app", factory)
    monkeypatch.setattr(operations, "build_generation_operations_report", build)

    assert cli._read_report(locale="uk", forecast_type="weekly") is payload
    factory.assert_called_once_with()
    build.assert_called_once_with(locale="uk", forecast_type="weekly")

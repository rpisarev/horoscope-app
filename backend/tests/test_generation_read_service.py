from datetime import date

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app import db
from app.models import Forecast, ZodiacSign
from app.services.generation_read_service import (
    enabled_sign_keys,
    published_coverage,
    read_snapshot,
)


DAY = date(2026, 11, 15)


def coverage(connection, **kwargs):
    return published_coverage(
        connection, target_date=DAY, locale="ru", forecast_type="daily", **kwargs
    )


def forecast(sign, **overrides):
    fields = dict(sign_key=sign, target_date=DAY, locale="ru", forecast_type="daily",
                  text="not included in reports", status="published", source="stub")
    fields.update(overrides)
    return Forecast(**fields)


def test_coverage_is_published_only_and_exact_scope(app):
    db.session.add_all([
        forecast("aries"), forecast("taurus", status="draft"),
        forecast("gemini", locale="uk"), forecast("cancer", forecast_type="weekly"),
        forecast("leo", target_date=date(2026, 11, 14)),
    ])
    db.session.commit()
    with read_snapshot() as connection:
        result = coverage(connection, signs=["aries", "taurus", "gemini", "cancer", "leo"])
    assert result["published_signs"] == ["aries"]
    assert result["missing_signs"] == ["taurus", "gemini", "cancer", "leo"]
    assert result["coverage_state"] == "partial"
    assert result["expected_count"] == 5
    assert "text" not in result and "payload" not in result


def test_reports_do_not_flush_commit_or_rollback_caller_work(app, monkeypatch):
    pending = forecast("aries")
    db.session.add(pending)
    def forbidden(*args, **kwargs):
        pytest.fail("Report touched the caller's ORM transaction")
    for name in ("flush", "commit", "rollback"):
        monkeypatch.setattr(db.session, name, forbidden)
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(Engine, "before_cursor_execute", record)
    try:
        with read_snapshot() as connection:
            result = coverage(connection, signs=["aries"])
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    assert result["missing_signs"] == ["aries"]
    assert pending in db.session.new and pending.id is None
    assert statements and set(statements) <= {"SELECT", "SHOW"}


def test_snapshot_is_read_only_and_repeatable(app):
    with read_snapshot() as connection:
        assert connection.scalar(text("SHOW transaction_read_only")) == "on"
        assert connection.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert coverage(connection, signs=["aries"])["coverage_state"] == "none"
        db.session.add(forecast("aries"))
        db.session.commit()
        assert coverage(connection, signs=["aries"])["coverage_state"] == "none"
    with read_snapshot() as connection:
        assert coverage(connection, signs=["aries"])["coverage_state"] == "full"


def test_database_rejects_writes_inside_report_snapshot(app):
    with read_snapshot() as connection:
        with pytest.raises(DBAPIError) as error:
            connection.execute(text("UPDATE zodiac_signs SET name_en = name_en WHERE false"))
        assert error.value.orig.sqlstate == "25006"
    # Error rolled back on the independent connection; caller session stays usable.
    assert db.session.scalar(select(ZodiacSign.key).limit(1)) is not None


def test_zero_enabled_is_explicit_and_does_not_change_generation_fallback(app):
    # Reference rows are not reset by the harness: restore their original values.
    signs = db.session.scalars(select(ZodiacSign)).all()
    original = {sign.key: sign.is_enabled for sign in signs}
    try:
        for sign in signs:
            sign.is_enabled = False
        db.session.commit()
        with read_snapshot() as connection:
            assert enabled_sign_keys(connection) == []
            result = coverage(connection)
            assert result["coverage_state"] == "empty_enabled_signs"
            assert result["expected_count"] == 0
            explicit = coverage(connection, signs=["aries"])
            assert explicit["missing_signs"] == ["aries"]
            assert explicit["scope_source"] == "explicit_signs"
    finally:
        for sign in signs:
            sign.is_enabled = original[sign.key]
        db.session.commit()


def test_explicit_empty_scope_is_not_full_and_duplicates_are_normalized(app):
    with read_snapshot() as connection:
        assert coverage(connection, signs=[])["coverage_state"] == "empty_scope"
        assert coverage(connection, signs=["aries", "aries"])["expected_count"] == 1


@pytest.mark.parametrize("signs", ["aries", b"aries", {"aries": True}, {"aries"}, 1])
def test_invalid_scope_container_is_rejected_before_query(signs):
    from unittest.mock import Mock

    connection = Mock()
    with pytest.raises(ValueError, match="sequence of sign keys"):
        coverage(connection, signs=signs)
    connection.execute.assert_not_called()


def test_report_coverage_matches_existing_published_read_contract(app):
    from app.services.generation_service import get_missing_forecast_signs

    db.session.add_all([forecast("aries"), forecast("taurus", status="draft")])
    db.session.commit()
    requested = ["aries", "taurus", "gemini"]
    expected_missing = get_missing_forecast_signs(
        target_date=DAY, locale="ru", forecast_type="daily", signs=requested
    )
    with read_snapshot() as connection:
        result = coverage(connection, signs=requested)
    assert result["missing_signs"] == expected_missing


def test_connection_settings_bound_waits_without_using_application_pool(app, monkeypatch):
    from app.services import generation_read_service as service
    real_create = service.create_engine
    options = {}
    def create(url, **kwargs):
        options.update(kwargs)
        return real_create(url, **kwargs)
    monkeypatch.setattr(service, "create_engine", create)
    with read_snapshot() as connection:
        assert connection.scalar(text("SHOW statement_timeout")) == "2s"
        assert connection.scalar(text("SHOW lock_timeout")) == "1s"
    assert options["poolclass"] is service.NullPool
    assert options["connect_args"]["connect_timeout"] == 2

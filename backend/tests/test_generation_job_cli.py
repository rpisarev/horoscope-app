from datetime import date

import pytest

from utils.create_generation_jobs import (
    parse_signs,
    parse_target_date,
    resolve_date_range,
)
from utils.process_generation_jobs import require_openai_runtime_safety


class Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_parse_target_date_accepts_iso_date():
    assert parse_target_date("2026-06-15", name="--date") == date(2026, 6, 15)


def test_parse_target_date_rejects_invalid_date():
    with pytest.raises(SystemExit):
        parse_target_date("bad-date", name="--date")


def test_parse_signs_supports_csv_and_repeated_values():
    assert parse_signs(
        signs_csv="aries, taurus",
        sign_values=["gemini", "aries"],
    ) == ["aries", "taurus", "gemini"]


def test_parse_signs_returns_none_when_not_provided():
    assert parse_signs(signs_csv=None, sign_values=None) is None
    assert parse_signs(signs_csv="", sign_values=[]) is None


def test_resolve_date_range_supports_single_date():
    args = Args(
        date="2026-06-15",
        start_date=None,
        end_date=None,
    )

    assert resolve_date_range(args) == (date(2026, 6, 15), date(2026, 6, 15))


def test_resolve_date_range_supports_start_and_end_date():
    args = Args(
        date=None,
        start_date="2026-06-01",
        end_date="2026-06-03",
    )

    assert resolve_date_range(args) == (date(2026, 6, 1), date(2026, 6, 3))


def test_resolve_date_range_requires_end_date_for_range():
    args = Args(
        date=None,
        start_date="2026-06-01",
        end_date=None,
    )

    with pytest.raises(SystemExit):
        resolve_date_range(args)


def test_resolve_date_range_rejects_reversed_range():
    args = Args(
        date=None,
        start_date="2026-06-03",
        end_date="2026-06-01",
    )

    with pytest.raises(SystemExit):
        resolve_date_range(args)


def test_require_openai_runtime_safety_requires_key_when_enabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        require_openai_runtime_safety(allow_openai=True)


def test_require_openai_runtime_safety_ignores_key_when_disabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    require_openai_runtime_safety(allow_openai=False)
"""Protected local operator JSON report; never generates or processes jobs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy.exc import SQLAlchemyError


class _InvalidArguments(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo arbitrary argv values into the machine-readable error.
        raise _InvalidArguments()


def _read_report(*, locale: str, forecast_type: str) -> dict:
    # The application config guard honors this even with python-dotenv 1.0.1.
    # Operational diagnostics use explicitly supplied process configuration.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    backend_dir = str(Path(__file__).resolve().parents[1])
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from app import create_app
    from app.services.generation_operations_service import build_generation_operations_report

    app = create_app()
    with app.app_context():
        return build_generation_operations_report(locale=locale, forecast_type=forecast_type)


def _failure(code: str) -> int:
    print(json.dumps({"schema_version": 1, "state": "unavailable", "error": {"code": code}}))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Read current coverage, deadline and queue observations as JSON.")
    parser.add_argument("--locale", default="ru")
    parser.add_argument("--forecast-type", default="daily")
    try:
        args = parser.parse_args(argv)
    except _InvalidArguments:
        return _failure("invalid_arguments")
    try:
        report = _read_report(locale=args.locale, forecast_type=args.forecast_type)
    except (ValueError, KeyError):
        return _failure("invalid_configuration_or_scope")
    except (RuntimeError, SQLAlchemyError, OSError, ImportError):
        # Connection/schema failures can include SQL, DSNs or secrets. Never
        # print/log their str/repr/traceback, including failures during startup.
        return _failure("report_unavailable")
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return {
        "full_current": 0,
        "pending": 0,
        "missing_after_deadline": 1,
        "configuration_issue": 3,
    }[report["state"]]


if __name__ == "__main__":
    raise SystemExit(main())

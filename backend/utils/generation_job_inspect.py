"""Print safe JSON evidence for one job. No generation or recovery actions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal message echoes invalid input, potentially a secret.
        print(json.dumps({"schema_version": 1, "read_only": True, "outcome": "invalid_input",
                          "error": "invalid_arguments"}, sort_keys=True))
        raise SystemExit(2)


def _bounded_integer(maximum):
    def parse(value):
        if not value.isascii() or not value.isdecimal() or len(value) > 19:
            raise argparse.ArgumentTypeError("Expected a positive integer.")
        parsed = int(value)
        if not 1 <= parsed <= maximum:
            raise argparse.ArgumentTypeError("Integer outside supported range.")
        return parsed
    return parse


def parse_args(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--job-id", required=True, type=_bounded_integer(2**63 - 1))
    parser.add_argument("--item-limit", default=100, type=_bounded_integer(500))
    parser.add_argument("--attempt-limit", default=200, type=_bounded_integer(1000))
    parser.add_argument("--stale-after-minutes", default=60, type=_bounded_integer(10080),
                        help="Diagnostic age threshold only; never proves worker death.")
    args = parser.parse_args(argv)
    # Refuse silently selecting the last of multiple supplied job IDs.
    actual = sys.argv[1:] if argv is None else argv
    if sum(value == "--job-id" or value.startswith("--job-id=") for value in actual) != 1:
        parser.error("Exactly one job ID is required.")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    backend_dir = str(Path(__file__).resolve().parents[1])
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    # This diagnostic consumes explicitly supplied environment configuration.
    # Config imports load_dotenv; disable that before importing any app module.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    try:
        from app import create_app
        from app.services.generation_recovery_inspection_service import inspect_generation_job

        app = create_app()
        with app.app_context():
            result = inspect_generation_job(
                args.job_id, item_limit=args.item_limit, attempt_limit=args.attempt_limit,
                stale_after_minutes=args.stale_after_minutes,
            )
        output = json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except Exception:
        # Includes import/configuration/schema/connection failures. Do not log the
        # original exception or traceback; either can contain credentials or SQL.
        print(json.dumps({"schema_version": 1, "read_only": True, "outcome": "unavailable",
                          "job_id": args.job_id, "error": "inspection_unavailable"}, sort_keys=True))
        return 1
    print(output)
    return 3 if result["outcome"] == "not_found" else 0


if __name__ == "__main__":
    raise SystemExit(main())

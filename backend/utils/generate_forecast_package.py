from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_LOCALE = "ru"
DEFAULT_FORECAST_TYPE = "daily"
DEFAULT_RUN_TYPE = "manual"
DEFAULT_PROVIDER = "openai"


def ensure_backend_on_python_path() -> None:
    """
    When this script is executed as:
      python utils/generate_forecast_package.py

    Python puts /app/utils on sys.path, but the Flask package lives in /app/app.
    Add backend root (/app) explicitly so imports like `from app import ...` work.
    """
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    backend_dir_str = str(backend_dir)

    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)


def load_local_env() -> None:
    """
    Load .env files without importing Flask config first.

    Supported locations:
    - repository root .env
    - backend/.env
    - current working directory .env
    """
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    repo_root = backend_dir.parent

    for env_path in (
        repo_root / ".env",
        backend_dir / ".env",
        Path.cwd() / ".env",
    ):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a full daily forecast package for a target date."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Target date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help=(
            f"Provider name. Default: {DEFAULT_PROVIDER}. "
            "Use 'stub' for free local generation or 'openai' for real OpenAI calls."
        ),
    )
    parser.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help=f"Forecast locale. Default: {DEFAULT_LOCALE}",
    )
    parser.add_argument(
        "--forecast-type",
        default=DEFAULT_FORECAST_TYPE,
        help=f"Forecast type. Default: {DEFAULT_FORECAST_TYPE}",
    )
    parser.add_argument(
        "--run-type",
        default=DEFAULT_RUN_TYPE,
        help=f"Generation run type. Default: {DEFAULT_RUN_TYPE}",
    )
    parser.add_argument(
        "--allow-openai",
        action="store_true",
        help=(
            "Required safety flag when --provider=openai. "
            "Prevents accidental paid OpenAI calls."
        ),
    )
    parser.add_argument(
        "--show-items",
        action="store_true",
        help="Print generation item details after the run.",
    )
    parser.add_argument(
        "--show-errors",
        action="store_true",
        help="Print failed attempts/errors after the run.",
    )

    return parser.parse_args()


def parse_target_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value '{raw_value}'. Expected YYYY-MM-DD.") from exc


def require_openai_safety_confirmation(provider_name: str, allow_openai: bool) -> None:
    if provider_name.strip().lower() != "openai":
        return

    if allow_openai:
        return

    raise SystemExit(
        "Refusing to run paid OpenAI generation without --allow-openai.\n"
        "Run again with:\n"
        "  --provider openai --allow-openai\n"
        "or use:\n"
        "  --provider stub"
    )


def require_openai_key_if_needed(provider_name: str) -> None:
    if provider_name.strip().lower() != "openai":
        return

    if os.getenv("OPENAI_API_KEY"):
        return

    raise SystemExit(
        "OPENAI_API_KEY is missing. Add it to .env or export it before running OpenAI generation."
    )


def print_run_summary(run: Any) -> None:
    print("\n=== Generation run ===")
    print(f"run_id: {run.id}")
    print(f"run_type: {run.run_type}")
    print(f"target_date: {run.target_date}")
    print(f"locale: {run.locale}")
    print(f"forecast_type: {run.forecast_type}")
    print(f"status: {run.status}")
    print(f"total: {run.total_items}")
    print(f"success: {run.success_items}")
    print(f"skipped: {run.skipped_items}")
    print(f"failed: {run.failed_items}")
    print(f"started_at: {run.started_at}")
    print(f"finished_at: {run.finished_at}")
    print(f"error: {run.error_message}")


def print_items(run_id: int) -> None:
    from app import db
    from app.models import GenerationItem

    items = (
        db.session.query(GenerationItem)
        .filter(GenerationItem.run_id == run_id)
        .order_by(GenerationItem.id)
        .all()
    )

    print("\n=== Generation items ===")

    if not items:
        print("No generation items found.")
        return

    for item in items:
        print(
            " | ".join(
                [
                    f"id={item.id}",
                    f"sign={item.sign_key}",
                    f"status={item.status}",
                    f"forecast_id={item.forecast_id}",
                    f"provider={item.provider}",
                    f"model={item.model_name}",
                    f"error={item.error_message}",
                ]
            )
        )


def print_failed_attempts(run_id: int) -> None:
    from app import db
    from app.models import GenerationAttempt, GenerationItem

    attempts = (
        db.session.query(GenerationAttempt, GenerationItem)
        .join(GenerationItem, GenerationItem.id == GenerationAttempt.item_id)
        .filter(
            GenerationItem.run_id == run_id,
            GenerationAttempt.status != "success",
        )
        .order_by(GenerationAttempt.id)
        .all()
    )

    print("\n=== Failed attempts ===")

    if not attempts:
        print("No failed attempts found.")
        return

    for attempt, item in attempts:
        print("\n" + "-" * 100)
        print(f"attempt_id: {attempt.id}")
        print(f"item_id: {item.id}")
        print(f"sign_key: {item.sign_key}")
        print(f"attempt_no: {attempt.attempt_no}")
        print(f"status: {attempt.status}")
        print(f"provider: {attempt.provider}")
        print(f"model_name: {attempt.model_name}")
        print(f"error_type: {attempt.error_type}")
        print(f"error_message: {attempt.error_message}")


def main() -> int:
    ensure_backend_on_python_path()
    load_local_env()

    args = parse_args()

    provider_name = args.provider.strip().lower()
    target_date = parse_target_date(args.date)

    require_openai_safety_confirmation(
        provider_name=provider_name,
        allow_openai=args.allow_openai,
    )
    require_openai_key_if_needed(provider_name)

    from app import create_app
    from app.services import run_daily_generation

    app = create_app()

    print("\n=== Generate forecast package ===")
    print(f"target_date: {target_date.isoformat()}")
    print(f"provider: {provider_name}")
    print(f"locale: {args.locale}")
    print(f"forecast_type: {args.forecast_type}")
    print(f"run_type: {args.run_type}")
    print(f"started_at_local_script_time: {datetime.now().isoformat(timespec='seconds')}")

    with app.app_context():
        run = run_daily_generation(
            target_date=target_date,
            run_type=args.run_type,
            provider_name=provider_name,
            locale=args.locale,
            forecast_type=args.forecast_type,
        )

        print_run_summary(run)

        if args.show_items:
            print_items(run.id)

        if args.show_errors:
            print_failed_attempts(run.id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
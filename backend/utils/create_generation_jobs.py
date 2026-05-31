from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


DEFAULT_LOCALE = "ru"
DEFAULT_FORECAST_TYPE = "daily"
DEFAULT_PROVIDER = "stub"
DEFAULT_JOB_TYPE = "backfill"


def ensure_backend_on_python_path() -> None:
    """Allow running as: python utils/create_generation_jobs.py"""
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    backend_dir_str = str(backend_dir)

    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)


def load_local_env() -> None:
    """Load .env files without importing Flask config first."""
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


def parse_target_date(raw_value: str, *, name: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid {name} value '{raw_value}'. Expected YYYY-MM-DD."
        ) from exc


def parse_signs(
    *,
    signs_csv: str | None,
    sign_values: Iterable[str] | None,
) -> list[str] | None:
    parsed: list[str] = []

    if signs_csv:
        parsed.extend(part.strip() for part in signs_csv.split(","))

    if sign_values:
        parsed.extend(sign.strip() for sign in sign_values)

    parsed = [sign for sign in parsed if sign]

    if not parsed:
        return None

    deduped: list[str] = []

    for sign in parsed:
        normalized = sign.lower()

        if normalized not in deduped:
            deduped.append(normalized)

    return deduped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create queued generation jobs for one date or a date range. "
            "This only creates DB jobs; it does not execute generation."
        )
    )

    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--date",
        help="Single target date in YYYY-MM-DD format.",
    )
    date_group.add_argument(
        "--start-date",
        help="Range start date in YYYY-MM-DD format. Requires --end-date.",
    )

    parser.add_argument(
        "--end-date",
        help="Range end date in YYYY-MM-DD format. Required with --start-date.",
    )
    parser.add_argument(
        "--job-type",
        default=DEFAULT_JOB_TYPE,
        choices=["manual", "backfill", "retry_missing", "scheduled"],
        help=f"Job type. Default: {DEFAULT_JOB_TYPE}.",
    )
    parser.add_argument(
        "--retry-missing",
        action="store_true",
        help="Shortcut for --job-type retry_missing.",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=["stub", "openai"],
        help=f"Provider name. Default: {DEFAULT_PROVIDER}.",
    )
    parser.add_argument(
        "--allow-openai",
        action="store_true",
        help="Required safety flag when --provider=openai.",
    )
    parser.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help=f"Forecast locale. Default: {DEFAULT_LOCALE}.",
    )
    parser.add_argument(
        "--forecast-type",
        default=DEFAULT_FORECAST_TYPE,
        help=f"Forecast type. Default: {DEFAULT_FORECAST_TYPE}.",
    )
    parser.add_argument(
        "--signs",
        help="Comma-separated sign keys, for example: aries,taurus.",
    )
    parser.add_argument(
        "--sign",
        action="append",
        dest="sign_values",
        help="Single sign key. Can be repeated.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Provider/item attempts inside generation_service. Default: 3.",
    )
    parser.add_argument(
        "--max-retry-runs",
        type=int,
        default=3,
        help="Retry run limit for retry_missing jobs. Default: 3.",
    )
    parser.add_argument(
        "--max-job-attempts",
        type=int,
        default=1,
        help="Queue-level attempts for this job. Default: 1.",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=0,
        help="Higher priority is processed first. Default: 0.",
    )
    parser.add_argument(
        "--batch-id",
        help="Optional batch id. If omitted, service generates one.",
    )
    parser.add_argument(
        "--created-by",
        default="cli",
        help="Audit label for created_by. Default: cli.",
    )
    parser.add_argument(
        "--skip-covered",
        action="store_true",
        help="Do not create jobs for dates that already have full coverage.",
    )
    parser.add_argument(
        "--no-skip-duplicate",
        action="store_true",
        help="Raise on active duplicate jobs instead of skipping them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without inserting jobs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of dates processed from the range.",
    )
    parser.add_argument(
        "--show-items",
        action="store_true",
        help="Print one line per processed date.",
    )

    return parser.parse_args()


def resolve_date_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        target_date = parse_target_date(args.date, name="--date")

        if args.end_date:
            raise SystemExit("--end-date cannot be used with --date.")

        return target_date, target_date

    if not args.end_date:
        raise SystemExit("--end-date is required when --start-date is used.")

    start_date = parse_target_date(args.start_date, name="--start-date")
    end_date = parse_target_date(args.end_date, name="--end-date")

    if end_date < start_date:
        raise SystemExit("--end-date must be greater than or equal to --start-date.")

    return start_date, end_date


def require_openai_safety_confirmation(provider_name: str, allow_openai: bool) -> None:
    if provider_name != "openai":
        return

    if allow_openai:
        return

    raise SystemExit(
        "Refusing to create provider=openai generation jobs without --allow-openai.\n"
        "Run again with:\n"
        "  --provider openai --allow-openai\n"
        "or use:\n"
        "  --provider stub"
    )


def warn_openai_key_missing(provider_name: str) -> None:
    if provider_name != "openai":
        return

    if os.getenv("OPENAI_API_KEY"):
        return

    print(
        "WARNING: OPENAI_API_KEY is missing in this environment. "
        "Jobs can be created, but worker execution will fail until the key is configured.",
        file=sys.stderr,
    )


def print_summary(result: dict) -> None:
    print("\n=== Generation jobs creation ===")
    print(f"batch_id: {result['batch_id']}")
    print(f"job_type: {result['job_type']}")
    print(f"provider: {result['provider']}")
    print(f"locale: {result['locale']}")
    print(f"forecast_type: {result['forecast_type']}")
    print(f"start_date: {result['start_date']}")
    print(f"end_date: {result['end_date']}")
    print(f"processed_dates: {result['processed_dates']}")
    print(f"created_count: {result['created_count']}")
    print(f"duplicate_count: {result['duplicate_count']}")
    print(f"covered_count: {result['covered_count']}")
    print(f"dry_run_count: {result['dry_run_count']}")
    print(f"dry_run: {result['dry_run']}")


def print_items(result: dict) -> None:
    print("\n=== Dates ===")

    if not result["items"]:
        print("No dates processed.")
        return

    for item in result["items"]:
        print(
            " | ".join(
                [
                    f"date={item['date']}",
                    f"status={item['status']}",
                    f"job_id={item['job_id']}",
                ]
            )
        )


def main() -> int:
    ensure_backend_on_python_path()
    load_local_env()

    args = parse_args()
    provider_name = args.provider.strip().lower()
    job_type = "retry_missing" if args.retry_missing else args.job_type
    start_date, end_date = resolve_date_range(args)
    signs = parse_signs(
        signs_csv=args.signs,
        sign_values=args.sign_values,
    )

    require_openai_safety_confirmation(
        provider_name=provider_name,
        allow_openai=args.allow_openai,
    )
    warn_openai_key_missing(provider_name)

    from app import create_app
    from app.services.generation_job_service import create_generation_jobs_for_range

    app = create_app()

    print("\n=== Create generation jobs ===")
    print(f"started_at_local_script_time: {datetime.now().isoformat(timespec='seconds')}")
    print(f"start_date: {start_date.isoformat()}")
    print(f"end_date: {end_date.isoformat()}")
    print(f"job_type: {job_type}")
    print(f"provider: {provider_name}")
    print(f"locale: {args.locale}")
    print(f"forecast_type: {args.forecast_type}")
    print(f"signs: {signs}")
    print(f"skip_covered: {args.skip_covered}")
    print(f"dry_run: {args.dry_run}")

    with app.app_context():
        result = create_generation_jobs_for_range(
            start_date=start_date,
            end_date=end_date,
            job_type=job_type,
            locale=args.locale,
            forecast_type=args.forecast_type,
            provider=provider_name,
            signs=signs,
            max_attempts=args.max_attempts,
            max_retry_runs=args.max_retry_runs,
            max_job_attempts=args.max_job_attempts,
            priority=args.priority,
            batch_id=args.batch_id,
            created_by=args.created_by,
            allow_openai=args.allow_openai,
            skip_covered=args.skip_covered,
            skip_duplicate=not args.no_skip_duplicate,
            dry_run=args.dry_run,
            limit=args.limit,
        )

    print_summary(result)

    if args.show_items:
        print_items(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
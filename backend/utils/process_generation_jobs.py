from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


def ensure_backend_on_python_path() -> None:
    """Allow running as: python utils/process_generation_jobs.py"""
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process queued generation jobs manually."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum queued jobs to process. Default: 1.",
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Optional worker id for lock/audit. Default: generated automatically.",
    )
    parser.add_argument(
        "--allow-openai",
        action="store_true",
        help="Required safety flag to execute provider=openai jobs.",
    )
    parser.add_argument(
        "--stale-after-hours",
        type=int,
        default=2,
        help="Pass-through stale run timeout for generation_service. Default: 2.",
    )
    parser.add_argument(
        "--close-stale",
        action="store_true",
        help="Close stale running jobs before processing queued jobs.",
    )
    parser.add_argument(
        "--stale-after-minutes",
        type=int,
        default=60,
        help="Queue job lock timeout used with --close-stale. Default: 60.",
    )
    parser.add_argument(
        "--show-jobs",
        action="store_true",
        help="Print processed job details.",
    )

    return parser.parse_args()


def require_openai_runtime_safety(allow_openai: bool) -> None:
    if not allow_openai:
        return

    if os.getenv("OPENAI_API_KEY"):
        return

    raise SystemExit(
        "OPENAI_API_KEY is missing. Refusing to process OpenAI jobs even though "
        "--allow-openai was provided."
    )


def print_summary(result: dict, *, stale_closed_count: int | None) -> None:
    print("\n=== Process generation jobs ===")

    if stale_closed_count is not None:
        print(f"stale_closed_count: {stale_closed_count}")

    print(f"worker_id: {result['worker_id']}")
    print(f"requested_limit: {result['requested_limit']}")
    print(f"processed_count: {result['processed_count']}")


def print_jobs(result: dict) -> None:
    print("\n=== Jobs ===")

    if not result["jobs"]:
        print("No queued jobs processed.")
        return

    for job in result["jobs"]:
        print("\n" + "-" * 100)
        print(f"id: {job['id']}")
        print(f"job_type: {job['job_type']}")
        print(f"status: {job['status']}")
        print(f"date: {job['date']}")
        print(f"locale: {job['locale']}")
        print(f"forecast_type: {job['forecast_type']}")
        print(f"provider: {job['provider']}")
        print(f"signs: {job['signs']}")
        print(f"run_id: {job['run_id']}")
        print(f"attempt_count: {job['attempt_count']}")
        print(f"error_message: {job['error_message']}")
        print(f"started_at: {job['started_at']}")
        print(f"finished_at: {job['finished_at']}")


def main() -> int:
    ensure_backend_on_python_path()
    load_local_env()

    args = parse_args()

    if args.allow_openai:
        require_openai_runtime_safety(args.allow_openai)

    from app import create_app
    from app.services.generation_job_service import (
        close_stale_running_jobs,
        process_generation_jobs,
    )

    app = create_app()

    print("\n=== Manual generation job worker ===")
    print(f"started_at_local_script_time: {datetime.now().isoformat(timespec='seconds')}")
    print(f"limit: {args.limit}")
    print(f"worker_id: {args.worker_id}")
    print(f"allow_openai: {args.allow_openai}")
    print(f"close_stale: {args.close_stale}")

    with app.app_context():
        stale_closed_count = None

        if args.close_stale:
            stale_closed_count = close_stale_running_jobs(
                stale_after_minutes=args.stale_after_minutes,
            )

        result = process_generation_jobs(
            limit=args.limit,
            worker_id=args.worker_id,
            allow_openai=args.allow_openai,
            stale_after_hours=args.stale_after_hours,
        )

    print_summary(result, stale_closed_count=stale_closed_count)

    if args.show_jobs:
        print_jobs(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
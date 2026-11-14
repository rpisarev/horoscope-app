"""CLI contracts with mocked services; run only through the safe test harness."""

from contextlib import nullcontext
from datetime import date, datetime
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils import generate_forecast_package as package_cli
from utils import process_generation_jobs as worker_cli


DAY = date(2026, 11, 14)


def make_run(status="success", *, success=2, skipped=0, failed=0):
    return SimpleNamespace(
        id=7, run_type="manual", target_date=DAY, locale="ru",
        forecast_type="daily", status=status, total_items=success + skipped + failed,
        success_items=success, skipped_items=skipped, failed_items=failed,
        started_at="2026-11-14T10:00:00+00:00",
        finished_at="2026-11-14T10:01:00+00:00", error_message=None,
    )


def make_job(status="success", *, job_id=8, run_id=7, error=None):
    return {
        "id": job_id, "job_type": "manual", "status": status,
        "date": DAY.isoformat(), "locale": "ru", "forecast_type": "daily",
        "provider": "stub", "signs": None, "run_id": run_id, "attempt_count": 1,
        "error_message": error, "started_at": "2026-11-14T10:00:00+00:00",
        "finished_at": "2026-11-14T10:01:00+00:00",
    }


def make_result(*jobs, limit_reached=False):
    return {
        "worker_id": "cli-test", "requested_limit": 4,
        "processed_count": len(jobs), "jobs": list(jobs),
        "openai_limit_reached": limit_reached,
    }


@pytest.fixture
def cli_runtime(monkeypatch):
    """No real app creation, dotenv reads, generation or queue execution."""
    create_app = Mock(return_value=SimpleNamespace(app_context=nullcontext))
    generation = Mock(return_value=make_run())
    process = Mock(return_value=make_result())
    close_stale = Mock(return_value=2)
    monkeypatch.setattr("app.create_app", create_app)
    monkeypatch.setattr("app.services.run_daily_generation", generation)
    monkeypatch.setattr("app.services.generation_job_service.process_generation_jobs", process)
    monkeypatch.setattr("app.services.generation_job_service.close_stale_running_jobs", close_stale)
    # run_path imports load_dotenv afresh for __main__; keep that path inert too.
    monkeypatch.setattr("dotenv.load_dotenv", Mock())
    monkeypatch.setattr(package_cli, "load_local_env", Mock())
    monkeypatch.setattr(worker_cli, "load_local_env", Mock())
    monkeypatch.setattr(package_cli, "datetime", SimpleNamespace(
        now=lambda: datetime(2026, 11, 14, 10, 0, 0),
    ))
    monkeypatch.setattr(worker_cli, "datetime", package_cli.datetime)
    return SimpleNamespace(
        create_app=create_app, generation=generation, process=process, close_stale=close_stale,
    )


def set_args(monkeypatch, cli, *extra):
    defaults = (
        ["--date", DAY.isoformat(), "--provider", "stub"]
        if cli is package_cli else ["--limit", "4", "--worker-id", "cli-test"]
    )
    monkeypatch.setattr(sys, "argv", [cli.__file__, *defaults, *extra])


def invoke(cli, *, as_script):
    if not as_script:
        return cli.main()
    # Execute the real __main__ guard in this process; the harness forbids subprocesses.
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(cli.__file__, run_name="__main__")
    return raised.value.code


@pytest.mark.parametrize("as_script", [False, True], ids=["main", "__main__"])
@pytest.mark.parametrize(
    "status,success,skipped,failed,expected",
    [
        ("success", 2, 0, 0, 0),
        ("success", 0, 2, 0, 0),  # All published already: lifecycle reports success.
        ("failed", 0, 0, 2, 1),
        ("failed", 0, 0, 0, 1),  # Preflight denial has no items/attempts.
        ("partial_failed", 1, 0, 1, 1),
        ("interrupted", 0, 0, 2, 1),
        ("running", 0, 0, 0, 1),  # Existing active run is not completed work.
        ("unknown", 0, 0, 0, 1),
    ],
)
def test_package_exit_status(
    monkeypatch, cli_runtime, capsys, as_script, status, success, skipped, failed, expected,
):
    cli_runtime.generation.return_value = make_run(
        status, success=success, skipped=skipped, failed=failed,
    )
    set_args(monkeypatch, package_cli)

    assert invoke(package_cli, as_script=as_script) == expected
    assert f"status: {status}\n" in capsys.readouterr().out
    cli_runtime.generation.assert_called_once_with(
        target_date=DAY, run_type="manual", provider_name="stub",
        locale="ru", forecast_type="daily",
    )


@pytest.mark.parametrize("as_script", [False, True], ids=["main", "__main__"])
@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([], 0), (["success"], 0), (["success", "success"], 0),
        (["failed"], 1), (["partial_failed"], 1),
        (["success", "failed"], 1), (["failed", "success"], 1),
        (["success", "partial_failed"], 1),
        (["running"], 1), (["queued"], 1), (["cancelled"], 1), (["unknown"], 1),
    ],
)
def test_worker_exit_status(monkeypatch, cli_runtime, capsys, as_script, statuses, expected):
    cli_runtime.process.return_value = make_result(*(
        make_job(status, job_id=index) for index, status in enumerate(statuses)
    ))
    set_args(monkeypatch, worker_cli, "--show-jobs")

    assert invoke(worker_cli, as_script=as_script) == expected
    output = capsys.readouterr().out
    assert f"processed_count: {len(statuses)}\n" in output
    for status in statuses:
        assert f"status: {status}\n" in output
    if not statuses:
        assert "No queued jobs processed.\n" in output
    cli_runtime.process.assert_called_once_with(
        limit=4, worker_id="cli-test", allow_openai=False, stale_after_hours=2,
    )


@pytest.mark.parametrize("jobs", [[], [make_job()]])
def test_worker_count_limit_is_legitimate_no_work(monkeypatch, cli_runtime, jobs):
    cli_runtime.process.return_value = make_result(*jobs, limit_reached=True)
    set_args(monkeypatch, worker_cli)
    assert worker_cli.main() == 0


@pytest.mark.parametrize("status,expected", [("success", 0), ("failed", 1)])
def test_worker_retry_missing_uses_result_status(monkeypatch, cli_runtime, status, expected):
    job = make_job(
        status, run_id=None,
        error="Retry run limit reached with missing forecasts" if status == "failed" else None,
    )
    job["job_type"] = "retry_missing"
    cli_runtime.process.return_value = make_result(job)
    set_args(monkeypatch, worker_cli)
    assert worker_cli.main() == expected


def test_package_report_and_optional_details_are_preserved(monkeypatch, cli_runtime, capsys):
    items = Mock(side_effect=lambda run_id: print("item details"))
    errors = Mock(side_effect=lambda run_id: print("attempt details"))
    monkeypatch.setattr(package_cli, "print_items", items)
    monkeypatch.setattr(package_cli, "print_failed_attempts", errors)
    cli_runtime.generation.return_value = make_run("partial_failed", success=1, failed=1)
    set_args(monkeypatch, package_cli, "--show-items", "--show-errors")

    assert package_cli.main() == 1
    assert capsys.readouterr().out == (
        "\n=== Generate forecast package ===\n"
        "target_date: 2026-11-14\nprovider: stub\nlocale: ru\nforecast_type: daily\n"
        "run_type: manual\nstarted_at_local_script_time: 2026-11-14T10:00:00\n"
        "\n=== Generation run ===\nrun_id: 7\nrun_type: manual\n"
        "target_date: 2026-11-14\nlocale: ru\nforecast_type: daily\n"
        "status: partial_failed\ntotal: 2\nsuccess: 1\nskipped: 0\nfailed: 1\n"
        "started_at: 2026-11-14T10:00:00+00:00\n"
        "finished_at: 2026-11-14T10:01:00+00:00\nerror: None\n"
        "item details\nattempt details\n"
    )
    items.assert_called_once_with(7)
    errors.assert_called_once_with(7)


def test_worker_report_and_stale_cleanup_are_preserved(monkeypatch, cli_runtime, capsys):
    cli_runtime.process.return_value = make_result(make_job("failed", error="denied"))
    set_args(monkeypatch, worker_cli, "--show-jobs", "--close-stale", "--stale-after-minutes", "30")

    assert worker_cli.main() == 1
    assert capsys.readouterr().out == (
        "\n=== Manual generation job worker ===\n"
        "started_at_local_script_time: 2026-11-14T10:00:00\n"
        "limit: 4\nworker_id: cli-test\nallow_openai: False\nclose_stale: True\n"
        "\n=== Process generation jobs ===\nstale_closed_count: 2\n"
        "worker_id: cli-test\nrequested_limit: 4\nprocessed_count: 1\n"
        "\n=== Jobs ===\n\n" + "-" * 100 + "\n"
        "id: 8\njob_type: manual\nstatus: failed\ndate: 2026-11-14\n"
        "locale: ru\nforecast_type: daily\nprovider: stub\nsigns: None\n"
        "run_id: 7\nattempt_count: 1\nerror_message: denied\n"
        "started_at: 2026-11-14T10:00:00+00:00\nfinished_at: 2026-11-14T10:01:00+00:00\n"
    )
    cli_runtime.close_stale.assert_called_once_with(stale_after_minutes=30)


@pytest.mark.parametrize("cli,args", [
    (package_cli, []),
    (package_cli, ["--date", DAY.isoformat(), "--unknown"]),
    (worker_cli, ["--limit", "invalid"]),
    (worker_cli, ["--unknown"]),
])
@pytest.mark.parametrize("as_script", [False, True])
def test_argparse_keeps_exit_two(monkeypatch, cli_runtime, cli, args, as_script):
    monkeypatch.setattr(sys, "argv", [cli.__file__, *args])
    if as_script:
        assert invoke(cli, as_script=True) == 2
    else:
        with pytest.raises(SystemExit) as raised:
            cli.main()
        assert raised.value.code == 2
    cli_runtime.create_app.assert_not_called()


@pytest.mark.parametrize("cli,args,message", [
    (package_cli, ["--date", "invalid"], "Invalid --date value"),
    (package_cli, ["--provider", " "], "--provider must not be empty"),
    (package_cli, ["--provider", "openai"], "without --allow-openai"),
    (package_cli, ["--provider", "openai", "--allow-openai"], "OPENAI_API_KEY is missing"),
    (worker_cli, ["--allow-openai"], "OPENAI_API_KEY is missing"),
])
@pytest.mark.parametrize("as_script", [False, True])
def test_existing_system_exit_messages_are_preserved(
    monkeypatch, cli_runtime, cli, args, message, as_script,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    set_args(monkeypatch, cli, *args)
    if as_script:
        assert message in invoke(cli, as_script=True)
    else:
        with pytest.raises(SystemExit, match=message):
            cli.main()
    cli_runtime.create_app.assert_not_called()


@pytest.mark.parametrize("cli,service_name", [(package_cli, "generation"), (worker_cli, "process")])
@pytest.mark.parametrize("as_script", [False, True])
@pytest.mark.parametrize("error", [RuntimeError("unexpected failure"), KeyboardInterrupt()])
def test_unexpected_errors_and_interrupts_propagate(
    monkeypatch, cli_runtime, cli, service_name, as_script, error,
):
    getattr(cli_runtime, service_name).side_effect = error
    set_args(monkeypatch, cli)
    with pytest.raises(type(error)) as raised:
        invoke(cli, as_script=as_script)
    assert raised.value is error


def test_worker_service_validation_error_still_propagates(monkeypatch, cli_runtime):
    from app.services.generation_job_service import GenerationJobValidationError

    cli_runtime.process.side_effect = GenerationJobValidationError("limit must be at least 1.")
    set_args(monkeypatch, worker_cli, "--limit", "0")
    with pytest.raises(GenerationJobValidationError, match="limit must be at least 1"):
        worker_cli.main()


def test_reporting_error_does_not_become_success(monkeypatch, cli_runtime):
    monkeypatch.setattr(package_cli, "print_items", Mock(side_effect=RuntimeError("report failed")))
    set_args(monkeypatch, package_cli, "--show-items")
    with pytest.raises(RuntimeError, match="report failed"):
        package_cli.main()

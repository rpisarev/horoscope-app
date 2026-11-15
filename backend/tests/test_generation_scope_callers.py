"""Busy response contracts with mocked generation; STAB-007 harness only."""

from contextlib import nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.generation_admission_service import GenerationPackageScope, GenerationScopeBusy
from test_generation_cli_exit_codes import cli_runtime, invoke, package_cli, set_args


DAY = date(2026, 11, 17)
SCOPE = GenerationPackageScope(DAY, "ru", "daily")


@pytest.mark.parametrize("route,function", [
    ("/generation/runs", "create_manual_generation_run"),
    ("/generation/retry-missing", "retry_missing_generation"),
])
def test_admin_busy_has_explicit_409_existing_error_envelope(app, client, monkeypatch, route, function):
    from app import admin_routes
    monkeypatch.setitem(app.config, "ADMIN_API_ENABLED", True)
    monkeypatch.setitem(app.config, "ADMIN_API_TOKEN", "test-key")
    call = Mock(side_effect=GenerationScopeBusy(SCOPE))
    monkeypatch.setattr(admin_routes, function, call)
    response = client.post("/api/admin" + route, json={"date": DAY.isoformat(), "provider": "stub"},
                           headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 409
    assert response.get_json() == {"error": {
        "code": "generation_scope_busy",
        "message": "Generation package is already active or being admitted.",
    }}
    call.assert_called_once()


@pytest.mark.parametrize("as_script", [False, True])
def test_package_cli_busy_returns_one_without_foreign_run_summary(
    cli_runtime, monkeypatch, capsys, as_script,
):
    cli_runtime.generation.side_effect = GenerationScopeBusy(SCOPE)
    set_args(monkeypatch, package_cli)
    assert invoke(package_cli, as_script=as_script) == 1
    captured = capsys.readouterr()
    assert "generation_scope_busy" in captured.err
    assert "run_id:" not in captured.out
    assert "Traceback" not in captured.err
    cli_runtime.generation.assert_called_once()


@pytest.mark.parametrize("entry", ["daily", "retry"])
def test_direct_scheduler_busy_skips_only_its_target(monkeypatch, entry):
    import tasks
    tomorrow = DAY + timedelta(days=1)
    monkeypatch.setattr(tasks, "app", SimpleNamespace(app_context=nullcontext))
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULER_USE_QUEUE", False)
    monkeypatch.setattr(tasks, "scheduled_target_dates", lambda: [DAY, tomorrow])
    monkeypatch.setattr(tasks, "RETRY_MISSING_ENABLED", True)
    monkeypatch.setattr(tasks, "retry_window_is_open", lambda: True)
    monkeypatch.setattr(tasks, "has_generation_coverage", lambda **kwargs: False)
    completed = SimpleNamespace(id=17, status="success", total_items=1, success_items=1,
                                skipped_items=0, failed_items=0)
    generator = Mock(side_effect=[GenerationScopeBusy(SCOPE), completed])
    monkeypatch.setattr(tasks, "run_daily_generation", generator)
    monkeypatch.setattr(tasks, "run_retry_for_missing_forecasts", generator)
    start = Mock(side_effect=AssertionError("scheduler must not start"))
    monkeypatch.setattr(tasks.scheduler, "start", start)
    result = tasks.generate_daily_forecasts() if entry == "daily" else tasks.retry_missing_forecasts()
    assert result["runs"][0] == {
        "date": DAY.isoformat(), "target_date": DAY.isoformat(), "run_id": None,
        "status": "skipped", "reason": "generation_scope_busy",
    }
    assert result["runs"][1]["run_id"] == 17
    assert result["runs"][1]["status"] == "success"
    assert generator.call_count == 2
    assert generator.call_args.kwargs["target_date"] == tomorrow
    start.assert_not_called()

import importlib
from datetime import date


class DummyAppContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class DummyApp:
    def app_context(self):
        return DummyAppContext()


def test_tasks_env_flag_parses_common_truthy_values():
    import tasks

    assert tasks.env_flag("MISSING_FLAG_FOR_TEST", "1") is True
    assert tasks.env_flag("MISSING_FLAG_FOR_TEST", "0") is False


def test_tasks_env_int_uses_default_for_missing_value():
    import tasks

    assert tasks.env_int("MISSING_INT_FOR_TEST", 42, min_value=1) == 42


def test_process_queued_generation_jobs_returns_none_when_disabled(monkeypatch):
    import tasks

    monkeypatch.setattr(tasks, "GENERATION_JOB_WORKER_ENABLED", False)

    assert tasks.process_queued_generation_jobs() is None


def test_process_queued_generation_jobs_calls_service_layer(monkeypatch):
    import tasks

    calls = {}

    def fake_close_stale_running_jobs(*, stale_after_minutes):
        calls["stale_after_minutes"] = stale_after_minutes
        return 2

    def fake_process_generation_jobs(
        *,
        limit,
        worker_id,
        allow_openai,
        stale_after_hours,
    ):
        calls["limit"] = limit
        calls["worker_id"] = worker_id
        calls["allow_openai"] = allow_openai
        calls["stale_after_hours"] = stale_after_hours

        return {
            "worker_id": worker_id,
            "requested_limit": limit,
            "processed_count": 1,
            "jobs": [{"id": 123, "status": "success"}],
        }

    monkeypatch.setattr(tasks, "app", DummyApp())
    monkeypatch.setattr(tasks, "GENERATION_JOB_WORKER_ENABLED", True)
    monkeypatch.setattr(tasks, "GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK", 5)
    monkeypatch.setattr(tasks, "GENERATION_JOB_WORKER_ALLOW_OPENAI", False)
    monkeypatch.setattr(tasks, "GENERATION_JOB_WORKER_ID", "pytest-worker")
    monkeypatch.setattr(tasks, "GENERATION_JOB_STALE_AFTER_MINUTES", 90)
    monkeypatch.setattr(tasks, "GENERATION_STALE_HOURS", 3)
    monkeypatch.setattr(
        tasks,
        "close_stale_running_jobs",
        fake_close_stale_running_jobs,
    )
    monkeypatch.setattr(
        tasks,
        "process_generation_jobs",
        fake_process_generation_jobs,
    )

    result = tasks.process_queued_generation_jobs()

    assert result["processed_count"] == 1
    assert result["stale_closed_count"] == 2
    assert calls == {
        "stale_after_minutes": 90,
        "limit": 5,
        "worker_id": "pytest-worker",
        "allow_openai": False,
        "stale_after_hours": 3,
    }


def test_generate_daily_forecasts_uses_queue_when_enabled(monkeypatch):
    import tasks

    calls = {}

    def fake_current_app_date():
        return date(2026, 6, 20)

    def fake_create_scheduled_generation_job(**kwargs):
        calls.update(kwargs)
        return {
            "job": {"id": 10},
            "created": True,
            "reason": None,
            "date": kwargs["target_date"].isoformat(),
            "target_date": kwargs["target_date"].isoformat(),
            "locale": kwargs["locale"],
            "forecast_type": kwargs["forecast_type"],
            "provider": kwargs["provider"],
            "job_type": "scheduled",
        }

    monkeypatch.setattr(tasks, "app", DummyApp())
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULER_USE_QUEUE", True)
    monkeypatch.setattr(tasks, "HOROSCOPE_PROVIDER", "stub")
    monkeypatch.setattr(tasks, "GENERATION_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(tasks, "MAX_RETRY_RUNS_PER_DAY", 4)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULED_JOB_PRIORITY", 100)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI", False)
    monkeypatch.setattr(tasks, "current_app_date", fake_current_app_date)
    monkeypatch.setattr(
        tasks,
        "create_scheduled_generation_job",
        fake_create_scheduled_generation_job,
    )

    result = tasks.generate_daily_forecasts(run_type="scheduled")

    assert result["created"] is True
    assert calls == {
        "target_date": date(2026, 6, 20),
        "locale": "ru",
        "forecast_type": "daily",
        "provider": "stub",
        "max_attempts": 2,
        "max_retry_runs": 4,
        "max_job_attempts": 1,
        "priority": 100,
        "created_by": "scheduler:scheduled",
        "allow_openai": False,
        "skip_covered": True,
    }


def test_generate_daily_forecasts_legacy_mode_calls_generation_service(monkeypatch):
    import tasks

    calls = {}

    class DummyRun:
        id = 55
        status = "success"
        total_items = 13
        success_items = 13
        skipped_items = 0
        failed_items = 0

    def fake_current_app_date():
        return date(2026, 6, 20)

    def fake_run_daily_generation(**kwargs):
        calls.update(kwargs)
        return DummyRun()

    monkeypatch.setattr(tasks, "app", DummyApp())
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULER_USE_QUEUE", False)
    monkeypatch.setattr(tasks, "HOROSCOPE_PROVIDER", "stub")
    monkeypatch.setattr(tasks, "GENERATION_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(tasks, "GENERATION_STALE_HOURS", 3)
    monkeypatch.setattr(tasks, "current_app_date", fake_current_app_date)
    monkeypatch.setattr(tasks, "run_daily_generation", fake_run_daily_generation)

    run = tasks.generate_daily_forecasts(run_type="scheduled")

    assert run.id == 55
    assert calls == {
        "target_date": date(2026, 6, 20),
        "run_type": "scheduled",
        "locale": "ru",
        "forecast_type": "daily",
        "provider_name": "stub",
        "max_attempts": 2,
        "stale_after_hours": 3,
    }


def test_retry_missing_forecasts_uses_queue_when_enabled(monkeypatch):
    import tasks

    calls = {}

    def fake_current_app_date():
        return date(2026, 6, 20)

    def fake_retry_window_is_open():
        return True

    def fake_create_scheduled_retry_missing_job(**kwargs):
        calls.update(kwargs)
        return {
            "job": {"id": 11},
            "created": True,
            "reason": None,
            "missing_signs": ["aries"],
            "date": kwargs["target_date"].isoformat(),
            "target_date": kwargs["target_date"].isoformat(),
            "locale": kwargs["locale"],
            "forecast_type": kwargs["forecast_type"],
            "provider": kwargs["provider"],
            "job_type": "retry_missing",
        }

    monkeypatch.setattr(tasks, "app", DummyApp())
    monkeypatch.setattr(tasks, "RETRY_MISSING_ENABLED", True)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULER_USE_QUEUE", True)
    monkeypatch.setattr(tasks, "HOROSCOPE_PROVIDER", "stub")
    monkeypatch.setattr(tasks, "GENERATION_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(tasks, "MAX_RETRY_RUNS_PER_DAY", 4)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULED_RETRY_JOB_PRIORITY", 90)
    monkeypatch.setattr(tasks, "GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI", False)
    monkeypatch.setattr(tasks, "current_app_date", fake_current_app_date)
    monkeypatch.setattr(tasks, "retry_window_is_open", fake_retry_window_is_open)
    monkeypatch.setattr(
        tasks,
        "create_scheduled_retry_missing_job",
        fake_create_scheduled_retry_missing_job,
    )

    result = tasks.retry_missing_forecasts()

    assert result["created"] is True
    assert calls == {
        "target_date": date(2026, 6, 20),
        "locale": "ru",
        "forecast_type": "daily",
        "provider": "stub",
        "max_attempts": 2,
        "max_retry_runs": 4,
        "max_job_attempts": 1,
        "priority": 90,
        "created_by": "scheduler:retry_missing",
        "allow_openai": False,
    }


def test_tasks_registers_queue_worker_only_when_enabled(monkeypatch):
    monkeypatch.setenv("GENERATION_JOB_WORKER_ENABLED", "1")
    monkeypatch.setenv("GENERATION_JOB_WORKER_INTERVAL_SECONDS", "60")

    import tasks

    reloaded_tasks = importlib.reload(tasks)

    job_ids = {job.id for job in reloaded_tasks.scheduler.get_jobs()}

    assert "queued_generation_jobs_worker" in job_ids
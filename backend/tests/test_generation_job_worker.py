import importlib


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


def test_tasks_registers_queue_worker_only_when_enabled(monkeypatch):
    monkeypatch.setenv("GENERATION_JOB_WORKER_ENABLED", "1")
    monkeypatch.setenv("GENERATION_JOB_WORKER_INTERVAL_SECONDS", "60")

    import tasks

    reloaded_tasks = importlib.reload(tasks)

    job_ids = {job.id for job in reloaded_tasks.scheduler.get_jobs()}

    assert "queued_generation_jobs_worker" in job_ids
import importlib


def test_tasks_module_imports_without_starting_scheduler():
    tasks = importlib.import_module("tasks")

    assert hasattr(tasks, "generate_daily_forecasts")
    assert hasattr(tasks, "scheduler")
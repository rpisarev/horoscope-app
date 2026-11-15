"""Pure unit checks; run with unittest to avoid the database pytest conftest.

    python -m unittest discover -s backend/tests -p 'test_paid_execution_policy.py'
    python -m unittest discover -s backend/tests -p 'test_paid_execution_probe.py'

Services are loaded with in-memory dependency modules, never the Flask app,
SQLAlchemy models, dotenv configuration, or a database session.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import nullcontext
from datetime import date
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from paid_execution_policy import (
    PAID_EXECUTION_ENV,
    PaidExecutionDenied,
    paid_execution_enabled,
    require_paid_execution,
)
from paid_admission_policy import PaidAdmissionUnavailable


class PaidExecutionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        for target in ("connect", "connect_ex", "sendto"):
            self.enterContext(patch.object(
                socket.socket, target, side_effect=AssertionError("Unexpected network")
            ))
        self.enterContext(patch.object(
            socket, "create_connection", side_effect=AssertionError("Unexpected network")
        ))
        self.enterContext(patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("Unexpected DNS")
        ))
        self.enterContext(patch.dict(sys.modules))

    def test_only_exact_one_enables(self):
        for value in (None, "", "0", "true", "yes", "on", "invalid", "01", " 1", "1 ", "1\n"):
            with self.subTest(value=value):
                os.environ.pop(PAID_EXECUTION_ENV, None)
                if value is not None:
                    os.environ[PAID_EXECUTION_ENV] = value
                self.assertFalse(paid_execution_enabled())
                with self.assertRaisesRegex(PaidExecutionDenied, PAID_EXECUTION_ENV) as raised:
                    require_paid_execution("openai")
                self.assertIs(raised.exception.retryable, False)
        os.environ[PAID_EXECUTION_ENV] = "1"
        self.assertTrue(paid_execution_enabled())
        require_paid_execution("openai")

    def test_stub_and_unknown_development_providers_are_unchanged(self):
        for name in ("stub", "fake", "future-real", "unknown", None, ""):
            with self.subTest(name=name):
                require_paid_execution(name)
        with self.assertRaises(PaidExecutionDenied):
            require_paid_execution(" OPENAI ")

    def test_environment_is_rechecked_after_enable(self):
        os.environ[PAID_EXECUTION_ENV] = "1"
        require_paid_execution("openai")
        os.environ[PAID_EXECUTION_ENV] = "0"
        with self.assertRaises(PaidExecutionDenied):
            require_paid_execution("openai")

    def test_config_snapshot_uses_policy_without_overriding_runtime_environment(self):
        self._module("dotenv", load_dotenv=Mock())
        config = self._load("_paid_execution_config", BACKEND / "app/config.py").Config
        self.assertFalse(config.GENERATION_PAID_EXECUTION_ENABLED)
        config.GENERATION_PAID_EXECUTION_ENABLED = True
        with self.assertRaises(PaidExecutionDenied):
            require_paid_execution("openai")
        os.environ[PAID_EXECUTION_ENV] = "1"
        config = self._load("_paid_execution_config_enabled", BACKEND / "app/config.py").Config
        self.assertTrue(config.GENERATION_PAID_EXECUTION_ENABLED)

    def _module(self, name, **attributes):
        module = ModuleType(name)
        module.__path__ = []
        module.__dict__.update(attributes)
        sys.modules[name] = module
        return module

    def _load(self, name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def _service(self, *, queue=False, provider_name="openai"):
        prefix = "_paid_execution_unit"
        # Pure preflight tests never execute SQL. Later services import Core/
        # ORM names, so provide in-memory symbols rather than requiring a host
        # SQLAlchemy installation or importing application database machinery.
        self._module("sqlalchemy", event=Mock(), inspect=Mock(), select=Mock(), update=Mock())
        self._module("sqlalchemy.exc", IntegrityError=type("IntegrityError", (Exception,), {}))
        self._module("sqlalchemy.orm", Mapper=type("Mapper", (), {}), Session=type("Session", (), {}))
        self.session = Mock()
        self._module(prefix, db=SimpleNamespace(session=self.session))
        self._module(prefix + ".services")
        self._module(prefix + ".services.generation_admission_service",
                     GenerationScopeBusy=type("GenerationScopeBusy", (RuntimeError,), {}),
                     GenerationPackageScope=Mock(), package_admission=Mock(return_value=nullcontext()),
                     package_scope_lock=Mock(return_value=nullcontext()))
        self._module(prefix + ".services.generation_execution_service", **{
            name: Mock() for name in (
                "assert_autonomous_session_clean", "link_execution_run",
                "record_execution_start", "require_execution_activation",
                "require_unlinked_execution", "selected_provider_name",
                "claim_execution_id", "deployment_mode", "unlinked_claim_execution",
            )
        })
        sys.modules[prefix + ".services.generation_execution_service"].ExecutionAlreadyStarted = type(
            "ExecutionAlreadyStarted", (RuntimeError,), {},
        )
        sys.modules[prefix + ".services.generation_execution_service"].selected_provider_name.side_effect = (
            lambda name=None: (name or os.getenv("HOROSCOPE_PROVIDER") or "stub").strip().lower()
        )
        self.provider = SimpleNamespace(
            name=provider_name, model_name="fake-model",
            generate=Mock(side_effect=AssertionError("Unexpected transport")),
        )
        self._module(
            prefix + ".providers", GenerationProviderError=RuntimeError,
            HoroscopeProvider=object, ProviderResult=object,
            get_horoscope_provider=Mock(return_value=self.provider),
        )
        self.publication_check = Mock()
        self._module(prefix + ".providers.publication_policy",
                     require_publication_provider=self.publication_check)
        self._module(prefix + ".providers.registry", PROVIDERS={"stub": None, "openai": None})
        self._module(prefix + ".services.constants", DEFAULT_LOCALE="ru", DEFAULT_FORECAST_TYPE="daily")
        self._module(prefix + ".services.sign_service", get_enabled_sign_keys=Mock(return_value=["aries"]))
        self.models = self._module(prefix + ".models", **{
            name: Mock() for name in (
                "Forecast", "GenerationAttempt", "GenerationItem", "GenerationRun",
                "PromptVersion", "GenerationJob", "GenerationExecution", "GenerationExecutionRun",
            )
        })
        if queue:
            self._module(prefix + ".services.generation_service", **{
                name: Mock(side_effect=AssertionError("Unexpected lifecycle dispatch"))
                for name in (
                    "get_missing_forecast_signs", "has_generation_coverage",
                    "run_daily_generation", "run_retry_for_missing_forecasts",
                )
            })
            return self._load(prefix + ".services.generation_job_service",
                              BACKEND / "app/services/generation_job_service.py")

        self.save_forecast = Mock(side_effect=AssertionError("Unexpected publication"))
        self._module(prefix + ".services.forecast_service",
                     get_published_forecast=Mock(), save_forecast=self.save_forecast)
        self._module(prefix + ".services.forecast_validation_service", find_forbidden_forecast_terms=Mock())
        self.prompt = Mock(return_value=SimpleNamespace(id=1))
        self._module(prefix + ".services.prompt_service",
                     build_provider_request=Mock(), get_prompt_version=self.prompt)
        self.models.GenerationRun.side_effect = lambda **values: SimpleNamespace(
            id=1, items=[], error_message=None, **values
        )
        self.models.GenerationRun.query.filter_by.return_value.first.return_value = None
        service = self._load(prefix + ".services.generation_service",
                             BACKEND / "app/services/generation_service.py")
        service.close_stale_running_runs = Mock()
        return service

    def test_lifecycle_denial_creates_only_failed_run_without_items_attempts_or_publication(self):
        for value in (None, "0", "invalid"):
            with self.subTest(value=value):
                if value is not None:
                    os.environ[PAID_EXECUTION_ENV] = value
                service = self._service()
                run = service.run_daily_generation(
                    target_date=date(2026, 11, 14), provider_name="openai", signs=["aries"]
                )
                self.assertEqual(run.status, "failed")
                self.assertIn("Paid execution denied", run.error_message)
                self.assertEqual(run.total_items, 0)
                self.assertEqual(run.items, [])
                self.models.GenerationItem.assert_not_called()
                self.models.GenerationAttempt.assert_not_called()
                self.session.add.assert_called_once_with(run)
                self.session.add_all.assert_not_called()
                self.provider.generate.assert_not_called()
                self.save_forecast.assert_not_called()
                self.publication_check.assert_not_called()
                self.prompt.assert_not_called()

    def test_stub_lifecycle_reaches_existing_prompt_preflight(self):
        service = self._service(provider_name="stub")
        self.prompt.return_value = None
        run = service.run_daily_generation(target_date=date(2026, 11, 14), signs=["aries"])
        self.assertIn("No active prompt version", run.error_message)
        self.publication_check.assert_called_once_with("stub")
        self.prompt.assert_called_once_with(locale="ru", forecast_type="daily")

    def test_queue_denial_precedes_lifecycle_even_with_worker_opt_in(self):
        service = self._service(queue=True)
        for job_type in (service.JOB_TYPE_MANUAL, service.JOB_TYPE_RETRY_MISSING):
            with self.subTest(job_type=job_type):
                job = SimpleNamespace(
                    id=1, status="running", locked_by="unit", provider="openai", job_type=job_type,
                    run_id=None, attempt_count=1, target_date=date(2026, 11, 14),
                    locale="ru", forecast_type="daily",
                )
                self.session.get.side_effect = (
                    lambda model, identity, **kwargs: job
                    if model is self.models.GenerationJob else None
                )
                service.serialize_generation_job = lambda row: {"status": row.status}
                result = service.process_claimed_generation_job(job, worker_id="unit", allow_openai=True)
                self.assertEqual(result["status"], "failed")
                self.assertIn("Paid execution denied", job.error_message)
                self.assertIsNone(job.run_id)
                service.run_daily_generation.assert_not_called()
                service.run_retry_for_missing_forecasts.assert_not_called()
                service.get_missing_forecast_signs.assert_not_called()
                self.publication_check.assert_not_called()

    def test_enabled_worker_still_requires_local_opt_in_and_key(self):
        service = self._service(queue=True)
        os.environ[PAID_EXECUTION_ENV] = "1"
        job = SimpleNamespace(provider="openai")
        with self.assertRaisesRegex(service.GenerationJobProcessingError, "worker allow_openai"):
            service._ensure_provider_can_execute(job, allow_openai=False)
        with self.assertRaisesRegex(service.GenerationJobProcessingError, "OPENAI_API_KEY"):
            service._ensure_provider_can_execute(job, allow_openai=True)
        os.environ["OPENAI_API_KEY"] = "unit-test-fake-key"
        with self.assertRaises(PaidAdmissionUnavailable):
            service._ensure_provider_can_execute(job, allow_openai=True)

    def test_enabled_lifecycle_denies_canonical_provider_before_factory(self):
        os.environ[PAID_EXECUTION_ENV] = "1"
        service = self._service(provider_name="stub")  # misleading factory result
        run = service.run_daily_generation(
            target_date=date(2026, 11, 14), provider_name=" OPENAI ", signs=["aries"]
        )
        self.assertEqual(run.status, "failed")
        self.assertIn("atomic request admission", run.error_message)
        service.get_horoscope_provider.assert_not_called()
        self.models.GenerationItem.assert_not_called()
        self.models.GenerationAttempt.assert_not_called()
        self.provider.generate.assert_not_called()

    def test_disabled_worker_keeps_stub_path_and_publication_policy(self):
        service = self._service(queue=True)
        service._ensure_provider_can_execute(SimpleNamespace(provider="stub"), allow_openai=False)
        self.publication_check.assert_called_once_with("stub")
        self.publication_check.side_effect = RuntimeError("Publication still denied")
        with self.assertRaisesRegex(RuntimeError, "Publication still denied"):
            service._ensure_provider_can_execute(SimpleNamespace(provider="stub"), allow_openai=False)

    def test_package_cli_allow_openai_cannot_bypass_global_denial(self):
        service = self._service()
        self._module("dotenv", load_dotenv=Mock(side_effect=AssertionError("Unexpected dotenv load")))
        cli = self._load("_paid_execution_package_cli", BACKEND / "utils/generate_forecast_package.py")
        cli.load_local_env = Mock()
        cli.print_run_summary = Mock()
        self._module("app", create_app=Mock(return_value=SimpleNamespace(app_context=nullcontext)))
        self._module("app.services", run_daily_generation=service.run_daily_generation)
        self._module("app.services.generation_admission_service",
                     GenerationScopeBusy=type("GenerationScopeBusy", (RuntimeError,), {}))
        os.environ["OPENAI_API_KEY"] = "unit-test-fake-key"
        with patch.object(sys, "argv", ["generate_forecast_package.py", "--date", "2026-11-14",
                                        "--provider", "openai", "--allow-openai"]), patch("builtins.print"):
            self.assertEqual(cli.main(), 1)
        run = cli.print_run_summary.call_args.args[0]
        self.assertEqual(run.status, "failed")
        self.assertIn("Paid execution denied", run.error_message)
        self.models.GenerationItem.assert_not_called()
        self.models.GenerationAttempt.assert_not_called()
        self.provider.generate.assert_not_called()
        self.save_forecast.assert_not_called()

        os.environ[PAID_EXECUTION_ENV] = "1"
        with self.assertRaisesRegex(SystemExit, "without --allow-openai"):
            cli.require_openai_safety_confirmation("openai", False)
        with patch.object(sys, "argv", ["generate_forecast_package.py", "--date", "2026-11-14",
                                        "--provider", "openai", "--allow-openai"]), patch("builtins.print"):
            self.assertEqual(cli.main(), 1)
        self.assertIn("atomic request admission", cli.print_run_summary.call_args.args[0].error_message)
        self.models.GenerationItem.assert_not_called()
        self.models.GenerationAttempt.assert_not_called()
        self.provider.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

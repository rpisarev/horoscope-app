"""Standalone probe checks with a fake SDK and no app/database imports."""

from __future__ import annotations

import builtins
import importlib.util
import io
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]
SETTING = "GENERATION_PAID_EXECUTION_ENABLED"
MODE_SETTING = "APP_DEPLOYMENT_MODE"
PRODUCTION_DENIAL = "Paid prompt probe is forbidden in production."
INVALID_MODE_DENIAL = (
    "Paid prompt probe denied: APP_DEPLOYMENT_MODE is missing or invalid."
)


class PaidExecutionProbeTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(patch.dict(sys.modules))
        self.enterContext(patch.object(sys, "path", [p for p in sys.path if p != str(BACKEND)]))
        original_import = builtins.__import__
        self.allow_sdk_import = False

        def no_app_import(name, *args, **kwargs):
            if name.split(".")[0] in {"app", "flask", "flask_sqlalchemy", "sqlalchemy"}:
                raise AssertionError(f"Unexpected application import: {name}")
            if name.split(".")[0] == "openai" and not self.allow_sdk_import:
                raise AssertionError("Unexpected SDK import")
            return original_import(name, *args, **kwargs)

        self.enterContext(patch("builtins.__import__", side_effect=no_app_import))
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
        dotenv = ModuleType("dotenv")
        dotenv.load_dotenv = Mock(side_effect=AssertionError("Unexpected dotenv read"))
        sdk = ModuleType("openai")
        sdk.OpenAI = Mock(side_effect=AssertionError("Unexpected SDK client construction"))
        sys.modules.update(dotenv=dotenv, openai=sdk)
        spec = importlib.util.spec_from_file_location(
            "_paid_execution_probe", BACKEND / "utils/openai_prompt_probe.py"
        )
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)
        self.original_load_local_env = self.probe.load_local_env
        self.probe.load_local_env = Mock()
        self.sdk = sdk
        self.policy = sys.modules["paid_execution_policy"]
        self.client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=object())))

    def call_probe(self):
        return self.probe.call_openai(
            client=self.client, model="unit-model", max_output_tokens=5, user_prompt="Unit test"
        )

    def test_direct_helper_denies_missing_zero_and_invalid_without_transport(self):
        os.environ[MODE_SETTING] = "development"
        for value in (None, "0", "invalid", "true", " 1"):
            with self.subTest(value=value):
                os.environ.pop(SETTING, None)
                if value is not None:
                    os.environ[SETTING] = value
                with self.assertRaisesRegex(self.policy.PaidExecutionDenied, SETTING) as raised:
                    self.call_probe()
                self.assertIs(raised.exception.retryable, False)
                self.client.responses.create.assert_not_called()
                self.sdk.OpenAI.assert_not_called()

    def test_enabled_helper_uses_fake_sdk_then_rechecks_after_disable(self):
        os.environ.update({MODE_SETTING: "development", SETTING: "1"})
        self.assertIs(self.call_probe(), self.client.responses.create.return_value)
        self.client.responses.create.assert_called_once()
        self.assertEqual(self.client.responses.create.call_args.kwargs["model"], "unit-model")
        self.client.responses.create.reset_mock()
        os.environ[SETTING] = "0"
        with self.assertRaises(self.policy.PaidExecutionDenied):
            self.call_probe()
        self.client.responses.create.assert_not_called()

    def test_main_denies_before_key_or_sdk(self):
        os.environ[MODE_SETTING] = "development"
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaises(self.policy.PaidExecutionDenied):
                self.probe.main()
        self.sdk.OpenAI.assert_not_called()

    def test_enabled_main_still_requires_key(self):
        os.environ.update({MODE_SETTING: "development", SETTING: "1"})
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY is missing"):
                self.probe.main()
        self.sdk.OpenAI.assert_not_called()

    def test_list_profiles_remains_read_only_while_denied(self):
        os.environ.update({
            "OPENAI_MODEL": "secret-model-marker",
            "OPENAI_TIMEOUT_SECONDS": "invalid-timeout-secret",
            "OPENAI_MAX_OUTPUT_TOKENS": "invalid-token-secret",
        })
        for mode in (None, "", "invalid-secret-marker", "production", "development", "test"):
            for gate in ("0", "1"):
                for key in (None, "unit-test-fake-key"):
                    with self.subTest(mode=mode, gate=gate, key_present=key is not None):
                        self.set_mode(mode)
                        os.environ[SETTING] = gate
                        os.environ.pop("OPENAI_API_KEY", None)
                        if key is not None:
                            os.environ["OPENAI_API_KEY"] = key
                        output = io.StringIO()
                        with patch.object(sys, "argv", ["openai_prompt_probe.py", "--list-profiles"]), \
                                patch("sys.stdout", output), patch("sys.stderr", output):
                            self.assertEqual(self.probe.main(), 0)
                        self.assertIn("Available profiles", output.getvalue())
                        self.assertNotIn("unit-test-fake-key", output.getvalue())
                        self.assertNotIn("invalid-secret-marker", output.getvalue())
                        self.assertNotIn("secret-model-marker", output.getvalue())
                        self.assertNotIn("invalid-timeout-secret", output.getvalue())
                        self.assertNotIn("invalid-token-secret", output.getvalue())
                        self.probe.load_local_env.assert_not_called()
                        self.sdk.OpenAI.assert_not_called()
                        self.client.responses.create.assert_not_called()

    def test_main_rechecks_inside_helper_after_preflight(self):
        os.environ.update({
            MODE_SETTING: "development", SETTING: "1", "OPENAI_API_KEY": "unit-test-fake-key"
        })
        self.allow_sdk_import = True

        def construct_fake_client(**kwargs):
            os.environ[SETTING] = "0"
            return self.client

        self.sdk.OpenAI.side_effect = construct_fake_client
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaises(self.policy.PaidExecutionDenied):
                self.probe.main()
        self.sdk.OpenAI.assert_called_once()
        self.client.responses.create.assert_not_called()

    def set_mode(self, mode):
        os.environ.pop(MODE_SETTING, None)
        if mode is not None:
            os.environ[MODE_SETTING] = mode

    def assert_mode_denied(self, call, message):
        with self.assertRaises(self.probe.ProbeExecutionDenied) as raised:
            call()
        self.assertEqual(str(raised.exception), message)
        self.assertIsInstance(raised.exception, self.policy.PaidExecutionDenied)
        self.assertIs(raised.exception.retryable, False)
        self.client.responses.create.assert_not_called()

    def test_production_denies_main_and_helper_regardless_of_global_gate(self):
        for mode in ("production", "PRODUCTION", " Production "):
            for gate in ("0", "1"):
                for key in (None, "unit-test-fake-key"):
                    with self.subTest(mode=mode, gate=gate, key_present=key is not None):
                        os.environ.update({MODE_SETTING: mode, SETTING: gate})
                        os.environ.pop("OPENAI_API_KEY", None)
                        if key is not None:
                            os.environ["OPENAI_API_KEY"] = key
                        self.assert_mode_denied(self.call_probe, PRODUCTION_DENIAL)
                        output = io.StringIO()
                        with patch.object(sys, "argv", ["openai_prompt_probe.py", "--show-prompt"]), \
                                patch("sys.stdout", output), patch("sys.stderr", output):
                            self.assert_mode_denied(self.probe.main, PRODUCTION_DENIAL)
                        self.assertEqual(output.getvalue(), "")
                        self.sdk.OpenAI.assert_not_called()

    def test_missing_or_invalid_mode_fails_closed_in_main_and_helper(self):
        for mode in (None, "", " ", "invalid", "prod", "dev", "secret-marker\nproduction"):
            for gate in ("0", "1"):
                with self.subTest(mode=mode, gate=gate):
                    self.set_mode(mode)
                    os.environ.update({SETTING: gate, "OPENAI_API_KEY": "unit-test-fake-key"})
                    self.assert_mode_denied(self.call_probe, INVALID_MODE_DENIAL)
                    with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
                        self.assert_mode_denied(self.probe.main, INVALID_MODE_DENIAL)
                    self.sdk.OpenAI.assert_not_called()

    def test_nonproduction_modes_still_require_independent_safe001_gate(self):
        for mode in ("development", "test", " Development ", "TEST"):
            for gate in (None, "", "0", "invalid", "true", " 1"):
                with self.subTest(mode=mode, gate=gate):
                    os.environ[MODE_SETTING] = mode
                    os.environ.pop(SETTING, None)
                    if gate is not None:
                        os.environ[SETTING] = gate
                    for call in (self.call_probe, self.probe.main):
                        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
                            with self.assertRaisesRegex(self.policy.PaidExecutionDenied, SETTING) as raised:
                                call()
                        self.assertNotIsInstance(raised.exception, self.probe.ProbeExecutionDenied)
                        self.assertIs(raised.exception.retryable, False)
                    self.client.responses.create.assert_not_called()
                    self.sdk.OpenAI.assert_not_called()

    def test_explicit_nonproduction_helper_compatibility_uses_only_fake_requests(self):
        os.environ[SETTING] = "1"
        for mode in ("development", "test", " Development ", "TEST"):
            with self.subTest(mode=mode):
                os.environ[MODE_SETTING] = mode
                self.assertIs(self.call_probe(), self.client.responses.create.return_value)
                self.client.responses.create.assert_called_once()
                self.client.responses.create.reset_mock()
        self.sdk.OpenAI.assert_not_called()

    def test_helper_rechecks_mode_on_every_call(self):
        os.environ[SETTING] = "1"
        for mode, message in (
            ("production", PRODUCTION_DENIAL),
            (None, INVALID_MODE_DENIAL),
            ("invalid", INVALID_MODE_DENIAL),
        ):
            with self.subTest(mode=mode):
                os.environ[MODE_SETTING] = "development"
                self.call_probe()
                self.client.responses.create.assert_called_once()
                self.client.responses.create.reset_mock()
                self.set_mode(mode)
                self.assert_mode_denied(self.call_probe, message)

    def test_main_rechecks_mode_inside_helper_after_preflight(self):
        os.environ.update({SETTING: "1", "OPENAI_API_KEY": "unit-test-fake-key"})
        self.allow_sdk_import = True
        for mode, message in (
            ("production", PRODUCTION_DENIAL),
            (None, INVALID_MODE_DENIAL),
            ("invalid", INVALID_MODE_DENIAL),
        ):
            with self.subTest(mode=mode):
                os.environ[MODE_SETTING] = "development"

                def construct_fake_client(**kwargs):
                    self.set_mode(mode)
                    return self.client

                self.sdk.OpenAI.side_effect = construct_fake_client
                with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
                    self.assert_mode_denied(self.probe.main, message)
                self.sdk.OpenAI.assert_called_once()
                self.sdk.OpenAI.reset_mock()

    def test_main_rechecks_mode_between_batch_requests(self):
        os.environ.update({
            MODE_SETTING: "development", SETTING: "1", "OPENAI_API_KEY": "unit-test-fake-key"
        })
        self.allow_sdk_import = True
        self.sdk.OpenAI.side_effect = None
        self.sdk.OpenAI.return_value = self.client

        def first_fake_response(**kwargs):
            os.environ[MODE_SETTING] = "production"
            return SimpleNamespace(output_text='{"title": null, "text": "Unit test"}')

        self.client.responses.create.side_effect = first_fake_response
        with patch.object(sys, "argv", ["openai_prompt_probe.py", "--batch", "2"]), \
                patch("sys.stdout", io.StringIO()):
            with self.assertRaisesRegex(self.probe.ProbeExecutionDenied, "forbidden in production"):
                self.probe.main()
        self.sdk.OpenAI.assert_called_once()
        self.client.responses.create.assert_called_once()

    def test_process_mode_cannot_be_overridden_by_flask_config(self):
        flask = ModuleType("flask")
        flask.current_app = SimpleNamespace(config={MODE_SETTING: "development", SETTING: True})
        sys.modules["flask"] = flask
        os.environ.update({MODE_SETTING: "production", SETTING: "1"})
        self.assert_mode_denied(self.call_probe, PRODUCTION_DENIAL)
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            self.assert_mode_denied(self.probe.main, PRODUCTION_DENIAL)
        self.sdk.OpenAI.assert_not_called()

    def test_exported_production_mode_cannot_be_overridden_by_dotenv(self):
        os.environ.update({MODE_SETTING: "production", SETTING: "1"})
        self.probe.load_local_env.side_effect = self.original_load_local_env

        def fake_dotenv_load(path, *, override):
            self.assertIs(override, False)
            # Simulate a development dotenv without reading any file.
            os.environ.setdefault(MODE_SETTING, "development")
            os.environ.setdefault("OPENAI_API_KEY", "unit-test-fake-key")

        with patch.object(self.probe.Path, "exists", return_value=True), \
                patch.object(self.probe, "load_dotenv", side_effect=fake_dotenv_load) as loader, \
                patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            self.assert_mode_denied(self.probe.main, PRODUCTION_DENIAL)
        self.assertEqual(loader.call_count, 3)
        self.assertEqual(os.environ[MODE_SETTING], "production")
        self.sdk.OpenAI.assert_not_called()

    def test_main_preserves_request_option_precedence_with_fake_sdk(self):
        self.allow_sdk_import = True
        self.sdk.OpenAI.side_effect = None
        self.sdk.OpenAI.return_value = self.client
        self.client.responses.create.return_value = SimpleNamespace(
            output_text='{"title": null, "text": "Unit test"}'
        )

        def fake_env_load():
            os.environ.update({
                MODE_SETTING: "development",
                SETTING: "1",
                "OPENAI_API_KEY": "unit-test-fake-key",
                "OPENAI_MODEL": "env-model",
                "OPENAI_TIMEOUT_SECONDS": "17",
                "OPENAI_MAX_OUTPUT_TOKENS": "19",
            })

        self.probe.load_local_env.side_effect = fake_env_load
        for options, model, timeout, tokens in (
            ([], "env-model", 17.0, 19),
            (["--model", "cli-model", "--timeout", "7", "--max-output-tokens", "9"],
             "cli-model", 7.0, 9),
        ):
            with self.subTest(options=options):
                os.environ.clear()
                with patch.object(sys, "argv", ["openai_prompt_probe.py", *options]), \
                        patch("sys.stdout", io.StringIO()):
                    self.assertEqual(self.probe.main(), 0)
                self.sdk.OpenAI.assert_called_once_with(
                    api_key="unit-test-fake-key", timeout=timeout
                )
                self.client.responses.create.assert_called_once()
                request = self.client.responses.create.call_args.kwargs
                self.assertEqual(request["model"], model)
                self.assertEqual(request["max_output_tokens"], tokens)
                self.sdk.OpenAI.reset_mock()
                self.client.responses.create.reset_mock()


if __name__ == "__main__":
    unittest.main()

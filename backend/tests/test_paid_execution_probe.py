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


class PaidExecutionProbeTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(patch.dict(sys.modules))
        self.enterContext(patch.object(sys, "path", [p for p in sys.path if p != str(BACKEND)]))
        original_import = builtins.__import__

        def no_app_import(name, *args, **kwargs):
            if name.split(".")[0] in {"app", "flask", "flask_sqlalchemy", "sqlalchemy"}:
                raise AssertionError(f"Unexpected application import: {name}")
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
        self.probe.load_local_env = Mock()
        self.sdk = sdk
        self.policy = sys.modules["paid_execution_policy"]
        self.client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=object())))

    def call_probe(self):
        return self.probe.call_openai(
            client=self.client, model="unit-model", max_output_tokens=5, user_prompt="Unit test"
        )

    def test_direct_helper_denies_missing_zero_and_invalid_without_transport(self):
        for value in (None, "0", "invalid", "true", " 1"):
            with self.subTest(value=value):
                os.environ.pop(SETTING, None)
                if value is not None:
                    os.environ[SETTING] = value
                with self.assertRaisesRegex(self.policy.PaidExecutionDenied, SETTING):
                    self.call_probe()
                self.client.responses.create.assert_not_called()
                self.sdk.OpenAI.assert_not_called()

    def test_enabled_helper_uses_fake_sdk_then_rechecks_after_disable(self):
        os.environ[SETTING] = "1"
        self.assertIs(self.call_probe(), self.client.responses.create.return_value)
        self.client.responses.create.assert_called_once()
        self.assertEqual(self.client.responses.create.call_args.kwargs["model"], "unit-model")
        self.client.responses.create.reset_mock()
        os.environ[SETTING] = "0"
        with self.assertRaises(self.policy.PaidExecutionDenied):
            self.call_probe()
        self.client.responses.create.assert_not_called()

    def test_main_denies_before_key_or_sdk(self):
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaises(self.policy.PaidExecutionDenied):
                self.probe.main()
        self.sdk.OpenAI.assert_not_called()

    def test_enabled_main_still_requires_key(self):
        os.environ[SETTING] = "1"
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY is missing"):
                self.probe.main()
        self.sdk.OpenAI.assert_not_called()

    def test_list_profiles_remains_read_only_while_denied(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["openai_prompt_probe.py", "--list-profiles"]), \
                patch("sys.stdout", output):
            self.assertEqual(self.probe.main(), 0)
        self.assertIn("Available profiles", output.getvalue())
        self.sdk.OpenAI.assert_not_called()
        self.client.responses.create.assert_not_called()

    def test_main_rechecks_inside_helper_after_preflight(self):
        os.environ.update({SETTING: "1", "OPENAI_API_KEY": "unit-test-fake-key"})

        def construct_fake_client(**kwargs):
            os.environ[SETTING] = "0"
            return self.client

        self.sdk.OpenAI.side_effect = construct_fake_client
        with patch.object(sys, "argv", ["openai_prompt_probe.py"]):
            with self.assertRaises(self.policy.PaidExecutionDenied):
                self.probe.main()
        self.sdk.OpenAI.assert_called_once()
        self.client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()

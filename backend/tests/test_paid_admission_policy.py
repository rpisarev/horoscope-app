"""Pure unittest tests: no Flask, pytest fixtures, database or provider SDK."""

import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from paid_admission_policy import PaidAdmissionUnavailable, require_paid_admission
from paid_execution_policy import PaidExecutionDenied


class PaidAdmissionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        for name in ("connect", "connect_ex", "sendto"):
            self.enterContext(patch.object(socket.socket, name, side_effect=AssertionError("Unexpected network")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("Unexpected network")))
        self.enterContext(patch.object(socket, "getaddrinfo", side_effect=AssertionError("Unexpected DNS")))

    def test_safe001_is_checked_first(self):
        for setting in (None, "0", "invalid", " 1"):
            with self.subTest(setting=setting):
                os.environ.pop("GENERATION_PAID_EXECUTION_ENABLED", None)
                if setting is not None:
                    os.environ["GENERATION_PAID_EXECUTION_ENABLED"] = setting
                with self.assertRaises(PaidExecutionDenied) as caught:
                    require_paid_admission("openai")
                self.assertIs(type(caught.exception), PaidExecutionDenied)
                self.assertIs(caught.exception.retryable, False)

    def test_enablement_and_all_deployment_modes_still_deny(self):
        os.environ["GENERATION_PAID_EXECUTION_ENABLED"] = "1"
        for mode in (None, "development", "test", "production", "invalid"):
            with self.subTest(mode=mode):
                os.environ.pop("APP_DEPLOYMENT_MODE", None)
                if mode is not None:
                    os.environ["APP_DEPLOYMENT_MODE"] = mode
                with self.assertRaises(PaidAdmissionUnavailable) as caught:
                    require_paid_admission(" OPENAI ")
                self.assertEqual(caught.exception.code, "paid_admission_unavailable")
                self.assertIs(caught.exception.retryable, False)

    def test_nonpaid_workflows_are_unchanged(self):
        for name in (None, "", "stub", "fake"):
            require_paid_admission(name)

    def test_error_does_not_echo_configuration(self):
        os.environ["GENERATION_PAID_EXECUTION_ENABLED"] = "1"
        os.environ["OPENAI_API_KEY"] = "test-key-never-used"
        with self.assertRaises(PaidAdmissionUnavailable) as caught:
            require_paid_admission("openai")
        self.assertNotIn("test-key-never-used", str(caught.exception))
        self.assertNotIn("OPENAI_API_KEY", str(caught.exception))

    def test_no_caller_override(self):
        os.environ["GENERATION_PAID_EXECUTION_ENABLED"] = "1"
        with self.assertRaises(TypeError):
            require_paid_admission("openai", enabled=True)
        with self.assertRaises(PaidAdmissionUnavailable):
            require_paid_admission("openai")

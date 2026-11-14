"""Pure negative tests: never import the app or backend/tests/conftest.py."""

import ast
import io
import os
from pathlib import Path
import socket
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_db_guard as guard


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "a" * 32


def runtime_env(name="horoscope_test"):
    return {
        "TEST_DB_NAME": name,
        "TEST_DB_IDENTITY": guard.database_url(name),
        "TEST_DB_RUN_ID": RUN_ID,
        "DATABASE_URL": guard.database_url(name),
        "POSTGRES_HOST": "test-db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": name,
        "POSTGRES_USER": "test_runner",
        "POSTGRES_PASSWORD": "dummy-test-db",
        "APP_DEPLOYMENT_MODE": "test",
        "HOROSCOPE_PROVIDER": "stub",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def resolved_url(**changes):
    fields = dict(drivername="postgresql+psycopg", host="test-db", port=5432,
                  database="horoscope_test", username="test_runner",
                  password="dummy-test-db", query={})
    fields.update(changes)
    return SimpleNamespace(**fields)


class NoNetworkTest(unittest.TestCase):
    def setUp(self):
        self.socket_patch = patch.object(socket, "socket", side_effect=AssertionError("Unexpected network"))
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)
        self.dns_patch = patch.object(socket, "getaddrinfo", side_effect=AssertionError("Unexpected DNS"))
        self.dns_patch.start()
        self.addCleanup(self.dns_patch.stop)


class HostPreflightTests(NoNetworkTest):
    def test_every_inherited_database_or_compose_override_is_rejected(self):
        for key in ("DATABASE_URL", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT",
                    "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE",
                    "PGHOST", "PGSERVICE", "PGOPTIONS", "PGPASSFILE", "PGPORT",
                    "COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
                    "DOCKER_HOST", "DOCKER_CONTEXT", "ALLOW_PYTEST_ON_DEV_DB",
                    "KEEP_TEST_DB", "PYTEST_ADDOPTS", "TEST_DB_RUN_ID"):
            for value in ("", "anything"):
                with self.subTest(key=key, value=value), self.assertRaises(guard.SafetyError):
                    guard.validate_host({key: value}, [])

    def test_production_development_and_live_provider_are_rejected(self):
        for key, value in (("APP_DEPLOYMENT_MODE", "production"),
                           ("APP_DEPLOYMENT_MODE", "development"),
                           ("HOROSCOPE_PROVIDER", "openai"),
                           ("OPENAI_API_KEY", "sk-example-not-a-real-key"),
                           ("ADMIN_API_TOKEN", "operator-token")):
            with self.subTest(key=key), self.assertRaises(guard.SafetyError):
                guard.validate_host({key: value}, [])

    def test_positive_disposable_namespace_and_explicit_custom_identity(self):
        for name in ("horoscope", "production", "db_test", "horoscope_test_prod/other",
                     "", "horoscope_test_", "Horoscope_test", "horoscope_test_" + "a" * 60):
            with self.subTest(name=name), self.assertRaises(guard.SafetyError):
                guard.validate_host({"TEST_DB_NAME": name}, [])
        with self.assertRaises(guard.SafetyError):
            guard.validate_host({"TEST_DB_NAME": "horoscope_test_ci"}, [])
        name = "horoscope_test_ci"
        self.assertEqual(guard.validate_host({"TEST_DB_NAME": name,
                          "TEST_DB_IDENTITY": guard.database_url(name)}, []).name, name)
        with self.assertRaises(guard.SafetyError):
            guard.validate_host({"TEST_DB_NAME": name,
                                 "TEST_DB_IDENTITY": guard.database_url("horoscope_test")}, [])

    def test_only_positive_existing_file_or_node_selectors(self):
        for selector in ("-p", "--confcutdir=/", "-c", "../tests/test_config.py",
                         "tests/../test_db_guard.py", "utils/openai_prompt_probe.py",
                         "tests/test_config.py;false", "tests/no_such_file.py",
                         "tests/test_config.py::", "tests/test_config.py::a --no-header"):
            with self.subTest(selector=selector), self.assertRaises(guard.SafetyError):
                guard.validate_host({}, [selector])
        self.assertEqual(guard.validate_host({}, []).name, "horoscope_test")
        guard.validate_host({}, ["tests/test_config.py", "tests/test_config.py::test_read_secret_file_returns_none_for_missing_path"])


class RuntimeIdentityTests(NoNetworkTest):
    def test_pytest_runtime_metadata_is_allowed_but_options_are_not(self):
        env = runtime_env()
        env.update(PYTEST_VERSION="8.4.2", PYTEST_CURRENT_TEST="tests/test_config.py (setup)")
        guard.validate_runtime(env)
        for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
            with self.subTest(key=key), self.assertRaises(guard.SafetyError):
                guard.validate_runtime({**env, key: "untrusted"})

    def test_missing_identity_and_conflicting_overrides_fail_without_connection(self):
        for key, value in (("DATABASE_URL", "postgresql+psycopg://user:secret@db:5432/horoscope"),
                           ("POSTGRES_DB", "horoscope"), ("POSTGRES_HOST", "db"),
                           ("POSTGRES_PORT", "5433"), ("POSTGRES_USER", "operator"),
                           ("POSTGRES_PASSWORD_FILE", "/must-not-be-read"),
                           ("PGHOST", "production"), ("ALLOW_PYTEST_ON_DEV_DB", "1"),
                           ("TEST_DB_RUN_ID", ""), ("TEST_DB_IDENTITY", ""),
                           ("APP_DEPLOYMENT_MODE", "production")):
            env = runtime_env()
            env[key] = value
            with self.subTest(key=key), self.assertRaises(guard.SafetyError):
                guard.validate_runtime(env)
        for key in runtime_env():
            env = runtime_env()
            del env[key]
            with self.subTest(missing=key), self.assertRaises(guard.SafetyError):
                guard.validate_runtime(env)

    def test_resolved_sqlalchemy_url_checks_every_target_component(self):
        identity = guard.validate_runtime(runtime_env())
        for field, value in (("drivername", "sqlite"), ("drivername", "postgresql"),
                             ("host", "db"), ("host", "127.0.0.1"), ("port", None),
                             ("port", 5433), ("database", "horoscope"),
                             ("username", "postgres"), ("password", "real-secret"),
                             ("query", {"host": "production"})):
            with self.subTest(field=field, value=value), self.assertRaises(guard.SafetyError):
                guard.assert_url(resolved_url(**{field: value}), identity)
        guard.assert_url(resolved_url(), identity)
        for url in (identity.url + "?host=production", identity.url.replace("test-db", "db"),
                    "sqlite:///db.sqlite3", identity.url.replace(":5432", "")):
            with self.subTest(url=url), self.assertRaises(guard.SafetyError):
                guard.assert_url(url, identity)

    def test_actual_connection_is_verified_with_read_only_query(self):
        identity = guard.validate_runtime(runtime_env())
        expected = (identity.name, "test_runner", 5432, RUN_ID)
        for actual in (("horoscope", *expected[1:]), (expected[0], "postgres", *expected[2:]),
                       (*expected[:2], 5433, RUN_ID), (*expected[:3], None),
                       (*expected[:3], "b" * 32), None):
            connection = Mock()
            connection.engine.url = resolved_url()
            connection.exec_driver_sql.return_value.one.return_value = actual
            with self.subTest(actual=actual), self.assertRaises(guard.SafetyError):
                guard.assert_connection(connection, identity)
            sql = connection.exec_driver_sql.call_args.args[0]
            self.assertTrue(sql.startswith("SELECT current_database()"))
            self.assertNotIn("TRUNCATE", sql)
        connection = Mock()
        connection.engine.url = resolved_url(host="db")
        with self.assertRaises(guard.SafetyError):
            guard.assert_connection(connection, identity)
        connection.exec_driver_sql.assert_not_called()

    def test_valid_connection_passes(self):
        identity = guard.validate_runtime(runtime_env())
        connection = Mock()
        connection.engine.url = resolved_url()
        connection.exec_driver_sql.return_value.one.return_value = (identity.name, "test_runner", 5432, RUN_ID)
        guard.assert_connection(connection, identity)

    def test_fixture_cannot_mutate_when_identity_check_fails(self):
        # Execute only the cleanup function AST, never import the DB conftest.
        tree = ast.parse((ROOT / "backend/tests/conftest.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_clean_mutable_tables")
        db = Mock()
        scope = {"db": db, "text": lambda sql: sql,
                 "_assert_safe_test_database": Mock(side_effect=guard.SafetyError("unsafe"))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "cleanup-guard", "exec"), scope)
        with self.assertRaises(guard.SafetyError):
            scope["_clean_mutable_tables"]()
        db.session.execute.assert_not_called()
        db.session.commit.assert_not_called()

    def test_runtime_registers_one_shared_hook_and_checks_each_new_connection(self):
        event = Mock()
        modules = {"dotenv": SimpleNamespace(load_dotenv=Mock()),
                   "sqlalchemy": SimpleNamespace(event=event),
                   "sqlalchemy.engine": SimpleNamespace(Engine=object)}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, runtime_env(), clear=True), \
                patch.object(guard, "_runtime_identity", None), \
                patch.object(guard, "_network_policy", None), \
                patch.object(socket, "getaddrinfo", return_value=[(None, None, None, None, ("172.30.0.2", 5432))]), \
                patch.object(sys, "addaudithook") as add_hook:
            first = guard.prepare_runtime()
            self.assertEqual(guard.prepare_runtime(), first)
            add_hook.assert_called_once()
            event.listen.assert_called_once()
            callback = event.listen.call_args.args[2]
            connection = Mock()
            connection.engine.url = resolved_url()
            connection.exec_driver_sql.return_value.one.return_value = (first.name, "test_runner", 5432, RUN_ID)
            callback(connection)
            connection.rollback.assert_called_once()
            connection.reset_mock()
            connection.exec_driver_sql.return_value.one.return_value = ("horoscope", "test_runner", 5432, RUN_ID)
            with self.assertRaises(guard.SafetyError):
                callback(connection)
            connection.rollback.assert_not_called()

    def test_main_publishes_canonical_guard_module_before_conftest_import(self):
        with patch.dict(sys.modules), patch.dict(os.environ, {}, clear=True), \
                patch.object(sys, "argv", ["test_db_guard.py", "host"]), \
                patch.object(sys, "stdout", io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ROOT / "backend/test_db_guard.py"), run_name="__main__")
            self.assertEqual(result.exception.code, 0)
            canonical = sys.modules["test_db_guard"]
            self.assertEqual(canonical.__name__, "__main__")
            self.assertIs(canonical.prepare_runtime.__globals__, canonical.__dict__)


class NetworkPolicyTests(NoNetworkTest):
    def test_outbound_network_and_child_processes_fail_closed(self):
        policy = guard.NetworkPolicy({"test-db", "172.30.0.2"})
        for event, args in (("socket.connect", (None, ("api.openai.com", 443))),
                            ("socket.connect", (None, ("172.30.0.2", 443))),
                            ("socket.connect", (None, ("127.0.0.1", 5432))),
                            ("socket.connect", (None, "/var/run/postgresql/.s.PGSQL.5432")),
                            ("socket.getaddrinfo", ("api.openai.com", 443, 0, 0, 0)),
                            ("socket.sendto", (None, ("8.8.8.8", 53))),
                            ("subprocess.Popen", ("curl", [], None, {})),
                            ("os.system", ("curl example.com",))):
            with self.subTest(event=event, args=args), self.assertRaises(guard.NetworkViolation):
                policy(event, args)
        policy("socket.connect", (None, ("172.30.0.2", 5432)))
        policy("socket.getaddrinfo", ("test-db", 5432, 0, 0, 0))
        # psycopg resolves libpq connection parameters, whose port is a string.
        policy("socket.getaddrinfo", ("test-db", "5432", 0, 0, 0))
        for port in ("5433", "postgresql", "05432", None):
            with self.subTest(port=port), self.assertRaises(guard.NetworkViolation):
                policy("socket.getaddrinfo", ("test-db", port, 0, 0, 0))
        policy("open", ("test.py", "r", 0))

    def test_only_explicit_dummy_credentials_are_allowed(self):
        for token in ("test-key", "test-api-key", "test-key-never-used", "dummy-test-token", "unit-test-fake-key", ""):
            guard.validate_credentials({"OPENAI_API_KEY": token})
        for token in ("sk-placeholder", "test-any-arbitrary-secret", "actual-looking-value"):
            with self.subTest(token=token), self.assertRaises(guard.SafetyError):
                guard.validate_credentials({"OPENAI_API_KEY": token})
        policy = guard.NetworkPolicy(set())
        with self.assertRaises(guard.NetworkViolation):
            policy("os.putenv", (b"OPENAI_API_KEY", b"sk-placeholder"))

    def test_network_failure_cannot_be_swallowed_by_provider_exception_handlers(self):
        self.assertFalse(issubclass(guard.NetworkViolation, Exception))
        with self.assertRaises(guard.NetworkViolation):
            try:
                guard.NetworkPolicy(set())("socket.connect", (None, ("example.invalid", 443)))
            except Exception:
                self.fail("Provider broad handler swallowed an unexpected network call")

    def test_swallowed_violations_override_pytest_success(self):
        for event, args in (("socket.connect", (None, ("example.invalid", 443))),
                            ("subprocess.Popen", ("curl", [], None, {})),
                            ("os.putenv", (b"OPENAI_API_KEY", b"sk-placeholder"))):
            policy = guard.NetworkPolicy(set())
            try:
                policy(event, args)
            except BaseException:
                pass
            with self.subTest(event=event), patch.object(guard, "_network_policy", policy):
                self.assertEqual(len(policy.violations), 1)
                with patch("sys.stderr"):
                    self.assertEqual(guard.suite_exit_code(0), 1)
                    self.assertNotEqual(guard.suite_exit_code(2), 0)
        with patch.object(guard, "_network_policy", guard.NetworkPolicy(set())):
            self.assertEqual(guard.suite_exit_code(0), 0)
            self.assertEqual(guard.suite_exit_code(2), 2)


class ShellOrderingTests(NoNetworkTest):
    def run_script(self, overrides=None, selectors=(), docker_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            docker = directory / "docker"
            log = directory / "docker.log"
            docker.write_text(
                f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n'
                f'case "$*" in *" run --rm "*) exit {docker_exit};; esac\nexit 0\n'
            )
            docker.chmod(0o755)
            env = {"PATH": f"{directory}:/usr/local/bin:/usr/bin:/bin", "HOME": str(directory)}
            env.update(overrides or {})
            result = subprocess.run(["bash", str(ROOT / "scripts/backend-test.sh"), *selectors],
                                    env=env, cwd=ROOT, capture_output=True, text=True, timeout=20)
            return result, log.read_text() if log.exists() else ""

    def test_negative_inputs_never_invoke_even_docker_config_or_cleanup(self):
        for overrides, selectors in (({"DATABASE_URL": "must-never-be-printed"}, ()),
                                     ({"POSTGRES_DB": "horoscope"}, ()),
                                     ({"TEST_DB_NAME": "horoscope"}, ()),
                                     ({"TEST_DB_NAME": "horoscope_test_ci"}, ()),
                                     ({"ALLOW_PYTEST_ON_DEV_DB": "1"}, ()),
                                     ({"COMPOSE_FILE": "docker-compose.yml"}, ()),
                                     ({}, ("--confcutdir=/",))):
            with self.subTest(overrides=overrides, selectors=selectors):
                result, log = self.run_script(overrides, selectors)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(log, "")
                self.assertNotIn("must-never-be-printed", result.stdout + result.stderr)

    def test_all_operations_are_scoped_and_cleanup_never_deletes_volumes(self):
        result, log = self.run_script(selectors=("tests/test_config.py",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("compose.backend-tests.yml", log)
        self.assertIn("--env-file /dev/null", log)
        self.assertIn("--project-name horoscope-test-", log)
        self.assertIn("tests/test_config.py", log)
        self.assertNotIn("--volumes", log)
        self.assertNotIn(" -v", log)
        self.assertNotIn("dropdb", log)
        self.assertNotIn("createdb", log)
        self.assertTrue(log.splitlines()[-1].endswith("down --timeout 10"))

    def test_failed_docker_run_remains_failure_even_after_cleanup(self):
        result, log = self.run_script(docker_exit=42)
        self.assertEqual(result.returncode, 42)
        self.assertTrue(log.splitlines()[-1].endswith("down --timeout 10"))


if __name__ == "__main__":
    unittest.main()

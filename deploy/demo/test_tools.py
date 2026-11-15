"""No database/container execution: guard unit tests and Compose model checks."""

from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, call, patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/demo_tools"))

import bootstrap
import demo_common as common
import migrate

INSTANCE = UUID("11111111-1111-4111-8111-111111111111")


def valid_environment():
    return {**common.SAFETY_ENV, "DEMO_EXPECTED_DATABASE": common.DATABASE,
            "DEMO_EXPECTED_INSTANCE_ID": str(INSTANCE)}


def connection_with_rows(*rows):
    connection = Mock()
    results = []
    for value in rows:
        result = Mock()
        result.fetchone.return_value = value
        result.fetchall.return_value = value
        results.append(result)
    connection.execute.side_effect = results
    return connection


def marker_rows():
    return [
        (common.DATABASE, common.OWNER, common.OWNER),
        (False, False, False, False, False),
        None,
        [(common.OWNER, common.OWNER, common.OWNER)],
        [(1, "horoscope-demo", 1, INSTANCE, common.DATABASE, common.IMPORTER)],
    ]


class GuardTests(unittest.TestCase):
    def test_explicit_environment(self):
        self.assertEqual(common.validate_environment(valid_environment()), INSTANCE)

    def test_generic_database_overrides_even_empty_are_refused(self):
        for key in ("DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PASSWORD_FILE", "PGHOST", "PGSERVICE", "PGOPTIONS"):
            with self.subTest(key=key), self.assertRaises(common.Refused):
                common.validate_environment({**valid_environment(), key: ""})

    def test_incomplete_or_unsafe_environment_is_refused(self):
        changes = [{"DEMO_EXPECTED_DATABASE": "horoscope"},
                   {"DEMO_EXPECTED_INSTANCE_ID": ""},
                   {"DEMO_EXPECTED_INSTANCE_ID": str(UUID(int=0))},
                   {"DEMO_EXPECTED_INSTANCE_ID": "not-a-uuid"}]
        changes.extend({key: "unsafe"} for key in common.SAFETY_ENV)
        for change in changes:
            with self.subTest(change=change), self.assertRaises(common.Refused):
                common.validate_environment({**valid_environment(), **change})

    def test_child_environment_never_inherits_credentials(self):
        with patch.dict(os.environ, {"PATH": "/bin", "OPENAI_API_KEY": "fake",
                                     "DATABASE_URL": "fake", "PGHOST": "fake"}, clear=True):
            child = common.child_environment()
        self.assertFalse({"OPENAI_API_KEY", "DATABASE_URL", "PGHOST"} & child.keys())

    def test_url_password_is_encoded(self):
        with patch.object(common, "password", return_value="p@ss:/?#%+ "):
            url = common.database_url(common.IMPORTER)
        self.assertEqual(url, "postgresql+psycopg://demo_importer:p%40ss%3A%2F%3F%23%25%2B%20@db:5432/horoscope_demo")

    def test_fresh_cluster_accepts_only_empty_dedicated_target(self):
        connection = connection_with_rows(
            ("postgres", common.ADMIN, common.ADMIN),
            [("postgres",), ("template0",), ("template1",)],
            [(common.ADMIN,)], [("public",)], None,
        )
        bootstrap.verify_fresh_cluster(connection)
        self.assertTrue(all(call.args[0].startswith("SELECT") for call in connection.execute.call_args_list))

    def test_password_ddl_uses_only_client_scram_and_suppresses_statement_logs(self):
        roles = (common.OWNER, common.IMPORTER, common.READONLY)
        passwords = {role: f"raw-{role}-test-password-never-SQL" for role in roles}
        verifiers = [f"SCRAM-SHA-256$test-verifier-{role}" for role in roles]
        connection = Mock()
        connection.transaction.return_value = nullcontext()
        connection.pgconn.encrypt_password.side_effect = [v.encode() for v in verifiers]
        # SQL composition double exposes Literal inputs and rendered SQL without
        # requiring psycopg or a database. This tests the credential boundary.
        sql = Mock()
        sql.SQL.side_effect = lambda template: template
        sql.Identifier.side_effect = lambda value: value
        sql.Literal.side_effect = lambda value: repr(value)
        with patch.dict(sys.modules, {"psycopg": Mock(sql=sql)}):
            bootstrap.create_roles(connection, passwords)
        self.assertEqual(connection.pgconn.encrypt_password.call_args_list,
                         [call(passwords[role].encode(), role.encode(), b"scram-sha-256") for role in roles])
        self.assertEqual(sql.Literal.call_args_list, [call(value) for value in verifiers])
        statements = [item.args[0] for item in connection.execute.call_args_list]
        for secret in passwords.values():
            self.assertNotIn(secret, "\n".join(statements))
        first_ddl = next(i for i, value in enumerate(statements) if value.startswith("CREATE ROLE"))
        for setting in ("SET log_statement = 'none'", "SET log_min_error_statement = 'panic'",
                        "SET log_min_duration_statement = -1", "SET log_min_duration_sample = -1",
                        "SET log_transaction_sample_rate = 0"):
            self.assertIn(setting, statements[:first_ddl])

    def test_password_ddl_refuses_invalid_verifier_or_logging_configuration_failure(self):
        for failure in ("verifier", "logging"):
            connection = Mock()
            connection.transaction.return_value = nullcontext()
            connection.pgconn.encrypt_password.return_value = b"raw-password"
            if failure == "logging":
                connection.execute.side_effect = RuntimeError("logging setup failed")
            sql = Mock()
            with patch.dict(sys.modules, {"psycopg": Mock(sql=sql)}), \
                    self.subTest(failure=failure), self.assertRaises(RuntimeError):
                bootstrap.create_roles(connection, {common.OWNER: "raw-password"})
            sql.Literal.assert_not_called()

    def test_bootstrap_refuses_existing_database_roles_schema_and_objects(self):
        rows = [("postgres", common.ADMIN, common.ADMIN),
                [("postgres",), ("template0",), ("template1",)],
                [(common.ADMIN,)], [("public",)], None]
        failures = [(0, ("horoscope", common.ADMIN, common.ADMIN)),
                    (0, ("postgres", common.ADMIN, "other")),
                    (1, [("horoscope",), ("postgres",), ("template0",), ("template1",)]),
                    (2, [(common.ADMIN,), ("existing_owner",)]),
                    (3, [("demo_control",), ("public",)]), (4, (1,))]
        for index, value in failures:
            bad = rows.copy()
            bad[index] = value
            connection = connection_with_rows(*bad)
            with self.subTest(index=index), self.assertRaises(common.Refused):
                bootstrap.verify_fresh_cluster(connection)
            self.assertTrue(all(call.args[0].startswith("SELECT") for call in connection.execute.call_args_list))

    def test_marker_accepts_exact_identity(self):
        common.verify_marker(connection_with_rows(*marker_rows()), INSTANCE, common.OWNER)

    def test_marker_refuses_identity_ownership_privilege_membership_mismatch(self):
        failures = [(0, (common.DATABASE, common.OWNER, "other")),
                    (1, (True, False, False, False, False)), (2, (1,)),
                    (3, [(common.OWNER, common.IMPORTER, common.OWNER)]),
                    (4, []),
                    (4, [(1, "horoscope-demo", 1, UUID(int=2), common.DATABASE, common.IMPORTER)])]
        for index, value in failures:
            bad = marker_rows()
            bad[index] = value
            with self.subTest(index=index), self.assertRaises(common.Refused):
                common.verify_marker(connection_with_rows(*bad), INSTANCE, common.OWNER)

    def test_migration_refusal_never_starts_alembic_or_ddl(self):
        for mismatch in ("marker", "existing_public"):
            rows = marker_rows()
            if mismatch == "marker":
                rows[-1] = []
            connection = connection_with_rows(None, *rows, (1,))
            connection.transaction.return_value = nullcontext()
            with patch.dict(os.environ, valid_environment(), clear=True), \
                    patch.object(migrate, "connect", return_value=nullcontext(connection)), \
                    patch.object(migrate.subprocess, "run") as child, \
                    self.subTest(mismatch=mismatch), self.assertRaises(common.Refused):
                migrate.main()
            child.assert_not_called()
            statements = [call.args[0] for call in connection.execute.call_args_list]
            self.assertEqual(statements[0], "SET TRANSACTION READ ONLY")
            self.assertTrue(all(sql.startswith(("SELECT", "SET TRANSACTION READ ONLY")) for sql in statements))


class ComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def render(local=False, tools=False):
            command = ["docker", "compose", "--env-file", "/dev/null", "-f", "compose.demo.yml"]
            if local:
                command += ["-f", "compose.demo.local.yml"]
            if tools:
                command += ["--profile", "tools"]
            command += ["config", "--format", "json"]
            env = {"PATH": "/usr/bin:/bin", "DEMO_HOST": "demo.invalid",
                   "DEMO_EXPECTED_INSTANCE_ID": str(INSTANCE),
                   "DEMO_SECRETS_DIR": "/tmp/demo-static-placeholder", "DEMO_LOCAL_HTTPS_PORT": "9443"}
            return json.loads(subprocess.check_output(command, cwd=ROOT, env=env, text=True))
        cls.runtime = render()
        cls.local = render(local=True)
        cls.tools = render(tools=True)

    def test_only_three_runtime_services_and_only_proxy_ports(self):
        services = self.runtime["services"]
        self.assertEqual(set(services), {"proxy", "backend", "db"})
        self.assertEqual([name for name, service in services.items() if service.get("ports")], ["proxy"])
        for service in self.tools["services"].values():
            self.assertTrue(all(volume["type"] != "bind" for volume in service.get("volumes", [])))

    def test_only_caddyfile_is_mounted_as_config(self):
        self.assertEqual(set(self.tools["configs"]), {"demo_caddyfile"})
        for name, service in self.tools["services"].items():
            expected = ["demo_caddyfile"] if name == "proxy" else []
            self.assertEqual([config["source"] for config in service.get("configs", [])], expected)

    def test_backend_only_receives_readonly_secret_and_no_generation_authority(self):
        backend = self.runtime["services"]["backend"]
        self.assertEqual([s["source"] for s in backend["secrets"]], ["demo_readonly_password"])
        self.assertEqual(backend["environment"]["POSTGRES_USER"], common.READONLY)
        self.assertTrue(all(backend["environment"][key] == value for key, value in common.SAFETY_ENV.items()))
        self.assertFalse(any("API_KEY" in key for key in backend["environment"]))
        self.assertTrue(self.runtime["networks"]["data"]["internal"])
        self.assertTrue(self.runtime["networks"]["web"]["internal"])

    def test_tools_are_explicit_and_have_clean_environment(self):
        for name in ("demo-bootstrap", "demo-migrate", "demo-import"):
            tool = self.tools["services"][name]
            self.assertEqual(tool["profiles"], ["tools"])
            self.assertEqual(tool["command"], [])
            self.assertFalse(tool.get("ports"))
            self.assertEqual(common.validate_environment(tool["environment"]), INSTANCE)
        importer = self.tools["services"]["demo-import"]
        self.assertEqual([s["source"] for s in importer["secrets"]], ["demo_importer_password"])

    def test_tools_are_unprivileged_without_extra_capabilities_or_secrets(self):
        expected_secrets = {
            "demo-bootstrap": {"demo_admin_password", "demo_owner_password",
                               "demo_importer_password", "demo_readonly_password"},
            "demo-migrate": {"demo_owner_password"},
            "demo-import": {"demo_importer_password"},
        }
        for name, secrets in expected_secrets.items():
            with self.subTest(service=name):
                tool = self.tools["services"][name]
                self.assertEqual(tool["user"], "10001:10001")
                self.assertEqual(tool["cap_drop"], ["ALL"])
                self.assertFalse(tool.get("cap_add"))
                self.assertFalse(tool.get("privileged"))
                self.assertIn("no-new-privileges:true", tool["security_opt"])
                self.assertTrue(tool["read_only"])
                self.assertEqual({s["source"] for s in tool["secrets"]}, secrets)

    def test_local_override_replaces_ports_and_storage(self):
        services = self.local["services"]
        ports = services["proxy"]["ports"]
        self.assertEqual(len(ports), 1)
        self.assertEqual((ports[0]["host_ip"], ports[0]["published"], ports[0]["target"]),
                         ("127.0.0.1", "9443", 443))
        for name in ("proxy", "db"):
            self.assertTrue(all(v["type"] == "tmpfs" for v in services[name]["volumes"]))
        self.assertEqual(services["backend"]["environment"]["PUBLIC_SITE_URL"], "https://localhost:9443")


if __name__ == "__main__":
    unittest.main()

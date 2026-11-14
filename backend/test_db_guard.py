"""Fail-closed guards; importing this module never imports app or touches DBs."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
import sys
import uuid


class SafetyError(RuntimeError):
    pass


class NetworkViolation(BaseException):
    """Must escape provider/client broad Exception handlers and fail the test."""


DB_HOST = "test-db"
DB_PORT = 5432
DB_USER = "test_runner"
DB_PASSWORD = "dummy-test-db"
DUMMY_TOKENS = {"", "test-key", "test-api-key", "test-key-never-used",
                "dummy-test-token", "unit-test-fake-key"}
IDENTITY_SQL = (
    "SELECT current_database(), current_user, inet_server_port(), "
    "current_setting('horoscope.test_run_id', true)"
)


@dataclass(frozen=True)
class Identity:
    name: str
    run_id: str = ""

    @property
    def url(self):
        return database_url(self.name)


def database_url(name):
    return f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{name}"


def _require(condition, message):
    if not condition:
        raise SafetyError(message)


def validate_credentials(env):
    # Exact test literals only; never echo a rejected credential or URL.
    for key in ("OPENAI_API_KEY", "ADMIN_API_TOKEN"):
        _require(env.get(key, "") in DUMMY_TOKENS, f"Real credentials forbidden: {key}")


def _identity(env, *, runtime=False):
    name = env.get("TEST_DB_NAME", "horoscope_test")
    _require(isinstance(name, str) and len(name) <= 63 and
             re.fullmatch(r"horoscope_test(?:_[a-z0-9]+(?:_[a-z0-9]+)*)?", name),
             "TEST_DB_NAME must be in the disposable horoscope_test namespace")
    identity = Identity(name, env.get("TEST_DB_RUN_ID", ""))
    if runtime or name != "horoscope_test" or "TEST_DB_IDENTITY" in env:
        _require(env.get("TEST_DB_IDENTITY") == identity.url,
                 "TEST_DB_IDENTITY must explicitly match the disposable target URL")
    if runtime:
        _require(re.fullmatch(r"[a-f0-9]{32}", identity.run_id), "Missing or invalid TEST_DB_RUN_ID")
    return identity


def validate_selectors(selectors):
    backend = Path(__file__).resolve().parent
    for selector in selectors:
        _require(re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py(?:::[A-Za-z0-9_]+)*", selector),
                 "Only positive tests/test_file.py[::Class::test_name] selectors are accepted")
        path = backend / selector.split("::", 1)[0]
        _require(path.is_file() and not path.is_symlink(), "Test selector must name an existing regular file")


def validate_host(env, selectors):
    for key in env:
        if (key.startswith(("POSTGRES_", "PG", "COMPOSE_", "DOCKER_", "PYTEST_")) or
                key in {"DATABASE_URL", "ALLOW_PYTEST_ON_DEV_DB", "KEEP_TEST_DB", "TEST_DB_RUN_ID"}):
            raise SafetyError(f"Inherited override forbidden: {key}; use a clean shell")
        if key.startswith("TEST_") and key not in {"TEST_DB_NAME", "TEST_DB_IDENTITY"}:
            raise SafetyError(f"Unknown test harness override: {key}")
    _require(env.get("APP_DEPLOYMENT_MODE", "test") == "test", "Host deployment mode must be absent or test")
    _require(env.get("HOROSCOPE_PROVIDER", "stub") == "stub", "Host provider must be absent or stub")
    validate_credentials(env)
    validate_selectors(selectors)
    return _identity(env)


def validate_runtime(env):
    identity = _identity(env, runtime=True)
    expected = {
        "TEST_DB_NAME": identity.name,
        "DATABASE_URL": identity.url,
        "POSTGRES_HOST": DB_HOST, "POSTGRES_PORT": str(DB_PORT),
        "POSTGRES_DB": identity.name, "POSTGRES_USER": DB_USER,
        "POSTGRES_PASSWORD": DB_PASSWORD,
        "APP_DEPLOYMENT_MODE": "test", "HOROSCOPE_PROVIDER": "stub",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    for key, value in expected.items():
        _require(env.get(key) == value, f"Missing or conflicting test configuration: {key}")
    for key in env:
        if (key.startswith(("PG", "COMPOSE_", "DOCKER_")) or
                (key.startswith("POSTGRES_") and key not in expected) or
                # Pytest itself adds these informational variables after startup.
                (key.startswith("PYTEST_") and key not in {
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_CURRENT_TEST", "PYTEST_VERSION"
                }) or
                key in {"ALLOW_PYTEST_ON_DEV_DB", "KEEP_TEST_DB"}):
            raise SafetyError(f"Runtime override forbidden: {key}")
    validate_credentials(env)
    return identity


def assert_url(url, identity):
    if isinstance(url, str):
        _require(url == identity.url, "Resolved database URL does not match the disposable identity")
        return
    expected = {"drivername": "postgresql+psycopg", "host": DB_HOST, "port": DB_PORT,
                "database": identity.name, "username": DB_USER, "password": DB_PASSWORD,
                "query": {}}
    _require(all(getattr(url, key, None) == value for key, value in expected.items()),
             "Resolved SQLAlchemy target does not match the disposable identity")


def assert_connection(connection, identity):
    assert_url(connection.engine.url, identity)
    actual = connection.exec_driver_sql(IDENTITY_SQL).one()
    _require(actual is not None and tuple(actual) == (identity.name, DB_USER, DB_PORT, identity.run_id),
             "Connected database identity mismatch; refusing database mutation")


class NetworkPolicy:
    """Socket audit policy; internal Docker networking also contains C/libpq.

    MockTransport/fake clients do not use sockets and remain usable.
    Child processes cannot escape the Python socket guard.
    """
    def __init__(self, db_hosts):
        self.db_hosts = set(db_hosts)
        self.violations = []

    def deny(self, message):
        # Latch first: even an explicit BaseException handler cannot turn an
        # attempted network/credential violation into a passing suite.
        self.violations.append(message)
        raise NetworkViolation(message)

    def __call__(self, event, args):
        if event == "os.putenv":
            key, value = args
            key = os.fsdecode(key)
            if key in {"OPENAI_API_KEY", "ADMIN_API_TOKEN"}:
                try:
                    validate_credentials({key: os.fsdecode(value)})
                except SafetyError:
                    self.deny("Non-dummy credentials attempted during backend tests")
        elif event in {"socket.connect", "socket.getaddrinfo"}:
            address = args[1] if event == "socket.connect" else args[:2]
            if not (isinstance(address, tuple) and len(address) >= 2 and
                    address[0] in self.db_hosts and address[1] in {DB_PORT, str(DB_PORT)}):
                self.deny("Unexpected network access in backend tests")
        elif event.startswith("socket.") and event not in {"socket.__new__", "socket.gethostname"}:
            self.deny("Unexpected socket operation in backend tests")
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
            self.deny("Child processes are forbidden in backend tests")


_runtime_identity = None
_network_policy = None


def prepare_runtime():
    global _runtime_identity, _network_policy
    identity = validate_runtime(os.environ)
    if _runtime_identity is not None:
        _require(_runtime_identity == identity, "Test runtime identity changed")
        return identity

    # Before app/config.py can load any dotenv file.
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    policy = NetworkPolicy({DB_HOST})
    _network_policy = policy
    sys.addaudithook(policy)
    addresses = socket.getaddrinfo(DB_HOST, DB_PORT, type=socket.SOCK_STREAM)
    policy.db_hosts.update(item[4][0] for item in addresses)

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def verify_new_connection(connection):
        assert_connection(connection, identity)
        # End only our read-only identity query, before caller starts its work.
        connection.rollback()

    event.listen(Engine, "engine_connect", verify_new_connection)
    _runtime_identity = identity
    return identity


def run_suite(selectors):
    validate_selectors(selectors)
    identity = prepare_runtime()
    from app.config import Config
    from sqlalchemy.engine import make_url
    assert_url(make_url(Config.SQLALCHEMY_DATABASE_URI), identity)
    # Alembic's connection is checked by the listener before its first DDL.
    from alembic import command
    from alembic.config import Config as AlembicConfig
    command.upgrade(AlembicConfig("alembic.ini"), "head")
    import pytest
    return suite_exit_code(pytest.main(["-q", "-p", "no:cacheprovider", *(selectors or ["tests"])]))


def suite_exit_code(pytest_code):
    if _network_policy is not None and _network_policy.violations:
        print("Test safety guard: forbidden network/process/credential activity attempted", file=sys.stderr)
        return 1
    return int(pytest_code)


def main():
    mode, *selectors = sys.argv[1:]
    try:
        if mode == "host":
            identity = validate_host(os.environ, selectors)
            print(identity.name)
            print(identity.url)
            print(uuid.uuid4().hex)
            return 0
        if mode == "run":
            return run_suite(selectors)
        raise SafetyError("Unknown test guard command")
    except SafetyError as exc:
        print(f"Test safety guard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    # The conftest import must reuse our already installed process-wide guards.
    sys.modules["test_db_guard"] = sys.modules[__name__]
    raise SystemExit(main())

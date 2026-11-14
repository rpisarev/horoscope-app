"""Run only through the orchestrator-owned disposable backend harness."""

from pathlib import Path
from unittest.mock import MagicMock, Mock

from alembic import command
from alembic.script import ScriptDirectory
from flask import Flask
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, ProgrammingError, TimeoutError
from sqlalchemy.pool import NullPool

from app import db, providers, services
from app.health_routes import health_bp
from app.models import Forecast
from app.services import forecast_service, generation_job_service, generation_service
from app.services import readiness_service
import test_db_guard


def test_application_factory_registers_readiness_without_changing_signs(client, monkeypatch):
    assert_response(client.get("/health/ready"), True)
    monkeypatch.setattr(
        readiness_service, "create_engine",
        Mock(side_effect=OperationalError("connect", {}, Exception("DB unavailable"))),
    )
    assert_response(client.get("/health/ready"), False)
    response = client.get("/api/signs")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)
    assert "aries" in response.get_json()


@pytest.fixture
def readiness_client(app):
    # This owns registration until the parent integrates health_bp in create_app.
    # It remains usable after that integration and never mutates the shared app.
    probe_app = Flask(__name__)
    probe_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=app.config["SQLALCHEMY_DATABASE_URI"],
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(probe_app)
    probe_app.register_blueprint(health_bp)
    return probe_app.test_client()


@pytest.fixture
def fake_probe(monkeypatch):
    heads = frozenset({"expected-head-a", "expected-head-b"})
    monkeypatch.setattr(readiness_service, "expected_schema_heads", lambda: heads)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value.all.return_value = list(heads)
    builder = Mock(return_value=engine)
    monkeypatch.setattr(readiness_service, "create_engine", builder)
    return engine, connection, builder


def assert_response(response, is_ready):
    assert response.status_code == (200 if is_ready else 503)
    assert response.get_json() == {"ready": is_ready}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.mimetype == "application/json"


def test_ready_with_exact_script_heads(readiness_client, fake_probe):
    engine, connection, builder = fake_probe
    assert_response(readiness_client.get("/health/ready"), True)
    builder.assert_called_once()
    statement, parameters = connection.execute.call_args.args
    assert str(statement) == "SELECT version_num FROM alembic_version LIMIT :limit"
    assert parameters == {"limit": 3}
    connection.execute.assert_called_once()
    connection.commit.assert_not_called()
    engine.connect.return_value.__exit__.assert_called_once()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("revisions", [
    [], ["expected-head-a"], ["old-revision"], ["future-revision"],
    ["expected-head-a", "unexpected-head"],
    ["expected-head-a", "expected-head-b", "unexpected-head"],
    ["expected-head-a", "expected-head-a"], [None],
])
def test_missing_wrong_extra_or_duplicate_revisions(
    readiness_client, fake_probe, revisions
):
    engine, connection, _ = fake_probe
    connection.execute.return_value.scalars.return_value.all.return_value = revisions
    assert_response(readiness_client.get("/health/ready"), False)
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("failure_stage,error", [
    ("connect", OperationalError("connect", {}, Exception("database unavailable"))),
    ("connect", TimeoutError("connection timeout")),
    ("execute", ProgrammingError("query", {}, Exception("missing alembic_version"))),
    ("execute", OperationalError("query", {}, Exception("statement timeout"))),
    ("fetch", OperationalError("fetch", {}, Exception("connection dropped"))),
    ("close", OperationalError("rollback", {}, Exception("connection dropped"))),
    ("dispose", RuntimeError("dispose failed")),
])
def test_database_down_query_timeout_and_cleanup_fail_closed(
    readiness_client, fake_probe, failure_stage, error
):
    engine, connection, _ = fake_probe
    failing_call = {
        "connect": engine.connect,
        "execute": connection.execute,
        "fetch": connection.execute.return_value.scalars.return_value.all,
        "close": engine.connect.return_value.__exit__,
        "dispose": engine.dispose,
    }[failure_stage]
    failing_call.side_effect = error
    assert_response(readiness_client.get("/health/ready"), False)
    engine.dispose.assert_called_once()
    if failure_stage != "connect":
        engine.connect.return_value.__exit__.assert_called_once()


def test_response_and_logs_redact_connection_sql_and_revision_details(
    readiness_client, fake_probe, caplog
):
    _, connection, _ = fake_probe
    secret = "postgresql://private-user:private-password@private-host/private-db"
    connection.execute.side_effect = OperationalError(
        "SELECT private_revision FROM private_schema.alembic_version",
        {"secret": secret}, Exception(secret),
    )
    response = readiness_client.get("/health/ready")
    assert_response(response, False)
    for fragment in (
        secret, "private-user", "private-password", "private-host", "private-db",
        "private_revision", "private_schema", "expected-head-a", "SELECT",
    ):
        assert fragment not in response.get_data(as_text=True)
        assert fragment not in caplog.text


def test_probe_does_not_cache_success_or_failure(readiness_client, fake_probe):
    engine, connection, _ = fake_probe
    results = connection.execute.return_value.scalars.return_value.all
    results.side_effect = [
        ["expected-head-a", "expected-head-b"], [],
        ["expected-head-b", "expected-head-a"],
    ]
    for expected in (True, False, True):
        assert_response(readiness_client.get("/health/ready"), expected)
    assert engine.dispose.call_count == 3


def test_limits_are_connection_arguments_without_changing_guarded_url(app, fake_probe):
    _, _, builder = fake_probe
    url = db.engine.url
    assert readiness_service.database_ready(url) is True
    args, kwargs = builder.call_args
    assert args == (url,)
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"] == {
        "connect_timeout": 2,
        "options": (
            "-c default_transaction_read_only=on"
            " -c statement_timeout=1000 -c lock_timeout=1000"
        ),
    }
    assert kwargs["hide_parameters"] is True
    assert kwargs["echo"] is False
    test_db_guard.assert_url(args[0], test_db_guard.prepare_runtime())


def test_url_options_cannot_remove_probe_limits(app, fake_probe):
    _, _, builder = fake_probe
    # Mock engine only: harness forbids real connections with URL query options.
    url = db.engine.url.update_query_dict({
        "options": "-c search_path=public -c statement_timeout=0 -c default_transaction_read_only=off",
        "connect_timeout": "0", "sslmode": "require",
    })
    assert readiness_service.database_ready(url) is True
    assert builder.call_args.args == (url,)
    assert builder.call_args.kwargs["connect_args"]["connect_timeout"] == 2
    options = builder.call_args.kwargs["connect_args"]["options"]
    assert options.startswith(url.query["options"])
    assert options.endswith(
        "-c default_transaction_read_only=on -c statement_timeout=1000 -c lock_timeout=1000"
    )


@pytest.mark.parametrize("url", [
    "sqlite:///:memory:", "postgresql+psycopg2://unused/unused", "not a URL", None,
])
def test_invalid_or_unsupported_database_configuration_fails_closed(fake_probe, url):
    _, _, builder = fake_probe
    assert readiness_service.database_ready(url) is False
    builder.assert_not_called()


@pytest.mark.parametrize("heads,error", [
    (frozenset(), None), (None, OSError("unreadable private migration path")),
])
def test_missing_expected_heads_never_connects(fake_probe, monkeypatch, app, heads, error):
    _, _, builder = fake_probe
    monkeypatch.setattr(
        readiness_service, "expected_schema_heads", Mock(return_value=heads, side_effect=error)
    )
    assert readiness_service.database_ready(db.engine.url) is False
    builder.assert_not_called()


def test_script_heads_are_source_relative_without_running_migrations(monkeypatch, tmp_path):
    forbidden = Mock(side_effect=AssertionError("Readiness cannot execute migrations"))
    monkeypatch.setattr(ScriptDirectory, "run_env", forbidden)
    monkeypatch.setattr(command, "upgrade", forbidden)
    monkeypatch.setattr(command, "stamp", forbidden)
    monkeypatch.chdir(tmp_path)
    expected_path = Path(__file__).resolve().parents[1] / "migrations"
    expected = frozenset(ScriptDirectory(str(expected_path)).get_heads())
    assert expected
    assert readiness_service.expected_schema_heads() == expected
    forbidden.assert_not_called()


def test_guard_network_violations_are_not_swallowed(readiness_client, fake_probe):
    engine, _, _ = fake_probe
    # Synthetic exception, not an actual network attempt (which latches suite failure).
    engine.connect.side_effect = test_db_guard.NetworkViolation("synthetic guard failure")
    with pytest.raises(test_db_guard.NetworkViolation):
        readiness_client.get("/health/ready")
    engine.dispose.assert_called_once()


def test_real_schema_readonly_settings_and_identity_guard(
    readiness_client, monkeypatch
):
    create_engine = readiness_service.create_engine
    assert_connection = test_db_guard.assert_connection
    events = []
    connections = []
    settings = []

    def checked_identity(connection, identity):
        assert_connection(connection, identity)
        events.append("identity")

    def instrumented_engine(*args, **kwargs):
        engine = create_engine(*args, **kwargs)
        assert isinstance(engine.pool, NullPool)

        @event.listens_for(engine, "engine_connect")
        def inspect_settings(connection):
            connections.append(connection)
            settings.append(connection.execute(text(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('statement_timeout'), current_setting('lock_timeout')"
            )).one())
            connection.rollback()

        @event.listens_for(engine, "before_cursor_execute")
        def inspect_query(connection, cursor, statement, parameters, context, executemany):
            if "FROM alembic_version" in statement:
                events.append("revision")

        return engine

    monkeypatch.setattr(test_db_guard, "assert_connection", checked_identity)
    monkeypatch.setattr(readiness_service, "create_engine", instrumented_engine)
    assert_response(readiness_client.get("/health/ready"), True)
    assert events == ["identity", "revision"]
    assert [tuple(row) for row in settings] == [("on", "1s", "1s")]
    assert len(connections) == 1
    assert connections[0].closed


def test_identity_guard_failure_prevents_revision_query(readiness_client, monkeypatch):
    create_engine = readiness_service.create_engine
    original_assertion = test_db_guard.assert_connection
    revision_queries = []

    def reject_probe_identity(connection, identity):
        original_assertion(connection, identity)
        # Keep teardown's normal application-engine checks intact.
        if isinstance(connection.engine.pool, NullPool):
            raise test_db_guard.SafetyError("synthetic identity mismatch")

    def instrumented_engine(*args, **kwargs):
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "before_cursor_execute")
        def inspect_query(connection, cursor, statement, parameters, context, executemany):
            if "FROM alembic_version" in statement:
                revision_queries.append(statement)

        return engine

    monkeypatch.setattr(test_db_guard, "assert_connection", reject_probe_identity)
    monkeypatch.setattr(readiness_service, "create_engine", instrumented_engine)
    assert_response(readiness_client.get("/health/ready"), False)
    assert revision_queries == []


def test_postgresql_statement_timeout_is_effective(readiness_client, monkeypatch):
    create_engine = readiness_service.create_engine
    errors = []

    def slow_probe_engine(*args, **kwargs):
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "before_cursor_execute", retval=True)
        def slow_revision_query(connection, cursor, statement, parameters, context, executemany):
            if "FROM alembic_version" in statement:
                return "SELECT pg_sleep(5)", ()
            return statement, parameters

        @event.listens_for(engine, "handle_error")
        def capture_error(context):
            errors.append(context.original_exception)

        return engine

    monkeypatch.setattr(readiness_service, "create_engine", slow_probe_engine)
    assert_response(readiness_client.get("/health/ready"), False)
    # Proves PostgreSQL cancelled the statement, not merely a mismatched result.
    assert len(errors) == 1
    assert errors[0].sqlstate == "57014"


def test_readiness_preserves_pending_session_and_never_calls_providers(app, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Readiness must only inspect the database"))
    for module, names in [
        (providers, ["get_horoscope_provider"]),
        (services, ["generate_horoscope", "save_forecast", "run_daily_generation"]),
        (forecast_service, ["generate_horoscope", "save_forecast", "get_horoscope_provider"]),
        (generation_service, ["run_daily_generation", "get_horoscope_provider"]),
        (generation_job_service, ["create_generation_job", "process_generation_jobs"]),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, forbidden)

    # Intentionally invalid pending row: any accidental autoflush would fail.
    pending = Forecast(text="uncommitted readiness sentinel")
    db.session.add(pending)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(db.session, "flush", forbidden)
            patch.setattr(db.session, "commit", forbidden)
            patch.setattr(db.session, "rollback", forbidden)
            patch.setattr(db.engine, "connect", forbidden)
            assert readiness_service.database_ready(db.engine.url) is True
            assert pending in db.session.new
            assert pending.id is None
        forbidden.assert_not_called()
    finally:
        db.session.rollback()

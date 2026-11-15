"""Shared fail-closed checks for explicit demo setup tools, never app startup."""

import os
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

DATABASE = "horoscope_demo"
OWNER = "demo_owner"
IMPORTER = "demo_importer"
READONLY = "demo_readonly"
ADMIN = "demo_bootstrap"
SAFETY_ENV = {
    "PYTHON_DOTENV_DISABLED": "1",
    "APP_DEPLOYMENT_MODE": "production",
    "APP_TIMEZONE": "Europe/Kyiv",
    "PRODUCTION_PUBLICATION_PROVIDERS": "",
    "HOROSCOPE_PROVIDER": "stub",
    "GENERATION_PAID_EXECUTION_ENABLED": "0",
    "ADMIN_API_ENABLED": "0",
    "ADMIN_API_ALLOW_OPENAI": "0",
    "RUN_NIGHTLY_ON_START": "0",
    "GENERATION_SCHEDULER_USE_QUEUE": "0",
    "GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI": "0",
    "GENERATION_JOB_WORKER_ENABLED": "0",
    "GENERATION_JOB_WORKER_ALLOW_OPENAI": "0",
}


class Refused(RuntimeError):
    """Messages are fixed descriptions, never credentials or driver errors."""


def require(condition, message):
    if not condition:
        raise Refused(message)


def validate_environment(environ=None):
    env = os.environ if environ is None else environ
    require(
        not any(key == "DATABASE_URL" or key.startswith(("POSTGRES", "PG")) for key in env),
        "Generic database configuration is forbidden in demo tools.",
    )
    require(all(env.get(key) == value for key, value in SAFETY_ENV.items()),
            "Explicit demo safety environment is required.")
    require(env.get("DEMO_EXPECTED_DATABASE") == DATABASE, "Unexpected demo database.")
    try:
        instance = UUID(env.get("DEMO_EXPECTED_INSTANCE_ID", ""))
    except (ValueError, TypeError, AttributeError):
        raise Refused("A valid demo instance UUID is required.") from None
    require(instance.int != 0, "The demo instance UUID must be nonzero.")
    return instance


def password(role):
    names = {ADMIN: "admin", OWNER: "owner", IMPORTER: "importer", READONLY: "readonly"}
    value = Path(f"/run/secrets/demo_{names[role]}_password").read_text().strip()
    require(len(value) >= 24 and "\x00" not in value, "Invalid demo password file.")
    return value


def database_url(role):
    return f"postgresql+psycopg://{role}:{quote(password(role), safe='')}@db:5432/{DATABASE}"


def connect(role, database=DATABASE):
    import psycopg

    return psycopg.connect(
        host="db", port=5432, dbname=database, user=role, password=password(role),
        connect_timeout=5, autocommit=True,
        options="-c statement_timeout=10000 -c lock_timeout=3000",
    )


def verify_session(connection, database, role):
    actual = connection.execute(
        "SELECT current_database(), current_user, session_user"
    ).fetchone()
    require(actual == (database, role, role), "Database/session identity mismatch.")


def verify_marker(connection, instance, role):
    """Caller starts a READ ONLY transaction before invoking this preflight."""
    verify_session(connection, DATABASE, role)
    flags = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    require(flags == (False, False, False, False, False), "Elevated demo role refused.")
    memberships = connection.execute(
        "SELECT 1 FROM pg_auth_members WHERE member = "
        "(SELECT oid FROM pg_roles WHERE rolname = current_user) LIMIT 1"
    ).fetchone()
    require(memberships is None, "Demo role membership refused.")
    owners = connection.execute(
        "SELECT pg_get_userbyid(d.datdba), pg_get_userbyid(n.nspowner), "
        "pg_get_userbyid(c.relowner) FROM pg_database d "
        "JOIN pg_namespace n ON n.nspname = 'demo_control' "
        "JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = 'identity' "
        "AND c.relkind = 'r' WHERE d.datname = current_database()"
    ).fetchall()
    require(owners == [(OWNER, OWNER, OWNER)], "Demo marker ownership mismatch.")
    rows = connection.execute(
        "SELECT id, purpose, contract_version, instance_id, database_name, importer_role "
        "FROM demo_control.identity"
    ).fetchall()
    require(rows == [(1, "horoscope-demo", 1, instance, DATABASE, IMPORTER)],
            "Demo marker mismatch.")


def require_empty_public(connection):
    objects = connection.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' UNION ALL "
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' LIMIT 1"
    ).fetchone()
    require(objects is None, "Existing public objects refused; setup is initial-only.")


def child_environment():
    # No inherited URLs, PG settings, dotenv files or provider credentials.
    env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
    return {**env, **SAFETY_ENV, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def run_safely(main):
    try:
        main()
    except Refused as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("Demo tool failed; credentials and driver details suppressed.") from None

"""Read-only PostgreSQL/schema readiness, independent of the application pool."""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool


CONNECT_TIMEOUT_SECONDS = 2
STATEMENT_TIMEOUT_MS = 1000
LOCK_TIMEOUT_MS = 1000
MIGRATIONS_PATH = Path(__file__).resolve().parents[2] / "migrations"


def expected_schema_heads() -> frozenset[str]:
    """Read packaged revision metadata; never run env.py or migration functions."""
    return frozenset(ScriptDirectory(str(MIGRATIONS_PATH)).get_heads())


def _probe_engine(database_url: str | URL):
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Readiness requires PostgreSQL with psycopg")

    # Preserve routing/search_path/SSL options and the exact engine URL. In the
    # disposable harness its Engine.engine_connect listener validates that URL
    # and the actual server identity before our query. Timeout/read-only options
    # go in connect_args, not URL query parameters, so that guard stays effective.
    options = url.query.get("options", "")
    if not isinstance(options, str):
        raise ValueError("Invalid PostgreSQL startup options")
    options = (
        f"{options} -c default_transaction_read_only=on"
        f" -c statement_timeout={STATEMENT_TIMEOUT_MS}"
        f" -c lock_timeout={LOCK_TIMEOUT_MS}"
    ).strip()

    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": options,
        },
        hide_parameters=True,
        echo=False,
    )


def database_ready(database_url: str | URL) -> bool:
    """Return only readiness; connection/configuration/schema errors fail closed.

    NullPool removes application-pool acquisition waits. libpq connect_timeout
    and startup statement_timeout cover connection attempts and every statement,
    including dialect initialization and test identity checks. They are not a
    whole-process/DNS/network wall-clock deadline; see database-readiness.md.
    """
    engine = None
    ready = False
    try:
        expected = expected_schema_heads()
        if not expected:
            return False

        engine = _probe_engine(database_url)
        with engine.connect() as connection:
            # The successful SELECT itself proves connectivity. Limit the result
            # to detect unexpected extra heads without reading an unbounded table.
            actual = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT :limit"),
                {"limit": len(expected) + 1},
            ).scalars().all()
            ready = len(actual) == len(expected) and frozenset(actual) == expected
        # Connection context exit rolls back the read-only transaction; no ORM
        # session/flush/commit, application data, migrations or providers involved.
    except Exception:
        # Do not log SQL exceptions/DSNs or expose revision details to callers.
        # BaseException-derived STAB-007 network violations must still escape.
        ready = False
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                ready = False
    return ready

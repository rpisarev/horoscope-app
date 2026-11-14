"""Shared, published-only reads for explicit operational reports.

These reports never borrow the application's ORM session: pending caller writes
must not be flushed, committed, or rolled back by an inspection. Existing public
and generation helpers retain their contracts, including legacy empty-sign rules.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

from sqlalchemy import Connection, create_engine, select
from sqlalchemy.pool import NullPool

from .. import db
from ..models import Forecast, ZodiacSign


MAX_REPORT_SIGNS = 1000
CONNECT_TIMEOUT_SECONDS = 2
STATEMENT_TIMEOUT_MS = 2000


@contextmanager
def read_snapshot() -> Iterator[Connection]:
    """Yield a separate PostgreSQL read-only snapshot, then always roll it back.

    NullPool avoids waiting on the application pool. Connection/statement timeouts
    bound database waits; reports use a fixed number of queries and bounded results.
    This does not provide a whole-process deadline for DNS or OS/network failures.
    """
    url = db.engine.url
    if url.drivername != "postgresql+psycopg":
        raise RuntimeError("Operational reports require PostgreSQL with psycopg.")
    options = url.query.get("options", "")
    if not isinstance(options, str):
        raise RuntimeError("Invalid PostgreSQL report connection options.")

    engine = create_engine(
        url,
        poolclass=NullPool,
        isolation_level="REPEATABLE READ",
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": (
                f"{options} -c default_transaction_read_only=on "
                f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c lock_timeout=1000"
            ).strip(),
        },
        hide_parameters=True,
        echo=False,
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def enabled_sign_keys(connection: Connection) -> list[str]:
    """Return actual enabled metadata, including an explicitly empty set."""
    keys = list(connection.execute(
        select(ZodiacSign.key)
        .where(ZodiacSign.is_enabled.is_(True))
        .order_by(ZodiacSign.sort_order, ZodiacSign.key)
        .limit(MAX_REPORT_SIGNS + 1)
    ).scalars())
    if len(keys) > MAX_REPORT_SIGNS:
        raise RuntimeError("Enabled-sign metadata exceeds the report limit.")
    return keys


def published_coverage(
    connection: Connection,
    *,
    target_date: date,
    locale: str,
    forecast_type: str,
    signs: Sequence[str] | None = None,
) -> dict:
    """Read exact-scope published coverage without content or provider metadata.

    Explicit signs represent the requested job scope, even if metadata has since
    disabled those signs. None represents the currently enabled metadata. Neither an
    empty set nor a job/run success is evidence of complete operational coverage.
    """
    if signs is None:
        expected = enabled_sign_keys(connection)
    else:
        if not isinstance(signs, Sequence) or isinstance(signs, (str, bytes, bytearray)):
            raise ValueError("Requested signs must be a sequence of sign keys.")
        expected = []
        seen = set()
        for index, sign in enumerate(signs):
            if index >= MAX_REPORT_SIGNS:
                raise RuntimeError("Requested scope exceeds the report limit.")
            if not isinstance(sign, str) or not sign or len(sign) > 32:
                raise ValueError("Invalid requested sign scope.")
            if sign not in seen:
                seen.add(sign)
                expected.append(sign)

    published_set = set()
    if expected:
        published_set = set(connection.execute(
            select(Forecast.sign_key).where(
                Forecast.sign_key.in_(expected),
                Forecast.target_date == target_date,
                Forecast.locale == locale,
                Forecast.forecast_type == forecast_type,
                Forecast.status == "published",
            ).limit(MAX_REPORT_SIGNS)
        ).scalars())
    published = [sign for sign in expected if sign in published_set]
    missing = [sign for sign in expected if sign not in published_set]
    if not expected:
        state = "empty_enabled_signs" if signs is None else "empty_scope"
    elif not missing:
        state = "full"
    elif published:
        state = "partial"
    else:
        state = "none"

    return {
        "date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "scope_source": "enabled_metadata" if signs is None else "explicit_signs",
        "expected_signs": expected,
        "published_signs": published,
        "missing_signs": missing,
        "expected_count": len(expected),
        "published_count": len(published),
        "missing_count": len(missing),
        "coverage_state": state,
    }

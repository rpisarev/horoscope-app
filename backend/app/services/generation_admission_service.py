"""Short PostgreSQL admission boundary; no provider calls or transaction commits.

Lifecycle integration must commit its execution/run/link before processing items.
The unique index is the active-package invariant; the transaction advisory lock
serializes cooperating callers' retry-cap decisions. Neither is lease fencing.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Iterator

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import GenerationRun


ACTIVE_PACKAGE_CONSTRAINT = "uq_generation_runs_active_package"
ADMISSION_LOCK_TIMEOUT_MS = 1000
ADMISSION_STATEMENT_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class GenerationPackageScope:
    target_date: date
    locale: str
    forecast_type: str

    def __post_init__(self) -> None:
        # Do not create aliases or change the stored case/whitespace semantics.
        if type(self.target_date) is not date:
            raise ValueError("Generation package target_date must be a date.")
        if not isinstance(self.locale, str) or not self.locale.strip():
            raise ValueError("Generation package locale must not be empty.")
        if not isinstance(self.forecast_type, str) or not self.forecast_type.strip():
            raise ValueError("Generation package forecast_type must not be empty.")

    def lock_key(self) -> int:
        encoded = json.dumps(
            ["generation-package-admission-v1", self.target_date.isoformat(),
             self.locale, self.forecast_type],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big", signed=True)


class GenerationScopeBusy(RuntimeError):
    """No execution was admitted; this is not a retryable provider failure."""

    code = "generation_scope_busy"
    retryable = False

    def __init__(self, scope: GenerationPackageScope):
        self.scope = scope
        # Do not expose raw DB exceptions, returned provider data or foreign runs.
        super().__init__("Generation package is already active or being admitted.")


class GenerationAdmissionConfigurationError(RuntimeError):
    retryable = False


def _is_active_package_conflict(exc: IntegrityError) -> bool:
    original = exc.orig
    return (
        getattr(original, "sqlstate", None) == "23505"
        and getattr(getattr(original, "diag", None), "constraint_name", None)
        == ACTIVE_PACKAGE_CONSTRAINT
    )


@contextmanager
def package_scope_lock(
    session: Session, *, scope: GenerationPackageScope,
) -> Iterator[None]:
    """Serialize package decisions in one bounded READ COMMITTED transaction.

    The caller must have an active short transaction and commit after this block,
    before provider execution. This helper commits/rolls back only its savepoint,
    never the caller's transaction. Already-flushed outer writes remain owned by
    the caller. Unflushed state is rejected before begin_nested's implicit flush.
    An already-active SQLAlchemy autobegin transaction is caller-owned too; this
    helper will not create one. DBAPI autocommit is independently forbidden even
    if get_isolation_level() reports READ COMMITTED. Admission is not authority
    to execute transport before the caller's actual durable transaction commit.

    This lock alone does NOT admit a run: use package_admission for run creation.
    It also lets a losing worker decide busy disposition atomically with another
    caller's run-link commit. The index remains the active-package backstop.
    SQL timeouts and unrelated errors propagate; only that named 23505 is busy.
    """
    transaction = session.get_transaction()
    if transaction is None or not transaction.is_active:
        raise GenerationAdmissionConfigurationError(
            "Package admission requires an active caller-owned transaction."
        )
    if session.new or session.dirty or session.deleted:
        raise GenerationAdmissionConfigurationError(
            "Package admission requires an explicitly flushed owned transaction."
        )

    connection = session.connection()
    if connection.dialect.name != "postgresql":
        raise GenerationAdmissionConfigurationError("Package admission requires PostgreSQL.")
    raw_connection = connection.connection.driver_connection
    if getattr(raw_connection, "autocommit", None) is not False:
        raise GenerationAdmissionConfigurationError(
            "Package admission requires DBAPI autocommit to be disabled."
        )
    if connection.get_isolation_level().upper() != "READ COMMITTED":
        raise GenerationAdmissionConfigurationError(
            "Package admission requires PostgreSQL READ COMMITTED isolation."
        )

    try:
        with session.begin_nested():
            # Session savepoints are lazy. Obtain the connection again inside
            # the nested transaction so SAVEPOINT precedes SET LOCAL and lock
            # acquisition. Reusing the outer Connection would change caller
            # settings before the savepoint and leak them on a busy rollback.
            connection = session.connection()
            previous = connection.execute(text(
                "SELECT name, setting::bigint, current_setting(name) FROM pg_settings "
                "WHERE name IN ('lock_timeout', 'statement_timeout')"
            )).all()
            limits = {
                "lock_timeout": ADMISSION_LOCK_TIMEOUT_MS,
                "statement_timeout": ADMISSION_STATEMENT_TIMEOUT_MS,
            }
            for name, current_ms, _ in previous:
                # pg_settings stores both settings in ms. Zero is unlimited;
                # preserve a caller's stricter bound rather than relaxing it.
                timeout_ms = min(current_ms, limits[name]) if current_ms else limits[name]
                connection.execute(text("SELECT set_config(:name, :value, true)"),
                                   {"name": name, "value": f"{timeout_ms}ms"})
            locked = connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"),
                                       {"key": scope.lock_key()})
            if not locked:
                raise GenerationScopeBusy(scope)

            yield
            # Flush before leaving the savepoint, so named unique violations are
            # normalized here rather than escaping from an outer commit.
            session.flush()
            for name, _, value in previous:
                connection.execute(text("SELECT set_config(:name, :value, true)"),
                                   {"name": name, "value": value})
    except IntegrityError as exc:
        if _is_active_package_conflict(exc):
            raise GenerationScopeBusy(scope) from exc
        raise


@contextmanager
def package_admission(
    session: Session, *, scope: GenerationPackageScope,
) -> Iterator[None]:
    """Require an empty active package before caller-owned run/link insertion."""
    with package_scope_lock(session, scope=scope):
        active = session.connection().scalar(select(GenerationRun.id).where(
            GenerationRun.target_date == scope.target_date,
            GenerationRun.locale == scope.locale,
            GenerationRun.forecast_type == scope.forecast_type,
            GenerationRun.status == "running",
        ).limit(1))
        if active is not None:
            raise GenerationScopeBusy(scope)
        yield

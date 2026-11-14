# Generation job exact-key conflicts (STAB-015.03a)

This changes creation and failed-job retry in
[generation_job_service.py](../backend/app/services/generation_job_service.py).
It implements only the existing exact-key conflict boundary from the
[accepted ADR/backlog](adr/STAB-015-backlog.md#stab-01503a--exact-key-conflict-normalization).
The hash inputs, migration 0005 partial unique index
`uq_generation_jobs_active_dedupe_key`, and predicate
`status IN ('queued', 'running')` are unchanged. Package admission, execution
accounting, fencing, recovery policy, providers and scheduler defaults are outside
this change.

## Conflict result

Only a PostgreSQL `IntegrityError` whose original exception has **both**
`sqlstate == '23505'` and `diag.constraint_name ==
'uq_generation_jobs_active_dedupe_key'` is normalized. Other integrity failures
propagate unchanged. The candidate INSERT or retry UPDATE happens inside a
savepoint; a known conflict rolls back only that savepoint and reloads an active
job by the same key.

- Creation with `skip_duplicate=True` returns `(active_job, False)`.
- Creation with `skip_duplicate=False` raises the existing
  `GenerationJobValidationError` with `Active generation job already exists:
  id=…`. The Admin API continues translating this class to its existing 400 error.
- If the competing row becomes final before reload, there is at most **one more
  write attempt**. Either it succeeds, finds another active duplicate, or raises
  a controlled validation error asking the caller to retry the request. A final
  job is never returned as an active duplicate.
- Single-job retry uses the same validation rejection for an active duplicate.
  The failed job retains its status, run link, attempts, error, and timestamps.
- Batch retry skips the colliding member, counts it under its original status
  in `skipped_status_counts`, and continues with other eligible members. The
  existing envelope/status vocabulary is unchanged. An unrelated error still
  propagates and rolls back the private batch transaction.

## Transaction ownership

`commit=False` participates in the scoped caller Session. It never commits or
rolls back the outer transaction. `Session.begin_nested()` **always pre-flushes**
existing pending writes, even under `no_autoflush`. Therefore the candidate is
added/changed only after entering the savepoint, and the pre-flush is outside the
dedupe catch. Valid caller writes may become flushed in the outer transaction;
they survive candidate failure and remain under caller commit/rollback control.
An invalid caller pre-flush propagates its original error; the caller must recover
its own failed transaction.

`commit=True` now owns a short, independent Session/transaction on the same engine.
Committing a savepoint cannot commit just that savepoint's rows, so using the
scoped Session's commit would also commit unrelated caller work. The independent
transaction preserves even previously flushed unrelated inserts, updates and
deletes. After its commit, `merge(load=False)` attaches its clean job snapshot to
the caller Session without flushing unrelated work. Returned jobs remain usable
by existing callers that later update them through `db.session`. A caller rollback
does not undo a job already committed with `commit=True`.

Independent writes require committed state for the **related job**. Pending edits
to the candidate key or retry target produce a controlled validation rejection
before refreshing/merging their objects or writing the target. This applies to
pending duplicate priority edits under `commit=False` as well: they are preserved,
not silently refreshed. Commit/flush those edits explicitly before another lookup.

Two narrow public SQLAlchemy Session event handlers record only GenerationJob
IDs/keys written by ORM flushes and clear them when the outer transaction ends.
Registration requires a real mapped model class; the flush callback captures
that class. Import-only policy checks with fake/unmapped models must not register
process-wide hooks or poison later real ORM writes.
This lets `commit=True` detect a related job insert/update/delete that has already
been flushed (and therefore left `new`/`dirty`), preventing an independent writer
from waiting on that caller's own write. Unrelated job keys remain allowed. The
record is conservative across a rolled-back nested transaction: end the outer
transaction before using `commit=True` for a touched key. Existing untouched ORM
objects are not treated as uncommitted writes.

The supported composition boundary is ORM writes through the application Session.
Raw SQL/Core DML or row locks taken directly by a caller are not tracked by these
ORM-flush handlers: callers holding such related work must finish that transaction
before a committed creation/retry, or use `create_generation_job(commit=False)`.
This change does not add a global database lock timeout or claim generic SQL
transaction introspection. SQLAlchemy Sessions must not be shared across threads.

The conflict reload assumes the supported PostgreSQL default READ COMMITTED
isolation. A caller using a stronger snapshot may not observe a committed winner;
the two-attempt bound still applies, and unrelated serialization errors propagate.

## Verification and integration handoff

The new [regression module](../backend/tests/test_generation_job_dedupe_conflicts.py)
is written for the [disposable harness](testing-safety.md). It uses independent
Sessions bound to the captured test engine, two non-daemon contender threads,
barriers/events at SQL execution, real PostgreSQL constraint diagnostics, bounded
waits/statement and lock timeouts, and unconditional rollback/close/join cleanup.
No provider execution is needed. The matrix includes both commit/skip modes,
different keys, winner finalization and repeated contention, parent pending and
flushed insert/update/delete preservation, unrelated constraints, retry collisions,
same-key caller edits and batch/Admin contracts.

The orchestrator verified the six-file selection below (145 tests), together
with 99 recovery/shared-read regressions: **244 passed in 11.12s** on 2026-11-15.
The sanitized disposable PostgreSQL project cleaned up successfully. Two fixture
setup failures in the first run were corrected by performing delete-cascade
loading before staging the pending state under test; pre/post preservation
assertions remain. Independent source review found no blocker within the
documented ORM composition boundary. Full integrated verification is recorded in
[CURRENT_STATE](CURRENT_STATE.md).

The first full integration run exposed an import-order regression: existing
paid-policy unit tests import the service with fake models, and unconditional
global listeners survived those imports. Registration now requires a mapped
model class and captures it. Three new import/flush regressions and the unchanged
paid/publication/service/sitemap checks passed (**126 tests in 5.69s**), followed
by the **681-test integrated full suite in 30.39s**. Existing safety tests were
not altered to hide the regression.

Focused selection:

```bash
bash scripts/backend-test.sh tests/test_generation_job_dedupe_conflicts.py tests/test_generation_job_service.py tests/test_admin_generation_jobs_api.py tests/test_generation_job_scheduler_producer.py tests/test_generation_job_worker.py tests/test_generation_job_cli.py
```

No migration, route/app-factory registration, Compose setting, credential or
scheduler wiring is required. None of these tests executes a provider request.

# Atomic package admission — STAB-015.03b

Implementation contract, reviewed against `.02b` commit `eee6ab1`. Accepted
[D3/D4](adr/STAB-015-generation-execution.md) remain authoritative. This is not
production activation, paid-request admission or complete fencing.

## Why the boundary changed

At the iteration baseline, lifecycle admission performed SELECT-before-INSERT
and returned another caller's running run. An age-only reaper ran first, allowing
a slow execution to lose its active status while still processing. Exact-key
job deduplication could not exclude other providers, job types or overlapping
sign subsets. The retry helper also counted retries before admission.

The new authoritative package is the exact stored tuple
`target_date + locale + forecast_type`. Provider, job type and sign subset do not
partition it. No case/whitespace aliases or sign-level parallelism are introduced.

## PostgreSQL and transaction contract

Migration `0007_generation_scope_admission` adds partial unique index
`uq_generation_runs_active_package` for `status = 'running'`. Multiple finalized
historical runs remain valid. A transactional historical-conflict check plus DDL
lock prevents installing the index over conflicting active history. Conflicts
abort unchanged with bounded sanitized diagnostics; the migration does not select
a winner, rewrite history or resolve duplicates. Downgrade removes only this index.
All migrations in verification run only in the disposable PostgreSQL environment.

[`package_admission`](../backend/app/services/generation_admission_service.py)
combines that database backstop with a short transaction advisory lock. The lock
key is a namespaced deterministic hash of the package. Hash collision can cause
conservative contention, never authorize duplicate work. `package_scope_lock`
coordinates decisions but does not independently admit an execution.

The helper requires PostgreSQL READ COMMITTED, DBAPI autocommit disabled and an
active caller-owned transaction. Pending ORM writes are rejected before the
savepoint can implicitly flush them. Flushed unrelated work remains caller-owned.
Only the named unique conflict becomes `GenerationScopeBusy`; other SQL errors
propagate. It never commits or rolls back the outer transaction.

A real savepoint is established before SET LOCAL or lock operations. Lock and
statement waits are bounded (1s/5s), preserving stricter caller settings. Settings
restore after success or savepoint rollback. The transaction owner must commit
before processing; advisory locks remain held until that commit. No package
admission lock spans provider transport. The existing lifecycle's separate item
transaction behavior is unchanged by this task.

Lifecycle first rejects caller-owned writes, performs existing preflight, then
commits run/execution/link together under package admission. Failed preflight
retains its established failed-run audit. An admitted queue claim retains its
previous immutable execution even when package admission loses. A losing
contender receives no foreign run, creates no generation items/transport attempts
and makes no provider call.

The retry helper rechecks missing coverage and its existing retry-run count
under the same lock. Thus a fast winner that finishes before the next lock is
acquired cannot bypass the cap with an old count. This counts existing retry runs
for the package, not requests, tokens, jobs or daily paid budget. Preflight-denied
failed audit rows are recorded outside that lock: this serializes admitted starts,
not an absolute upper bound on every failed audit row. Normal generation
still preserves published forecasts and retries normally target missing content.

## Caller contracts

| Caller | Busy outcome |
| --- | --- |
| Direct lifecycle | Nonretryable `GenerationScopeBusy`; no foreign run result. |
| Immediate Admin generation/retry | Additive HTTP 409, existing error envelope, code `generation_scope_busy`. Success responses unchanged. |
| Package CLI | Exit 1 and sanitized stderr message; no false run summary. |
| Direct scheduler | Reports the target skipped/busy and continues other dates. |
| Queue worker | Fails only its own unlinked losing claim using status/owner/claim-count CAS; does not attach the winning run. No automatic requeue added. |

Before paid/local/publication gates, an already-linked duplicate dispatch raises
`ExecutionAlreadyStarted` without changing the job, owner, locks or run. This
exception cannot fall through to generic failure cleanup. Busy disposition
reacquires the package lock and rechecks the immutable link, closing the race with
the first dispatch's admission commit. If that admission is still in progress,
the second call preserves the claim and reports a controlled processing failure.
The future lease epoch strengthens captured claim authority separately.

Successful/no-work CLI contracts, queue dedupe semantics, public read endpoints,
publication rules and SDK retry settings are preserved. Public reads never admit
or execute generation.

## Recovery and activation limits

Generation startup no longer automatically closes stale runs. Its existing
`stale_after_hours` argument remains accepted but cannot authorize package release.
Explicit legacy run cleanup excludes ledger-linked runs. Queue stale cleanup
excludes jobs with any execution history, including an unlinked claim. This is
conservative retention; age or missing link does not prove that transport was
never reached. Explicit cleanup of unmanaged legacy history remains available.

Normal finalization releases the running-index slot. A crash can leave it blocked;
no automatic recovery is implemented here. `.04b/.04c/.05b` are required for safe
fencing/recovery. The early duplicate check does not fence a later generic error:
if a link commits after an early miss, the old preflight/error/finalization paths
still need `.04c`. Mixed old/new executors must remain stopped during rollout.
These are explicit remaining limits, not evidence that package uniqueness or
successful tests provide exactly-once external execution.

Production remains blocked by `.02b`. A real epoch, atomic request cap `.03c`,
provider pause, complete fencing, role isolation and an approved rollout are
still required. There is no new paid enable flag or production permission.

## Verification

The orchestrator's focused disposable selection passed **273 tests in 40.28s**
(2026-11-15). It includes the four new scope suites plus execution starts,
lifecycle, worker/job/dedupe and paid/publication regressions. The initial run
exposed lazy-savepoint timeout leakage; the correction passed the same regression
without weakening its assertions.

Deterministic independent-session tests cover direct/queue/provider/subset/job-type
races; losing-call zero transport; unique-index bypass arbitration; historical
migration rejection/preservation; rollback/timeout/outer transaction ownership;
retry-cap serialization; published-content preservation; duplicate dispatch before
and after link commit; busy API/CLI/scheduler mappings. Full integrated iteration
results and rollout limitations are recorded in [CURRENT_STATE.md](CURRENT_STATE.md).
The subsequent full backend run passed **864 tests in 86.85s**; both disposable
projects cleaned up. No live runtime or database was used.

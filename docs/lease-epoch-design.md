# Lease epoch and explicit bounded renewal — STAB-015.04a

Implemented foundation, with integrated verification recorded in
[CURRENT_STATE.md](CURRENT_STATE.md). **Not complete fencing, automatic recovery,
automatic heartbeat scheduling or production timing activation.**
Accepted D4 is unchanged; P2 runtime timing measurements remain pending.

## Schema and migration

Revision `0008_generation_job_leases` follows `0007_generation_scope_admission`.
It adds six GenerationJob fields: nonnegative bigint `lease_epoch` (default 0),
nullable UTC heartbeat/expiry/deadline timestamps and nullable integer TTL/interval.
Zero represents unallocated legacy history; no historical epoch is fabricated.

A timing snapshot must be wholly absent or wholly present with positive epoch,
finite aware timestamps, positive interval < TTL, heartbeat < expiry <= deadline,
and expiry no later than heartbeat + TTL. A running positive-epoch job requires
an owner and finite claim timestamp. Model metadata matches these DB constraints.

The trigger requires queued -> running to advance exactly one epoch. Other
transitions cannot alter the epoch; terminal -> running must first requeue.
Owner/claim timestamp and timing policy are fixed within a running epoch.
Heartbeat/expiry cannot move backwards; a new claim can choose a new timing policy.
Direct INSERT cannot fabricate an allocated epoch. These structural rules are not
complete authorization/fencing of every job/run/forecast write.

Upgrade locks jobs and executions before any DDL and refuses **any positive
historical job-linked execution epoch**. Migration 0006 allowed such snapshots;
starting those jobs again at zero could reuse an old epoch and let an old execution
match a later claim. Refusal preserves schema/data and requires separately
authorized inspection/reconciliation; it does not infer a counter or rewrite rows.
NULL-epoch legacy history upgrades unchanged and receives epoch 1 on its first
new claim. DDL lock/statement waits are bounded at 5s/15s while preserving stricter
caller settings. Alembic owns rollback on failure.

Downgrade locks jobs and refuses allocated/timed lease state before dropping
anything. No force option or live migration is supplied. Migration/readiness now
require packaged head 0008; rollout to a live DB remains separately authorized.

## Claim and handoff contract

The existing PostgreSQL row lock / SKIP LOCKED claim serializes allocation. In one
transaction it increments epoch and claim count, snapshots optional timing using
DB clock after the lock, and creates the `.02b` immutable execution with that epoch.
The stable claim UUID still derives from job ID and monotonic claim count; it is
correlation, while the genuine epoch distinguishes ownership generations.
Retry/reclaim does not erase previous executions or reset counters.

A frozen `LeaseIdentity(job_id, owner, epoch, execution_id)` is captured before
commit/ORM expiration and attached only after confirmed commit. Commit failure or
ambiguous acknowledgment returns no authority. A later claim in the same Session
uses a fresh ORM object, preserving the old caller's identity rather than silently
replacing it through the identity map.

`claim_next_generation_job` still returns GenerationJob. Existing same-object
claim -> process callers remain compatible. A reloaded job must explicitly receive
the **original captured** identity through `process_claimed_generation_job(...,
lease_identity=identity)`; the worker never adopts an epoch from fresh DB columns.
A missing, expired or mismatched identity fails without modifying the successor.
Entry validation and `.03b` busy CAS check epoch; existing linked-duplicate
protection is preserved. Public queue response shapes are unchanged.
In-process observers must re-query a job by ID after a new claim; an older
captured ORM handle may be detached and cannot be refreshed as current authority.

The low-level execution writer trusts its internal caller to supply allocator
provenance; a positive numeric snapshot alone is not authority. Current runtime
job-linked starts use only the claim allocator. Arbitrary privileged SQL/internal
fabrication is outside this application contract and is not made safe by UUIDs.

## Timing and renewal

No heartbeat environment setting, automatic thread or production numeric timing
policy is activated. `lease_policy=None` is the default: epoch identity exists,
all timing fields remain NULL and renewal reports disabled. Explicit nonproduction
callers/tests may supply validated `LeasePolicy(interval_seconds, ttl_seconds,
max_duration_seconds)` with interval < TTL <= duration. PostgreSQL integer bounds
are storage limits, not recommended operating values. Test values are not defaults.

`renew_generation_job_lease(identity)` owns a separate short Core transaction and
connection; it never commits/flushes/rolls back the caller Session. Connect timeout
is 2s and statement/lock timeouts 1s, using NOWAIT on the matching job. These are
local operation bounds, not a strict end-to-end DNS/network wall-clock deadline.

Renewal verifies running state, captured owner/epoch and matching immutable
execution snapshot. DB time is sampled after the lock. Early cadence reports
not_due without writing; clock regression, expiration and deadline fail closed.
A renewal can extend expiry only up to the original fixed deadline. Conditional
update is serialized with takeover; old handles, including reused worker IDs,
cannot renew a new owner's lease. Only confirmed commit returns renewed.
Connection/commit/cleanup uncertainty returns sanitized unavailable, never a
new execution permit. STAB-007 BaseException network violations are not swallowed.

P2 still needs measured provider/run durations, bounded transport deadlines,
operator-selected heartbeat/TTL/max duration and a justified renewal runner.
No measurement or production value is invented by this change.

## Recovery and activation limits

Age-only cleanup excludes positive-epoch jobs, known paid legacy jobs and any
ledger-managed history. Legacy unmanaged stub cleanup remains available. Expiry
alone does not prove a worker died or transport was absent; this task never
requeues/cancels/refunds a managed job automatically.

Admission-time identity checks do **not** fence later forecast/item/attempt or
run/job writes. A stale in-flight worker may still reach existing publication or
finalization writers; `.04b` and `.04c` must cover every writer before safe reclaim
or production rollout. Generic pre-link/error/finalization races remain explicitly
open. The migration trigger is not a substitute for those conditional writers.

Production timing/renewal remains disabled. Production claims can allocate a
structurally valid epoch for existing denial audit, but do not create a production
execution start or authorize transport. `.02b` production blocker, `.02c` known-paid
deny, SAFE-001, publication policy and local permissions remain independent.
A genuine epoch alone does not satisfy cap, fencing, provider pause or rollout.

## Verification scope

Focused suites cover pure fake-clock policy; first/concurrent claim; manual retry
with reused worker ID; stale/reloaded handles; current/stale owner renewal;
renewal/takeover contention; exact expiry/deadline/cadence; long execution;
caller-owned transactions; before/after commit failure; production denial;
legacy cleanup exclusions; fresh/old schema upgrade; old positive epoch refusal;
constraints, UTC timezone metadata and refused destructive downgrade.

Parent integrated verification on 2026-11-15: **354 focused tests in 59.24s**;
after updating publication tests to re-query detached historical claim handles,
**64 publication/lease regressions in 10.29s** and **1049 full backend tests in
127.24s** passed. Existing production-denial assertions remain and now also check
epoch increments and zero generated items/attempts.

All database checks used STAB-007 disposable PostgreSQL and fake/stub execution;
projects cleaned their containers/networks. No live DB, production migration,
automatic heartbeat, scheduler or provider transport was used. These are parent
integrated results, not inferred from agent-local AST checks.

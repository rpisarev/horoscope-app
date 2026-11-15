# Immutable execution starts — STAB-015.02b

Implementation contract (not production activation): migration
[`0006_generation_ledger`](generation-ledger-schema.md) is the storage boundary.
The writer participates in its caller's transaction; it never commits or rolls
back that transaction. A replay of an execution UUID must match its complete
immutable snapshot. A replay of a run link must identify the same run.

Development/test queue claim and execution-start insert commit together. The
claim identity is a deterministic UUID of job ID and the monotonically increasing
claim attempt count. This is idempotency/correlation only, **not lease authority**.
Manual retry and reclaim have a new claim count and keep previous ledger rows.
No epoch is fabricated. `.04a` must supply the real epoch separately.

Direct lifecycle execution first performs the existing paid/publication/prompt
preflight, then commits its new run, execution and immutable run link together.
Denied preflight retains the legacy failed-run audit with no execution, item or
provider-attempt row. Queue claims can exist without a run (preflight denial,
no-work or a crash before run creation); a claim is never a paid-request attempt.
Lifecycle dispatch of a queue claim reuses its execution ID and never creates a
second `dev_direct` record. A linked execution cannot start another run/transport.

Operational timestamps come from PostgreSQL `clock_timestamp()`, converted to
UTC; they are not target dates or mutable historical job timestamps. Provider
identity comes from the normalized factory selection (queue: persisted provider),
never returned provider/model metadata. Existing item/attempt metadata contracts
are unchanged.

Production lifecycle execution is explicitly blocked after existing paid and
publication checks. Production claims retain existing claim/audit behavior but
do not create a production ledger row or reach transport. This preserves useful
denial reasons and avoids fake epochs. It deliberately tightens the former
production capability-only execution contract; publication capabilities remain
valid independently. A real epoch alone will not authorize production transport:
atomic admission `.03c`, fencing, pause and rollout prerequisites remain pending.

Autonomous lifecycle/claim functions reject unrelated pending or ORM-flushed
caller writes before their first mutation. Explicit low-level ledger writers are
transaction-owned and may be combined with other writes by their caller. Session
Core DML and writable CTEs are tracked too. Textual SQL is conservatively treated
as caller-owned unknown work (including textual SELECT); finish that transaction
before invoking an autonomous lifecycle. Arbitrary driver-level connection work
is outside the ORM ownership contract. Transaction errors must be rolled back by
their owner.

The writers require PostgreSQL and do not silently change caller timeouts. The
transaction owner must set bounded lock/statement timeouts where needed; INSERT
triggers/FKs and UUID conflicts can wait on concurrent transactions. Admission
timeout/locking policy is the `.03b` coordinator's responsibility. The legacy
claim transaction has no new timeout policy in .02b; runtime activation stays
blocked. Regression transactions explicitly bound their lock/statement waits.

No legacy backfill, request-intent/reservation writer, diagnostic accounting,
admission cap, new stale recovery policy or complete fencing is added here.
Standalone probe accounting belongs to `.08c-B`. The legacy stub-only text helper
records a direct start without a run link; it does not publish forecasts.

Parent integrated verification (2026-11-15): **210 focused tests passed in
12.23s**, followed by **795 full backend tests in 45.92s** through the unchanged
STAB-007 disposable PostgreSQL harness. Both generated projects cleaned up.
No live database, provider transport, scheduler or deployment was used. The
subagent's host mock check lacked SQLAlchemy; the integrated harness subsequently
covered those tests successfully. This prerequisite does not activate production.

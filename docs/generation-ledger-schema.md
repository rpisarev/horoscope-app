# Generation ledger schema — STAB-015.02a

Status: **P3 storage design approved by parent for .02a (2026-11-15).** Accepted
[D1–D8](adr/STAB-015-generation-execution.md#6-прийняті-рішення-власника)
remain future policy. This change adds storage only: no writers, admission,
transport, fencing, recovery, release/refund, runtime switch or legacy backfill.

## Storage contract

All four new tables are append-only under ordinary SQL: PostgreSQL triggers
reject every UPDATE and DELETE, including no-op UPDATE. There is no mutable
status, updated_at or ORM delete cascade. New foreign keys use RESTRICT, never
SET NULL/CASCADE. Existing tables, IDs, constraints and mutable fields are not
altered. New-table INSERT triggers check cross-table coherence; a foreign key
alone does not establish that an item belongs to a run or execution.
Those checks hold referenced rows under FOR SHARE until the inserting transaction
ends and resolve tables in the trigger's own schema, not the caller's search path.
FOR SHARE blocks changes by other transactions; it does not stop the inserting
transaction itself from subsequently changing the referenced mutable legacy rows.
They establish insertion-time coherence only. Existing mutable job/run/item rows
can subsequently change; this is neither full historical cross-row immutability
nor fencing. The immutable snapshots and links remain unchanged.

UUID primary keys are caller-supplied (no hidden server/client generator). A retry
has a fresh request UUID; replay of a committed insert reuses its original UUID.
Neither kind of UUID provides provider-side idempotency.

### generation_executions / GenerationExecution

| Field | Contract |
| --- | --- |
| id | UUID PK, immutable execution-start identity. |
| job_id | Nullable bigint FK generation_jobs.id; required for queue_worker, forbidden for other origins. Indexed with started_at. |
| origin | queue_worker, dev_direct or dev_diagnostic. |
| deployment_mode | production, development or test. Production requires queue_worker and positive lease_epoch; diagnostics never production. |
| provider | Nonblank lowercase canonical selected-provider identity, not response metadata. |
| target_date, locale, forecast_type | Package snapshot; all required except dev_diagnostic, which has all three NULL. Scope index includes started_at. |
| policy_version | Required nonblank version of the execution policy snapshot. |
| lease_epoch | Nullable positive bigint; NULL only where epoch is unavailable outside production. Snapshot, not fencing or a lease allocator. |
| started_at | Required timestamptz, explicitly supplied; not a job's mutable timestamp. |

INSERT checks job provider and package scope match the execution snapshot. It
does not compare the mutable job.run_id, which may change after retry/reclaim.
Multiple executions per job are allowed. No active-scope uniqueness is claimed.
A positive numeric lease_epoch is only a structural requirement, not proof of
lease authority. Current-owner authorization still requires the future epoch
allocator, ownership checks and fencing protocol.

### generation_execution_runs / GenerationExecutionRun

| Field | Contract |
| --- | --- |
| execution_id | UUID PK/FK generation_executions.id. One run link per execution. |
| run_id | Required bigint FK generation_runs.id; indexed, not unique. Multiple historical executions may reference the same run. |
| linked_at | Required timestamptz, explicitly supplied. |

Unique (execution_id, run_id) supports a composite FK from request intent. INSERT
checks the run's date/locale/type against the execution snapshot and linked_at
>= started_at. Diagnostic execution cannot have a run link. Start can commit
before a run exists; creation of the run and this link belong to the same future
transaction. This avoids UPDATE of an immutable execution to fill run_id.

### generation_api_requests / GenerationApiRequest

One row means **one admitted paid API request intent AND its reservation**. It
does not mean one job, item, claim, execution, or confirmed remote request.
No separate mutable reservation row/counter can commit without its intent.

| Field | Contract |
| --- | --- |
| id | UUID PK. |
| execution_id | Required UUID FK generation_executions.id. |
| request_no | Required positive integer, unique with execution_id; each admitted retry has its own number/UUID. |
| run_id, item_id | Both nullable only for dev_diagnostic; required otherwise. Composite execution_id/run_id FK to execution_runs; item_id FK generation_items.id. |
| legacy_attempt_id | Optional bigint FK generation_attempts.id; INSERT checks attempt.item_id matches item_id. Not unique: legacy attempt and API request are distinct units. |
| admission_scope | Required nonblank nonsecret logical budget/account scope supplied by future P1 configuration; not a key or provider-returned ID. |
| policy_version | Required nonblank admission policy version. |
| admitted_at | Required explicit timestamptz, >= execution.started_at and linked_at when linked. |
| admission_day | STORED GENERATED date: (admitted_at AT TIME ZONE 'UTC')::date. Caller cannot override; independent of session/business timezone and target date. |

Index (admission_scope, admission_day, admitted_at) supports future .03c shared
cap accounting. Index item_id supports historical correlation. INSERT checks
item.run_id and item package scope agree with the immutable execution and link.
Diagnostics require all run/item/legacy_attempt links NULL and nonproduction
execution. Structural allowance is not diagnostic execution authorization.
No defaults fabricate request counts, admitted timestamps or legacy records.
The future writer must derive admitted_at from trusted database admission time,
not caller input, target date or backdating. The explicit schema timestamp allows
fixtures and historical identity storage; it does not enforce caller trust or a
hard cap. .03c must prove its UTC-midnight lock-boundary recheck: establish the
authoritative admission instant/day after acquiring serialization and re-evaluate
the day/lock/count if midnight was crossed. It cannot count under yesterday's
lock and reserve on today's date without rechecking today's cap.

### generation_api_observations / GenerationApiObservation

| Field | Contract |
| --- | --- |
| id | UUID PK. |
| request_id | Required UUID FK generation_api_requests.id. |
| observation_no | Required positive integer; unique with request_id. |
| recorded_at | Required explicit timestamptz, >= admitted_at. |
| outcome | unknown, succeeded, failed or not_sent. No default success/failure. |
| review_state | requires_review or recorded; unknown requires requires_review. recorded is evidence registration, not authorization/resolution. |
| evidence_code | Nullable nonblank bounded code; required for not_sent. A code is not itself proof; .02c must establish durable protocol evidence before writing not_sent. |
| provider_request_id | Optional bounded provider correlation ID; not an idempotency guarantee. |
| input_tokens, output_tokens | Nullable nonnegative bigint, independently unknown; no zero defaults. |
| usage_source, model_name | Nullable nonblank provenance; both required if either token count is supplied. Model is usage provenance, never execution permission. |

No unbounded/raw response, secrets, prompt payload or monetary estimate fields.
P7 pricing/usage ingestion is .02d; no invented price/currency precision here.
Multiple observations are allowed, including unknown followed by more evidence.
Their sequence records observations, not a latest-row-wins truth algorithm.
An absent observation is semantically unknown/requires_review, never not_sent.
Outcome certainty and independently reliable usage evidence are separate: even
an unknown outcome may contain supported token counts and provenance. No observation reduces the
reservation count; even not_sent has no release/refund action in this schema.
A single not_sent observation cannot contain positive input_tokens or
output_tokens. Either field may be NULL or explicitly zero; zero still requires
the existing usage provenance and model fields. Conflicting observations may
coexist, and this consistency check establishes no latest-row-wins rule.

## Future transaction protocol (not implemented by .02a)

1. .02b commits an execution start with the claim/identity snapshot. .03b/.04a
   will supply package ownership and the actual epoch; a new start does not
   authorize spending. Run creation and the immutable run link commit together.
2. .02c/.03c use a short, private transaction with a deterministic shared lock
   providing exclusive serialization for (configured admission_scope, UTC
   admission day), plus .03b package and
   .04a epoch checks. Under that lock recheck SAFE-001/local permission, pause,
   package ownership, deadline and numeric cap; insert one request intent/
   reservation row. All callers for the same logical cap must share the lock
   scope. P1 mapping/number and exact .03b/.03c/.04a locking SQL remain their
   implementation gates. This migration installs no locks or caps.
3. Commit before HTTP; release database locks before transport. A failed or
   ambiguous commit forbids proceeding with transport. Reconcile only using the
   original request identity; do not create a second reservation to hide doubt.
   Referenced run/item/legacy-attempt rows must already be durable or be inserted
   in this same reservation transaction. Do not leave them uncommitted in a
   different Session while opening a private transaction whose FOR SHARE reads
   wait for those rows; that can self-lock the caller. Future writers must test
   transaction ownership explicitly.
4. Record observations in a separate bounded transaction after transport. A
   crash after intent commit, before transport, or after remote acceptance can
   leave identical durable rows: unknown/requires_review. Missing result, lease
   expiry, socket exception, timestamp or local UUID proves neither sent nor
   not_sent. Observation write/commit failure preserves the committed intent.
5. Any allowed retry needs a new admission, reservation and request identity.
   Later reconciliation appends evidence; it must not rewrite admission history
   or assume the latest observation is authoritative. Releases, cancellation,
   authorized manual decisions and complete fencing need future explicit
   protocol/schema work; there is no automatic refund or recovery here.

The production epoch constraint deliberately blocks .02b production activation
until .04a supplies a genuine epoch. Do not invent an epoch to satisfy the schema.
Approval covers .02a storage only; future locking, admission and fencing above
are requirements for subsequent work, not implemented or approved protocols.

## Retention, migration and enforcement boundary

Upgrade creates empty tables/functions/triggers only. Existing rows and IDs stay
unchanged; all pre-cutover API counts and usage remain unknown. Retain all ledger
rows indefinitely until a separately authorized retention/archive design exists.
No ordinary DELETE cleanup or administrative SQL override is supplied.

Append-only triggers do not prevent database-owner DDL, trigger disabling or
TRUNCATE. Runtime roles must not have those powers before paid rollout; current
role deployment is unchanged. STAB-007's verified disposable test identity owns
its DB and uses TRUNCATE ... CASCADE intentionally. PostgreSQL follows FK table
dependencies, so standalone diagnostic rows with NULL job/run links are also
included through the execution table's job FK. No shared fixture edit is needed.

Downgrade obtains locks on all four new tables and refuses if any contains rows,
before dropping any object. Empty-schema downgrade removes only new objects.
Nonempty history must be archived under separate authorization; no destructive
force option is provided. Migration is PostgreSQL-only and fails explicitly on
unsupported dialects rather than silently omitting the enforcement contract.

The new packaged Alembic head is 0006_generation_ledger. Existing readiness
discovers packaged heads dynamically: deploying this code against a database
still at 0005 will report not ready until the separately authorized migration
rollout. No live deployment or migration is performed here; the isolated
worktree leaves the live checkout and development database untouched; the live
DB revision was not queried. Existing API contracts and dynamic packaged-head
lookup passed the parent's combined regressions below.

## Parent verification

The parent ran the schema/migration plus existing schema/readiness selection:
**89 passed in 13.60s**. After a test-only metadata-target cleanup removed an
unneeded legacy FK-cycle warning and cross-review added not_sent/usage consistency,
**7 focused tests passed in 1.24s**. The final integrated backend suite passed:
**750 tests in 76.81s**, no warnings. These runs used the unchanged STAB-007
disposable PostgreSQL harness, guarded connections, dummy credentials and blocked
provider network. Schema-local migration fixtures roll back completely; the test
projects cleaned up. The implementation subagent ran no DB tests. These checks
do not apply a live migration, authorize deployment, or prove future admission.

Covered scenarios:

- Fresh migration through 0006; 0005 history upgrade with unchanged IDs/content
  and zero fabricated ledger rows; no-current-table identity/schema changes.
- Schema/model column/type/default/PK/FK/unique/check/index parity; trigger
  existence and behavioral enforcement using raw SQL as well as ORM writes.
- Valid queue/dev/diagnostic links; rejected missing/foreign/mismatched links;
  immutable link history after a job's run_id changes; uniqueness violations.
- UTC midnight with non-UTC session timezone, immutable generated day and
  timestamps, positive epochs/ordinals, chronological link/request/observation.
- Unknown/no-outcome and multiple observations; NULL/partial/explicit-zero
  usage, provenance and negative-value rejection; no automatic refund logic.
- Failed insert/savepoint rollback, outcome rollback retaining committed intent,
  UPDATE/DELETE rejection, standalone diagnostic TRUNCATE CASCADE cleanup.
- Empty downgrade/re-upgrade; nonempty downgrade refusal and transactional DDL
  failure rollback preserving original history and schema.

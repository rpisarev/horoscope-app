# Durable paid-request intent — STAB-015.02c

Status: **Incremental storage protocol and paid-deny boundaries implemented.**
**Production transport coordinator, atomic daily cap and paid activation remain
blocked pending .03c and the remaining accepted safety chain.**

Accepted [D1–D8](adr/STAB-015-generation-execution.md) and the reviewed
[P3 storage contract](generation-ledger-schema.md) remain authoritative. This
changeset builds on `.02b` / `.03b` and needs no new migration. It deliberately
does not route paid execution through a partially implemented reservation system.

## Boundary and reason for staged implementation

The legacy lifecycle prepares a GenerationAttempt with flush, then calls the
provider inside the item transaction. A crash/rollback can therefore lose that
attempt without proving that an external request was never sent. An execution
start is durable separately, but is not a paid-request reservation.

Migration 0006 makes one GenerationApiRequest row both intent and counted
reservation. It has no speculative/noncounted intent state. Creating a provisional
row, permitting transport, and adding the cap later would violate D2. Therefore
this task delivers reusable transaction-owned primitives plus an unconditional
known-paid transport blocker. The final transaction/dispatch coordinator belongs
to `.03c`; no runtime fallback or enabling knob is supplied here.

## Implemented storage interfaces

[`generation_request_intent_service.py`](../backend/app/services/generation_request_intent_service.py)
uses an explicitly active PostgreSQL Core transaction with DBAPI autocommit off.
It does not borrow/flush an ORM Session, commit/roll back the outer transaction,
call a provider, publish, retry, refund or reconcile history.

| Interface | Implemented contract |
| --- | --- |
| `insert_request_intent` | Caller supplies stable request/execution UUIDs, request ordinal, scope/policy and durable linkage. Exact UUID replay must match all immutable inputs; timestamp is preserved. A new request uses DB clock time and the schema-generated UTC admission day. |
| `append_request_observation` | Appends a separate stable observation UUID and serialized ordinal. Exact replay must match evidence. Known outcome/usage must be supported by caller evidence; this helper does not infer them from an exception. |
| `read_request_evidence` | Bounded metadata-only evidence, default 100 and maximum 200 observations. Returns unknown/requires_review for missing, truncated, conflicting or unresolved evidence. No recovery authority. |

Intent writes lock the parent execution; observations lock their request. Core
savepoints are established before timeouts or writes. Operation waits are bounded
(1s lock, 5s statement), retaining stricter caller settings and restoring settings
on success/rollback. Only known UUID/ordinal unique conflicts are normalized;
other IntegrityErrors propagate without rolling back unrelated outer work.
These primitives do not prescribe the final budget isolation/lock contract.
`.03c` must establish that separately, including current UTC-day revalidation.

An intent receipt can still be rolled back by its transaction owner. Even a
confirmed committed receipt is not a transport permit. Retries require independent
request identities and future fresh admission; replaying an insert never means
repeating HTTP. Request identity and execution identity remain distinct.

Observations permit unknown, succeeded or failed. This writer refuses `not_sent`
because no durable proof protocol exists yet. Missing response, intent-only state,
lease age, socket exception and crash timing prove neither sent nor not-sent.
Unknown usage remains NULL. Independently reliable usage may accompany an unknown
outcome with provenance/model metadata, without making billing or completion
certain. No reservation is refunded by an observation.

The evidence reader preserves explicit `requires_review`, including schema-valid
succeeded/failed records. Later success cannot silently erase earlier uncertainty;
conflicting outcome/correlation/usage and truncated history remain review-required.
Provider success is not forecast publication success. No raw prompts/responses,
keys or unbounded provider payloads are added to this ledger interface.

## Integrated transport-deny contract

[`paid_admission_policy.py`](../backend/paid_admission_policy.py) has no Flask,
DB, dotenv or SDK dependency. It checks SAFE-001 first, then always raises
nonretryable `PaidAdmissionUnavailable` for known paid providers. No environment
value, injected client, fake receipt or caller flag authorizes paid transport.
This intentionally tightens previously enabled paid behavior, including explicit
development/test diagnostics. It is not an account-level budget control.

| Path | Current behavior |
| --- | --- |
| Direct lifecycle | Canonical selected provider is captured before factory access. SAFE-001 and admission blocker run before provider construction/items/attempts. Existing failed-run reporting is retained, with no fictional request reservation. |
| Queue worker | Persisted provider is checked with existing global/publication/local permissions. A denied claimed job fails without dispatch; its genuine claim/execution history remains. |
| Legacy stub text helper | Explicit canonical stub identity, existing execution-start behavior; no paid fallback or publication added. |
| OpenAI adapter | Literal openai guard at entry and immediately before SDK request; mutable adapter/result metadata cannot bypass it. |
| Probe main/helper | Production prohibition remains independent; admission denial precedes client construction/transport. Static profile listing remains read-only without dotenv/SDK. |
| CLI/Admin/scheduler | Existing entrypoint authorization remains; downstream guards cannot be bypassed with --allow-openai or SAFE-001=1. No scheduler activation. |

The adapter retains SDK `max_retries=0` and STAB-001 classification. Tests that
exercise parser/SDK/quota behavior explicitly mock the new blocker locally with
fake SDK or MockTransport; denial tests keep it real. Runtime has no test-mode
exemption. Public reads, publication policy and result envelopes are unchanged.
Package busy/duplicate handling stays separate; `.04c` still owns complete job/run
transition fencing. Full development diagnostic accounting remains `.08c-B`.

## Future transaction owner and activation gates

The following is required, **not implemented by this changeset**:

1. `.03c` validates logical account/cap mapping, finite numeric limits, current
   ownership/deadline, global/local permissions and applicable provider pause.
   It locks the shared admission scope/day and rechecks UTC day/count after lock
   acquisition; it must not count yesterday and insert today's reservation.
2. Under that final atomic boundary, insert one intent/reservation. Referenced
   run/item/attempt rows must already be committed or belong to the same
   transaction. Never hold those rows uncommitted in another Session while
   opening a private intent transaction; the schema's FOR SHARE checks can
   otherwise self-lock. Never commit unrelated caller work to cure that error.
3. Confirm transaction commit before HTTP and release DB locks. Failed/ambiguous
   commit forbids transport; investigate the original identity, never create a
   replacement reservation to hide doubt. No ledger-error fallback is allowed.
4. Record supported outcome in a separate bounded committed transaction.
   Observation INSERT/commit failure must preserve the intent and prohibit resend.
   Timeout/crash with uncertain remote outcome stays unknown/requires_review.
5. Complete provider pause/retry policy, fencing `.04b/.04c`, authorized recovery
   and controlled rollout before production paid activation. A real epoch or
   successful primitive test alone does not satisfy this chain.

Exactly-once remote requests are not claimed. Production mode remains separately
blocked by execution-start policy; the production probe is always forbidden.

## Verification and limits

Parent verification on 2026-11-15 through STAB-007:

- Standalone storage/policy selection: **67 passed in 11.12s**.
- Combined intent, SDK/quota, probe, lifecycle, worker, scope and publication
  selection: **297 passed in 38.50s**.
- Subsequent complete backend suite: **943 passed in 104.86s**, disposable project cleaned.
- Test image explicitly includes the new standalone module in COPY and its
  positive build-context allowlist; secret exclusions/network guards remain.

Fault tests inject failures into actual DBAPI commit before/after commit and into
observation INSERT/commit. Independent connections verify durability and see
intent before a fake timeout. Concurrent UUID conflicts hit real PostgreSQL
23505, preserving unrelated caller work. Other tests cover exact replay, new retry
identities, UTC day, lock/self-lock boundaries, explicit review state, no paid
transport/publication on denial and already-published stub content preservation.

The fault scenarios manually compose transaction-owned primitives and fake
transport. They do **not** prove a production dispatcher exists or that its future
no-resend/atomic-budget behavior is implemented. Final integrated results and
remaining deployment limits are in [CURRENT_STATE.md](CURRENT_STATE.md).

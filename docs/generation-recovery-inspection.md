# Read-only generation job inspection

STAB-015.05a adds bounded evidence for one positive job ID. It does not implement
the [Accepted execution ADR](adr/STAB-015-generation-execution.md)'s future ledger,
admission, fencing, recovery actions or queue defaults.

From `backend/`, in an explicitly configured environment:

```bash
python utils/generation_job_inspect.py --job-id 123
python utils/generation_job_inspect.py --job-id 123 --item-limit 50 --attempt-limit 100 --stale-after-minutes 60
```

The CLI sets `PYTHON_DOTENV_DISABLED=1` before application imports. The explicit
guard in `app/config.py` honors this value even with pinned python-dotenv 1.0.1;
normal startup without the flag retains its existing dotenv behavior. Provide database
configuration through the process environment. No provider credentials are
required. It never starts a scheduler, generates content, claims work, changes
records, retries, refunds, cancels, or closes stale work. It adds no HTTP route.

| Exit | JSON outcome | Meaning |
| --- | --- | --- |
| 0 | `ok` | Evidence report produced, including failed/partial/unfinished jobs. This is not a health or safe-retry verdict. |
| 1 | `unavailable` | Configuration, connection, schema or inspection failure; sanitized error only. |
| 2 | `invalid_input` | Exactly one valid positive job ID and bounded options are required. Invalid arguments are not echoed. |
| 3 | `not_found` | No job with that ID in the snapshot. |

`--help` prints ordinary CLI help. IDs are bounded to PostgreSQL signed bigint;
item detail defaults to 100 (maximum 500), attempt detail to 200 (maximum 1000),
and the diagnostic lock-age threshold to 60 minutes (range 1–10080). These
options never change worker policy. Output JSON has sorted keys; the same
snapshot and observation time give the same report. The service's optional
timezone-aware `now` argument supports reproducible age checks.

The service API is
`inspect_generation_job(job_id, *, now=None, item_limit=100, attempt_limit=200, stale_after_minutes=60)`
in [generation_recovery_inspection_service.py](../backend/app/services/generation_recovery_inspection_service.py).
Its successful envelope contains `schema_version`, `read_only`, `outcome`,
`job_id`, `observed_at`, `job`, `scope`, `coverage`, `run`, `lock`, `items`,
`attempts`, `observations`, `inconsistencies`, `unknowns`, and `limits`.
Missing jobs return only the version/read-only/job-ID/outcome fields. Invalid
service input raises `ValueError`; database/runtime read failures raise sanitized
`GenerationInspectionUnavailable`. The CLI additionally sanitizes startup failures.

All reads share one dedicated PostgreSQL READ ONLY REPEATABLE READ connection
from `generation_read_service.read_snapshot`. The caller ORM session is never
flushed, committed or rolled back, so pending writes are excluded and remain
pending. The shared service sets connect timeout 2 seconds, statement timeout
2 seconds, and lock timeout 1 second, with rollback/close on exit. These bound
database waits, not DNS or the entire process. There is a fixed number of queries.

`coverage` uses only the shared `published_coverage` helper's exact
date/locale/type scope and published rows. Explicit requested signs remain in
scope even when disabled later; `signs=null` uses current enabled metadata and
labels `scope.metadata_state=current_reconstruction`; historical intent remains
unknown. Items outside today's enabled set are observations, not proof of a
historical scope violation. Empty explicit/enabled scopes keep their
distinct states and never become full or fall back to static signs. Malformed
scope is `unknown`, not an inferred enabled scope. Scope is capped at 1000 entries
and 65536 serialized bytes. Oversized job scope has an unavailable coverage reason;
oversized enabled metadata fails the inspection through the shared helper.

Item/attempt `total` and `status_counts` cover the full currently linked run.
`records`, `returned`, and `truncated` describe bounded detail rows ordered by
item ID and item/attempt number/ID respectively. Detailed link inconsistencies
are checked only for returned rows. Missing/unlinked runs have unavailable/null
counts, not invented zero history. No matching date is used to guess a missing
run link. A job's claim counter is not a paid HTTP attempt count, and its mutable
run link does not represent every historical execution.

Lock owner presence and timestamps are exposed; arbitrary owner identity is
withheld. Stale age never proves worker death. Stored attempt status and boolean
response presence are local evidence; no stored response or attempt is not proof
that transport was unsent. `transport_outcome` remains unknown without the future
durable protocol. Publication coverage establishes current content availability,
not which worker caused it. Published content alongside an unfinished job/run
is reported explicitly. Stored run counters may lag items; a difference is an
observation, not proof of corruption. Later missing coverage also does not prove
a once-successful job failed historically.

Queries project safe fields and boolean response-presence expressions only.
Prompts, content, request/response bodies, error strings/types, model names,
creator, dedupe and batch metadata are never fetched for display. Provider,
status, locale and forecast-type display uses closed allowlists (`unknown` for
unrecognized values). Sign identifiers are bounded and suspicious/non-token
values become null placeholders, with `redacted_sign_count` preserving honest
counts. Exact raw scope still governs coverage; display redaction does not
change the lookup. This is conservative metadata handling, not a guarantee that
an arbitrary valid-looking identifier could never contain sensitive information.

The [focused regressions](../backend/tests/test_generation_recovery_inspection.py)
cover complete/partial/failed/missing-run/stale-lock/unknown-attempt and published
unfinished fixtures, safe CLI failures, malformed/oversized scope, explicit
disabled/empty metadata, bounded details, and pending/flushed caller writes.
Reference metadata changes are restored in `finally` blocks. Database execution
belongs to the authorized orchestrator via the [disposable harness](testing-safety.md):

```bash
bash scripts/backend-test.sh tests/test_generation_recovery_inspection.py
```

Orchestrator verification on 2026-11-15: 86 recovery/CLI/config tests and 13 shared
read-service regressions passed as part of the 244-test combined dedupe/recovery
run in 11.12s. The project cleaned up. Config tests execute configuration with a
fake dotenv loader and dummy environment, never a real .env or provider. A fixture
autoflush issue was corrected before the successful run without weakening the
pending/flushed-write assertions. Independent review identified the pinned dotenv
opt-out gap; the explicit config guard and regressions close it. Final full-suite
evidence is in [CURRENT_STATE](CURRENT_STATE.md). No live report was invoked.

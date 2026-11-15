# Current Project State

- State updated: 2026-11-15 (iteration 5 integration; ADR decision date remains 2026-11-14).
- Main working branch: `feature/main-page-start`
- Historical iteration 4 base: `17fb256ce8f5e651a5d05b4a8911d905585f4e82` (PR #25). Its worktree/runtime observations below describe that earlier iteration, not the current checkout. STAB-015 D1–D8 remain Accepted.
- Historical iteration 3 base: `4fe11be` (PR #24), incorporating STAB-015.01 and earlier safety fixes. The older verification sections below retain their own evidence and dates.
- Earlier publication audit baseline: `34623b27bd69d681edf1a3ab8f8aac31bc74cafa` (`Update frontend (#20)`). Results and runtime observations in the historical sections below belong to their recorded checkpoints.

## Stabilization checkpoint — iteration 5

Verified base `ea3c0ec166b37b00e05164521b7ab9cd4e78fd8f` (PR #26), local and
actual remote integration SHA agree. Original bind-mounted checkout remains
untouched on `feature/project-stabilization6`; work is isolated in
`/tmp/horoscope-iter5-integration`, branch `integration/project-stabilization-5`.
Owner-requested pause was resumed with all checkpoint file hashes unchanged.

| Task | Implemented boundary and activation limit |
| --- | --- |
| .02b | Immutable development/test execution starts and run links; canonical provider and DB UTC clock, exact UUID replay. Production activation still blocked. [Contract](generation-execution-starts.md). |
| .03b | Running-package unique index and short advisory admission transaction across providers/job types/sign subsets; controlled busy outcomes, retry-helper recheck. No hard paid-attempt cap. [Contract](package-admission-design.md). |
| .02c | **Incremental implementation:** transaction-owned durable intent/observation primitives and conservative evidence reader. No runtime paid coordinator/final atomic reservation boundary. Known paid application paths unconditionally denied until .03c and the remaining safety chain. [Contract](request-intent-design.md). |
| .04a | Real monotonic claim epoch, frozen ownership identity and explicit bounded nonproduction renewal. Timing default disabled; no automatic heartbeat/reclaim or complete fencing. [Contract](lease-epoch-design.md). |

Five native agents prepared independent changes in separate worktrees. Backend
prerequisites and DB suites were integrated serially; frontend verification ran
independently. Shared worker imports, test doubles and transaction boundaries were
reviewed explicitly. Independent cross-task review found no remaining new blocker;
generic error/publication/finalization races remain `.04b/.04c` work.

**Verification milestones:** 19 mock safety guards passed before PostgreSQL work.
`.02b`: 210 focused / 795 full; `.03b`: 273 focused / 864 full; `.02c`: 67 primitive,
297 focused / 943 full. `.04a` integrated selection: **354 passed in 59.24s**.
These are distinct prerequisite runs, not a substitute for final combined results.
An admission test found lazy-savepoint timeout leakage; the coordinator now opens
its savepoint before connection-level settings. Cross-review found a historical
positive-epoch migration hazard; 0008 now refuses that history before DDL.
Full integration also exposed old publication tests refreshing detached claim
handles; they now read current state by ID and additionally verify monotonic epoch
and zero items/attempts. No publication/paid-denial assertion was removed.

**Final combined backend verification:** `bash scripts/backend-test.sh` passed
**1049 tests in 127.24s** after **64 publication/lease regressions in 10.29s**.
The initial combined run had 1045 passes and the four detached-handle test
failures described above. Only the test's state-read contract changed before the
passing rerun. All DB runs used disposable PostgreSQL, dummy credentials and
fail-on-unexpected-network/process guards; their test containers/networks were
removed. The STAB-007 script, guard, conftest and Compose isolation are unchanged;
the test image allowlist/COPY additionally includes the new paid-admission module.
SEC-002 frontend is independently verified on the integrated tree (181 tests, 22 POC,
typecheck/build/ci/ls passed; audit 6 High/1 Moderate); its separate commit is pending
at this backend milestone.

**Migration/runtime boundary:** packaged head is **0008**, never applied to live
PostgreSQL here. 0007 refuses historical running-scope overlaps; 0008 refuses
preexisting job-linked positive epochs. Inspect/refine an approved migration plan
instead of deleting history or bypassing refusal. Live revision was not queried;
readiness may report mismatch until an approved rollout. Compose startup runs
Alembic, so no live backend recreate is authorized by these changes.

Read-only runtime inspection found scheduler exited and backend/db/frontend running
on their original source mounts. The runtime still selects OpenAI/direct scheduler
mode, global paid setting unset (fail-closed), worker OpenAI permission false.
Configured keys were reported only as configured/absent; no values were exposed.
No known generation CLI/probe process was observed. New worktree code is not
deployed into those processes. No real provider calls, live data/schema changes,
scheduler restart, live recreate, push/PR or shared merge occurred.

**Still required:** final atomic cap/coordinator `.03c`, all-writer fencing
`.04b/.04c`, provider pause `.06a`, constrained retries `.06b`, reliable usage `.02d`,
conservative recovery `.05b`, async contracts/keyless roles/queue-default rollout
and bounded development diagnostics `.08c-B`. P1 account/cap configuration and P2
measured timing remain pending; no arbitrary production values were chosen.

## Previous checkpoint — iteration 4


**IMPLEMENTED:** STAB-029, SEC-001, STAB-005, STAB-015.08c-A and .02a.
Five native agents used separate worktrees from the same base. The orchestrator
regenerated the authoritative combined lock, reviewed P3 storage before migration,
serialized backend verification and reconciled documentation. No shared branch
merge, push, deployment or live runtime activation is part of this checkpoint.

| Task | Implemented boundary |
| --- | --- |
| STAB-029 | Swiper 12.2.0; narrow malformed-realIndex guard after reproducing a crash; component/router-adapter, real-Swiper jsdom and isolated advisory regressions. Valid-event synchronization remains unchanged. [Evidence](swiper-security.md). |
| SEC-001 | form-data 4.0.6 plus required hasown 2.0.4; jsdom 24.1.3 and Vue/Router/Vite/Vitest unchanged. [Evidence](form-data-security.md). |
| STAB-005 | Committed validated route owns forecast loading; invalid-route/unmount cleanup rejects late results; same-valid recovery and duplicate-fetch prevention. [Contract](horoscope-route-recovery.md). |
| STAB-015.08c-A | Production paid probe denied in CLI/helper even with SAFE-001=1; missing/invalid mode denied; static listing skips dotenv/SDK. .08c-B bounded audited development diagnostics remains OPEN; real dev transport is not authorized. [Contract](production-probe-policy.md). |
| STAB-015.02a | Additive `0006_generation_ledger`, four empty append-only tables, immutable reservation identity/UTC day and outcome evidence. No writers, backfill, hard cap, fencing or recovery activation. [P3 design and schema](generation-ledger-schema.md). |

**INTEGRATED VERIFICATION — 2026-11-15**, in `/tmp/horoscope-iter4-integration`:

| Check | Result |
| --- | --- |
| STAB-007 mock safety checks and shell syntax | 19 passed; harness/guard/Compose/conftest unchanged from base. |
| Focused probe + SAFE-001 backend selection | 39 passed in 2.76s. |
| Focused ledger schema/migration + existing schema/readiness | 89 passed in 13.60s; a test metadata-copy warning was removed without changing schema/assertions before the full run. |
| Final not_sent/usage consistency + metadata parity selection | 7 passed in 1.24s; positive usage with not_sent rejected, unknown + reliable usage preserved. |
| Full backend, `bash scripts/backend-test.sh` | **750 passed in 76.81s**, no warnings. Includes final metadata fixture, public APIs, publication/paid gates, quota, dedupe and read-only reports. |
| Focused route recovery/read/legacy navigation on combined dependencies | 56 passed, 3 files. |
| Final `npm ci`, `npm ls --all`, typecheck | Passed with allowlisted private npm environment; Node 24.22.2 / npm 11.19.1. No personal registry credentials. |
| Full frontend | **181 passed**, 14 files; no assertion removal. |
| Production build / `npm run poc:check` | Passed / **22 passed**; fixture POC only, no browser capture or live backend. |
| Final npm audit | Exit 1: **0 critical, 9 high, 1 moderate** package entries, down from 2 critical/9 high/1 moderate. Both targeted packages absent. |

Remaining High entries: Vue and @vue/server-renderer 3.5.13 (two entries),
brace-expansion 2.0.1, browserslist 4.24.5, editorconfig 1.0.4, glob 10.4.5,
js-cookie 3.0.5, minimatch 9.0.1/9.0.5 (one entry), ws 8.18.2. Moderate:
postcss-selector-parser 6.1.2. These are affected package entries, not proven
application exploits. Their advisory IDs remain in the historical
[toolchain residual table](frontend-toolchain.md#audit-findings-outside-this-change).

All DB tests used the unchanged STAB-007 disposable PostgreSQL identity, dummy
credentials and fail-on-unexpected-network/process safeguards. Projects
`horoscope-test-e7726162cfe849008c9d63da94f32471`,
`horoscope-test-cf077b9f88a14e77bf110fb9a9e4c0cb`,
`horoscope-test-6b00040412eb4326ad6602d51820b838`,
`horoscope-test-77a9d4cdb22745db9739ce9e9c520490` and
`horoscope-test-09de2a747d7c4d1882d05dcfc62bb931` cleaned their containers/networks;
no volumes are used. Build images/cache may remain. Migration scenarios ran only
inside that disposable database, including rollback-only schema fixtures.

**Runtime/limits:** Scheduler was verified exited; backend/db/frontend stayed
running with original bind mounts. Their live ports still publish on all interfaces
and frontend uses the old Node 20 image; repository loopback/Node 22 defaults have
not been applied. No known generation CLI/probe process was observed. No real
provider request, live DB mutation/migration, secret exposure, scheduler restart,
live Docker recreate, push or PR action was performed. Live DB revision was not
queried. Native browser inventory was empty: real-browser/touch/native keyboard
and combined real-view/Swiper transition ordering remain unverified. Node 22/Alpine
runtime deployment and GitHub CI were not executed by this iteration.

**Remaining accepted architecture:** .02a is storage only; .02b → .02c → .03c,
package-level .03b, full .04a–c fencing, pause/retry policy, recovery, async contracts,
keyless producer migration and queue-default rollout remain open. .08c-A does not
close .08c-B. Production epoch is not invented to activate .02b before .04a.
Deploying packaged migration head 0006 requires a separate approved DB rollout;
readiness will reject a database that still reports 0005. D1–D8 and default paid
deny remain unchanged; the 06:00 product SLO is not paid authorization.

## Previous checkpoint — iteration 3

**ITERATION 3 SCOPE:** STAB-003, STAB-015.03a, .05a, .07a and .07b are implemented
in five task commits on the dedicated integration branch. D1–D8 remain Accepted;
this iteration does not implement their ledger, admission, fencing, pause, recovery
mutations, role isolation or queue-default rollout. No paid activation follows.

**FINAL INTEGRATED VERIFICATION (2026-11-15):** **681 backend tests passed in
30.39s** in `/tmp/horoscope-iter3-verified` via the unchanged STAB-007 disposable
harness, sanitized environment, dummy credentials and network/process guards.
All test projects cleaned up their containers/networks; no test volume is used.
19 mock safety guards passed before DB testing. Focused results below are additional
evidence, not substitutes for this combined run. The first full run exposed fake
model imports leaking Session listeners; mapped-class registration/capture plus
three regressions fixed it, followed by 126 focused tests and this passing full run.
Existing safety/publication assertions were not weakened.

Frontend verification used the isolated Node 22.23.5 worktree: `npm ci`, typecheck,
111 unit tests, build and 22 POC checks passed. All 74 tracked frontend files in
integration match that tested tree byte-for-byte. Audit still exits 1 with the
12 documented non-Vite package entries. Static Compose rendering preserves default
loopback ports, explicit remote override and default-deny paid gates; only the
frontend image changed to Node 22. These are local results, not a GitHub CI pass
or an Alpine/live-browser/deployment test. No live report/provider call, generation,
scheduler restart, container recreate, or development data/schema mutation occurred.

**STAB-015.07b IMPLEMENTED:** A local read-only operations CLI reports backend
business date, today/tomorrow enabled-sign published coverage, a 06:00 Kyiv verdict,
scoped queue depth/oldest creation age and last observed run. Empty enabled metadata
or a non-Kyiv product timezone is a configuration condition. Current full coverage
does not prove historical on-time publication; worker progress and quota causes
remain unknown. The shared reader matches per-job coverage while retaining explicit
historical sign subsets. All 79 operations/cross-report/redaction/CLI regressions
passed in 4.81s; no live report was invoked. See [operations contract](generation-operations.md).

**STAB-015.07a IMPLEMENTED:** Additive `GET /health/ready` returns minimal
200/503 JSON after read-only PostgreSQL connectivity and exact packaged Alembic
head comparison. It is separate from liveness, worker progress and coverage;
matching revision markers are not a full schema audit. Independent connections
have server-statement/connection limits, not a whole DNS/HTTP wall-clock deadline.
33 readiness tests and the then-current 8 shared-reader tests passed (41 total,
2.82s). Compose healthchecks and live services are unchanged. See
[readiness contract and limits](database-readiness.md).

**STAB-015.05a IMPLEMENTED:** A bounded per-job JSON inspection CLI exposes safe
job/run/item/attempt evidence, published/missing coverage and explicit unknowns.
It grants no retry/recovery authority. A shared read service uses a separate
PostgreSQL READ ONLY REPEATABLE READ connection; pending/flushed ORM work stays
caller-owned. Current enabled metadata and an explicit historical job scope remain
distinct, with no static fallback for an empty set. New diagnostic CLI startup
disables implicit dotenv discovery through an explicit config guard compatible
with pinned python-dotenv 1.0.1; normal application startup is unchanged.
86 recovery/CLI/config tests plus 13 shared-reader tests passed in the 244-test
combined run below. See [inspection contract](generation-recovery-inspection.md).

**STAB-015.03a IMPLEMENTED:** Exact active-key PostgreSQL unique conflicts now
produce duplicate reuse or controlled validation errors. Savepoints preserve
caller transaction ownership; `commit=True` uses an independent transaction,
while `commit=False` leaves the outer transaction with its caller. Related pending
or flushed ORM writes receive explicit rejection rather than overwrite/self-lock.
Winner-finalization retry is bounded; unrelated IntegrityErrors still propagate.
Single/batch retry collisions preserve the failed member's history. The six-file
dedupe/admin/worker/CLI selection and recovery/shared-read regressions passed
together: **244 tests in 11.12s** through the disposable harness. See
[exact-key transaction contract](generation-job-deduplication.md); this does not
implement package-level admission, fencing or raw-SQL lock introspection.

**STAB-003 IMPLEMENTED (2026-11-15):** Vite 6.4.6 and Vitest 4.1.12 replace the
affected root/nested Vite versions; Vue, Router, Swiper and application code are
unchanged. Compose now selects Node 22, matching CI's major; no running container
or dependency volume was updated. In the isolated frontend worktree, locked
installation, typecheck, 111 unit tests, build and 22 POC fixture checks passed.
`npm audit` changed from 22 to 12 affected package entries (2 critical, 9 high,
1 moderate remain outside the Vite task). This is not an audit-clean or deployed
security claim. See [toolchain evidence and residual advisories](frontend-toolchain.md).

**STAB-015.01 COMPLETED — ACCEPTED TARGET, NOT FULLY IMPLEMENTED:** The owner explicitly
approved D1–D8 in the [production execution ADR](adr/STAB-015-generation-execution.md),
decision date **2026-11-14**. It is the authoritative target: queue-first production;
hard UTC-day paid API-attempt cap with immutable intent/reservation; package-level
exclusivity; complete fencing and conservative unknown-outcome recovery; at most
one additional proven-safe transient attempt; async production Admin/CLI and a
production paid-probe ban; worker-only credentials; enabled-sign published coverage
by **06:00 Europe/Kyiv**. SAFE-001 remains mandatory and default-deny. D1–D8 do not
need renewed approval; numeric/configuration parameters and rollout remain pending.

The scheduler's code default is still direct; immediate generation is synchronous;
the ledger, atomic package admission, final fencing, cross-run pause and credential
role isolation do not yet exist. Current broad timeout/connection/validation retries
also differ from accepted D5. Documentation acceptance itself changed no runtime.
The [backlog](adr/STAB-015-backlog.md) now closes .01/.03a/.05a/.07a/.07b; .08b is mandatory before
worker-only topology, and admission/accounting/recovery prerequisites precede rollout.

The [five-task handoff](adr/STAB-015-next-iteration.md) preserves the original
pre-implementation findings and records the completed iteration 3 scopes.
The affected Vite lock versions have been replaced; runtime package exploitability
was not tested and installed live packages were not updated. Per-job recovery
inspection (.05a) and aggregate coverage/queue visibility (.07b) remain separate.

**STAB-015.01 VERIFICATION BOUNDARY (2026-11-15):** Source/history/configuration
inspection and documentation consistency checks only. Backend/frontend suites
were not rerun; counts below are historical. Read-only Compose inventory showed
backend/db/frontend running and scheduler exited; no runtime action was performed.
Neither accepted policy nor the 06:00 SLO authorizes paid generation.
Static documentation checks verified 194 relative links, 86 source function/class
coordinates, 12 future entry points and an acyclic prerequisite graph. All 22
previous task IDs are preserved; .02d/.08e/.08f bring the backlog to 25 cards.

**STAB-004 IMPLEMENTED:** Package CLI exits `0` only for a successful run,
including an all-skipped package; failed, partial, interrupted and existing active
runs return `1`. Worker CLI exits `0` for zero jobs or all successful jobs, otherwise
`1`. Existing invocation errors and report formats remain unchanged. Retry-missing
jobs now fail if the lifecycle returns no run while coverage remains incomplete;
complete coverage retains no-work success. No lifecycle states or queue algorithm
changed. See [cli-exit-codes.md](cli-exit-codes.md).

**ITERATION 2 INTEGRATED VERIFICATION (2026-11-14):** 19 database-safety mock
guards passed before test execution; 160 focused CLI/worker/publication/paid-policy
tests passed, followed by **397 full backend tests in 14.80s**. Both backend runs
used the STAB-007 disposable harness, sanitized host environments, dummy credentials,
and fail-on-unexpected-network/process guards; their projects cleaned up. Tests
cover the combined STAB-002 and STAB-004 source with the prior three safety fixes.
These are local checks, not a GitHub CI result.

The historical iteration 2 STAB-015 documentation review checked 14 ADR sections, 22 task cards,
160 relative links across the affected documentation, and integrated CLI source
references. Independent reviews corrected the durable-intent uncertainty boundary
and made monitoring/topology dependencies explicit. The third changeset contains
documentation only, so the 397-test result remains applicable to the final code.

**STAB-002 IMPLEMENTED / STATICALLY VERIFIED:** Development Compose publishes
PostgreSQL `5432`, Flask `8000`, and Vite `5173` on `127.0.0.1` by default.
`DEV_HOST_IP` provides one explicit override for all three host bindings. Unset,
empty, LAN-address and all-interface variants were rendered with sanitized inputs;
all other Compose settings match the baseline. Vite's internal `0.0.0.0` listener
and proxy are unchanged. Live containers were not recreated and retain their old
bindings. See [development-networking.md](development-networking.md).

**SAFE-001 IMPLEMENTED:** `GENERATION_PAID_EXECUTION_ENABLED` permits known paid
execution only for the exact process value `1`; unset, `0` and invalid values deny.
Lifecycle/worker preflight and the final OpenAI adapter boundary enforce it;
standalone probe main/helper are protected too. Local CLI/admin/worker permissions,
production publication policy and existing queue limits remain required. Stub and
fake workflows remain available. Compose maps the gate to backend and scheduler,
defaulting to `0`. This does not deploy the changes or update running environments.
See [paid-execution.md](paid-execution.md).

**INTEGRATED VERIFICATION (2026-11-14):** 126 focused safety/quota/publication/queue
tests passed, followed by **315 full backend tests in 12.88s**, through the STAB-007
workflow. Test projects cleaned up successfully. Compose rendering verified the
unset/zero/invalid/enabled values for both application services without loading
operator dotenv or secrets. Tests used dummy credentials and fake clients or
MockTransport, with a process-wide network/process guard and an internal network.
No paid requests, live-service restart, or development-data writes were performed.

**REMAINING BOUNDARIES:** This is an application execution gate, not account-level
budget control. Direct execution still lacks queue count limits once enabled;
quota classification is per item, not a cross-run circuit breaker. A blocked
claimed job retains existing failed-job/claim accounting and needs explicit review
before retry. CLI failure exit codes are corrected by STAB-004 above; scheduler
reactivation still requires its own controlled operational decision.

**STAB-001 IMPLEMENTED:** Structured `insufficient_quota` is nonretryable per
generation item. The lifecycle owns retries; OpenAI SDK retries are disabled for
both created and injected real clients. Temporary 429, timeout and connection
failures retain retry behavior. No cross-run circuit breaker, scheduler policy,
publication policy or historical data change is included. See
[openai-retries.md](openai-retries.md).

**STAB-001 VERIFIED (2026-11-14):** 47 focused provider/lifecycle tests passed on
the explicit custom disposable target `horoscope_test_stab001`; the full suite
passed **286 tests in 11.59s**. OpenAI SDK `2.37.0` ran against MockTransport with
SDK platform metadata fixed to avoid a host subprocess. Quota/transient attempt
counts and absence of failed-generation publication were verified.

**STAB-007 IMPLEMENTED:** Backend verification now uses a dedicated ephemeral
PostgreSQL cluster and internal network, with no development services, volumes,
secrets, or bind mounts. Host overrides fail before Docker; resolved URL and actual
database identity are checked before migrations and fixture truncation. Dotenv is
disabled in tests, credentials are absent or explicit dummy literals, and unexpected
network/process attempts fail the suite even when caught by application code.
The old development-DB bypass and `KEEP_TEST_DB` workflow are removed. See
[testing-safety.md](testing-safety.md).

**STAB-007 VERIFIED (2026-11-14):** 19 guard-only mock tests passed. The full
backend suite passed **256 tests in 10.26s** through `bash scripts/backend-test.sh`,
with migrations `0001`–`0005` and successful cleanup of its disposable project.
Integration checks corrected psycopg's string DNS port and pytest's informational
`PYTEST_VERSION` handling; both earlier rejected runs cleaned up safely.

**HISTORICAL OPERATIONAL CHECKPOINT (2026-11-14):** The pre-existing scheduler container was stopped before
implementation and was still stopped at that checkpoint. No standalone generation CLI or probe process
was found in the pre-test process inventory. The live source checkout and development
data are outside the test runner. Starting automatic generation is not part of this
milestone.

## Snapshot

**IMPLEMENTED:** The integration baseline includes read-only forecast GET, backend-authoritative business dates, sign-aware archive availability, and canonical forecast-day navigation. The provider audit was followed by a capability-based production publication guard, focused tests, and explicit deployment configuration. Local stub publication remains supported. No existing development forecasts were changed, and no paid generation was run. Test generation uses stub/fake providers in the disposable test database. This change does not establish a production deployment or remediate existing published data.

Read [architecture.md](architecture.md) for source-level flows and [README.md](../README.md) for setup. **VERIFIED/CONFIRMED** means source/test evidence, not permanent design approval. **KNOWN ISSUE**, **RISK**, **OPEN QUESTION**, **HISTORICAL CONTEXT**, and **PROPOSED NEXT STEP** distinguish consequences, uncertainty, history, and proposals.

## Architecture summary

**VERIFIED:** Vue 3 / Vue Router / Vite / Tailwind / Swiper frontend; Flask / SQLAlchemy backend; PostgreSQL 17 in Docker Compose; Alembic migrations `0001`–`0005`; separate APScheduler process. Seven application tables cover signs, prompts, forecasts, runs, items, attempts, and queued jobs. Compose runs development servers, not a production serving configuration.

## Main page

**VERIFIED:** `/` renders `Home.vue`: animated `Starfield`, rotating `ZodiacWheel`, and hover tooltips. Click/Enter/Space selects a sign and navigates to `/horoscope/{sign}/{business-date}`. The wheel pauses on hover. Starfield cleans up timers, animation frames, and listeners on unmount.

Home refreshes `/api/meta` before sign navigation; it does not fetch forecast content or sign metadata itself. `HOME_ZODIACS` derives from shared `constants/zodiac.ts`; names, glyphs, ranges, and ordering are static. Home labels/tooltips are English; forecast/archive views are predominantly Russian. Forecast content is fetched only after navigation. The animation is active application UI included in the production build, with no separate prototype switch; production readiness was not established by this audit.

**HISTORICAL CONTEXT:** The old modal/card and tooltip forecast placeholder were superseded by direct navigation in `a35c50c`. Current Home has no forecast preview. Its static sign list ignores database activation changes. Future sign-metadata integration would require an ownership/ordering decision; that design remains open. The branch is the cumulative integration baseline and includes the backend, archives, generation, and SEO work below, beyond the static Home selector.

## Backend capabilities

| Capability | Audited status |
| --- | --- |
| Forecast persistence, zodiac metadata, migrations | Implemented and used by public routes and generation; seed has 13 signs including Ophiuchus. |
| Lifecycle, attempts/audit, prompt variation, validation | Implemented and wired into controlled generation; covered by backend tests. |
| Stub / OpenAI provider abstraction | Both implemented with shared capability definitions. Factory/Compose default to stub; immediate package CLI defaults to OpenAI. Stub publication is allowed locally and rejected in production. Local-LLM aliases remain unimplemented. |
| Manual admin generation, coverage and audit APIs | Implemented; admin access is disabled by default and requires a bearer token when enabled. |
| Queue, range/backfill, worker, batch status/cancel/retry-failed | Implemented and tested; worker is opt-in. Batch cancellation affects queued jobs only. |
| Scheduled producer / worker | Implemented in `tasks.py`; queue mode and polling worker default off. Legacy direct lifecycle execution remains the default scheduler mode. |
| Public signs metadata, archive, sitemap APIs | Implemented; ArchiveMonth consumes sign-aware month coverage; sign metadata and day/year-wide coverage APIs are not consumed by the frontend. `/api/meta` supplies its business date. |

## Public API

**VERIFIED:** Routes live in `backend/app/routes.py`.

| GET endpoint | Current semantics |
| --- | --- |
| `/api/signs` | Static legacy array of keys; does not filter database activation. |
| `/api/signs/meta` | Active database rows, ordered by `sort_order`; `key`, localized `name`, `sort_order`, `is_active`. Russian fallback for unavailable/unknown locales. |
| `/api/meta` | Uncached `business_date` (`YYYY-MM-DD`) and `timezone`, derived from `APP_TIMEZONE`. |
| `/api/forecast` | Published-only lookup by sign/date/locale/type; `200` with existing aliases, or `404` with `error: forecast_not_published` and `message: Forecast is not published`. Never generates or writes. Existing published stubs still return `200`; invalid input retains `400`. |
| `/api/years` | Published years, optional sign filter, exact locale/type filters; **no active-sign filter**. Empty filtered results fall back to `2024..business-current-year`. |
| `/api/archive/day` | Published forecasts for active signs, ordered by sign order, plus coverage for the requested date. Actual sign keys are present in `forecasts`. |
| `/api/archive/month` | Every calendar day with aggregate `forecast_count`, `missing_count`, `has_full_coverage`. Optional active `sign` adds boolean `has_forecast` per day for that sign/date/locale/type; aggregates remain unchanged. Unknown, empty, or disabled supplied sign returns `400`. |
| `/api/archive/months` | All 12 months with forecast totals, covered/full day totals, and availability/full-month booleans. Aggregate across active signs. |

Archive locale/type are exact database filters, defaulting to `ru`/`daily`, not validated enums. `expected_sign_count` counts enabled `zodiac_signs` at request time; it is not hardcoded to 13. With N active signs, empty/partial/full days have counts 0 / between 0 and N / N; missing is `max(N-count, 0)`. Full coverage requires N > 0. Archive tests verify empty/partial/full summaries, selected-sign published availability, locale/type/status filtering, and dynamic coverage after enabling only one or two signs. Without `sign`, response keys and semantics remain unchanged.

## Zodiac metadata

**VERIFIED against model, migration, seed, API, and client constants:** `zodiac_signs` has `key`, `name_ru`, `name_uk`, `name_en`, `glyph`, `start_month`, `start_day`, `end_month`, `end_day`, `sort_order`, `is_enabled`, `created_at`, and `updated_at`. Bounds are integer month/day components, not full-date columns. Migration `0001` seeds them; later migrations do not change this sign schema.

`ZodiacSign.to_dict()` derives `start`/`end` as `MM-DD` strings, but `/api/signs/meta` does not use that serializer. The public envelope is `locale` + `items`; each item has only `key`, `name`, `sort_order`, and `is_active` (from `is_enabled`). `/api/signs` returns only keys.

Frontend `ZODIACS` has `key`, `nameEn`, `nameRu`, `glyph`, `start`, and `end`; Home derives a formatted `range`. There are no separately named `symbol`, `emoji`, `element`, `date_start`, `date_end`, or `date_range` fields in the current sign schema/shared constants. Unicode `glyph` characters can render in an emoji style; that is not a separate emoji field. Illustrations and constellations are frontend PNG assets; grammatical/genitive labels are local view data, not server fields. See the detailed ownership inventory in [architecture.md](architecture.md).

## Frontend / routing / archive

**VERIFIED:** `main.js` → `App.vue` → router view. `router/index.js` re-exports `index.ts`; there is one active route table. The named views/components from the handoff still exist. Older `pages/`, `store.js`, and card/selector components were removed in earlier history. Task 5 adds only `api/forecast.ts` and `api/archive.ts` for endpoint queries, HTTP handling, and consumed-response parsing. Views retain route and request state. The standalone `utils/businessDate.ts` helper remains unchanged; no generic HTTP layer or store was introduced.

| Route | Behavior |
| --- | --- |
| `/` | Home selector. |
| `/horoscope/:sign/:day` | `HoroscopeView`; contextual 404 for unknown sign or invalid ISO date. |
| `/horoscope` | Redirect to Capricorn and the backend business date after metadata loads. |
| `/archive/:sign/:year/:month` | `ArchiveMonth`; validates sign/year/month and checks loaded nonempty year list; normalizes month padding. |
| `/archive` | Redirect to Capricorn and the backend business year/month after metadata loads. |
| `/archive/:sign/:year/:month/:day` | `ArchiveForecast` compatibility shim: validate explicit sign/date, then `router.replace` to `/horoscope/:sign/:YYYY-MM-DD`, preserving query/hash. Invalid sign/date renders contextual NotFound without fallback/clamping. |
| Catch-all | `NotFound` with `CosmicGate404`; client-rendered 404 UI, not a proven HTTP 404 response. |

`HoroscopeView` is the forecast-content page. It calls `/api/forecast?sign=…&date=…`, accepts legacy/new text aliases, splits paragraphs, manages loading/errors, and uses request IDs to reject superseded responses. The exact unpublished `404` shows “Прогноз ещё не опубликован”; other failures show a generic load error and empty successful content shows an empty message. `ArchiveForecast` no longer fetches metadata, years, or forecasts, nor duplicates forecast rendering/assets. Valid one- or two-digit legacy month/day values are padded for the canonical URL; malformed or impossible explicit dates are rejected.

`ArchiveMonth` requests `/api/years?sign=…&locale=ru&type=daily` when the selected sign changes and one `/api/archive/month?year=…&month=…&sign=…&locale=ru&type=daily` per sign/year/month scope. Only `has_forecast=true` days link directly to `/horoscope/:sign/:date`, whether past, today, or future. Loading/error states disable all days; there is no past-date fallback or per-day fetch. Request IDs and a scope check reject stale month responses; sign-scoped year requests also reject stale responses. Explicit month availability loads without `/api/meta`; business date only supplies today highlighting/linking. Existing year-list validation/fallback behavior remains, and `/api/archive/day` and `/api/archive/months` remain unused by the frontend.

**TASK 5:** The forecast module preserves JSON strings, `text` before `forecast`, non-JSON text, and explicit empty strings. Missing compatible strings now reject instead of masquerading as empty content. Years parsing requires an array and preserves numeric conversion/integer filtering; failure still leaves valid explicit months usable. Month parsing requires a `days` array and returns only real ISO dates with `has_forecast === true`, ignoring malformed entries. Views keep localized messages, request IDs, scope checks, and navigation. No timeout/cancellation or locale/type behavior was redesigned.

Task 5 verification: focused API/view tests **66 passed**; `npm test -- --run` **111 passed across 10 files**; `npm run build` passed; `git diff --check` passed. Existing Vite CJS deprecation warnings remain. No typecheck, lint, backend suite, or live-browser test was run for this extraction.

## Business-date policy

**VERIFIED / IMPLEMENTED:** `backend/app/business_date.py` converts aware instants using the existing `APP_TIMEZONE`, default `Europe/Kyiv`. Flask forecast defaults, fallback years, the ORM forecast-date default, and the scheduler use this helper. Operational timestamps and OpenAI daily limits remain UTC; no queue policy was redesigned.

Only `/horoscope` and `/archive` convenience redirects await `/api/meta` for route resolution. Home refreshes it on sign selection. Home, explicit dated forecast/archive routes, and not-found routes render without metadata. `todayIso` returns null until an authoritative snapshot exists: labels then show absolute dates, forward-day controls are disabled, and archive today links/highlights wait for metadata. Published month availability and explicit legacy-day redirects do not need today. ArchiveForecast no longer has a fallback that invents a date. Plain-date arithmetic/formatting may use UTC as a representation without deriving today from the browser clock.

App starts metadata loading without gating its router view and remains the sole periodic refresh owner: every minute while visible after initialization, and when a tab becomes visible. It removes its timer/listener on unmount. Requests share one pending promise and have a five-second deadline covering fetch and body reading; timeout aborts the request, releases pending state, and allows retry. Late responses cannot overwrite a successful retry. Initial failure shows the existing retry/reload action; only convenience redirects and today-dependent controls wait, while explicit-date content remains usable. Later failures retain the last server snapshot and show an error. **LIMITATION:** a long-lived page can lag a date change until refresh (normally up to one minute, longer while offline); it never substitutes a browser date.

## Generation pipeline

**VERIFIED:** Jobs are orchestration; runs/items/attempts are execution history. Workers claim PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, execute `generation_service`, and record results. Lifecycle generation skips existing **published** rows regardless of source; retry/coverage selection also counts published stubs. Prompts use deterministic variation and keep sign/date in metadata rather than direct creative instructions. Validated results are persisted as published forecasts.

Scheduler target dates use `APP_TIMEZONE` (default `Europe/Kyiv`) and default to today + tomorrow. Direct and queued modes share that policy. SAFE-001 now protects direct scheduler and prompt-probe paid calls as well as the queue/admin/CLI paths. Their local permissions still differ; direct execution does not gain queue count limits when globally enabled. No live OpenAI generation was run.

## Provider policy and publication safety

**CURRENT ENFORCED BEHAVIOR:** `APP_DEPLOYMENT_MODE` accepts `development` (default), `test`, or `production`. In production, publication requires a registered provider that is not development-only, is production-publication capable, and appears in `PRODUCTION_PUBLICATION_PROVIDERS` (default `openai`). Stub is rejected even if listed. Empty/unknown modes and unknown allowlist names fail configuration validation; an empty allowlist denies production publication. Development/test modes retain normal controlled stub publication. Every production generating process must explicitly use production mode; the application cannot infer deployment intent.

Provider definitions and supported names now share a registry; selection defaults remain unchanged. Scheduler/direct factory calls use `HOROSCOPE_PROVIDER` with a stub default; omitted admin/queue-creation provider choices default to stub independently of that environment variable. The package CLI defaults to OpenAI and requires `--allow-openai` and a key. Queued jobs persist provider choice; workers and requeued retries retain it, while model configuration is resolved at execution. Direct retry-missing calls select the caller/current configured provider rather than inheriting a prior run. See the [provider-path audit](architecture.md#current-provider-selection-and-publication-audit) for details.

The shared lifecycle checks authorization before generation and records a failed run on denial. Workers revalidate stored jobs at execution and record a failed job on denial, including retries/backfills. `save_forecast(status="published")` rechecks policy before querying or mutating forecast rows, using the caller's captured execution identity (`publication_provider`), not result source/model fields. Production generic publication without that explicit identity is rejected; generic draft saves remain available. Direct scheduler, admin, and package CLI reach the shared lifecycle; no provider substitution occurs and existing OpenAI gates remain unchanged. Queue creation may still enqueue a stub job; execution in production rejects it. Existing published rows, skip/coverage rules, public reads, archives, and sitemaps are unchanged.

**AGREED PRODUCT/PROVIDER POLICY:** The current seed/presentation set has **13 zodiac signs**, including Ophiuchus. Accepted D8 requires operational expected coverage from enabled database metadata; 13 is not a permanent coverage invariant. Stub is for development, testing, and cost-free local workflows; it is not intended for public production content. OpenAI is the current real generation provider. The new-write guard now enforces production capability/allowlist approval without an OpenAI-only check. Existing published-stub treatment remains a separate decision.

**FUTURE DIRECTION — NOT IMPLEMENTED:** A local-model adapter may use Ollama or an equivalent runtime, with Qwen as one candidate model family. It must be a separate real provider adapter, reuse lifecycle/validation/attempt audit/persistence/publication, and receive explicit production-publication approval. It must not extend or alias stub. No Ollama/Qwen adapter, runtime, dependencies, or configuration are part of this milestone. The [implemented guard](architecture.md#production-publication-guard) accepts approved future real providers through registry capabilities and configuration.

### Local historical evidence (2026-09-29)

Read-only queries against `horoscope-app-db-1`, database `horoscope`, reconfirmed 196 published forecasts: 169 `openai` / `gpt-5.4-mini`, and 27 `stub` / `stub`. Of the stubs, 26 link to successful lifecycle runs; one is unlinked. No cleanup was performed.

| Recorded run / linked job | Target date | Published stub forecasts | Evidence |
| --- | --- | --- | --- |
| Run 1 / job 1 | 2026-05-28 | 13 | Scheduled, successful; job provider and successful item/attempt metadata are `stub`. |
| Run 2 / job 2 | 2026-05-31 | 13 | Scheduled, successful; job provider and successful item/attempt metadata are `stub`. |

Both jobs record `created_by=scheduler:on_start`, `provider=stub`, and `openai_allowed_at_creation=false`, which does not restrict stub execution. This records scheduler-startup job provenance and a persisted stub choice. Stub selection is consistent with development defaults, including the historical scheduler default; records do not establish whether an operator explicitly selected stub or omitted the setting. Historical environment/default-versus-explicit selection is not snapshotted. At that earlier audit checkpoint, the running scheduler had `HOROSCOPE_PROVIDER=openai`, direct mode (`GENERATION_SCHEDULER_USE_QUEUE=0`), worker enabled, and scheduled/worker OpenAI opt-ins off. Those queue gates did not guard direct scheduler calls and cannot explain past choices. The stabilization checkpoint above records the later stopped scheduler and new paid gate.

The unlinked row is forecast 196, Aries, `2026-02-01`. Lack of linkage is compatible with the removed GET fallback but does not prove its origin. All 27 published stubs satisfy the existing-generation skip condition; preventing new production stub publication will not itself replace them or remove their public eligibility.

**SEPARATE METADATA-INTEGRITY FOLLOW-UP (from the audit):** Stored provider/model result metadata is still not fully validated against the selected adapter. The `ProviderResult.provider` default `unknown` remains truthy; an approved adapter could return inaccurate source/model metadata. Authorization now uses the separately captured execution identity, so result metadata cannot authorize a forbidden provider. This task does not repair metadata integrity; no anomalous source was found in the audited inventory.

**SEPARATE HISTORICAL FOLLOW-UP (from the audit):** Job 2 records `created_at=2026-05-31 12:59:57.678527+00`, after its `started_at=2026-05-31 10:02:47.294568+00` and `finished_at=2026-05-31 10:02:47.748358+00`. Its cause remains unknown; it was not investigated or repaired during guard implementation.

## SEO / sitemap

**BOUNDED POC (2026-10-01), NOT PRODUCTION:** [`frontend/poc`](../frontend/poc/README.md)
captures selected routes with the existing production Vue bundle in a real browser.
A disposable loopback harness serves captured HTML with backend-authorized 200/404
and shared-validation legacy 301 behavior. Explicit fixture-only publication/update/
withdrawal and business-date refreshes demonstrate incremental invalidation without
database writes or historical full-site regeneration. The bootstrap retains the
snapshot while the unchanged SPA starts; no SSR framework, application-view changes,
dependencies, language changes, or production serving/automation were introduced.
Artifacts are in memory and require an operator browser to capture. Production
refresh ownership, persistent artifacts, failure UX and freshness policy remain open.

**VERIFIED:** `/api/seo/sitemap/urls`, `/api/seo/sitemap/documents`, `/sitemap.xml`, `/sitemap-index.xml`, and `/sitemaps/<filename>` exist. Published rows for active signs produce `/`, `/horoscope/{sign}/{YYYY-MM-DD}`, and populated `/archive/{sign}/{YYYY}/{MM}` URLs. Archive-day URLs are excluded. Tests cover URL policy, filters, inactive signs, XML, and chunk/index behavior.

**VERIFIED:** Archive-day → horoscope replacement now establishes one client forecast-day URL; the legacy route does not render duplicate forecast content. **NORMAL APPLICATION / DEPLOYMENT PATH — STILL ABSENT:** canonical link tags, robots/noindex policy, server HTTP redirects, and SSR. The separate POC above does not change that path. Sitemap selection and client navigation do not implement these SEO mechanisms. Vite proxies `/api` only; serving Flask's root sitemap endpoints at the public frontend origin is not configured here.

## Verification status

**2026-09-29 provider guard:** Focused backend checks passed: **93 tests in 7.29s**, using the safe disposable-database script with only the pytest selector narrowed. They cover local stub behavior, production capability/allowlist denial, existing-row preservation, scheduler/admin/CLI, stored queue jobs/retries/backfills, a fake future real provider, and final-boundary authorization independent of returned metadata. No frontend source changed, so frontend checks were not repeated. The table below retains earlier archive-milestone results, not new frontend results.

Full guard verification: `bash scripts/backend-test.sh` — **248 passed in 17.82s**, with migrations through `0005` and cleanup of disposable `horoscope_test`. `git diff --check` passed. No paid API calls or development forecast writes were performed. The script managed the DB service as part of normal test setup; no generation scheduler was started by this task.

| Check | Command and actual result |
| --- | --- |
| Backend | `bash scripts/backend-test.sh` — **220 passed in 16.81s**, isolated PostgreSQL database, migrations through `0005`. |
| Frontend tests | From `frontend/`: `npm test -- --run` — **64 passed in 6.08s** (8 files; total Vitest duration). Adds month availability/loading/failure/scope/stale-response cases and strict history-replacing legacy redirects. Existing business-date, convenience navigation, and forecast states remain covered; real Swiper/browser interaction coverage remains limited. |
| Production bundle | From `frontend/`: `npm run build` — **passed in 7.29s**, Vite 6.3.5. |
| Typecheck / vue-tsc | **Historical archive checkpoint:** not configured then. **Current baseline:** `npm run typecheck` runs vue-tsc; not rerun in STAB-015.01. `strict` is not enabled; JS checking is off. |
| Lint | **Not available**; no lint script/configuration. |
| CI | **Historical archive checkpoint:** backend/Compose only. **Current baseline:** `.github/workflows/frontend-tests.yml` also runs `npm ci`, typecheck, unit tests and build on Node 22. POC checks/lint are not in that workflow. No new CI run was inspected in STAB-015.01. |

Focused checks passed before full verification: backend archive tests **19 passed in 3.11s**, using a temporary copy of the safe test script with only its pytest selector changed to `tests/test_api_archive.py`; frontend archive-month, archive-day-navigation, business-date-navigation, and forecast-read files **46 passed in 4.91s**. Build and Vitest emitted the existing Vite CJS Node API deprecation warning. `git diff --check` passed. Real-browser interaction, deployment, and live generation were not exercised; build success does not prove Swiper behavior.

## Known architectural issues

- **RESOLVED IN STAB-004:** Failed, partial and incomplete generation no longer reports process success through the package/worker CLIs. Valid no-work remains successful. Retry-missing run-cap exhaustion with missing content now maps to a failed job; details and verification are recorded above.

- **RESOLVED IN TASK 1:** Public forecast GET no longer creates stubs or exposes draft/non-published rows. `test_api_forecast.py` covers published normal/stub responses, exact missing/draft responses, repeated missing reads with no forecast/audit rows or commits, blocked generation/provider calls, scope filters, and invalid inputs. Old tests requiring GET-created stubs were replaced; year tests now seed data explicitly.
- **HISTORICAL DATA / OPEN QUESTION:** Existing published stubs remain readable and still count toward generation skip rules, archive coverage, and sitemaps. This task does not clean or replace them; their future treatment is undecided.

- **RESOLVED THIS MILESTONE:** Optional `sign` makes month coverage explicit for the selected sign even on partial aggregate days. The original aggregate contract is preserved. `/api/archive/months` remains aggregate-only; `/api/years?sign=aries` still has synthetic fallback years and cannot establish daily availability.
- **RESOLVED IN TASK 2:** Product today has a shared configurable business timezone and a backend authority. Deterministic tests cover winter/summer midnight boundaries, DST transitions, timezone overrides, API defaults, year rollover, model defaults, and scheduler agreement. Operational UTC clocks remain separate intentionally.

- **VERIFIED — README/configuration gaps.** README's old `188 passed in 8.66s` is historical. Its OpenAI per-run limit example is 1; the service default is 2 (scheduler total jobs per tick separately defaults to 1). Compose does not pass through `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, scheduler target-policy/rolling settings, or `GENERATION_OPENAI_MAX_*`; putting them only in root `.env` does not inject them into these containers. README now documents the forecast read contract and `/api/meta`; unrelated configuration gaps were not changed.

## Known frontend issues / risks

- **HISTORICAL TASK-5 ISSUE — RESOLVED BY STAB-005 IN ITERATION 4:** In a reused HoroscopeView, valid → invalid → the same valid route clears content without retriggering its sign/date watcher. Forecast invalid-route and unmount invalidation behavior was deliberately left unchanged by the API extraction.

- **RESOLVED THIS MILESTONE:** ArchiveMonth uses backend-published sign availability; past dates are no longer assumed available.
- **RESOLVED THIS MILESTONE:** ArchiveForecast now uses `validateArchiveForecastRoute`, rejects malformed/impossible explicit dates and unknown signs, and only replaces valid URLs to HoroscopeView. Historical Capricorn fallback/date clamping and independent rendering were removed.
- **RISK / NOT REPRODUCED:** ZodiacCarousel has unchecked `findIndexByKey` results, unconditionally emits on `slideChange`, and uses `slideToLoop` on model changes without suppressing programmatic events. Parent route/model watchers add feedback paths. ArchiveMonth delays mounting until years load. Arrow inactivity/reset symptoms were not reproduced; no runtime race is claimed. Desktop-only arrows and Wheel selection behavior are not classified as defects.
- **CONFIRMED:** ArchiveMonth still duplicates some names/glyphs and adds grammatical labels; HoroscopeView owns forecast illustration/constellation maps. ArchiveForecast's duplicate presentation data was removed with its rendering role. The four-field metadata API is not equivalent to the current frontend presentation model; see the exact field inventory above. Future ownership is an open decision, not a requirement that all such data remain frontend-owned forever.

## Open decisions

**OPEN QUESTION:** Treatment of existing published stubs, SEO tags/server handling, and sign metadata/presentation ownership during Home/archive integration remain unresolved. Sign-aware month availability and strict client archive-day redirects are implemented. Frontend sign choices still come from static constants, while month validation checks database enablement; disabled signs can therefore produce a month-load error. `/api/years` active-sign/fallback semantics remain unchanged.

## Historical branch context

**HISTORICAL CONTEXT (earlier archive milestone):** At the initial audit, `feature/main-page-start` and `feature/frontend-archive-api-integration`, including their origin refs, pointed to `ae31a4f`. The main working branch then advanced to the documentation commit `bbdb9ef` (#19), from which clean `update-frontend` started. At that checkpoint, the local archive-integration branch pointed to `ae31a4f`; the documentation commit added no application functionality, and the archive branch name did not establish completed API integration. The `feature/backend-api-updates` ref was absent after pruning, but checkpoint `b7e92cf` was available. It and `ae31a4f` have identical tree `7ac671d2a18b72a36a8cbb02ee2f037b7e46e317`. PR #18 is the squash result of its seven commits (`8223944` through `b7e92cf`), containing metadata/archive/sitemap work. The older branch's code is fully present; different commit IDs do not imply different content.

Tasks 1 + 2 were committed on `update-frontend` as `1de8f05` (published-only forecast reads) and `5a12652` (business date). The remote implementation branch matched that baseline when this milestone began. The archive milestone is recorded in two local commits: `Add sign-aware archive month availability` and `Use published availability for archive navigation`.

Major stages: initial wheel/cards and horoscope UI (`cc37e94`, `aedb774`, `29c3dac`); archive/router work (`0689db1`, `ebd3f6c`, `4707b3b`); shared zodiac data/direct Home navigation (`7ae0830`, `a35c50c`) and Starfield cleanup (`7439064`); contextual 404/archive polish/assets (`1264231`, `be39b40`, `066f3ee`); Docker/PostgreSQL/persistence/Alembic (`3d40507`); lifecycle/prompts/tests/CI (`8f694e8`); OpenAI/variation (`8d95a72`); admin API (`5a61c21`); queue/batches/scheduler policy (`c618f27`); public backend APIs/SEO (`ae31a4f`). The branch name denotes the cumulative working baseline, not a new isolated Home prototype. `origin/HEAD` still points to the older `origin/master`.

Differences from the supplied handoff: no separate newer archive-integration branch content; backend checkpoint is already incorporated; Home's old modal/placeholder is superseded; archive-day 404 protection was later removed; the database has glyph/range fields although its public metadata endpoint omits them; current test runtime differs. Legacy public reads and mixed product-date clocks were subsequently corrected in Tasks 1 + 2; this milestone implements the month integration and strict archive-day redirect. Other frontend/configuration gaps remain.

## Previous archive milestone and scope boundary

**IMPLEMENTED:** Sign-aware `/api/archive/month` supplements unchanged aggregates; ArchiveMonth uses published availability and canonical day links; legacy day URLs validate and replace to HoroscopeView. Tasks 1 + 2 remain intact: read-only published-only forecast reads, the exact missing `404` payload, published-stub compatibility, and backend-authoritative business date. No shared frontend API layer, Pinia, SEO/SSR/deployment changes, old-stub cleanup, generation/provider/queue redesign, design overhaul, or carousel changes were included. The implementation was reviewed before being recorded in the two local commits above; nothing was pushed.

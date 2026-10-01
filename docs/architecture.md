# Current architecture

This describes `feature/main-page-start` at `34623b2` plus the provider publication guard implemented on 2026-09-29, including the earlier read-only forecast/business-date milestone and sign-aware archive integration. Current behavior, agreed policy, and future direction are separated below. The publication guard is implemented; an Ollama/Qwen adapter is not. See [CURRENT_STATE.md](CURRENT_STATE.md) for the dated snapshot, verification results, and open decisions. [README.md](../README.md) remains the setup reference.

## System overview and entry points

```text
Browser
  -> Vue SPA (main.js -> App.vue -> Vue Router)
       -> /api requests (Vite development proxy)
            -> Flask (run.py -> app.create_app)
                 -> SQLAlchemy -> PostgreSQL

APScheduler (tasks.py, separate Compose service)
  -> direct generation lifecycle                 [default mode]
  -> generation_jobs -> worker -> lifecycle      [opt-in queue mode]

Flask site blueprint -> XML sitemaps               [outside /api]
```

[`docker-compose.yml`](../docker-compose.yml) defines PostgreSQL 17 Alpine, a Python 3.12 backend, a scheduler using the same backend image, and a Node 20 frontend. Backend starts with `alembic upgrade head && python run.py`; scheduler waits for backend health. PostgreSQL data and frontend dependencies use named volumes. The database password comes from a local Docker secret.

The frontend runs Vite's dev server on 5173; Flask runs its development server on 8000 with debug enabled by default. Source directories are bind-mounted. Vite proxies `/api` to `VITE_API_PROXY_TARGET` or localhost:8000. There is no production reverse proxy/static hosting or SPA fallback deployment configuration here. Flask enables CORS for `/api/*` and registers public, admin, and root sitemap blueprints in [`backend/app/__init__.py`](../backend/app/__init__.py).

## Frontend structure and main-page flow

[`router/index.ts`](../frontend/src/router/index.ts) owns the route table; `index.js` is a compatibility re-export. Views are eagerly imported. `Home.vue`, `HoroscopeView.vue`, `ArchiveMonth.vue`, and `NotFound.vue` are content views; `ArchiveForecast.vue` is only a legacy-route validation/redirect shim. Endpoint-specific [`api/forecast.ts`](../frontend/src/api/forecast.ts) and [`api/archive.ts`](../frontend/src/api/archive.ts) own query construction, HTTP handling, and response parsing. The standalone `utils/businessDate.ts` helper still holds the server date context; there is no general HTTP client, shared forecast composable, or central store.

```text
/ -> Home -> Starfield + ZodiacWheel + ZodiacTooltip
              static HOME_ZODIACS <- constants/zodiac.ts
              selection -> /horoscope/{sign}/{business-date}
                             -> HoroscopeView -> GET /api/forecast
```

Home uses static English names, glyphs, date ranges, and a dedicated display order derived from shared `ZODIACS`. It refreshes `/api/meta` before navigation but does not fetch signs or forecasts. Wheel hover pauses rotation and displays a tooltip; click/Enter/Space emits selection. Starfield's canvas animation releases interval/frame/listener resources on unmount. These components are on the normal route and bundled in the production build; there is no separate prototype path. **Historical context:** earlier forecast tooltip placeholders and modal/card navigation were superseded.

`HoroscopeView` renders forecast API text with loading, explicit unpublished (`404 forecast_not_published`), generic error, and empty-content states. `getForecast` returns a published-text or not-published result; other HTTP/network/contract failures reject. JSON strings, string `text` before `forecast`, and non-JSON text remain supported, including explicit empty strings; malformed JSON success shapes reject. The view retains paragraph splitting, request-ID handling, route/model watchers, and asset maps. Invalid-route restoration remains a separate known issue. `ArchiveForecast` no longer fetches or renders forecast content. Zodiac illustrations and constellations live under `frontend/src/assets/zodiac/`; Home itself uses glyphs rather than those forecast hero images.

Routing uses browser history. The navigation guard fetches business metadata only for `/horoscope` and `/archive` convenience redirects. Home, explicit dated routes, and not-found routes resolve without it. `/horoscope` and `/archive` then redirect to Capricorn and backend-supplied current dates, preserving trailing-slash matching and query/hash handling. `HoroscopeView` validates the sign and real ISO day; `ArchiveMonth` validates sign/year/month and a loaded nonempty year list. They render contextual `NotFound` without rewriting invalid routes. ArchiveMonth pads month URLs. `ArchiveForecast` calls `validateArchiveForecastRoute` without fetching a year list or metadata. For a known explicit sign and real calendar date it calls `router.replace` to `/horoscope/:sign/:YYYY-MM-DD`, preserving query/hash. Valid one- or two-digit legacy month/day values are padded; malformed/impossible dates and unknown signs render contextual NotFound without clamping, guessing a date, or choosing Capricorn. Catch-all routes render `NotFound`/`CosmicGate404`. These are client-side UI states, not configured server HTTP status handling.

**VERIFIED / RISK:** `ZodiacCarousel` synchronizes `v-model` with Swiper's `realIndex` and `slideToLoop`; `HoroscopeView` and `ArchiveMonth` also synchronize model and route state. It lacks invalid-index and programmatic-event guards. This is an untested synchronization risk, not a reproduced arrow/reset failure. `YearSwiper` and `MonthSwiper` have separate index checks and synchronization flags.

## PostgreSQL and persistence

Models live in [`backend/app/models.py`](../backend/app/models.py). Alembic uses the Flask-configured database URL through `backend/migrations/env.py`.

| Table | Responsibility |
| --- | --- |
| `zodiac_signs` | Key, translated names, Unicode glyph, four month/day bounds, ordering, enablement, timestamps. |
| `prompt_versions` | Versioned prompt text/schema/model metadata and activation. |
| `forecasts` | Sign/date/locale/type, text/title/payload, status, source/model, publication timestamps, optional prompt/item links. |
| `generation_runs` | Execution for a date/locale/type, status and counters. |
| `generation_items` | Per-sign work, provider metadata, status, result link, payloads/errors. |
| `generation_attempts` | Numbered attempts per item, request/response/raw output, failure details and timestamps. |
| `generation_jobs` | Queue scope, provider, optional signs, priority, batch/dedupe key, attempts, worker lock, linked run. |

Forecast uniqueness is `(sign_key, target_date, locale, forecast_type)`, independent of status or provider. `save_forecast` updates the matching row or inserts one, sets generation/publication timestamps, and commits unless called with `commit=False`. Thus there are not separate stub and OpenAI rows for the same scope.

Migration sequence: `0001_initial_schema` creates persistence/reference tables and seeds 13 signs plus `daily-ru-v1`; `0002_add_generation_attempts` adds attempt history and updates prompts; `0003_prompt_pipeline` and `0004_variation_prompt` update prompt content/schema; `0005_generation_jobs` adds the queue. `app/init_db.py` now exits with Alembic instructions. PostgreSQL is the supported Compose/test path; `Config` still falls back to SQLite when no database settings exist, which is not equivalent to the tested PostgreSQL migration/locking environment.

## Public forecast read: published-only and read-only

```text
ArchiveMonth day link / valid legacy archive-day replacement
  -> /horoscope/{sign}/{ISO-day} -> HoroscopeView
       -> GET /api/forecast?sign=…&date=…[&locale=…&type=…]
            -> routes.forecast -> get_published_forecast
                 published row -> 200, existing serializer/aliases
                 missing or only non-published -> 404 forecast_not_published
```

[`forecast_service.py`](../backend/app/services/forecast_service.py) already provides `get_published_forecast`; the public route now reuses it. Sign validation still uses static `SIGNS`, not active database metadata. An omitted day uses `business_today()`. Locale/type default to `ru`/`daily` and remain exact lookup filters; invalid sign/date input retains its existing `400` behavior.

**VERIFIED:** The missing response is exactly `{"error":"forecast_not_published","message":"Forecast is not published"}`. No public GET invokes a provider, generation lifecycle, queue, or persistence. Successful responses preserve `sign`/`sign_key`, `day`/`date`, `text`/`forecast`, and `model_version`/`model_name`. `HoroscopeView` shows “Прогноз ещё не опубликован” for this response; legacy day routes reach this same page. Regression tests explicitly forbid generation/provider calls and commits and assert repeated missing reads create no forecast or audit rows.

**HISTORICAL CONTEXT / DATA REMAINS:** The previous GET-created published stub path was removed. The legacy standalone `generate_horoscope` helper remains available outside the public route. Existing published stubs are returned normally and still count toward controlled-generation skip rules, archive coverage, and sitemaps; no cleanup or replacement policy changed.

## Controlled generation and provider boundary

```text
Admin / CLI / scheduler producer
  -> generation_jobs
       -> queue worker
            -> generation_service.run_daily_generation
                 -> generation_runs -> publication policy -> generation_items
                      -> existing published forecast? skip
                      -> prompt pipeline -> generation_attempts
                           -> stub OR OpenAI provider
                           -> result validation
                           -> publication policy -> published forecast + audit updates

Admin immediate API / package CLI / legacy scheduler
  -----------------------------------------> same lifecycle (no queue job)
```

[`generation_job_service.py`](../backend/app/services/generation_job_service.py) creates manual, backfill, scheduled, and retry-missing jobs, including inclusive date ranges, dry runs, coverage checks, active duplicate checks, and batches. Claims use descending priority then creation time/id; PostgreSQL uses `FOR UPDATE SKIP LOCKED`. Jobs transition from queued/running to success/partial_failed/failed/cancelled. Stale locks are requeued or failed according to attempt limits. Batch status aggregates jobs; cancel affects queued members, while retry-failed requeues failed/partial-failed members. Running jobs cannot be cancelled by the single-job API.

[`generation_service.py`](../backend/app/services/generation_service.py) closes stale runs, returns an existing running run when its date/locale/type lookup finds one, creates per-sign items, skips published forecasts, retries retryable provider errors, validates output, persists successful forecasts, and finalizes counters/status. Default sign selection queries enabled database signs; `sign_service.get_enabled_sign_keys` retains a static `SIGNS` fallback when that query is empty. This fallback differs from archive coverage's zero-active-sign handling.

[`prompt_service.py`](../backend/app/services/prompt_service.py) loads prompts from the database, validates supported template variables, and builds provider requests. Sign/date select deterministic variation profiles and are retained in audit metadata; they are excluded as literal creative instructions from prompt messages. The seeded prompt is Russian/daily; accepting locale/type parameters is not proof of equivalent generated content for every combination. `forecast_validation_service.py` rejects forbidden zodiac terms/phrases in generated text; lifecycle also rejects empty text.

Providers implement `ProviderRequest` → `ProviderResult` and do not persist forecasts. The stub returns fixed Russian text. `openai_provider.py` calls the Responses API with structured JSON output, parses results/refusals, and maps provider errors for lifecycle retry handling. Tests inject fake clients. Local-LLM provider aliases raise an explicit unimplemented error.

The admin blueprint is `/api/admin`, disabled by default and protected by a bearer token when enabled. Under `/generation`, it exposes coverage; GET/POST runs; retry-missing; run/item attempt detail; GET/POST jobs; backfill; job detail/cancel/retry; and batch status/cancel/retry-failed. Immediate admin generation and queued generation both still exist.

Utilities in `backend/utils/` support immediate packages, queue creation/processing, package reporting, and standalone prompt probing. They are operational commands, not harmless general test commands.

### Current provider selection and publication audit

**CURRENT ENFORCED BEHAVIOR (2026-09-29):** [`providers/factory.py`](../backend/app/providers/factory.py) constructs `stub` and `openai`. It resolves an explicit truthy argument, then `HOROSCOPE_PROVIDER`, then `stub`, and strips/lowercases the name. Unknown names fail; `local`, `local-llm`, and `local_llm` explicitly fail as unimplemented. `ollama` is not registered. There is no fallback from an OpenAI error to stub. The missing-provider default is distinct from error handling.

| Entry point | Selection and defaults | Relevant gates / persistence |
| --- | --- | --- |
| Direct lifecycle `run_daily_generation` | Explicit `provider_name`, otherwise factory environment/default. | Shared publication policy before generation; no universal paid-provider opt-in. |
| Direct scheduler daily and retry-missing | `tasks.py` reads `HOROSCOPE_PROVIDER` at process initialization, default `stub`; Compose also defaults it to `stub`. | Default `GENERATION_SCHEDULER_USE_QUEUE=0` calls lifecycle directly. Queue OpenAI flags do not guard this path. |
| Scheduler queue producer | Same scheduler provider, passed explicitly into scheduled/retry-missing job creation. | OpenAI creation requires `GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI`; provider persists in each job. |
| Queue creation service, ranges/backfills | Omitted provider defaults to `stub`, independently of `HOROSCOPE_PROVIDER`; accepts only `stub`/`openai`. | OpenAI needs `allow_openai`; each range member stores the selected provider. |
| Queue worker / `process_generation_jobs.py` | Uses persisted `job.provider`, not current `HOROSCOPE_PROVIDER`. | Revalidates publication policy at execution. OpenAI still requires worker `allow_openai` and key. Scheduler polling uses `GENERATION_JOB_WORKER_ENABLED` and `GENERATION_JOB_WORKER_ALLOW_OPENAI`; CLI uses `--allow-openai`. OpenAI count limits still apply. |
| Immediate admin runs/retry-missing; admin jobs/backfill | Request `provider`, omitted/empty defaults to `stub`, independently of `HOROSCOPE_PROVIDER`; accepts only `stub`/`openai`. | API enable/token checks; OpenAI additionally needs `ADMIN_API_ALLOW_OPENAI`, request `allow_openai=true`, and key. Queued work also faces worker gates. |
| `generate_forecast_package.py` | `--provider` defaults to **`openai`**, overriding the factory environment default. Explicit `--provider stub` is supported. | OpenAI requires `--allow-openai` and key before immediate lifecycle execution. |
| `create_generation_jobs.py` | `--provider` defaults to `stub`; choices `stub`/`openai`. | OpenAI requires `--allow-openai`; missing key warns at creation, execution still requires it. |
| `openai_prompt_probe.py` | Standalone OpenAI client; model/options use CLI/environment defaults, ignoring `HOROSCOPE_PROVIDER`. | Generating probes require a key but no `--allow-openai` flag; profile listing does not generate. It does not use lifecycle or publish/persist forecasts. |
| Legacy `generate_horoscope` helper | Explicitly selects stub and returns text. | Not called by public GET; does not itself persist. Package reporting is read-only and selects no provider. |

Construction, capabilities, and accepted provider names share [`providers/registry.py`](../backend/app/providers/registry.py); admin, queue, and queue CLI derive supported names from that registry. Selection defaults and OpenAI-specific permission checks remain entry-point-specific. Setting `HOROSCOPE_PROVIDER=openai` does not globally prevent stub selection through admin or queue defaults, but production execution rejects a forbidden selection.

Retries within one item reuse the same provider object. Direct retry-missing starts a new run with the supplied/current provider, not the previous run's choice. Retrying a failed job or batch retains its stored provider; worker retries and retry-missing jobs pass that provider to lifecycle. Backfill members likewise retain their selected provider. Jobs do not pin model configuration: adapter/model resolution occurs at execution, so later configuration/prompt changes may affect a retry's model.

OpenAI reads `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS` (default 30), and `OPENAI_MAX_OUTPUT_TOKENS` (default 500). Effective model selection is nonblank `OPENAI_MODEL`, otherwise a prompt model other than `stub`, otherwise the adapter model (default `gpt-5.4-mini`). Missing credentials fail when generation is attempted; applicable entry points reject them earlier. Invalid numeric settings are rejected by adapter parsing; invalid credentials/model/API requests fail through error handling, with retryable errors retried. None switches to stub. Omitting OpenAI model settings uses defaults, not a provider change.

**PUBLICATION:** [`generation_service.py`](../backend/app/services/generation_service.py) captures the selected adapter identity and checks the shared publication policy before provider calls or item processing. Once authorized, the existing scope check skips published forecasts by `(sign_key, target_date, locale, forecast_type)`, without a source filter. Successful output passes nonempty-text/forbidden-term validation and reaches `save_forecast(status="published", ..., publication_provider=<captured execution identity>)`, which checks the policy again. Publication remains automatic for allowed providers. Stub therefore still publishes locally, but production stub runs fail before generation. Direct and queued execution share this lifecycle.

[`forecast_service.save_forecast`](../backend/app/services/forecast_service.py) authorizes before querying or mutating any forecast row. In production, publication requires the keyword-only `publication_provider` identity from the trusted caller; `source`, `model_version`, and result payloads cannot supply authorization. Missing identity is rejected. Generic non-published saves remain available, and development/test persistence stays compatible. This is a shared service boundary, not a database constraint or protection against arbitrary direct ORM/SQL writes.

**SEPARATE METADATA-INTEGRITY FOLLOW-UP:** Stored metadata still uses `result.provider or provider.name` and `result.model_name or provider.model_name`, without full consistency validation; even `ProviderResult.provider="unknown"` is truthy. The guard does not solve that audit finding: an approved real adapter can still return inaccurate metadata, but such metadata cannot authorize a forbidden execution provider. No existing metadata was repaired.

### Agreed provider policy and future adapter direction

**AGREED POLICY:** The product has exactly 13 zodiac signs, including Ophiuchus; active generation/archive coverage remains derived from database metadata. Stub is a development/test provider for cost-free local workflows and must never supply public production content. OpenAI is currently the implemented real provider. The write guard now requires production approval through capabilities/allowlists rather than a permanent `provider == "openai"` rule. Existing data and public-read eligibility remain separate from this write guard.

**FUTURE, NOT IMPLEMENTED:** An Ollama or equivalent local-model adapter, potentially running a Qwen model, fits under `backend/app/providers/` and the factory. The existing `HoroscopeProvider.generate(ProviderRequest) -> ProviderResult` interface is sufficient for an initial adapter: messages/schema/metadata enter, normalized content/model metadata/audit payloads or classified errors leave. It should reuse the existing lifecycle, validation, attempts/audit, persistence, and publication flow. Keep provider identity (for example `ollama`) separate from the actual model/version/tag (a specific Qwen model); do not use `stub` as its source or alias.

A future adapter needs one registry definition with its factory and capabilities, plus explicit membership in the production publication allowlist after approval. Supported names in admin/jobs/queue CLI derive from that registry, so the core publication guard does not need provider-specific edits. Adapter-specific credentials, model selection, and operational limits still need design during an actual experiment; OpenAI's existing gates and quotas remain OpenAI-specific. The `local*` aliases remain error placeholders. Do not add Ollama transport, dependencies/services/env wiring, or broaden approval before the experiment. Choosing Qwen alone is not approval.

### Production publication guard

**IMPLEMENTED:** [`publication_policy.py`](../backend/app/providers/publication_policy.py) uses trusted execution identity and the shared provider registry. Definitions distinguish `development_only` and `production_publication_capable`; stub is true/false, OpenAI false/true. Registry keys identify providers; model names remain separate metadata. The guard contains no OpenAI-specific authorization branch.

| Setting | Enforced behavior |
| --- | --- |
| `APP_DEPLOYMENT_MODE` | `development` by default to preserve local use; also accepts `test` and `production`. Empty/unknown values fail. Production operators must explicitly select production in every generating process. |
| `PRODUCTION_PUBLICATION_PROVIDERS` | Comma-separated registry names, default `openai` (the currently approved real provider). Empty denies all production publication; unknown names fail configuration validation. Listing stub cannot override its development-only capability. |

Both settings are validated at Flask app creation and revalidated at publication checks; tests explicitly configure test mode. Compose forwards them to backend and scheduler with unset-only defaults, preserving an explicit empty value for validation/deny-all behavior. This minimal implementation differs from the audit's earlier illustrative design: there is no separate generation allowlist, and absent deployment mode defaults to development rather than denying local startup. `FLASK_DEBUG` never selects policy. Startup validation does not itself generate or touch forecast data.

Lifecycle preflight denial records a failed run with a clear non-retryable `PublicationPolicyError` message and no provider attempt. Workers check the current policy against persisted `job.provider` before execution and record a failed job on denial, even when the job was created in development or requeued. A final persistence denial uses existing failed item/attempt handling and cannot overwrite an existing forecast. Immediate admin returns the existing run-status envelope (including failed status/error); scheduler and package CLI report failed runs through their existing reporting. Job creation is not a promise of later publication and can still enqueue a stub job that production workers reject. No provider substitution occurs; existing OpenAI paid-execution gates are unchanged.

Focused tests cover development/test stub success, production denial including a mistakenly allowlisted stub, no insert/overwrite, direct lifecycle/scheduler/admin/CLI paths, persisted scheduled/manual/retry/backfill jobs and requeues, runtime policy changes at persistence, misleading result metadata, approved fake real providers, and invalid configuration. No paid requests are needed.

**UNCHANGED DATA BOUNDARY:** The new-write guard does not change skip/coverage rules or remove existing rows from forecast reads, archives, or sitemaps. All 27 previously audited local published stubs remain untouched. Before a public rollout, explicitly decide data remediation or matching public-read eligibility enforcement across those surfaces. No cleanup, metadata repair, or public-contract change is part of this implementation.

No Ollama implementation or queue redesign was introduced. See [the dated local evidence](CURRENT_STATE.md#local-historical-evidence-2026-09-29) for the existing stub runs and the separate, unchanged historical timestamp follow-up.

## Scheduler flow

[`backend/tasks.py`](../backend/tasks.py) runs APScheduler in a separate process using `APP_TIMEZONE`, default `Europe/Kyiv`.

- Nightly cron defaults to 01:00; startup generation defaults off.
- `scheduler_target_policy_service.py` supports today, tomorrow, today-and-tomorrow (default), and rolling dates. Both direct generation and queued producers use this policy.
- `GENERATION_SCHEDULER_USE_QUEUE=0` runs the lifecycle directly. With it enabled, scheduled tasks only enqueue jobs and skip fully covered dates/active duplicates.
- Retry-missing defaults on at 30-minute intervals, subject to the local 01:00–06:00 window and retry limits; it executes or enqueues according to mode.
- `GENERATION_JOB_WORKER_ENABLED=1` separately registers polling in the same scheduler process. It closes stale jobs and processes up to the configured limit; defaults are off, 60-second interval, and one job per tick. CLI can also process the queue.

## Shared business-date policy

[`backend/app/business_date.py`](../backend/app/business_date.py) is the single conversion helper: an aware instant (default now in UTC) becomes a date/datetime in Flask's `APP_TIMEZONE`, default `Europe/Kyiv`. Naive instants are rejected. The scheduler reuses this configuration and helper; cron/retry/target-date policies are otherwise unchanged. The forecast API's omitted date, `/api/years` fallback year, and ORM `Forecast.target_date` default also use it. Forecast dates stay plain `YYYY-MM-DD`; operational timestamps and OpenAI daily job accounting stay UTC. No database migration is needed for the Python-side default.

```text
APP_TIMEZONE -> business_date.py -> GET /api/meta (no-store)
                                      {business_date, timezone}
                                -> frontend utils/businessDate.ts
                                     -> router/Home navigation
                                     -> defaults, labels, limits, archive today link/highlight
```

`/api/meta` is public, read-only, and exposes only `business_date` and `timezone`. The frontend requests it with `cache: no-store`, validates the response, and shares one reactive snapshot; concurrent requests are deduplicated. A five-second deadline covers fetch and body reading. Timeout aborts the request; success, failure, abort, and timeout release pending state and clear the deadline, allowing later retries. A late response cannot overwrite a newer snapshot. No browser clock is used to derive product today. App starts the initial load without gating its router view and owns the only periodic refresh (every minute while visible after initialization, plus visibility changes), cleaning up its timer/listener on unmount. Home selection and the two convenience redirects request metadata on demand; individual views do not poll.

Initial failure offers retry/reload while explicit-date content, Home, and not-found views remain renderable. Convenience redirects cannot proceed without a successfully refreshed authoritative date. Until a snapshot exists, `todayIso` returns null: date labels remain absolute, forward-day navigation is disabled, and archive today links/highlighting are unavailable. ArchiveMonth published availability and legacy-day validation/redirects do not depend on that snapshot. Refresh failures show an error and retain the last server value; no local-clock fallback is used. Thus an idle page can lag midnight until the next refresh, or longer when offline. Relative labels, limits, and archive today highlighting react to the shared snapshot; month clickability instead depends exclusively on the published-availability response. UTC arithmetic and UTC formatting of plain date strings preserve calendar dates; they do not establish a separate UTC-today policy.

## Public archive read flow

`getArchiveYears` requires an array and preserves numeric conversion/integer filtering. `getArchiveMonthAvailability` requires a `days` array and returns a date set containing only real ISO dates with strict `has_forecast === true`; malformed entries are ignored. These domain functions expose no aggregate fields. ArchiveMonth retains request IDs, scope checks, unmount invalidation, loading/error state, calendar rendering, and navigation. Years failures remain console-only and do not prevent an explicit month from loading. No generic networking infrastructure, timeout, or cancellation changes accompany this extraction.

```text
Vue ArchiveMonth (explicit sign/year/month)
  -> GET /api/years?sign=…&locale=ru&type=daily -> published year query
  -> GET /api/archive/month?year=…&month=…&sign=…&locale=ru&type=daily
       -> published forecasts JOIN enabled zodiac_signs -> PostgreSQL
       -> aggregate daily coverage + selected-sign has_forecast
            -> clickable iff has_forecast=true
            -> /horoscope/{sign}/{ISO-day} -> HoroscopeView

Legacy /archive/{sign}/{year}/{month}/{day}
  -> ArchiveForecast: strict sign/date validation
       valid -> router.replace to /horoscope/{sign}/{ISO-day}
       invalid -> contextual NotFound (no forecast/meta/year fetch)
```

Coverage queries in [`routes.py`](../backend/app/routes.py) match locale and type exactly, count only published forecasts of enabled signs, and derive expected sign count from enabled database rows. Count uses distinct sign keys for grouped days. Month includes empty days; months includes empty months. Daily full coverage requires a positive expected count and enough forecasts; missing count is floored at zero.

Without `sign`, `/api/archive/month` keeps its original envelope and daily fields: `date`, `forecast_count`, `missing_count`, and `has_full_coverage`. With `sign`, the handler first validates an enabled database row, then reuses `_published_archive_counts` with a sign filter for one additional grouped month query. Every day gains a boolean `has_forecast`; aggregate counts still include all enabled signs. Unknown, empty, or disabled supplied signs return the existing Flask `400` error convention. Another sign's forecast, a non-published selected-sign row, or a locale/type mismatch cannot make `has_forecast` true.

ArchiveMonth fetches one month per normalized sign/year/month scope, never one request per day. It clears availability when the scope changes and accepts only `has_forecast === true`. Past, today, and future days follow the same rule. Loading or request failure leaves days unavailable; a minimal status/error message replaces the old past-date guidance. A request ID and captured scope check reject late success/error responses; unmount invalidates pending IDs. Only today highlighting and the today link use business metadata, so metadata failure cannot block explicit-month availability.

The view requests `/api/years` for the selected sign and the same locale/type, refetching on sign changes and ignoring old responses. Existing validation against a loaded nonempty year list remains. The years endpoint has no active-sign join and returns synthetic fallback years when its query is empty; it does not establish day availability. `/api/archive/day` still returns forecast records with sign keys, and `/api/archive/months` remains aggregate-only. These two endpoints are not consumed by the frontend. All archive reads remain read-only.

`test_api_archive.py` covers aggregate compatibility, selected-sign scope/status, enabled-sign validation, and dynamic active counts. Frontend tests cover request scope, loading/errors, past/today/future flags, metadata independence, stale responses, canonical links, and strict legacy replacement without a duplicate history entry. Real Swiper interactions are not covered by these tests.

## Zodiac metadata ownership

**VERIFIED:** The model, migrated schema, default constants, model serializer, public responses, and frontend presentation are distinct layers.

| Layer | Exact fields/data |
| --- | --- |
| `ZodiacSign` / `zodiac_signs` schema | `key`, `name_ru`, `name_uk`, `name_en`, `glyph`, `start_month`, `start_day`, `end_month`, `end_day`, `sort_order`, `is_enabled`, `created_at`, `updated_at`. The last two come from `TimestampMixin`. |
| Migration `0001` seed | 13 rows with localized names, Unicode glyphs, integer month/day bounds, sort order, and enabled state. Later migrations do not change these sign columns. |
| Backend `ZODIAC_SIGNS` defaults | `key`, `name_ru`, `name_uk`, `name_en`, `glyph`, `start`, `end`, `sort_order`; `start`/`end` are `MM-DD` strings. `SIGNS` derives the static key list. These constants do not supply `/api/signs/meta` at request time. |
| `ZodiacSign.to_dict()` | `key`, `nameRu`, `nameUk`, `nameEn`, `glyph`, `start`, `end`, `sortOrder`, `enabled`; bounds become `MM-DD` strings or null. This serializer is not used by `/api/signs/meta`. |
| Public `/api/signs/meta` | Envelope: `locale`, `items`. Each item: `key`, localized `name`, `sort_order`, `is_active`. `is_active` maps from `is_enabled`; only enabled rows are returned, ordered by `sort_order`. |
| Public `/api/signs` | Static array of keys only, derived from `SIGNS`. |
| Frontend `ZODIACS` | `key`, `nameEn`, `nameRu`, `glyph`, `start`, `end`; bounds are `MM-DD` strings. |
| Frontend `HOME_ZODIACS` | Derived `name`, `glyph`, formatted `range`, and `slug`, using a separate Home ordering. |

`glyph` is a text field containing Unicode zodiac characters such as `♈` and `⛎`. There is no separate `symbol` or `emoji` field in this schema or the shared sign constants; font-dependent emoji rendering does not add such metadata. There is also no `element` field.

There are no `date_start`, `date_end`, or `date_range` columns/properties in those definitions. The database's four small-integer month/day bounds describe recurring calendar ranges, without a year. The model serializer's `start`/`end` strings and Home's formatted `range` are different representations; none is a publicly exposed date-range field in `/api/signs/meta`.

Illustrations and constellation art are separate PNG files under `frontend/src/assets/zodiac/illustrations/` and `constellations/`, imported by view maps. They are not glyphs or database image fields. Russian grammatical/genitive labels are local `ArchiveMonth` metadata; the database's translated sign names do not provide those grammatical variants.

Home derives its items from the shared constants; Carousel starts with Capricorn, while Home starts with Aries and positions Ophiuchus differently from backend sort order. ArchiveMonth duplicates names/glyphs and adds genitives; HoroscopeView owns the forecast asset maps. The legacy ArchiveForecast presentation maps were removed with its content-rendering role. **RISK:** separately maintained presentation values can drift from server metadata; no live metadata mismatch was reproduced. The four-field public response cannot replace all current frontend data. Future ownership and API expansion remain **OPEN QUESTIONS**.

## Sitemap policy and frontend SEO

The optional [bounded prerender POC](../frontend/poc/README.md) is separate from the
application/deployment path. It runs the unchanged built SPA in browser iframes,
captures its actual rendered root, and holds selected HTML artifacts in memory.
Its loopback HTTP harness reuses route validators and checks Flask read responses
before serving artifacts; mismatches require explicit recapture, and unpublished
forecasts remain 404. Refresh plans select a forecast and, only for availability
changes, its archive month. Business-date refresh covers Home, archive today links,
and affected relative date labels. A POC bootstrap retains the visible snapshot
while mounting the existing app offscreen; it does not introduce hydration or SSR.
Real-data/browser checks and isolated response-fixture simulations are distinct.
This is disposable evidence, not production routing, cache policy, robots/sitemap
wiring, durable artifact storage, or a publication freshness guarantee.

[`sitemap_service.py`](../backend/app/services/sitemap_service.py) builds entries from published forecasts joined to enabled signs, with locale/type/date filters and include flags. It emits home, each `/horoscope/{sign}/{ISO-day}`, and each populated `/archive/{sign}/{year}/{MM}` pair. It omits archive-day URLs. Forecast `lastmod` uses the first available timestamp in this order: `published_at`, `updated_at`, `generated_at`, `created_at`. Month entries use the latest of those chosen forecast values.

Flask exposes JSON URL/document inspection under `/api/seo/sitemap/urls` and `/api/seo/sitemap/documents`, flat `/sitemap.xml`, `/sitemap-index.xml`, and numbered `/sitemaps/sitemap-N.xml` chunks. Chunk size defaults to 50,000; public origin defaults to localhost:5173. These handlers do not generate forecasts.

**VERIFIED:** Legacy archive-day URLs now validate and replace to the canonical horoscope route in the client, removing the duplicate forecast screen. **STILL ABSENT / OUT OF SCOPE:** Frontend `index.html` has a static title and no canonical/robots tags; views do not add them. There are no server HTTP redirects or SSR changes. Sitemap selection and client history replacement do not supply these SEO mechanisms. Root sitemap requests also require public serving/routing beyond Vite's `/api` proxy, which this repository does not configure.

## Configuration and safety boundaries

`app/config.py` loads dotenv and resolves database settings as `DATABASE_URL` → PostgreSQL fields/secret file → SQLite fallback. Flask admin configuration, scheduler environment reads, provider environment reads, and queue-limit environment reads are separate; not all settings are Flask configuration keys.

Compose explicitly maps selected environment variables; root `.env` is not automatically a container environment file. Current mappings omit `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, `GENERATION_SCHEDULED_TARGET_POLICY`, `GENERATION_SCHEDULED_ROLLING_DAYS`, and `GENERATION_OPENAI_MAX_*`. Code supports these settings, but README/root `.env` examples alone do not wire them into Compose services.

OpenAI job creation and execution have distinct opt-ins. Admin additionally requires its enable/token controls and OpenAI allow flag plus request confirmation. Queue execution requires worker opt-in and an API key; range/per-run/per-UTC-day limits are count-based. Service defaults are seven backfill days, two OpenAI jobs per worker call, and ten started jobs per UTC day. Scheduler's separate total-job limit defaults to one. Legacy direct scheduler execution uses the selected provider directly; the standalone prompt probe can call OpenAI with a configured key. Thus default stub settings and task-level authorization remain essential; queue gates are not universal protection.

**PRODUCTION SAFETY:** The shared capability/allowlist policy above guards controlled publication in explicit production mode, including the legacy direct scheduler. Deployment operators must set `APP_DEPLOYMENT_MODE=production`; leaving it unset intentionally preserves development behavior. Default/omitted provider selection may still choose stub, which production execution rejects. Explicit OpenAI failures never fall back to stub. Existing published data and result metadata integrity remain separate follow-ups; the guard is not a production deployment configuration or a database-wide constraint.

Backend verification uses `bash scripts/backend-test.sh`: it starts the DB service, creates a disposable `horoscope_test`, applies migrations, runs pytest, and drops that test DB. Fixtures truncate mutable tables while retaining seeds and refuse the default development DB unless explicitly overridden. Do not use that override or run raw pytest against development data. The provider guard uses this isolated workflow; the preceding read-only audit inspected development data without changing it.

Frontend has Vitest/jsdom with focused tests for the server date context, navigation/history replacement, strict legacy validation, labels/limits, refresh cleanup, forecast rendering, and sign-scoped month availability including loading/failure and stale-response handling. Broader UI/Swiper coverage remains limited. Vite build transpiles TS but does not type-check it. There is no configured vue-tsc/typecheck/lint check, and TS strict mode is not enabled. GitHub Actions currently runs only backend/Compose checks. Current command results and the limits of verification are recorded in [CURRENT_STATE.md](CURRENT_STATE.md).

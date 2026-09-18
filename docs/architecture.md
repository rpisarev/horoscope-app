# Current architecture

This describes the current source on `update-frontend`, based on `feature/main-page-start` at the documentation checkpoint `bbdb9ef`, plus the implemented read-only forecast and business-date milestone. The branch contains substantially more than Home-page work. Known issues, risks, and historical changes are identified explicitly; this is not a proposed replacement architecture. See [CURRENT_STATE.md](CURRENT_STATE.md) for the dated snapshot, verification results, and open decisions. [README.md](../README.md) remains the setup reference.

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

[`router/index.ts`](../frontend/src/router/index.ts) owns the route table; `index.js` is a compatibility re-export. Views are eagerly imported. `Home.vue`, `HoroscopeView.vue`, `ArchiveMonth.vue`, `ArchiveForecast.vue`, and `NotFound.vue` remain the active screens. A small `utils/businessDate.ts` helper holds the server date context; there is no general API client, shared forecast composable, or central store.

```text
/ -> Home -> Starfield + ZodiacWheel + ZodiacTooltip
              static HOME_ZODIACS <- constants/zodiac.ts
              selection -> /horoscope/{sign}/{business-date}
                             -> HoroscopeView -> GET /api/forecast
```

Home uses static English names, glyphs, date ranges, and a dedicated display order derived from shared `ZODIACS`. It refreshes `/api/meta` before navigation but does not fetch signs or forecasts. Wheel hover pauses rotation and displays a tooltip; click/Enter/Space emits selection. Starfield's canvas animation releases interval/frame/listener resources on unmount. These components are on the normal route and bundled in the production build; there is no separate prototype path. **Historical context:** earlier forecast tooltip placeholders and modal/card navigation were superseded.

Forecast and archive-day screens render API text with loading, explicit unpublished (`404 forecast_not_published`), generic error, and empty-content states. Both contain their own response parsing, paragraph splitting, request-ID handling, route/model watchers, and asset maps. Zodiac illustrations and constellations live under `frontend/src/assets/zodiac/`; Home itself uses glyphs rather than those forecast hero images.

Routing uses browser history. The navigation guard fetches business metadata only for `/horoscope` and `/archive` convenience redirects. Home, explicit dated routes, and not-found routes resolve without it. `/horoscope` and `/archive` then redirect to Capricorn and backend-supplied current dates, preserving trailing-slash matching and query/hash handling. `HoroscopeView` validates the sign and real ISO day; `ArchiveMonth` validates sign/year/month and a loaded nonempty year list. They render contextual `NotFound` without rewriting invalid routes. ArchiveMonth pads month URLs. ArchiveForecast instead falls back to Capricorn, normalizes/clamps numeric dates, and replaces its URL; it no longer calls `validateArchiveForecastRoute`. Its year list feeds the swiper rather than enforcing year membership. Catch-all routes render `NotFound`/`CosmicGate404`. These are client-side UI states, not configured server HTTP status handling.

**VERIFIED / RISK:** `ZodiacCarousel` synchronizes `v-model` with Swiper's `realIndex` and `slideToLoop`; all three detail/archive views also synchronize model and route state. It lacks invalid-index and programmatic-event guards. This is an untested synchronization risk, not a reproduced arrow/reset failure. `YearSwiper` and `MonthSwiper` have separate index checks and synchronization flags.

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
HoroscopeView / ArchiveForecast
  -> GET /api/forecast?sign=…&date=…[&locale=…&type=…]
       -> routes.forecast -> get_published_forecast
            published row -> 200, existing serializer/aliases
            missing or only non-published -> 404 forecast_not_published
```

[`forecast_service.py`](../backend/app/services/forecast_service.py) already provides `get_published_forecast`; the public route now reuses it. Sign validation still uses static `SIGNS`, not active database metadata. An omitted day uses `business_today()`. Locale/type default to `ru`/`daily` and remain exact lookup filters; invalid sign/date input retains its existing `400` behavior.

**VERIFIED:** The missing response is exactly `{"error":"forecast_not_published","message":"Forecast is not published"}`. No public GET invokes a provider, generation lifecycle, queue, or persistence. Successful responses preserve `sign`/`sign_key`, `day`/`date`, `text`/`forecast`, and `model_version`/`model_name`. Both frontend forecast views show “Прогноз ещё не опубликован” for this response. Regression tests explicitly forbid generation/provider calls and commits and assert repeated missing reads create no forecast or audit rows.

**HISTORICAL CONTEXT / DATA REMAINS:** The previous GET-created published stub path was removed. The legacy standalone `generate_horoscope` helper remains available outside the public route. Existing published stubs are returned normally and still count toward controlled-generation skip rules, archive coverage, and sitemaps; no cleanup or replacement policy changed.

## Controlled generation and provider boundary

```text
Admin / CLI / scheduler producer
  -> generation_jobs
       -> queue worker
            -> generation_service.run_daily_generation
                 -> generation_runs -> generation_items
                      -> existing published forecast? skip
                      -> prompt pipeline -> generation_attempts
                           -> stub OR OpenAI provider
                           -> result validation
                           -> published forecast + audit updates

Admin immediate API / package CLI / legacy scheduler
  -----------------------------------------> same lifecycle (no queue job)
```

[`generation_job_service.py`](../backend/app/services/generation_job_service.py) creates manual, backfill, scheduled, and retry-missing jobs, including inclusive date ranges, dry runs, coverage checks, active duplicate checks, and batches. Claims use descending priority then creation time/id; PostgreSQL uses `FOR UPDATE SKIP LOCKED`. Jobs transition from queued/running to success/partial_failed/failed/cancelled. Stale locks are requeued or failed according to attempt limits. Batch status aggregates jobs; cancel affects queued members, while retry-failed requeues failed/partial-failed members. Running jobs cannot be cancelled by the single-job API.

[`generation_service.py`](../backend/app/services/generation_service.py) closes stale runs, returns an existing running run when its date/locale/type lookup finds one, creates per-sign items, skips published forecasts, retries retryable provider errors, validates output, persists successful forecasts, and finalizes counters/status. Default sign selection queries enabled database signs; `sign_service.get_enabled_sign_keys` retains a static `SIGNS` fallback when that query is empty. This fallback differs from archive coverage's zero-active-sign handling.

[`prompt_service.py`](../backend/app/services/prompt_service.py) loads prompts from the database, validates supported template variables, and builds provider requests. Sign/date select deterministic variation profiles and are retained in audit metadata; they are excluded as literal creative instructions from prompt messages. The seeded prompt is Russian/daily; accepting locale/type parameters is not proof of equivalent generated content for every combination. `forecast_validation_service.py` rejects forbidden zodiac terms/phrases in generated text; lifecycle also rejects empty text.

Providers implement `ProviderRequest` → `ProviderResult` and do not persist forecasts. The stub returns fixed Russian text. `openai_provider.py` calls the Responses API with structured JSON output, parses results/refusals, and maps provider errors for lifecycle retry handling. Tests inject fake clients. Local-LLM provider aliases raise an explicit unimplemented error.

The admin blueprint is `/api/admin`, disabled by default and protected by a bearer token when enabled. Under `/generation`, it exposes coverage; GET/POST runs; retry-missing; run/item attempt detail; GET/POST jobs; backfill; job detail/cancel/retry; and batch status/cancel/retry-failed. Immediate admin generation and queued generation both still exist.

Utilities in `backend/utils/` support immediate packages, queue creation/processing, package reporting, and standalone prompt probing. They are operational commands, not harmless general test commands.

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
                                     -> defaults, labels, limits, archive comparisons
```

`/api/meta` is public, read-only, and exposes only `business_date` and `timezone`. The frontend requests it with `cache: no-store`, validates the response, and shares one reactive snapshot; concurrent requests are deduplicated. A five-second deadline covers fetch and body reading. Timeout aborts the request; success, failure, abort, and timeout release pending state and clear the deadline, allowing later retries. A late response cannot overwrite a newer snapshot. No browser clock is used to derive product today. App starts the initial load without gating its router view and owns the only periodic refresh (every minute while visible after initialization, plus visibility changes), cleaning up its timer/listener on unmount. Home selection and the two convenience redirects request metadata on demand; individual views do not poll.

Initial failure offers retry/reload while explicit-date content, Home, and not-found views remain renderable. Convenience redirects cannot proceed without a successfully refreshed authoritative date. Until a snapshot exists, `todayIso` returns null: date labels remain absolute, forward-day navigation is disabled, and archive today links/past-day selection are unavailable. ArchiveForecast defers only its existing invalid-date fallback when that fallback needs today; explicit valid dates load immediately. Refresh failures show an error and retain the last server value; no local-clock fallback is used. Thus an idle page can lag midnight until the next refresh, or longer when offline. Relative labels, limits, and archive comparisons react to the shared snapshot; normal loaded-date availability rules are unchanged. UTC arithmetic and UTC formatting of plain date strings preserve calendar dates; they do not establish a separate UTC-today policy.

## Public archive read flow

```text
Current Vue ArchiveMonth -> GET /api/years -> published year query -> PostgreSQL
                         -> calendar (past business days clickable)
                         -> ArchiveForecast -> published-only GET /api/forecast

Implemented coverage flow, not yet connected to Vue archive UI:
Flask /api/archive/day|month|months
  -> published forecasts JOIN active zodiac metadata -> PostgreSQL
  -> coverage summaries (day also returns actual forecast/sign records)
```

Coverage queries in [`routes.py`](../backend/app/routes.py) match locale and type exactly, count only published forecasts of enabled signs, and derive expected sign count from enabled database rows. Count uses distinct sign keys for grouped days. Month includes empty days; months includes empty months. Daily full coverage requires a positive expected count and enough forecasts; missing count is floored at zero.

There is no `sign` filter or list of present signs in month/months responses. A partial aggregate day therefore cannot establish whether the currently selected sign exists. `/api/archive/day` returns the forecast records needed to answer that question for a single date. `/api/years` can filter by sign, but has no active-sign join and returns synthetic fallback years when its query is empty. It cannot establish daily availability.

Both coverage handlers and the separate forecast handler used by the archive-day UI are now read-only. Tests in `test_api_archive.py` cover published filtering, scope, and empty/partial/full summaries. Frontend tests cover archive-day published/missing/error rendering; calendar availability integration remains out of scope.

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

Home derives its items from the shared constants; Carousel starts with Capricorn, while Home starts with Aries and positions Ophiuchus differently from backend sort order. ArchiveMonth duplicates names/glyphs and adds genitives; ArchiveForecast duplicates names/glyphs/assets; HoroscopeView has another asset map. **RISK:** separately maintained presentation values can drift from server metadata; no live metadata mismatch was reproduced. The four-field public response cannot replace all current frontend data. Future ownership and API expansion remain **OPEN QUESTIONS**.

## Sitemap policy and frontend SEO

[`sitemap_service.py`](../backend/app/services/sitemap_service.py) builds entries from published forecasts joined to enabled signs, with locale/type/date filters and include flags. It emits home, each `/horoscope/{sign}/{ISO-day}`, and each populated `/archive/{sign}/{year}/{MM}` pair. It omits archive-day URLs. Forecast `lastmod` uses the first available timestamp in this order: `published_at`, `updated_at`, `generated_at`, `created_at`. Month entries use the latest of those chosen forecast values.

Flask exposes JSON URL/document inspection under `/api/seo/sitemap/urls` and `/api/seo/sitemap/documents`, flat `/sitemap.xml`, `/sitemap-index.xml`, and numbered `/sitemaps/sitemap-N.xml` chunks. Chunk size defaults to 50,000; public origin defaults to localhost:5173. These handlers do not generate forecasts.

**KNOWN ISSUE:** Frontend `index.html` has a static title and no canonical/robots policy; views do not add one. Archive-day URLs still render content instead of redirecting to the horoscope URL. Sitemap exclusion is therefore only backend URL-selection policy. Root sitemap requests also require public serving/routing beyond Vite's `/api` proxy, which this repository does not configure.

## Configuration and safety boundaries

`app/config.py` loads dotenv and resolves database settings as `DATABASE_URL` → PostgreSQL fields/secret file → SQLite fallback. Flask admin configuration, scheduler environment reads, provider environment reads, and queue-limit environment reads are separate; not all settings are Flask configuration keys.

Compose explicitly maps selected environment variables; root `.env` is not automatically a container environment file. Current mappings omit `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, `GENERATION_SCHEDULED_TARGET_POLICY`, `GENERATION_SCHEDULED_ROLLING_DAYS`, and `GENERATION_OPENAI_MAX_*`. Code supports these settings, but README/root `.env` examples alone do not wire them into Compose services.

OpenAI job creation and execution have distinct opt-ins. Admin additionally requires its enable/token controls and OpenAI allow flag plus request confirmation. Queue execution requires worker opt-in and an API key; range/per-run/per-UTC-day limits are count-based. Service defaults are seven backfill days, two OpenAI jobs per worker call, and ten started jobs per UTC day. Scheduler's separate total-job limit defaults to one. Legacy direct scheduler execution uses the selected provider directly; the standalone prompt probe can call OpenAI with a configured key. Thus default stub settings and task-level authorization remain essential; queue gates are not universal protection.

Backend verification uses `bash scripts/backend-test.sh`: it starts the DB service, creates a disposable `horoscope_test`, applies migrations, runs pytest, and drops that test DB. Fixtures truncate mutable tables while retaining seeds and refuse the default development DB unless explicitly overridden. Do not use that override or run raw pytest against development data. The audit exercised only the isolated test workflow, not generation smoke examples against development data.

Frontend has Vitest/jsdom with focused tests for the server date context, navigation, labels/limits, refresh cleanup, and forecast rendering. Broader UI/Swiper coverage remains limited. Vite build transpiles TS but does not type-check it. There is no configured vue-tsc/typecheck/lint check, and TS strict mode is not enabled. GitHub Actions currently runs only backend/Compose checks. Current command results and the limits of verification are recorded in [CURRENT_STATE.md](CURRENT_STATE.md).

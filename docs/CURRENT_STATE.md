# Current Project State

- State updated: 2026-09-18 (Task 1 + Task 2, including pre-commit cleanup).
- Main working branch: `feature/main-page-start`
- Implementation branch: `update-frontend`
- Implementation baseline HEAD: `bbdb9efc46116a073049fce719a538b33f8143a7` (documentation checkpoint; implementation commits follow on `update-frontend`).
- Origin status at implementation start: the remote `feature/main-page-start` and its tracking ref both match this SHA; no remote `update-frontend` ref was found.

## Snapshot

**VERIFIED:** Implementation started on clean `update-frontend`. This milestone implements read-only, published-only forecast GETs and one backend-authoritative business-date policy. No pushes, merges, schema changes, paid generation, or development-data cleanup were performed. All database verification used the disposable test DB. This describes the verified implementation, not a verified production deployment or its data.

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
| Stub / OpenAI provider abstraction | Both implemented; stub is the code/Compose default. OpenAI tests use fakes, not paid calls. Local-LLM aliases explicitly remain unimplemented. |
| Manual admin generation, coverage and audit APIs | Implemented; admin access is disabled by default and requires a bearer token when enabled. |
| Queue, range/backfill, worker, batch status/cancel/retry-failed | Implemented and tested; worker is opt-in. Batch cancellation affects queued jobs only. |
| Scheduled producer / worker | Implemented in `tasks.py`; queue mode and polling worker default off. Legacy direct lifecycle execution remains the default scheduler mode. |
| Public signs metadata, archive, sitemap APIs | Implemented; frontend does not yet consume sign metadata/archive coverage endpoints; `/api/meta` now supplies its business date. |

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
| `/api/archive/month` | Every calendar day with aggregate `forecast_count`, `missing_count`, `has_full_coverage`; no sign filter or per-sign availability. |
| `/api/archive/months` | All 12 months with forecast totals, covered/full day totals, and availability/full-month booleans. Aggregate across active signs. |

Archive locale/type are exact database filters, defaulting to `ru`/`daily`, not validated enums. `expected_sign_count` counts enabled `zodiac_signs` at request time; it is not hardcoded to 13. With N active signs, empty/partial/full days have counts 0 / between 0 and N / N; missing is `max(N-count, 0)`. Full coverage requires N > 0. Existing archive tests use the 13-sign seed and verify empty, partial, full, draft, locale, and type cases.

## Zodiac metadata

**VERIFIED against model, migration, seed, API, and client constants:** `zodiac_signs` has `key`, `name_ru`, `name_uk`, `name_en`, `glyph`, `start_month`, `start_day`, `end_month`, `end_day`, `sort_order`, `is_enabled`, `created_at`, and `updated_at`. Bounds are integer month/day components, not full-date columns. Migration `0001` seeds them; later migrations do not change this sign schema.

`ZodiacSign.to_dict()` derives `start`/`end` as `MM-DD` strings, but `/api/signs/meta` does not use that serializer. The public envelope is `locale` + `items`; each item has only `key`, `name`, `sort_order`, and `is_active` (from `is_enabled`). `/api/signs` returns only keys.

Frontend `ZODIACS` has `key`, `nameEn`, `nameRu`, `glyph`, `start`, and `end`; Home derives a formatted `range`. There are no separately named `symbol`, `emoji`, `element`, `date_start`, `date_end`, or `date_range` fields in the current sign schema/shared constants. Unicode `glyph` characters can render in an emoji style; that is not a separate emoji field. Illustrations and constellations are frontend PNG assets; grammatical/genitive labels are local view data, not server fields. See the detailed ownership inventory in [architecture.md](architecture.md).

## Frontend / routing / archive

**VERIFIED:** `main.js` → `App.vue` → router view. `router/index.js` re-exports `index.ts`; there is one active route table. The named views/components from the handoff still exist. Older `pages/`, `store.js`, and card/selector components were removed in earlier history. A small `utils/businessDate.ts` helper owns only the server date context; no general API/service/composable layer or store was introduced.

| Route | Behavior |
| --- | --- |
| `/` | Home selector. |
| `/horoscope/:sign/:day` | `HoroscopeView`; contextual 404 for unknown sign or invalid ISO date. |
| `/horoscope` | Redirect to Capricorn and the backend business date after metadata loads. |
| `/archive/:sign/:year/:month` | `ArchiveMonth`; validates sign/year/month and checks loaded nonempty year list; normalizes month padding. |
| `/archive` | Redirect to Capricorn and the backend business year/month after metadata loads. |
| `/archive/:sign/:year/:month/:day` | `ArchiveForecast`; unknown sign becomes Capricorn, numeric dates are normalized/clamped, and URL is replaced. |
| Catch-all | `NotFound` with `CosmicGate404`; client-rendered 404 UI, not a proven HTTP 404 response. |

Both forecast views call `/api/forecast?sign=…&date=…`, accept legacy/new text aliases, split paragraphs, manage loading/errors, and use request IDs to reject responses superseded by another fetch. The exact unpublished `404` shows “Прогноз ещё не опубликован”; other failures show a generic load error and empty successful content shows an empty message. Fetch parsing, state/route synchronization, and illustration/constellation maps are duplicated.

`ArchiveMonth` still calls unfiltered `/api/years` for year choices and uses the shared business-date context. It marks past business days clickable and today/future days non-clickable, independently of stored forecasts. `/api/archive/month`, `/api/archive/day`, and `/api/archive/months` are not integrated anywhere in the frontend.

## Business-date policy

**VERIFIED / IMPLEMENTED:** `backend/app/business_date.py` converts aware instants using the existing `APP_TIMEZONE`, default `Europe/Kyiv`. Flask forecast defaults, fallback years, the ORM forecast-date default, and the scheduler use this helper. Operational timestamps and OpenAI daily limits remain UTC; no queue policy was redesigned.

Only `/horoscope` and `/archive` convenience redirects await `/api/meta` for route resolution. Home refreshes it on sign selection. Home, explicit dated forecast/archive routes, and not-found routes render without metadata. `todayIso` returns null until an authoritative snapshot exists: labels then show absolute dates, forward-day controls are disabled, and archive today links/day selection wait for metadata. The existing invalid-date fallback in ArchiveForecast also waits if it needs today; explicit dates do not. Loaded-date archive availability rules are unchanged. Plain-date arithmetic/formatting may use UTC as a representation without deriving today from the browser clock.

App starts metadata loading without gating its router view and remains the sole periodic refresh owner: every minute while visible after initialization, and when a tab becomes visible. It removes its timer/listener on unmount. Requests share one pending promise and have a five-second deadline covering fetch and body reading; timeout aborts the request, releases pending state, and allows retry. Late responses cannot overwrite a successful retry. Initial failure shows the existing retry/reload action; only convenience redirects and today-dependent controls wait, while explicit-date content remains usable. Later failures retain the last server snapshot and show an error. **LIMITATION:** a long-lived page can lag a date change until refresh (normally up to one minute, longer while offline); it never substitutes a browser date.

## Generation pipeline

**VERIFIED:** Jobs are orchestration; runs/items/attempts are execution history. Workers claim PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, execute `generation_service`, and record results. Lifecycle generation skips existing **published** rows regardless of source; retry/coverage selection also counts published stubs. Prompts use deterministic variation and keep sign/date in metadata rather than direct creative instructions. Validated results are persisted as published forecasts.

Scheduler target dates use `APP_TIMEZONE` (default `Europe/Kyiv`) and default to today + tomorrow. Direct and queued modes share that policy. Queue/admin/CLI paths have explicit OpenAI gates; these are not a universal guard on the legacy direct scheduler or prompt-probe utility. No live OpenAI generation was run.

## SEO / sitemap

**VERIFIED:** `/api/seo/sitemap/urls`, `/api/seo/sitemap/documents`, `/sitemap.xml`, `/sitemap-index.xml`, and `/sitemaps/<filename>` exist. Published rows for active signs produce `/`, `/horoscope/{sign}/{YYYY-MM-DD}`, and populated `/archive/{sign}/{YYYY}/{MM}` URLs. Archive-day URLs are excluded. Tests cover URL policy, filters, inactive signs, XML, and chunk/index behavior.

**KNOWN ISSUE:** The frontend has no canonical link, robots/noindex policy, or archive-day → horoscope redirect. Both day routes render forecast content. Sitemap exclusion alone does not implement canonical handling. Vite proxies `/api` only; serving Flask's root sitemap endpoints at the public frontend origin is not configured here.

## Verification status

| Check | Command and actual result |
| --- | --- |
| Backend | `bash scripts/backend-test.sh` — **207 passed in 15.07s**, isolated PostgreSQL database, migrations through `0005`. |
| Frontend tests | From `frontend/`: `npm test -- --run` — **41 passed in 5.22s** (6 files; total Vitest duration). Coverage includes metadata timeout/abort/retry/deduplication, nonblocking App/explicit-date rendering, isolated Home/redirect navigation, date labels/limits, and forecast published/404/error states; broader interaction coverage remains limited. |
| Production bundle | From `frontend/`: `npm run build` — **passed in 6.97s**, Vite 6.3.5. |
| Typecheck / vue-tsc | **Not available** as a configured repository check; no declared compiler/checker tooling or script. `strict` is not enabled; JS checking is off. |
| Lint | **Not available**; no lint script/configuration. |
| CI | Only `.github/workflows/backend-tests.yml`; backend tests and Compose validation. No frontend test/build/typecheck/lint job. |

Build and Vitest emitted Vite's CJS Node API deprecation warning. Before full verification, the navigation file passed independently (13 tests in 2.32s) and in shuffled order with seed 1729 (13 in 2.26s); the other affected files passed together (26 in 4.39s). The safe backend script was rerun for this cleanup without backend code changes. `git diff --check` passed. Browser interaction, deployment, and live generation were not exercised; build success does not prove route/Swiper behavior.

## Known architectural issues

- **RESOLVED THIS MILESTONE:** Public forecast GET no longer creates stubs or exposes draft/non-published rows. `test_api_forecast.py` covers published normal/stub responses, exact missing/draft responses, repeated missing reads with no forecast/audit rows or commits, blocked generation/provider calls, scope filters, and invalid inputs. Old tests requiring GET-created stubs were replaced; year tests now seed data explicitly.
- **HISTORICAL DATA / OPEN QUESTION:** Existing published stubs remain readable and still count toward generation skip rules, archive coverage, and sitemaps. This task does not clean or replace them; their future treatment is undecided.

- **CONFIRMED — month coverage is not sign-aware.** On `/archive/aries/2026/06`, a partial day's aggregate count cannot identify whether Aries exists. `/api/archive/day` can answer for one day via its forecast list; month/months cannot. `/api/years?sign=aries` only answers at year granularity and has synthetic fallback years.
- **RESOLVED THIS MILESTONE:** Product today has a shared configurable business timezone and a backend authority. Deterministic tests cover winter/summer midnight boundaries, DST transitions, timezone overrides, API defaults, year rollover, model defaults, and scheduler agreement. Operational UTC clocks remain separate intentionally.

- **VERIFIED — README/configuration gaps.** README's old `188 passed in 8.66s` is historical. Its OpenAI per-run limit example is 1; the service default is 2 (scheduler total jobs per tick separately defaults to 1). Compose does not pass through `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, scheduler target-policy/rolling settings, or `GENERATION_OPENAI_MAX_*`; putting them only in root `.env` does not inject them into these containers. README now documents the forecast read contract and `/api/meta`; unrelated configuration gaps were not changed.

## Known frontend issues / risks

- **CONFIRMED:** ArchiveMonth availability is inferred from time, not backend coverage.
- **CONFIRMED:** ArchiveForecast normalizes invalid signs to Capricorn and clamps dates. Commit `066f3ee` removed its contextual 404 guard during the assets redesign; `HoroscopeView` and `ArchiveMonth` still use contextual validation. `validateArchiveForecastRoute` remains in the utility but is unused by that view.
- **RISK / NOT REPRODUCED:** ZodiacCarousel has unchecked `findIndexByKey` results, unconditionally emits on `slideChange`, and uses `slideToLoop` on model changes without suppressing programmatic events. Parent route/model watchers add feedback paths. ArchiveMonth delays mounting until years load. Arrow inactivity/reset symptoms were not reproduced; no runtime race is claimed. Desktop-only arrows and Wheel selection behavior are not classified as defects.
- **CONFIRMED:** Presentation metadata/assets are duplicated in archive/forecast views. The four-field metadata API is not equivalent to the current frontend presentation model; see the exact field inventory above. Future ownership is an open decision, not a requirement that all such data remain frontend-owned forever.

## Open decisions

**OPEN QUESTION:** Treatment of existing published stubs; sign-aware month availability; consistent invalid-route behavior; frontend canonical handling; and sign metadata/presentation ownership during Home/archive integration remain unresolved. The missing forecast contract (`404`) and business-date policy are now implemented; the other decisions were not part of this milestone.

## Historical branch context

**HISTORICAL CONTEXT:** At the initial audit, `feature/main-page-start` and `feature/frontend-archive-api-integration`, including their origin refs, pointed to `ae31a4f`. The main working branch has since advanced to the documentation commit `bbdb9ef` (#19), from which clean `update-frontend` started. The local archive-integration branch still points to `ae31a4f`; the documentation commit adds no application functionality, and the archive branch name does not establish completed API integration. The `feature/backend-api-updates` ref is absent after pruning, but checkpoint `b7e92cf` is available. It and `ae31a4f` have identical tree `7ac671d2a18b72a36a8cbb02ee2f037b7e46e317`. PR #18 is the squash result of its seven commits (`8223944` through `b7e92cf`), containing metadata/archive/sitemap work. The older branch's code is fully present; different commit IDs do not imply different content.

Major stages: initial wheel/cards and horoscope UI (`cc37e94`, `aedb774`, `29c3dac`); archive/router work (`0689db1`, `ebd3f6c`, `4707b3b`); shared zodiac data/direct Home navigation (`7ae0830`, `a35c50c`) and Starfield cleanup (`7439064`); contextual 404/archive polish/assets (`1264231`, `be39b40`, `066f3ee`); Docker/PostgreSQL/persistence/Alembic (`3d40507`); lifecycle/prompts/tests/CI (`8f694e8`); OpenAI/variation (`8d95a72`); admin API (`5a61c21`); queue/batches/scheduler policy (`c618f27`); public backend APIs/SEO (`ae31a4f`). The branch name denotes the cumulative working baseline, not a new isolated Home prototype. `origin/HEAD` still points to the older `origin/master`.

Differences from the supplied handoff: no separate newer archive-integration branch content; backend checkpoint is already incorporated; Home's old modal/placeholder is superseded; archive-day 404 protection was later removed; the database has glyph/range fields although its public metadata endpoint omits them; current test runtime differs. Legacy public reads and mixed product-date clocks were subsequently corrected in this milestone; the archive integration and other frontend gaps remain.

## Completed milestone and scope boundary

**IMPLEMENTED:** Public forecast reads are published-only and free of writes, both forecast views have an explicit unpublished state, and product today comes from backend `APP_TIMEZONE` through `/api/meta`. No archive coverage integration, archive-day canonicalization, general frontend API architecture, SEO/deployment changes, old-stub cleanup, or queue/provider redesign was included. Further implementation requires its own task.

# Current Project State

- State updated: 2026-09-18 (Tasks 3, 4, and 6: sign-aware archive availability and canonical day navigation).
- Main working branch: `feature/main-page-start`
- Implementation branch: `update-frontend`
- Implementation baseline HEAD: `5a126528bfa2821f12ace8fcd5e9ea75e418a493` (Tasks 1 + 2 checkpoint before this archive milestone).
- Origin status at implementation start: remote `update-frontend` matches this HEAD; no local upstream is configured. Remote `feature/main-page-start` remains at `bbdb9efc46116a073049fce719a538b33f8143a7`.

## Snapshot

**VERIFIED:** Implementation started on clean `update-frontend`. This milestone adds sign-aware month availability, connects ArchiveMonth to published backend data, and makes legacy archive-day URLs strict compatibility redirects. The read-only forecast contract and backend-authoritative business-date policy from Tasks 1 + 2 are unchanged. No pushes, merges, schema changes, paid generation, or development-data cleanup were performed. All database verification used the disposable test DB. This describes the verified implementation, not a verified production deployment or its data.

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

**VERIFIED:** `main.js` → `App.vue` → router view. `router/index.js` re-exports `index.ts`; there is one active route table. The named views/components from the handoff still exist. Older `pages/`, `store.js`, and card/selector components were removed in earlier history. A small `utils/businessDate.ts` helper owns only the server date context; no general API/service/composable layer or store was introduced.

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

## Business-date policy

**VERIFIED / IMPLEMENTED:** `backend/app/business_date.py` converts aware instants using the existing `APP_TIMEZONE`, default `Europe/Kyiv`. Flask forecast defaults, fallback years, the ORM forecast-date default, and the scheduler use this helper. Operational timestamps and OpenAI daily limits remain UTC; no queue policy was redesigned.

Only `/horoscope` and `/archive` convenience redirects await `/api/meta` for route resolution. Home refreshes it on sign selection. Home, explicit dated forecast/archive routes, and not-found routes render without metadata. `todayIso` returns null until an authoritative snapshot exists: labels then show absolute dates, forward-day controls are disabled, and archive today links/highlights wait for metadata. Published month availability and explicit legacy-day redirects do not need today. ArchiveForecast no longer has a fallback that invents a date. Plain-date arithmetic/formatting may use UTC as a representation without deriving today from the browser clock.

App starts metadata loading without gating its router view and remains the sole periodic refresh owner: every minute while visible after initialization, and when a tab becomes visible. It removes its timer/listener on unmount. Requests share one pending promise and have a five-second deadline covering fetch and body reading; timeout aborts the request, releases pending state, and allows retry. Late responses cannot overwrite a successful retry. Initial failure shows the existing retry/reload action; only convenience redirects and today-dependent controls wait, while explicit-date content remains usable. Later failures retain the last server snapshot and show an error. **LIMITATION:** a long-lived page can lag a date change until refresh (normally up to one minute, longer while offline); it never substitutes a browser date.

## Generation pipeline

**VERIFIED:** Jobs are orchestration; runs/items/attempts are execution history. Workers claim PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, execute `generation_service`, and record results. Lifecycle generation skips existing **published** rows regardless of source; retry/coverage selection also counts published stubs. Prompts use deterministic variation and keep sign/date in metadata rather than direct creative instructions. Validated results are persisted as published forecasts.

Scheduler target dates use `APP_TIMEZONE` (default `Europe/Kyiv`) and default to today + tomorrow. Direct and queued modes share that policy. Queue/admin/CLI paths have explicit OpenAI gates; these are not a universal guard on the legacy direct scheduler or prompt-probe utility. No live OpenAI generation was run.

## SEO / sitemap

**VERIFIED:** `/api/seo/sitemap/urls`, `/api/seo/sitemap/documents`, `/sitemap.xml`, `/sitemap-index.xml`, and `/sitemaps/<filename>` exist. Published rows for active signs produce `/`, `/horoscope/{sign}/{YYYY-MM-DD}`, and populated `/archive/{sign}/{YYYY}/{MM}` URLs. Archive-day URLs are excluded. Tests cover URL policy, filters, inactive signs, XML, and chunk/index behavior.

**VERIFIED:** Archive-day → horoscope replacement now establishes one client forecast-day URL; the legacy route does not render duplicate forecast content. **OUT OF SCOPE / STILL ABSENT:** canonical link tags, robots/noindex policy, server HTTP redirects, and SSR. Sitemap selection and client navigation do not implement these SEO mechanisms. Vite proxies `/api` only; serving Flask's root sitemap endpoints at the public frontend origin is not configured here.

## Verification status

| Check | Command and actual result |
| --- | --- |
| Backend | `bash scripts/backend-test.sh` — **220 passed in 16.81s**, isolated PostgreSQL database, migrations through `0005`. |
| Frontend tests | From `frontend/`: `npm test -- --run` — **64 passed in 6.08s** (8 files; total Vitest duration). Adds month availability/loading/failure/scope/stale-response cases and strict history-replacing legacy redirects. Existing business-date, convenience navigation, and forecast states remain covered; real Swiper/browser interaction coverage remains limited. |
| Production bundle | From `frontend/`: `npm run build` — **passed in 7.29s**, Vite 6.3.5. |
| Typecheck / vue-tsc | **Not available** as a configured repository check; no declared compiler/checker tooling or script. `strict` is not enabled; JS checking is off. |
| Lint | **Not available**; no lint script/configuration. |
| CI | Only `.github/workflows/backend-tests.yml`; backend tests and Compose validation. No frontend test/build/typecheck/lint job. |

Focused checks passed before full verification: backend archive tests **19 passed in 3.11s**, using a temporary copy of the safe test script with only its pytest selector changed to `tests/test_api_archive.py`; frontend archive-month, archive-day-navigation, business-date-navigation, and forecast-read files **46 passed in 4.91s**. Build and Vitest emitted the existing Vite CJS Node API deprecation warning. `git diff --check` passed. Real-browser interaction, deployment, and live generation were not exercised; build success does not prove Swiper behavior.

## Known architectural issues

- **RESOLVED IN TASK 1:** Public forecast GET no longer creates stubs or exposes draft/non-published rows. `test_api_forecast.py` covers published normal/stub responses, exact missing/draft responses, repeated missing reads with no forecast/audit rows or commits, blocked generation/provider calls, scope filters, and invalid inputs. Old tests requiring GET-created stubs were replaced; year tests now seed data explicitly.
- **HISTORICAL DATA / OPEN QUESTION:** Existing published stubs remain readable and still count toward generation skip rules, archive coverage, and sitemaps. This task does not clean or replace them; their future treatment is undecided.

- **RESOLVED THIS MILESTONE:** Optional `sign` makes month coverage explicit for the selected sign even on partial aggregate days. The original aggregate contract is preserved. `/api/archive/months` remains aggregate-only; `/api/years?sign=aries` still has synthetic fallback years and cannot establish daily availability.
- **RESOLVED IN TASK 2:** Product today has a shared configurable business timezone and a backend authority. Deterministic tests cover winter/summer midnight boundaries, DST transitions, timezone overrides, API defaults, year rollover, model defaults, and scheduler agreement. Operational UTC clocks remain separate intentionally.

- **VERIFIED — README/configuration gaps.** README's old `188 passed in 8.66s` is historical. Its OpenAI per-run limit example is 1; the service default is 2 (scheduler total jobs per tick separately defaults to 1). Compose does not pass through `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, scheduler target-policy/rolling settings, or `GENERATION_OPENAI_MAX_*`; putting them only in root `.env` does not inject them into these containers. README now documents the forecast read contract and `/api/meta`; unrelated configuration gaps were not changed.

## Known frontend issues / risks

- **RESOLVED THIS MILESTONE:** ArchiveMonth uses backend-published sign availability; past dates are no longer assumed available.
- **RESOLVED THIS MILESTONE:** ArchiveForecast now uses `validateArchiveForecastRoute`, rejects malformed/impossible explicit dates and unknown signs, and only replaces valid URLs to HoroscopeView. Historical Capricorn fallback/date clamping and independent rendering were removed.
- **RISK / NOT REPRODUCED:** ZodiacCarousel has unchecked `findIndexByKey` results, unconditionally emits on `slideChange`, and uses `slideToLoop` on model changes without suppressing programmatic events. Parent route/model watchers add feedback paths. ArchiveMonth delays mounting until years load. Arrow inactivity/reset symptoms were not reproduced; no runtime race is claimed. Desktop-only arrows and Wheel selection behavior are not classified as defects.
- **CONFIRMED:** ArchiveMonth still duplicates some names/glyphs and adds grammatical labels; HoroscopeView owns forecast illustration/constellation maps. ArchiveForecast's duplicate presentation data was removed with its rendering role. The four-field metadata API is not equivalent to the current frontend presentation model; see the exact field inventory above. Future ownership is an open decision, not a requirement that all such data remain frontend-owned forever.

## Open decisions

**OPEN QUESTION:** Treatment of existing published stubs, SEO tags/server handling, and sign metadata/presentation ownership during Home/archive integration remain unresolved. Sign-aware month availability and strict client archive-day redirects are implemented. Frontend sign choices still come from static constants, while month validation checks database enablement; disabled signs can therefore produce a month-load error. `/api/years` active-sign/fallback semantics remain unchanged.

## Historical branch context

**HISTORICAL CONTEXT:** At the initial audit, `feature/main-page-start` and `feature/frontend-archive-api-integration`, including their origin refs, pointed to `ae31a4f`. The main working branch has since advanced to the documentation commit `bbdb9ef` (#19), from which clean `update-frontend` started. The local archive-integration branch still points to `ae31a4f`; the documentation commit adds no application functionality, and the archive branch name does not establish completed API integration. The `feature/backend-api-updates` ref is absent after pruning, but checkpoint `b7e92cf` is available. It and `ae31a4f` have identical tree `7ac671d2a18b72a36a8cbb02ee2f037b7e46e317`. PR #18 is the squash result of its seven commits (`8223944` through `b7e92cf`), containing metadata/archive/sitemap work. The older branch's code is fully present; different commit IDs do not imply different content.

Tasks 1 + 2 were committed on `update-frontend` as `1de8f05` (published-only forecast reads) and `5a12652` (business date). The remote implementation branch matched that baseline when this milestone began. The archive milestone is recorded in two local commits: `Add sign-aware archive month availability` and `Use published availability for archive navigation`.

Major stages: initial wheel/cards and horoscope UI (`cc37e94`, `aedb774`, `29c3dac`); archive/router work (`0689db1`, `ebd3f6c`, `4707b3b`); shared zodiac data/direct Home navigation (`7ae0830`, `a35c50c`) and Starfield cleanup (`7439064`); contextual 404/archive polish/assets (`1264231`, `be39b40`, `066f3ee`); Docker/PostgreSQL/persistence/Alembic (`3d40507`); lifecycle/prompts/tests/CI (`8f694e8`); OpenAI/variation (`8d95a72`); admin API (`5a61c21`); queue/batches/scheduler policy (`c618f27`); public backend APIs/SEO (`ae31a4f`). The branch name denotes the cumulative working baseline, not a new isolated Home prototype. `origin/HEAD` still points to the older `origin/master`.

Differences from the supplied handoff: no separate newer archive-integration branch content; backend checkpoint is already incorporated; Home's old modal/placeholder is superseded; archive-day 404 protection was later removed; the database has glyph/range fields although its public metadata endpoint omits them; current test runtime differs. Legacy public reads and mixed product-date clocks were subsequently corrected in Tasks 1 + 2; this milestone implements the month integration and strict archive-day redirect. Other frontend/configuration gaps remain.

## Completed milestone and scope boundary

**IMPLEMENTED:** Sign-aware `/api/archive/month` supplements unchanged aggregates; ArchiveMonth uses published availability and canonical day links; legacy day URLs validate and replace to HoroscopeView. Tasks 1 + 2 remain intact: read-only published-only forecast reads, the exact missing `404` payload, published-stub compatibility, and backend-authoritative business date. No shared frontend API layer, Pinia, SEO/SSR/deployment changes, old-stub cleanup, generation/provider/queue redesign, design overhaul, or carousel changes were included. The implementation was reviewed before being recorded in the two local commits above; nothing was pushed.

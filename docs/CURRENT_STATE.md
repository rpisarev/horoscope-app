# Current Project State

- Audit date: 2026-09-17
- Main working branch: `feature/main-page-start`
- HEAD: `ae31a4fae4687eb94962f4211c3a9317862fc8ae`
- Origin status: synchronized at audit time (`origin/feature/main-page-start` has the same SHA; 0 ahead / 0 behind).

## Snapshot

**VERIFIED:** The audit began on clean `add-docs` at this same HEAD and switched safely to `feature/main-page-start`. The tree was clean before documentation changes and after the interruption. `git fetch --prune` completed. No application changes, commits, merges, or pushes were made. This snapshot describes the audited code, not a verified production deployment or its data.

Read [architecture.md](architecture.md) for source-level flows and [README.md](../README.md) for setup. **VERIFIED/CONFIRMED** means source/test evidence, not permanent design approval. **KNOWN ISSUE**, **RISK**, **OPEN QUESTION**, **HISTORICAL CONTEXT**, and **PROPOSED NEXT STEP** distinguish consequences, uncertainty, history, and proposals.

## Architecture summary

**VERIFIED:** Vue 3 / Vue Router / Vite / Tailwind / Swiper frontend; Flask / SQLAlchemy backend; PostgreSQL 17 in Docker Compose; Alembic migrations `0001`–`0005`; separate APScheduler process. Seven application tables cover signs, prompts, forecasts, runs, items, attempts, and queued jobs. Compose runs development servers, not a production serving configuration.

## Main page

**VERIFIED:** `/` renders `Home.vue`: animated `Starfield`, rotating `ZodiacWheel`, and hover tooltips. Click/Enter/Space selects a sign and navigates to `/horoscope/{sign}/{UTC-today}`. The wheel pauses on hover. Starfield cleans up timers, animation frames, and listeners on unmount.

Home makes no API calls. `HOME_ZODIACS` derives from shared `constants/zodiac.ts`; names, glyphs, ranges, and ordering are static. Home labels/tooltips are English; forecast/archive views are predominantly Russian. Forecast content is fetched only after navigation. The animation is active application UI included in the production build, with no separate prototype switch; production readiness was not established by this audit.

**HISTORICAL CONTEXT:** The old modal/card and tooltip forecast placeholder were superseded by direct navigation in `a35c50c`. Current Home has no forecast preview. Its static sign list ignores database activation changes. Future API integration would require an ownership/ordering decision; no integration design is approved here. The branch is the cumulative integration baseline and includes the backend, archives, generation, and SEO work below, beyond the static Home selector.

## Backend capabilities

| Capability | Audited status |
| --- | --- |
| Forecast persistence, zodiac metadata, migrations | Implemented and used by public routes and generation; seed has 13 signs including Ophiuchus. |
| Lifecycle, attempts/audit, prompt variation, validation | Implemented and wired into controlled generation; covered by backend tests. |
| Stub / OpenAI provider abstraction | Both implemented; stub is the code/Compose default. OpenAI tests use fakes, not paid calls. Local-LLM aliases explicitly remain unimplemented. |
| Manual admin generation, coverage and audit APIs | Implemented; admin access is disabled by default and requires a bearer token when enabled. |
| Queue, range/backfill, worker, batch status/cancel/retry-failed | Implemented and tested; worker is opt-in. Batch cancellation affects queued jobs only. |
| Scheduled producer / worker | Implemented in `tasks.py`; queue mode and polling worker default off. Legacy direct lifecycle execution remains the default scheduler mode. |
| Public signs metadata, archive, sitemap APIs | Implemented; frontend does not yet consume the metadata/archive coverage endpoints. |

## Public API

**VERIFIED:** Routes live in `backend/app/routes.py`.

| GET endpoint | Current semantics |
| --- | --- |
| `/api/signs` | Static legacy array of keys; does not filter database activation. |
| `/api/signs/meta` | Active database rows, ordered by `sort_order`; `key`, localized `name`, `sort_order`, `is_active`. Russian fallback for unavailable/unknown locales. |
| `/api/forecast` | Looks up sign/date/locale/type without a status filter; creates a published stub if no row exists. See known issues. |
| `/api/years` | Published years, optional sign filter, exact locale/type filters; **no active-sign filter**. Empty filtered results fall back to `2024..server-current-year`. |
| `/api/archive/day` | Published forecasts for active signs, ordered by sign order, plus coverage for the requested date. Actual sign keys are present in `forecasts`. |
| `/api/archive/month` | Every calendar day with aggregate `forecast_count`, `missing_count`, `has_full_coverage`; no sign filter or per-sign availability. |
| `/api/archive/months` | All 12 months with forecast totals, covered/full day totals, and availability/full-month booleans. Aggregate across active signs. |

Archive locale/type are exact database filters, defaulting to `ru`/`daily`, not validated enums. `expected_sign_count` counts enabled `zodiac_signs` at request time; it is not hardcoded to 13. With N active signs, empty/partial/full days have counts 0 / between 0 and N / N; missing is `max(N-count, 0)`. Full coverage requires N > 0. Existing archive tests use the 13-sign seed and verify empty, partial, full, draft, locale, and type cases.

## Zodiac metadata

**VERIFIED against model, migration, seed, API, and client constants:** `zodiac_signs` has `key`, `name_ru`, `name_uk`, `name_en`, `glyph`, `start_month`, `start_day`, `end_month`, `end_day`, `sort_order`, `is_enabled`, `created_at`, and `updated_at`. Bounds are integer month/day components, not full-date columns. Migration `0001` seeds them; later migrations do not change this sign schema.

`ZodiacSign.to_dict()` derives `start`/`end` as `MM-DD` strings, but `/api/signs/meta` does not use that serializer. The public envelope is `locale` + `items`; each item has only `key`, `name`, `sort_order`, and `is_active` (from `is_enabled`). `/api/signs` returns only keys.

Frontend `ZODIACS` has `key`, `nameEn`, `nameRu`, `glyph`, `start`, and `end`; Home derives a formatted `range`. There are no separately named `symbol`, `emoji`, `element`, `date_start`, `date_end`, or `date_range` fields in the current sign schema/shared constants. Unicode `glyph` characters can render in an emoji style; that is not a separate emoji field. Illustrations and constellations are frontend PNG assets; grammatical/genitive labels are local view data, not server fields. See the detailed ownership inventory in [architecture.md](architecture.md).

## Frontend / routing / archive

**VERIFIED:** `main.js` → `App.vue` → router view. `router/index.js` re-exports `index.ts`; there is one active route table. The named views/components from the handoff still exist. Older `pages/`, `store.js`, and card/selector components were removed in earlier history. No shared API/service/composable layer currently exists.

| Route | Behavior |
| --- | --- |
| `/` | Home selector. |
| `/horoscope/:sign/:day` | `HoroscopeView`; contextual 404 for unknown sign or invalid ISO date. |
| `/horoscope` | Redirect to Capricorn and UTC today. |
| `/archive/:sign/:year/:month` | `ArchiveMonth`; validates sign/year/month and checks loaded nonempty year list; normalizes month padding. |
| `/archive` | Redirect to Capricorn and UTC current year/month. |
| `/archive/:sign/:year/:month/:day` | `ArchiveForecast`; unknown sign becomes Capricorn, numeric dates are normalized/clamped, and URL is replaced. |
| Catch-all | `NotFound` with `CosmicGate404`; client-rendered 404 UI, not a proven HTTP 404 response. |

Both forecast views call `/api/forecast?sign=…&date=…`, accept legacy/new text aliases, split paragraphs, manage loading/errors, and use request IDs to reject responses superseded by another fetch. Non-OK responses show a generic load error; empty successful content shows an empty message. There is no distinct unpublished/missing state. Fetch parsing, state/route synchronization, and illustration/constellation maps are duplicated.

`ArchiveMonth` calls only unfiltered `/api/years`. It marks browser-local past days clickable and today/future days non-clickable, independently of stored forecasts. `/api/archive/month`, `/api/archive/day`, and `/api/archive/months` are not integrated anywhere in the frontend.

## Generation pipeline

**VERIFIED:** Jobs are orchestration; runs/items/attempts are execution history. Workers claim PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, execute `generation_service`, and record results. Lifecycle generation skips existing **published** rows regardless of source; retry/coverage selection also counts published stubs. Prompts use deterministic variation and keep sign/date in metadata rather than direct creative instructions. Validated results are persisted as published forecasts.

Scheduler target dates use `APP_TIMEZONE` (default `Europe/Kyiv`) and default to today + tomorrow. Direct and queued modes share that policy. Queue/admin/CLI paths have explicit OpenAI gates; these are not a universal guard on the legacy direct scheduler or prompt-probe utility. No live OpenAI generation was run.

## SEO / sitemap

**VERIFIED:** `/api/seo/sitemap/urls`, `/api/seo/sitemap/documents`, `/sitemap.xml`, `/sitemap-index.xml`, and `/sitemaps/<filename>` exist. Published rows for active signs produce `/`, `/horoscope/{sign}/{YYYY-MM-DD}`, and populated `/archive/{sign}/{YYYY}/{MM}` URLs. Archive-day URLs are excluded. Tests cover URL policy, filters, inactive signs, XML, and chunk/index behavior.

**KNOWN ISSUE:** The frontend has no canonical link, robots/noindex policy, or archive-day → horoscope redirect. Both day routes render forecast content. Sitemap exclusion alone does not implement canonical handling. Vite proxies `/api` only; serving Flask's root sitemap endpoints at the public frontend origin is not configured here.

## Verification status

| Check | Command and actual result |
| --- | --- |
| Backend | `bash scripts/backend-test.sh` — **188 passed in 12.04s**, isolated PostgreSQL database, migrations through `0005`. |
| Frontend tests | From `frontend/`: `npm test -- --run` — **1 passed in 2.65s** (1 file; total Vitest duration). Only DaySlider's “Сегодня” label is covered; coverage is very limited. |
| Production bundle | From `frontend/`: `npm run build` — **passed in 5.01s**, Vite 6.3.5. |
| Typecheck / vue-tsc | **Not available** as a configured repository check; no declared compiler/checker tooling or script. `strict` is not enabled; JS checking is off. |
| Lint | **Not available**; no lint script/configuration. |
| CI | Only `.github/workflows/backend-tests.yml`; backend tests and Compose validation. No frontend test/build/typecheck/lint job. |

Build and Vitest emitted Vite's CJS Node API deprecation warning. No application code changed afterward; successful checks were not repeated. Browser interaction, deployment, and live generation were not exercised; build success does not prove route/Swiper behavior.

## Known architectural issues

- **CONFIRMED — forecast GET writes and bypasses lifecycle.** `routes.forecast` calls unfiltered `forecast_service.get_forecast`. On no row, `generate_horoscope` forces the stub provider, then `save_forecast` commits `status="published"`, `source="stub"`, `model_name="stub"`, and publication time. No job/run/item/attempt is created and lifecycle validation is bypassed. `test_forecast_endpoint_creates_published_stub_forecast` and the idempotence test explicitly assert this behavior; they do not establish it as permanent design. `test_run_daily_generation_skips_existing_published_forecast` verifies the later skip rule; the consequence for GET-created stubs follows directly. Home → forecast navigation can therefore publish placeholders without the controlled pipeline's validation/audit trail, and that pipeline subsequently treats them as completed publications. They also count toward archive and sitemap coverage.
- **CONFIRMED — public forecast lookup is not published-only.** An existing draft/non-published row is returned unchanged by that query, rather than replaced or hidden. This follows from code; `test_api_forecast.py` has no draft-exclusion case. No development data was modified to probe it.
- **CONFIRMED — month coverage is not sign-aware.** On `/archive/aries/2026/06`, a partial day's aggregate count cannot identify whether Aries exists. `/api/archive/day` can answer for one day via its forecast list; month/months cannot. `/api/years?sign=aries` only answers at year granularity and has synthetic fallback years.
- **CONFIRMED — mixed calendar clocks.** Home, router redirects, and `todayIso`/`isoAddDays` use UTC; Day.js archive comparisons and some view fallbacks use browser-local dates. ISO dates are also formatted with browser-local `toLocaleDateString`. Backend public defaults use server-local `date.today()`, scheduler uses `APP_TIMEZONE`, and OpenAI daily job limits use UTC. **RISK:** these clocks can disagree near midnight; no shared business-date policy is implemented. `maxForwardDate` is computed once at module load.
- **VERIFIED — README/configuration gaps.** README's old `188 passed in 8.66s` is historical. Its OpenAI per-run limit example is 1; the service default is 2 (scheduler total jobs per tick separately defaults to 1). Compose does not pass through `PUBLIC_SITE_URL`, `SITEMAP_CHUNK_SIZE`, scheduler target-policy/rolling settings, or `GENERATION_OPENAI_MAX_*`; putting them only in root `.env` does not inject them into these containers. README omits the public-read issues above. It was left unchanged rather than rewritten during this audit.

## Known frontend issues / risks

- **CONFIRMED:** ArchiveMonth availability is inferred from time, not backend coverage.
- **CONFIRMED:** ArchiveForecast normalizes invalid signs to Capricorn and clamps dates. Commit `066f3ee` removed its contextual 404 guard during the assets redesign; `HoroscopeView` and `ArchiveMonth` still use contextual validation. `validateArchiveForecastRoute` remains in the utility but is unused by that view.
- **RISK / NOT REPRODUCED:** ZodiacCarousel has unchecked `findIndexByKey` results, unconditionally emits on `slideChange`, and uses `slideToLoop` on model changes without suppressing programmatic events. Parent route/model watchers add feedback paths. ArchiveMonth delays mounting until years load. Arrow inactivity/reset symptoms were not reproduced; no runtime race is claimed. Desktop-only arrows and Wheel selection behavior are not classified as defects.
- **CONFIRMED:** Presentation metadata/assets are duplicated in archive/forecast views. The four-field metadata API is not equivalent to the current frontend presentation model; see the exact field inventory above. Future ownership is an open decision, not a requirement that all such data remain frontend-owned forever.

## Open decisions

**OPEN QUESTION:** Agree the missing/unpublished forecast response and frontend empty state before changing the tested read contract; decide how existing published stubs should be treated. Also unresolved: sign-aware month availability contract; consistent invalid-route behavior; shared business date; frontend canonical handling; and API metadata/presentation ownership during Home/archive integration. None is approved or implemented by this audit.

## Historical branch context

**VERIFIED BRANCH STATE / HISTORICAL CONTEXT:** `feature/main-page-start` and `feature/frontend-archive-api-integration`, including their origin refs, currently point to `ae31a4f`. There is no content difference between these branch tips; the archive branch name does not establish completed API integration. The `feature/backend-api-updates` ref is absent after pruning, but checkpoint `b7e92cf` is available. It and `ae31a4f` have identical tree `7ac671d2a18b72a36a8cbb02ee2f037b7e46e317`. PR #18 is the squash result of its seven commits (`8223944` through `b7e92cf`), containing metadata/archive/sitemap work. The older branch's code is fully present; different commit IDs do not imply different content.

Major stages: initial wheel/cards and horoscope UI (`cc37e94`, `aedb774`, `29c3dac`); archive/router work (`0689db1`, `ebd3f6c`, `4707b3b`); shared zodiac data/direct Home navigation (`7ae0830`, `a35c50c`) and Starfield cleanup (`7439064`); contextual 404/archive polish/assets (`1264231`, `be39b40`, `066f3ee`); Docker/PostgreSQL/persistence/Alembic (`3d40507`); lifecycle/prompts/tests/CI (`8f694e8`); OpenAI/variation (`8d95a72`); admin API (`5a61c21`); queue/batches/scheduler policy (`c618f27`); public backend APIs/SEO (`ae31a4f`). The branch name denotes the cumulative working baseline, not a new isolated Home prototype. `origin/HEAD` still points to the older `origin/master`.

Differences from the supplied handoff: no separate newer archive-integration branch content; backend checkpoint is already incorporated; Home's old modal/placeholder is superseded; archive-day 404 protection was later removed; the database has glyph/range fields although its public metadata endpoint omits them; current test runtime differs. Confirmed legacy reads and archive/frontend gaps remain unresolved.

## Recommended next task

**PROPOSED NEXT STEP — one implementation task, not approved by this audit:** Make the Home → HoroscopeView forecast read published-only and free of writes, with an explicit “not yet published” state and focused regression coverage. Agree the missing-response contract, preserve existing success aliases, and account for ArchiveForecast's shared endpoint. This addresses a database mutation triggered by the current main-page navigation without refactoring Home or implementing archive coverage.

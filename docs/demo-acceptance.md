# MVP-A05 acceptance — 2026-11-15

**READY WITH MANUAL CHECKS.** The implemented private demo passed the automated
checks below. Physical-phone touch/Safari and public-domain TLS on the later
approved host remain manual rollout checks. No public deployment was performed.
This is a read-only demonstration, with no nightly generation or 06:00 SLO.

## Tested build and data

Base: `33974d99e3e46bfe878f7e74e98f9d0f425e3797` (merged PR #27).
Integration: `integration/mvp-demo-1`, with the final image wiring/guard changes.
The original `feature/mvp-000` checkout stayed unchanged.

| Component | Tested identity |
| --- | --- |
| Backend image | `sha256:3807b0b6df19ac6e72cb61c948e37e4b6f1e1207ec57cde2fb1dae9935fca645` |
| Proxy/frontend image | `sha256:ced91b3ad459bc4e3374e0e8a3fb1403cacbdd9628329a7c7f005bbcfda79689` |
| Frontend bundle | `index-TtwSIUOm.js`, production Vite output |
| Browser | Google Chrome 156.0.8078.79; Playwright 1.61.1; fresh profiles |
| Demo dataset | `demo-2026-11-15-v1`, 143 published rows, `ru/daily` |
| Business date/timezone | Real backend `2026-11-15`, `Europe/Kyiv` |
| Schema | `0008_generation_job_leases`, applied only to disposable databases |
| Runtime | Caddy 2.11.9, Gunicorn 27.0.1, PostgreSQL 17; no Vite/debug server |

The unique verification project was `horoscope-mvp1-verify`, with PostgreSQL and
Caddy storage on tmpfs and only `127.0.0.1:8443` published. No existing database,
source mount, secret, network or volume was reused.

## Automated results

- **29 mock safety checks**: existing 19 STAB-007 checks plus 10 importer guards.
- **18 demo setup/config tests**: target refusal, credential handling, scoped roles,
  immutable executable packaging and local/proxy-only configuration.
- Release context tests: 17 backend allowed canaries / 191 denied, 14 frontend
  allowed / 111 denied. Both final images built successfully.
- Focused disposable PostgreSQL importer regressions: **5 passed**.
- Full integrated `bash scripts/backend-test.sh`: **1054 passed in 120.28s**.
  The harness migrated its own tmpfs PostgreSQL and removed its project afterward.
- Integrated frontend: locked `npm ci`, typecheck, **188 unit tests / 15 files**,
  production build and **22 POC checks** passed. POC checks are fixture checks,
  not the evidence for browser acceptance. No frontend dependency changed.
- Actual unpatched demo CLI: dry-run reported 143 rows without writes; explicit
  apply inserted 143; repeat inserted 0 and preserved IDs/timestamps/content.
  Wrong instance UUID and conflicting generic DB environment refused before writes.
- Actual runtime role: `demo_readonly`; an UPDATE with `WHERE false`, even after
  explicitly selecting a read-write transaction, failed with PostgreSQL `42501`.
  Admin remained disabled in both proxy and direct backend. Debug false, paid
  flag `0`, OpenAI credential absent, scheduler module not imported.
- Forecast data fingerprint stayed identical across browser/public GET requests
  and a stop/start of the **disposable backend only**. Jobs/runs/items/attempts,
  execution starts and paid request history remained empty.

## Real browser and HTTP acceptance

**42 integrated Chrome checks passed**, plus explicit 320px forecast/archive layout
checks. Desktop: Home selection for all 13 enabled signs, marked forecast text,
archive to another published date, missing day not linked, Back/Forward, refresh
of a canonical deep link, invalid contextual NotFound, and carousel navigation.
Keyboard Enter/Space and emulated touch wheel/carousel navigation passed.

Home bounds were checked at 320, 390, 768 and 1440px; forecast/archive at 320px had
no horizontal page overflow or clipped links/buttons. Screenshots were visually
inspected. [Focused Wheel evidence](mobile-wheel.md) additionally checks 24 rotation
positions, labels, hover tooltips, focus and landscape on the real Home component
with intercepted API fixtures; that evidence is distinct from this real demo API run.

Unauthenticated Home/assets/deep links/API/health/sitemap/admin requests returned
401. Authenticated admin returned 404; missing asset returned 404; missing
forecast kept JSON `404 forecast_not_published`. API400 and an intentional upstream
502 during the disposable backend stop were preserved, not replaced by SPA200.
Readiness recovered after restart. Local HTTPS chain and hostname verification
passed using the exported **public** Caddy root certificate. Browser contexts
accepted this isolated local CA without changing the host trust store.

Final browser run: **0 page exceptions**. One console resource404 remains from
the existing missing `/favicon.svg` link; it is cosmetic and was not expanded into
an unrelated UI change. An initial harness run navigated away before two forecast
loads completed and logged aborted fetches; waiting for each displayed forecast
removed those cancellation errors. Application assertions were not weakened.

Sanitized reports and screenshots were retained under
`/tmp/horoscope-mvp1-tools/` for this local review; they are temporary artifacts,
not a production monitoring system. No real credential values are included.
GitHub CI, a public domain/ACME rollout, physical phones and Safari were not run.

## Repeating acceptance on an approved demo

Follow [the runbook](demo-stack.md) with fresh isolated resources and the current
[fixture window](demo-fixtures.md). Repeat the browser journeys and HTTP cases
above; verify the backend's real business date falls in the loaded coverage.
Use a new browser profile and the local CA (or valid hosted certificate). Keep
all checks on the private demo, never the running development frontend/API.

The accepted STAB-015 architecture remains intact. Hard paid admission,
complete fencing/recovery and generation rollout are intentionally deferred;
MVP readiness does not authorize paid execution or scheduler startup.

## Cleanup and live-runtime boundary

The disposable demo and both STAB-007 projects were removed after verification.
No task-owned containers, networks or database volumes remain. Temporary demo
password/hash files and private browser credentials were deleted. Tested images,
Docker build cache and sanitized reports/screenshots remain available locally.
Existing development container IDs, start timestamps and restart counts matched
the initial snapshot; scheduler stayed exited. No existing data/schema, live
credentials, deployment configuration or shared Git branch was changed.

# Bounded browser-prerender experiment

This is disposable local evidence, **not production serving**. It captures seven
selected routes with the real production Vue bundle in a browser. Swiper, views,
router, API modules and business-date helper run unchanged. No new dependencies.

From `frontend/`, with the existing Flask API running:

```bash
npm run build
npm run poc:serve
```

Open `http://127.0.0.1:4173/__poc` in a browser and press **Capture selected route
set**. The dashboard discovers the known published Gemini June 26 fixture and one
Ophiuchus forecast from Flask's existing sitemap inventory. It also captures Home,
Gemini June archive, an unpublished Aries route, an invalid sign and an unknown
route. It refuses to assume the Gemini fixture exists. Missing Ophiuchus is omitted
and must be reported rather than fabricated. Nothing enumerates/render-captures
the full historical inventory.

The operator's browser captures routes sequentially in temporary iframes; the
server alone is not a headless renderer. Artifacts are an **in-memory** map of HTML,
source fingerprints and revisions, lost when this disposable process stops.
`GET /__poc/state` reports hashes/revisions for change comparisons. Stop with Ctrl-C.
The server binds loopback only. It has no production authentication or persistence.

## What is reused and what is adapted

`shared.ts` exports existing sign presentation and route validation. Vite compiles
those exports in memory for the Node harness. The browser bootstrap loads the
unchanged built entrypoint, waits for initial API/body/DOM completion with a bounded
deadline, then serializes the actual Vue root. Forecast/archive templates are not
duplicated. Home gains a POC-only heading and plain links derived from the shared
13-sign list and `/api/meta`, because the wheel's current buttons are not no-JS links.
The existing document language is preserved.

Captured forecast/archival HTML gets a route-specific title and self-canonical.
Dynamic HTML, title and bootstrap metadata are inserted through replacement
callbacks, preserving literal dollar replacement tokens in captured content.
The normal `createApp().mount()` clears its target and initially loads data. The
POC bootstrap therefore retains the visible snapshot (controls temporarily inert),
mounts the normal app offscreen at viewport width, and swaps only after its initial
requests settle. This is **not hydration**. A startup failure leaves a visible POC
error notice with the snapshot retained, rather than quietly showing empty content.
Production accessibility/failure UX and an explicit view-readiness interface are
not solved by this adapter.

## HTTP boundary and authority

Every direct forecast request reads Flask's existing forecast endpoint. HTTP 200
authorizes published rendering; only the exact `404 forecast_not_published` response
authorizes unpublished absence. No provider/source policy is copied. Other backend
failures become 503. An artifact whose source response changed is discarded; a
published route without a current capture is 503 pending explicit refresh. A
withdrawn forecast is 404 immediately at the next checked request, even before
manual capture, and cannot be fetched through an unguarded static HTML directory.

Home checks its metadata fingerprint. Archive month fingerprints, capture acceptance
and refresh planning all use the same sorted set of valid selected-sign dates with
`has_forecast === true`. Unused aggregate coverage counts do not invalidate a
calendar. Route identity is fixed by its path; business-date dependencies still use
the explicit date-refresh operation below.
Unknown/invalid routes return 404. Existing shared legacy validation produces a
301 to the padded canonical forecast path. Only assets and an allowlist of public
read API endpoints are forwarded; admin/generation endpoints are inaccessible.
The harness does not implement sitemap/robots serving or a production origin policy.
Uncaptured routes are intentionally not a general production website.

## Incremental operations and isolated simulation

The dashboard's **Refresh Gemini June 26** calls
`POST /__poc/forecast {"sign":"gemini","date":"2026-06-26"}`. This invalidates
and recaptures that forecast. It includes its archive month only when backend
`has_forecast` date membership differs from the captured availability (or there is
no archive artifact). Content-only changes do not regenerate the archive or Home.
`POST /__poc/refresh {"paths":[...]}` selects at most ten routes explicitly.
These endpoints return capture tickets; the dashboard browser completes them.
Failed capture stays unavailable, and superseded tickets cannot overwrite new data.
Refreshes carry monotonic generations per route, including across asynchronous
dependency planning. Obsolete inspections cannot create tickets; capture acceptance
rechecks both generation and ticket identity. An older pending GET cannot discard a
newer captured artifact. These are single-process POC checks, not distributed locks
or a production-wide cache-coherence guarantee.

Run a separate isolated instance for mutations of **response fixtures only**:

```bash
POC_PORT=4174 npm run poc:serve -- --fixture
```

At `http://127.0.0.1:4174/__poc`, capture the baseline, then use Withdraw, Publish A,
Update B, Withdraw. Fixture mode snapshots upstream GET responses on first read and
overrides only in-memory forecast text/absence, matching month `has_forecast`, and
business metadata. Aggregate coverage fields are not a simulated backend model;
the existing view consumes only selected-sign availability. No Flask/database writes
occur. The fixture UI and process explicitly identify themselves as simulated.

Set the isolated business date and press **Set date and refresh** to call
`POST /__poc/date`. It refreshes Home, captured archives (their today links), and
captured forecasts whose yesterday/today/tomorrow label depends on the old or new
business date. Unrelated historical forecasts remain byte-identical. No browser
clock establishes the domain date. This operation is explicit, with no scheduling
or freshness SLA. Production would still need a reliable refresh/invalidation
driver, durable/atomic artifact management and publication-aware serving/cache rules.

## Verification

```bash
npm run poc:check
# With the live POC running and its selected routes captured in the browser:
npm run poc:verify
npm run typecheck
npm test -- --run
npm run build
```

The Node tests use isolated responses and synthetic capture payloads to test the
HTTP/artifact boundary, including invalidation and late-capture races. They do **not**
claim to test Vue rendering. `poc:verify` checks the real browser captures through
HTTP, parsing initial HTML without running JavaScript; it requires the verified live
fixtures. Separately smoke-test browser startup. No backend source changes or backend
tests needed.

Focused regressions use controlled asynchronous barriers (no timing sleeps) for
overlapping refresh creation, dependency planning, capture validation and pending
GETs. They also verify literal replacement tokens, aggregate-only month changes,
selected-sign publication/withdrawal and content-only updates. To run only these:

```bash
node --test --test-name-pattern='regression:' poc/checks.mjs
```

Observed proof: real Gemini and Ophiuchus text appeared completely in HTTP HTML;
Home had 13 dated links; Gemini June had days 6, 7, 26–29. All status/redirect checks
passed. Browser startup retained sign/date/content, with working day navigation and
archive-day navigation. Fixture withdrawal/publication changed forecast plus month;
text update changed only forecast; date rollover changed Home plus the archive,
leaving historical forecast revisions/hashes untouched. Timings are observations,
not a production promise. No production architecture decision is implemented here.

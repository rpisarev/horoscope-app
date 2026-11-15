# MVP-A04 responsive ZodiacWheel

## Scope and behavior

[ZodiacWheel.vue](../frontend/src/components/ZodiacWheel.vue) now sizes its targets
between 56px and 96px and caps the orbit radius at the existing 240px. The radius
also respects viewport width and small viewport height, with 12px reserved around
the targets for focus rings. The rotating container has the same dimensions as a
target, eliminating the previous 100px-container/96px-target center offset.
Typography scales with the targets; names remain visible at 320px.

At widths or heights below 768px, hover details appear in the wheel's center.
This avoids a 224px tooltip projecting beyond the viewport from an outer target.
The central tooltip does not intercept pointer events. Larger viewports retain
the tooltip attached to the hovered sign. The shared tooltip component is unchanged.

The existing 120-second rotation/counter-rotation, hover pause/resume, click,
Enter, Space, tab order, focus ring, selection payload, and Home navigation are
preserved. Sizing is CSS-only: there are no new observers, listeners, timers or
animation handles to clean up. Routes, Home, shared styles, dependencies, backend,
publication safeguards and database behavior are unchanged.

## Reproduction and measured bounds

Measurements used the actual Home page in fresh headless Chrome 156.0.8078.79
contexts, Playwright 1.61.1 and Node 24.22.2. The unmodified baseline was
`33974d9`; both versions were served from the assigned isolated worktree at
`127.0.0.1:54104`. All API requests were intercepted, and external page requests,
including Google Fonts, were blocked. No backend or live frontend was contacted.

The table gives the minimum left edge and maximum right edge of all sign targets
over 24 equally spaced samples of the 120-second rotation, in CSS pixels. Values
are rounded to two decimals; the tiny fractional differences are browser rounding.

| Viewport | Before: target x bounds | After: target x bounds | After: target diameter |
| --- | --- | --- | --- |
| 320 × 568 | −130.54 … 450.54 | 12.00 … 308.00 | 56.00 |
| 390 × 844 | −95.54 … 485.54 | 12.00 … 377.99 | 62.39 |
| 768 × 1024 | 93.46 … 674.54 | 96.00 … 672.00 | 96.00 |
| 1440 × 900 | 429.46 … 1010.54 | 432.00 … 1008.00 | 96.00 |

At 320 × 568, the old targets also extended vertically from −6.54 to 574.54px;
the new bounds are 136 … 432px. `documentElement.scrollWidth` equaled the viewport
width even **before** the fix: fixed-position target clipping is not detected by
that assertion alone. The browser regression therefore inspects each target and
label's bounding rectangle, including space for the focus ring.

For all four viewports above **and 568 × 320 landscape**, checks passed for every
target and label at all 24 rotation samples. All displayed sign names fit within
their targets. Desktop/tablet radius remains 240px with 96px targets.

Hover overflow was checked separately: every sign was hovered at animation times
0, 45 and 90 seconds in each of those five viewports. Exactly one tooltip was
visible after its transition; its complete rectangle remained within all four
viewport edges, and document width did not grow. The 320px wheel and its central
Sagittarius tooltip were also inspected visually.

## Verification

- `npm test -- --run`: **188 passed in 15 files**, including seven new dedicated
  [wheel unit tests](../frontend/tests/unit/zodiacWheel.spec.ts).
- `npm run typecheck`: passed.
- `npm run build`: passed. The existing stale Browserslist-data notice remains;
  no dependency update was made.
- [Real-browser regressions](../frontend/tests/browser/zodiacWheel.browser.mjs):
  five geometry/tooltip cases passed; three interaction cases passed on the focused
  rerun. They verify active rotation, synchronized hover pause/resume, visible
  keyboard focus retained across all four requested widths, click/Enter/Space
  navigation, removal of wheel animations after navigation, and a touch tap at 320px.
- The initial new unit tests needed selectors scoped around Vue's transition stubs.
  The initial browser interaction helpers waited for a stationary animated target.
  Those helpers now use actual mouse/touch coordinates from the target rectangle;
  no application behavior was changed to accommodate the test runner.

Installation and npm checks used a clean environment, the locked dependencies,
separate empty user/global npm configuration paths, and an isolated npm cache.
Package files are unchanged. No DB-backed tests were run; the parent owns STAB-007
serialization and final combined A05 browser/integration verification.

## Re-running the focused browser check

No browser dependency or package script was added. From this worktree's
`frontend/`, use an already installed Playwright client and Chrome. Start a
dedicated server in one terminal (the closed proxy target prevents accidental
live API access even if interception fails):

```bash
env -i PATH=/home/user/.local/bin:/usr/bin:/bin \
  VITE_API_PROXY_TARGET=http://127.0.0.1:1 \
  /home/user/.local/bin/node node_modules/vite/bin/vite.js \
  --host 127.0.0.1 --port 54104 --strictPort
```

Run the browser checks in another terminal:

```bash
env -i PATH=/home/user/.local/bin:/usr/bin:/bin \
  PLAYWRIGHT_MODULE=/tmp/horoscope-mvp1-tools/browser/node_modules/playwright/index.mjs \
  CHROME_BIN=/usr/bin/google-chrome \
  WHEEL_BASE_URL=http://127.0.0.1:54104 \
  /home/user/.local/bin/node --test tests/browser/zodiacWheel.browser.mjs
```

Use another explicitly unique loopback port if needed; port 5173 is rejected by
the test. The harness creates disposable browser contexts, supplies a fixed
business-date response, and returns an unpublished fixture for other API reads.
It does not use a personal browser profile or real forecast data. Stop this
isolated server when finished.

These are Chromium layout and emulated-touch results with local fallback fonts,
not physical-device, Safari/Firefox, live-data or deployment verification.
Final combined browser review and shared documentation updates belong to the parent.

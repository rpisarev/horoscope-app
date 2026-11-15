# STAB-029 Swiper security update

Verified on 2026-11-15 in the independent `/tmp/horoscope-iter4-a` worktree,
branch `fix/stab-029-swiper-security`, starting clean at
`17fb256ce8f5e651a5d05b4a8911d905585f4e82`. This records the standalone Swiper
change and its local checks. It does not describe installed live dependencies
or the parent's combined iteration 4 lock and verification.

## Version choice and support boundary

The official [GHSA-hmx5-qpq5-p643 advisory](https://github.com/advisories/GHSA-hmx5-qpq5-p643)
(CVE-2026-27212) covers `>=6.5.1 <12.1.2`, including the baseline locked
**11.2.7**. It identifies **12.1.2** as the patched floor; there is no patched
11.x version in that advisory. A crafted object can bypass the forbidden-key
check when `Array.prototype.indexOf` has been altered. This package defect is
distinct from proof that the application's input paths expose it.

The manifest and lock now select exact **12.2.0**. This is the smallest major
upgrade that clears the advisory while retaining upstream's v12 compatibility
line. The [12.2.0 release](https://github.com/nolimits4web/swiper/releases/tag/v12.2.0)
adds stale-event guards for destroyed instances and fixes duplicate CSS type
resolution. Those lifecycle fixes make it preferable to the minimum
[12.1.2 security release](https://github.com/nolimits4web/swiper/releases/tag/v12.1.2)
for components mounted and unmounted during navigation. This is a dependency
selection rationale, not a claim that a stale-event defect was reproduced here.

The official [v14 release notes](https://github.com/nolimits4web/swiper/releases/tag/v14.0.0)
raise the browser baseline and explicitly direct applications needing older
browsers to stay on v12. That supports retaining v12 for this scoped migration.
However, the upstream [security-policy page](https://github.com/nolimits4web/swiper/security/policy)
reports no `SECURITY.md`; the inspected official material establishes no v12
LTS duration or guaranteed future backports. This is a patched retained line,
not a promise of indefinite security maintenance. Reassess support when updating
dependencies again.

## Migration and dependency review

[v12.0.0 release notes](https://github.com/nolimits4web/swiper/releases/tag/v12.0.0)
identify removal of LESS/SCSS exports and conversion of built-in navigation
icons to SVG. This application imports CSS and renders its own Lucide arrow
buttons, so those changes require no application migration.

Registry metadata for [Swiper 12.2.0](https://registry.npmjs.org/swiper/12.2.0)
and the installed package retain the exports used by this repository:

| Import | Existing consumer | Verification |
| --- | --- | --- |
| `swiper/vue` (`Swiper`, `SwiperSlide`) | ZodiacCarousel, YearSwiper, MonthSwiper | Real-package jsdom mount, existing suite, production build |
| `swiper` (`Swiper` type) | All three carousel components | Existing `vue-tsc` check |
| `swiper/css` | `src/main.js`, YearSwiper, MonthSwiper | Production CSS bundling |

The package declares no runtime or peer dependency additions. The lock diff
changes only the root Swiper requirement and `node_modules/swiper` (version,
registry URL, integrity and package metadata). Vue 3.5.13, Vue Router 4.5.1,
Vite 6.4.6, Vitest 4.1.12, TypeScript 5.9.3 and vue-tsc 3.3.11 are unchanged.
There are no overrides, forced resolutions or blanket dependency updates.
The application Node engine remains `^22.12.0 || >=24.0.0`.

## Reproduced defect and narrow source change

Before changing source, a focused component test injected invalid `realIndex`
values `-1`, the slide count, `0.5`, `NaN` and `Infinity`. All five cases failed
with `TypeError: Cannot read properties of undefined (reading 'key')` in
`ZodiacCarousel.onSlide`. The other 20 initial component/router-adapter tests
passed. These are synthetic malformed events, not evidence that real Swiper
emits such indices during normal browser operation.

With the parent's explicit approval, `onSlide` now uses `SwiperType` and checks
integer/range validity before assigning the active index or emitting a sign.
The regressions verify no error, no model emission, no active-sign corruption,
and normal handling of the next valid event. Programmatic synchronization,
route logic, arrow handlers, breakpoint settings and loop configuration are
unchanged. No HoroscopeView, ArchiveMonth, YearSwiper or MonthSwiper source
was edited by this task.

## Verification layers

| Tests | Evidence | Limits |
| --- | --- | --- |
| [zodiacCarousel.spec.ts](../frontend/tests/unit/zodiacCarousel.spec.ts), 26 tests | Every initial sign, real-index mapping, loop endpoints, arrow delegation, parent-driven `slideToLoop`, malformed indices and recovery, native button focus and keyboard-style click; synthetic memory-router sign/date updates, Back/Forward and repeated navigation | Uses a synchronous Swiper double. The minimal router adapter is not HoroscopeView or ArchiveMonth. |
| [zodiacCarouselReal.spec.ts](../frontend/tests/unit/zodiacCarouselReal.spec.ts), 7 tests | Real installed Swiper/Vue exports, initial selections including Ophiuchus, actual `slidePrev`/`slideNext` loop behavior, repeated programmatic moves and mount/destruction | jsdom uses supplied geometry/media queries, fake frame timers and zero animation duration. No real browser layout or input gestures. |
| [swiperSecurity.spec.ts](../frontend/tests/unit/swiperSecurity.spec.ts), 1 test | Advisory reproduction fails on 11.2.7 (`polluted: true`) and passes on 12.2.0 (`polluted: false`) | Runs only in a disposable local Node child process; does not establish application exploitability. |

All seven real-package jsdom tests also passed with the original 11.2.7 package
before updating the lock. The security regression deliberately isolates the
advisory's prototype modification from the Vitest process and restores the
modified properties in the child before exit.

The first full patched run exposed an error in the new keyboard-style test:
Vue Test Utils attempted to assign read-only `UIEvent.detail`. Constructing a
native `MouseEvent` corrected the test; no application change was made for it.
The final full run below includes that correction.

## Standalone worktree check results

Commands ran sequentially from the isolated `frontend/` directory using
**Node 24.22.2 / npm 11.19.1**. A fixed helper constructed an environment from
an allowlist, with private HOME/temp/cache directories, empty private user and
global npm configs, and the explicit public registry `https://registry.npmjs.org/`.
No personal credentials or frontend dotenv files were inherited. The helper,
cache and logs are outside the tracked tree at `/tmp/horoscope-stab029-tools/`.

| Command | Final result | Wall time |
| --- | --- | --- |
| `npm ci --no-audit` | Passed; 268 packages installed from final lock | 5.82s |
| `npm run typecheck` | Passed | 3.87s |
| `npm test -- --run --maxWorkers=2` | 145 tests in 13 files passed; no skips | 7.92s |
| `npm run build` | Passed; 1,699 modules transformed | 4.87s |
| `npm run poc:check` | 22 fixture tests passed; no skips | 2.39s |
| `npm ls --all --json` | Exit 0; no dependency/peer problems | 0.66s |
| `npm audit --json` | Exit 1; Swiper absent, 11 other package entries remain | 2.27s |

The baseline locked install also passed (268 packages, 47.41s). The audit was
run separately rather than hidden in installation. Existing stale Browserslist
data and npm's esbuild postinstall `allowScripts` warning remain. Neither warning
prevented the checks; this task does not update those tools or their configuration.
The fixture POC uses injected responses and temporary local listeners, not a
live application backend, real browser capture or production renderer.

| Audit snapshot (standalone A worktree) | Critical | High | Moderate | Total package entries |
| --- | ---: | ---: | ---: | ---: |
| Base | 2 | 9 | 1 | 12 |
| Swiper update | 1 | 9 | 1 | 11 |

Remaining entries are form-data (critical); Vue, @vue/server-renderer,
brace-expansion, browserslist, editorconfig, glob, js-cookie, minimatch and ws
(high); and postcss-selector-parser (moderate). These are package-entry counts,
not unique advisories or reachable exploits. The separate form-data task and
the parent's combined lock are outside this snapshot. This tree is not
audit-clean.

## Pending browser verification and integration

The parent reported the supported browser inventory as `apps=[]`, `browsers=[]`.
Real-browser smoke remains pending. Required checks are initial deep-linked
selection, desktop mouse arrows, focus plus native Enter/Space activation,
mobile touch/swipe, loop edges, programmatic sign changes, Back/Forward and
repeated navigation across horoscope/archive views. Also check the archive's
year/month Swipers because they share this dependency. The unit keyboard-style
click proves handling of the click event only, not a browser's generation of
that event from a keypress. jsdom and mocked Swiper results cannot close these
browser gaps or rule out asynchronous route/transition races.

No alternate browser tooling or live frontend server was launched. There were
no backend test runs, Docker actions, live DB operations, provider requests,
secret/dotenv reads, runtime configuration changes, commits or pushes. Shared
CURRENT_STATE, architecture, ADR and backlog documents remain parent-owned.
Accepted D1–D8 remain future policy, not guarantees added by this frontend work.

The parent must reconcile the package lock with the independent form-data update
and verify the combined tree. Updating source and lockfiles does not replace a
running frontend's dependencies or its named dependency volume; deployment and
browser verification remain separate work.

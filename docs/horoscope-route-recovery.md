# STAB-005: Horoscope route recovery

Implemented in the independent Iteration 4 worktree, based on
`17fb256ce8f5e651a5d05b4a8911d905585f4e82`.

## Reproduced behavior

In a reused `HoroscopeView`, navigating from a valid forecast URL to an invalid
sign/date and back to the same valid URL cleared the forecast without reloading
it. The models retained their previous valid sign/day, while fetching depended
on those models changing. Invalid navigation and unmount also left pending
requests able to write text, error and loading state. A delayed, superseded
control navigation could fetch the latest forecast a second time when its
`router.replace` promise finished.

The new deterministic tests reproduced these failures before the source change:
the focused run had **24 failures and 32 passes**. Its existing forecast-read and
legacy archive-day suites passed; all failures were in the new recovery suite.

## Implementation

[`HoroscopeView.vue`](../frontend/src/views/HoroscopeView.vue) now loads from the
validated, committed route's sign/day. A watcher on those two individual values
clears prior state, synchronizes the controls and starts exactly one forecast
request for a valid identity. Returning from an invalid route reloads even when
the controls still hold the same valid values. Repeating the current identity,
including query/hash-only navigation, does not reload it.

The route watcher's cleanup invalidates its request ID on sign/day changes and
unmount. Success, rejection and `finally` all retain their request-ID checks.
This is logical invalidation: the existing API helper does not abort transport
or impose a request deadline. The control watcher only validates and navigates;
finishing a canceled navigation cannot start another request.

Strict sign/calendar validation, contextual NotFound, canonical forecast URLs,
legacy archive replacement, unpublished/empty/error messages and forecast API
parsing are unchanged. No global state or carousel behavior was introduced.

## Verification

[`horoscopeRouteRecovery.spec.ts`](../frontend/tests/unit/horoscopeRouteRecovery.spec.ts)
adds 36 cases using the real route table/router and deferred fake fetch promises.
It covers invalid cold loads, same-instance valid → invalid → same-valid
recovery, late success/rejection/404 while invalid and after restoration,
preserving newer loading state against stale `finally`, unmount state writes,
rapid sign/date changes, repeated identity/query/hash navigation, control changes
without duplicate fetches or replace feedback, canceled navigation, current
404/error/empty states, and legacy canonical replacement with query/hash.
Carousel and day controls are stubbed; these tests exercise their parent model
boundary, not Swiper's browser behavior.

Commands ran from `frontend/` with Node **24.22.2**, npm **11.19.1**, the unchanged
baseline lockfile, an environment allowlist, private HOME/cache/temp directories,
empty private npm configs and the public npm registry. `npm ci --ignore-scripts
--no-audit --no-fund` installed 268 packages. No personal configuration or dotenv
was loaded. Temporary runner and logs are outside the tracked worktree.

| Check | Result |
| --- | --- |
| Focused recovery/read/legacy navigation tests, `--run --maxWorkers=2` | 56 passed across 3 files |
| `npm test -- --run --maxWorkers=2` | 147 passed across 11 files, including strengthened hidden-state assertions |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; 1,699 modules transformed |
| `git diff --check` | Passed |

The existing stale Browserslist-data warning remains. No backend tests, database
operations, provider requests, Docker actions, live frontend use or runtime
changes were performed. Parent-owned combined dependency/browser verification
remains separate from these baseline-dependency checks. Shared state/architecture
documents and accepted future generation policy were not edited.

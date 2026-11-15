# SEC-001 form-data security remediation

Verified on 2026-11-15 in `/tmp/horoscope-iter4-b`, branch
`fix/sec-001-form-data`, against base
`17fb256ce8f5e651a5d05b4a8911d905585f4e82`. This records the independent SEC-001
dependency change and its verification. Combined Iteration 4 verification belongs
to the integration owner; installed live dependencies were not inspected or changed.

## Dependency decision

The actual installed path is the direct dev dependency `jsdom@24.1.3` →
`form-data@4.0.2`. Vitest also accepts this jsdom installation through its optional
peer. jsdom's `form-data: ^4.0.0` range already accepts both security fixes, so a
jsdom major upgrade, override or new direct dependency is unnecessary.

| Package | Baseline → selected lock | Reason |
| --- | --- | --- |
| form-data | 4.0.2 → 4.0.6 | Meets both advisory floors below within jsdom's existing range. |
| hasown | 2.0.2 → 2.0.4 | form-data 4.0.6 adds `hasown: ^2.0.4`; the existing shared installation updates compatibly. |
| jsdom | 24.1.3 → 24.1.3 | Existing DOM/test environment retained; manifest remains `^24.0.0`. |

The [published form-data 4.0.6 metadata](https://registry.npmjs.org/form-data/4.0.6)
also raises its mime-types range from `^2.1.12` to `^2.1.35`; the existing locked
mime-types 2.1.35 already satisfies it. Other dependency ranges remain compatible.
There are **no added or removed package entries** and exactly two changed package
entries: `node_modules/form-data` and `node_modules/hasown`. Their registry URLs,
integrities and license metadata update with the versions. hasown remains deduplicated
with its existing consumers; its `function-bind: ^1.1.2` dependency is unchanged.

Only `frontend/package-lock.json` and this document change. `package.json`, source,
configuration, tests and POC code are unchanged. The focused command was
`npm update form-data --package-lock-only --ignore-scripts --no-audit` under the
isolated environment below. No `audit fix`, force update or overrides were used.
The checked-in lock carries this transitive fix; retaining or restoring an old
installation/lock does not receive it merely from the unchanged jsdom range.

## Advisory basis and exposure boundary

| Official advisory | Affected ranges | Patched versions |
| --- | --- | --- |
| [GHSA-fjxv-7rqg-78g4](https://github.com/advisories/GHSA-fjxv-7rqg-78g4), critical, predictable multipart boundaries | `<2.5.4`; `>=3.0.0 <3.0.4`; `>=4.0.0 <4.0.4` | 2.5.4, 3.0.4, 4.0.4 |
| [GHSA-hmw2-7cc7-3qxx](https://github.com/advisories/GHSA-hmw2-7cc7-3qxx), high, CRLF/quote injection in multipart names/filenames | `<2.5.6`; `>=3.0.0 <3.0.5`; `>=4.0.0 <4.0.6` | 2.5.6, 3.0.5, 4.0.6 |

The first advisory requires attacker-controlled request data and predictability
of the old `Math.random()` boundary. The second depends on untrusted field names
or filenames reaching serialization. Installed 4.0.6 source uses
`crypto.randomBytes(12)` for boundaries and percent-escapes CR, LF and quotes in
both header parameters. This describes the package fix, not proven exploitability
of the application or an assessment of the live service.

Source inspection found jsdom configured as the
[unit environment](../frontend/vitest.config.js), with explicit JSDOM use in
[POC checks](../frontend/poc/checks.mjs) and
[POC verification](../frontend/poc/verify.mjs). No direct form-data, FormData or
XMLHttpRequest reference was found in `frontend/src`. jsdom itself imports form-data
in `lib/jsdom/living/xhr/xhr-utils.js` for multipart XMLHttpRequest bodies. This is
a dev dependency in the reviewed lock, not an application import. No server or
live exploit was exercised to establish runtime reachability.

## Verification

Node **24.22.2** and npm **11.19.1** on Linux x64 satisfy the existing
`^22.12.0 || >=24.0.0` engine range. Commands used the parent-verified Node/npm
executables through a private bin directory. The child environment was constructed
from an allowlist, with private HOME, temp and cache directories, empty user/global
npm configs, explicit `https://registry.npmjs.org/`, and paid execution set to `0`.
No caller credentials, proxy settings or personal npm configuration were inherited.
Filename-only checks found no automatically loaded dotenv or project npmrc in the
worktree/frontend; the tracked root `.env.example` was not loaded.

Regression checks ran sequentially in the independent frontend directory. No existing
assertion, DOM environment, watcher test, fetch mock or fake-timer setup changed.

| Check | Result | Wall time |
| --- | --- | ---: |
| Baseline `npm ci --no-audit` | 268 packages installed | 39.229s |
| Final `npm ci --no-audit` | 268 packages installed from final lock | 5.697s |
| `npm run typecheck` | Passed | 3.822s |
| `npm test -- --run --maxWorkers=2` | 111 tests / 10 files passed, none skipped | 7.278s |
| `npm run build` | Passed, 1,699 modules transformed | 5.967s |
| `npm run poc:check` | 22 fixture checks passed, none skipped/cancelled | 2.744s |
| `npm ls --all --json` | Exit 0, no dependency/peer problems | 0.676s |
| Final `npm explain form-data hasown jsdom --json` | One installation of each at the versions above | 0.647s |
| Baseline / final `npm audit --json` | Both exit 1; residual findings below | 7.884s / 1.284s |

Two additional in-memory serialization probes used the same assertions before
and after the update, with explicit vulnerable/fixed expectations. They replaced
`Math.random` temporarily with a throwing function during boundary generation,
then restored it; appended field names and filenames containing CR/LF/quotes;
and inspected `getBuffer()` output. Baseline 4.0.2 called `Math.random` and emitted
an injected header line. Final 4.0.6 avoided `Math.random`, encoded the parameters,
and emitted no injected header line. Ordinary bracket/dot/Unicode field names and
values were preserved. These probes made **zero network requests**. The existing
POC suite separately uses temporary loopback listeners with injected responses;
it does not fetch the live backend or validate real-browser capture.

Evidence remains under ignored `frontend/.vite/sec001/`: `run.py` constructs the
allowlisted environment, `serialization-check.cjs` contains the in-memory probes,
and `logs/` holds command metadata plus stdout/stderr, including complete baseline
and final audit JSON. These local evidence files are not part of the source diff.

Existing stale Browserslist-data warnings remain. npm reports esbuild's postinstall
script as not covered by `allowScripts`; no script approval/config change was made,
and installation/build/checks passed. No coverage/lint run, backend tests, DB action,
Docker action, provider request, live smoke, `poc:serve`, `poc:verify` or runtime
rollout was performed. Browser smoke and combined integration validation are owned
by the parent. Local timing is evidence, not a performance guarantee.

## Residual audit entries

These are the **SEC-001-only worktree** snapshots, before integrating the parallel
Swiper change. Counts are affected npm package entries, not unique advisories or
confirmed exploitable paths. Final audit has no form-data entry or new entry.

| Snapshot | Critical | High | Moderate | Total |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 2 | 9 | 1 | 12 |
| SEC-001 final | 1 | 9 | 1 | 11 |

| Remaining package(s) / locked version | Severity | Dependency context |
| --- | --- | --- |
| Swiper 11.2.7 | Critical | Direct application dependency; parallel Swiper scope. |
| Vue / @vue/server-renderer 3.5.13 (two entries) | High | Direct Vue and its server renderer. |
| brace-expansion 2.0.1 | High | Shared minimatch tree. |
| browserslist 4.24.5 | High | Autoprefixer. |
| editorconfig 1.0.4 | High | Vue test-utils → js-beautify; minimatch findings. |
| glob 10.4.5 | High | js-beautify and Tailwind → sucrase. |
| js-cookie 3.0.5 | High | Vue test-utils → js-beautify. |
| minimatch 9.0.1 / 9.0.5 (one entry) | High | editorconfig and glob. |
| ws 8.18.2 | High | jsdom; independent of the form-data remediation. |
| postcss-selector-parser 6.1.2 | Moderate | Tailwind/postcss-nested. |

The unchanged residual advisory IDs are recorded in the earlier
[frontend-toolchain residual table](frontend-toolchain.md#audit-findings-outside-this-change)
and this worktree's complete final audit log. They remain separate remediation
work; this change does not make the full tree audit-clean. In particular, retaining
jsdom for compatibility does not resolve its separate ws dependency advisories.

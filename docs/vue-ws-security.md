# SEC-002: Vue and ws dependency remediation

Verified on 2026-11-15 in the isolated `fix/sec-002-vue-ws-security`
worktree, from baseline `ea3c0ec166b37b00e05164521b7ab9cd4e78fd8f`.
The isolated results below are preserved separately from the orchestrator
verification at the end. Neither establishes GitHub CI or installation in running
containers.

## Changes and security basis

| Dependency | Baseline lock | Selected lock | Reason |
| --- | --- | --- | --- |
| Vue, server renderer and the coordinated compiler/runtime/shared packages | 3.5.13 | 3.5.45 | Stable Vue 3.5 patch release above the 3.5.42 security floor. Manifest minimum is now `^3.5.45`. |
| ws | 8.18.2 | 8.23.0 | Current cumulative patched 8.x release, including the November 12 automatic-pong advisory. |

Vue is direct; `@vue/server-renderer` is an exact-version dependency of Vue and
is also consumed by Vue Test Utils. `ws` is a dev dependency through jsdom 24.1.3,
whose `^8.18.0` range already accepts the fix. No direct ws dependency or override
was added. All ten Vue core packages resolve to 3.5.45, without nested old copies.

The original maintainer
[Vue advisory](https://github.com/vuejs/core/security/advisories/GHSA-g2v6-rqmx-r4w6)
still displays no patched version. The subsequently updated
[GitHub Reviewed record](https://github.com/advisories/GHSA-g2v6-rqmx-r4w6)
identifies 3.5.42 as the stable patched floor. This was reconciled against the
[tagged upstream source](https://raw.githubusercontent.com/vuejs/core/v3.5.42/packages/shared/src/domAttrConfig.ts):
its attribute-name blacklist contains carriage return (`\u000d`). The installed
3.5.45 shared implementation was also inspected and contains the same check.
No attack payload or exploit against a running service was used for this review.
The [3.5.45 changelog](https://github.com/vuejs/core/blob/v3.5.45/CHANGELOG.md)
records the selected stable patch release.

This is an SSR attribute-name issue. Current application/POC source has no
`@vue/server-renderer`, `createSSRApp` or `renderToString` use; the POC captures a
browser-rendered SPA. Package presence is not evidence of an exploitable public
SSR endpoint. The affected installed dependency is nevertheless updated.

The ws maintainer advisories establish these cumulative floors:

| Advisory | Patched 8.x floor |
| --- | --- |
| [GHSA-58qx-3vcg-4xpx](https://github.com/websockets/ws/security/advisories/GHSA-58qx-3vcg-4xpx), uninitialized memory disclosure | 8.20.1 |
| [GHSA-96hv-2xvq-fx4p](https://github.com/websockets/ws/security/advisories/GHSA-96hv-2xvq-fx4p), fragment/chunk memory exhaustion | 8.21.0 |
| [GHSA-37g9-w4hg-h9qr](https://github.com/websockets/ws/security/advisories/GHSA-37g9-w4hg-h9qr), automatic-pong memory exhaustion | 8.23.0 |

The last advisory was absent from the baseline npm audit feed. Choosing only
8.21.0 based on that feed would miss the newer fix. The
[8.23.0 release](https://github.com/websockets/ws/releases/tag/8.23.0)
documents the cumulative selected fix. Advisory reproductions were not run.

## Lockfile scope and compatibility

Only Vue and ws were targeted for resolution. Vue 3.5.45 requires these supporting
transitive updates:

- `@babel/parser`, `@babel/types`, `@babel/helper-string-parser`:
  7.27.1 → 7.29.14; `@babel/helper-validator-identifier`: 7.27.1 → 7.29.7.
  The compiler now requires parser `^7.29.12` and its corresponding helpers.
- `entities`: 4.5.0 → 7.0.1, required by compiler-core `^7.0.1`.
- `csstype`: 3.1.3 → 3.2.3, required by runtime-dom `^3.2.3`.
- npm refreshed license metadata for unchanged estree-walker 2.0.2.

Existing PostCSS, magic-string and source-map-js already satisfy the newer Vue
requirements and remain unchanged. Router 4.5.1, Swiper 12.2.0, Vite 6.4.6,
Vitest 4.1.12, Vue plugin 5.2.3, Vue Test Utils 2.4.6, jsdom 24.1.3,
TypeScript 5.9.3 and vue-tsc 3.3.11 are unchanged. There are no application,
test/assertion, rendering, configuration or CI edits, no major toolchain migration,
no forced audit fix and no peer dependency overrides.

## Isolated verification

Linux x64 verification used Node **24.22.2** and npm **11.19.1**, satisfying the
existing engine policy. Each npm command received an environment built from an
allowlist, private HOME/cache/temp directories, empty private user/global npmrc,
the public npm registry, no inherited credentials and paid execution set to `0`.
Only the tracked `.env.example` existed; no live dotenv was loaded.

For typecheck, tests, build and POC, a temporary Node preload additionally denied
TLS and TCP connections except connections to loopback listeners created by that
same process. This permitted the POC's ephemeral fixture server, while blocking
external transport and access to the live localhost backend/frontend. Application
fetch behavior remains mocked by the existing tests. The preload is verification
instrumentation outside the repository, not an application security boundary.

| Command, from `frontend/` | Result | Wall time |
| --- | --- | ---: |
| `npm ci --no-audit` | Passed; 268 packages installed from the final lock | 15.16s |
| `npm ls --all --json` | Passed; no dependency/peer errors | 0.27s |
| `npm audit --json` | Exit 1; only the seven out-of-scope entries below | 0.77s |
| `npm run typecheck` | Passed | 1.78s |
| `npm test -- --run` | 181 tests, 14 files passed; no skipped tests | 2.80s |
| `npm run build` | Passed | 2.49s |
| `npm run poc:check` | 22 fixture tests passed; none skipped/cancelled | 1.27s |

The unchanged unit suite covers 36 HoroscopeView route-recovery scenarios,
26 mocked carousel cases, seven real Swiper/jsdom cases, archive availability,
forecast reads, business-date state, async responses and cleanup. These checks do
not establish real-browser touch/keyboard behavior or a production prerenderer.
No browser, Alpine/Node 22 runtime or GitHub CI result is claimed.

The existing Browserslist data-age warning and npm's esbuild `allowScripts`
warning remain; installation/build succeeded without changing those policies.
No backend suite, DB operation, provider call, live server access, Docker action,
deployment, push or PR was performed by this task.

## Audit delta and remaining work

| Snapshot | Critical | High | Moderate | Total affected package entries |
| --- | ---: | ---: | ---: | ---: |
| Baseline lock | 0 | 9 | 1 | 10 |
| Final installed lock | 0 | 6 | 1 | 7 |

Both audit commands exited 1. These are package-entry counts, not distinct CVEs or
confirmed reachable exploits. Final audit no longer lists Vue, server-renderer or
ws. The remaining exact installed versions are unchanged and require separate
scoped remediation:

| Package | Version(s) | Severity | Path |
| --- | --- | --- | --- |
| brace-expansion | 2.0.1 | High | minimatch / test and CSS tooling |
| browserslist | 4.24.5 | High | Autoprefixer |
| editorconfig | 1.0.4 | High | Vue Test Utils → js-beautify |
| glob | 10.4.5 | High | js-beautify and Tailwind → sucrase |
| js-cookie | 3.0.5 | High | Vue Test Utils → js-beautify |
| minimatch | 9.0.1, 9.0.5 | High | editorconfig and glob; one audit entry |
| postcss-selector-parser | 6.1.2 | Moderate | Tailwind / postcss-nested |

The whole dependency tree is not audit-clean. Running containers and existing
node_modules volumes retain their prior installations until an explicitly
authorized rollout; this task does not refresh them.

Task evidence is in `/tmp/horoscope-iter5-e-tools/logs/`: `baseline-audit.log`,
`vue-metadata.log`, `ws-metadata.log`, `update-vue.log`, `update-ws.log`,
`final-ci.log`, `final-ls.log`, `final-audit.log`, `final-typecheck.log`,
`final-test.log`, `final-build.log`, and `final-poc.log`. Matching `.result.json`
files contain exit codes, commands and wall times. Temporary evidence may be
removed after orchestration; the version and result tables above are the durable
handoff. The orchestrator owns integrated verification and shared status docs.

## Orchestrator integration verification — 2026-11-15

The same dependency changes were integrated into
`/tmp/horoscope-iter5-integration`. `npm ci` (5.82s), `npm ls --all`, typecheck,
**181 unit tests**, production build and **22 POC checks** all passed again using
the private Node/npm environment and execution network guard described above.
`npm audit --json` still reports exactly **0 Critical, 6 High, 1 Moderate**,
with the same seven entries listed above; Vue and ws are absent. This is
integrated-tree verification, not reuse of agent-local test results.

The browser inventory was checked again and contained no enabled browsers/apps.
Real-browser touch/keyboard checks remain unavailable. No live dev server was
contacted or restarted, and no GitHub CI was triggered. Backend-only changes
after this verification do not alter the tested frontend tree.

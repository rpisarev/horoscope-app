# STAB-003 frontend toolchain

Verified on 2026-11-15 in the isolated `fix/stab-003-vite-security` worktree,
against baseline `4fe11beaa3109f50a738ddcd274b8cab59fd058e`. This records the
dependency change and local verification, not installation in running containers.

## Later iteration 4 delta

STAB-029 upgrades Swiper to 12.2.0; SEC-001 updates form-data to 4.0.6 and its
required hasown dependency to 2.0.4 without changing jsdom. The historical
STAB-003 snapshots below remain unchanged evidence from that task, not the current
lock. The integrated audit now reports **0 critical, 9 high, 1 moderate** package
entries. See [Swiper rationale/tests](swiper-security.md),
[form-data compatibility](form-data-security.md) and the final integrated
[CURRENT_STATE](CURRENT_STATE.md) checkpoint. No live image or dependency volume
was updated. Browser smoke and Alpine/Node 22 deployment verification remain separate.

## Supported compatible versions

| Component | Baseline lock | Selected lock / policy | Reason |
| --- | --- | --- | --- |
| Vite | 6.3.5 plus two nested 5.4.19 copies | 6.4.6, manifest `^6.4.6` | Lowest supported major with the current critical fix; one shared installation. |
| Vitest | 1.6.1 | 4.1.12, manifest `^4.1.12` | Lowest currently supported branch; patched mocker; accepts Vite 6 and removes the old vite-node dependency. |
| Vue plugin | 5.2.3 | 5.2.3, unchanged | Its Vite `^5.0.0 || ^6.0.0` and Vue `^3.2.25` peers are satisfied. |
| Node | Compose 20, CI 22 | Prefer current patched Node 22 LTS; engine `^22.12.0 || >=24.0.0` | Node 20 is EOL; 22.12 enables native ESM loading through `require()` for the existing JavaScript config. |
| Application packages | Vue 3.5.13, Router 4.5.1, Swiper 11.2.7 | Unchanged | No application migration is required. |
| Compiler checks | TypeScript 5.9.3, vue-tsc 3.3.11 | Unchanged | Keep the existing typecheck. |

The official [Vite support policy](https://vite.dev/releases) still backports
security fixes to 6.4. The [Vitest support policy](https://vitest.dev/releases)
supports 4.1, 5.0 and 5.1; 3.x is no longer a supported alternative. Registry
metadata for [Vitest 4.1.12](https://registry.npmjs.org/vitest/4.1.12) accepts
Vite `^6.0.0 || ^7.0.0 || ^8.0.0`; the
[Vue plugin metadata](https://registry.npmjs.org/@vitejs/plugin-vue/5.2.3)
supports the retained major. No peer overrides or forced dependency resolution
were used. These support statements describe the verification date.

[Node's release status](https://nodejs.org/en/about/previous-releases) marks 20
EOL and 22 LTS. The [22.12.0 release notes](https://nodejs.org/en/blog/release/v22.12.0)
document default `require(esm)` support. The engine range is a compatibility
floor, not a recommendation to use an old patch or an unsupported odd-numbered
Node release. Verification used **Node 22.23.5 and npm 11.19.1 on Linux x64**.

## Security basis

The official critical
[GHSA-p4f5-76q4-ffq7](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7)
covers Vite 4.0.0 through 6.4.5 and identifies 6.4.6 as the patched 6.x floor.
Both baseline versions were affected. The advisory concerns a network-exposed
development server; this is a dependency finding, not evidence of exploitation
or a measurement of the live container. No exploit or dev-server probe was run.
The [6.4.6 release](https://github.com/vitejs/vite/releases/tag/v6.4.6) supplies
the backport without a Vite major migration.

Other primary Vite advisories were checked rather than assuming that the critical
fix was the only requirement:

| Advisory | Relevant patched version / applicability |
| --- | --- |
| [GHSA-g4jq-h2w9-997c](https://github.com/vitejs/vite/security/advisories/GHSA-g4jq-h2w9-997c), [GHSA-jqfw-vq24-v9c3](https://github.com/vitejs/vite/security/advisories/GHSA-jqfw-vq24-v9c3) | 6.3.6; baseline root and nested copies affected. |
| [GHSA-93m4-6634-74q7](https://github.com/vitejs/vite/security/advisories/GHSA-93m4-6634-74q7) | 6.4.1; Windows deny-list bypass. |
| [GHSA-4w7w-66w2-5vf9](https://github.com/vitejs/vite/security/advisories/GHSA-4w7w-66w2-5vf9), [GHSA-p9ff-h696-f583](https://github.com/vitejs/vite/security/advisories/GHSA-p9ff-h696-f583) | 6.4.2; optimized dependency paths and WebSocket file access. |
| [GHSA-fx2h-pf6j-xcff](https://github.com/vitejs/vite/security/advisories/GHSA-fx2h-pf6j-xcff) | 6.4.3; Windows alternate paths. |
| [GHSA-rq7h-c2jc-7f22](https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22), [GHSA-9jrq-w75r-8gcw](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw) | 6.4.4; filesystem boundaries and cross-origin middleware. |
| [GHSA-8g5g-mxqh-grgj](https://github.com/vitejs/vite/security/advisories/GHSA-8g5g-mxqh-grgj) | 6.4.5; regression in 6.4.4. |
| [GHSA-v2wj-q39q-566r](https://github.com/vitejs/vite/security/advisories/GHSA-v2wj-q39q-566r), [GHSA-vfpm-58rq-9qcg](https://github.com/vitejs/vite/security/advisories/GHSA-vfpm-58rq-9qcg) | Listed affected ranges do not include Vite 6. |

Vitest 4.1.12 also meets the current mocker fixes:
[GHSA-qxg6-89mg-rqv8](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8)
and [GHSA-xp26-3454-mjgp](https://github.com/vitest-dev/vitest/security/advisories/GHSA-xp26-3454-mjgp).
The [4.1.12 release](https://github.com/vitest-dev/vitest/releases/tag/v4.1.12)
documents their backport. Earlier redirect-mock, browser and UI fixes have
4.1.x floors no higher than 4.1.11:
[redirect mocks](https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9),
[provider file access](https://github.com/vitest-dev/vitest/security/advisories/GHSA-p63j-vcc4-9vmv),
[browser API](https://github.com/vitest-dev/vitest/security/advisories/GHSA-g8mr-85jm-7xhm),
[inline script](https://github.com/vitest-dev/vitest/security/advisories/GHSA-2h32-95rg-cppp),
and [UI file access](https://github.com/vitest-dev/vitest/security/advisories/GHSA-5xrq-8626-4rwp).
The newer [server deny-list advisory](https://github.com/vitest-dev/vitest/security/advisories/GHSA-p458-7748-mcp3)
lists Vitest 5, not 4.1. This repository uses jsdom, without installing Vitest's
browser providers or UI; those servers were not enabled for verification.

## Focused transitive updates

Updating Vite and Vitest alone retained vulnerable packages from the old lock.
Only the following additional package names were explicitly updated, within
their existing major ranges:

| Package | Baseline → selected | Security reason |
| --- | --- | --- |
| Rollup | 4.40.2 → 4.68.3 | [GHSA-mw96-cpmx-2vgc](https://github.com/rollup/rollup/security/advisories/GHSA-mw96-cpmx-2vgc), patched 4.x floor 4.59.0. |
| PostCSS | 8.5.3 → 8.5.33 | [GHSA-fxqj-rqcc-2cmp](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp), cumulative patched floor 8.5.23. |
| picomatch | 2.3.1 / 4.0.2 → 2.3.2 / 4.0.7 | [GHSA-c2c7-rcm5-vvqj](https://github.com/micromatch/picomatch/security/advisories/GHSA-c2c7-rcm5-vvqj) and GHSA-3v7f-55p6-f55p; preserve both dependency majors. |
| nanoid | 3.3.11 → 3.3.20 | PostCSS dependency; npm advisories [GHSA-2v37-7h3g-55p8](https://github.com/advisories/GHSA-2v37-7h3g-55p8), GHSA-28wg-ghj8-5hjv, GHSA-xwg4-73v4-xw9w; required floor 3.3.18. |
| source-map-js | 1.2.1 → 1.2.2 | PostCSS dependency shared with Vue's compiler; [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q), patched 1.2.2. |
| yaml | 2.7.1 → 2.9.1 | Installed Vite optional peer shared with Tailwind; [GHSA-48c2-rrv3-qjmp](https://github.com/eemeli/yaml/security/advisories/GHSA-48c2-rrv3-qjmp), patched 2.x floor 2.8.3. |

PostCSS is also a direct dev dependency. Its declared minimum is raised from
`^8.4.33` to `^8.5.23` so the manifest excludes the affected range when resolving
the shared Vite/CSS-tooling dependency. Other direct dependency ranges are unchanged
except Vite and Vitest. The lock chooses available compatible releases above the
security floors; it does not add these transitives as direct dependencies.

The remaining lock changes follow those packages' dependency requirements:
Vitest's coordinated `@vitest/*` packages, Chai/assertion types, mock/module
utilities, `magic-string`/sourcemap-codec, `pathe`, `std-env`, and tiny utilities;
Rollup's matching optional native binaries and ESTree types; and tinyglobby's
fdir/picomatch dependencies. Old vite-node, tinypool and both nested Vite 5 /
esbuild 0.21 trees disappear. Root esbuild 0.25.4 stays unchanged. Lock review
confirms one Vite 6.4.6, unchanged application dependency versions, and no
application, config, test, POC or script edits. No blanket update, `audit fix`,
force flag, or dependency override was used.

## Verification

All verification commands ran sequentially from the isolated frontend directory. The command
environment was constructed from an allowlist, with private HOME/cache/temp
directories under its ignored `.vite/stab003/` directory, empty private npm
configuration, explicit public npm registry and paid execution set to `0`.
No real npmrc, credentials or development dotenv were loaded. The only dotenv
filename present in the worktree was the tracked root `.env.example`, which is
not an automatically loaded Vite environment file. Node 22.23.5 was installed
privately through npm; the host's Node installation was not replaced.

| Check | Final result | Wall time |
| --- | --- | --- |
| `npm ci` | 268 packages installed from the final lock | 2.14s |
| `npm run typecheck` | Passed | 1.91s |
| `npm test -- --run --maxWorkers=2` | 111 tests, 10 files; no skips | 3.63s (Vitest 3.19s) |
| `npm run build` | Passed; 1,699 modules transformed | 2.26s (Vite 1.97s) |
| `npm run poc:check` | 22 tests passed, none skipped/cancelled | 1.17s (Node test runner 1.057s) |
| `npm ls --all --json` | Passed; no dependency/peer problems | 0.33s |
| `npm audit --json` | Exit 1; 12 affected package entries remain below | 0.95s |

The unit worker cap bounds resource use without changing test selection or
assertions. The fixture POC uses injected responses and temporary loopback HTTP
listeners, including unchanged routing, publication and capture-race assertions.
It does not validate browser captures or a production renderer. Baseline `npm ci`
also passed (302 packages, 12.32s); baseline audit took 4.82s. Timing is local
evidence, not a performance guarantee.

Existing stale Browserslist-data warnings remain. npm 11 also reports esbuild's
postinstall script as not yet covered by its `allowScripts` setting; installation,
typecheck, build and POC succeeded without changing that setting. No backend
tests, database access, provider traffic, live backend probes, `poc:serve`,
`poc:verify`, advisory exploits, Docker actions or live rollout were performed.
Alpine/container runtime and browser smoke checks are not established by this
Linux x64 check. The repo has no configured lint script; coverage was not run.

## Audit findings outside this change

| npm audit snapshot | Critical | High | Moderate | Total affected package entries |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 4 | 15 | 3 | 22 |
| Final | 2 | 9 | 1 | 12 |

These are package-entry counts, not unique advisory counts or confirmed reachable
exploits. Both audits exited 1. The baseline npm feed omitted the newly published
critical Vite advisory and the 6.4.4 regression advisory, so npm's baseline
`vite: high` label was not the security decision source. The primary advisories
above governed the selected floors. Final npm audit no longer lists Vite, Vitest,
esbuild, tinypool, Rollup, PostCSS, picomatch, nanoid, source-map-js or yaml.

All remaining entries are retained for separate, scoped remediation; this change
does **not** make the whole dependency tree audit-clean:

| Remaining package(s) | Severity | Dependency path / advisory IDs from final npm audit |
| --- | --- | --- |
| Swiper 11.2.7 | Critical | Direct application dependency; [GHSA-hmx5-qpq5-p643](https://github.com/advisories/GHSA-hmx5-qpq5-p643). |
| form-data 4.0.2 | Critical | jsdom; [GHSA-fjxv-7rqg-78g4](https://github.com/advisories/GHSA-fjxv-7rqg-78g4), GHSA-hmw2-7cc7-3qxx. |
| Vue / @vue/server-renderer 3.5.13 (two entries) | High | Direct Vue and its server renderer; [GHSA-g2v6-rqmx-r4w6](https://github.com/advisories/GHSA-g2v6-rqmx-r4w6). |
| brace-expansion 2.0.1 | High | Vue test-utils → js-beautify and shared glob/minimatch; [GHSA-v6h2-p8h4-qcjw](https://github.com/advisories/GHSA-v6h2-p8h4-qcjw), GHSA-f886-m6hf-6m8v, GHSA-3jxr-9vmj-r5cp, GHSA-mh99-v99m-4gvg, GHSA-rgw5-rvv9-x895, GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p. |
| browserslist 4.24.5 | High | Autoprefixer; [GHSA-c83g-rgw3-j3cx](https://github.com/advisories/GHSA-c83g-rgw3-j3cx), GHSA-73wf-gq98-2v4g. |
| editorconfig 1.0.4 | High | Vue test-utils → js-beautify; transitive minimatch advisories. |
| glob 10.4.5 | High | js-beautify and Tailwind → sucrase; [GHSA-5j98-mcp5-4vw2](https://github.com/advisories/GHSA-5j98-mcp5-4vw2), GHSA-3g3m-2fjr-6pw4. |
| js-cookie 3.0.5 | High | Vue test-utils → js-beautify; [GHSA-qjx8-664m-686j](https://github.com/advisories/GHSA-qjx8-664m-686j). |
| minimatch 9.0.1 / 9.0.5 (one entry) | High | editorconfig and glob; [GHSA-3ppc-4f35-3m26](https://github.com/advisories/GHSA-3ppc-4f35-3m26), GHSA-7r86-cg39-jmmj, GHSA-23c5-xmqv-rm74, GHSA-g3hv-75wg-m249. |
| ws 8.18.2 | High | jsdom; [GHSA-58qx-3vcg-4xpx](https://github.com/advisories/GHSA-58qx-3vcg-4xpx), GHSA-96hv-2xvq-fx4p. |
| postcss-selector-parser 6.1.2 | Moderate | Tailwind/postcss-nested (separate from PostCSS core); [GHSA-w9m9-85wc-3x92](https://github.com/advisories/GHSA-w9m9-85wc-3x92), GHSA-rj75-hqrm-r3gf. |

## Integration boundary

Integration changes only the frontend image from `node:20-alpine` to
`node:22-alpine` in [Compose](../docker-compose.yml). The existing
[frontend CI](../.github/workflows/frontend-tests.yml) Node 22 selection needs no
version change. Use a current patched 22.x image; this work does not pull or
recreate it. Shared documentation was reconciled by the orchestrator.
No route/blueprint wiring or backend test run is
required by this dependency-only change.

The `/api` proxy, internal `0.0.0.0` Vite listener and
[development loopback defaults](development-networking.md) remain unchanged.
An eventual authorized runtime rollout must refresh the frontend dependency
installation as well as the image; an existing named node_modules volume is not
evidence that the patched lock has been installed. No claim about current live
versions or port bindings follows from this worktree's results.

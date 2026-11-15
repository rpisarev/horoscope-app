# Production prompt-probe prohibition

STAB-015.08c-A implements only the production-denial part of Accepted D6.
STAB-015.08c-B (bounded, auditable development admission) remains pending;
this is not completion of .08c or implementation of all Accepted D1–D8.

**Iteration 5 delta:** `.02c` now additionally denies known paid transport in
both probe entry points, even in explicit development/test mode with SAFE-001
enabled. There is no configuration override for this incomplete-admission blocker.
The mode rules below remain independently necessary. Fake compatibility tests
explicitly isolate the new blocker; denial tests keep it intact. Real diagnostic
transport remains unavailable until `.03c` and `.08c-B` supply the required
bounded, auditable path. See [request-intent contract](request-intent-design.md).

## Enforced boundary

[`openai_prompt_probe.py`](../backend/utils/openai_prompt_probe.py) checks the
current process `APP_DEPLOYMENT_MODE` in both `main()` and `call_openai()`:

| Process mode | Paid probe behavior |
| --- | --- |
| `production` | Denied regardless of whether the global paid gate is `0` or `1`, and regardless of credentials. |
| Missing, empty, or unrecognized | Denied; this diagnostic has no implicit development fallback. |
| Explicit `development` or `test` | Preserves the existing path to the independent SAFE-001 check; this does not authorize real transport. |

Mode values are stripped and lowercased, consistent with existing publication
mode normalization. A Flask configuration snapshot cannot override this process
setting. The main check precedes credential validation and SDK import/construction;
the helper checks on every call, including direct calls and each batch request.
A mode change after main preflight therefore blocks the next request at the
helper. Checks cannot cancel an already in-flight request.

Mode denial raises `ProbeExecutionDenied`, a `PaidExecutionDenied` subclass with
`retryable=False`. Messages are fixed: production is forbidden, or deployment
mode is missing/invalid. They contain no supplied mode, key, prompt, or provider
response. An uncaught CLI denial exits unsuccessfully, as existing SAFE-001
denials do. The standalone module does not import Flask or create an application.

The separate [SAFE-001 policy](../backend/paid_execution_policy.py) is unchanged
and remains independently necessary at both boundaries. Only its exact process
gate value `1` passes that guard. This patch adds no opt-in, fallback, account
budget, or development transport enablement, and does not affect stub workflows.

`--list-profiles` remains read-only in all modes, including missing/invalid modes
and with the global gate denied. It returns before dotenv loading or request
environment-default resolution. It requires no API key, does not import or
construct the OpenAI SDK, and never calls transport. It prints only the static
profile catalog; supplied secrets and deployment-mode values are not echoed.
Generation keeps CLI options ahead of environment/dotenv defaults, then built-in
defaults. The existing dotenv loader keeps `override=False`, so exported
production mode cannot be overwritten by a development dotenv value.

## Development compatibility and authorization

**The retained development/test path is NOT authorized for real transport until
STAB-015.08c-B provides bounded, auditable API-attempt accounting and admission.**
The compatibility tests use a fake SDK only. Explicit mode and SAFE-001 are
necessary code guards, not proof that Accepted D6 development controls exist.

The live paid gate remains unchanged/default-denied. No runtime environment,
dotenv/secrets, services, scheduler state, or databases are changed by this task.
There is no new development permission or automatic publication. Existing probe
SDK retry defaults, batch behavior, and lack of durable request audit remain
limitations for .08c-B; no hard attempt cap or retry guarantee is claimed here.

Existing callers that omitted `APP_DEPLOYMENT_MODE` now fail closed, even when
the paid gate is enabled. Fake tests of the pre-existing non-production path must
set an explicit recognized non-production mode. Production cannot be enabled by
setting the paid gate or supplying a key. These notes are not paid activation
instructions.

## Historical iteration 4 verification

[`test_paid_execution_probe.py`](../backend/tests/test_paid_execution_probe.py)
covers main/helper production denial with global `0`/`1`, missing/invalid modes,
normalization, sanitized nonretryable errors, profile listing with and without
a dummy key, independent SAFE-001 denial, process-versus-Flask authority, and
mode changes after preflight and between batch requests. SDK imports are blocked
for denied/listing paths; permitted test paths use an in-memory fake. Unexpected
network/DNS, application imports, and actual dotenv reads remain forbidden by the
tests. Mock-only cases verify that listing skips dotenv, exported production mode
survives loading, and generation retains CLI/environment option precedence.

The subagent performed AST parsing and diff/whitespace review, without executing
backend tests. The parent ran this selection **serially through the verified
STAB-007 isolated harness**, with its established sanitized environment and guards:

```bash
bash scripts/backend-test.sh tests/test_paid_execution_probe.py tests/test_paid_execution_policy.py tests/test_paid_execution_adapter.py tests/test_paid_execution_lifecycle.py
```

The selection above passed **39 tests in 2.76s**, followed by **750 integrated
backend tests in 76.81s** through the same harness. Both disposable projects
cleaned up. These results are not a runtime rollout. The shared state,
architecture and backlog documents record the integrated checkpoint.

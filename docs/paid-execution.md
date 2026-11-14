# Paid execution gate

`GENERATION_PAID_EXECUTION_ENABLED` is a process-wide opt-in for paid provider
execution. Only the exact environment string `1` enables it. Unset, empty, `0`,
`true`, whitespace-padded values, and every other value deny paid execution.
Compose passes the setting to both backend and scheduler with default `0`.

The source of truth is [`backend/paid_execution_policy.py`](../backend/paid_execution_policy.py).
It uses only the standard library, does not load dotenv or create a Flask app,
and rechecks the process environment on each call to
`require_paid_execution(provider_name)`. The Flask Config boolean is an
informational snapshot, not an override. Setting `app.config` cannot enable
execution while the environment denies it. Publication policy remains separate.

OpenAI is the currently known paid provider. Stub and unknown development fakes
retain their existing behavior; the factory still rejects unsupported production
adapters. Future paid adapters must be registered in the policy's paid-provider
set and call the same guard at their transport boundary with a literal canonical
identity. Returned source/model metadata cannot grant execution permission.

## Boundaries

- Lifecycle preflight checks the selected adapter identity before prompt loading,
  item creation, or provider attempts. Denial can record a failed run with a clear
  `PaidExecutionDenied` message and zero items/attempts; it cannot publish a forecast.
- Queue execution checks the persisted provider before dispatching to lifecycle.
  A claimed denied job becomes failed without creating a generation run. Job
  claiming consumes the existing queue `attempt_count` and sets `started_at`;
  these count a worker claim, not a provider attempt. No `generation_attempts`
  row is created. Job creation and existing count-based limits retain their
  existing semantics, including started-job daily accounting.
- The standalone prompt probe checks before constructing its SDK client and again
  inside `call_openai`, including direct helper invocations. `--list-profiles`
  remains read-only and does not require enablement or a key. The probe CLI adds
  no local flag; its existing API-key requirement remains.
- The OpenAI adapter checks literal `"openai"` on entry and immediately before
  the SDK request, after obtaining the client. Direct adapter invocation and
  mutation of `provider.name` cannot bypass this boundary. SDK retry ownership
  remains as defined in [openai-retries.md](openai-retries.md).

Denial raises `PaidExecutionDenied`, a `RuntimeError` with `retryable=False`.
Preflight denial is not a provider attempt. No retry-loop behavior is changed.
If the process gate changes after preflight, the final transport check must deny
the request; an already-created lifecycle attempt may record that nonretryable
denial. The gate cannot cancel an HTTP request already in flight.

## Existing authorization remains required

Global enablement permits evaluation of existing controls; it does not replace
credentials, package/worker CLI `--allow-openai`, worker opt-in, admin enable/token
and request confirmation, scheduled queue creation opt-in, production publication
capabilities/allowlist, or count-based cost limits. A local CLI flag cannot bypass
a disabled global gate. Direct legacy scheduler execution has no separate local
OpenAI flag; it now reaches the lifecycle global preflight check.

This covers known application paths, not arbitrary external code or other users
of the same API key. It is not account-level budget control. Once enabled, direct
execution still lacks the queue's count limits. The standalone probe retains its
SDK retry defaults and does not acquire lifecycle audit/retry semantics.

## Environment and reload boundary

The gate reads the environment of the process doing the work. A host `.env` edit
does not change a running container's environment, and changing another process's
environment does not change the worker's. New Compose environment values require
the normal separately authorized container configuration reload/recreation; a
restart with unchanged container configuration does not import new Compose values.
Backend, scheduler, and standalone utilities each need their own intended value.
The existing probe dotenv loader runs at CLI startup without overriding exported
values; a direct helper call uses the environment already present in its process.
No reload, restart, recreation, scheduler start, or provider call is part of this
implementation task. Existing published data and public reads are unaffected.

## Verification

The new pure unit tests can run without pytest or its database fixtures:

```bash
python3 -m unittest discover -s backend/tests -p 'test_paid_execution_policy.py' -v
python3 -m unittest discover -s backend/tests -p 'test_paid_execution_probe.py' -v
```

They load service code with in-memory dependencies, block unexpected sockets/DNS,
use a fake SDK, and never create the Flask app or load dotenv secrets. Checks cover
fail-closed values, runtime rechecks, unchanged stub preflight, failed-run/job audit
behavior without attempts/publication, existing local gates, CLI non-bypass, and
probe listing/direct calls. ORM and final adapter regressions run separately through
the disposable database workflow. Tests intentionally executing fake OpenAI paths
have an explicit global opt-in scoped to those tests, not a broad fixture default
that would hide denial coverage.

[`test_paid_execution_lifecycle.py`](../backend/tests/test_paid_execution_lifecycle.py)
is a separate database-backed pytest regression file for the orchestrator's
disposable-database run. It verifies persisted failed-run/job state and a successful
fake-provider path with all opt-ins. Do not include it in host unittest discovery
or run it against development data.

[`test_paid_execution_adapter.py`](../backend/tests/test_paid_execution_adapter.py)
checks direct denial, spoofed adapter identity, a conflicting Flask config snapshot,
rechecking immediately before transport, and honest nonretryable audit after a
post-preflight denial. All transport is fake or forbidden.

Integrated verification (2026-11-14): **126 focused tests** and **315 full backend
tests** passed serially through `scripts/backend-test.sh`; disposable projects
cleaned up. Compose rendering confirmed default `0` and explicit value propagation
to backend and scheduler. This verifies repository behavior, not deployment or
account-level controls. No live process was restarted to apply the new setting.

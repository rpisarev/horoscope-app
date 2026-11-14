# Generation operations report

STAB-015.07b adds a read-only JSON report for an authorized local operator. It
observes published coverage for today and tomorrow, queue counts and age, and the
last known run in one locale/type scope. It does not enqueue, claim, generate,
publish, close stale work, or implement recovery, admission, pause or heartbeat.
The [accepted ADR](adr/STAB-015-generation-execution.md) remains the authority for
the future production architecture.

From `backend/`, in an already authorized application/database environment:

```bash
python utils/generation_operations_report.py
python utils/generation_operations_report.py --locale uk --forecast-type daily
```

The defaults are `ru` and `daily`. Locale/type are exact read filters, not proof
that the generation pipeline supports every requested combination. Supply database
configuration (`DATABASE_URL` or the supported `POSTGRES_*` settings) and
`APP_TIMEZONE` through the process environment. Before importing the application,
the CLI forces `PYTHON_DOTENV_DISABLED=1`; the application configuration guard skips
dotenv loading, including with python-dotenv 1.0.1. The command does not discover
local `.env` files. It does not require provider credentials or enable generation.
Access is protected by local host/container and database
permissions; no HTTP route or public status endpoint is added. Do not expose the
command through an unauthenticated wrapper. Running it against an operational DB
requires the operator's authorization; it is not a routine verification command.

The service API, inside an application context, is:

```python
build_generation_operations_report(
    *, locale: str = "ru", forecast_type: str = "daily",
    now: datetime | None = None,
) -> dict
```

Only tests inject `now`, which must be timezone-aware UTC. There is no CLI clock
or date override. `app.business_date.business_datetime(now)` supplies product
today using `APP_TIMEZONE`; tomorrow is the next calendar date, including month,
year and DST transitions. Operational timestamps are rendered in UTC.

The report envelope contains `schema_version` (1), `observed_at`, `scope`, `state`,
`configuration`, `coverage`, `queue`, `last_known_run`, and `signals`.
`coverage.today` and `coverage.tomorrow` retain the shared read service's coverage
fields, with display redaction described below. Each adds a `deadline` object and
`redacted_sign_count`.

Expected signs come only from current enabled database metadata, ordered by
metadata sort order and key. Only exact-scope published forecasts count; existing
published stubs remain eligible. Drafts and disabled signs do not count. Zero
enabled signs produces `empty_enabled_signs` and an explicit configuration
condition; it never becomes full coverage or the legacy static sign fallback.
This does not change that fallback in generation paths.

Display identifiers are conservatively filtered without changing database lookup
values. Sign keys must match `[a-z][a-z0-9_]{0,31}`; locale/type use their existing
input syntax. Identifiers containing `secret`, `token`, `password`, or `api_key`
(case-insensitive, treating hyphens as underscores) are withheld. Malformed or
suspicious signs become JSON `null` placeholders in expected/published/missing
lists; order, cardinality, numeric counts and coverage/deadline states are retained.
`redacted_sign_count` counts withheld expected signs. Suspicious locale/type values
become `null` in the report, coverage and queue scopes. This is display redaction,
not filtering, renaming, disabling signs or rejecting an otherwise valid exact
query scope. Ordinary custom identifiers remain visible; there is no hardcoded
sign list. The conservative rule may withhold legitimate identifiers containing
these substrings and cannot detect every arbitrary secret embedded in metadata.

The deadline is fixed at **06:00 Europe/Kyiv**, separately from configurable
`APP_TIMEZONE`. With the default timezone, incomplete coverage is `pending` before
06:00 and `missing_after_deadline` at or after 06:00. Full coverage is
`full_current`. `historical_on_time` remains `unknown`: current forecast rows and
publication timestamps cannot reconstruct withdrawals, updates, or historical
enablement. Even full coverage at noon does not prove on-time publication.

Any `APP_TIMEZONE` other than the exact `Europe/Kyiv` setting conservatively
produces `timezone_mismatch`, even if the dates currently happen to agree. Coverage
still uses backend-authoritative business dates; the report leaves deadline `at`
and `reached` null instead of choosing a possibly wrong Kyiv day. Resolving that
mapping is a separate policy/configuration decision. Empty metadata and mismatch
can both appear in `configuration.conditions`.

Queue scope is explicitly the requested locale/type across **all target dates**.
`counts_by_status` contains queued, running, failed, partial_failed, success,
cancelled and unknown counts. Terminal counts describe stored history. `active_count`
is queued plus running. `oldest_queued` and `oldest_active` measure seconds since
the oldest matching `created_at`, not time in status or worker progress. Empty
sets have null timestamp/age; future timestamps have null age and an explicit
`future_timestamp` condition. Unrecognized statuses are aggregated as unknown
without exposing their raw values.

An empty scoped queue only means `no_active_jobs_observed`. It does not mean
globally drained, successful generation, healthy workers or complete coverage.
Jobs that appear blocked retain `blocking_reason=unknown`; freeform stored errors
do not establish quota/pause causes. `last_known_run` is null when absent;
otherwise it selects the greatest persisted started/finished/created timestamp,
then descending run ID, within the same locale/type and all dates. It returns
only ID, date, allowlisted status and timestamps. A successful run never overrides
missing publication coverage.

`signals` separates a successful database read from DB/schema readiness, API
liveness and worker evidence. API/worker liveness, worker progress, worker pause
and provider quota remain unknown. Full schema readiness is not assessed by this
command. There is no durable heartbeat/pause evidence in the current schema, and
the report never calls a provider to probe quota or health.

| Exit | Meaning |
| --- | --- |
| `0` | Today's coverage is full currently, or its deadline is still pending. Not a historical SLO/worker-health verdict. |
| `1` | Today's enabled-sign coverage is incomplete at or after the deadline. |
| `2` | Invalid arguments/configuration/scope, or unavailable report reads/startup. |
| `3` | Report obtained, but empty enabled metadata or timezone mismatch needs attention. |

Errors return only `schema_version`, `state=unavailable`, and an allowlisted
`error.code`: `invalid_arguments`, `invalid_configuration_or_scope`, or
`report_unavailable`. Connection/schema errors are not printed or logged with
DSNs, SQL, exception messages or tracebacks. Normal reports exclude forecast text,
raw payloads, prompts/responses, freeform errors, credentials and worker identities.

Reads use the shared `generation_read_service.read_snapshot()` context manager:
a dedicated PostgreSQL READ ONLY REPEATABLE READ connection, independent of the
caller ORM session. Pending caller work stays unflushed and its transaction is
unchanged. The report performs at most six data SELECTs: two bounded metadata
reads, two bounded published-sign reads, one queue aggregate row and one latest
run row. Shared metadata bounds are 1,000 signs; exceeding the bound fails rather
than presenting truncated coverage. Connection timeout is 2 seconds, statement
timeout 2 seconds and lock timeout 1 second. These are database wait bounds, not a
global DNS/whole-process deadline. Transactions are rolled back and connections
closed by the shared helper. No schema, migration or runtime topology changes are
part of this report.

Tests in `backend/tests/test_generation_operations.py` cover temporal and coverage
boundaries, queue/run observations, report redaction, CLI exits, and SELECT-only
caller-state preservation. They restore changed reference metadata because the
shared harness does not truncate it. Additional malformed-identifier and exact-scope
redaction regressions are in `backend/tests/test_generation_operations_redaction.py`.
All tests, including mocked CLI cases in this
directory, must run through the orchestrator-owned serialized disposable harness:

```bash
bash scripts/backend-test.sh tests/test_generation_operations.py
bash scripts/backend-test.sh tests/test_generation_operations_redaction.py
```

No agent-local database run or live report smoke invocation is required. Shared
read-snapshot tests separately verify transaction isolation and connection policy.

Orchestrator verification on 2026-11-15: **79 tests passed in 4.81s**, comprising
the original 65 cases, two integrated per-job/aggregate coverage comparisons, and
12 metadata-redaction/CLI startup regressions. The sanitized disposable PostgreSQL
project cleaned up. Independent reviews prompted display-only metadata redaction
and consistent pre-import dotenv opt-out; exact query filters/counts remain intact.
Final full-suite evidence is recorded in [CURRENT_STATE](CURRENT_STATE.md).

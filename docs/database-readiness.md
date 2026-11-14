# Database readiness

STAB-015.07a adds `health_bp` in
[`backend/app/health_routes.py`](../backend/app/health_routes.py), registered by
the app factory without a URL prefix. Compose healthchecks remain unchanged;
adding the endpoint does not restart services or apply a deployment policy.

`GET /health/ready` returns HTTP 200 with `{"ready": true}` only when PostgreSQL
answers the revision SELECT and its complete Alembic revision set equals the
heads of the packaged migration scripts. Failure returns HTTP 503 with
`{"ready": false}`. Both responses have `Cache-Control: no-store`. No DSN,
credentials, SQL errors or revision identifiers are returned or logged by the
probe. Missing/empty version tables, old/unknown/extra revisions, unreadable or
empty migration metadata, connection errors and query timeouts fail closed.

The expected heads come from Alembic `ScriptDirectory` at the source-relative
`backend/migrations` path. This reads revision modules without running `env.py`,
upgrade/downgrade functions, schema repair or `create_all()`. All heads must match;
a matching version marker is not an audit of every table/column or permission.
The database uses the same schema/search-path convention as the existing Alembic
environment. Each request reads current revision state; results are not cached.

## Connection and timeout boundaries

The service creates a short-lived SQLAlchemy `NullPool` engine from the configured
application engine's URL, supporting `postgresql+psycopg`. Other drivers (including
the development SQLite fallback) return not-ready. It never checks out from the
application pool, touches the ORM session, flushes pending changes or commits.
Each connection closes after its read-only transaction and the engine is disposed
on success and failure. No per-request background thread or retry loop is used.

Connection arguments force libpq `connect_timeout=2` seconds. PostgreSQL startup
options force `default_transaction_read_only=on`, `statement_timeout=1000` ms and
`lock_timeout=1000` ms. They apply before dialect initialization, the test identity
query and the readiness SELECT; URL options cannot turn those limits off. Other
startup options (such as `search_path`) are preserved. Only at most the number of
expected heads plus one version row is fetched. No application tables are read.

These are **connection-attempt and server-statement limits**, not a strict total
HTTP deadline. libpq may try several configured hosts/addresses; DNS resolution,
OS scheduling and a broken network/connection teardown can exceed those limits.
Dialect initialization and the harness identity check are separate statements,
each subject to the statement timeout. This implementation does not claim that
adding 2 seconds and 1 second gives a whole-probe wall-clock bound. Deployment
request/DNS/network deadlines and health polling frequency remain operator policy;
this endpoint does not install a healthcheck or trigger service restarts.

## Meaning and verification

Ready describes connectivity and the migration marker at the time of the probe.
It does not infer worker/producer progress, provider quota, publication coverage,
the 06:00 deadline, or permission to generate. Public forecast/sign/archive
contracts, paid guards and generation defaults remain unchanged.

The unchanged [STAB-007 harness](testing-safety.md) applies its process-wide
`Engine.engine_connect` identity listener to this new engine, including URL,
database/user/port and run-ID checks before the readiness query. Timeout settings
are passed separately from the unchanged engine URL. Tests must only be run by
the orchestrator through that harness:

```bash
bash scripts/backend-test.sh tests/test_readiness.py
```

Focused tests use a temporary Flask app; an integration regression verifies the
actual app-factory registration and static signs response while DB readiness fails.
Failure/schema cases use fake engines; real SELECT checks use only the guarded
disposable target. They do not alter reference data or the Alembic version table.
The suite includes read-only startup settings, actual server query timeout,
identity-guard coverage, pending-session preservation and no provider calls.
Orchestrator validation on 2026-11-15: **33 readiness tests plus 8 shared-read
tests passed (41 total, 2.82s)** through the sanitized disposable harness, followed
by successful cleanup. Independent reviews found no concrete readiness/wiring
blocker. Later shared-reader additions and full integrated verification are
recorded in [CURRENT_STATE](CURRENT_STATE.md). No live endpoint smoke call,
healthcheck switch or Docker restart was performed.

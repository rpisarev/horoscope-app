# Static demonstration forecasts — MVP-A03

The [versioned dataset](../backend/fixtures/demo-2026-11-15-v1.json) contains static
texts, not model output. Every displayed forecast includes **Демонстраційний текст — не результат AI-генерації**.
The existing API/frontend require no special rendering path.

`demo-2026-11-15-v1` covers `ru/daily`: 2026-11-15 through 2026-11-21,
2026-11-14, and archive dates 2025-12-31, 2026-09-30, 2026-10-31.
2026-11-13 deliberately remains unpublished. Each enabled database sign receives
11 rows (143 with the seeded 13 enabled signs). Unknown enabled signs or empty
metadata cause refusal; disabling a sign does not silently create its rows.

The presentation window is finite. `/api/meta` and the server clock remain real.
After 2026-11-21, prepare/review another version with explicit later dates and
marked text. Import only nonconflicting dates; do not overwrite old datasets,
change the business date, generate content nightly, or run generation utilities.
A new version overlapping existing content is intentionally refused. For example,
the next nonoverlapping dataset can cover 2026-11-22–29: presentation window
2026-11-23–29 plus its previous day 2026-11-22. Do not reinclude already imported
archive dates; those rows remain available from the old version.

## Guarded offline import

Use only the separate stack from [demo-stack.md](demo-stack.md), after its explicit
fresh-cluster bootstrap and migration. The normal backend role cannot import.
The wrapper constructs a dedicated URL from the importer secret. It never reads
host `.env`, generic `DATABASE_URL`, libpq overrides, or OpenAI credentials.

```bash
# Use the same explicit -p / --env-file / -f demo Compose arguments as setup.
docker compose ... run --rm --no-deps demo-import
# Review would_insert, unchanged, dataset/window before authorizing writes.
docker compose ... run --rm --no-deps demo-import --apply
# Repeating the same import reports inserted=0, with timestamps/IDs unchanged.
```

The packaged version is the default. `--dataset /path/to/reviewed.json` selects a
new explicit version packaged in an updated tools image. This is not a public
endpoint or a general import tool for arbitrary production databases.

The [loader](../backend/demo_fixture_import.py) checks the explicit URL's fixed
host/port/database/user and rejects conflicting environment before connecting.
In a read-only transaction it verifies current database, session/current role,
non-elevated privileges, absence of role memberships, and the protected
`demo_control.identity` row and ownership. The expected nonzero instance UUID
must match the bootstrap marker. A name suffix alone is never accepted.
Before INSERT, the write transaction repeats the identity and conflict checks.
The INSERT helper independently validates identity as well. Missing marker,
unknown target, elevated role, modification privileges or existing conflicting
forecast all cause refusal. Exceptions never print driver details or credentials.

Importer privileges are SELECT on sign/forecast data and INSERT on forecasts,
with sequence USAGE; no UPDATE, DELETE, TRUNCATE or generation-table grants.
The transaction is all-or-nothing. Concurrent conflicting inserts fail safely;
there is no unbounded retry. After an uncertain connection failure, dry-run again
before an explicit retry. Exact same-version rows are a no-op; other content,
provenance, or publication state is not overwritten or deleted.

Rows have `source=demo-fixture`, dataset ID/hash and `ai_generated=false` in payload.
`published_at` is the actual database timestamp. Model, prompt, generated_at and
generation-item references remain NULL. No jobs, runs, attempts, request ledger,
token usage or fake generation history are created. Production publication policy
is unchanged; this restricted offline staging import does not call its lifecycle.

## Verification boundary

Run mock guards first (no DB/network):

```bash
python3 -B -m unittest discover -s backend/safety_tests -p test_demo_fixture_guard.py -v
```

Only through the [STAB-007 harness](testing-safety.md):

```bash
bash scripts/backend-test.sh tests/test_demo_fixtures.py
```

Those SQL tests use the harness-owned disposable DB and explicitly mock the
separate target guard; they do not pretend that `horoscope_test` is a valid demo
instance. Final integration additionally runs the unpatched CLI guard against the
separate disposable demo, including actual database roles/marker, dry-run, repeat
no-op, public JSON/archives and zero generation history. Never use the development
DB for either positive or negative tests.

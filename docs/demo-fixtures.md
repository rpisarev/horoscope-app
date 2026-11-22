# Static demonstration forecasts

Both packaged datasets contain static forecasts with a visible demo marker in the text.
The importer writes only the signs currently enabled in database metadata. An empty
enabled set or an enabled sign absent from the selected dataset causes refusal.

| Dataset | Published daily forecasts | Deliberately unpublished | New rows with all 13 seeded signs enabled |
| --- | --- | --- | ---: |
| [V1, CLI default](../backend/fixtures/demo-2026-11-15-v1.json) | Russian, Nov 14–21, 2026 and archive dates Dec 31, 2025, Sep 30 and Oct 31, 2026 | Nov 13, 2026 | 143 |
| [V2, explicit selection](../backend/fixtures/demo-2026-11-22-v2.json) | English, Ukrainian and Russian, Nov 22–24, 2026 | Nov 25, 2026 in all three locales | 117 |

V1 retains its original bytes, Russian locale, per-sign text and historical
Ukrainian marker **Демонстраційний текст — не результат AI-генерації**.
V2 adds three rows for each enabled sign/day. Each group in the JSON contains a
distinct English original and Ukrainian and Russian translations of that original.
Their respective opening lines are **Demo forecast.**, **Демонстраційний прогноз.**
and **Демонстрационный прогноз.**

Every V2 forecast has its own `(sign_key, target_date, locale, forecast_type)` key.
Its payload records `content_role` as `original` or `translation`, the dataset ID
as `source_version`, and the canonical English `source_key`. For example, all
three Aries rows for Nov 22 refer to
`{"sign_key":"aries","target_date":"2026-11-22","locale":"en","forecast_type":"daily"}`.
Their `source_text_sha256` hashes the exact stored English forecast text as UTF-8,
including its marker, punctuation and two line feeds before the body. The separate
`dataset_sha256` hashes the entire fixture file. The loader checks each source
digest, full locale coverage and unique keys before connecting. It checks that
each sign has a different marked text on each date within a locale.
A published row on the V2 missing date in the active scope also
causes preflight to refuse the import.

The two versions can coexist. Importing V2 preserves V1 rows, timestamps and payloads.
The presentation dates are fixed in each file. The business date still comes from
`/api/meta`. Future demonstrations can package a reviewed version for new dates.

## Guarded offline import

Use only the separate stack from [demo-stack.md](demo-stack.md), after its explicit
fresh-cluster bootstrap and migration. The normal backend role cannot import.
The wrapper constructs a dedicated URL from the importer secret. It never reads
host `.env`, generic `DATABASE_URL`, libpq overrides, or OpenAI credentials.

Using the `demo` shell function defined in the runbook, omit `--dataset` for
V1. Select V2 by its packaged path on both the preview and the write command.

```bash
demo --profile tools run --rm --no-deps demo-import --dataset /app/fixtures/demo-2026-11-22-v2.json
# After reviewing the dataset, window and expected counts on the approved demo instance
demo --profile tools run --rm --no-deps demo-import --dataset /app/fixtures/demo-2026-11-22-v2.json --apply
```

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
python3 -B -m unittest discover -s backend/safety_tests -v
```

Only through the [STAB-007 harness](testing-safety.md):

```bash
bash scripts/backend-test.sh tests/test_demo_fixtures.py tests/test_multilingual_demo_fixtures.py
```

The SQL tests use the harness-owned disposable DB and mock the separate demo
target guard. They exercise dry-run, conflicts, repeat imports, preservation of
V1 rows, translation provenance, public reads, archive availability and empty
generation history. The original V1 demo-stack acceptance used a separate
disposable demo with the real bootstrap marker and roles.

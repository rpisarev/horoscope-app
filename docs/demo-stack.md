# Isolated demo stack

[`compose.demo.yml`](../compose.demo.yml) is standalone. Never combine it with
`docker-compose.yml`, reuse the development project/volume/secrets, or operate it
from the live bind-mounted checkout. Runtime services are exactly `proxy`,
`backend`, and `db`; only the proxy publishes host ports. This serves curated
published demo fixtures. It has no scheduler, worker, generation credentials,
automatic migration, or startup fixture import.

The release images use `backend/Dockerfile.release` (application `/app`, port
8000) and `frontend/Dockerfile.release` (Caddy and built frontend `/srv`). The
backend uses `demo_readonly`, production publication policy with an empty provider
allowlist, disabled paid/admin/worker gates, and no external network route. Stub
selection does not authorize production generation. SAFE-001 and application
publication rules remain unchanged; existing published fixture reads remain valid.

## Proxy contract

[`Caddyfile`](../deploy/demo/Caddyfile) authenticates every HTTPS application
request before routing, including `/api`, `/api/*`, assets, health, and sitemaps.
Authenticated `/api/admin`, `/api/admin/*`, `/admin`, and `/admin/*` receive 404.
API paths retain their prefix; upstream 400/404/503 responses are not converted
to frontend HTML. `/assets` and file-like paths receive a static 404 when missing.
Other paths fall back to the SPA, whose own route validators handle invalid pages.
All responses through this route carry `X-Robots-Tag: noindex, nofollow, noarchive`.
Public HTTP is only Caddy's automatic HTTPS redirect, never application content;
send Basic Auth credentials only over HTTPS.

The wrapper reads a bcrypt hash from `/run/secrets/demo_basic_auth_hash`, validates
its format, and exports it only into the Caddy process. There is no plaintext
password or hash in Compose, the image, or tracked configuration. Caddy's admin
endpoint and configuration persistence are disabled. Do not use `set -x`, dump
the process environment, or run Caddy with `--environ`. Basic Auth is removed from
upstream requests after proxy authentication.

The ordering follows Caddy's [literal route ordering](https://caddyserver.com/docs/caddyfile/directives/route)
and [Basic Auth environment placeholders](https://caddyserver.com/docs/caddyfile/directives/basic_auth).

## Database identity and roles

The target is fixed to service `db:5432`, database `horoscope_demo`. Setup checks
the actual database/current user/session user, not a database-name suffix.
`demo_control.identity` contains exactly one row:

| Column | Value |
| --- | --- |
| `id` | `1` (primary key with singleton check) |
| `purpose` | `horoscope-demo` |
| `contract_version` | `1` |
| `instance_id` | Operator-generated, nonzero UUID for this instance |
| `database_name` | `horoscope_demo` |
| `importer_role` | `demo_importer` |

`demo_owner` owns the database, public schema, marker schema/table, and migrated
objects. Readonly/importer roles cannot create or modify the marker. They have no
superuser, create-role, create-database, replication, bypass-RLS, or membership
privileges. No runtime role owns application tables.

| Role | Credential available to | Authority |
| --- | --- | --- |
| `demo_bootstrap` | PostgreSQL and explicit bootstrap tool | Dedicated fresh-cluster administrator; never backend/importer |
| `demo_owner` | Bootstrap and initial migration tools | DDL/migrations; never runtime backend |
| `demo_importer` | Bootstrap and import tool | SELECT `forecasts`/`zodiac_signs`/marker; INSERT `forecasts`; USAGE only on forecast ID sequence |
| `demo_readonly` | Bootstrap and runtime backend | SELECT `zodiac_signs`, `forecasts`, `prompt_versions`, `alembic_version`, marker; default transactions read-only |

There are no importer UPDATE/DELETE/TRUNCATE or lifecycle/audit grants. No broad
table/default SELECT grants exist. Functions created by the owner do not gain
PUBLIC EXECUTE by default. PostgreSQL privileges, not just the readonly transaction
default, prevent runtime writes. A future schema revision needs its own reviewed
role grants.

Bootstrap requires an explicit CLI confirmation and a fresh cluster containing
only the PostgreSQL template databases, `postgres`, the `demo_bootstrap` user
(plus built-in `pg_*` roles), and an empty public schema. It refuses existing
databases, roles, schemas, or public objects before DDL. It does not run as a
PostgreSQL init hook or application startup action.

The initial migration tool checks identity/ownership in a read-only transaction
and refuses existing public objects before invoking Alembic. It applies the
packaged head, then grants only the listed permissions. **It is initial setup,
not a generic upgrade or rollback tool.** A repeat or partial setup failure is
refused and requires operator inspection; never bypass it or delete a volume to
make the check pass. Role creation and database creation cannot share one atomic
transaction, so a failed bootstrap can leave a partial target.

## Secret preparation and clean invocation

These are operator steps for a separately approved new demo instance. Do not run
them against development. Requirements: Docker Compose >=2.24.4 (local override
uses [`!override`](https://docs.docker.com/reference/compose-file/merge/)), release
images, OpenSSL, and Caddy's CLI for interactive password hashing.

Use a dedicated absolute directory outside every build context. Protect the
directory with mode `0700`; make all mounted password/hash files `0444` so the
backend and setup tools running as UID/GID `10001:10001` can read their secrets.
Tools retain `cap_drop: ALL`, `no-new-privileges`, and a read-only filesystem.
Database administrator authority comes from the bootstrap credential, not the
container UID. UID 0 with all capabilities dropped cannot bypass a host owner's
`0600` file permissions; changing UID alone does not make that file readable.
Compose file-backed secrets retain host
file permissions; declaring `mode` in Compose does not fix unreadable `0600`
files. Only the exact secret files listed per service are mounted, not the
directory. The owner-only host directory prevents other local users traversing
to these readable files. Alternatively, provision an exact UID-owned readable
file appropriate for each container; do not mount owner/importer credentials in
the backend.

```bash
demo_secrets=/absolute/private/horoscope-demo-secrets
install -d -m 700 "$demo_secrets"
umask 077
for role in admin owner importer readonly; do
  openssl rand -base64 32 > "$demo_secrets/${role}_password"
done
# Prompts interactively; the plaintext must not be put on a command line.
caddy hash-password --algorithm bcrypt > "$demo_secrets/basic_auth_hash"
chmod 444 "$demo_secrets"/*
python3 -c 'import uuid; print(uuid.uuid4())'
```

Record the generated instance UUID in the operator's private configuration. Keep
all credentials out of Git, command arguments, logs, and issue reports. These are
database/authentication credentials only; no provider keys are needed.

From the isolated checkout, define an explicit invocation (replace the example
values; keep a unique project name). Clean environment plus `--env-file /dev/null`
prevents accidental root `.env`, provider, Compose-file, or project overrides:

```bash
demo() {
  env -i PATH="$PATH" \
    DEMO_HOST=localhost \
    DEMO_SECRETS_DIR="$demo_secrets" \
    DEMO_EXPECTED_INSTANCE_ID=REPLACE_WITH_GENERATED_UUID \
    DEMO_LOCAL_HTTPS_PORT=8443 \
    docker compose --env-file /dev/null -p horoscope-demo-check-unique \
      -f compose.demo.yml -f compose.demo.local.yml "$@"
}
demo config --quiet
demo --profile tools config --quiet
```

`compose.demo.local.yml` publishes only `127.0.0.1:8443` (configurable via
`DEMO_LOCAL_HTTPS_PORT`) and uses `tls internal`. PostgreSQL data and Caddy's
certificate/config storage use tmpfs. Removing/stopping this disposable setup
loses its data and CA; record/export the local public root certificate when needed.
Named volume declarations in the base file are unused by this override.

For a persistent hosted demo, omit the local override, set the real `DEMO_HOST`,
select a dedicated project, and explicitly set `DEMO_BIND_IP=0.0.0.0` if intended.
The base defaults to loopback ports 80/443 and separate project-scoped named
volumes. DNS/firewall/ACME reachability, backups, secret rotation, and hosting
approval remain operator responsibilities; do not enable provider execution.

## Explicit setup and checks

After the parent/operator coordinates a new isolated instance:

```bash
demo build backend proxy
demo up -d db
demo --profile tools run --rm demo-bootstrap --confirm-new-isolated-cluster
demo --profile tools run --rm demo-migrate
# Inspect available fixture-import arguments; this does not import data.
demo --profile tools run --rm demo-import --help
```

Import approved curated fixtures through `demo-import` before starting the web
services. The wrapper executes `python -m utils.import_demo_fixtures`, forwarding
its explicit dry-run/apply arguments. It builds `DEMO_FIXTURE_DATABASE_URL` from
the importer secret in process memory and supplies `DEMO_EXPECTED_INSTANCE_ID`,
`DEMO_EXPECTED_DATABASE=horoscope_demo`, and `DEMO_EXPECTED_ROLE=demo_importer`.
Generic `DATABASE_URL`, `POSTGRES*`, or `PG*` inputs are refused. The importer
checks marker/role/session identity itself and owns fixture validation and exact
no-op/conflict handling. It does not invoke generation or publication services.

```bash
demo up -d backend proxy
demo ps
demo cp proxy:/data/caddy/pki/authorities/local/root.crt /tmp/horoscope-demo-root.crt
# Use the local CA, not a permanent browser TLS bypass.
curl --cacert /tmp/horoscope-demo-root.crt -i https://localhost:8443/api
curl --cacert /tmp/horoscope-demo-root.crt --user demo -i https://localhost:8443/api/meta
```

Acceptance checks belong to the parent/operator on this isolated target:

- Unauthenticated `/`, `/assets/missing.js`, `/api`, `/api/signs`, `/health/ready`,
  and `/sitemap.xml` return 401. Authenticated admin paths return 404.
- Authenticated published forecast returns its existing JSON; missing/unpublished
  forecast keeps `404 forecast_not_published`; malformed API parameters keep 400.
- A missing asset returns 404, while explicit frontend deep links return the SPA.
- Readiness returns 200 only with the packaged schema. Public API aliases and
  publication behavior are unchanged.
- Direct database checks prove marker ownership and INSERT-only/readonly grants,
  deny forbidden mutations, and verify exact importer rerun/conflict behavior.
- `demo ps` shows only three runtime services and only proxy ports. Backend/db
  have no published ports; tools exit instead of remaining runtime services.

Stop only the exact isolated project using `demo down`. Do not add `-v` as routine
cleanup; the local override already avoids persistent data storage. Never use
the unqualified development Compose command or remove shared Docker volumes.

## Verification boundaries

`python3 -B -m unittest discover -s deploy/demo -p test_tools.py -v` tests setup
refusals with mocks and renders base/tools/local Compose models with dummy inputs.
It never opens a database connection or starts a container. Shell syntax is checked
with `sh -n deploy/demo/caddy-entrypoint.sh`. Actual image/Caddy validation,
bootstrap/migrations/role enforcement, fixture import and browser checks require
the separately coordinated isolated integration run. Mock/config checks do not
claim those runtime results. Database-backed regression tests remain serialized
through the parent-owned STAB-007 harness.

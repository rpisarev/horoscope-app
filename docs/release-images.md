# MVP-A01 release images

These images package the application independently of the development Compose
stack. They do not deploy services, start generation, initialize a database or run
migrations. The existing development Dockerfile and Compose behavior are unchanged.

## Build interface

From an isolated repository checkout, use the service directories as contexts:

```bash
docker build -f backend/Dockerfile.release -t horoscope-backend:release backend
docker build -f frontend/Dockerfile.release -t horoscope-frontend:release frontend
```

Each Dockerfile has its own positive context allowlist. Docker's
[Dockerfile-specific ignore rules](https://docs.docker.com/build/concepts/context/#dockerignore-files)
take precedence over a directory's ordinary `.dockerignore`. Use BuildKit, retain
these filenames and do not substitute the repository root as a build context.
Neither build needs secrets, application environment variables or registry
credentials. `.env` variants, credentials, tests and artifacts are excluded even
inside allowed source directories. New runtime asset types require an explicit
allowlist change.

## Backend contract

- Python 3.12, working directory `/app`, UID/GID `10001:10001`, port `8000`.
- [Gunicorn 27.0.1](https://pypi.org/project/gunicorn/27.0.1/) is pinned in the
  existing requirements file and supports Python 3.12. The shared dependency
  list still includes the existing development/test packages.
- Gunicorn invokes [`wsgi:create_app()`](../backend/wsgi.py) using its supported
  [factory syntax](https://gunicorn.org/run/), with two synchronous workers, no
  preload or reload, and logs on stdout/stderr. Factory initialization occurs
  independently in each worker. Importing `wsgi` does not create an app.
- Source files remain root-owned. The process needs writable `/tmp` for worker
  temporary files; `/app` does not need a source bind mount or write permission.
- Packaged files are `app/`, Python utilities, migrations, `alembic.ini`, the two
  paid-policy modules, WSGI entry point and requirements. `tasks.py`, the
  development `run.py`, repository tests, local databases and secrets are absent.
- `APP_DEPLOYMENT_MODE=production`, `PYTHON_DOTENV_DISABLED=1`, `FLASK_DEBUG=0`,
  `ADMIN_API_ENABLED=0`, `GENERATION_PAID_EXECUTION_ENABLED=0` and
  `GENERATION_JOB_WORKER_ENABLED=0` are image defaults. Existing publication and
  paid-admission enforcement is unchanged; image packaging grants no execution
  permission. Runtime configuration remains the deployment owner's responsibility.

Supply an explicit PostgreSQL target through the existing configuration interface;
the release image does not provide DB credentials or provision a database. Use a
read-only database role for the public API. Any required secret file must be
readable by UID 10001. The application factory registers its normal routes but
does not start a scheduler or migrate the database. Packaged migrations are
required by `/health/ready`; an explicit migration command is a separate operator
action, never part of the image startup command.

Gunicorn command-line flags take precedence over `GUNICORN_CMD_ARGS`. To change
the fixed worker count/bind address, override the complete command in the
integration configuration. No Docker healthcheck is added: the parent stack owns
probe selection, routing and readiness timing.

The parent will add exact allowlist/COPY entries for `demo_fixture_import.py`,
`fixtures/` and any offline bootstrap script after those files are integrated.
This image already supplies Python and psycopg. It has no importer placeholder,
fixture data or source bind mount; those integration additions require a rebuild.

## Frontend contract

The build stage uses Node 24 Alpine, `npm ci` against the committed lockfile and
`npm run build`. The final stage is the official `caddy:2.11.9-alpine` image with
only compiled frontend output copied to `/srv`; it contains no application source,
Node/npm, dependencies from the build stage, tests or `.env` files.

The included [`Caddyfile.release`](../frontend/Caddyfile.release) serves static
files on port 80 with root `/srv`. It intentionally contains only static hosting.
The parent stack mounts its reviewed Caddyfile read-only at
`/etc/caddy/Caddyfile`, the path used by the image command and the
[official Caddy image](https://hub.docker.com/_/caddy). That mounted configuration
owns SPA fallback, `/api` and root sitemap proxying, health routing, TLS and
headers. The static-only default does not implement those integration routes.
Vite's development proxy configuration is not a production proxy.

The Caddy base image's user, exposed ports and `/data`/`/config` conventions remain
unchanged. Port publishing, writable locations and runtime hardening belong to
the parent stack. There are no frontend build arguments for secrets or API keys.

## Verification boundary

Run the focused context regression check from the repository root:

```bash
python3 -B tests/release_images/check_contexts.py
```

It exports synthetic scratch build contexts using the actual ignore policies,
checks exact allowed files and rejects nested secret/test/artifact canaries. It
uses the local Docker socket and a clean client configuration, without registry
pulls, RUN instructions, application imports or runtime containers. In particular,
directory negations ending in `/` must not be added: Docker discards the trailing
slash, which can admit unrelated files beneath an allowed directory.

Image builds and static/image-content checks are separate from runtime evidence.
The parent owns serialized STAB-007 database tests, container startup, Caddy
routing/browser checks, fixture integration and deployment decisions. Do not run
the development Compose stack to verify these images.

Python and Node base tags track their selected major/minor release lines; Caddy
and Gunicorn are version-pinned. Image digests and the existing loosely pinned
Python transitive dependencies are not locked by this change.

### MVP-A01 verification, 2026-11-15

Both release image builds passed on the local Linux builder. Frontend `npm ci`
and Vite build ran in the Node 24 Alpine stage; 1,699 modules compiled. Existing
Browserslist age and npm/esbuild install-script notices remain. The corrected
context policies passed the scratch-export regression: 11 expected backend files
and 13 expected frontend files, with all 129 backend and 103 frontend negative
canaries excluded.

Static inspection of saved image layers confirmed exactly 59 application files
under backend `/app`, readable but not writable by runtime UID/GID 10001, and
29 compiled frontend files under `/srv`. Backend image configuration has the
expected WSGI command, production/paid-disabled/dotenv-disabled defaults and port;
frontend configuration uses the external Caddyfile path and contains no Node/npm,
build-stage dependencies, Vue/TypeScript source or source maps. Python AST,
relative documentation links and diff whitespace checks passed.

No application container startup, WSGI runtime smoke, DB-backed suite, frontend
unit/typecheck run, browser check or live-stack change was performed in MVP-A01.
Those runtime/integration checks remain with the parent; successful image builds
do not establish them.

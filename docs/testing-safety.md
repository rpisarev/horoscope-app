# Disposable backend test runner

Run from the repository root, including an isolated worktree:

```bash
python3 -B -m unittest discover -s backend/safety_tests -v
bash scripts/backend-test.sh
```

The first command uses only Python's standard library. It does not import the
application or `backend/tests/conftest.py`, connect to a database, or invoke real
Docker. Sockets/DNS fail under mocks; shell tests substitute a fake Docker binary.
Run these negative checks before the database suite. The second command builds an
image and creates a disposable PostgreSQL cluster, so it belongs to the operator
authorized to run database tests. CI follows the same order.

Optional selectors are existing positive file/node IDs, for example:

```bash
bash scripts/backend-test.sh tests/test_config.py tests/test_openai_provider.py
bash scripts/backend-test.sh tests/test_config.py::test_read_secret_file_returns_none_for_missing_path
```

No arguments runs the full `backend/tests` suite. Flags, expressions, traversal,
symlinks, arbitrary paths and parameterized node suffixes are rejected before
Docker. Select a whole file/function for parameterized cases. This prevents
selectors from disabling conftest or loading alternative pytest configuration.

## Isolation and cleanup

[The runner](../scripts/backend-test.sh) uses only
[compose.backend-tests.yml](../compose.backend-tests.yml), a generated
`horoscope-test-<32-hex-run-id>` project, and the local daemon socket
`/var/run/docker.sock`. Remote Docker contexts and rootless daemon sockets are
not supported by this harness. Requirements are Bash, Python 3, Docker and a
Compose version supporting `up --wait` and Dockerfile-specific ignore files.

The project has only `test-db` and `test-runner`. PostgreSQL 17 stores its data
on tmpfs. There are no host ports, external/shared networks, bind mounts,
secrets, persistent volumes, API services or schedulers. The network is internal.
The runner filesystem is read-only with a writable `/tmp` for pytest fixtures.
Source is baked into a dedicated test image using
[Dockerfile.tests](../backend/Dockerfile.tests); its
[context allowlist](../backend/Dockerfile.tests.dockerignore) excludes `.env`,
`.env.*` and secrets at every depth. The runtime disables dotenv before importing
application configuration. Changes to the development checkout are never mounted.

Image build/dependency download may use the network; test execution has only the
private test network. No operator credentials are injected into the build or test
containers. The Docker client retains its normal HOME for local daemon/client
operation; no HOME files are mounted in containers.

An EXIT trap removes only the generated project's containers and network using
`down --timeout 10`. It never passes `-v`, prunes volumes, drops an existing DB,
or operates on the development Compose project. Tmpfs contents disappear with
the DB container. Cleanup failures produce a nonzero result. An uncatchable kill
or daemon failure can leave the printed project behind; remove that exact project
with the same dedicated Compose file and without `-v`. Do not use development
Compose cleanup commands. Test build images/cache may remain.

`KEEP_TEST_DB` and `ALLOW_PYTEST_ON_DEV_DB` are rejected, even when empty or `0`.
There is no development bypass, SQLite fallback or retained-database mode.
Older README examples of those workflows no longer describe this harness.

## Database identity and precedence

Application configuration normally resolves `DATABASE_URL` first, then PostgreSQL
fields (with `POSTGRES_PASSWORD_FILE` before `POSTGRES_PASSWORD`), then SQLite.
Overriding only `POSTGRES_DB` cannot safely select a test target.

Host preflight rejects any inherited `DATABASE_URL`, `POSTGRES_*`, `PG*`,
`COMPOSE_*`, `DOCKER_*`, `PYTEST_*`, run-id or unknown `TEST_*` overrides, including
empty values. An explicitly supplied deployment mode must be `test`, and an
explicit provider must be `stub`. No rejected values are printed. Compose runs
with an environment allowlist and `--env-file /dev/null`; the repository's real
`.env` and secret files are neither needed nor loaded.

The fixed identity is driver `postgresql+psycopg`, host `test-db`, explicit port
`5432`, user `test_runner`, password `dummy-test-db`, and DB `horoscope_test`.
These are public disposable test credentials, not credentials for any other DB.
Custom database names must match `horoscope_test_<lowercase_alphanumeric_suffix>`
(underscore-separated suffixes supported, total length at most 63), with explicit
matching identity:

```bash
TEST_DB_NAME=horoscope_test_ci \
TEST_DB_IDENTITY=postgresql+psycopg://test_runner:dummy-test-db@test-db:5432/horoscope_test_ci \
bash scripts/backend-test.sh
```

The runtime must receive the complete matching runner-owned `DATABASE_URL` and
PostgreSQL fields. It rejects password files, libpq routing overrides and
conflicts. It checks the resolved SQLAlchemy URL's driver, host, port, database,
user, password and absence of query routing options. A fresh server is tagged
with the generated run ID. Every newly opened SQLAlchemy connection must match
`current_database()`, `current_user`, `inet_server_port()` and the server's
`horoscope.test_run_id` before callers receive it, including Alembic before DDL.
This read-only identity query is rolled back before caller transactions begin.

Fixtures revalidate configuration and the engine URL before cleanup, then check
actual identity on the same session connection used for TRUNCATE. They retain
seed/reference tables. Knowing a test-like DB name alone never authorizes cleanup.

## No paid calls and credential policy

OpenAI/admin environment credentials start absent. Only these exact dummy tokens
may be explicitly set by tests: `test-key`, `test-api-key`, `test-key-never-used`,
`dummy-test-token`, `unit-test-fake-key`, or empty. Arbitrary `test-` prefixes are
not accepted. Tests can still exercise production policy, fake clients and
`httpx.MockTransport`; none requires provider network access.

Before application/test imports a process-wide Python audit hook blocks sockets
and DNS except the validated DB host/resolved addresses at port 5432. It also
blocks child processes and non-dummy credential assignments. Violations are
latched before raising a BaseException-derived failure, so provider error handlers
cannot convert them into a successful test; a swallowed violation still forces
the final pytest exit code to fail. Conftest and the runner share one guard module
and install it once. Temporary environment mocks within individual tests remain
possible; identity is revalidated before the next destructive fixture operation.

Python hooks do not intercept arbitrary native-code networking (including libpq).
The internal Docker network supplies that additional containment. This is a guard
against accidental test misconfiguration, not a sandbox for hostile Python code.
Direct raw pytest outside this validated environment fails before app setup.

## Review and verification contract

Review guard negatives and `bash -n scripts/backend-test.sh` first, then let one
authorized operator run the isolated harness serially. Record the exact selectors,
test result, generated project and cleanup result. Do not infer that a passing
mock suite proves PostgreSQL/container integration; that requires the authorized
disposable run. No real provider credentials or generation commands are needed.

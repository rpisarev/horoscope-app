#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Preflight precedes EVERY Docker invocation, including config/build/cleanup.
# Isolated Python mode prevents PYTHONPATH/user-site injection; no app import.
validated="$(python3 -I -B "$ROOT/backend/test_db_guard.py" host "$@")"
mapfile -t identity <<< "$validated"
test_db_name="${identity[0]}"
test_db_identity="${identity[1]}"
test_run_id="${identity[2]}"
project="horoscope-test-$test_run_id"

compose() {
  # No host keys, POSTGRES/PG settings, Compose overrides, proxies or dotenv.
  # Only the local Docker daemon is supported.
  env -i PATH="$PATH" HOME="$HOME" \
    TEST_DB_NAME="$test_db_name" TEST_DB_IDENTITY="$test_db_identity" \
    TEST_DB_RUN_ID="$test_run_id" \
    docker --host unix:///var/run/docker.sock compose \
    --env-file /dev/null --project-name "$project" \
    --file "$ROOT/compose.backend-tests.yml" "$@"
}

compose config --quiet
compose build test-runner

cleanup() {
  status=$?
  trap - EXIT
  if ! compose down --timeout 10; then
    echo "Disposable test project cleanup failed: $project" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Disposable test project: $project; database: $test_db_name"
compose up --detach --wait test-db
compose run --rm --no-deps test-runner "$@"

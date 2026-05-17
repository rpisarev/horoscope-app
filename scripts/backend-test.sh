#!/usr/bin/env bash
set -euo pipefail

TEST_DB_NAME="${TEST_DB_NAME:-horoscope_test}"

if [[ "$TEST_DB_NAME" == "horoscope" ]]; then
  echo "Refusing to run tests against the default development database: $TEST_DB_NAME"
  exit 1
fi

if [[ ! "$TEST_DB_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "Invalid TEST_DB_NAME: $TEST_DB_NAME"
  echo "Use only letters, numbers and underscores, and do not start with a number."
  exit 1
fi

docker compose up -d db

docker compose exec -T db sh -lc '
  until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    sleep 1
  done
'

cleanup() {
  if [[ "${KEEP_TEST_DB:-0}" == "1" ]]; then
    echo "Keeping test database: $TEST_DB_NAME"
    return 0
  fi

  docker compose exec -T db sh -lc "dropdb --force -U \"\$POSTGRES_USER\" --if-exists \"$TEST_DB_NAME\"" || true
}

trap cleanup EXIT

docker compose exec -T db sh -lc "dropdb --force -U \"\$POSTGRES_USER\" --if-exists \"$TEST_DB_NAME\""
docker compose exec -T db sh -lc "createdb -U \"\$POSTGRES_USER\" \"$TEST_DB_NAME\""

docker compose run --rm \
  -e POSTGRES_DB="$TEST_DB_NAME" \
  backend sh -c "alembic upgrade head && pytest -q"
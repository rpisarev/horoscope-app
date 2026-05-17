# Horoscope App

Vue + Flask application for a dynamic horoscope website.

The frontend/UI is mostly formed. The current development focus is backend lifecycle: PostgreSQL storage, Alembic migrations, scheduled forecast generation, provider abstraction, generation audit logs, retry-friendly status handling, and future OpenAI/local-LLM integration.

Current branch context:

```text
feature/lifecycle
```

## Current development setup

The local development environment runs through Docker Compose.

Services:

```text
frontend   Vue/Vite dev server
backend    Flask API
scheduler  APScheduler process for forecast generation
db         PostgreSQL 17 Alpine
```

Start the app:

```bash
docker compose up --build
```

After startup:

```text
frontend: http://localhost:5173
backend:  http://localhost:8000
```

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose logs -f scheduler
docker compose logs -f db
docker compose down
docker compose down -v
```

`docker compose down -v` removes the local PostgreSQL volume and therefore deletes the local dev database.

## PostgreSQL dev database

The app uses PostgreSQL in Docker for local development.

The database container uses a named volume:

```text
postgres_data
```

Inside Docker network, backend and scheduler connect to PostgreSQL through:

```text
db:5432
```

From the host machine PostgreSQL is exposed as:

```text
localhost:5432
```

if the port is not already occupied.

## Local secrets

The PostgreSQL password is stored as a Docker secret-style file and must not be committed.

Create local secret:

```bash
mkdir -p secrets
touch secrets/.gitkeep
openssl rand -base64 32 > secrets/postgres_password.txt
chmod 700 secrets
chmod 600 secrets/postgres_password.txt
```

Expected git behavior:

```text
committed:     secrets/.gitkeep
not committed: secrets/postgres_password.txt
not committed: .env
```

Check ignore rule:

```bash
git check-ignore -v secrets/postgres_password.txt
```

## Backend configuration

Backend config resolves database connection in this order:

1. use `DATABASE_URL` if it is set;
2. otherwise build PostgreSQL URI from:
   - `POSTGRES_HOST`
   - `POSTGRES_PORT`
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD_FILE`
3. fallback to local SQLite:

```text
sqlite:///db.sqlite3
```

In Docker Compose development mode, PostgreSQL with secret file is the expected path.

## Migrations

Database schema is managed by Alembic.

Backend container applies migrations before starting Flask:

```bash
alembic upgrade head && python run.py
```

The old `db.create_all()` flow is no longer the working schema-management path.

Current migrations:

```text
0001_initial_schema
0002_add_generation_attempts
```

Check current migration:

```bash
docker compose exec backend alembic current
```

Expected current head:

```text
0002_add_generation_attempts (head)
```

Show migration history:

```bash
docker compose exec backend alembic history
```

Expected history:

```text
0001_initial_schema -> 0002_add_generation_attempts (head), add generation attempts
<base> -> 0001_initial_schema, initial schema
```

## Database schema overview

Main tables:

```text
zodiac_signs
prompt_versions
forecasts
generation_runs
generation_items
generation_attempts
```

### `zodiac_signs`

Stores zodiac metadata used by backend and future API improvements.

The current seed includes 13 signs, including:

```text
ophiuchus
```

Important note: signs are important for routing, DB uniqueness, archive display, and frontend pages. They are intentionally not passed into the text generation provider as prompt content.

### `prompt_versions`

Stores prompt templates and metadata.

Current initial prompt version:

```text
daily-ru-v1
```

The prompt is sign-agnostic: it instructs the generator to create a universal daily forecast and not mention any zodiac sign.

### `forecasts`

Stores published or non-published forecast records.

Important fields:

```text
id
sign_key
target_date
locale
forecast_type
title
text
payload
status
source
model_name
prompt_version_id
generation_item_id
created_at
updated_at
generated_at
published_at
```

Unique constraint:

```text
sign_key + target_date + locale + forecast_type
```

This means there is one current forecast slot for one sign, one date, one locale, and one forecast type.

### `generation_runs`

One generation run represents one scheduled, manual, retry, or on-start generation process.

Important fields:

```text
run_type
 target_date
 locale
 forecast_type
 status
 started_at
 finished_at
 total_items
 success_items
 failed_items
 skipped_items
 error_message
```

Typical run statuses:

```text
running
success
partial_failed
failed
interrupted
```

### `generation_items`

One generation item represents one sign/date/locale/type slot inside a run.

Important fields:

```text
run_id
sign_key
target_date
locale
forecast_type
status
forecast_id
prompt_version_id
provider
model_name
request_payload
response_payload
raw_response
error_message
started_at
finished_at
```

Typical item statuses:

```text
pending
running
success
failed
skipped
interrupted
```

`skipped` means a published forecast already exists and the provider was not called.

### `generation_attempts`

One generation attempt represents one actual provider call attempt for a generation item.

Important fields:

```text
item_id
attempt_no
status
provider
model_name
request_payload
response_payload
raw_response
error_type
error_message
started_at
finished_at
```

This table is intended to make production troubleshooting easier once OpenAI or a local LLM provider is added.

## Service layer

The backend service layer is split into a package:

```text
backend/app/services/
```

Current service modules:

```text
constants.py
forecast_service.py
generation_service.py
prompt_service.py
sign_service.py
__init__.py
```

`services/__init__.py` keeps compatibility exports for the current routes, including:

```text
SIGNS
generate_horoscope
get_forecast
save_forecast
run_daily_generation
run_retry_for_missing_forecasts
has_generation_coverage
```

## Provider abstraction

Forecast text generation is behind a provider abstraction:

```text
backend/app/providers/
```

Current provider modules:

```text
base.py
factory.py
stub.py
__init__.py
```

Current working provider:

```text
stub
```

Configured but not implemented yet:

```text
openai
local
local-llm
local_llm
```

The provider request is intentionally sign-agnostic. The generator receives:

```text
target_date
locale
forecast_type
prompt_version
```

It does not receive:

```text
sign_key
```

This is intentional. Product logic treats horoscope text as universal. The sign key is only for DB slotting and frontend routing/display.

## Generation lifecycle

The scheduler and manual generation use the same lifecycle service.

Main lifecycle entry point:

```python
run_daily_generation(...)
```

Expected flow:

```text
1. close stale running runs
2. avoid duplicate active running run for the same date/locale/type
3. create generation_run
4. resolve provider
5. resolve active prompt version
6. create generation_items for signs
7. for each item:
   - if published forecast exists: mark item as skipped
   - otherwise call provider
   - create generation_attempt
   - validate provider result
   - save/update forecast
   - mark item as success or failed
8. finalize run counters
9. set run status: success / partial_failed / failed
```

Coverage is based on published forecasts, not merely on the existence of a row in `forecasts`.

This means a forecast with:

```text
status = failed
```

is treated as missing and can be regenerated in a later run.

## Scheduler

Scheduler container runs:

```bash
python tasks.py
```

Main environment variables:

```text
APP_TIMEZONE=Europe/Kyiv
SCHEDULE_HOUR=1
SCHEDULE_MINUTE=0
RUN_NIGHTLY_ON_START=0
HOROSCOPE_PROVIDER=stub
GENERATION_MAX_ATTEMPTS=3
GENERATION_STALE_HOURS=2
RETRY_MISSING_ENABLED=1
RETRY_INTERVAL_MINUTES=30
RETRY_WINDOW_START_HOUR=1
RETRY_WINDOW_END_HOUR=6
MAX_RETRY_RUNS_PER_DAY=3
```

Default scheduled generation time:

```text
01:00 Europe/Kyiv
```

### Run generation manually

Manual runtime test from backend container:

```bash
docker compose exec -T backend python - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo

from app import create_app
from app.services import run_daily_generation

app = create_app()

with app.app_context():
    target_date = datetime.now(ZoneInfo("Europe/Kyiv")).date()
    run = run_daily_generation(
        target_date=target_date,
        run_type="manual",
        provider_name="stub",
    )

    print("run_id:", run.id)
    print("status:", run.status)
    print("total:", run.total_items)
    print("success:", run.success_items)
    print("skipped:", run.skipped_items)
    print("failed:", run.failed_items)
PY
```

Expected first clean result:

```text
status: success
total: 13
success: 13
skipped: 0
failed: 0
```

Expected second result for the same date:

```text
status: success
total: 13
success: 0
skipped: 13
failed: 0
```

## API compatibility

The current frontend-compatible API remains intentionally conservative.

### `GET /api/signs`

Still returns the old format:

```json
["aries", "taurus", "gemini"]
```

The DB already has `zodiac_signs`, but the frontend contract is not changed yet.

### `GET /api/forecast?sign=aries&date=YYYY-MM-DD`

Returns backward-compatible fields:

```json
{
  "id": 1,
  "sign": "aries",
  "sign_key": "aries",
  "day": "2026-05-17",
  "date": "2026-05-17",
  "text": "...",
  "forecast": "...",
  "status": "published",
  "source": "stub",
  "model_version": "stub",
  "model_name": "stub"
}
```

The frontend can keep reading either:

```text
text
forecast
```

### `GET /api/years`

Returns years based on published forecasts when available.

If there are no published forecasts, it falls back to:

```text
2024..current_year
```

## Runtime verification status

The current lifecycle was manually verified in Docker with PostgreSQL.

Confirmed:

```text
Alembic current head: 0002_add_generation_attempts
manual generation run: success
13 generation_items: success
13 generation_attempts: success
13 forecasts: published
repeated run: 13 skipped, 0 provider attempts
failed forecast recovery: works
forecast upsert by unique slot: works
/api/forecast smoke test: works
sign-agnostic stub text: confirmed
```

A tested failed-forecast recovery scenario:

```sql
update forecasts set status='failed' where id=3;
```

Next manual run produced:

```text
total: 13
success: 1
skipped: 12
failed: 0
```

The `gemini` forecast was restored to:

```text
status = published
```

and only one new generation attempt was created for the regenerated item.

## Useful DB inspection commands

Generation runs:

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select id, run_type, target_date, status, total_items, success_items, skipped_items, failed_items, started_at, finished_at
from generation_runs
order by id desc
limit 5;
"'
```

Generation items:

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select id, run_id, sign_key, target_date, status, forecast_id, provider, model_name, error_message
from generation_items
order by id desc
limit 20;
"'
```

Generation attempts:

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select id, item_id, attempt_no, status, provider, model_name, error_type, error_message
from generation_attempts
order by id desc
limit 20;
"'
```

Forecasts:

```bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
select id, sign_key, target_date, locale, forecast_type, status, source, model_name, generation_item_id
from forecasts
order by id desc
limit 20;
"'
```

Check one forecast through API:

```bash
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-05-17"
```

## Design notes

### Sign-agnostic generation

The project intentionally does not generate different text based on the zodiac sign.

The generated text should address the reader directly:

```text
Вы
Вам
Вас
```

and should not contain sign names like:

```text
aries
Овен
Телец
Gemini
```

The sign key remains important for:

```text
DB uniqueness
frontend routing
archive pages
zodiac carousel/pages
```

but not for prompt content.

### Forecast status and coverage

A forecast is considered ready only if:

```text
status = published
```

Rows with other statuses, including:

```text
failed
draft
```

are not considered coverage-complete and may be regenerated.

### Skipped items

If a published forecast already exists, the lifecycle creates a `generation_item` with:

```text
status = skipped
```

No `generation_attempt` is created for skipped items.

## Known limitations / next work

Current limitations:

```text
OpenAI provider is not implemented yet
local LLM provider is not implemented yet
backend tests are not added yet
production deployment setup is not ready yet
admin/manual API for generation is not implemented yet
retry provider-failure scenarios still need explicit tests
```

Recommended next steps:

```text
1. Smoke-test /api/signs and /api/years after lifecycle changes.
2. Test retry_missing_forecasts explicitly.
3. Add backend tests for generation lifecycle.
4. Add provider failure tests with a controlled failing provider.
5. Implement OpenAI provider behind the existing provider factory.
6. Add production deploy setup later: gunicorn, frontend build, nginx/caddy, secrets, backups, healthchecks.
```

## Production notes for later

Current Docker Compose setup is for development, not production.

Future production setup should include:

```text
backend served by gunicorn
frontend built statically and served by nginx/caddy
migrations as explicit deploy step
production-grade secrets
PostgreSQL backup strategy
healthchecks
observability/logging
provider quota/error monitoring
```

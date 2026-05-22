# Horoscope App

Vue + Flask application for sign-agnostic daily horoscope forecast generation.

Current working branch:

```text
feature/forecast-gen-queued
```

Current backend focus:

```text
Docker Compose dev environment
PostgreSQL
Alembic migrations
Generation lifecycle
Provider abstraction
OpenAI provider
Prompt-building pipeline
Prompt variation profiles
Generation attempts / audit trail
Queued generation jobs
Backfill job creation
Manual and scheduler queue workers
Backend tests + GitHub Actions CI
Forecast quality utilities
Admin/manual generation API
Admin queued jobs API
```

The frontend/UI is treated as mostly formed for now. The main active work is backend generation infrastructure, generated forecast quality, DB-backed generation queue, and safe admin control over generation runs/jobs.

---

## Current state summary

The app runs locally through Docker Compose.

Docker Compose services:

```text
frontend   Vue/Vite dev server
backend    Flask API
scheduler  APScheduler process for daily generation and optional queue polling
db         PostgreSQL 17 Alpine
```

Default local URLs:

```text
frontend: http://localhost:5173
backend:  http://localhost:8000
```

Generation providers:

```text
stub       default local/dev provider
openai     implemented provider for real model generation
```

Planned future providers:

```text
local-LLM
```

Current selected OpenAI model:

```text
gpt-5.4-mini
```

This model is used by Docker/env defaults and by the current production prompt version.

Important product rule:

```text
Forecast text is sign-agnostic.
```

The zodiac sign key is used for database routing, scheduler lifecycle, deterministic variation selection, API compatibility and frontend display, but the generation prompt/provider must not receive the sign name as a creative instruction.

Forecast copy should address the reader directly:

```text
Вы / Вам / Вас / Ваш / Ваши
```

Forbidden in generated text:

```text
Овен, Телец, Близнецы...
Овнов, Тельцам, Рыбам...
представители знака
люди этого знака
для вашего знака
ваш знак
знак зодиака
дата
```

---

## Project structure

```text
horoscope-app/
├── backend/
│   ├── app/
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   ├── openai_provider.py
│   │   │   └── stub.py
│   │   ├── services/
│   │   │   ├── constants.py
│   │   │   ├── forecast_service.py
│   │   │   ├── forecast_validation_service.py
│   │   │   ├── generation_admin_service.py
│   │   │   ├── generation_job_service.py
│   │   │   ├── generation_service.py
│   │   │   ├── prompt_service.py
│   │   │   ├── prompt_variation_service.py
│   │   │   └── sign_service.py
│   │   ├── admin_auth.py
│   │   ├── admin_routes.py
│   │   ├── config.py
│   │   ├── models.py
│   │   └── routes.py
│   ├── migrations/
│   ├── tests/
│   ├── utils/
│   │   ├── create_generation_jobs.py
│   │   ├── forecast_package_report.py
│   │   ├── generate_forecast_package.py
│   │   ├── openai_prompt_probe.py
│   │   └── process_generation_jobs.py
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run.py
│   └── tasks.py
├── frontend/
├── secrets/
├── scripts/
│   └── backend-test.sh
├── .github/workflows/
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Requirements

Recommended local development setup:

```text
Linux shell
Docker Engine
Docker Compose plugin
```

Check installation:

```bash
docker --version
docker compose version
```

---

## Initial local setup

From the repository root:

```bash
cd /home/user/horoscope_project/1/horoscope-app
```

Create the local secrets directory and PostgreSQL password file:

```bash
mkdir -p secrets
touch secrets/.gitkeep
openssl rand -base64 32 > secrets/postgres_password.txt
chmod 700 secrets
chmod 600 secrets/postgres_password.txt
```

The file below is required locally but must not be committed:

```text
secrets/postgres_password.txt
```

Verify that it is ignored:

```bash
git check-ignore -v secrets/postgres_password.txt
```

Expected: git reports that the file is ignored by `.gitignore`.

---

## Optional `.env`

The app can run without `.env` because `docker-compose.yml` defines defaults. To override local settings:

```bash
cp .env.example .env
```

Useful settings:

```env
APP_TIMEZONE=Europe/Kyiv
LOG_LEVEL=INFO

SCHEDULE_HOUR=1
SCHEDULE_MINUTE=0
RUN_NIGHTLY_ON_START=0

# Keep stub for normal local/dev work without paid API calls.
HOROSCOPE_PROVIDER=stub

# For real OpenAI generation:
# HOROSCOPE_PROVIDER=openai
# OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_MODEL=gpt-5.4-mini
# OPENAI_TIMEOUT_SECONDS=30
# OPENAI_MAX_OUTPUT_TOKENS=500

# Legacy retry-missing scheduler for current APP_TIMEZONE date.
RETRY_MISSING_ENABLED=1
RETRY_INTERVAL_MINUTES=30
RETRY_WINDOW_START_HOUR=1
RETRY_WINDOW_END_HOUR=6
MAX_RETRY_RUNS_PER_DAY=3

# Queued generation jobs worker.
# Disabled by default.
GENERATION_JOB_WORKER_ENABLED=0
GENERATION_JOB_WORKER_INTERVAL_SECONDS=60
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
GENERATION_JOB_STALE_AFTER_MINUTES=60
GENERATION_JOB_WORKER_ID=scheduler

# Admin/manual generation API.
# Disabled by default.
ADMIN_API_ENABLED=0
ADMIN_API_TOKEN=change-me-local-admin-token
ADMIN_API_ALLOW_OPENAI=0

# Local admin API smoke testing:
# ADMIN_API_ENABLED=1
# ADMIN_API_TOKEN=dev-admin-token
```

The Admin API and queued job worker are disabled by default.

After changing `.env`, recreate affected containers so Docker Compose passes new environment variables into them:

```bash
docker compose up -d --force-recreate backend scheduler
```

Verify environment values inside containers:

```bash
docker compose exec backend sh -lc 'env | grep ADMIN'
docker compose exec scheduler sh -lc 'env | grep GENERATION_JOB'
```

Do not commit `.env`, real admin tokens, or real API keys.

---

## Run the app

Start all services:

```bash
docker compose up --build
```

Open:

```text
http://localhost:5173
```

Backend API:

```text
http://localhost:8000
```

Show service status:

```bash
docker compose ps
```

Show logs:

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f scheduler
docker compose logs -f db
docker compose logs -f frontend
```

Stop services but keep DB volume:

```bash
docker compose down
```

Stop services and delete DB volume:

```bash
docker compose down -v
```

Warning: `docker compose down -v` deletes the local PostgreSQL data volume.

---

## Docker services

### `db`

PostgreSQL database.

Default local settings:

```text
host inside Docker network: db
port inside Docker network: 5432
host port on laptop: 5432
database: horoscope
user: horoscope
password: read from secrets/postgres_password.txt
volume: postgres_data
```

### `backend`

Flask API container.

Startup command:

```bash
alembic upgrade head && python run.py
```

The old `db.create_all()` workflow is no longer used. Schema changes must go through Alembic migrations.

Admin API environment variables are passed to the backend container:

```env
ADMIN_API_ENABLED=0
ADMIN_API_TOKEN=
ADMIN_API_ALLOW_OPENAI=0
```

Queued generation job env vars are also available in the backend container so utility scripts and app config can read them:

```env
GENERATION_JOB_WORKER_ENABLED=0
GENERATION_JOB_WORKER_INTERVAL_SECONDS=60
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
GENERATION_JOB_STALE_AFTER_MINUTES=60
```

### `scheduler`

Separate APScheduler process.

Startup command:

```bash
python tasks.py
```

By default it schedules legacy daily forecast generation at:

```text
01:00 Europe/Kyiv
```

It also can poll queued generation jobs if explicitly enabled.

To force legacy generation when the scheduler starts, set:

```env
RUN_NIGHTLY_ON_START=1
```

To enable DB-backed queue polling, set:

```env
GENERATION_JOB_WORKER_ENABLED=1
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
```

Keep `GENERATION_JOB_WORKER_ALLOW_OPENAI=0` unless you intentionally want the scheduler to execute OpenAI jobs.

### `frontend`

Vue/Vite dev server.

Available at:

```text
http://localhost:5173
```

Inside Docker, Vite proxies API requests to:

```text
http://backend:8000
```

---

## Database and migrations

The project uses Alembic.

Migration files live in:

```text
backend/migrations/versions/
```

Current migration chain:

```text
-> 0001_initial_schema
0001_initial_schema -> 0002_add_generation_attempts
0002_add_generation_attempts -> 0003_prompt_pipeline
0003_prompt_pipeline -> 0004_variation_prompt
0004_variation_prompt -> 0005_generation_jobs
```

Check current migration:

```bash
docker compose exec backend alembic current
```

Expected after current migrations:

```text
0005_generation_jobs (head)
```

Show migration history:

```bash
docker compose exec backend alembic history
```

Apply migrations manually:

```bash
docker compose exec backend alembic upgrade head
```

Create a new migration after model changes:

```bash
docker compose exec backend alembic revision --autogenerate -m "Describe change"
```

Always review autogenerated migrations manually before applying them.

---

## Current database schema

### `zodiac_signs`

Stores zodiac sign metadata.

Important fields:

```text
key
name_ru
name_uk
name_en
glyph
start_month
start_day
end_month
end_day
sort_order
is_enabled
created_at
updated_at
```

The initial migration seeds 13 signs including `ophiuchus`.

### `prompt_versions`

Stores prompt versions for forecast generation.

Important fields:

```text
id
key
locale
forecast_type
system_prompt
user_prompt_template
output_schema
model_name
is_active
created_at
updated_at
```

Seeded active prompt:

```text
daily-ru-v1
```

The current active prompt is sign-agnostic, date-agnostic and variation-aware.

Current production model configured on the prompt version:

```text
gpt-5.4-mini
```

Date/sign metadata may exist in request metadata for audit/debugging, but user-facing prompt content should not instruct the provider to generate for a specific sign or date.

### `forecasts`

Stores published or non-published forecasts.

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

This gives one current forecast slot per sign/date/locale/type.

### `generation_jobs`

DB-backed queue/orchestration layer.

Important fields:

```text
id
job_type
status
target_date
locale
forecast_type
provider
signs
max_attempts
max_retry_runs
max_job_attempts
attempt_count
priority
run_id
batch_id
dedupe_key
openai_allowed_at_creation
created_by
error_message
started_at
finished_at
locked_at
locked_by
created_at
updated_at
```

Common job types:

```text
manual
backfill
retry_missing
scheduled
```

Common statuses:

```text
queued
running
success
partial_failed
failed
cancelled
```

`generation_jobs` is not a provider attempt log. It stores the queued unit of work that should eventually call the existing generation lifecycle.

### `generation_runs`

One generation run, such as a scheduled nightly generation, retry run, manual admin run, or run created by processing a queued job.

Important fields:

```text
id
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
created_at
```

Common statuses:

```text
running
success
partial_failed
failed
interrupted
```

### `generation_items`

One item inside a run, usually one sign/date/locale/type slot.

Important fields:

```text
id
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
created_at
```

Common statuses:

```text
pending
running
success
failed
skipped
interrupted
```

### `generation_attempts`

One provider call attempt for a generation item.

Important fields:

```text
id
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
created_at
```

This table is the detailed audit trail for provider calls. Skipped items should not create attempts.

---

## Generation architecture

The generation pipeline is split into several layers.

### Provider abstraction

Provider code lives in:

```text
backend/app/providers/
```

Current providers:

```text
stub
openai
```

Provider factory:

```text
backend/app/providers/factory.py
```

The scheduler selects provider by:

```env
HOROSCOPE_PROVIDER=stub
```

or:

```env
HOROSCOPE_PROVIDER=openai
```

### OpenAI provider

The OpenAI provider lives in:

```text
backend/app/providers/openai_provider.py
```

It is intentionally a thin adapter:

```text
ProviderRequest
  -> OpenAI Responses API call
  -> structured JSON parsing
  -> ProviderResult
```

The provider does not:

```text
build prompts
insert sign names
insert dates into prompt messages
write forecasts to the database
decide whether a forecast is published
```

Those responsibilities stay in:

```text
prompt_service.py
generation_service.py
forecast_validation_service.py
forecast_service.py
```

The provider uses:

```env
OPENAI_API_KEY
OPENAI_MODEL
OPENAI_TIMEOUT_SECONDS
OPENAI_MAX_OUTPUT_TOKENS
```

Default local provider remains `stub`, so normal development and CI do not require OpenAI credentials.

### Service layer

Service code lives in:

```text
backend/app/services/
```

Main responsibilities:

```text
sign_service.py                 enabled sign lookup
prompt_service.py               prompt variables/rendering/provider request building
prompt_variation_service.py     deterministic neutral variation profile selection
forecast_service.py             forecast read/write compatibility helpers
forecast_validation_service.py  forbidden zodiac term checks
generation_service.py           run/item/attempt lifecycle, retry, coverage checks
generation_job_service.py       queued jobs creation, claiming, processing, retry/cancel
generation_admin_service.py     protected admin read/write orchestration helpers
```

### Sign-agnostic generation

The generation text must not depend on the zodiac sign.

The sign key is still stored in:

```text
forecasts.sign_key
generation_items.sign_key
generation_attempts.request_payload.metadata.sign_key
```

But the provider-facing prompt messages are designed so the creative instruction does not ask for a specific sign.

### Prompt variation profiles

Production generation uses neutral variation profiles to avoid 13 same-looking daily forecasts.

The variation profiles live in:

```text
backend/app/services/prompt_variation_service.py
```

Each profile contains:

```text
key
theme
mood
tone
composition
opening_move
concrete_zone
ending_energy
sentence_style
avoid
```

Current profile keys:

```text
small_joy
relationships
recovery
new_chance
creative_view
boundaries
money_careful
social_warmth
inner_choice
home_mood
romantic_hint
playful_spontaneity
quiet_confidence
```

The profile choice is deterministic. The backend may use `sign_key + target_date + locale + forecast_type` as an internal seed, but only neutral variation profile data is rendered into prompt messages.

This preserves the main product rule:

```text
sign_key and target_date are allowed in metadata/storage/debugging,
but not as creative prompt content.
```

### Prompt pipeline

The prompt layer builds:

```text
system prompt
user prompt
messages
output schema
prompt variables
metadata
```

Supported prompt variables include:

```text
locale
forecast_type
output_language
address_style
sentence_count
prompt_variation_key
prompt_variation_theme
prompt_variation_mood
prompt_variation_tone
prompt_variation_composition
prompt_variation_opening_move
prompt_variation_concrete_zone
prompt_variation_ending_energy
prompt_variation_sentence_style
prompt_variation_avoid
```

Unsupported placeholders should fail early rather than silently generating invalid prompts.

### Forecast validation

Generated text is validated before publishing.

Current validation includes:

```text
non-empty text
forbidden zodiac terms check
```

If a provider returns text containing zodiac sign names or generic zodiac phrases, the attempt is treated as retryable failure and the forecast is not published.

---

## Generation lifecycle

A direct daily generation run works like this:

```text
1. Close stale running runs if needed.
2. Check that there is no active running run for the same date/locale/type.
3. Create generation_run with status=running.
4. Resolve enabled signs.
5. Resolve active prompt version.
6. Create generation_items for signs.
7. For each item:
   - if published forecast already exists, mark item skipped;
   - otherwise create generation_attempt;
   - build provider request;
   - call provider;
   - validate result;
   - save/update forecast as published;
   - mark item success or failed.
8. Recalculate counters.
9. Finalize run as success / partial_failed / failed.
```

Coverage is based on published forecasts:

```text
A sign/date/locale/type is complete only if a published forecast exists.
```

If a forecast row exists but its status is `failed`, the next generation run treats it as missing and can regenerate that slot.

---

## Queued generation jobs

The backend now has a DB-backed generation queue.

The important separation is:

```text
generation_jobs      queued unit of work / orchestration layer
generation_runs      execution/audit record for one run
generation_items     per-sign records inside a run
generation_attempts  provider attempts inside an item
forecasts            published or non-published forecast rows
```

Processing a queued job does not replace `generation_service.py`. It calls the existing lifecycle:

```text
GenerationJob
  -> process_generation_jobs()
  -> run_daily_generation() or run_retry_for_missing_forecasts()
  -> GenerationRun
  -> GenerationItem
  -> GenerationAttempt
  -> Forecast
```

### Job claiming

Workers claim jobs with status:

```text
queued
```

and mark them as:

```text
running
```

The worker stores:

```text
locked_at
locked_by
attempt_count
started_at
```

PostgreSQL workers use row locking with `SKIP LOCKED` to avoid two workers picking the same queued job.

### Dedupe

Jobs have a `dedupe_key`. The database prevents duplicate active jobs for the same normalized job scope while status is:

```text
queued
running
```

Finished jobs do not block history or later repeat runs:

```text
success
partial_failed
failed
cancelled
```

For backfill usage, prefer `--skip-covered` after a date already has published forecasts.

### OpenAI safety

OpenAI queued jobs have a double safety model:

```text
1. Job creation requires explicit --allow-openai or allow_openai=true.
2. Job execution requires explicit worker --allow-openai or GENERATION_JOB_WORKER_ALLOW_OPENAI=1.
```

This means it is possible to create OpenAI jobs without accidentally executing them from the scheduler.

Recommended local default:

```env
GENERATION_JOB_WORKER_ENABLED=0
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
```

---

## Backend API

The public API remains frontend-compatible.

### `GET /api/signs`

```bash
curl http://localhost:8000/api/signs
```

Current response shape is still a list of sign keys:

```json
[
  "aries",
  "taurus",
  "gemini",
  "cancer",
  "leo",
  "virgo",
  "libra",
  "scorpio",
  "sagittarius",
  "capricorn",
  "aquarius",
  "pisces",
  "ophiuchus"
]
```

The database has richer sign metadata in `zodiac_signs`, but `/api/signs` intentionally keeps the old response shape for frontend compatibility.

### `GET /api/forecast`

```bash
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-06-05"
```

Parameters:

```text
sign    required zodiac sign key
date    optional YYYY-MM-DD, defaults to current date
locale  optional, defaults to ru
type    optional forecast type, defaults to daily
```

Response includes both old and new aliases:

```json
{
  "id": 1,
  "sign": "aries",
  "sign_key": "aries",
  "day": "2026-06-05",
  "date": "2026-06-05",
  "text": "...",
  "forecast": "...",
  "status": "published",
  "source": "openai",
  "model_version": "gpt-5.4-mini",
  "model_name": "gpt-5.4-mini",
  "prompt_version": "daily-ru-v1"
}
```

### `GET /api/years`

```bash
curl http://localhost:8000/api/years
```

Current behavior:

```text
If published forecasts exist, returns years from DB.
If there are no forecasts yet, falls back to 2024..current_year.
```

---

## Admin/manual generation API

The Admin API is mounted under:

```text
/api/admin
```

It is disabled by default and requires bearer-token authentication:

```http
Authorization: Bearer <ADMIN_API_TOKEN>
```

Required local environment variables:

```env
ADMIN_API_ENABLED=1
ADMIN_API_TOKEN=dev-admin-token
ADMIN_API_ALLOW_OPENAI=0
```

After changing these values, recreate the backend container:

```bash
docker compose up -d --force-recreate backend
```

Verify that the variables reached the container:

```bash
docker compose exec backend sh -lc 'env | grep ADMIN'
```

Expected local output:

```text
ADMIN_API_ENABLED=1
ADMIN_API_TOKEN=dev-admin-token
ADMIN_API_ALLOW_OPENAI=0
```

### Check generation coverage

```bash
curl -s "http://localhost:8000/api/admin/generation/coverage?date=2026-06-15" \
  -H "Authorization: Bearer dev-admin-token"
```

This returns published/missing forecast coverage for the selected date, locale and forecast type.

### List generation runs

```bash
curl -s "http://localhost:8000/api/admin/generation/runs?limit=10" \
  -H "Authorization: Bearer dev-admin-token"
```

Optional filters:

```text
date=YYYY-MM-DD
locale=ru
type=daily
status=success|failed|partial_failed|running|interrupted
run_type=manual|scheduled|retry|backfill
limit=1..100
offset=0..10000
```

### Inspect one generation run

```bash
curl -s "http://localhost:8000/api/admin/generation/runs/1" \
  -H "Authorization: Bearer dev-admin-token"
```

Payload fields are hidden by default.

To include stored request/response/raw payloads:

```bash
curl -s "http://localhost:8000/api/admin/generation/runs/1?include_payloads=1" \
  -H "Authorization: Bearer dev-admin-token"
```

### Inspect item attempts

```bash
curl -s "http://localhost:8000/api/admin/generation/items/1/attempts" \
  -H "Authorization: Bearer dev-admin-token"
```

### Run manual stub generation immediately

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/runs \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","signs":["aries","taurus"],"max_attempts":1}'
```

Behavior:

```text
run_type=manual
already published forecast slots are skipped
missing slots are generated through the selected provider
```

### Retry missing forecasts immediately

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/retry-missing \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","max_attempts":1}'
```

This retries all currently missing published forecast slots for the selected date.

### OpenAI safety gate for immediate Admin API generation

OpenAI generation through Admin API requires two explicit confirmations.

Environment:

```env
ADMIN_API_ALLOW_OPENAI=1
```

Request body:

```json
{
  "provider": "openai",
  "allow_openai": true
}
```

Example:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/runs \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-16","provider":"openai","allow_openai":true,"max_attempts":3}'
```

Keep `ADMIN_API_ALLOW_OPENAI=0` for normal local development.

---

## Admin queued jobs API

Queued job API is also mounted under:

```text
/api/admin
```

It uses the same Admin API authentication and the same OpenAI safety gate.

### List jobs

```bash
curl -s "http://localhost:8000/api/admin/generation/jobs?limit=20" \
  -H "Authorization: Bearer dev-admin-token"
```

Optional filters:

```text
status=queued|running|success|partial_failed|failed|cancelled
date=YYYY-MM-DD
target_date=YYYY-MM-DD
batch_id=<batch id>
provider=stub|openai
job_type=manual|backfill|retry_missing|scheduled
limit=1..200
offset=0..100000
```

### Create one queued job

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","job_type":"manual","signs":["aries","taurus"],"max_attempts":1}'
```

This creates a queued job only. It does not execute generation immediately.

### Create backfill jobs for a date range

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/backfill \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-07","provider":"stub","skip_covered":true}'
```

Dry run:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/backfill \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-07","provider":"stub","skip_covered":true,"dry_run":true}'
```

Create OpenAI backfill jobs:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/backfill \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-03","provider":"openai","allow_openai":true,"skip_covered":true}'
```

OpenAI backfill via Admin API also requires:

```env
ADMIN_API_ALLOW_OPENAI=1
```

### Inspect one job

```bash
curl -s "http://localhost:8000/api/admin/generation/jobs/1" \
  -H "Authorization: Bearer dev-admin-token"
```

If a job already produced a `generation_run`, the response includes a run summary.

### Cancel a queued job

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/1/cancel \
  -H "Authorization: Bearer dev-admin-token"
```

Running jobs cannot be safely cancelled in the current version.

### Retry a failed job

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/1/retry \
  -H "Authorization: Bearer dev-admin-token"
```

Only `failed` and `partial_failed` jobs can be queued for retry.

---

## Utility scripts

Utility scripts live in:

```text
backend/utils/
```

They are development/QA helpers. They do not replace authenticated admin APIs.

### `openai_prompt_probe.py`

Makes exactly one OpenAI request with a hardcoded prompt/variation setup.

Useful for quick model and prompt experiments without touching the DB or Flask app.

List available probe options:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --help
```

Run one probe request:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini
```

Run a specific probe variation:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py \
  --model gpt-5.4-mini \
  --variation creative_view \
  --show-prompt
```

List probe variations without making an API request:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --list-variations
```

### `generate_forecast_package.py`

Runs the real generation lifecycle for a full forecast package on a target date.

This is the convenient CLI replacement for a multi-line Python snippet.

OpenAI generation requires an explicit safety flag to avoid accidental paid API calls:

```bash
docker compose exec -T backend python utils/generate_forecast_package.py \
  --date 2026-06-06 \
  --provider openai \
  --allow-openai \
  --show-items \
  --show-errors
```

Free local stub generation:

```bash
docker compose exec -T backend python utils/generate_forecast_package.py \
  --date 2026-06-06 \
  --provider stub \
  --show-items
```

Important behavior:

```text
If a published forecast already exists for a sign/date/locale/type,
the corresponding item is skipped.
```

For repeated OpenAI quality checks, prefer using a new empty date rather than deleting existing forecasts.

### `forecast_package_report.py`

Prints a quality report for a generated forecast package.

It extracts:

```text
source/model
variation profile metadata
duplicate titles
duplicate endings
forbidden zodiac hits
soft repetition hints
full forecast text
```

Text report:

```bash
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-06
```

Compact report:

```bash
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-06 --compact
```

JSON report:

```bash
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-06 --json
```

Show extracted variation metadata:

```bash
docker compose exec -T backend python utils/forecast_package_report.py \
  --date 2026-06-06 \
  --show-metadata
```

The report utility uses word-aware matching for short forbidden patterns, so words like `ракурс` should not trigger a false-positive hit for the sign name `рак`.

### `create_generation_jobs.py`

Creates queued generation jobs for one date or a date range. It does not execute generation.

Create stub jobs:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider stub \
  --show-items
```

Create OpenAI jobs:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider openai \
  --allow-openai \
  --show-items
```

Create jobs only for dates without full published coverage:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider openai \
  --allow-openai \
  --skip-covered \
  --show-items
```

Dry run:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider stub \
  --dry-run \
  --show-items
```

Useful options:

```text
--date YYYY-MM-DD
--start-date YYYY-MM-DD
--end-date YYYY-MM-DD
--job-type manual|backfill|retry_missing|scheduled
--retry-missing
--provider stub|openai
--allow-openai
--locale ru
--forecast-type daily
--signs aries,taurus
--sign aries --sign taurus
--max-attempts 3
--max-retry-runs 3
--max-job-attempts 1
--priority 0
--batch-id custom-batch-id
--created-by cli
--skip-covered
--dry-run
--limit 10
--show-items
```

### `process_generation_jobs.py`

Manually processes queued generation jobs. This is useful before enabling scheduler polling.

Process one stub job:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs
```

Process one OpenAI job:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs \
  --allow-openai
```

Close stale running jobs before processing:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --close-stale \
  --stale-after-minutes 60 \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs
```

Useful options:

```text
--limit 1
--worker-id local-manual
--allow-openai
--stale-after-hours 2
--close-stale
--stale-after-minutes 60
--show-jobs
```

---

## OpenAI local smoke check

By default the app uses:

```env
HOROSCOPE_PROVIDER=stub
```

To try real OpenAI generation locally, create/update `.env`:

```env
HOROSCOPE_PROVIDER=stub
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=500
RUN_NIGHTLY_ON_START=0
```

Keeping `HOROSCOPE_PROVIDER=stub` is safe for normal container startup.

Manual utility commands can still pass `--provider openai --allow-openai` when you intentionally want real API calls.

Generate a full OpenAI package directly:

```bash
docker compose exec -T backend python utils/generate_forecast_package.py \
  --date 2026-06-06 \
  --provider openai \
  --allow-openai \
  --show-items \
  --show-errors
```

Or create and process OpenAI queued jobs:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider openai \
  --allow-openai \
  --show-items

docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs \
  --allow-openai
```

Review the generated package:

```bash
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-05-16 --compact
```

Expected healthy package:

```text
13 published forecasts
source=openai for all items
model_name=gpt-5.4-mini for all items
13 different variation profiles used once each
no forbidden zodiac hits
no duplicate titles
no duplicate endings
```

Do not commit real OpenAI keys.

---

## Useful SQL checks

Open psql:

```bash
docker compose exec db psql -U horoscope -d horoscope
```

Migration version:

```sql
select * from alembic_version;
```

Recent jobs:

```sql
select id, job_type, status, target_date, provider, priority, run_id, attempt_count, locked_by, error_message, created_at, started_at, finished_at
from generation_jobs
order by id desc
limit 20;
```

Queued jobs:

```sql
select id, job_type, target_date, provider, priority, batch_id, created_at
from generation_jobs
where status = 'queued'
order by priority desc, created_at asc, id asc;
```

Recent runs:

```sql
select id, run_type, target_date, status, total_items, success_items, skipped_items, failed_items, started_at, finished_at
from generation_runs
order by id desc
limit 5;
```

Items for a run:

```sql
select id, run_id, sign_key, target_date, status, forecast_id, provider, model_name, error_message
from generation_items
where run_id = 1
order by id;
```

Attempts for a run:

```sql
select a.id, a.item_id, i.sign_key, i.run_id, a.attempt_no, a.status, a.provider, a.error_type, a.error_message
from generation_attempts a
join generation_items i on i.id = a.item_id
where i.run_id = 1
order by a.id;
```

Forecasts:

```sql
select id, sign_key, target_date, locale, forecast_type, status, source, model_name, generation_item_id
from forecasts
order by id desc
limit 20;
```

Exit psql:

```sql
\q
```

---

## Backend tests

Backend tests run against an isolated PostgreSQL database.

Main command:

```bash
bash scripts/backend-test.sh
```

What it does:

```text
1. Starts db service.
2. Waits until PostgreSQL accepts connections.
3. Drops test DB if it exists.
4. Creates test DB.
5. Runs backend container with POSTGRES_DB=horoscope_test.
6. Applies Alembic migrations.
7. Runs pytest.
8. Drops test DB on cleanup unless KEEP_TEST_DB=1.
```

Keep test DB for debugging:

```bash
KEEP_TEST_DB=1 bash scripts/backend-test.sh
```

Use another test DB name:

```bash
TEST_DB_NAME=horoscope_test_local bash scripts/backend-test.sh
```

Safety guard: the script refuses to run against the default development DB name `horoscope`. OpenAI provider tests are mock-based and do not make real OpenAI API requests.

Known local backend test run after initial queued jobs service/CLI work:

```text
106 passed
```

After scheduler polling and Admin queued jobs API changes, rerun:

```bash
bash scripts/backend-test.sh
```

---

## GitHub Actions CI

The repository has backend CI that runs the backend test script.

Current CI expectation:

```text
alembic upgrade head
pytest -q
```

The CI flow avoids PostgreSQL Unix socket issues while preparing the isolated test database. Test DB setup should use explicit TCP host/port inside the db container.

---

## Smoke checks

### Stub queued job smoke

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-06-15 \
  --end-date 2026-06-16 \
  --provider stub \
  --show-items

docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs
```

### OpenAI queued job smoke

Requires `OPENAI_API_KEY` in the backend container.

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider openai \
  --allow-openai \
  --show-items

docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs \
  --allow-openai
```

If an OpenAI job is processed without `--allow-openai`, it should fail safely with an error similar to:

```text
Refusing to process provider=openai job without explicit worker allow_openai.
```

The failed job can be retried after explicit allow:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/1/retry \
  -H "Authorization: Bearer dev-admin-token"
```

or from Python shell/service code if needed.

### Verify generated package

```bash
docker compose exec -T backend python utils/forecast_package_report.py \
  --date 2026-05-16 \
  --compact
```

### Check skip-covered behavior

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-05-15 \
  --end-date 2026-05-16 \
  --provider openai \
  --allow-openai \
  --skip-covered \
  --show-items
```

Expected after both dates already have full published coverage:

```text
created_count: 0
covered_count: 2
status=skipped_covered
```

---

## Current confirmed status

```text
Docker Compose dev                         done
PostgreSQL dev                             done
Docker secrets                             done
Backend config                             done
Alembic environment                        done
0001 initial schema                        done
0002 generation_attempts                   done
0003 prompt pipeline                       done
0004 variation prompt                      done
0005 generation_jobs                       done
Models expanded                            done
Service layer split                        done
Provider abstraction                       done
Stub provider                              done
OpenAI provider                            done
OpenAI model selection                     done: gpt-5.4-mini
OpenAI provider mock tests                 done
Prompt-building pipeline                   done
Prompt variation service                   done
Variation profiles in production           done
Prompt polish                              done
Forecast package generation utility        done
Forecast package report utility            done
Prompt probe utility                       done
Create generation jobs utility             done
Process generation jobs utility            done
Sign-agnostic generation                   done
Forecast validation                        done
Generation lifecycle                       done
Generation runs/items/attempts             done
Generation jobs queue                      done
Manual queue worker                        done
Scheduler queue polling                    done, disabled by default
Queued jobs Admin API                      done
Skipped behavior confirmed                 done
Failed forecast recovery                   done
Retry missing forecasts                    done
Stale running run cleanup                  done
Stale running job cleanup                  done
Admin/manual generation API MVP            done
Protected admin read API                   done
Manual admin generation endpoint           done
Retry-missing admin endpoint               done
OpenAI admin safety gate                   done
OpenAI queue creation safety gate          done
OpenAI queue execution safety gate         done
Backend pytest baseline                    done
GitHub Actions backend CI                  done
API compatibility preserved                done
README updated for feature/forecast-gen-queued
Local LLM provider                         not implemented yet
Archive API improvements                   not implemented yet
/api/signs/meta                            not implemented yet
Production deploy                          not implemented yet
```

---

## Known limitations / next work

### 1. Queued generation jobs hardening

Current capabilities:

```text
create one queued generation job
create range/backfill jobs
create retry_missing jobs
manual worker CLI
scheduler polling worker
list/inspect/cancel/retry jobs through Admin API
OpenAI double safety gate
active job dedupe
stale running job cleanup
```

Still intentionally limited:

```text
no admin UI
no running job cancellation
no per-day/month production quota
no distributed metrics dashboard
no automatic exponential backoff policy
no separate worker container yet
```

### 2. Production backfill workflow

Before running large OpenAI backfills:

```text
start with stub
use --dry-run
use --skip-covered
limit date ranges
process small batches
keep GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK low
monitor costs and logs
```

Do not run OpenAI for all dates since 2024 in one uncontrolled batch.

### 3. Archive API improvements

Possible future endpoint:

```text
GET /api/archive?sign=aries&year=2026&month=05
```

This would let the frontend query available published days from the DB.

### 4. `/api/signs/meta`

`/api/signs` intentionally remains a simple key list.

A future endpoint can expose richer DB metadata:

```text
GET /api/signs/meta
```

### 5. Local LLM provider

A local provider can later be added behind the same provider interface.

### 6. Production deploy

Current Docker Compose setup is for development.

Production still needs:

```text
gunicorn or another production WSGI server
frontend build + nginx/caddy/static hosting
migration deploy step
production secrets
backup strategy
healthchecks
monitoring/logging
stronger Admin API protection
```

Do not expose the current Admin API publicly without stronger production authentication and network-level protection.

---

## Development notes

Use clean local DB reset after schema experiments:

```bash
docker compose down -v
docker compose up --build
```

Use this only for local development because it deletes the PostgreSQL volume.

Do not commit:

```text
.env
secrets/postgres_password.txt
PostgreSQL data volumes
node_modules
frontend build artifacts
```

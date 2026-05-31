# Horoscope App

Vue + Flask application for sign-agnostic daily horoscope generation.

The project runs locally with Docker Compose and includes:

```text
frontend   Vue/Vite dev server
backend    Flask public API and Admin API
scheduler  APScheduler process for scheduled generation and queue processing
db         PostgreSQL 17 Alpine
```

Default local URLs:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
```

## Requirements

Recommended local setup:

```text
Docker Engine
Docker Compose plugin
Linux shell
```

Check Docker:

```bash
docker --version
docker compose version
```

## Initial setup

From the repository root:

```bash
mkdir -p secrets
touch secrets/.gitkeep
openssl rand -base64 32 > secrets/postgres_password.txt
chmod 700 secrets
chmod 600 secrets/postgres_password.txt
```

`secrets/postgres_password.txt` is required locally and must not be committed.

Verify it is ignored:

```bash
git check-ignore -v secrets/postgres_password.txt
```

## Optional `.env`

The app can run without `.env` because `docker-compose.yml` provides safe defaults.

To override local settings:

```bash
cp .env.example .env
```

Safe local defaults:

```env
APP_TIMEZONE=Europe/Kyiv
LOG_LEVEL=INFO
HOROSCOPE_PROVIDER=stub
RUN_NIGHTLY_ON_START=0

ADMIN_API_ENABLED=0
ADMIN_API_ALLOW_OPENAI=0

GENERATION_SCHEDULER_USE_QUEUE=0
GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI=0

GENERATION_JOB_WORKER_ENABLED=0
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
```

OpenAI should stay disabled by default in local automation unless you explicitly enable all relevant gates.

## Run locally

```bash
docker compose up --build
```

Useful commands:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f scheduler
docker compose down
```

## Backend database and migrations

The backend uses Alembic migrations. `db.create_all()` is not used.

The backend container starts with:

```bash
alembic upgrade head && python run.py
```

Current migrations:

```text
0001_initial_schema.py
0002_add_generation_attempts.py
0003_prompt_pipeline.py
0004_variation_prompt.py
0005_generation_jobs.py
```

Main tables:

```text
zodiac_signs
prompt_versions
forecasts
generation_runs
generation_items
generation_attempts
generation_jobs
```

Seed/reference data:

```text
zodiac_signs     13 signs, including ophiuchus
prompt_versions  daily-ru-v1
```

The forecast uniqueness rule is:

```text
sign_key + target_date + locale + forecast_type
```

## Public API compatibility

The frontend-compatible public endpoints are kept backward-compatible.

### `GET /api/signs`

Returns the legacy array format:

```json
["aries", "taurus", "...", "ophiuchus"]
```

### `GET /api/forecast`

Example:

```bash
curl -s "http://localhost:8000/api/forecast?sign=aries&date=2026-06-05" | python -m json.tool
```

Response includes old and new aliases:

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

Returns years available in published forecasts.

If the database has no published forecasts, it falls back to:

```text
2024..current_year
```

## Forecast generation rules

Forecast text is sign-agnostic.

The backend may use `sign_key` and `target_date` for routing, storage, deterministic variation selection, audit metadata, and API compatibility, but they must not be used as user-facing creative instructions in prompt messages.

Generated text should address the reader directly:

```text
Вы / Вас / Вам / Ваш / Ваши
```

Generated text must not include zodiac names or generic zodiac phrases such as:

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

`forecast_validation_service.py` validates generated text. If forbidden terms are detected, the attempt fails and the forecast is not published.

## Providers

Provider code lives in:

```text
backend/app/providers/
```

Available providers:

```text
stub
openai
```

Main provider types/functions:

```text
ProviderRequest
ProviderResult
GenerationProviderError
get_horoscope_provider()
```

OpenAI provider is a thin adapter:

```text
ProviderRequest
  -> OpenAI Responses API call
  -> structured JSON parsing
  -> ProviderResult
```

It does not build prompts, choose sign names, write forecasts, or manage lifecycle state. Those responsibilities belong to service-layer code.

OpenAI-related env:

```env
HOROSCOPE_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=500
```

Safe local default:

```env
HOROSCOPE_PROVIDER=stub
```

## Prompt pipeline and variation profiles

The production prompt pipeline is sign/date-agnostic.

Prompt rendering and provider request construction live in:

```text
backend/app/services/prompt_service.py
```

Variation profiles live in:

```text
backend/app/services/prompt_variation_service.py
```

Current profiles:

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

For a full 13-sign daily package, the pipeline deterministically spreads all 13 variation profiles across the signs.

## Generation lifecycle and queue architecture

The app separates queue orchestration from execution audit trail.

```text
generation_jobs       what should be executed
generation_runs       execution run / audit record
generation_items      per-sign execution records
generation_attempts   provider attempts
forecasts             published result
```

`generation_service.py` remains responsible for executing one generation run.

`generation_job_service.py` is responsible for:

```text
creating queued jobs
creating backfill ranges
creating scheduled jobs
claiming queued jobs safely
processing jobs through generation_service
closing stale running jobs
retrying or cancelling jobs
serializing job state
```

Queue jobs use statuses:

```text
queued
running
success
partial_failed
failed
cancelled
```

Active duplicate protection is based on a `dedupe_key` and applies to active jobs only:

```text
status in queued/running
```

This prevents duplicate active work while preserving completed job history.

## Scheduler and automation

The `scheduler` container runs `python tasks.py` and uses APScheduler.

There are two scheduler modes.

### Legacy direct mode

```env
GENERATION_SCHEDULER_USE_QUEUE=0
```

In this mode, the nightly scheduler directly calls `run_daily_generation()` and retry-missing logic.

### Queue producer mode

```env
GENERATION_SCHEDULER_USE_QUEUE=1
```

In this mode, scheduled tasks create rows in `generation_jobs`. The queue worker then processes them.

Queue worker env:

```env
GENERATION_JOB_WORKER_ENABLED=1
GENERATION_JOB_WORKER_INTERVAL_SECONDS=60
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1
GENERATION_JOB_WORKER_ALLOW_OPENAI=0
GENERATION_JOB_STALE_AFTER_MINUTES=60
GENERATION_JOB_WORKER_ID=scheduler

# OpenAI queue safety / cost guards.
# These are intentionally count-based, not money-based.
GENERATION_OPENAI_MAX_BACKFILL_DAYS=7
GENERATION_OPENAI_MAX_JOBS_PER_RUN=1
GENERATION_OPENAI_MAX_JOBS_PER_DAY=10
```

Scheduled producer env:

```env
SCHEDULE_HOUR=1
SCHEDULE_MINUTE=0
RUN_NIGHTLY_ON_START=0
GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI=0
GENERATION_SCHEDULED_JOB_PRIORITY=100
GENERATION_SCHEDULED_RETRY_JOB_PRIORITY=90
```

Retry-missing scheduler env:

```env
RETRY_MISSING_ENABLED=1
RETRY_INTERVAL_MINUTES=30
RETRY_WINDOW_START_HOUR=1
RETRY_WINDOW_END_HOUR=6
MAX_RETRY_RUNS_PER_DAY=3
```

Production-like OpenAI queue mode requires all relevant gates:

```env
HOROSCOPE_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here

GENERATION_SCHEDULER_USE_QUEUE=1
GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI=1

GENERATION_JOB_WORKER_ENABLED=1
GENERATION_JOB_WORKER_ALLOW_OPENAI=1
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1

GENERATION_OPENAI_MAX_BACKFILL_DAYS=7
GENERATION_OPENAI_MAX_JOBS_PER_RUN=1
GENERATION_OPENAI_MAX_JOBS_PER_DAY=10
```

OpenAI is intentionally disabled by default at both job-creation and job-execution layers.

## OpenAI safety gates and queue limits

OpenAI jobs are protected by multiple gates.

CLI job creation requires:

```bash
--provider openai --allow-openai
```

CLI queue worker execution requires:

```bash
--allow-openai
```

Admin API job creation requires:

```env
ADMIN_API_ALLOW_OPENAI=1
```

and request body:

```json
{
  "provider": "openai",
  "allow_openai": true
}
```

Scheduler producer requires:

```env
GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI=1
```

Scheduler worker execution requires:

```env
GENERATION_JOB_WORKER_ALLOW_OPENAI=1
```

Additional OpenAI queue limits:

```env
GENERATION_OPENAI_MAX_BACKFILL_DAYS=7
GENERATION_OPENAI_MAX_JOBS_PER_RUN=2
GENERATION_OPENAI_MAX_JOBS_PER_DAY=10
```

These are count-based safety guards. The project intentionally does not track a money budget in this layer.

Behavior:

* `GENERATION_OPENAI_MAX_BACKFILL_DAYS` limits OpenAI backfill job creation through both CLI and Admin API.
* `GENERATION_OPENAI_MAX_JOBS_PER_RUN` limits how many OpenAI jobs a worker run/tick may execute.
* `GENERATION_OPENAI_MAX_JOBS_PER_DAY` limits how many OpenAI jobs may be started per UTC day.
* When the worker reaches an OpenAI execution limit, matching OpenAI jobs stay `queued`.
* OpenAI jobs are not marked as `failed` for a quota/safety condition.
* The worker may still process non-OpenAI queued jobs in the same run.

## Admin API

Admin API is mounted under:

```text
/api/admin
```

Env:

```env
ADMIN_API_ENABLED=0
ADMIN_API_TOKEN=change-me-local-admin-token
ADMIN_API_ALLOW_OPENAI=0
```

For local smoke testing:

```env
ADMIN_API_ENABLED=1
ADMIN_API_TOKEN=dev-admin-token
ADMIN_API_ALLOW_OPENAI=0
```

After changing env values:

```bash
docker compose up -d --force-recreate backend
docker compose exec backend sh -lc 'env | grep ADMIN'
```

Admin requests require:

```text
Authorization: Bearer <ADMIN_API_TOKEN>
```

### Generation run endpoints

```text
GET  /api/admin/generation/coverage?date=YYYY-MM-DD
GET  /api/admin/generation/runs
GET  /api/admin/generation/runs/<run_id>
GET  /api/admin/generation/items/<item_id>/attempts
POST /api/admin/generation/runs
POST /api/admin/generation/retry-missing
```

Manual stub generation:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/runs \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","signs":["aries","taurus"],"max_attempts":1}' \
  | python -m json.tool
```

Coverage:

```bash
curl -s "http://localhost:8000/api/admin/generation/coverage?date=2026-06-15" \
  -H "Authorization: Bearer dev-admin-token" \
  | python -m json.tool
```

Retry missing:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/retry-missing \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","max_attempts":1}' \
  | python -m json.tool
```

### Generation job endpoints

```text
GET  /api/admin/generation/jobs
POST /api/admin/generation/jobs
POST /api/admin/generation/jobs/backfill
GET  /api/admin/generation/jobs/batches/<batch_id>
POST /api/admin/generation/jobs/batches/<batch_id>/cancel
POST /api/admin/generation/jobs/batches/<batch_id>/retry-failed
GET  /api/admin/generation/jobs/<job_id>
POST /api/admin/generation/jobs/<job_id>/cancel
POST /api/admin/generation/jobs/<job_id>/retry
```

Create one queued job:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-06-15","provider":"stub","job_type":"manual","signs":["aries","taurus"],"max_attempts":1}' \
  | python -m json.tool
```

Create a backfill range:

```bash
curl -s -X POST http://localhost:8000/api/admin/generation/jobs/backfill \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-06-15","end_date":"2026-06-17","provider":"stub","skip_covered":true}' \
  | python -m json.tool
```

List jobs:

```bash
curl -s "http://localhost:8000/api/admin/generation/jobs?status=queued" \
  -H "Authorization: Bearer dev-admin-token" \
  | python -m json.tool
```

Batch status:

```bash
curl -s "http://localhost:8000/api/admin/generation/jobs/batches/<batch_id>" \
  -H "Authorization: Bearer dev-admin-token" \
  | python -m json.tool
```

Batch cancel queued jobs:

```bash
curl -s -X POST "http://localhost:8000/api/admin/generation/jobs/batches/<batch_id>/cancel" \
  -H "Authorization: Bearer dev-admin-token" \
  | python -m json.tool
```

Batch retry failed jobs:

```bash
curl -s -X POST "http://localhost:8000/api/admin/generation/jobs/batches/<batch_id>/retry-failed" \
  -H "Authorization: Bearer dev-admin-token" \
  | python -m json.tool
```

OpenAI through Admin API requires both:

```env
ADMIN_API_ALLOW_OPENAI=1
```

and JSON body:

```json
{
  "provider": "openai",
  "allow_openai": true
}
```

There is intentionally no HTTP endpoint for “process jobs now”. Job execution is handled by the worker or CLI.

## Backend utilities

Utilities are run inside the backend container.

### Prompt probe

```text
backend/utils/openai_prompt_probe.py
```

Examples:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini
docker compose exec -T backend python utils/openai_prompt_probe.py --list-variations
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini --variation relationships
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini --variation creative_view --show-prompt
```

### Generate one forecast package immediately

```text
backend/utils/generate_forecast_package.py
```

Stub:

```bash
docker compose exec -T backend python utils/generate_forecast_package.py \
  --date 2026-06-06 \
  --provider stub \
  --show-items
```

OpenAI:

```bash
docker compose exec -T backend python utils/generate_forecast_package.py \
  --date 2026-06-06 \
  --provider openai \
  --allow-openai \
  --show-items \
  --show-errors
```

### Create queued generation jobs

```text
backend/utils/create_generation_jobs.py
```

Stub backfill jobs:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-06-15 \
  --end-date 2026-06-17 \
  --provider stub \
  --skip-covered \
  --show-items
```

OpenAI backfill jobs:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-06-15 \
  --end-date 2026-06-17 \
  --provider openai \
  --allow-openai \
  --skip-covered \
  --show-items
```

Dry run:

```bash
docker compose exec -T backend python utils/create_generation_jobs.py \
  --start-date 2026-06-15 \
  --end-date 2026-06-17 \
  --provider stub \
  --skip-covered \
  --dry-run \
  --show-items
```

### Process queued jobs manually

```text
backend/utils/process_generation_jobs.py
```

Stub:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs
```

OpenAI:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --limit 1 \
  --worker-id local-manual \
  --show-jobs \
  --allow-openai
```

Close stale locks before processing:

```bash
docker compose exec -T backend python utils/process_generation_jobs.py \
  --close-stale \
  --stale-after-minutes 60 \
  --limit 1 \
  --show-jobs
```

### Forecast package report

```text
backend/utils/forecast_package_report.py
```

Examples:

```bash
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-05
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-05 --compact
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-05 --show-metadata
docker compose exec -T backend python utils/forecast_package_report.py --date 2026-06-05 --json
```

The report checks package size, source/model distribution, variation profile distribution, duplicate titles/endings, forbidden terms, and soft repetition hints.

## Smoke tests

### Backend tests

Use the safe isolated test database script:

```bash
bash scripts/backend-test.sh
```

Keep test database after run:

```bash
KEEP_TEST_DB=1 bash scripts/backend-test.sh
```

Do not run pytest directly against the normal development database unless you intentionally know what you are doing. The test fixture refuses to clean the default dev database by default.

### Queue CLI smoke with stub

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

### Scheduler queue-mode smoke with stub

```bash
GENERATION_SCHEDULER_USE_QUEUE=1 \
GENERATION_JOB_WORKER_ENABLED=1 \
GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK=1 \
GENERATION_JOB_WORKER_ALLOW_OPENAI=0 \
RUN_NIGHTLY_ON_START=1 \
HOROSCOPE_PROVIDER=stub \
docker compose up -d --force-recreate scheduler
```

Check scheduler logs:

```bash
docker compose logs scheduler --tail=120
```

Check recent jobs:

```bash
docker compose exec -T backend python - <<'PY'
from app import create_app
from app.models import GenerationJob

app = create_app()

with app.app_context():
    for job in GenerationJob.query.order_by(GenerationJob.id.desc()).limit(10).all():
        print(
            f"id={job.id} "
            f"type={job.job_type} "
            f"date={job.target_date} "
            f"status={job.status} "
            f"provider={job.provider} "
            f"run_id={job.run_id} "
            f"created_by={job.created_by} "
            f"error={job.error_message}"
        )
PY
```

Validate generated package:

```bash
docker compose exec -T backend python utils/forecast_package_report.py \
  --date YYYY-MM-DD \
  --compact
```

Expected for a complete package:

```text
forecast_count: 13
status: published
forbidden_hits: none
```

## GitHub Actions

Backend tests are run by GitHub Actions using the backend test workflow in:

```text
.github/workflows/
```

Local equivalent:

```bash
bash scripts/backend-test.sh
```

## Development notes

Keep these rules in mind when changing generation code:

```text
Do not break existing frontend API response shapes.
Do not pass zodiac sign names or target dates into user-facing prompt messages.
Keep OpenAI disabled by default in local/dev automation.
Use queued jobs for backfill and scheduled automation.
Use generation_runs/items/attempts as execution audit trail.
Prefer small commits with tests.
```

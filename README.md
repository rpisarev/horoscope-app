# Horoscope App

Vue + Flask application for sign-agnostic daily horoscope forecast generation.

Current working branch:

```text
feature/openai-provider
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
Backend tests + GitHub Actions CI
```

The frontend/UI is treated as mostly formed for now. The main active work is backend generation infrastructure and forecast quality.

---

## Current state summary

The app runs locally through Docker Compose.

Docker Compose services:

```text
frontend   Vue/Vite dev server
backend    Flask API
scheduler  APScheduler process for daily generation
db         PostgreSQL 17 Alpine
```

Default local URLs:

```text
frontend: http://localhost:5173
backend:  http://localhost:8000
```

Generation providers:

```text
stub    default local/dev provider
openai  implemented provider for real model generation
```

Planned future providers:

```text
local-LLM
```

Current selected OpenAI model for production prompt version:

```text
gpt-5.4-mini
```

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
│   │   │   ├── generation_service.py
│   │   │   ├── prompt_service.py
│   │   │   ├── prompt_variation_service.py
│   │   │   └── sign_service.py
│   │   ├── config.py
│   │   ├── models.py
│   │   └── routes.py
│   ├── migrations/
│   ├── tests/
│   ├── utils/
│   │   └── openai_prompt_probe.py
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

The app can run without `.env` because `docker-compose.yml` defines defaults.

To override local settings:

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

HOROSCOPE_PROVIDER=stub

# For real OpenAI generation:
# HOROSCOPE_PROVIDER=openai
# OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_MODEL=gpt-5.4-mini
# OPENAI_TIMEOUT_SECONDS=30
# OPENAI_MAX_OUTPUT_TOKENS=500
```

Do not commit `.env`.

Note: after choosing `gpt-5.4-mini` as the working model, keep local `.env` aligned with that value when using `HOROSCOPE_PROVIDER=openai`.

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

### `scheduler`

Separate APScheduler process.

Startup command:

```bash
python tasks.py
```

By default it schedules daily forecast generation at:

```text
01:00 Europe/Kyiv
```

It uses the same Flask app code and the same PostgreSQL database as the API.

To force generation when the scheduler starts, set:

```env
RUN_NIGHTLY_ON_START=1
```

Then start/restart the scheduler.

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
<base> -> 0001_initial_schema
0001_initial_schema -> 0002_add_generation_attempts
0002_add_generation_attempts -> 0003_prompt_pipeline
0003_prompt_pipeline -> 0004_variation_prompt
```

Check current migration:

```bash
docker compose exec backend alembic current
```

Expected after current migrations:

```text
0004_variation_prompt (head)
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

Migration `0004_variation_prompt` updates `daily-ru-v1` to a variation-aware prompt and sets the working model:

```text
gpt-5.4-mini
```

The current production prompt is sign-agnostic and date-agnostic in rendered message content. Date/sign metadata may exist in request metadata for audit/debugging, but user-facing prompt content should not instruct the provider to generate for a specific sign or date.

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

### `generation_runs`

One generation run, such as a scheduled nightly generation or manual run.

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

This table is the detailed audit trail for provider calls.

Skipped items should not create attempts.

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
prompt_variation_service.py
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
sign_service.py                    enabled sign lookup
prompt_service.py                  prompt variables/rendering/provider request building
prompt_variation_service.py        deterministic neutral variation profiles
forecast_service.py                forecast read/write compatibility helpers
forecast_validation_service.py     forbidden zodiac term checks
generation_service.py              run/item/attempt lifecycle, retry, coverage checks
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

Production prompt generation now uses deterministic neutral variation profiles.

Variation profile selection may use internal data:

```text
sign_key
target_date
locale
forecast_type
```

But rendered prompt messages receive only neutral profile fields, such as:

```text
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

This keeps prompts sign/date-agnostic while avoiding 13 daily forecasts that all sound the same.

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

Known zodiac signs use deterministic rotation over the profile list for a given date, so the daily package uses all available profiles with minimal repeats while keeping the selection stable.

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

Supported prompt variables include general fields:

```text
locale
forecast_type
output_language
address_style
sentence_count
```

and variation fields:

```text
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

A daily generation run works like this:

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

## Runtime checks used during development

Manual generation with stub provider:

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

Expected first run on an empty date:

```text
status: success
total: 13
success: 13
skipped: 0
failed: 0
```

Expected second run for the same date:

```text
status: success
total: 13
success: 0
skipped: 13
failed: 0
```

If one forecast is manually marked failed:

```sql
update forecasts set status='failed' where id=3;
```

Expected next run:

```text
status: success
total: 13
success: 1
skipped: 12
failed: 0
```

This confirms failed forecast recovery and no unnecessary provider attempts for skipped items.

---

## OpenAI local smoke check

By default the app uses:

```env
HOROSCOPE_PROVIDER=stub
```

To try real OpenAI generation locally, create/update `.env`:

```env
HOROSCOPE_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=500
```

Then restart backend/scheduler:

```bash
docker compose up --build
```

Manual OpenAI generation for current date:

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
        provider_name="openai",
    )

    print("run_id:", run.id)
    print("status:", run.status)
    print("total:", run.total_items)
    print("success:", run.success_items)
    print("skipped:", run.skipped_items)
    print("failed:", run.failed_items)
PY
```

Check attempts:

```sql
select
  a.id,
  a.item_id,
  i.sign_key,
  a.attempt_no,
  a.status,
  a.provider,
  a.model_name,
  a.error_type,
  a.error_message
from generation_attempts a
join generation_items i on i.id = a.item_id
order by a.id desc
limit 20;
```

Check generated forecasts:

```sql
select
  id,
  sign_key,
  target_date,
  status,
  source,
  model_name,
  generation_item_id
from forecasts
order by id desc
limit 20;
```

Do not commit real OpenAI keys.

---

## OpenAI prompt probe utility

Development utility:

```text
backend/utils/openai_prompt_probe.py
```

Purpose: test model and prompt quality without Flask app or DB.

Useful commands:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini
```

List available profiles without making an API request:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --list-profiles
```

Run one selected profile:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini --profile relationships
```

Run a small batch:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini --batch 13 --seed 42
```

Show prompt before requests:

```bash
docker compose exec -T backend python utils/openai_prompt_probe.py --model gpt-5.4-mini --profile creative_view --show-prompt
```

The utility is for prompt/model experimentation only. Production generation should use `generation_service.py`.

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

Recent runs:

```sql
select
  id,
  run_type,
  target_date,
  status,
  total_items,
  success_items,
  skipped_items,
  failed_items,
  started_at,
  finished_at
from generation_runs
order by id desc
limit 5;
```

Items for a run:

```sql
select
  id,
  run_id,
  sign_key,
  target_date,
  status,
  forecast_id,
  provider,
  model_name,
  error_message
from generation_items
where run_id = 1
order by id;
```

Attempts for a run:

```sql
select
  a.id,
  a.item_id,
  i.sign_key,
  i.run_id,
  a.attempt_no,
  a.status,
  a.provider,
  a.error_type,
  a.error_message
from generation_attempts a
join generation_items i on i.id = a.item_id
where i.run_id = 1
order by a.id;
```

Forecasts:

```sql
select
  id,
  sign_key,
  target_date,
  locale,
  forecast_type,
  status,
  source,
  model_name,
  generation_item_id
from forecasts
order by id desc
limit 20;
```

Exit psql:

```sql
\q
```

---

## Backend API

The API remains frontend-compatible.

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
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-05-17"
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
  "day": "2026-05-17",
  "date": "2026-05-17",
  "text": "...",
  "forecast": "...",
  "status": "published",
  "source": "openai",
  "model_version": "gpt-5.4-mini",
  "model_name": "gpt-5.4-mini"
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

Safety guard: the script refuses to run against the default development DB name `horoscope`.

OpenAI provider tests are mock-based and do not make real OpenAI API requests.

Current confirmed local test result after OpenAI provider and variation profiles:

```text
62 passed in 2.55s
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

## Current confirmed status

```text
Docker Compose dev                   done
PostgreSQL dev                       done
Docker secrets                       done
Backend config                       done
Alembic environment                  done
0001 initial schema                  done
0002 generation_attempts             done
0003 prompt pipeline                 done
0004 variation prompt                done
Models expanded                      done
Service layer split                  done
Provider abstraction                 done
Stub provider                        done
OpenAI provider                      done
OpenAI provider mock tests           done
Prompt probe utility                 done
Prompt variation service             done
Variation profiles in production     done
Deterministic variation selection    done
Sign-agnostic generation             done
Prompt-building pipeline             done
Forecast validation                  done
Generation lifecycle                 done
Generation runs/items/attempts       done
Skipped behavior confirmed           done
Failed forecast recovery             done
Retry missing forecasts              done
Stale running run cleanup            done
Backend pytest baseline              done
GitHub Actions backend CI            done
API compatibility preserved          done
Working OpenAI model selected        gpt-5.4-mini
README                               updated for feature/openai-provider

Local LLM provider                   not implemented yet
Admin/manual generation API          not implemented yet
Archive API improvements             not implemented yet
/api/signs/meta                      not implemented yet
Production deploy                    not implemented yet
```

---

## Known limitations / next work

### 1. Real OpenAI package quality check

The technical pipeline is implemented, but the generated daily package should still be reviewed as a set of 13 forecasts.

Check for:

```text
enough variation between signs
no forbidden zodiac terms
no dates in text
no repeated title pattern
no repeated ending pattern
no excessive productivity tone
```

### 2. Admin/manual generation API

Manual generation is currently possible from Python commands.

A future admin endpoint could trigger:

```text
manual generation for date
retry missing forecasts
regenerate one sign/date slot
inspect run/item/attempt status
```

This should not be exposed publicly without authentication.

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
```

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

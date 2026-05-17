# Horoscope App

Vue + Flask application for daily horoscope generation.

The current local development setup uses Docker Compose and runs four services:

- `frontend` — Vue/Vite dev server
- `backend` — Flask API
- `scheduler` — separate APScheduler process for scheduled horoscope generation
- `db` — PostgreSQL database

The app is still in development. Horoscope generation is currently implemented as a placeholder in `backend/app/services.py`.

---

## Project structure

```text
horoscope-app/
├── backend/              # Flask backend
│   ├── app/              # Flask app, models, routes, services
│   ├── migrations/       # Alembic migration environment
│   ├── tests/            # Backend pytest test suite
│   ├── alembic.ini       # Alembic configuration
│   ├── Dockerfile        # Backend development image
│   ├── pytest.ini        # Pytest configuration
│   ├── requirements.txt  # Python dependencies
│   ├── run.py            # Flask dev server entry point
│   └── tasks.py          # Scheduler entry point
├── frontend/             # Vue frontend
├── secrets/              # Local Docker secrets, not committed to git
├── docker-compose.yml    # Local development Compose setup
├── .env.example          # Optional non-secret local overrides
└── README.md
```

---

## Requirements

For the recommended local development flow you need:

- Ubuntu/Linux shell
- Docker Engine
- Docker Compose plugin

Check installation:

```bash
docker --version
docker compose version
```

---

## Initial setup

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

The file `secrets/postgres_password.txt` is required by `docker-compose.yml`.

It must not be committed to git.

Verify that it is ignored:

```bash
git check-ignore -v secrets/postgres_password.txt
```

Expected result: git should report that the file is ignored by `.gitignore`.

---

## Optional `.env` file

The project works without a local `.env` file because `docker-compose.yml` has defaults.

If you want to override non-secret local settings, copy the example file:

```bash
cp .env.example .env
```

Available options:

```env
APP_TIMEZONE=Europe/Kyiv
LOG_LEVEL=INFO

SCHEDULE_HOUR=1
SCHEDULE_MINUTE=0

RUN_NIGHTLY_ON_START=0

# Future LLM integration
# OPENAI_API_KEY=your_openai_api_key_here
```

Do not commit `.env`.

---

## Run the app with Docker Compose

Start all services:

```bash
docker compose up --build
```

The first launch can take some time because Docker needs to:

- pull the PostgreSQL image
- build the backend image
- install Python dependencies
- start the Node/Vite frontend container
- run `npm install` for the frontend
- create the PostgreSQL volume
- run Alembic migrations

After startup, open:

```text
http://localhost:5173
```

Backend API is available at:

```text
http://localhost:8000
```

---

## Services

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
```

Data is stored in the Docker named volume:

```text
postgres_data
```

### `backend`

Flask API container.

On startup it currently runs:

```bash
alembic upgrade head && python run.py
```

This means the backend applies all Alembic migrations before starting the Flask development server.

### `scheduler`

Separate scheduler container.

It runs:

```bash
python tasks.py
```

By default it schedules daily generation at:

```text
01:00 Europe/Kyiv
```

The scheduler uses the same backend code and the same PostgreSQL database as the API.

To force generation on scheduler startup, set:

```env
RUN_NIGHTLY_ON_START=1
```

Then restart the scheduler:

```bash
docker compose restart scheduler
```

### `frontend`

Vue/Vite dev server.

It is available at:

```text
http://localhost:5173
```

Inside Docker, Vite proxies API requests to:

```text
http://backend:8000
```

Outside Docker, if you run the frontend manually, the default API proxy target is:

```text
http://localhost:8000
```

---

## Useful Docker commands

Start all services in the foreground:

```bash
docker compose up --build
```

Start all services in the background:

```bash
docker compose up --build -d
```

Show service status:

```bash
docker compose ps
```

Show logs for all services:

```bash
docker compose logs -f
```

Show logs for one service:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f scheduler
docker compose logs -f db
```

Restart one service:

```bash
docker compose restart backend
docker compose restart frontend
docker compose restart scheduler
docker compose restart db
```

Stop services but keep volumes:

```bash
docker compose down
```

Stop services and delete volumes:

```bash
docker compose down -v
```

Warning: `docker compose down -v` deletes the local PostgreSQL data volume.

---

## Alembic migrations

The project uses Alembic for database migrations.

The backend container runs migrations automatically before starting Flask:

```bash
alembic upgrade head
```

Run migrations manually:

```bash
docker compose run --rm backend alembic upgrade head
```

Check current Alembic revision:

```bash
docker compose run --rm backend alembic current
```

Create a new migration later:

```bash
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
```

Then review the generated migration before committing it.

The old `db.create_all()` flow is no longer used.

---

## Backend tests

Backend tests use `pytest`.

They verify:

- Alembic schema tables exist
- initial seed data exists
- `/api/signs` keeps the current frontend-compatible response shape
- `/api/forecast` creates and returns published stub forecasts
- `/api/forecast` is idempotent for the same sign/date
- `/api/forecast` rejects unknown signs and invalid dates
- `/api/years` fallback and DB-backed behavior
- `Forecast.to_dict()` backward-compatible response fields
- `ZodiacSign.to_dict()` date-range formatting
- `save_forecast()` create/update behavior
- config secret-file helpers
- scheduler module import smoke test

Run tests from the repository root:

```bash
docker compose up -d db
docker compose run --rm backend sh -c "alembic upgrade head && pytest -q"
```

A clean full test run:

```bash
docker compose down -v
docker compose up -d db
docker compose run --rm backend sh -c "alembic upgrade head && pytest -q"
docker compose down
```

Warning: tests clean mutable backend tables:

```text
forecasts
generation_runs
generation_items
```

Seed/reference tables are kept:

```text
zodiac_signs
prompt_versions
```

If `pytest` cannot import the `app` package, make sure `backend/pytest.ini` contains:

```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
addopts = -ra
```

---

## Backend API

### Get available signs

```bash
curl http://localhost:8000/api/signs
```

Returns a frontend-compatible list of supported zodiac sign keys:

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

This endpoint intentionally returns a list of strings for now.

The database already has richer sign metadata in `zodiac_signs`, but the API response shape is kept stable for the current frontend.

### Get forecast

```bash
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-05-10"
```

Parameters:

- `sign` — zodiac sign key
- `date` — optional date in `YYYY-MM-DD` format
- `locale` — optional, defaults to `ru`
- `type` — optional forecast type, defaults to `daily`

If no forecast exists yet, the backend currently generates and saves a placeholder forecast.

Example response shape:

```json
{
  "id": 1,
  "sign": "aries",
  "sign_key": "aries",
  "day": "2026-05-10",
  "date": "2026-05-10",
  "locale": "ru",
  "forecast_type": "daily",
  "title": null,
  "text": "Вас ждет спокойный день, в котором лучше не спешить с выводами...",
  "forecast": "Вас ждет спокойный день, в котором лучше не спешить с выводами...",
  "payload": null,
  "status": "published",
  "source": "stub",
  "model_version": "stub",
  "model_name": "stub",
  "prompt_version": "daily-ru-v1"
}
```

### Get years

```bash
curl http://localhost:8000/api/years
```

Optional filters:

```bash
curl "http://localhost:8000/api/years?sign=aries"
```

Current behavior:

- if published forecasts exist in the database, years are derived from `forecasts.target_date`;
- if no forecasts exist yet, the endpoint falls back to the range from `2024` to the current year.

---

## Database access

Open PostgreSQL shell inside the database container:

```bash
docker compose exec db psql -U horoscope -d horoscope
```

Useful SQL commands:

```sql
\dt
select * from alembic_version;
select key, name_ru, sort_order from zodiac_signs order by sort_order;
select key, is_active from prompt_versions;
select id, sign_key, target_date, status, source from forecasts;
```

Exit `psql`:

```sql
\q
```

---

## Recreate local database

If you need to fully reset the local development database:

```bash
docker compose down -v
docker compose up --build
```

This deletes the `postgres_data` volume and creates a fresh database.

Use this only for local development.

---

## Current database schema

The current initial schema is managed by Alembic.

Main tables:

```text
zodiac_signs
prompt_versions
forecasts
generation_runs
generation_items
```

### `zodiac_signs`

Stores zodiac sign metadata.

Seeded by the initial Alembic migration.

### `prompt_versions`

Stores prompt version metadata.

Currently seeded with:

```text
daily-ru-v1
```

### `forecasts`

Stores generated/published horoscope texts.

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

### `generation_runs`

Reserved for tracking scheduled/manual generation runs.

The table exists, but scheduler lifecycle logic is not implemented yet.

### `generation_items`

Reserved for tracking generation of each sign inside a generation run.

The table exists, but scheduler lifecycle logic is not implemented yet.

---

## Manual development without Docker

Docker Compose is the recommended local development flow.

Manual launch is still possible, but it is not the primary workflow anymore.

Backend:

```bash
cd backend
python3 -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python run.py
```

Frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Manual mode uses backend configuration fallback. If no `DATABASE_URL` or `POSTGRES_*` variables are set, the backend falls back to SQLite.

---

## Secrets and git safety

The repository should contain:

```text
secrets/.gitkeep
```

The repository must not contain:

```text
secrets/postgres_password.txt
.env
frontend/node_modules/
backend/db.sqlite3
*.sqlite3
*.db
```

Before committing infrastructure changes, check:

```bash
git status --short
git diff --cached --name-only
```

Make sure these files are not staged:

```text
secrets/postgres_password.txt
.env
```

---

## Troubleshooting

### `docker: command not found`

Docker is not installed. Install Docker Engine and the Docker Compose plugin first.

### `permission denied while trying to connect to the Docker daemon socket`

Your user may not be in the `docker` group.

Temporary workaround:

```bash
sudo docker compose up --build
```

Recommended local fix:

```bash
sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker "$USER"
newgrp docker
```

If it still fails, log out and log back in.

### Port `5432` is already in use

Another PostgreSQL instance may already be running on your laptop.

In `docker-compose.yml`, change:

```yaml
ports:
  - "5432:5432"
```

to:

```yaml
ports:
  - "5433:5432"
```

The backend will still use `db:5432` inside the Docker network.

### Port `5173` is already in use

Stop the old manually started frontend:

```bash
pkill -f "vite"
```

Or stop the process manually from the terminal where it was started.

### Port `8000` is already in use

Stop the old manually started backend.

You can search for the process:

```bash
lsof -i :8000
```

Then stop it manually.

### PostgreSQL password was changed but login still fails

If the database volume already exists, changing `secrets/postgres_password.txt` does not automatically change the password of the existing PostgreSQL user.

For local development, reset the database volume:

```bash
docker compose down -v
docker compose up --build
```

Warning: this deletes local database data.

---

## Notes for future backend work

The current Docker Compose setup is a development environment, not a production deployment.

Next backend steps:

1. Implement generation lifecycle in the scheduler.
2. Use `generation_runs` and `generation_items` during scheduled generation.
3. Split `services.py` into smaller service modules.
4. Add prompt pipeline.
5. Replace placeholder horoscope generation with a real LLM provider.
6. Add GitHub Actions workflow for backend tests.
7. Add production deployment configuration separately.

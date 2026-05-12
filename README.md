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
├── backend/                 # Flask backend
│   ├── app/                 # Flask app, models, routes, services
│   ├── migrations/          # Alembic migration environment
│   ├── alembic.ini          # Alembic configuration
│   ├── Dockerfile           # Backend development image
│   ├── requirements.txt     # Python dependencies
│   ├── run.py               # Flask dev server entry point
│   └── tasks.py             # Scheduler entry point
├── frontend/                # Vue frontend
├── secrets/                 # Local Docker secrets, not committed to git
├── docker-compose.yml       # Local development Compose setup
├── .env.example             # Optional non-secret local overrides
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

If Docker is not installed, install Docker Engine and the Docker Compose plugin first.

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

The old `db.create_all()` workflow is no longer used. `backend/app/init_db.py` now exits with a message telling you to use Alembic.

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

For example, in `.env`:

```env
RUN_NIGHTLY_ON_START=1
```

Then restart the scheduler:

```bash
docker compose restart scheduler
```

Current scheduler limitation: the database tables for generation tracking already exist, but the scheduler does not yet create `generation_runs` and `generation_items`. It currently generates placeholder forecasts directly.

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

## Useful commands

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

## Clean local database start

After database schema changes, especially after switching from the old `db.create_all()` flow to Alembic, reset the local development database:

```bash
docker compose down -v
docker compose up --build
```

This removes the old PostgreSQL volume and recreates the database from Alembic migrations.

Use this only for local development.

---

## Alembic migrations

This project now uses Alembic for database migrations.

Migration files live in:

```text
backend/migrations/
```

Current initial migration:

```text
backend/migrations/versions/0001_initial_schema.py
```

The initial migration creates:

```text
zodiac_signs
prompt_versions
forecasts
generation_runs
generation_items
```

The backend container automatically runs:

```bash
alembic upgrade head
```

before starting Flask.

Run migrations manually from the backend container:

```bash
docker compose exec backend alembic upgrade head
```

Check current migration version:

```bash
docker compose exec backend alembic current
```

Show migration history:

```bash
docker compose exec backend alembic history
```

Create a new autogenerated migration after changing SQLAlchemy models:

```bash
docker compose exec backend alembic revision --autogenerate -m "Describe change"
```

Then review the generated migration file manually before applying it.

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

The initial migration seeds 13 signs, including `ophiuchus`.

### `prompt_versions`

Stores prompt version metadata for future LLM generation.

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

The initial migration seeds one prompt version:

```text
daily-ru-v1
```

### `forecasts`

Stores generated or manually edited forecasts.

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

This means one sign can have only one forecast for the same date, locale and forecast type.

### `generation_runs`

Stores one generation run, for example a scheduled nightly generation for all signs.

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

The table exists, but the scheduler does not fully use it yet.

### `generation_items`

Stores one generated item inside a generation run, usually one sign for one date.

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

The table exists, but the scheduler does not fully use it yet.

---

## Database access

Open PostgreSQL shell inside the database container:

```bash
docker compose exec db psql -U horoscope -d horoscope
```

Useful SQL commands:

```sql
\dt
select key, name_ru, sort_order from zodiac_signs order by sort_order;
select key, is_active from prompt_versions;
select id, sign_key, target_date, status, source from forecasts order by id desc limit 10;
select * from alembic_version;
```

Exit `psql`:

```sql
\q
```

---

## Backend API

### Get available signs

```bash
curl http://localhost:8000/api/signs
```

Returns a frontend-compatible list of supported zodiac sign keys.

Current response shape:

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

Note: the database now has a `zodiac_signs` table with richer metadata, but `/api/signs` intentionally keeps the old response shape for frontend compatibility.

### Get forecast

```bash
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-05-12"
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
  "day": "2026-05-12",
  "date": "2026-05-12",
  "locale": "ru",
  "forecast_type": "daily",
  "title": null,
  "text": "Для Aries этот день (2026-05-12) обещает новые возможности, спокойные решения и полезные совпадения.",
  "forecast": "Для Aries этот день (2026-05-12) обещает новые возможности, спокойные решения и полезные совпадения.",
  "payload": null,
  "status": "published",
  "source": "stub",
  "model_version": "stub",
  "model_name": "stub",
  "prompt_version": "daily-ru-v1"
}
```

The response intentionally includes both old and new field names, for example `sign` and `sign_key`, `day` and `date`, `text` and `forecast`.

### Get years

```bash
curl http://localhost:8000/api/years
```

Optional filters:

```bash
curl "http://localhost:8000/api/years?sign=aries"
curl "http://localhost:8000/api/years?sign=aries&locale=ru&type=daily"
```

The endpoint tries to return years that exist in the `forecasts` table for published forecasts.

If there are no forecasts yet, it falls back to a simple year range from 2024 to the current year.

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

Manual backend mode uses the backend configuration fallback. If no `DATABASE_URL` or `POSTGRES_*` variables are set, the backend falls back to SQLite.

Important: if you run manual mode with SQLite, Alembic and the current migration were primarily prepared for PostgreSQL. The recommended path is Docker Compose with PostgreSQL.

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

### Alembic says a table already exists

This usually means the local PostgreSQL volume was created before the Alembic initial schema and still contains old tables.

Reset the local dev database:

```bash
docker compose down -v
docker compose up --build
```

### `python -m app.init_db` no longer works

That is expected. The project now uses Alembic migrations.

Use:

```bash
alembic upgrade head
```

or, inside Docker:

```bash
docker compose exec backend alembic upgrade head
```

---

## Current backend status

Done:

- Docker Compose local development environment
- PostgreSQL development database
- Docker Compose secret for PostgreSQL password
- Alembic migration environment
- Initial database schema migration
- Expanded SQLAlchemy models
- Frontend-compatible `/api/signs`
- Backward-compatible `/api/forecast` response
- Basic `/api/years` based on existing published forecasts, with fallback

Still to do:

- update scheduler to create `generation_runs` and `generation_items`
- split backend service layer into smaller modules
- implement real prompt building and LLM provider calls
- store request/response payloads for generation attempts
- add backend tests
- add admin/manual generation endpoints later
- prepare separate production deployment configuration later

---

## Notes for future production deployment

The current Docker Compose setup is a development environment, not a production deployment.

For production, the project should later use:

- backend served by Gunicorn or another WSGI server
- frontend static build served by nginx/caddy or another web server
- PostgreSQL backups
- production-grade secret management
- a separate migration step before starting web containers
- separate production Compose or deployment configuration

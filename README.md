# Horoscope App

Vue + Flask application for daily horoscope generation.

Current development setup uses Docker Compose and runs four services:

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

If Docker is not installed, install Docker Engine and the Compose plugin first.

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

You can verify that it is ignored:

```bash
git check-ignore -v secrets/postgres_password.txt
```

Expected result: git should report that the file is ignored by `.gitignore`.

---

## Optional `.env` file

The project works without a local `.env` file because `docker-compose.yml` has sensible defaults.

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
python -m app.init_db && python run.py
```

`app.init_db` creates database tables for local development using SQLAlchemy `db.create_all()`.

This is a development helper. In the future it should be replaced with Alembic migrations.

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

## Backend API

### Get available signs

```bash
curl http://localhost:8000/api/signs
```

Returns a list of supported zodiac sign keys.

Current signs:

```text
aries
taurus
gemini
cancer
leo
virgo
libra
scorpio
sagittarius
capricorn
aquarius
pisces
ophiuchus
```

### Get forecast

```bash
curl "http://localhost:8000/api/forecast?sign=aries&date=2026-05-10"
```

Parameters:

- `sign` — zodiac sign key
- `date` — optional date in `YYYY-MM-DD` format

If no forecast exists yet, the backend currently generates and saves a placeholder forecast.

Example response shape:

```json
{
  "id": 1,
  "sign": "aries",
  "day": "2026-05-10",
  "text": "Для Aries цей день (2026-05-10) обіцяє успіх і нові можливості.",
  "model_version": "stub"
}
```

### Get years

```bash
curl http://localhost:8000/api/years
```

Currently returns a simple year range from 2024 to the current year.

This endpoint should later be changed to return years that actually exist in the forecasts table.

---

## Database access

Open PostgreSQL shell inside the database container:

```bash
docker compose exec db psql -U horoscope -d horoscope
```

Useful SQL commands:

```sql
\dt
select * from forecasts limit 10;
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

## Current database model

Current `forecasts` table is minimal:

```text
id
sign
day
text
model_version
created_at
```

There is a unique constraint on:

```text
sign + day
```

This model is expected to evolve.

Planned backend improvements:

- add Alembic migrations
- extend forecast metadata
- add locale and forecast type
- add generation status
- add generation run logs
- add prompt versioning
- replace placeholder generation with real LLM generation

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
python -m app.init_db
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

Manual mode uses the backend configuration fallback. If no `DATABASE_URL` or `POSTGRES_*` variables are set, the backend falls back to SQLite.

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

1. Add Alembic or Flask-Migrate.
2. Replace `db.create_all()` with migrations.
3. Expand the `Forecast` model.
4. Add generation run tracking.
5. Add prompt versioning.
6. Replace placeholder horoscope generation with a real LLM provider.
7. Add production deployment configuration separately.

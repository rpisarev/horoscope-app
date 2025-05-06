# Horoscope App (Flask + Vue)

## Quick start

```bash
# clone repository
unzip horoscope-app.zip && cd horoscope-app
# Backend
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
python - <<'PY'
from app import db, create_app
app = create_app()
app.app_context().push()
db.create_all()
PY

Copy .env.example -> .env and substitute your API key
python backend/run.py
# Frontend (in new terminal)
cd frontend
npm install
npm run dev
```

Now open http://localhost:5173 in your browser.

### Using Docker

```bash
docker-compose up --build
```

### Replace placeholder generator

Edit `backend/app/services.py` and implement `generate_horoscope` with your LLM or OpenAI call.

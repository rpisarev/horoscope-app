import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None

    secret_path = Path(path)
    if not secret_path.exists():
        return None

    value = secret_path.read_text(encoding="utf-8").strip()
    return value or None


def _build_postgres_uri() -> str | None:
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = (
        _read_secret_file(os.getenv("POSTGRES_PASSWORD_FILE"))
        or os.getenv("POSTGRES_PASSWORD")
    )

    if not all([host, port, db_name, user, password]):
        return None

    safe_user = quote_plus(user)
    safe_password = quote_plus(password)
    safe_db_name = quote_plus(db_name)
    return f"postgresql+psycopg://{safe_user}:{safe_password}@{host}:{port}/{safe_db_name}"


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or _build_postgres_uri()
        or "sqlite:///db.sqlite3"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ADMIN_API_ENABLED = _env_flag("ADMIN_API_ENABLED", "0")
    ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN")
    ADMIN_API_ALLOW_OPENAI = _env_flag("ADMIN_API_ALLOW_OPENAI", "0")
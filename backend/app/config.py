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


def _env_int(
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None or raw_value == "":
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be greater than or equal to {min_value}.")

    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be less than or equal to {max_value}.")

    return value


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

    GENERATION_JOB_WORKER_ENABLED = _env_flag("GENERATION_JOB_WORKER_ENABLED", "0")
    GENERATION_JOB_WORKER_INTERVAL_SECONDS = _env_int(
        "GENERATION_JOB_WORKER_INTERVAL_SECONDS",
        60,
        min_value=5,
        max_value=86400,
    )
    GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK = _env_int(
        "GENERATION_JOB_WORKER_MAX_JOBS_PER_TICK",
        1,
        min_value=1,
        max_value=100,
    )
    GENERATION_JOB_WORKER_ALLOW_OPENAI = _env_flag(
        "GENERATION_JOB_WORKER_ALLOW_OPENAI",
        "0",
    )
    GENERATION_JOB_STALE_AFTER_MINUTES = _env_int(
        "GENERATION_JOB_STALE_AFTER_MINUTES",
        60,
        min_value=1,
        max_value=10080,
    )
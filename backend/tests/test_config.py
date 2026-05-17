from app.config import _build_postgres_uri, _read_secret_file


def test_read_secret_file_returns_none_for_missing_path():
    assert _read_secret_file(None) is None


def test_read_secret_file_reads_trimmed_value(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("  secret-password\n", encoding="utf-8")

    assert _read_secret_file(str(secret_file)) == "secret-password"


def test_build_postgres_uri_from_env_and_secret_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "postgres_password.txt"
    secret_file.write_text("password with spaces\n", encoding="utf-8")

    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "horoscope")
    monkeypatch.setenv("POSTGRES_USER", "horoscope")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(secret_file))
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    uri = _build_postgres_uri()

    assert uri == "postgresql+psycopg://horoscope:password+with+spaces@db:5432/horoscope"


def test_build_postgres_uri_returns_none_when_env_is_incomplete(monkeypatch):
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD_FILE", raising=False)

    assert _build_postgres_uri() is None
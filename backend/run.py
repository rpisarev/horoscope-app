import os

from app import create_app

app = create_app()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    debug = _as_bool(os.getenv("FLASK_DEBUG"), default=True)

    app.run(host="0.0.0.0", port=port, debug=debug)
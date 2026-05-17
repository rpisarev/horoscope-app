import os

import pytest
from sqlalchemy import text

from app import create_app, db


FORBIDDEN_POSTGRES_TEST_DATABASES = {
    "horoscope",
}


def _assert_safe_test_database() -> None:
    """Prevent pytest cleanup from truncating the local development database."""

    if db.engine.dialect.name != "postgresql":
        return

    current_database = db.session.execute(text("SELECT current_database()")).scalar()

    if (
        current_database in FORBIDDEN_POSTGRES_TEST_DATABASES
        and os.environ.get("ALLOW_PYTEST_ON_DEV_DB") != "1"
    ):
        raise RuntimeError(
            "Refusing to run pytest against the default development database "
            f"'{current_database}'. Use an isolated test database, for example "
            "'horoscope_test'. Local recommended command: "
            "'bash scripts/backend-test.sh'."
        )


def _clean_mutable_tables() -> None:
    """Clean tables that tests are allowed to mutate.

    Keep Alembic seed/reference data:
    - zodiac_signs
    - prompt_versions
    """

    _assert_safe_test_database()

    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text(
                """
                TRUNCATE TABLE
                    generation_attempts,
                    forecasts,
                    generation_items,
                    generation_runs
                RESTART IDENTITY CASCADE
                """
            )
        )
    else:
        db.session.execute(text("UPDATE forecasts SET generation_item_id = NULL"))
        db.session.execute(text("UPDATE generation_items SET forecast_id = NULL"))

        db.session.execute(text("DELETE FROM generation_attempts"))
        db.session.execute(text("DELETE FROM forecasts"))
        db.session.execute(text("DELETE FROM generation_items"))
        db.session.execute(text("DELETE FROM generation_runs"))

    db.session.commit()


@pytest.fixture(scope="session")
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True)

    with flask_app.app_context():
        yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_database(app):
    with app.app_context():
        _clean_mutable_tables()

        yield

        db.session.remove()
        _clean_mutable_tables()
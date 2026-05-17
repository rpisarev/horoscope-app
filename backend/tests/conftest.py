import pytest
from sqlalchemy import text

from app import create_app, db


def _clean_mutable_tables() -> None:
    """Clean tables that tests are allowed to mutate.

    Keep Alembic seed data:
    - zodiac_signs
    - prompt_versions
    """

    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text(
                """
                TRUNCATE TABLE
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
        db.session.execute(text("DELETE FROM generation_items"))
        db.session.execute(text("DELETE FROM generation_runs"))
        db.session.execute(text("DELETE FROM forecasts"))

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
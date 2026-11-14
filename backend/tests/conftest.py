import pytest
from sqlalchemy import text

from test_db_guard import assert_connection, assert_url, prepare_runtime, suite_exit_code

# Reject unsafe configuration and disable dotenv/network before app imports.
TEST_IDENTITY = prepare_runtime()

from app import create_app, db


def pytest_sessionfinish(session, exitstatus):
    session.exitstatus = suite_exit_code(exitstatus)


def _assert_safe_test_database() -> None:
    # Revalidate before each cleanup. Use the SAME session connection for the
    # identity query and subsequent TRUNCATE, including fixture teardown.
    identity = prepare_runtime()
    assert_url(db.engine.url, identity)
    assert_connection(db.session.connection(), identity)


def _clean_mutable_tables() -> None:
    """Clean tables that tests are allowed to mutate.

    Keep Alembic seed/reference data:
    - zodiac_signs
    - prompt_versions
    """
    _assert_safe_test_database()

    db.session.execute(
        text(
            """
                TRUNCATE TABLE
                    generation_attempts,
                    forecasts,
                    generation_items,
                    generation_jobs,
                    generation_runs
                RESTART IDENTITY CASCADE
            """
        )
    )
    db.session.commit()


@pytest.fixture(scope="session")
def app():
    from app.config import Config
    from sqlalchemy.engine import make_url

    assert_url(make_url(Config.SQLALCHEMY_DATABASE_URI), TEST_IDENTITY)

    # Disposable tests must not inherit the operator's deployment policy.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Config, "APP_DEPLOYMENT_MODE", "test")
        patch.setattr(Config, "PRODUCTION_PUBLICATION_PROVIDERS", "openai")
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

from sqlalchemy import inspect

from app import db
from app.models import PromptVersion, ZodiacSign


def test_alembic_schema_tables_exist(app):
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())

    assert "alembic_version" in table_names
    assert "zodiac_signs" in table_names
    assert "prompt_versions" in table_names
    assert "forecasts" in table_names
    assert "generation_runs" in table_names
    assert "generation_items" in table_names
    assert "generation_attempts" in table_names


def test_initial_zodiac_signs_seed_exists(app):
    with app.app_context():
        signs = ZodiacSign.query.order_by(ZodiacSign.sort_order).all()

    assert len(signs) == 13
    assert signs[0].key == "aries"
    assert signs[-1].key == "ophiuchus"
    assert len({sign.key for sign in signs}) == 13
    assert all(sign.is_enabled for sign in signs)


def test_initial_prompt_version_seed_exists(app):
    with app.app_context():
        prompt_version = PromptVersion.query.filter_by(key="daily-ru-v1").first()

    assert prompt_version is not None
    assert prompt_version.locale == "ru"
    assert prompt_version.forecast_type == "daily"
    assert prompt_version.is_active is True
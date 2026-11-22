"""Exercise the versioned rows in STAB-007's disposable database only."""
from hashlib import sha256
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app import db
from demo_fixture_import import (
    DEFAULT_DATASET, MULTILINGUAL_DATASET, Refused, import_fixtures, load_dataset,
)


def run_import(path, *, apply=False):
    # The production marker/role is intentionally absent from the disposable
    # harness. Its connection identity guard remains active on this engine.
    with db.engine.connect() as connection, patch('demo_fixture_import.verify_identity'):
        return import_fixtures(connection.connection.driver_connection, None, load_dataset(path), apply=apply)


def forecast_rows():
    return db.session.execute(text('SELECT * FROM forecasts ORDER BY id')).all()


def test_legacy_sitemap_links_to_the_russian_only_publication(client):
    run_import(DEFAULT_DATASET, apply=True)
    day = '2026-11-21'
    scope = {'from': day, 'to': day, 'include_home': 0}
    inventory = client.get('/api/seo/sitemap/urls', query_string=scope).get_json()
    assert inventory['locale'] == 'ru'
    paths = [item['path'] for item in inventory['items'] if item['sign_key'] == 'aries']
    assert paths == ['/horoscope/aries/2026-11-21?lang=ru', '/archive/aries/2026/11?lang=ru']

    params = {'date': day, 'sign': 'aries'}
    response = client.get('/api/forecast', query_string={**params, 'locale': 'ru'})
    assert response.status_code == 200
    publication = response.get_json()
    assert publication['locale'] == 'ru'
    assert publication['text'] == load_dataset(DEFAULT_DATASET)['texts']['aries']

    english = client.get('/api/seo/sitemap/urls', query_string={**scope, 'locale': 'en'})
    assert english.get_json()['items'] == []
    missing = client.get('/api/forecast', query_string={**params, 'locale': 'en'})
    assert missing.status_code == 404
    assert missing.get_json()['error'] == 'forecast_not_published'


def test_v2_dry_run_repeat_preserves_rows_and_leaves_history_empty(app):
    run_import(DEFAULT_DATASET, apply=True)
    legacy = forecast_rows()
    preview = run_import(MULTILINGUAL_DATASET)
    expected = preview['enabled_signs'] * 3 * 3
    assert preview['would_insert'] == expected and preview['unchanged'] == 0
    assert forecast_rows() == legacy
    applied = run_import(MULTILINGUAL_DATASET, apply=True)
    assert applied['inserted'] == expected and applied['unchanged'] == 0
    combined = forecast_rows()
    assert len(combined) == len(legacy) + expected
    assert combined[:len(legacy)] == legacy
    for path, count in ((DEFAULT_DATASET, len(legacy)), (MULTILINGUAL_DATASET, expected)):
        repeated = run_import(path, apply=True)
        assert repeated['inserted'] == 0 and repeated['unchanged'] == count
    assert forecast_rows() == combined
    for table in ('generation_jobs', 'generation_runs', 'generation_items', 'generation_attempts',
                  'generation_executions', 'generation_execution_runs', 'generation_api_requests',
                  'generation_api_observations'):
        assert db.session.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0


def test_public_translations_resolve_to_published_original_and_archive(client):
    run_import(MULTILINGUAL_DATASET, apply=True)
    before = forecast_rows()
    dataset = load_dataset(MULTILINGUAL_DATASET)
    for day in dataset['dates']:
        original = client.get('/api/forecast', query_string={'date': day, 'sign': 'aries', 'locale': 'en'}).get_json()
        source_key = {'target_date': day, 'sign_key': 'aries', 'locale': 'en', 'forecast_type': 'daily'}
        digest = sha256(original['text'].encode('utf-8')).hexdigest()
        record = next(r for r in dataset['records'] if r['sign_key'] == 'aries' and r['target_date'] == day)
        for locale, displayed in record['texts'].items():
            response = client.get('/api/forecast', query_string={'date': day, 'sign': 'aries', 'locale': locale})
            assert response.status_code == 200
            row = response.get_json()
            assert row['text'] == row['forecast'] == displayed
            assert row['locale'] == locale and row['source'] == 'demo-fixture' and row['status'] == 'published'
            assert row['generated_at'] is None and row['model_name'] is None and row['prompt_version'] is None
            assert row['payload'] == {
                'demo_dataset': dataset['id'], 'dataset_sha256': dataset['digest'],
                'provenance': 'static-demo-fixture', 'ai_generated': False, 'source_version': dataset['id'],
                'source_key': source_key, 'source_text_sha256': digest,
                'content_role': 'original' if locale == 'en' else 'translation',
            }
    for locale in ('en', 'uk', 'ru'):
        params = {'sign': 'aries', 'locale': locale}
        missing = client.get('/api/forecast', query_string={**params, 'date': dataset['missing_date']})
        assert missing.status_code == 404 and missing.get_json()['error'] == 'forecast_not_published'
        month = client.get('/api/archive/month', query_string={
            **params, 'year': '2026', 'month': '11', 'include_latest': '1',
        }).get_json()
        assert month['latest_published_date'] == '2026-11-24'
        assert [d['date'] for d in month['days'] if d['has_forecast']] == dataset['dates']
    assert forecast_rows() == before


@pytest.mark.parametrize(('day', 'reason'), [
    ('2026-11-24', 'Conflicting forecast'),
    ('2026-11-25', 'already published'),
])
def test_import_refuses_existing_translation_or_published_missing_day(app, day, reason):
    with db.engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO forecasts (sign_key,target_date,locale,forecast_type,text,status)
            VALUES ('aries',:day,'uk','daily','Previously published text','published')
        """), {'day': day})
    before = forecast_rows()
    with pytest.raises(Refused, match=reason):
        run_import(MULTILINGUAL_DATASET, apply=True)
    assert forecast_rows() == before

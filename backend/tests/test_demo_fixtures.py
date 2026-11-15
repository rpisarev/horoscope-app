"""SQL/contract regressions exclusively inside STAB-007 disposable PostgreSQL.

The real target guard is tested with mocks separately and against the isolated
Compose demo. These SQL tests replace only that guard for the harness-owned DB.
"""
from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import text
from app import db
from demo_fixture_import import DEFAULT_DATASET, MARKER, Refused, load_dataset, plan_import, _insert_rows


def populate():
    dataset=load_dataset(DEFAULT_DATASET)
    with db.engine.begin() as connection:
        raw=connection.connection.driver_connection
        pending,unchanged,signs=plan_import(raw,dataset)
        with patch('demo_fixture_import.verify_identity'):
            _insert_rows(raw,None,pending)
    return dataset,len(pending),unchanged,signs


def test_explicit_import_and_repeat_are_insert_only(app):
    dataset,count,unchanged,signs=populate()
    assert count==signs*11 and unchanged==0
    with db.engine.begin() as connection:
        raw=connection.connection.driver_connection
        before=connection.execute(text('SELECT id,created_at,updated_at,published_at FROM forecasts ORDER BY id')).all()
        pending,same,_=plan_import(raw,dataset)
        assert pending==[] and same==count
        with patch('demo_fixture_import.verify_identity'):_insert_rows(raw,None,pending)
        assert connection.execute(text('SELECT id,created_at,updated_at,published_at FROM forecasts ORDER BY id')).all()==before
        for table in ['generation_jobs','generation_runs','generation_items','generation_attempts','generation_executions','generation_api_requests']:
            assert connection.execute(text('SELECT count(*) FROM '+table)).scalar_one()==0


def test_plan_dry_run_does_not_write(app):
    with db.engine.begin() as connection:
        pending,_,signs=plan_import(connection.connection.driver_connection,load_dataset(DEFAULT_DATASET))
        assert len(pending)==signs*11
        assert connection.execute(text('SELECT count(*) FROM forecasts')).scalar_one()==0


def test_existing_conflict_refuses_entire_plan(app):
    dataset,_,_,_=populate()
    changed=deepcopy(dataset);changed['texts']['aries']+=' different content'
    with db.engine.begin() as connection:
        before=connection.execute(text('SELECT count(*) FROM forecasts')).scalar_one()
        with pytest.raises(Refused,match='Conflicting'):
            plan_import(connection.connection.driver_connection,changed)
        assert connection.execute(text('SELECT count(*) FROM forecasts')).scalar_one()==before


def test_enabled_metadata_required_and_subset_supported(app):
    with db.engine.begin() as connection:
        connection.execute(text('UPDATE zodiac_signs SET is_enabled=false'))
        with pytest.raises(Refused,match='metadata'):
            plan_import(connection.connection.driver_connection,load_dataset(DEFAULT_DATASET))
        connection.execute(text("UPDATE zodiac_signs SET is_enabled=true WHERE key='aries'"))
        pending,_,signs=plan_import(connection.connection.driver_connection,load_dataset(DEFAULT_DATASET))
        assert signs==1 and len(pending)==11
        connection.rollback()  # Reference metadata changes never escape this test.


def test_public_read_and_archive_preserve_demo_provenance(client,app):
    populate()
    r=client.get('/api/forecast?sign=aries&date=2026-11-15')
    assert r.status_code==200
    data=r.get_json()
    assert MARKER in data['text'] and data['text']==data['forecast']
    assert data['source']=='demo-fixture' and data['model_name'] is None
    assert data['generated_at'] is None and data['published_at'] is not None
    assert data['payload']['ai_generated'] is False
    missing=client.get('/api/forecast?sign=aries&date=2026-11-13')
    assert missing.status_code==404 and missing.get_json()['error']=='forecast_not_published'
    month=client.get('/api/archive/month?sign=aries&year=2026&month=11').get_json()
    days={d['date']:d['has_forecast'] for d in month['days']}
    assert days['2026-11-15'] is True and days['2026-11-13'] is False

"""Offline, INSERT-only demo fixtures. Never imports the Flask app or providers."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote, urlunsplit
from uuid import UUID

MARKER = 'Демонстраційний текст — не результат AI-генерації'
DEFAULT_DATASET = Path(__file__).parent / 'fixtures' / 'demo-2026-11-15-v1.json'
MULTILINGUAL_DATASET = DEFAULT_DATASET.with_name('demo-2026-11-22-v2.json')
DEMO_TITLES = {'en': 'Demo forecast', 'uk': 'Демонстраційний прогноз', 'ru': 'Демонстрационный прогноз'}


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


@dataclass(frozen=True)
class Target:
    dsn: str = field(repr=False)
    instance: UUID
    database: str = 'horoscope_demo'
    role: str = 'demo_importer'


def target_from_environment(env=None):
    env = os.environ if env is None else env
    require(not any(k == 'DATABASE_URL' or k.startswith(('POSTGRES', 'PG')) for k in env),
            'Conflicting database environment refused.')
    require(not any(k in env for k in ('OPENAI_API_KEY', 'ADMIN_API_TOKEN')),
            'Provider/admin credentials are not permitted in the importer.')
    require(env.get('PYTHON_DOTENV_DISABLED') == '1'
            and env.get('APP_DEPLOYMENT_MODE') == 'production'
            and env.get('GENERATION_PAID_EXECUTION_ENABLED') == '0',
            'Explicit isolated demo safety settings are required.')
    require(env.get('DEMO_EXPECTED_DATABASE') == 'horoscope_demo'
            and env.get('DEMO_EXPECTED_ROLE') == 'demo_importer', 'Unexpected demo target identity.')
    try:
        instance = UUID(env.get('DEMO_EXPECTED_INSTANCE_ID', ''))
        require(instance.int != 0, 'A nonzero staging UUID is required.')
        url = urlsplit(env.get('DEMO_FIXTURE_DATABASE_URL', ''))
        require(url.scheme in ('postgresql', 'postgresql+psycopg') and url.hostname == 'db'
                and url.port == 5432 and url.path == '/horoscope_demo'
                and unquote(url.username or '') == 'demo_importer'
                and len(unquote(url.password or '')) >= 24 and not url.query and not url.fragment,
                'The explicit isolated importer URL is invalid.')
    except (ValueError, TypeError, AttributeError):
        raise Refused('The explicit isolated importer identity is invalid.') from None
    return Target(urlunsplit(('postgresql', url.netloc, url.path, '', '')), instance)


def verify_identity(connection, target):
    require(connection.execute('SELECT current_database(), current_user, session_user, inet_server_port()').fetchone()
            == (target.database, target.role, target.role, 5432), 'Connected database/session identity mismatch.')
    flags = connection.execute('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls '
                               'FROM pg_roles WHERE rolname = current_user').fetchone()
    require(flags == (False, False, False, False, False), 'Elevated importer role refused.')
    require(connection.execute('SELECT 1 FROM pg_auth_members WHERE member = '
                               '(SELECT oid FROM pg_roles WHERE rolname = current_user) LIMIT 1').fetchone() is None,
            'Importer role memberships are forbidden.')
    owners = connection.execute("SELECT pg_get_userbyid(d.datdba), pg_get_userbyid(n.nspowner), "
                                "pg_get_userbyid(c.relowner) FROM pg_database d "
                                "JOIN pg_namespace n ON n.nspname = 'demo_control' "
                                "JOIN pg_class c ON c.relnamespace=n.oid AND c.relname='identity' "
                                "AND c.relkind='r' WHERE d.datname=current_database()").fetchall()
    require(owners == [('demo_owner', 'demo_owner', 'demo_owner')], 'Staging marker ownership mismatch.')
    rows = connection.execute('SELECT id, purpose, contract_version, instance_id, database_name, importer_role '
                              'FROM demo_control.identity LIMIT 2').fetchall()
    require(rows == [(1, 'horoscope-demo', 1, target.instance, target.database, target.role)],
            'Staging marker mismatch or missing.')
    privileges = connection.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE'), "
        "has_database_privilege(current_user,current_database(),'TEMP'), "
        "has_schema_privilege(current_user,'public','CREATE'), "
        "has_table_privilege(current_user,'demo_control.identity','INSERT,UPDATE,DELETE,TRUNCATE'), "
        "has_table_privilege(current_user,'public.forecasts','UPDATE,DELETE,TRUNCATE')").fetchone()
    require(privileges == (False, False, False, False, False), 'Excess importer privileges refused.')
    require(connection.execute("SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_' "
        "AND nspname <> 'information_schema' AND has_schema_privilege(current_user,oid,'CREATE') LIMIT 1").fetchone() is None,
        'Importer schema creation privileges refused.')
    require(connection.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname !~ '^pg_' "
        "AND n.nspname <> 'information_schema' AND NOT (n.nspname='public' AND c.relname='forecasts') "
        "AND has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE') LIMIT 1").fetchone() is None,
        'Importer has writes outside demo forecasts.')


def _validate_v1(data):
    require(data.get('locale') == 'ru' and data.get('forecast_type') == 'daily', 'Unsupported demo scope.')
    start, end = date.fromisoformat(data['window_start']), date.fromisoformat(data['window_end'])
    require(end-start == timedelta(days=6), 'The presentation window must contain seven days.')
    dates = [date.fromisoformat(d) for d in data['dates']]
    require(8 <= len(dates) <= 31 and len(set(dates)) == len(dates), 'Invalid or duplicate fixture dates.')
    require(set(start+timedelta(days=i) for i in range(-1,7)) <= set(dates), 'Presentation days are missing.')
    missing = date.fromisoformat(data['missing_date'])
    require(missing not in dates, 'The deliberate unpublished date must remain absent.')
    texts = data['texts']
    require(isinstance(texts, dict) and 1 <= len(texts) <= 64, 'Invalid sign content map.')
    for sign, text in texts.items():
        require(re.fullmatch(r'[a-z]+', sign) is not None and isinstance(text, str)
                and MARKER in text and 80 <= len(text) <= 12000, 'Invalid or unmarked demo text.')
    data['parsed_dates'] = sorted(dates)


def _distinct_json_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON field in dataset.')
        result[key] = value
    return result


def _iso_date(value):
    require(isinstance(value, str), 'Invalid fixture date.')
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise Refused('Invalid fixture date.') from None
    require(day.isoformat() == value, 'Fixture dates must use YYYY-MM-DD.')
    return day


def _validate_v2(data):
    require(set(data) == {'format', 'id', 'forecast_type', 'window_start', 'window_end',
                          'missing_date', 'dates', 'sign_keys', 'records'},
            'Unexpected multilingual dataset fields.')
    require(data['forecast_type'] == 'daily', 'Unsupported demo scope.')
    start, end = _iso_date(data['window_start']), _iso_date(data['window_end'])
    days = (end - start).days + 1
    require(1 <= days <= 31, 'Invalid multilingual presentation window.')
    require(data['id'].startswith(f'demo-{start.isoformat()}-v') and not data['id'].endswith('-v1'),
            'Dataset version must identify the multilingual window.')
    dates = [start + timedelta(days=i) for i in range(days)]
    require(isinstance(data['dates'], list) and sorted(_iso_date(d) for d in data['dates']) == dates,
            'Missing, duplicate or out-of-window fixture dates.')
    require(_iso_date(data['missing_date']) not in dates, 'The deliberate unpublished date must remain absent.')
    signs = data['sign_keys']
    require(isinstance(signs, list) and 1 <= len(signs) <= 64
            and all(isinstance(k, str) and re.fullmatch('[a-z]{1,32}', k) for k in signs)
            and len(set(signs)) == len(signs), 'Invalid or duplicate fixture sign keys.')
    require(isinstance(data['records'], list) and len(data['records']) == len(signs) * days,
            'Missing or extra multilingual forecast records.')

    index = {}
    seen_bodies = set()
    for record in data['records']:
        require(isinstance(record, dict) and set(record) == {'sign_key', 'target_date', 'texts', 'source_text_sha256'},
                'Invalid multilingual forecast fields.')
        sign, day = record['sign_key'], _iso_date(record['target_date'])
        require(sign in signs and day in dates and (sign, day) not in index,
                'Unknown or duplicate multilingual forecast key.')
        texts = record['texts']
        require(isinstance(texts, dict) and texts.keys() == DEMO_TITLES.keys(),
                'Each forecast must contain exactly en, uk and ru.')
        for locale, title in DEMO_TITLES.items():
            text = texts[locale]
            prefix = title + '.\n\n'
            require(isinstance(text, str) and text.startswith(prefix) and len(text) <= 12000,
                    'Invalid text or localized demo marker.')
            body = text[len(prefix):]
            body_key = (sign, locale, body)
            require(body and body == body.strip() and body_key not in seen_bodies
                    and not re.search(r'[\x00-\x08\x0b-\x1f\x7f\ud800-\udfff]', text),
                    'Invalid or reused multilingual forecast body.')
            seen_bodies.add(body_key)
        require(record['source_text_sha256'] == hashlib.sha256(texts['en'].encode('utf-8')).hexdigest(),
                'English source text digest mismatch.')
        index[sign, day] = record
    data['parsed_dates'] = dates
    data['record_index'] = index


def load_dataset(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 200_000, 'Dataset is too large.')
    data = json.loads(raw, object_pairs_hook=_distinct_json_keys)
    require(isinstance(data, dict) and type(data.get('format')) is int and data['format'] in (1, 2),
            'Unsupported demo dataset format.')
    require(isinstance(data.get('id'), str) and re.fullmatch(r'demo-\d{4}-\d{2}-\d{2}-v[1-9]\d*', data['id']),
            'Invalid dataset version.')
    if data['format'] == 1:
        _validate_v1(data)
    else:
        _validate_v2(data)
    data['digest'] = hashlib.sha256(raw).hexdigest()
    return data


def fixture_values(dataset, sign, day, locale='ru'):
    payload = {'demo_dataset': dataset['id'], 'dataset_sha256': dataset['digest'],
               'provenance': 'static-demo-fixture', 'ai_generated': False}
    if dataset['format'] == 1:
        require(locale == 'ru', 'Unsupported legacy demo locale.')
        title, text = 'Демонстраційний прогноз', dataset['texts'][sign]
    else:
        record = dataset['record_index'][sign, day]
        title, text = DEMO_TITLES[locale], record['texts'][locale]
        payload.update(
            source_key={'sign_key': sign, 'target_date': day.isoformat(), 'forecast_type': 'daily', 'locale': 'en'},
            source_version=dataset['id'],
            source_text_sha256=record['source_text_sha256'],
            content_role='original' if locale == 'en' else 'translation',
        )
    return (sign, day, locale, 'daily', title, text,
            payload, 'published', 'demo-fixture', None, None, None, None)


def plan_import(connection, dataset):
    signs = [r[0] for r in connection.execute(
        'SELECT key FROM public.zodiac_signs WHERE is_enabled ORDER BY sort_order LIMIT 65').fetchall()]
    multilingual = dataset['format'] == 2
    covered_signs = dataset['sign_keys'] if multilingual else dataset['texts']
    require(0 < len(signs) <= 64 and set(signs) <= set(covered_signs),
            'Enabled-sign metadata is empty or not covered by this dataset.')
    locales = list(DEMO_TITLES) if multilingual else ['ru']
    missing = date.fromisoformat(dataset['missing_date'])
    check_dates = dataset['parsed_dates'] + ([missing] if multilingual else [])
    rows = connection.execute('SELECT sign_key,target_date,locale,forecast_type,title,text,payload,status,source,'
        'model_name,prompt_version_id,generation_item_id,generated_at,published_at FROM public.forecasts '
        'WHERE sign_key = ANY(%s) AND target_date = ANY(%s) AND locale = ANY(%s) AND forecast_type=%s',
        (signs, check_dates, locales, 'daily')).fetchall()
    require(not any(row[1] == missing and row[7] == 'published' for row in rows),
            'A forecast is already published on the deliberate missing date.')
    existing = {row[:4]: row for row in rows}
    pending, unchanged = [], 0
    for sign in signs:
        for day in dataset['parsed_dates']:
            for locale in locales:
                values = fixture_values(dataset, sign, day, locale)
                previous = existing.get(values[:4])
                if previous is not None:
                    require(tuple(previous[:13]) == values and previous[13] is not None,
                            'Conflicting forecast exists; no rows were overwritten.')
                    unchanged += 1
                else:
                    pending.append(values)
    return pending, unchanged, len(signs)


def _insert_rows(connection, target, pending):
    verify_identity(connection, target)
    from psycopg.types.json import Jsonb
    for row in pending:
        values = (*row[:6], Jsonb(row[6]), *row[7:])
        connection.execute('INSERT INTO public.forecasts '
            '(sign_key,target_date,locale,forecast_type,title,text,payload,status,source,model_name,'
            'prompt_version_id,generation_item_id,generated_at,published_at) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)', values)


def import_fixtures(connection, target, dataset, *, apply=False):
    # Each call owns this dedicated offline connection. Validation is repeated in
    # the write transaction, before its first mutation. No app/ORM session exists.
    with connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        verify_identity(connection, target)
        pending, unchanged, signs = plan_import(connection, dataset)
    if apply:
        with connection.transaction():
            verify_identity(connection, target)
            pending, unchanged, signs = plan_import(connection, dataset)
            _insert_rows(connection, target, pending)
    return {'dataset': dataset['id'], 'mode': 'apply' if apply else 'dry-run',
            'enabled_signs': signs, 'dates': len(dataset['parsed_dates']),
            'inserted' if apply else 'would_insert': len(pending), 'unchanged': unchanged,
            'window_start': dataset['window_start'], 'window_end': dataset['window_end'],
            'missing_date': dataset['missing_date']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--apply', action='store_true', help='Explicitly insert into the validated isolated demo database')
    args = parser.parse_args(argv)
    try:
        target = target_from_environment()
        dataset = load_dataset(args.dataset)
        import psycopg
        with psycopg.connect(target.dsn, autocommit=True, connect_timeout=5,
                             options='-c statement_timeout=10000 -c lock_timeout=3000') as connection:
            result = import_fixtures(connection, target, dataset, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Refused as exc:
        print(str(exc))
    except Exception:
        print('Demo import failed; database and credential details suppressed. Verify state with a dry-run before retrying.')
    return 1

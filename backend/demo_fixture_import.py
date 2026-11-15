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
        "has_table_privilege(current_user,'forecasts','UPDATE,DELETE,TRUNCATE')").fetchone()
    require(privileges == (False, False, False, False, False), 'Excess importer privileges refused.')


def load_dataset(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 200_000, 'Dataset is too large.')
    data = json.loads(raw)
    require(isinstance(data, dict) and data.get('format') == 1, 'Unsupported demo dataset format.')
    require(re.fullmatch(r'demo-\d{4}-\d{2}-\d{2}-v[1-9]\d*', data.get('id', '')) is not None,
            'Invalid dataset version.')
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
    data['digest'] = hashlib.sha256(raw).hexdigest()
    return data


def fixture_values(dataset, sign, day):
    payload = {'demo_dataset': dataset['id'], 'dataset_sha256': dataset['digest'],
               'provenance': 'static-demo-fixture', 'ai_generated': False}
    return (sign, day, 'ru', 'daily', 'Демонстраційний прогноз', dataset['texts'][sign],
            payload, 'published', 'demo-fixture', None, None, None, None)


def plan_import(connection, dataset):
    signs = [r[0] for r in connection.execute(
        'SELECT key FROM zodiac_signs WHERE is_enabled ORDER BY sort_order LIMIT 65').fetchall()]
    require(0 < len(signs) <= 64 and set(signs) <= set(dataset['texts']),
            'Enabled-sign metadata is empty or not covered by this dataset.')
    rows = connection.execute('SELECT sign_key,target_date,locale,forecast_type,title,text,payload,status,source,'
        'model_name,prompt_version_id,generation_item_id,generated_at,published_at FROM forecasts '
        'WHERE sign_key = ANY(%s) AND target_date = ANY(%s) AND locale=%s AND forecast_type=%s',
        (signs, dataset['parsed_dates'], 'ru', 'daily')).fetchall()
    existing = {(r[0], r[1]): r for r in rows}
    pending, unchanged = [], 0
    for sign in signs:
        for day in dataset['parsed_dates']:
            values = fixture_values(dataset, sign, day)
            previous = existing.get((sign, day))
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
        connection.execute('INSERT INTO forecasts '
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

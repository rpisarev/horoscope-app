"""Mock-only importer refusal tests: no Flask, network, DB or credentials."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('demo_fixture_import', ROOT/'demo_fixture_import.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
INSTANCE = UUID('10000000-0000-0000-0000-000000000001')


def env():
    return {'DEMO_FIXTURE_DATABASE_URL':'postgresql+psycopg://demo_importer:dummy-password-not-real-123@db:5432/horoscope_demo',
            'DEMO_EXPECTED_INSTANCE_ID':str(INSTANCE), 'DEMO_EXPECTED_DATABASE':'horoscope_demo',
            'DEMO_EXPECTED_ROLE':'demo_importer', 'PYTHON_DOTENV_DISABLED':'1',
            'APP_DEPLOYMENT_MODE':'production','GENERATION_PAID_EXECUTION_ENABLED':'0'}


def good_connection():
    c = MagicMock()
    c.execute.side_effect = [
        MagicMock(fetchone=lambda:('horoscope_demo','demo_importer','demo_importer',5432)),
        MagicMock(fetchone=lambda:(False,)*5), MagicMock(fetchone=lambda:None),
        MagicMock(fetchall=lambda:[('demo_owner',)*3]),
        MagicMock(fetchall=lambda:[(1,'horoscope-demo',1,INSTANCE,'horoscope_demo','demo_importer')]),
        MagicMock(fetchone=lambda:(False,)*5),
        MagicMock(fetchone=lambda:None), MagicMock(fetchone=lambda:None),
    ]
    return c


class TargetTests(unittest.TestCase):
    def test_positive_explicit_target(self):
        target=m.target_from_environment(env())
        self.assertEqual(target.instance,INSTANCE)
        self.assertTrue(target.dsn.startswith('postgresql://'))

    def test_conflicting_environment(self):
        for name in ['DATABASE_URL','POSTGRES_DB','POSTGRES_PASSWORD_FILE','PGOPTIONS','PGHOST','OPENAI_API_KEY','ADMIN_API_TOKEN']:
            with self.subTest(name=name),self.assertRaises(m.Refused):
                m.target_from_environment({**env(),name:''})

    def test_wrong_targets_and_url_overrides(self):
        for url in ['postgresql://demo_importer:dummy-password-not-real-123@db:5432/horoscope',
                    'postgresql://demo_importer:dummy-password-not-real-123@localhost:5432/horoscope_demo',
                    'postgresql://demo_owner:dummy-password-not-real-123@db:5432/horoscope_demo',
                    env()['DEMO_FIXTURE_DATABASE_URL']+'?host=other', 'sqlite:///demo.db']:
            with self.subTest(url='redacted'),self.assertRaises(m.Refused):
                m.target_from_environment({**env(),'DEMO_FIXTURE_DATABASE_URL':url})

    def test_missing_identity_and_safety(self):
        for key in env():
            e=env();del e[key]
            with self.subTest(key=key),self.assertRaises(m.Refused):m.target_from_environment(e)
        for key,value in [('APP_DEPLOYMENT_MODE','development'),('GENERATION_PAID_EXECUTION_ENABLED','1'),
                          ('DEMO_EXPECTED_INSTANCE_ID','00000000-0000-0000-0000-000000000000')]:
            with self.assertRaises(m.Refused):m.target_from_environment({**env(),key:value})

    def test_exact_connected_identity(self):
        c=good_connection();m.verify_identity(c,m.target_from_environment(env()))
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in c.execute.call_args_list))

    def test_mismatched_connected_evidence(self):
        replacements=[MagicMock(fetchone=lambda:('horoscope','demo_importer','demo_importer',5432)),
                      MagicMock(fetchone=lambda:(True,False,False,False,False)),MagicMock(fetchone=lambda:(1,)),
                      MagicMock(fetchall=lambda:[('other',)*3]),MagicMock(fetchall=lambda:[]),
                      MagicMock(fetchone=lambda:(False,False,False,False,True)),
                      MagicMock(fetchone=lambda:(1,)), MagicMock(fetchone=lambda:(1,))]
        for index,replacement in enumerate(replacements):
            c=good_connection();results=list(c.execute.side_effect);results[index]=replacement;c.execute.side_effect=results
            with self.subTest(index=index),self.assertRaises(m.Refused):m.verify_identity(c,m.target_from_environment(env()))

    def test_failed_preflight_never_writes(self):
        c=MagicMock()
        with patch.object(m,'verify_identity',side_effect=m.Refused('refused')),patch.object(m,'plan_import') as plan:
            with self.assertRaises(m.Refused):m.import_fixtures(c,m.target_from_environment(env()),{},apply=True)
            plan.assert_not_called()
        self.assertEqual([x.args[0] for x in c.execute.call_args_list],['SET TRANSACTION READ ONLY'])

    def test_dry_run_never_calls_writer(self):
        c=MagicMock();dataset=m.load_dataset(m.DEFAULT_DATASET)
        with patch.object(m,'verify_identity'),patch.object(m,'plan_import',return_value=([1],0,13)),patch.object(m,'_insert_rows') as writer:
            result=m.import_fixtures(c,m.target_from_environment(env()),dataset)
            self.assertEqual(result['would_insert'],1);writer.assert_not_called()
        self.assertEqual(c.transaction.call_count,1)

    def test_writer_revalidates_before_insert(self):
        c=MagicMock()
        with patch.object(m,'verify_identity',side_effect=m.Refused('wrong-target')):
            with self.assertRaises(m.Refused):m._insert_rows(c,m.target_from_environment(env()),[])
        c.execute.assert_not_called()

    def test_dataset_is_explicit_static_and_marked(self):
        d=m.load_dataset(m.DEFAULT_DATASET)
        self.assertEqual(len(d['parsed_dates']),11)
        self.assertNotIn(d['missing_date'],[x.isoformat() for x in d['parsed_dates']])
        self.assertTrue(all(m.MARKER in text for text in d['texts'].values()))


if __name__=='__main__':unittest.main()

"""Validate the packaged fixture and reject malformed inputs offline."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_fixture_import as importer


class MultilingualDatasetTests(unittest.TestCase):
    def test_published_fixture_contract(self):
        data = importer.load_dataset(importer.MULTILINGUAL_DATASET)
        self.assertEqual(data['id'], 'demo-2026-11-22-v2')
        self.assertEqual(data['dates'], ['2026-11-22', '2026-11-23', '2026-11-24'])
        self.assertEqual(data['missing_date'], '2026-11-25')
        historical = importer.load_dataset(importer.DEFAULT_DATASET)
        self.assertEqual(set(data['sign_keys']), set(historical['texts']))
        self.assertTrue(set(data['parsed_dates']).isdisjoint(historical['parsed_dates']))
        self.assertEqual(len(data['record_index']), len(data['sign_keys']) * 3)
        for (sign, day), record in data['record_index'].items():
            english = record['texts']['en']
            digest = hashlib.sha256(english.encode('utf-8')).hexdigest()
            for locale, text in record['texts'].items():
                row = importer.fixture_values(data, sign, day, locale)
                self.assertEqual(row[:4], (sign, day, locale, 'daily'))
                self.assertEqual(row[5], text)
                self.assertEqual(row[6]['source_text_sha256'], digest)
                self.assertEqual(row[6]['source_key'], {
                    'sign_key': sign, 'target_date': day.isoformat(), 'locale': 'en', 'forecast_type': 'daily',
                })
                self.assertEqual(row[6]['source_version'], data['id'])
                self.assertEqual(row[6]['content_role'], 'original' if locale == 'en' else 'translation')

    def test_malformed_datasets_refused_before_connecting(self):
        mutations = {
            'missing sign/date record': lambda d, r: d['records'].pop(),
            'duplicate sign/date record': lambda d, r: d['records'].__setitem__(1, r),
            'absent source': lambda d, r: r['texts'].pop('en'),
            'absent translation': lambda d, r: r['texts'].pop('ru'),
            'extra locale': lambda d, r: r['texts'].update(de='unexpected'),
            'wrong localized marker': lambda d, r: r['texts'].update(uk=r['texts']['ru']),
            'reused translation on another date': lambda d, r: d['records'][len(d['sign_keys'])]['texts'].update(
                uk=r['texts']['uk']),
            'changed original': lambda d, r: r['texts'].update(en=r['texts']['en'] + ' A later edit.'),
            'wrong source digest': lambda d, r: r.update(source_text_sha256='0' * 64),
            'missing source digest': lambda d, r: r.pop('source_text_sha256'),
            'foreign source fields': lambda d, r: r.update(source_key={'locale': 'ru'}),
            'missing top-level field': lambda d, r: d.pop('missing_date'),
            'wrong version': lambda d, r: d.update(id='demo-2026-11-22-v1'),
            'out-of-window date': lambda d, r: r.update(target_date=d['missing_date']),
            'duplicate date': lambda d, r: d['dates'].append(d['dates'][0]),
            'unpublished date overlaps': lambda d, r: d.update(missing_date=d['dates'][0]),
            'unknown sign': lambda d, r: r.update(sign_key='unlisted'),
            'duplicate declared sign': lambda d, r: d['sign_keys'].append(r['sign_key']),
            'unexpected scope': lambda d, r: d.update(forecast_type='weekly'),
            'empty body': lambda d, r: r['texts'].update(en='Demo forecast.\n\n'),
        }
        fixture = importer.MULTILINGUAL_DATASET.read_text(encoding='utf-8')
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'malformed.json'
            for description, mutate in mutations.items():
                with self.subTest(description=description):
                    data = json.loads(fixture)
                    mutate(data, data['records'][0])
                    path.write_text(json.dumps(data), encoding='utf-8')
                    with self.assertRaises(importer.Refused):
                        importer.load_dataset(path)
            # A JSON object with the same translation key twice would otherwise
            # be silently reduced to its last value by the standard decoder.
            path.write_text(fixture.replace('"uk":', '"uk": "discarded", "uk":', 1), encoding='utf-8')
            with self.assertRaisesRegex(importer.Refused, 'Duplicate JSON field'):
                importer.load_dataset(path)
            driver = Mock()
            with patch.object(importer, 'target_from_environment'), patch.dict(sys.modules, psycopg=driver):
                with patch('builtins.print'):
                    self.assertEqual(importer.main(['--dataset', str(path), '--apply']), 1)
                driver.connect.assert_not_called()

    def test_body_uniqueness_is_scoped_to_sign_and_locale(self):
        data = json.loads(importer.MULTILINGUAL_DATASET.read_bytes())
        aries, taurus = data['records'][:2]
        taurus['texts']['uk'] = aries['texts']['uk']
        aries['texts']['ru'] = aries['texts']['uk'].replace('Демонстраційний прогноз.', 'Демонстрационный прогноз.')
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'shared-wording.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            importer.load_dataset(path)

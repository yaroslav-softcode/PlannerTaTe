"""Desktop About API integration, isolated from the user's data directory."""
import os
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = tempfile.TemporaryDirectory(prefix='plannertate_about_', dir=os.environ.get('TMPDIR'))
os.environ['PLANNERTATE_DATA'] = DATA.name
os.environ['PLANNERTATE_PORT'] = '5098'
import backend


class DesktopAboutTests(unittest.TestCase):
    def setUp(self):
        self.client = backend.app.test_client()

    def test_about_reports_version_of_the_installer(self):
        response = self.client.get('/api/about')
        self.assertEqual(response.status_code, 200)
        about = response.get_json()
        version = re.search(r'#define AppVersion "([^"]+)"', (ROOT / 'PlannerTaTe.iss').read_text(encoding='utf-8')).group(1)
        self.assertEqual(about['current_version'], version)
        self.assertEqual(about['name'], 'PlannerTaTe')
        self.assertFalse(about['can_install'], 'the source version must not overwrite python.exe')
        resource = (ROOT / 'PlannerTaTe_version.txt').read_text(encoding='utf-8')
        self.assertIn("'FileVersion', '" + version + ".0.0'", resource)
        installer = (ROOT / 'PlannerTaTe.iss').read_text(encoding='utf-8')
        self.assertIn('VersionInfoVersion=' + version + '.0.0', installer)
        self.assertFalse((pathlib.Path(DATA.name) / 'graph.json').exists())

    def test_about_reports_last_install_receipt_when_present(self):
        updates = pathlib.Path(DATA.name) / 'updates'
        updates.mkdir(parents=True, exist_ok=True)
        (updates / 'last-result.json').write_text(
            '{"state":"success","error":null,"version":"1.13","installer_exit_code":0,'
            '"restarted":true,"timestamp":"2026-11-24T00:00:00Z"}', encoding='utf-8-sig')
        about = self.client.get('/api/about').get_json()
        self.assertEqual(about['last_install']['state'], 'success')
        self.assertEqual(about['last_install']['version'], '1.13')
        self.assertTrue(about['last_install']['restarted'])

    def test_about_ignores_corrupted_last_install_receipt(self):
        updates = pathlib.Path(DATA.name) / 'updates'
        updates.mkdir(parents=True, exist_ok=True)
        (updates / 'last-result.json').write_text('not json', encoding='utf-8')
        self.assertIsNone(self.client.get('/api/about').get_json()['last_install'])

    def test_updates_dir_pruning_keeps_newest_installer_and_recent_logs(self):
        import time as _time
        from plannertate_updates import _prune_updates_dir
        folder = pathlib.Path(DATA.name) / 'updates_prune'
        folder.mkdir(exist_ok=True)
        old = folder / 'PlannerTaTe_Setup_1.10.exe'
        new = folder / 'PlannerTaTe_Setup_1.12.exe'
        old.write_bytes(b'MZ' + b'0' * 10)
        new.write_bytes(b'MZ' + b'1' * 10)
        _time.sleep(0.05)
        new.touch()
        stale_part = folder / 'PlannerTaTe_Setup_1.13.exe.abc.part'
        stale_part.write_bytes(b'x')
        old_ts = _time.time() - 30 * 86400
        for path in (stale_part, folder / 'update-old.ps1'):
            path.write_bytes(b'x')
            os.utime(path, (old_ts, old_ts))
        for index in range(25):
            log = folder / f'update-{index:02d}.helper.log'
            log.write_text('x', encoding='utf-8')
            os.utime(log, (_time.time() - index, _time.time() - index))
        _prune_updates_dir(folder)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertFalse(stale_part.exists())
        self.assertFalse((folder / 'update-old.ps1').exists())
        self.assertEqual(len(list(folder.glob('*.helper.log'))), 20)

    def test_updates_cannot_be_started_by_a_cross_origin_website(self):
        response = self.client.post('/api/updates/check', headers={
            'Origin': 'https://attacker.invalid', 'X-Plannertate-Client': '1'})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/updates/check')
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()

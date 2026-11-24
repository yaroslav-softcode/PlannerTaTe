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

    def test_updates_cannot_be_started_by_a_cross_origin_website(self):
        response = self.client.post('/api/updates/check', headers={
            'Origin': 'https://attacker.invalid', 'X-Plannertate-Client': '1'})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/updates/check')
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()

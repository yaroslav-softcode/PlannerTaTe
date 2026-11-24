"""Deterministic screenshot catalog tests; no network or user data access."""
from __future__ import annotations

import base64
import importlib
import io
import json
import os
from pathlib import Path
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request

from flask import Flask

SCRATCH = Path(os.environ.get('TMPDIR', 'C:/Users/Yar/AppData/Local/hermes/cache/scratch'))
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAFElEQVR4nGM0TpvJwMDAxAAGUAoAFqQBOCr5XboAAAAASUVORK5CYII=')
WEBP = base64.b64decode('UklGRjgAAABXRUJQVlA4ICwAAADwAQCdASoCAAMAAUAmJaACdLoB+AAETAAA/u+9V/43bjDfgu/33oDeBgAAAA==')
JPEG = base64.b64decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAADAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDnKKKK948Q/9k=')


class HTTPFixture(io.BytesIO):
    def __init__(self, body, url, content_type='image/png', length=None):
        super().__init__(body)
        self.url = url
        self.headers = {'Content-Type': content_type}
        if length is not None:
            self.headers['Content-Length'] = str(length)
        self.status = 200

    def geturl(self):
        return self.url


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='catalog-test-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network_guard = patch('socket.create_connection', side_effect=AssertionError('Offline test attempted network'))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def module(self):
        try:
            return importlib.import_module('app_catalog')
        except ModuleNotFoundError as error:
            if error.name != 'app_catalog':
                raise
            self.fail('Missing app_catalog: implement the README screenshot parser')

    def test_rate_limited_readme_uses_public_raw_default_head(self):
        module = self.module()
        from urllib.error import HTTPError
        api = 'https://api.github.com/repos/yaroslav-softcode/FAIR/readme'
        raw = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/HEAD/README.md'
        with patch.object(module, '_fetch_bytes', side_effect=[
                HTTPError(api, 403, 'rate limited', {}, None),
                (b'![Screenshot](screenshots/fair_ru.webp)', 'text/plain')]) as fetch:
            markdown, base = module.fetch_readme('FAIR')
        self.assertEqual(base, raw)
        self.assertEqual(fetch.call_args.args[0], raw)
        self.assertEqual(module.screenshot_candidates(markdown, base, 'FAIR')[0],
                         'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/HEAD/screenshots/fair_ru.webp')
        self.assertFalse(fetch.call_args.args[1]('https://evil.invalid/README.md'))

    def test_readme_relative_images_use_actual_readme_download_url(self):
        module = self.module()
        base = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/feature/new-ui/docs/README.md'
        markdown = '![Screenshot RU](../screenshots/fair-ru.png)\n![Screenshot EN](../screenshots/fair-en.webp)'
        self.assertEqual(module.screenshot_candidates(markdown, base, 'FAIR', 'ru')[0],
                         'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/feature/new-ui/screenshots/fair-ru.png')
        self.assertEqual(module.screenshot_candidates(markdown, base, 'FAIR', 'en')[0],
                         'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/feature/new-ui/screenshots/fair-en.webp')
    def test_parser_supports_html_reference_images_and_skips_non_screenshots(self):
        module = self.module()
        base = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/release-2026/README.md'
        readme = '''
![badge](https://img.shields.io/badge/FAIR-free-blue)
![Author portrait](assets/author.png)
![FAIR icon](assets/icon.png)
![Open Graph card](assets/og-image.jpg)
![Logo](assets/logo.png)
![generic](assets/cover.png)
![FAIR screenshot EN](shots/fair_en.png)
<img src="shots/fair_ru.webp" alt="Окно FAIR — русский интерфейс" width="1400">
![Screenshot RU][ru-shot]
[ru-shot]: <shots/extra-ru.jpg> "Russian window"
![Screenshot external](https://tracker.example/screen.png)
<!-- ![Screenshot hidden](shots/hidden.png) -->
```
![Screenshot example](shots/example.png)
```
'''
        candidates = module.screenshot_candidates(readme, base, 'FAIR', 'ru')
        self.assertEqual(candidates[0], base.rsplit('/', 1)[0] + '/shots/fair_ru.webp')
        self.assertIn(base.rsplit('/', 1)[0] + '/shots/extra-ru.jpg', candidates)
        self.assertNotIn(base.rsplit('/', 1)[0] + '/assets/cover.png', candidates[:2])
        self.assertFalse(any(word in url for url in candidates for word in
                             ('author', 'icon', 'og-image', 'logo', 'hidden', 'example', 'tracker', 'shields')))
        self.assertEqual(len(candidates), len(set(candidates)))

    def test_url_policy_scopes_raw_paths_and_allows_only_attachment_entrypoint(self):
        module = self.module()
        raw = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/main/screenshots/fair.png'
        attachment = 'https://github.com/user-attachments/assets/0b876119-a721-408d-aa11-9bde532e419c'
        self.assertTrue(module.is_allowed_image_url(raw, 'FAIR'))
        self.assertTrue(module.is_allowed_image_url(attachment, 'FAIR'))
        for url in (
            raw.replace('https:', 'http:'), raw.replace('/FAIR/', '/paste-pen/'),
            raw.replace('yaroslav-softcode', 'other-owner'), raw.replace('.com/', '.com.evil/'),
            raw.replace('https://', 'https://user:pass@'), raw.replace('.com/', '.com:444/'),
            raw.replace('screenshots/fair.png', '../paste-pen/private.png'),
            raw.replace('screenshots/fair.png', '%2e%2e/paste-pen/private.png'),
            raw.replace('screenshots/fair.png', '%252e%252e/private.png'),
            raw + '?token=private', raw + '#fragment',
            'file:///C:/private.png', 'https://127.0.0.1/private.png',
            'https://avatars.githubusercontent.com/u/1',
            'https://github.com/user-attachments/assets/not-an-id',
            'https://github.com/yaroslav-softcode/FAIR/blob/main/screen.png',
            'https://user-images.githubusercontent.com/1/screenshot.png',
        ):
            with self.subTest(url=url):
                self.assertFalse(module.is_allowed_image_url(url, 'FAIR'))
        self.assertEqual(module.screenshot_candidates('![Only image](screenshot.png)',
                         base := raw.rsplit('/screenshots/', 1)[0] + '/README.md', 'FAIR', 'en'),
                         [base.rsplit('/', 1)[0] + '/screenshot.png'])

    def test_download_image_accepts_real_png_jpeg_webp_not_html_svg_or_truncation(self):
        module = self.module()
        url = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/main/shot.png'
        for body, mime in ((PNG, 'image/png'), (JPEG, 'image/jpeg'), (WEBP, 'image/webp')):
            with self.subTest(mime=mime), patch.object(module, '_open_url', return_value=HTTPFixture(body, url, mime)):
                self.assertEqual(module.fetch_image(url, 'FAIR'), (body, mime))
                self.assertEqual(module.image_mime(body), mime)
        for body, mime in ((b'<html>403</html>', 'image/png'), (b'<svg/>', 'image/svg+xml'),
                           (PNG, 'text/html'), (PNG[:30], 'image/png'),
                           (WEBP[:25], 'image/webp'), (JPEG[:-2], 'image/jpeg')):
            with self.subTest(body=body[:15], mime=mime), patch.object(module, '_open_url', return_value=HTTPFixture(body, url, mime)):
                with self.assertRaises(ValueError):
                    module.fetch_image(url, 'FAIR')

    def test_download_size_cap_applies_to_header_and_stream(self):
        module = self.module()
        url = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/main/shot.png'
        for body, length in ((PNG, module.MAX_IMAGE_BYTES + 1),
                              (b'x' * (module.MAX_IMAGE_BYTES + 1), None)):
            with self.subTest(length=length), patch.object(module, '_open_url', return_value=HTTPFixture(body, url, length=length)):
                with self.assertRaises(ValueError):
                    module.fetch_image(url, 'FAIR')

    def test_redirects_are_checked_before_following_and_at_final_response(self):
        module = self.module()
        raw = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/main/shot.png'
        attachment = 'https://github.com/user-attachments/assets/0b876119-a721-408d-aa11-9bde532e419c'
        cdn = 'https://private-user-images.githubusercontent.com/123/shot.png?jwt=public-signed-token'
        policy = module._SafeRedirect('FAIR', attachment)
        self.assertIsInstance(policy.redirect_request(Request(attachment), None, 302, 'Found', {}, cdn), Request)
        for target in ('http://user-images.githubusercontent.com/1/shot.png',
                       'https://evil.example/shot.png', 'https://127.0.0.1/shot.png',
                       'https://avatars.githubusercontent.com/u/1'):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    policy.redirect_request(Request(attachment), None, 302, 'Found', {}, target)
        with self.assertRaises(ValueError):
            module._SafeRedirect('FAIR', raw).redirect_request(Request(raw), None, 302, 'Found', {}, cdn)
        with patch.object(module, '_open_url', return_value=HTTPFixture(PNG, 'https://evil.example/tracker.png')):
            with self.assertRaises(ValueError):
                module.fetch_image(raw, 'FAIR')
        with patch.object(module, '_open_url', return_value=HTTPFixture(PNG, cdn)):
            self.assertEqual(module.fetch_image(attachment, 'FAIR')[0], PNG)

    def test_fetch_readme_uses_public_api_download_url_and_verified_tls(self):
        module = self.module()
        url = 'https://api.github.com/repos/yaroslav-softcode/FAIR/readme'
        download_url = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/other-branch/docs/README.md'
        payload = json.dumps({'encoding': 'base64', 'content': base64.b64encode(b'![Screenshot](shot.png)').decode(),
                              'download_url': download_url}).encode()
        with patch.object(module, '_open_url', return_value=HTTPFixture(payload, url, 'application/json')) as open_url:
            self.assertEqual(module.fetch_readme('FAIR'), ('![Screenshot](shot.png)', download_url))
            self.assertEqual(open_url.call_args.args[0].full_url, url)
        with patch.object(module, 'build_opener') as build:
            module._open_url(Request(download_url), lambda u: True)
            handlers = build.call_args.args
            https = next(h for h in handlers if isinstance(h, module.HTTPSHandler))
            self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(https._context.check_hostname)
            self.assertGreater(build.return_value.open.call_args.kwargs['timeout'], 0)
            self.assertLessEqual(build.return_value.open.call_args.kwargs['timeout'], 20)

    def test_route_serves_bundled_fallback_without_network_or_download_route(self):
        module = self.module()
        bundled = self.root / 'resources' / 'frontend' / 'dist' / 'author-apps'
        bundled.mkdir(parents=True)
        for app_id in ('fair', 'pastepen'):
            for lang in ('ru', 'en'):
                (bundled / f'{app_id}-{lang}.webp').write_bytes(WEBP)
        app = Flask(__name__)
        manager = module.register_catalog(app, self.root / 'data', self.root / 'resources')
        self.assertIs(app.extensions['app_catalog'], manager)
        self.assertIs(module.register_catalog(app, self.root / 'data', self.root / 'resources'), manager)
        self.assertFalse((self.root / 'data').exists())
        self.assertEqual([str(rule) for rule in app.url_map.iter_rules()
                          if str(rule).startswith('/api/')], ['/api/apps/<app_id>/screenshot'])
        with patch.object(manager, 'refresh', return_value=False) as refresh, patch.object(module, 'fetch_readme', side_effect=AssertionError('Route must not fetch synchronously')):
            client = app.test_client()
            for app_id in ('fair', 'pastepen'):
                for lang in ('ru', 'en'):
                    response = client.get(f'/api/apps/{app_id}/screenshot?lang={lang}')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/webp')
                    self.assertEqual(response.data, WEBP)
                    self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                    self.assertNotIn('Location', response.headers)
                    self.assertIn('no-cache', response.headers['Cache-Control'])
            self.assertEqual(refresh.call_count, 4)
            self.assertEqual(client.get('/api/apps/other/screenshot').status_code, 404)
            self.assertEqual(client.get('/api/apps/fair/screenshot?lang=../../secret').status_code, 400)

    def test_route_prefers_valid_cache_and_ignores_corrupted_cache(self):
        module = self.module()
        bundled = self.root / 'frontend' / 'dist' / 'author-apps'
        bundled.mkdir(parents=True)
        (bundled / 'fair-ru.webp').write_bytes(WEBP)
        app = Flask(__name__)
        manager = module.register_catalog(app, self.root / 'data', self.root)
        manager.cache_dir.mkdir(parents=True)
        cache = manager.cache_dir / 'fair-ru.image'
        cache.write_bytes(PNG)
        with patch.object(manager, 'refresh', return_value=False):
            response = app.test_client().get('/api/apps/fair/screenshot?lang=ru')
            self.assertEqual(response.data, PNG)
            self.assertEqual(response.mimetype, 'image/png')
            cache.write_bytes(b'<html>corrupt</html>')
            response = app.test_client().get('/api/apps/fair/screenshot?lang=ru')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, WEBP)

    def test_refresh_is_background_daily_deduplicated_and_persistent(self):
        module = self.module()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def readme(repo):
            entered.set()
            if not release.wait(3):
                raise AssertionError('Fixture worker was not released')
            return '![Screenshot](screenshot.png)', f'https://raw.githubusercontent.com/yaroslav-softcode/{repo}/actual-branch/README.md'
        manager = module.CatalogManager(self.root / 'data', self.root)
        with patch.object(module.time, 'time', return_value=100000), patch.object(module, 'fetch_readme', side_effect=readme) as fetch_readme, patch.object(module, 'fetch_image', return_value=(PNG, 'image/png')) as fetch_image:
            self.assertTrue(manager.refresh())
            self.assertTrue(entered.wait(2))
            self.assertTrue(manager._worker.daemon)
            self.assertFalse(manager.refresh())
            self.assertFalse(manager.refresh(force=True))
            second_manager = module.CatalogManager(self.root / 'data', self.root)
            self.assertFalse(second_manager.refresh(force=True))
            release.set()
            manager._worker.join(5)
            self.assertFalse(manager._worker.is_alive())
            self.assertEqual(fetch_readme.call_count, 2)
            self.assertEqual(fetch_image.call_count, 2, 'Same README image serves both languages without duplicate HTTP requests')
            for app_id in ('fair', 'pastepen'):
                for lang in ('ru', 'en'):
                    self.assertEqual(manager.image(app_id, lang), (PNG, 'image/png'))
            self.assertFalse(manager.refresh())
            self.assertFalse(module.CatalogManager(self.root / 'data', self.root).refresh())
        with patch.object(module.time, 'time', return_value=100000 + module.REFRESH_SECONDS + 1), patch.object(module, 'fetch_readme', side_effect=readme), patch.object(module, 'fetch_image', return_value=(WEBP, 'image/webp')):
            self.assertTrue(manager.refresh())
            manager._worker.join(5)
            self.assertEqual(manager.image('fair', 'ru'), (WEBP, 'image/webp'))
        self.assertEqual(list(manager.cache_dir.glob('*.tmp')), [])
        self.assertFalse((manager.cache_dir / '.refresh.lock').exists())

    def test_failed_refresh_preserves_last_good_and_does_not_block_other_app(self):
        module = self.module()
        manager = module.CatalogManager(self.root / 'data', self.root)
        manager.cache_dir.mkdir(parents=True)
        (manager.cache_dir / 'fair-ru.image').write_bytes(WEBP)
        def readme(repo):
            if repo == 'FAIR':
                raise OSError('Offline')
            return '![Screenshot](screenshot.png)', f'https://raw.githubusercontent.com/yaroslav-softcode/{repo}/main/README.md'
        with patch.object(module, 'fetch_readme', side_effect=readme), patch.object(module, 'fetch_image', return_value=(PNG, 'image/png')):
            self.assertTrue(manager.refresh())
            manager._worker.join(5)
        self.assertEqual(manager.image('fair', 'ru'), (WEBP, 'image/webp'))
        self.assertEqual(manager.image('pastepen', 'en'), (PNG, 'image/png'))
        with patch.object(module, 'fetch_readme', side_effect=readme) as fetch_readme:
            self.assertFalse(manager.refresh())
            fetch_readme.assert_not_called()

    def test_atomic_cache_write_failure_keeps_previous_image_and_cleans_temp(self):
        module = self.module()
        manager = module.CatalogManager(self.root / 'data', self.root)
        manager.cache_dir.mkdir(parents=True)
        (manager.cache_dir / 'fair-ru.image').write_bytes(WEBP)
        original_replace = module.os.replace
        def failing_replace(source, destination):
            if str(destination).endswith('.image'):
                self.assertEqual(module.image_mime(Path(source).read_bytes()), 'image/png')
                raise OSError('Locked file')
            return original_replace(source, destination)
        with patch.object(module, 'fetch_readme', side_effect=lambda repo: ('![Screenshot](screenshot.png)', f'https://raw.githubusercontent.com/yaroslav-softcode/{repo}/main/README.md')), patch.object(module, 'fetch_image', return_value=(PNG, 'image/png')), patch.object(module.os, 'replace', side_effect=failing_replace):
            self.assertTrue(manager.refresh(force=True))
            manager._worker.join(5)
        self.assertEqual(manager.image('fair', 'ru'), (WEBP, 'image/webp'))
        self.assertEqual(list(manager.cache_dir.glob('*.tmp')), [])

    def test_failed_first_refresh_is_daily_and_route_returns_fallback_while_pending(self):
        module = self.module()
        bundled = self.root / 'frontend' / 'dist' / 'author-apps'
        bundled.mkdir(parents=True)
        (bundled / 'fair-ru.webp').write_bytes(WEBP)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def offline(repo):
            entered.set()
            release.wait(3)
            raise TimeoutError('Offline')
        app = Flask(__name__)
        manager = module.register_catalog(app, self.root / 'data', self.root)
        with patch.object(module, 'fetch_readme', side_effect=offline):
            self.assertTrue(manager.refresh())
            self.assertTrue(entered.wait(2))
            response = app.test_client().get('/api/apps/fair/screenshot?lang=ru')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, WEBP)
            release.set()
            manager._worker.join(5)
            self.assertFalse(manager.refresh())
            self.assertFalse(module.CatalogManager(self.root / 'data', self.root).refresh())


    def test_four_offline_assets_are_real_webp_and_pastepen_shares_one_image(self):
        module = self.module()
        folder = Path(module.__file__).parent / 'frontend' / 'public' / 'author-apps'
        images = {}
        for app_id in ('fair', 'pastepen'):
            for lang in ('ru', 'en'):
                path = folder / f'{app_id}-{lang}.webp'
                self.assertTrue(path.is_file(), f'Missing bundled fallback {path}')
                images[(app_id, lang)] = path.read_bytes()
                self.assertEqual(module.image_mime(images[(app_id, lang)]), 'image/webp')
        self.assertEqual(images[('pastepen', 'ru')], images[('pastepen', 'en')])
        self.assertNotEqual(images[('fair', 'ru')], images[('fair', 'en')])


    def test_parser_excludes_small_html_icons_and_open_graph_cards(self):
        module = self.module()
        base = 'https://raw.githubusercontent.com/yaroslav-softcode/FAIR/main/README.md'
        readme = '''
<img src="https://github.com/user-attachments/assets/0b876119-a721-408d-aa11-9bde532e419c" width="24" height="24">
![Open Graph](assets/og-card.webp)
![Profile photo](assets/profile.jpg)
![Actual app screenshot](screenshots/window.png)
'''
        self.assertEqual(module.screenshot_candidates(readme, base, 'FAIR', 'ru'),
                         [base.rsplit('/', 1)[0] + '/screenshots/window.png'])


if __name__ == '__main__':
    unittest.main()

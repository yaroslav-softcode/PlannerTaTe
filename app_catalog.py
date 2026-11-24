"""Local screenshots for the author's applications shown in About.

README images are resolved on the server; the browser never visits GitHub.
Only the two public repositories below are eligible screenshot sources.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import logging
import math
import os
from pathlib import Path
import re
import ssl
import struct
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
import zlib
import uuid

from flask import Blueprint, abort, make_response, request

OWNER = 'yaroslav-softcode'
APP_REPOS = {'fair': 'FAIR', 'pastepen': 'paste-pen'}
_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
_ATTACHMENT = re.compile(r'/user-attachments/assets/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_README_BYTES = 2 * 1024 * 1024
HTTP_TIMEOUT = 12
TRANSFER_TIMEOUT = 30
_CDN_HOSTS = frozenset(('user-images.githubusercontent.com',
                        'private-user-images.githubusercontent.com',
                        'github-production-user-asset-6210df.s3.amazonaws.com'))
_MIMES = frozenset(('image/png', 'image/jpeg', 'image/webp'))
REFRESH_SECONDS = 24 * 60 * 60
_LOCK_SECONDS = 60 * 60
_LOG = logging.getLogger(__name__)


def _https_parts(url: str):
    if not isinstance(url, str) or re.search(r'[\x00-\x20\x7f\\]', url):
        return None
    try:
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443)
                or parts.fragment or not parts.hostname):
            return None
        return parts
    except ValueError:
        return None


def is_allowed_image_url(url: str, repo: str) -> bool:
    """Initial URLs: same owner/repo raw files or GitHub attachment UUIDs."""
    parts = _https_parts(url)
    if parts is None or parts.query or repo not in APP_REPOS.values():
        return False
    path = unquote(parts.path)
    # Reject encoded traversal, double encoding and URL-parser disagreements.
    if '%' in path or '\\' in path or any(p in ('.', '..') for p in path.split('/')):
        return False
    if parts.hostname == 'raw.githubusercontent.com':
        pieces = path.split('/')
        return (len(pieces) >= 5 and pieces[1].lower() == OWNER
                and pieces[2].lower() == repo.lower() and all(pieces[3:]))
    return parts.hostname == 'github.com' and _ATTACHMENT.fullmatch(path) is not None


class _ImageTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'img':
            attrs = dict(attrs)
            if any(re.fullmatch(r'\d+(?:px)?', attrs.get(key) or '')
                   and int((attrs[key]).removesuffix('px')) < 128
                   for key in ('width', 'height')):
                return
            if attrs.get('src'):
                self.images.append((self.getpos(), attrs.get('alt', '') + ' ' + attrs.get('title', '')
                                    + ' ' + attrs.get('lang', ''), attrs['src']))


def _language(text: str) -> str:
    if re.search(r'(?<![a-z])(?:ru|rus|russian)(?![a-z])|русск', text):
        return 'ru'
    if re.search(r'(?<![a-z])(?:en|eng|english)(?![a-z])|английск', text):
        return 'en'
    return ''


def screenshot_candidates(markdown: str, download_url: str, repo: str,
                          lang: str = 'ru') -> list[str]:
    """Rank Markdown/HTML README images, not arbitrary links or web pages."""
    if not is_allowed_image_url(download_url, repo):
        return []
    markdown = re.sub(r'<!--.*?-->', '', markdown, flags=re.S)
    markdown = re.sub(r'^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', markdown, flags=re.M | re.S)
    references = {match.group(1).strip().casefold(): match.group(2) or match.group(3)
                  for match in re.finditer(
                      r'^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))', markdown, re.M)}
    images = [(m.start(), m.group(1), m.group(2) or m.group(3)) for m in re.finditer(
        r'!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\"\'].*?[\"\'])?\s*\)', markdown)]
    for match in re.finditer(r'!\[([^\]]*)\]\[([^\]]*)\]', markdown):
        target = references.get((match.group(2) or match.group(1)).strip().casefold())
        if target:
            images.append((match.start(), match.group(1), target))
    tags = _ImageTags()
    tags.feed(markdown)
    lines = markdown.splitlines(keepends=True)
    images.extend((sum(map(len, lines[:line - 1])) + column, alt, src)
                  for (line, column), alt, src in tags.images)
    ranked = []
    for index, alt, source in images:
        url = urljoin(download_url, unescape(source))
        if not is_allowed_image_url(url, repo):
            continue
        if urlsplit(url).hostname == 'raw.githubusercontent.com' and not urlsplit(url).path.lower().endswith(_IMAGE_EXTENSIONS):
            continue
        text = (alt + ' ' + unquote(urlsplit(url).path)).lower()
        if re.search(r'badge|shield|avatar|portrait|profile|headshot|author|favicon|\bicon\b|(?:^|[/_.-])icon(?:[/_.-]|$)|logo|og[-_](?:image|card)|open\s*graph|автор|портрет|фото автора', text):
            continue
        screenshot = bool(re.search(r'screen(?:shot)?|скрин|снимок|интерфейс|interface|window|окно|(?:^|[/_.-])ui(?:[/_.-]|$)', text))
        image_lang = _language(alt.lower() + ' ' + urlsplit(url).path.rsplit('/', 1)[-1].lower())
        language_rank = 2 if image_lang == lang else (1 if not image_lang else 0)
        ranked.append(((int(screenshot), language_rank, -index), url))
    ranked.sort(reverse=True)
    return list(dict.fromkeys(url for _rank, url in ranked))


def _image_destination(url: str, repo: str, source: str) -> bool:
    parts = _https_parts(url)
    if parts is None:
        return False
    if urlsplit(source).hostname == 'github.com':
        return url == source or parts.hostname in _CDN_HOSTS
    return parts.hostname == 'raw.githubusercontent.com' and is_allowed_image_url(url, repo)


class _CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, allowed):
        super().__init__()
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allowed(newurl):
            raise ValueError('Screenshot redirect is outside the GitHub allowlist')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _SafeRedirect(_CheckedRedirect):
    def __init__(self, repo: str, source: str):
        super().__init__(lambda url: _image_destination(url, repo, source))


def _open_url(request: Request, allowed):
    # Never inherit a requests session, browser cookies or a disabled TLS context.
    # ProxyHandler({}) keeps the path direct, matching the updater.
    context = ssl.create_default_context()
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), _CheckedRedirect(allowed))
    return opener.open(request, timeout=HTTP_TIMEOUT)


def _fetch_bytes(url: str, allowed, limit: int, accept: str) -> tuple[bytes, str]:
    if not allowed(url):
        raise ValueError('URL is outside the GitHub allowlist')
    request = Request(url, headers={'User-Agent': 'PlannerTaTe-Author-Catalog/1.0',
                                   'Accept': accept, 'Accept-Encoding': 'identity'})
    deadline = time.monotonic() + TRANSFER_TIMEOUT
    with _open_url(request, allowed) as response:
        if not allowed(response.geturl()) or response.status != 200:
            raise ValueError('Unexpected screenshot response URL/status')
        if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
            raise ValueError('Compressed transport is not supported')
        length = response.headers.get('Content-Length')
        if length is not None and (not length.isdigit() or int(length) > limit):
            raise ValueError('Screenshot response exceeds the size limit')
        chunks = []
        total = 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('Screenshot transfer deadline exceeded')
            chunk = response.read(min(65536, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError('Screenshot response exceeds the size limit')
            chunks.append(chunk)
        if length is not None and total != int(length):
            raise ValueError('Truncated screenshot response')
        return b''.join(chunks), response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()


def _png_valid(data: bytes) -> bool:
    pos = 8
    seen_header = seen_pixels = False
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            return False
        payload = data[pos + 8:end - 4]
        if zlib.crc32(kind + payload) != int.from_bytes(data[end - 4:end], 'big'):
            return False
        if not seen_header:
            if kind != b'IHDR' or length != 13:
                return False
            width, height = struct.unpack('>II', payload[:8])
            if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= 40000000):
                return False
            seen_header = True
        elif kind == b'IHDR':
            return False
        if kind == b'IDAT' and length:
            seen_pixels = True
        if kind == b'IEND':
            return length == 0 and seen_pixels and end == len(data)
        pos = end
    return False


def _jpeg_valid(data: bytes) -> bool:
    if not data.endswith(b'\xff\xd9'):
        return False
    pos = 2
    dimensions = False
    while pos + 4 <= len(data):
        if data[pos] != 255:
            return False
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos + 3 > len(data):
            return False
        marker = data[pos]
        pos += 1
        length = int.from_bytes(data[pos:pos + 2], 'big')
        if length < 2 or pos + length > len(data):
            return False
        if marker in (0xC0, 0xC1, 0xC2):
            if length < 8:
                return False
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
            dimensions = 0 < width <= 16384 and 0 < height <= 16384 and width * height <= 40000000
        if marker == 0xDA:
            return dimensions and pos + length < len(data) - 2
        pos += length
    return False


def _webp_valid(data: bytes) -> bool:
    if len(data) < 30 or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        return False
    pos = 12
    pixels = False
    while pos + 8 <= len(data):
        kind = data[pos:pos + 4]
        length = int.from_bytes(data[pos + 4:pos + 8], 'little')
        end = pos + 8 + length
        if end > len(data):
            return False
        payload = data[pos + 8:end]
        if kind == b'VP8 ':
            if length < 10 or payload[3:6] != b'\x9d\x01\x2a':
                return False
            width = int.from_bytes(payload[6:8], 'little') & 0x3fff
            height = int.from_bytes(payload[8:10], 'little') & 0x3fff
            pixels = 0 < width and 0 < height and width * height <= 40000000
        elif kind == b'VP8L':
            if length < 5 or payload[0] != 0x2f:
                return False
            bits = int.from_bytes(payload[1:5], 'little')
            width, height = (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
            pixels = width * height <= 40000000
        elif kind in (b'ANIM', b'ANMF'):
            return False  # About needs still screenshots, never animated tracking.
        pos = end + (length & 1)
    return pixels and pos == len(data)


def image_mime(data: bytes) -> str | None:
    """Check image containers/signatures, dimensions and truncation without PIL.

    This is not a pixel decoder: GitHub supplies the image bitstream, while these
    checks reject active content, wrong formats and incomplete cache writes.
    """
    if not isinstance(data, bytes) or not 30 <= len(data) <= MAX_IMAGE_BYTES:
        return None
    if data.startswith(b'\x89PNG\r\n\x1a\n') and _png_valid(data):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff') and _jpeg_valid(data):
        return 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP' and _webp_valid(data):
        return 'image/webp'
    return None


def fetch_image(url: str, repo: str) -> tuple[bytes, str]:
    if not is_allowed_image_url(url, repo):
        raise ValueError('Screenshot source is outside the GitHub allowlist')
    data, declared = _fetch_bytes(url, lambda target: _image_destination(target, repo, url),
                                  MAX_IMAGE_BYTES, ', '.join(sorted(_MIMES)))
    detected = image_mime(data)
    if declared not in _MIMES or detected != declared:
        raise ValueError('Screenshot is not a valid PNG, JPEG or WebP image')
    return data, detected


def fetch_readme(repo: str) -> tuple[str, str]:
    """GitHub chooses the README and branch; never assume master/main."""
    if repo not in APP_REPOS.values():
        raise ValueError('Unknown author repository')
    url = f'https://api.github.com/repos/{OWNER}/{repo}/readme'
    try:
        data, _mime = _fetch_bytes(url, lambda target: target == url,
                                   MAX_README_BYTES, 'application/vnd.github+json')
    except HTTPError as error:
        if error.code not in (403, 429):
            raise
        # Public raw HEAD follows the repository's default branch without using
        # the rate-limited API. Sources remain restricted to this exact repo.
        last_error = None
        for name in ('README.md', 'readme.md', 'Readme.md'):
            raw = f'https://raw.githubusercontent.com/{OWNER}/{repo}/HEAD/{name}'
            try:
                data, mime = _fetch_bytes(raw, lambda target, expected=raw: target == expected,
                                         MAX_README_BYTES, 'text/plain')
            except HTTPError as error:
                last_error = error
                if error.code == 404:
                    continue
                raise
            if mime not in ('text/plain', 'text/markdown', 'application/octet-stream'):
                raise ValueError('Unexpected public README content type')
            return data.decode('utf-8-sig'), raw
        raise last_error or ValueError('README not found')
    payload = json.loads(data.decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Invalid GitHub README response')
    download_url = payload.get('download_url')
    if not is_allowed_image_url(download_url, repo) or urlsplit(download_url).hostname != 'raw.githubusercontent.com':
        raise ValueError('README download URL is outside its repository')
    if payload.get('encoding') != 'base64' or not isinstance(payload.get('content'), str):
        raise ValueError('README content is not base64')
    try:
        decoded = base64.b64decode(''.join(payload['content'].split()), validate=True)
        return decoded.decode('utf-8-sig'), download_url
    except (binascii.Error, UnicodeError) as error:
        raise ValueError('Invalid README encoding') from error


def _read_image(path: Path) -> tuple[bytes, str] | None:
    try:
        with path.open('rb') as handle:
            data = handle.read(MAX_IMAGE_BYTES + 1)
        mime = image_mime(data)
        return (data, mime) if mime else None
    except OSError:
        return None


class CatalogManager:
    def __init__(self, data_dir, res_dir):
        self.cache_dir = Path(data_dir) / 'app-catalog'
        self.res_dir = Path(res_dir)
        self._lock = threading.Lock()
        self._worker = None
        self._last_attempt = None

    def image(self, app_id: str, lang: str) -> tuple[bytes, str] | None:
        if app_id not in APP_REPOS or lang not in ('ru', 'en'):
            return None
        cached = _read_image(self.cache_dir / f'{app_id}-{lang}.image')
        if cached:
            return cached
        for folder in ('dist', 'public'):
            for fallback_lang in (lang, 'en' if lang == 'ru' else 'ru'):
                result = _read_image(self.res_dir / 'frontend' / folder / 'author-apps'
                                     / f'{app_id}-{fallback_lang}.webp')
                if result:
                    return result
        return None

    def refresh(self, force: bool = False) -> bool:
        """Queue both apps; return immediately, false if fresh/already running.

        An unsuccessful attempt also counts toward the daily limit. Explicit
        force bypasses freshness, never the thread/process single-flight locks.
        """
        if not self._lock.acquire(blocking=False):
            return False
        token = None
        try:
            if self._worker is not None and self._worker.is_alive():
                return False
            now = time.time()
            if not force and self._fresh(now):
                return False
            token = self._acquire_process_lock(now)
            if token is None:
                return False
            # Another manager/process may have completed since the first check.
            if not force and self._fresh(now):
                self._release_process_lock(token)
                return False
            self._atomic_write(self.cache_dir / 'state.json',
                               json.dumps({'last_attempt': now}).encode('utf-8'))
            self._last_attempt = now
            self._worker = threading.Thread(target=self._refresh_worker,
                                             args=(token,), daemon=True,
                                             name='author-app-screenshots')
            self._worker.start()
            return True
        except (OSError, RuntimeError, ValueError):
            if token is not None:
                self._release_process_lock(token)
            _LOG.debug('Cannot start author screenshot refresh', exc_info=True)
            return False
        finally:
            self._lock.release()

    def _fresh(self, now: float) -> bool:
        last = self._last_attempt
        try:
            with (self.cache_dir / 'state.json').open('rb') as handle:
                state = json.loads(handle.read(4097))
            persisted = state.get('last_attempt') if isinstance(state, dict) else None
            if isinstance(persisted, (int, float)) and math.isfinite(persisted):
                last = max(last or 0, persisted)
        except (OSError, ValueError, UnicodeError):
            pass
        return last is not None and -300 <= now - last < REFRESH_SECONDS

    def _acquire_process_lock(self, now: float) -> str | None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / '.refresh.lock'
        token = uuid.uuid4().hex
        for _attempt in range(2):
            try:
                with path.open('x', encoding='ascii') as handle:
                    json.dump({'created': now, 'token': token}, handle)
                return token
            except FileExistsError:
                try:
                    with path.open('rb') as handle:
                        contents = handle.read(4097)
                    state = json.loads(contents)
                    created = state['created']
                    stale = isinstance(created, (int, float)) and math.isfinite(created) and now - created > _LOCK_SECONDS
                except (OSError, ValueError, KeyError, TypeError):
                    # A partially written lock may be an active competing writer.
                    try:
                        stale = now - path.stat().st_mtime > _LOCK_SECONDS
                    except OSError:
                        stale = False
                if not stale:
                    return None
                try:
                    path.unlink()
                except OSError:
                    return None
        return None

    def _release_process_lock(self, token: str):
        path = self.cache_dir / '.refresh.lock'
        try:
            with path.open('rb') as handle:
                state = json.loads(handle.read(4097))
            if state.get('token') == token:
                path.unlink()
        except (OSError, ValueError, AttributeError):
            pass

    @staticmethod
    def _atomic_write(path: Path, data: bytes):
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _refresh_worker(self, token: str):
        try:
            for app_id, repo in APP_REPOS.items():
                try:
                    markdown, download_url = fetch_readme(repo)
                except Exception:
                    _LOG.debug('Cannot read public README for %s', repo, exc_info=True)
                    continue
                fetched = {}
                for lang in ('ru', 'en'):
                    for url in screenshot_candidates(markdown, download_url, repo, lang)[:4]:
                        if url not in fetched:
                            try:
                                image, mime = fetch_image(url, repo)
                                fetched[url] = image if image_mime(image) == mime else None
                            except Exception:
                                _LOG.debug('Cannot fetch %s README screenshot', repo, exc_info=True)
                                fetched[url] = None
                        image = fetched[url]
                        if image is None:
                            continue
                        try:
                            self._atomic_write(self.cache_dir / f'{app_id}-{lang}.image', image)
                        except OSError:
                            _LOG.debug('Cannot replace %s screenshot cache', app_id, exc_info=True)
                        break
        finally:
            self._release_process_lock(token)


def register_catalog(app, data_dir, res_dir) -> CatalogManager:
    """Register only the screenshot route; download routes belong to updater."""
    if 'app_catalog' in app.extensions:
        return app.extensions['app_catalog']
    manager = CatalogManager(data_dir, res_dir)
    blueprint = Blueprint('author_app_catalog', __name__)

    @blueprint.get('/api/apps/<app_id>/screenshot')
    def author_app_screenshot(app_id):
        if app_id not in APP_REPOS:
            abort(404)
        lang = request.args.get('lang', 'ru')
        if lang not in ('ru', 'en'):
            abort(400)
        image = manager.image(app_id, lang)
        manager.refresh()
        if image is None:
            abort(503, description='Bundled application screenshot is missing')
        data, mime = image
        response = make_response(data)
        response.mimetype = mime
        response.headers['Cache-Control'] = 'private, no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response.set_etag(hashlib.sha256(data).hexdigest())
        return response.make_conditional(request)

    app.register_blueprint(blueprint)
    app.extensions['app_catalog'] = manager
    return manager

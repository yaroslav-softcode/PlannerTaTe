"""Desktop update API; never imports Qt or loads graph/phone/user settings.

Integration: register_updates(app, DATA_DIR, installed_exe=sys.executable,
on_exit=qt_signal.emit). The callback must be thread-safe (a daemon timer calls
it). POSTs accept an empty body or {} and X-Plannertate-Client: 1. GETs need no
custom header. All these routes are loopback-only, independently of other APIs.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import hashlib
import hmac
import ipaddress
import json
import os
import uuid
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (HTTPSHandler, HTTPRedirectHandler, ProxyHandler,
                            Request, build_opener)

from flask import Blueprint, jsonify, redirect, request

APP_VERSION = "1.13"
REPO = "yaroslav-softcode/PlannerTaTe"
REPO_URL = f"https://github.com/{REPO}"
_APP_REPOS = {
    "fair": ("yaroslav-softcode/FAIR", "FAIR-Setup-{version}.exe"),
    "pastepen": ("yaroslav-softcode/paste-pen", "PastePen_v{version}.exe"),
}
APP_LINK_CACHE_SECONDS = 300.0
NETWORK_TIMEOUT = 12.0
CHECK_TIMEOUT = 15.0
MAX_API_SIZE = 2 * 1024 * 1024
MAX_DOWNLOAD_SIZE = 512 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
_VERSION = re.compile(r"v?([0-9]{1,8}(?:\.[0-9]{1,8}){1,3})\Z", re.ASCII)
_DIGEST = re.compile(r"sha256:([0-9a-fA-F]{64})\Z", re.ASCII)
_METADATA_GATES = {repo: threading.BoundedSemaphore(1)
                   for repo in (REPO, *[entry[0] for entry in _APP_REPOS.values()])}
# When the last fetch of a repo started. A daemon thread wedged in DNS can hold
# its gate forever; after the stale window we reclaim the slot instead of
# disabling update checks until the process restarts.
_GATE_STARTED = {}
STALE_GATE_SECONDS = CHECK_TIMEOUT * 2


class UpdateError(Exception):
    """Only a fixed machine code, never upstream response/exception text."""
    def __init__(self, code, http_status=400):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _version(value):
    if not isinstance(value, str) or not (match := _VERSION.fullmatch(value)):
        raise UpdateError("invalid_version")
    text = match.group(1)
    parts = tuple(int(part) for part in text.split("."))
    return text, parts + (0,) * (4 - len(parts))


def _https_url(url):
    if not isinstance(url, str) or any(ord(char) < 33 for char in url) or "\\" in url:
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname is not None and
                parsed.username is None and parsed.password is None and
                parsed.port in (None, 443) and not parsed.fragment)
    except ValueError:
        return False


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise UpdateError("network_timeout")
    return min(NETWORK_TIMEOUT, remaining)


class _SafeRedirectHandler(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def __init__(self, allowed, deadline):
        super().__init__()
        self.allowed, self.deadline = allowed, deadline

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _https_url(newurl) or not self.allowed(newurl):
            raise UpdateError("unsafe_redirect")
        _remaining(self.deadline)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    def http_error_302(self, req, fp, code, msg, headers):
        req.timeout = _remaining(self.deadline)
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _make_opener(allowed, deadline):
    # No credentials/cookies/auth handlers; never disable certificate validation.
    return build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                        _SafeRedirectHandler(allowed, deadline))


def _error_code(exc):
    if isinstance(exc, UpdateError):
        return exc.code
    if isinstance(exc, HTTPError):
        return {403: "rate_limited", 429: "rate_limited",
                404: "release_not_found"}.get(exc.code, "http_error")
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return "tls_error"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "network_timeout"
    return "network_error"


def _open_response(url, allowed, deadline, api=False, method="GET", accept=None):
    if not _https_url(url) or not allowed(url):
        raise UpdateError("invalid_asset_url")
    headers = {"User-Agent": f"PlannerTaTe/{APP_VERSION} desktop-updater",
               "Accept": accept or ("application/vnd.github+json" if api else "application/octet-stream"),
               "Accept-Encoding": "identity"}
    if api:
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    response = _make_opener(allowed, deadline).open(Request(url, headers=headers, method=method),
                                                  timeout=_remaining(deadline))
    if not _https_url(response.geturl()) or not allowed(response.geturl()):
        response.close()
        raise UpdateError("unsafe_redirect")
    if response.status != 200:
        status, response_headers, final_url = response.status, response.headers, response.geturl()
        response.close()
        raise HTTPError(final_url, status, "", response_headers, None)
    return response


def _read_chunk(response, size, deadline):
    # read1 makes at most one raw read; shrink the socket timeout to the absolute
    # deadline so a trickling server cannot hold a synchronous check indefinitely.
    timeout = _remaining(deadline)
    raw_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    if raw_socket is not None:
        raw_socket.settimeout(timeout)
    chunk = getattr(response, "read1", response.read)(size)
    _remaining(deadline)
    return chunk


def _latest_release(repo):
    # urllib's socket timeout alone cannot bound OS DNS resolution. The HTTP
    # caller waits at most CHECK_TIMEOUT; a wedged daemon keeps a repo-specific
    # slot until it exits, so retries cannot create unbounded background work.
    gate = _METADATA_GATES[repo]
    if not gate.acquire(blocking=False):
        started = _GATE_STARTED.get(repo)
        if not started or time.monotonic() - started <= STALE_GATE_SECONDS:
            raise UpdateError("network_busy")
        try:
            gate.release()          # the previous worker is wedged past its budget
        except ValueError:
            pass
        if not gate.acquire(blocking=False):
            raise UpdateError("network_busy")
    _GATE_STARTED[repo] = time.monotonic()
    finished, outcome = threading.Event(), []
    deadline = time.monotonic() + CHECK_TIMEOUT

    def fetch():
        try:
            outcome.append(_fetch_latest_release(repo, deadline))
        except Exception as exc:
            outcome.append(exc)
        finally:
            _GATE_STARTED.pop(repo, None)
            try:
                gate.release()
            except ValueError:      # slot was reclaimed as stale after a timeout
                pass
            finished.set()

    try:
        threading.Thread(target=fetch, name="PlannerTaTe-release-check", daemon=True).start()
    except RuntimeError:
        gate.release()
        raise UpdateError("network_error") from None
    if not finished.wait(max(0, deadline - time.monotonic())):
        raise UpdateError("network_timeout")
    if isinstance(outcome[0], Exception):
        raise outcome[0]
    return outcome[0]


def _fetch_latest_release(repo, deadline):
    try:
        return _fetch_api_release(repo, deadline)
    except HTTPError as api_error:
        if api_error.code not in (403, 429):
            raise
        api_error.close()
        try:
            return _fetch_html_release(repo, deadline)
        except UpdateError:
            raise  # HTML integrity/redirect validation failures must remain visible.
        except Exception:
            raise api_error from None


def _read_metadata_body(response, deadline):
    content = bytearray()
    while chunk := _read_chunk(response, min(CHUNK_SIZE, MAX_API_SIZE + 1 - len(content)), deadline):
        content.extend(chunk)
        if len(content) > MAX_API_SIZE:
            raise UpdateError("response_too_large")
    return content


def _fetch_api_release(repo, deadline):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    with _open_response(url, lambda target: target == url, deadline, api=True) as response:
        content = _read_metadata_body(response, deadline)
    try:
        release = json.loads(content)
    except (ValueError, UnicodeError, RecursionError):
        raise UpdateError("invalid_response") from None
    if not isinstance(release, dict):
        raise UpdateError("invalid_response")
    if type(release.get("draft")) is not bool or type(release.get("prerelease")) is not bool:
        raise UpdateError("invalid_response")
    return release


class _GitHubReleaseHTML(HTMLParser):
    """Parse inert HTML only: asset href/digest are scoped to the same list row."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.badges, self._spans = [], [], []
        self._row, self._li_depth = None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            if self._row is None:
                self._row = {"links": [], "digests": []}
            self._li_depth += 1
        if self._row is not None:
            if tag == "a":
                self._row["links"].append(attrs.get("href"))
            elif tag == "clipboard-copy":
                self._row["digests"].append((attrs.get("aria-label"), attrs.get("value")))
        if tag == "span":
            self._spans.append([] if "Label" in attrs.get("class", "").split() else None)

    def handle_data(self, data):
        for capture in self._spans:
            if capture is not None:
                capture.append(data)

    def handle_endtag(self, tag):
        if tag == "li" and self._row is not None:
            self._li_depth -= 1
            if self._li_depth == 0:
                self.rows.append(self._row)
                self._row = None
        if tag == "span" and self._spans:
            capture = self._spans.pop()
            if capture is not None:
                self.badges.append("".join(capture).strip().casefold())


def _release_page_allowed(url, repo):
    if not _https_url(url):
        return False
    base = f"https://github.com/{repo}/releases/"
    if url == base + "latest":
        return True
    if not url.startswith(base + "tag/"):
        return False
    try:
        _version(url.removeprefix(base + "tag/"))
        return True
    except UpdateError:
        return False


def _parse_release_html(content):
    parser = _GitHubReleaseHTML()
    try:
        parser.feed(content.decode("utf-8", errors="strict"))
        parser.close()
    except (ValueError, UnicodeError, RecursionError):
        raise UpdateError("invalid_response") from None
    return parser


def _fetch_html_release(repo, deadline):
    base = f"https://github.com/{repo}"
    with _open_response(base + "/releases/latest", lambda url: _release_page_allowed(url, repo),
                        deadline, accept="text/html") as response:
        final = response.geturl()
        page = _parse_release_html(_read_metadata_body(response, deadline))
    prefix = base + "/releases/tag/"
    if not final.startswith(prefix):
        raise UpdateError("invalid_response")
    tag = final.removeprefix(prefix)
    version, numeric = _version(tag)
    if any(badge in ("pre-release", "prerelease", "draft") for badge in page.badges):
        raise UpdateError("release_not_stable")
    payload = {"tag_name": tag, "draft": False, "prerelease": False,
               "html_url": final, "assets": [], "metadata_source": "github_html"}
    if repo == REPO and numeric <= _version(APP_VERSION)[1]:
        return payload  # Never HEAD/download a same-version or older installer.
    pattern = ("PlannerTaTe_Setup_{version}.exe" if repo == REPO else
               next(entry[1] for entry in _APP_REPOS.values() if entry[0] == repo))
    name = pattern.format(version=version)
    url = f"{base}/releases/download/{tag}/{name}"
    fragment = f"{base}/releases/expanded_assets/{tag}"
    with _open_response(fragment, lambda target: target == fragment, deadline,
                        accept="text/html") as response:
        parser = _parse_release_html(_read_metadata_body(response, deadline))
    relative = url.removeprefix("https://github.com")
    matching = [row for row in parser.rows if row["links"] in ([relative], [url])]
    if len(matching) != 1:
        raise UpdateError("asset_not_found")
    digests = [value for label, value in matching[0]["digests"]
               if label == f"Copy to clipboard digest for {name}"]
    digest = digests[0] if len(digests) == 1 else None
    size = None
    if repo == REPO:
        if not digest:
            raise UpdateError("missing_digest")
        if not _DIGEST.fullmatch(digest):
            raise UpdateError("invalid_digest")
        # GitHub's HTML size is rounded, so obtain exact bytes using HEAD only.
        with _open_response(url, lambda target: _asset_redirect_allowed(target, url), deadline,
                            method="HEAD") as response:
            length = response.headers.get("Content-Length", "")
        if (not str(length).isascii() or not str(length).isdigit() or len(str(length)) > 10 or
                not 2 <= int(length) <= MAX_DOWNLOAD_SIZE):
            raise UpdateError("invalid_size")
        size = int(length)
    payload["assets"] = [{"name": name, "browser_download_url": url, "digest": digest, "size": size}]
    return payload


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    url: str
    size: int
    sha256: str
    name: str


def _select_release(payload):
    if payload["draft"] or payload["prerelease"]:
        return None, None
    version, numeric = _version(payload.get("tag_name"))
    if numeric <= _version(APP_VERSION)[1]:
        return None, version
    name = f"PlannerTaTe_Setup_{version}.exe"
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("invalid_response")
    matching = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
    if len(matching) != 1:
        raise UpdateError("asset_not_found")
    asset = matching[0]
    size = asset.get("size")
    if type(size) is not int or not 2 <= size <= MAX_DOWNLOAD_SIZE:
        raise UpdateError("invalid_size")
    digest = asset.get("digest")
    if not digest:
        raise UpdateError("missing_digest")
    if not isinstance(digest, str) or not (match := _DIGEST.fullmatch(digest)):
        raise UpdateError("invalid_digest")
    tag = payload["tag_name"]
    expected = f"{REPO_URL}/releases/download/{tag}/{name}"
    if asset.get("browser_download_url") != expected:
        raise UpdateError("invalid_asset_url")
    return Release(version, tag, expected, size, match.group(1).lower(), name), version


def _loopback(value, hostname=False):
    if hostname and value == "localhost":
        return True
    try:
        address = ipaddress.ip_address(value)
        return address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and
                                           address.ipv4_mapped.is_loopback)
    except (ValueError, TypeError):
        return False


def _origin_tuple(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or parsed.username is not None or
                parsed.password is not None or parsed.path or parsed.query or parsed.fragment or
                not _loopback(parsed.hostname, hostname=True)):
            return None
        port = parsed.port
        return parsed.scheme, parsed.hostname, port if port is not None else (443 if parsed.scheme == "https" else 80)
    except (ValueError, TypeError):
        return None


def _guard_local():
    host = request.headers.get("Host", "")
    local_origin = _origin_tuple(f"{request.scheme}://{host}")
    if not _loopback(request.remote_addr) or local_origin is None:
        raise UpdateError("local_only", 403)
    origin = request.headers.get("Origin")
    if origin is not None and _origin_tuple(origin) != local_origin:
        raise UpdateError("origin_forbidden", 403)
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        raise UpdateError("cross_site_forbidden", 403)
    if request.method == "POST":
        if request.headers.get("X-Plannertate-Client") != "1":
            raise UpdateError("client_header_required", 403)
        if request.args or (request.content_length or 0) > 1024:
            raise UpdateError("invalid_request")
        body = request.stream.read(1025)
        try:
            if len(body) > 1024 or (body.strip() and json.loads(body) != {}):
                raise UpdateError("invalid_request")
        except (ValueError, UnicodeError):
            raise UpdateError("invalid_request") from None


def _asset_redirect_allowed(url, initial):
    if not _https_url(url):
        return False
    host = urlsplit(url).hostname
    return url == initial or host in {
        "release-assets.githubusercontent.com", "objects.githubusercontent.com",
        "github-releases.githubusercontent.com"}


def _ensure_updates_dir(base):
    directory = base / "updates"
    if directory.is_symlink() or directory.resolve() != base / "updates":
        raise UpdateError("unsafe_update_directory")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _verify_file(path, release):
    if path.is_symlink() or not path.is_file():
        raise UpdateError("download_missing")
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size != release.size:
            raise UpdateError("size_mismatch")
        if stream.read(2) != b"MZ":
            raise UpdateError("invalid_executable")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not hmac.compare_digest(digest, release.sha256):
            raise UpdateError("hash_mismatch")


def _installed_target(installed_exe):
    if sys.platform != "win32" or not getattr(sys, "frozen", False) or installed_exe is None:
        return None
    try:
        target = Path(installed_exe)
        if (target.is_symlink() or not target.is_absolute() or
                target.name.casefold() != "plannertate.exe" or not target.is_file() or
                not target.samefile(sys.executable) or
                not (target.parent / "unins000.exe").is_file()):
            return None
        return target.resolve()
    except (OSError, ValueError, TypeError):
        return None


def _process_identity(process_id):
    """Capture executable and kernel creation time; never take a PID from HTTP."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    handle = kernel.OpenProcess(0x1000, False, process_id)
    if not handle:
        return None
    try:
        length = wintypes.DWORD(32768)
        name = ctypes.create_unicode_buffer(length.value)
        times = [wintypes.FILETIME() for _ in range(4)]
        if (not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)) or
                not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times))):
            return None
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return name.value, created
    finally:
        kernel.CloseHandle(handle)


def _powershell_path():
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < count < len(buffer):
        raise UpdateError("helper_launch_failed", 500)
    path = Path(buffer.value) / "WindowsPowerShell/v1.0/powershell.exe"
    if not path.is_file():
        raise UpdateError("helper_launch_failed", 500)
    return path


def _ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _render_helper(release, installer, installed, processes, helper_log, installer_log, receipt):
    """UTF-8-BOM file is emitted by install(); all values originate on the server."""
    entries = ", ".join("@{ Id = " + str(int(pid)) + "; Started = '" + str(int(start)) + "' }"
                        for pid, start in processes)
    prelude = (
        "$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version 2.0\n"
        f"$installer = {_ps_literal(installer)}\n"
        f"$installedExe = {_ps_literal(installed)}\n"
        f"$installDir = {_ps_literal(installed.parent)}\n"
        f"$expectedHash = {_ps_literal(release.sha256)}\n"
        f"$expectedSize = [long]{release.size}\n"
        f"$version = {_ps_literal(release.version)}\n"
        f"$helperLog = {_ps_literal(helper_log)}\n"
        f"$installerLog = {_ps_literal(installer_log)}\n"
        f"$receipt = {_ps_literal(receipt)}\n"
        f"$processes = @({entries})\n")
    return prelude + r'''
# Never terminate processes. Creation times avoid waiting on a recycled PID.
function Write-HelperLog([string]$code) {
    try { Add-Content -LiteralPath $helperLog -Value ((Get-Date -Format o) + ' ' + $code) -Encoding UTF8 } catch {}
}
$result = [ordered]@{ state = 'error'; error = 'helper_error'; version = $version;
    installer_exit_code = $null; restarted = $false; restart_error = $null; timestamp = $null }
$appExited = $false
$installerActive = $false
$lockedInstaller = $null
$installerProcess = $null
$phase = 'wait'
try {
    Write-HelperLog 'waiting_for_application'
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($entry in $processes) {
        $process = $null
        try {
            try { $process = [System.Diagnostics.Process]::GetProcessById([int]$entry.Id) }
            catch {
                if ($_.Exception -is [System.ArgumentException] -or $_.Exception.InnerException -is [System.ArgumentException]) { continue }
                throw 'wait_process_failed'
            }
            if ($process.StartTime.ToUniversalTime().ToFileTimeUtc().ToString() -ne $entry.Started) { continue }
            if (-not [string]::Equals($process.MainModule.FileName, $installedExe, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw 'process_identity_mismatch'
            }
            $remaining = 120000 - [int]$watch.ElapsedMilliseconds
            if ($remaining -le 0 -or -not $process.WaitForExit($remaining)) { throw 'wait_timeout' }
        } finally {
            if ($null -ne $process) { $process.Dispose() }
        }
    }
    $appExited = $true
    $phase = 'verify'
    # Keep a read-only handle open through installation: deny writes/replacement.
    if (((Get-Item -LiteralPath $installer).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'unsafe_update_directory' }
    $lockedInstaller = [IO.File]::Open($installer, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    if ($lockedInstaller.Length -ne $expectedSize) { throw 'size_mismatch' }
    if ($lockedInstaller.ReadByte() -ne 77 -or $lockedInstaller.ReadByte() -ne 90) { throw 'invalid_executable' }
    $lockedInstaller.Position = 0
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actualHash = [BitConverter]::ToString($sha.ComputeHash($lockedInstaller)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($actualHash -ne $expectedHash) { throw 'hash_mismatch' }
    $phase = 'install'
    Write-HelperLog 'starting_installer'
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/RESTARTEXITCODE=3010',
                   '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/NOFORCECLOSEAPPLICATIONS',
                   ('/DIR="' + $installDir + '"'), ('/LOG="' + $installerLog + '"'))
    $installerProcess = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru
    $installerActive = $true
    if (-not $installerProcess.WaitForExit(900000)) { throw 'installer_timeout' }
    $installerActive = $false
    $result.installer_exit_code = $installerProcess.ExitCode
    if ($installerProcess.ExitCode -notin @(0, 3010)) { throw 'installer_failed' }
    $result.state = 'success'
    $result.error = $null
    Write-HelperLog 'installer_success'
} catch {
    $known = @('wait_timeout', 'wait_process_failed', 'process_identity_mismatch', 'size_mismatch',
               'invalid_executable', 'hash_mismatch', 'installer_failed', 'installer_timeout', 'unsafe_update_directory')
    $message = $_.Exception.Message
    if ($known -contains $message) { $result.error = $message }
    else { $result.error = $phase + '_failed' }
    Write-HelperLog $result.error
} finally {
    if ($null -ne $lockedInstaller) { $lockedInstaller.Dispose() }
    if ($null -ne $installerProcess) { $installerProcess.Dispose() }
    # On installer/verification failure, relaunch the existing installation too.
    # A timed-out still-running app/installer is left alone, never duplicated.
    if ($appExited -and -not $installerActive) {
        try {
            $restartedProcess = Start-Process -FilePath $installedExe -WorkingDirectory $installDir -PassThru
            $restartedProcess.Dispose()
            $result.restarted = $true
            Write-HelperLog 'application_restarted'
        } catch {
            $result.restart_error = 'restart_failed'
            if ($result.state -eq 'success') { $result.state = 'error'; $result.error = 'restart_failed' }
            Write-HelperLog 'restart_failed'
        }
    }
    $result.timestamp = (Get-Date).ToUniversalTime().ToString('o')
    try {
        $json = $result | ConvertTo-Json -Compress
        $temporaryReceipt = $receipt + '.tmp'
        [IO.File]::WriteAllText($temporaryReceipt, $json, (New-Object Text.UTF8Encoding($true)))
        Move-Item -LiteralPath $temporaryReceipt -Destination $receipt -Force
        $lastReceipt = Join-Path (Split-Path -Parent $receipt) 'last-result.json'
        [IO.File]::WriteAllText(($lastReceipt + '.tmp'), $json, (New-Object Text.UTF8Encoding($true)))
        Move-Item -LiteralPath ($lastReceipt + '.tmp') -Destination $lastReceipt -Force
    } catch { Write-HelperLog 'receipt_failed' }
}
if ($result.state -eq 'success') { exit 0 }
exit 1
'''


def _launch_helper(script):
    # An absolute system PowerShell path, never PATH resolution or shell=True.
    # DETACHED_PROCESS (0x8) is NOT usable here: PowerShell fails to start without
    # a console and exits silently (verified 24.11.26). CREATE_NO_WINDOW keeps it
    # hidden and CREATE_NEW_PROCESS_GROUP detaches it from our console signals.
    return subprocess.Popen(
        [str(_powershell_path()), "-NoLogo", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=str(script.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, shell=False, close_fds=True,
        creationflags=0x00000200 | 0x08000000)


def _prune_updates_dir(directory):
    """Bounded cleanup: newest installer, recent logs, no stale partial files."""
    try:
        entries = [p for p in directory.iterdir() if p.is_file()]
    except OSError:
        return
    now = time.time()
    installers = sorted((p for p in entries if re.fullmatch(r"PlannerTaTe_Setup_[0-9.]+\.exe", p.name)),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for old in installers[1:]:
        try:
            old.unlink()
        except OSError:
            pass
    for p in entries:
        try:
            if p.suffix == ".part" or p.suffix == ".ps1":
                if now - p.stat().st_mtime > 7 * 86400:
                    p.unlink()
        except OSError:
            pass
    for pattern in ("*.helper.log", "*.inno.log", "*.result.json"):
        logs = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in logs[20:]:
            try:
                old.unlink()
            except OSError:
                pass


class UpdateManager:
    def __init__(self, data_dir, installed_exe=None, on_exit=None):
        self.data_dir = Path(data_dir).resolve()
        self.updates_dir = self.data_dir / "updates"
        self._download_path = None
        self._download_thread = None
        self.installed_exe = installed_exe
        self.on_exit = on_exit
        self._lock = threading.RLock()
        self._release = None
        self._app_cache = {}
        self._app_inflight = set()
        self._status = dict(state="idle", current_version=APP_VERSION,
                            latest_version=None, available=False,
                            download_size=0, downloaded=0, error=None,
                            release_url=f"{REPO_URL}/releases/latest",
                            can_install=False)

    def set_exit_callback(self, callback):
        """Register/clear Qt signal.emit after Qt starts; never call Qt directly here."""
        if callback is not None and not callable(callback):
            raise TypeError("exit callback must be callable or None")
        with self._lock:
            if self._status["state"] == "installing":
                raise UpdateError("busy", 409)
            self.on_exit = callback

    def status(self):
        target = _installed_target(self.installed_exe)
        with self._lock:
            result = dict(self._status)
            result["can_install"] = target is not None and callable(self.on_exit)
            return result

    def last_install(self):
        """Receipt of the last installation attempt; never trusted for decisions."""
        try:
            data = json.loads((self.updates_dir / "last-result.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return {key: data.get(key) for key in
                ("state", "error", "version", "installer_exit_code", "restarted", "timestamp")}

    def _fail(self, code):
        with self._lock:
            self._status.update(state="error", error=code)

    def app_download_url(self, app_id):
        if app_id not in _APP_REPOS:
            raise UpdateError("unknown_app", 404)
        repo, pattern = _APP_REPOS[app_id]
        fallback = f"https://github.com/{repo}/releases/latest"
        with self._lock:
            cached = self._app_cache.get(app_id)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            if app_id in self._app_inflight:
                return fallback
            self._app_inflight.add(app_id)
        url = fallback
        try:
            payload = _latest_release(repo)
            if not payload["draft"] and not payload["prerelease"]:
                version, _ = _version(payload.get("tag_name"))
                name = pattern.format(version=version)
                expected = f"https://github.com/{repo}/releases/download/{payload['tag_name']}/{name}"
                assets = payload.get("assets", [])
                if isinstance(assets, list):
                    matching = [asset for asset in assets if isinstance(asset, dict) and
                                asset.get("name") == name and asset.get("browser_download_url") == expected]
                    if len(matching) == 1:
                        url = expected
        except Exception:
            pass  # The fixed releases page remains useful when anonymous API is rate-limited.
        finally:
            with self._lock:
                self._app_cache[app_id] = (time.monotonic() + APP_LINK_CACHE_SECONDS, url)
                self._app_inflight.discard(app_id)
        return url

    def install(self):
        target = _installed_target(self.installed_exe)
        with self._lock:
            if self._status["state"] == "installing":
                raise UpdateError("busy", 409)
            if self._status["state"] != "ready" or self._release is None or self._download_path is None:
                raise UpdateError("update_not_ready", 409)
            if target is None or not callable(self.on_exit):
                raise UpdateError("install_unavailable", 409)
            callback, release, installer = self.on_exit, self._release, self._download_path
            self._status.update(state="installing", error=None)
        try:
            if _version(release.version)[1] <= _version(APP_VERSION)[1]:
                raise UpdateError("downgrade_forbidden")
            directory = _ensure_updates_dir(self.data_dir)
            if installer.parent != directory or installer.name != release.name:
                raise UpdateError("unsafe_update_directory")
            _verify_file(installer, release)
            worker_pid, parent_pid = os.getpid(), os.getppid()
            worker = _process_identity(worker_pid)
            if worker is None or Path(worker[0]).resolve() != target:
                raise UpdateError("process_identity_failed", 500)
            processes = [(worker_pid, worker[1])]
            parent = _process_identity(parent_pid)
            if parent is not None and Path(parent[0]).resolve() == target and parent_pid != worker_pid:
                processes.append((parent_pid, parent[1]))
            identifier = "update-" + uuid.uuid4().hex
            script = directory / f"{identifier}.ps1"
            content = _render_helper(release, installer, target, processes,
                                     directory / f"{identifier}.helper.log",
                                     directory / f"{identifier}.inno.log",
                                     directory / f"{identifier}.result.json")
            with script.open("x", encoding="utf-8-sig", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                _launch_helper(script)
            except Exception:
                raise UpdateError("helper_launch_failed", 500) from None
            # Freeze the selected callback for this operation. Qt's signal.emit
            # marshals quit to the main thread; never invoke quit synchronously.
            def exit_application():
                try:
                    callback()
                except Exception:
                    self._fail("exit_callback_failed")
            self._exit_timer = threading.Timer(1.0, exit_application)
            self._exit_timer.daemon = True
            self._exit_timer.start()
        except Exception as exc:
            error = exc if isinstance(exc, UpdateError) else UpdateError("file_error", 500)
            self._fail(error.code)
            raise error from None
        return self.status()

    def download(self):
        install_target = _installed_target(self.installed_exe)
        with self._lock:
            if self._status["state"] in ("checking", "downloading", "ready", "installing"):
                raise UpdateError("busy", 409)
            if self._status["state"] != "available" or self._release is None:
                raise UpdateError("update_not_available", 409)
            release = self._release
            self._download_path = None
            self._status.update(state="downloading", error=None, downloaded=0)
            self._download_thread = threading.Thread(target=self._download, args=(release,),
                                                     name="PlannerTaTe-download", daemon=True)
            response = dict(self._status)
            response["can_install"] = install_target is not None and callable(self.on_exit)
        try:
            self._download_thread.start()
        except RuntimeError:
            self._fail("download_start_failed")
            raise UpdateError("download_start_failed", 500) from None
        return response

    def _download(self, release):
        part = None
        try:
            directory = _ensure_updates_dir(self.data_dir)
            _prune_updates_dir(directory)
            target = directory / release.name
            part = directory / f"{release.name}.{uuid.uuid4().hex}.part"
            digest, prefix, downloaded = hashlib.sha256(), bytearray(), 0
            deadline = time.monotonic() + 15 * 60
            with _open_response(release.url, lambda url: _asset_redirect_allowed(url, release.url),
                                deadline) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None and (not str(content_length).isascii() or
                        not str(content_length).isdigit() or int(content_length) != release.size):
                    raise UpdateError("size_mismatch")
                if response.headers.get("Content-Encoding", "identity").strip().lower() not in ("", "identity"):
                    raise UpdateError("invalid_encoding")
                with part.open("xb") as stream:
                    while chunk := _read_chunk(response, CHUNK_SIZE, deadline):
                        downloaded += len(chunk)
                        if downloaded > release.size or downloaded > MAX_DOWNLOAD_SIZE:
                            raise UpdateError("size_mismatch")
                        prefix.extend(chunk[:max(0, 2 - len(prefix))])
                        if len(prefix) == 2 and prefix != b"MZ":
                            raise UpdateError("invalid_executable")
                        stream.write(chunk)
                        digest.update(chunk)
                        with self._lock:
                            self._status["downloaded"] = downloaded
                    stream.flush()
                    os.fsync(stream.fileno())
            if downloaded != release.size:
                raise UpdateError("size_mismatch")
            if not hmac.compare_digest(digest.hexdigest(), release.sha256):
                raise UpdateError("hash_mismatch")
            if target.is_symlink() or target.resolve().parent != directory:
                raise UpdateError("unsafe_update_directory")
            os.replace(part, target)
            with self._lock:
                self._download_path = target
                self._status.update(state="ready", error=None)
        except Exception as exc:
            network_errors = (URLError, HTTPError, ssl.SSLError, TimeoutError, ConnectionError, socket.gaierror)
            self._fail(exc.code if isinstance(exc, UpdateError) else
                       "file_error" if isinstance(exc, OSError) and not isinstance(exc, network_errors)
                       else _error_code(exc))
        finally:
            if part is not None:
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass

    def check(self):
        with self._lock:
            if self._status["state"] in ("checking", "downloading", "ready", "installing"):
                raise UpdateError("busy", 409)
            self._release = None
            self._status.update(state="checking", error=None, available=False,
                                latest_version=None, download_size=0, downloaded=0)
        try:
            release, latest = _select_release(_latest_release(REPO))
            with self._lock:
                self._release = release
                self._status.update(state="available" if release else "current", latest_version=latest,
                                    available=bool(release), download_size=release.size if release else 0,
                                    release_url=f"{REPO_URL}/releases/tag/{release.tag}" if release else
                                                f"{REPO_URL}/releases/latest")
        except Exception as exc:
            self._fail(_error_code(exc))
        return self.status()


def register_updates(app, data_dir, installed_exe=None, on_exit=None):
    """Register once before Flask serves requests; no startup I/O or network."""
    manager = UpdateManager(data_dir, installed_exe, on_exit)
    blueprint = Blueprint("plannertate_updates", __name__)

    @blueprint.before_request
    def guard():
        _guard_local()

    @blueprint.errorhandler(UpdateError)
    def update_error(exc):
        result = manager.status()
        result["error"] = exc.code
        return jsonify(result), exc.http_status

    @blueprint.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @blueprint.get("/api/about")
    def about():
        return jsonify(name="PlannerTaTe", repo_url=REPO_URL,
                       last_install=manager.last_install(), **manager.status())

    @blueprint.get("/api/updates/status")
    def status():
        return jsonify(manager.status())

    @blueprint.post("/api/updates/check")
    def check():
        return jsonify(manager.check())

    @blueprint.post("/api/updates/download")
    def download():
        return jsonify(manager.download()), 202

    @blueprint.post("/api/updates/install")
    def install():
        return jsonify(manager.install()), 202

    @blueprint.get("/api/apps/<app_id>/download")
    def app_download(app_id):
        if request.args:
            raise UpdateError("invalid_request")
        return redirect(manager.app_download_url(app_id), code=302)

    app.register_blueprint(blueprint)
    app.extensions["plannertate_updates"] = manager
    return manager

"""Offline updater tests: GitHub and process fixtures are NOT live results.

Never run an installer or exit the user's application. Temporary files stay in
Hermes scratch (or TMPDIR on other machines); no application data is loaded.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import socket
import ssl
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from flask import Flask

SCRATCH = (Path.home() / "AppData/Local/hermes/cache/scratch" if os.name == "nt"
           else Path(os.environ.get("TMPDIR", tempfile.gettempdir())))
SCRATCH.mkdir(parents=True, exist_ok=True)
REAL_POPEN_FOR_SAFE_POWERSHELL_TESTS = subprocess.Popen
CLIENT_HEADER = {"X-Plannertate-Client": "1"}
FIXTURE_BINARY = b"MZ" + b"OFFLINE-TEST-NOT-AN-INSTALLER" * 13


def github_release_fixture(version="1.12", repo="yaroslav-softcode/PlannerTaTe",
                           name=None):
    """Fabricated metadata solely for exercising the GitHub trust boundary."""
    tag = "v" + version
    name = name or f"PlannerTaTe_Setup_{version}.exe"
    return {"tag_name": tag, "draft": False, "prerelease": False,
            "html_url": f"https://github.com/{repo}/releases/tag/{tag}",
            "assets": [{"name": name, "size": len(FIXTURE_BINARY),
                        "digest": "sha256:" + hashlib.sha256(FIXTURE_BINARY).hexdigest(),
                        "browser_download_url":
                            f"https://github.com/{repo}/releases/download/{tag}/{name}"}]}


class FakeResponse(io.BytesIO):
    def __init__(self, content, url, headers=None, status=200):
        super().__init__(content)
        self.url = url
        self.headers = headers or {}
        self.status = status

    def geturl(self):
        return self.url


class FakeOpener:
    """Offline FIFO fixture; an unexpected request fails rather than networking."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if not self.responses:
            raise AssertionError("Unexpected network call in offline fixture")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(request)
        return response


def api_fixture(payload, repo="yaroslav-softcode/PlannerTaTe"):
    return FakeResponse(json.dumps(payload).encode(),
                        f"https://api.github.com/repos/{repo}/releases/latest")


def html_release_fixtures(version="1.12", repo="yaroslav-softcode/PlannerTaTe", name=None,
                          digest=None, bad_label=False):
    """Synthetic fixture, using the observed official expanded_assets HTML shape."""
    name = name or f"PlannerTaTe_Setup_{version}.exe"
    digest = digest if digest is not None else "sha256:" + hashlib.sha256(FIXTURE_BINARY).hexdigest()
    tag = "v" + version
    latest = FakeResponse(b'<html><span class="Label Label--success">Latest</span></html>',
                          f"https://github.com/{repo}/releases/tag/{tag}")
    # A preceding APK row must never donate its digest to the EXE row.
    fragment = (f'<ul><li><a href="/{repo}/releases/download/{tag}/PlannerTaTe.apk">APK</a>'
                f'<clipboard-copy aria-label="Copy to clipboard digest for PlannerTaTe.apk" '
                f'value="sha256:{"0" * 64}"></clipboard-copy><span>1 MB</span></li>'
                f'<li class="Box-row d-flex flex-column flex-md-row">'
                f'<div><a href="/{repo}/releases/download/{tag}/{name}" rel="nofollow">'
                f'<span class="text-bold">{name}</span></a></div><div>'
                f'<span class="Truncate-text">{digest}</span>'
                f'<clipboard-copy aria-label="Copy to clipboard digest for {"wrong.exe" if bad_label else name}" '
                f'value="{digest}"></clipboard-copy><span class="color-fg-muted">55.3 MB</span>'
                f'<relative-time datetime="2026-11-14T16:36:02Z"></relative-time></div></li></ul>')
    assets = FakeResponse(fragment.encode(), f"https://github.com/{repo}/releases/expanded_assets/{tag}")
    head = FakeResponse(b"", "https://release-assets.githubusercontent.com/fixture/asset",
                        {"Content-Length": str(len(FIXTURE_BINARY))})
    return latest, assets, head


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="updates-test-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spawn_guard = patch("subprocess.Popen", side_effect=AssertionError(
            "An offline test must not spawn an installer/helper"))
        self.spawn_guard.start()
        self.addCleanup(self.spawn_guard.stop)
        # Tests are written against a fixed baseline version so that a shipped
        # version bump (1.11 -> 1.12 -> ...) never rewrites every expectation.
        module = importlib.import_module("plannertate_updates")
        self.version_patch = patch.object(module, "APP_VERSION", "1.11")
        self.version_patch.start()
        self.addCleanup(self.version_patch.stop)

    def module(self):
        try:
            return importlib.import_module("plannertate_updates")
        except ModuleNotFoundError:
            self.fail("Missing updater module: implement register_updates")

    def make_app(self, *responses, installed_exe=None, on_exit=None):
        module = self.module()
        opener = FakeOpener(*responses)
        factory = patch.object(module, "_make_opener", return_value=opener, create=True)
        factory.start()
        self.addCleanup(factory.stop)
        app = Flask(__name__)
        app.testing = True
        manager = module.register_updates(app, self.root / "data", installed_exe, on_exit)

        def join_fixture_download():
            thread = manager._download_thread
            if thread is not None and thread.ident is not None:
                thread.join(4)
                self.assertFalse(thread.is_alive(), "offline fixture left a download thread")
        self.addCleanup(join_fixture_download)
        return module, manager, app.test_client(), opener

    def check(self, client, **kwargs):
        return client.post("/api/updates/check", headers=CLIENT_HEADER, **kwargs)

    def test_local_check_validates_github_asset_before_offering_update(self):
        module, manager, client, opener = self.make_app(api_fixture(github_release_fixture()))
        response = self.check(client)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["state"], "available")
        self.assertEqual(result["latest_version"], "1.12")
        self.assertTrue(result["available"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["download_size"], len(FIXTURE_BINARY))
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url,
                         "https://api.github.com/repos/yaroslav-softcode/PlannerTaTe/releases/latest")
        self.assertIn("application/vnd.github+json", request.get_header("Accept"))
        self.assertIn("PlannerTaTe", request.get_header("User-agent"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 15)
        self.assertFalse((self.root / "data").exists())

    def test_every_updater_route_requires_loopback_peer_and_host(self):
        _, _, client, opener = self.make_app()
        for endpoint in ("/api/about", "/api/updates/status", "/api/updates/check",
                         "/api/updates/download", "/api/updates/install", "/api/apps/fair/download"):
            method = client.post if endpoint in ("/api/updates/check", "/api/updates/download",
                                                "/api/updates/install") else client.get
            for host, peer in (("evil.example", "127.0.0.1"),
                               ("localhost", "192.168.1.99"),
                               ("127.0.0.1.evil.example", "127.0.0.1"),
                               ("localhost@evil.example", "127.0.0.1")):
                with self.subTest(endpoint=endpoint, host=host, peer=peer):
                    response = method(endpoint, headers={**CLIENT_HEADER, "Host": host},
                                      environ_overrides={"REMOTE_ADDR": peer})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.get_json()["error"], "local_only")
        self.assertFalse(opener.calls)

    def test_check_rejects_csrf_and_client_payload_without_network(self):
        _, _, client, opener = self.make_app()
        cases = [({}, {}, "client_header_required", 403),
                 ({**CLIENT_HEADER, "Origin": "https://evil.example"}, {}, "origin_forbidden", 403),
                 ({**CLIENT_HEADER, "Origin": "null"}, {}, "origin_forbidden", 403),
                 ({**CLIENT_HEADER, "Origin": "http://localhost:99"}, {}, "origin_forbidden", 403),
                 ({**CLIENT_HEADER, "Sec-Fetch-Site": "cross-site"}, {}, "cross_site_forbidden", 403),
                 (CLIENT_HEADER, {"json": {"url": "https://evil.example/payload.exe"}}, "invalid_request", 400),
                 (CLIENT_HEADER, {"json": {"path": "C:/arbitrary.exe", "pid": 1}}, "invalid_request", 400),
                 (CLIENT_HEADER, {"query_string": "url=evil"}, "invalid_request", 400)]
        for headers, kwargs, error, code in cases:
            with self.subTest(error=error, kwargs=kwargs):
                response = client.post("/api/updates/check", headers=headers, **kwargs)
                self.assertEqual(response.status_code, code)
                self.assertEqual(response.get_json()["error"], error)
        self.assertFalse(opener.calls)

    def test_same_origin_and_ipv6_loopback_are_allowed(self):
        _, _, client, _ = self.make_app(api_fixture(github_release_fixture("1.10")))
        response = client.post("/api/updates/check", base_url="http://[::1]:49999",
                               environ_overrides={"REMOTE_ADDR": "::1"},
                               headers={**CLIENT_HEADER, "Origin": "http://[::1]:49999",
                                        "Sec-Fetch-Site": "same-origin"}, json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["state"], "current")

    def test_numeric_versions_never_offer_same_version_or_downgrade(self):
        for version, state in (("1.9", "current"), ("1.10", "current"),
                               ("1.11", "current"), ("1.11.0", "current"),
                               ("1.12", "available"), ("1.100", "available"),
                               ("2.0", "available")):
            with self.subTest(version=version):
                _, _, client, _ = self.make_app(api_fixture(github_release_fixture(version)))
                result = self.check(client).get_json()
                self.assertEqual(result["state"], state)
                self.assertEqual(result["available"], state == "available")

    def test_release_metadata_fail_closed(self):
        cases = []
        for key in ("draft", "prerelease"):
            fixture = github_release_fixture()
            fixture[key] = True
            cases.append((fixture, "current", None))
        for tag in ("v2.0-rc1", "v../evil", "v1.12.exe", "v1", " v1.12"):
            fixture = github_release_fixture()
            fixture["tag_name"] = tag
            cases.append((fixture, "error", "invalid_version"))
        for changes, error in (({"name": "OTHER.exe"}, "asset_not_found"),
                               ({"size": 0}, "invalid_size"),
                               ({"size": 536870913}, "invalid_size"),
                               ({"size": True}, "invalid_size"),
                               ({"digest": None}, "missing_digest"),
                               ({"digest": "sha256:" + "z" * 64}, "invalid_digest"),
                               ({"browser_download_url": "http://github.com/evil.exe"}, "invalid_asset_url"),
                               ({"browser_download_url": "https://github.com/other/repo/releases/download/v1.12/PlannerTaTe_Setup_1.12.exe"}, "invalid_asset_url")):
            fixture = github_release_fixture()
            fixture["assets"][0].update(changes)
            cases.append((fixture, "error", error))
        for fixture, state, error in cases:
            with self.subTest(state=state, error=error, fixture=fixture):
                _, _, client, _ = self.make_app(api_fixture(fixture))
                result = self.check(client).get_json()
                self.assertEqual(result["state"], state)
                self.assertEqual(result["error"], error)
                self.assertFalse(result["available"])

    def test_network_and_response_errors_are_safe_machine_codes(self):
        url = "https://api.github.com/"
        cases = [(URLError("secret/file/path"), "network_error"),
                 (socket.timeout("secret timeout"), "network_timeout"),
                 (URLError(ssl.SSLCertVerificationError("secret cert")), "tls_error"),
                 (HTTPError(url, 403, "SECRET", {}, None), "rate_limited"),
                 (HTTPError(url, 404, "SECRET", {}, None), "release_not_found"),
                 (HTTPError(url, 500, "SECRET", {}, None), "http_error"),
                 (FakeResponse(b"<html>SECRET", url), "unsafe_redirect"),
                 (api_fixture([]), "invalid_response")]
        for fixture, error in cases:
            with self.subTest(error=error):
                _, _, client, _ = self.make_app(fixture)
                response = self.check(client)
                self.assertEqual(response.get_json()["state"], "error")
                self.assertEqual(response.get_json()["error"], error)
                self.assertNotIn("SECRET", response.get_data(as_text=True))
                self.assertNotIn("secret", response.get_data(as_text=True))

    def test_production_opener_enforces_tls_and_redirect_allowlist(self):
        module = self.module()
        self.assertTrue(hasattr(module, "_make_opener"), "Missing TLS/redirect-enforcing transport")
        opener = module._make_opener(lambda url: url == "https://github.com/good", 9999999999)
        redirect = next(handler for handler in opener.handlers
                        if isinstance(handler, module._SafeRedirectHandler))
        for bad in ("http://github.com/good", "https://evil.example/bad",
                    "file:///C:/payload.exe", "https://github.com.evil.example/good"):
            with self.subTest(url=bad):
                with self.assertRaises(module.UpdateError):
                    redirect.redirect_request(Request("https://github.com/good"),
                                              None, 302, "Found", {}, bad)
        self.assertTrue(any(isinstance(handler, module.HTTPSHandler) and
                            handler._context.verify_mode == ssl.CERT_REQUIRED and
                            handler._context.check_hostname for handler in opener.handlers))

    def finish_download(self, manager):
        deadline = time.monotonic() + 3
        while manager.status()["state"] == "downloading" and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertNotEqual(manager.status()["state"], "downloading", "offline download worker hung")
        if hasattr(manager, "_download_thread"):
            manager._download_thread.join(1)
        return manager.status()

    def test_download_streams_to_part_then_atomically_publishes_verified_exe(self):
        fixture = github_release_fixture()
        url = fixture["assets"][0]["browser_download_url"]
        module, manager, client, opener = self.make_app(
            api_fixture(fixture), FakeResponse(FIXTURE_BINARY, url,
                                               {"Content-Length": str(len(FIXTURE_BINARY))}))
        self.check(client)
        original_replace = os.replace
        seen = []

        def observe_replace(source, destination):
            self.assertTrue(str(source).endswith(".part"))
            self.assertEqual(Path(source).read_bytes(), FIXTURE_BINARY)
            self.assertFalse(Path(destination).exists())
            seen.append((source, destination))
            return original_replace(source, destination)

        with patch.object(module.os, "replace", side_effect=observe_replace):
            response = client.post("/api/updates/download", headers=CLIENT_HEADER)
            self.assertEqual(response.status_code, 202)
            status = self.finish_download(manager)
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["downloaded"], len(FIXTURE_BINARY))
        self.assertEqual(len(seen), 1)
        self.assertEqual(list(manager.updates_dir.glob("*.part")), [])
        self.assertEqual(list(manager.updates_dir.glob("*.exe"))[0].read_bytes(), FIXTURE_BINARY)
        self.assertEqual(len(opener.calls), 2)

    def test_download_rejects_bad_bytes_sizes_and_untrusted_final_redirect(self):
        fixture = github_release_fixture()
        url = fixture["assets"][0]["browser_download_url"]
        cases = [(FIXTURE_BINARY[:-1], url, {}, "size_mismatch"),
                 (FIXTURE_BINARY + b"!", url, {}, "size_mismatch"),
                 (b"ZZ" + FIXTURE_BINARY[2:], url, {}, "invalid_executable"),
                 (b"MZ" + b"x" * (len(FIXTURE_BINARY) - 2), url, {}, "hash_mismatch"),
                 (FIXTURE_BINARY, url, {"Content-Length": "1"}, "size_mismatch"),
                 (FIXTURE_BINARY, url, {"Content-Length": "bad"}, "size_mismatch"),
                 (FIXTURE_BINARY, "http://github.com/unsafe", {}, "unsafe_redirect"),
                 (FIXTURE_BINARY, "https://evil.example/unsafe.exe", {}, "unsafe_redirect"),
                 (FIXTURE_BINARY, "https://github.com/other/repo/exe", {}, "unsafe_redirect")]
        for body, final_url, headers, error in cases:
            with self.subTest(error=error, final_url=final_url):
                _, manager, client, _ = self.make_app(api_fixture(fixture), FakeResponse(body, final_url, headers))
                self.check(client)
                response = client.post("/api/updates/download", headers=CLIENT_HEADER)
                self.assertEqual(response.status_code, 202)
                status = self.finish_download(manager)
                self.assertEqual(status["state"], "error")
                self.assertEqual(status["error"], error)
                self.assertFalse(list(manager.updates_dir.glob("*.exe")))
                self.assertFalse(list(manager.updates_dir.glob("*.part")))

    def test_download_accepts_only_exact_github_https_cdn_hosts(self):
        module = self.module()
        self.assertTrue(hasattr(module, "_asset_redirect_allowed"), "Missing download redirect policy")
        initial = github_release_fixture()["assets"][0]["browser_download_url"]
        for host in ("release-assets.githubusercontent.com", "objects.githubusercontent.com",
                     "github-releases.githubusercontent.com"):
            self.assertTrue(module._asset_redirect_allowed(f"https://{host}/fixture?signature=abc", initial))
        for url in ("https://release-assets.githubusercontent.com.evil.example/file",
                    "https://user:password@release-assets.githubusercontent.com/file",
                    "https://release-assets.githubusercontent.com:8443/file",
                    "https://github.com/other/repo/file", "http://objects.githubusercontent.com/file",
                    "https://api.github.com/file", "file:///C:/file.exe"):
            self.assertFalse(module._asset_redirect_allowed(url, initial), url)

    def test_download_no_network_lock_and_concurrent_operations_do_not_duplicate(self):
        fixture = github_release_fixture()
        entered, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)

        class BlockingDownload(FakeResponse):
            def read1(self, size):
                if self.tell() > 0:
                    entered.set()
                    if not resume.wait(2):
                        raise TimeoutError()
                return super().read1(min(size, 7))

        _, manager, client, opener = self.make_app(api_fixture(fixture), BlockingDownload(
            FIXTURE_BINARY, fixture["assets"][0]["browser_download_url"]))
        self.check(client)
        self.assertEqual(client.post("/api/updates/download", headers=CLIENT_HEADER).status_code, 202)
        self.assertTrue(entered.wait(1))
        acquired = manager._lock.acquire(timeout=0.2)
        self.assertTrue(acquired, "network read holds manager lock")
        if acquired:
            manager._lock.release()
        status = client.get("/api/updates/status").get_json()
        self.assertGreater(status["downloaded"], 0)
        self.assertLess(status["downloaded"], len(FIXTURE_BINARY))
        self.assertTrue(list(manager.updates_dir.glob("*.part")))
        self.assertFalse(list(manager.updates_dir.glob("*.exe")))
        for action in ("check", "download"):
            response = client.post(f"/api/updates/{action}", headers=CLIENT_HEADER)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.get_json()["error"], "busy")
        self.assertEqual(len(opener.calls), 2)
        resume.set()
        self.assertEqual(self.finish_download(manager)["state"], "ready")
        self.assertEqual(self.check(client).status_code, 409)

    def test_download_requires_available_and_csrf_header(self):
        _, manager, client, opener = self.make_app()
        self.assertEqual(client.post("/api/updates/download").status_code, 403)
        response = client.post("/api/updates/download", headers=CLIENT_HEADER)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "update_not_available")
        self.assertFalse(opener.calls)
        self.assertFalse((self.root / "data").exists())

    def test_check_does_not_duplicate_while_first_request_is_inflight(self):
        entered, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)

        def blocked(request):
            entered.set()
            resume.wait(2)
            return api_fixture(github_release_fixture())

        _, manager, client, opener = self.make_app(blocked)
        thread = threading.Thread(target=manager.check)
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(manager.status()["state"], "checking")
        response = self.check(client)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "busy")
        self.assertEqual(len(opener.calls), 1)
        resume.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(manager.status()["state"], "available")

    def installed_fixture(self, name="PlannerTaTe.exe"):
        directory = self.root / "Installed App fixture"
        directory.mkdir(exist_ok=True)
        exe = directory / name
        exe.write_bytes(FIXTURE_BINARY)
        (directory / "unins000.exe").write_bytes(b"NOT-A-REAL-UNINSTALLER")
        for target, value, create in (("sys.frozen", True, True),
                                      ("sys.executable", str(exe), False),
                                      ("sys.platform", "win32", False)):
            patcher = patch(target, value, create=create)
            patcher.start()
            self.addCleanup(patcher.stop)
        return exe

    def ready_fixture(self):
        exe = self.installed_fixture()
        fixture = github_release_fixture()
        module, manager, client, opener = self.make_app(api_fixture(fixture),
            FakeResponse(FIXTURE_BINARY, fixture["assets"][0]["browser_download_url"]), installed_exe=exe)
        callback = Mock(name="fake_Qt_signal_emit_does_not_exit")
        self.assertTrue(hasattr(manager, "set_exit_callback"), "Missing late Qt callback setter")
        manager.set_exit_callback(callback)
        self.check(client)
        self.assertEqual(client.post("/api/updates/download", headers=CLIENT_HEADER).status_code, 202)
        self.assertEqual(self.finish_download(manager)["state"], "ready")
        return module, manager, client, callback, exe

    def test_can_install_requires_frozen_current_installed_exe_and_late_exit_callback(self):
        exe = self.installed_fixture()
        module, manager, client, _ = self.make_app(installed_exe=exe)
        self.assertFalse(client.get("/api/about").get_json()["can_install"])
        self.assertTrue(hasattr(manager, "set_exit_callback"), "Missing thread-safe setter")
        manager.set_exit_callback(Mock())
        self.assertTrue(client.get("/api/about").get_json()["can_install"])
        self.assertTrue(client.get("/api/updates/status").get_json()["can_install"])
        manager.set_exit_callback(None)
        self.assertFalse(manager.status()["can_install"])
        with self.assertRaises(TypeError):
            manager.set_exit_callback("not callable")
        manager.set_exit_callback(Mock())
        with patch.object(sys, "frozen", False):
            self.assertFalse(manager.status()["can_install"])
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(manager.status()["can_install"])
        with patch.object(sys, "executable", str(exe.parent / "python.exe")):
            self.assertFalse(manager.status()["can_install"])
        (exe.parent / "unins000.exe").unlink()
        self.assertFalse(manager.status()["can_install"])

    def test_python_exe_is_never_an_install_target_even_with_frozen_flag(self):
        exe = self.installed_fixture("python.exe")
        _, manager, _, _ = self.make_app(installed_exe=exe, on_exit=Mock())
        self.assertFalse(manager.status()["can_install"])

    def test_install_reverifies_file_before_any_process_or_exit(self):
        for corruption, error in ((FIXTURE_BINARY[:-1], "size_mismatch"),
                                  (b"MZ" + b"x" * (len(FIXTURE_BINARY) - 2), "hash_mismatch"),
                                  (b"ZZ" + FIXTURE_BINARY[2:], "invalid_executable")):
            with self.subTest(error=error):
                _, manager, client, callback, _ = self.ready_fixture()
                next(manager.updates_dir.glob("*.exe")).write_bytes(corruption)
                response = client.post("/api/updates/install", headers=CLIENT_HEADER)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], error)
                self.assertEqual(manager.status()["state"], "error")
                callback.assert_not_called()
                self.assertFalse(list(manager.updates_dir.glob("*.ps1")))
                # Each subcase starts from a clean artifact directory.
                next(manager.updates_dir.glob("*.exe")).unlink()

    def test_install_requires_ready_callback_and_csrf_no_client_path_pid(self):
        _, manager, client, callback, _ = self.ready_fixture()
        for kwargs, status in (({}, 403), ({"headers": CLIENT_HEADER, "json": {"pid": 1}}, 400)):
            self.assertEqual(client.post("/api/updates/install", **kwargs).status_code, status)
        manager.set_exit_callback(None)
        response = client.post("/api/updates/install", headers=CLIENT_HEADER)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "install_unavailable")
        callback.assert_not_called()
        _, _, idle, _ = self.make_app()
        response = idle.post("/api/updates/install", headers=CLIENT_HEADER)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "update_not_ready")

    def test_helper_does_not_inherit_pyinstaller_child_markers(self):
        module = self.module()
        ps1 = self.root / "update.ps1"
        ps1.write_text("# noop", encoding="utf-8")
        with patch.dict("os.environ", {"_PYI_APPLICATION_HOME_DIR": "C:/tmp/_MEI1",
                                       "_PYI_PARENT_PROCESS_LEVEL": "1", "PLANNERTATE_KEEP": "yes"}), \
             patch.object(module, "_powershell_path", return_value=Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")), \
             patch.object(module.subprocess, "Popen") as spawn:
            module._launch_helper(ps1)
        environment = spawn.call_args.kwargs["env"]
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", environment)
        self.assertNotIn("_PYI_PARENT_PROCESS_LEVEL", environment)
        self.assertEqual(environment.get("PLANNERTATE_KEEP"), "yes")

    def test_install_spawns_only_detached_powershell_then_defers_callback(self):
        module, manager, client, callback, exe = self.ready_fixture()
        fake_timer = Mock(name="fake_timer_no_exit")
        fake_process = Mock(name="fake_helper_process_no_execution")
        worker_pid, bootstrap_pid = 424242, 424241
        identities = {worker_pid: (str(exe), 123400000000), bootstrap_pid: (str(exe), 123399999999)}
        with patch.object(module.os, "getpid", return_value=worker_pid), \
             patch.object(module.os, "getppid", return_value=bootstrap_pid), \
             patch.object(module, "_process_identity", side_effect=identities.get), \
             patch.object(module.subprocess, "Popen", return_value=fake_process) as spawn, \
             patch.object(module.threading, "Timer", return_value=fake_timer) as timer:
            response = client.post("/api/updates/install", headers=CLIENT_HEADER)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.get_json()["state"], "installing")
            callback.assert_not_called()
            spawn.assert_called_once()
            argv = spawn.call_args.args[0]
            self.assertEqual(Path(argv[0]).name.lower(), "powershell.exe")
            self.assertIn("-File", argv)
            script = Path(argv[argv.index("-File") + 1])
            self.assertEqual(script.parent, manager.updates_dir)
            self.assertTrue(script.read_bytes().startswith(b"\xef\xbb\xbf"))
            content = script.read_text(encoding="utf-8-sig")
            for required in ("424242", "424241", "123400000000", "123399999999",
                             "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=", "/LOG=",
                             "WaitForExit", "wait_timeout", "hash_mismatch", "size_mismatch", "3010", "result.json"):
                self.assertIn(required, content)
            for forbidden in ("taskkill", "Stop-Process", "--quiet", "Invoke-Expression"):
                self.assertNotIn(forbidden, content)
            self.assertFalse(spawn.call_args.kwargs["shell"])
            self.assertTrue(spawn.call_args.kwargs["close_fds"])
            flags = spawn.call_args.kwargs["creationflags"]
            # DETACHED_PROCESS makes PowerShell exit before doing any work.
            self.assertFalse(flags & 0x00000008, "DETACHED_PROCESS breaks the helper")
            self.assertTrue(flags & 0x00000200)
            self.assertTrue(flags & 0x08000000)
            self.assertEqual(timer.call_args.args[0], 1.0)
            self.assertTrue(fake_timer.daemon)
            fake_timer.start.assert_called_once()
            timer.call_args.args[1]()
            callback.assert_called_once_with()
            # Even while the timer has not really exited the app, no second spawn.
            self.assertEqual(client.post("/api/updates/install", headers=CLIENT_HEADER).status_code, 409)
            self.assertEqual(self.check(client).status_code, 409)
            self.assertEqual(client.post("/api/updates/download", headers=CLIENT_HEADER).status_code, 409)
            spawn.assert_called_once()

    def test_helper_spawn_failure_never_exits_application(self):
        module, manager, client, callback, exe = self.ready_fixture()
        with patch.object(module, "_process_identity", return_value=(str(exe), 12345)), \
             patch.object(module.subprocess, "Popen", side_effect=OSError("PRIVATE-PATH")), \
             patch.object(module.threading, "Timer") as timer:
            response = client.post("/api/updates/install", headers=CLIENT_HEADER)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.get_json()["error"], "helper_launch_failed")
            self.assertNotIn("PRIVATE-PATH", response.get_data(as_text=True))
            callback.assert_not_called()
            timer.assert_not_called()

    def test_app_download_fixed_repos_and_five_minute_cache(self):
        for app_id, repo, name in (("fair", "yaroslav-softcode/FAIR", "FAIR-Setup-2.0.exe"),
                                   ("pastepen", "yaroslav-softcode/paste-pen", "PastePen_v2.0.exe")):
            with self.subTest(app_id=app_id):
                fixture = github_release_fixture("2.0", repo=repo, name=name)
                module, manager, client, opener = self.make_app(api_fixture(fixture, repo), api_fixture(fixture, repo))
                with patch.object(module.time, "monotonic", return_value=1000):
                    response = client.get(f"/api/apps/{app_id}/download")
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location, fixture["assets"][0]["browser_download_url"])
                    self.assertEqual(opener.calls[0][0].full_url,
                                     f"https://api.github.com/repos/{repo}/releases/latest")
                with patch.object(module.time, "monotonic", return_value=1299):
                    self.assertEqual(client.get(f"/api/apps/{app_id}/download").location, response.location)
                    self.assertEqual(len(opener.calls), 1)
                with patch.object(module.time, "monotonic", return_value=1301):
                    self.assertEqual(client.get(f"/api/apps/{app_id}/download").location, response.location)
                    self.assertEqual(len(opener.calls), 2)
                self.assertEqual(manager.status()["state"], "idle")
                self.assertFalse((self.root / "data").exists())

    def test_app_download_network_failure_or_wrong_asset_uses_fixed_release_fallback(self):
        repo = "yaroslav-softcode/FAIR"
        cases = [URLError("offline fixture"),
                 api_fixture(github_release_fixture("2.0", repo, name="surprise.exe"), repo)]
        for fixture in cases:
            with self.subTest(fixture=type(fixture).__name__):
                _, _, client, opener = self.make_app(fixture)
                response = client.get("/api/apps/fair/download")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, f"https://github.com/{repo}/releases/latest")
                self.assertEqual(client.get("/api/apps/fair/download").location, response.location)
                self.assertEqual(len(opener.calls), 1)

    def test_app_download_never_accepts_unknown_ids_urls_or_foreign_assets(self):
        _, _, client, opener = self.make_app()
        for app_id in ("not-an-app", "FAIR", "paste-pen", "https:evil.example"):
            self.assertEqual(client.get(f"/api/apps/{app_id}/download").status_code, 404)
        self.assertEqual(client.get("/api/apps/fair/download?url=https://evil.example").status_code, 400)
        self.assertFalse(opener.calls)
        fixture = github_release_fixture("2.0", "yaroslav-softcode/FAIR", "FAIR-Setup-2.0.exe")
        fixture["assets"][0]["browser_download_url"] = "https://github.com/evil/FAIR/releases/download/v2.0/FAIR-Setup-2.0.exe"
        _, _, client, _ = self.make_app(api_fixture(fixture, "yaroslav-softcode/FAIR"))
        self.assertEqual(client.get("/api/apps/fair/download").location,
                         "https://github.com/yaroslav-softcode/FAIR/releases/latest")

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell syntax parser")
    def test_generated_helper_is_parsed_by_real_powershell_without_execution(self):
        module = self.module()
        release, _ = module._select_release(github_release_fixture())
        # Special-character paths test quoting. No file at these paths is executed.
        directory = self.root / "Unicode \u041f\u0430\u043f\u043a\u0430 O'Hara $(not-a-command)"
        directory.mkdir()
        helper = directory / "helper.ps1"
        helper.write_text(module._render_helper(release, directory / release.name,
            directory / "PlannerTaTe.exe", [(99999999, 123456)], directory / "helper.log",
            directory / "inno.log", directory / "fixture.result.json"), encoding="utf-8-sig")
        parser = directory / "parse-only.ps1"
        parser.write_text("$tokens=$null; $errors=$null\n"
            "[void][System.Management.Automation.Language.Parser]::ParseFile(" +
            module._ps_literal(helper) + ", [ref]$tokens, [ref]$errors)\n"
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { [Console]::WriteLine($_.Message) }; exit 1 }\n"
            "[Console]::WriteLine('PS_SYNTAX_ERRORS=0')\n", encoding="utf-8-sig")
        # Exception to the spawn guard: this script only parses another file.
        with patch.object(subprocess, "Popen", REAL_POPEN_FOR_SAFE_POWERSHELL_TESTS):
            result = subprocess.run([str(module._powershell_path()), "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(parser)],
                capture_output=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"PS_SYNTAX_ERRORS=0", result.stdout)
        self.assertFalse(list(directory.glob("*.log")))
        self.assertFalse(list(directory.glob("*.json")))

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell offline fixture harness")
    def test_powershell_helper_receipts_with_fake_start_process_never_runs_installer(self):
        module = self.module()
        release, _ = module._select_release(github_release_fixture())
        cases = [(0, FIXTURE_BINARY, "success", None),
                 (3010, FIXTURE_BINARY, "success", None),
                 (5, FIXTURE_BINARY, "error", "installer_failed"),
                 (0, FIXTURE_BINARY[:-1], "error", "size_mismatch"),
                 (0, b"ZZ" + FIXTURE_BINARY[2:], "error", "invalid_executable"),
                 (0, b"MZ" + b"x" * (len(FIXTURE_BINARY) - 2), "error", "hash_mismatch")]
        for index, (exit_code, body, state, error) in enumerate(cases):
            with self.subTest(exit_code=exit_code, error=error):
                directory = self.root / f"PS fixture {index}"
                directory.mkdir()
                installer = directory / release.name
                installer.write_bytes(body)
                installed = directory / "PlannerTaTe.exe"
                installed.write_bytes(b"FAKE-APPLICATION-NEVER-EXECUTED")
                calls_file = directory / "fake-spawn-calls.jsonl"
                receipt = directory / "fixture.result.json"
                script = directory / "fixture-helper-with-fake-processes.ps1"
                fake_spawn = r'''
# OFFLINE TEST ONLY: shadow Start-Process. No child exe is ever launched.
function Start-Process {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory, [switch]$PassThru)
    $record = @{ file = $FilePath; arguments = @($ArgumentList); directory = $WorkingDirectory }
    Add-Content -LiteralPath $script:fixtureCalls -Value ($record | ConvertTo-Json -Compress) -Encoding UTF8
    $fakeProcess = [pscustomobject]@{ ExitCode = $script:fixtureExitCode }
    $fakeProcess | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { param($milliseconds) return $true }
    $fakeProcess | Add-Member -MemberType ScriptMethod -Name Dispose -Value {}
    return $fakeProcess
}
'''
                fake_spawn = (f"$script:fixtureExitCode = {exit_code}\n"
                              f"$script:fixtureCalls = {module._ps_literal(calls_file)}\n" + fake_spawn)
                helper = module._render_helper(release, installer, installed, [],
                    directory / "helper.log", directory / "inno.log", receipt)
                self.assertEqual(helper.count("Start-Process"), 2)
                script.write_text(fake_spawn + helper, encoding="utf-8-sig")
                # Run only the offline harness. Its Start-Process is a fake,
                # process identities are empty, and all files are in scratch.
                with patch.object(subprocess, "Popen", REAL_POPEN_FOR_SAFE_POWERSHELL_TESTS):
                    result = subprocess.run([str(module._powershell_path()), "-NoProfile", "-NonInteractive",
                        "-ExecutionPolicy", "Bypass", "-File", str(script)],
                        capture_output=True, timeout=20, check=False)
                self.assertEqual(result.returncode, 0 if state == "success" else 1,
                                 result.stdout + result.stderr)
                actual = json.loads(receipt.read_text(encoding="utf-8-sig"))
                self.assertEqual(actual["state"], state)
                self.assertEqual(actual["error"], error)
                self.assertTrue(actual["restarted"], result.stdout + result.stderr)
                self.assertEqual(json.loads((directory / "last-result.json").read_text(encoding="utf-8-sig")), actual)
                calls = [json.loads(line) for line in calls_file.read_text(encoding="utf-8-sig").splitlines()]
                self.assertEqual(calls[-1]["file"], str(installed))
                self.assertFalse(calls[-1]["arguments"])
                self.assertEqual(len(calls), 2 if body == FIXTURE_BINARY else 1)
                if len(calls) == 2:
                    self.assertIn('/DIR="' + str(directory) + '"', calls[0]["arguments"])
                    self.assertIn("/NORESTARTAPPLICATIONS", calls[0]["arguments"])
                self.assertFalse((directory / "inno.log").exists(), "no real installer should have run")

    @unittest.skipUnless(os.name == "nt", "Windows process identity API")
    def test_windows_process_identity_reads_current_process_without_execution(self):
        module = self.module()
        result = module._process_identity(os.getpid())
        self.assertIsNotNone(result)
        self.assertTrue(Path(result[0]).samefile(sys.executable))
        self.assertGreater(result[1], 0)
        self.assertIsNone(module._process_identity(4294967294))

    def test_synchronous_check_has_wall_clock_limit_even_if_opener_hangs(self):
        entered, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)

        def hanging_opener(request):
            entered.set()
            resume.wait(0.35)
            return api_fixture(github_release_fixture())

        module, manager, client, opener = self.make_app(hanging_opener)
        with patch.object(module, "CHECK_TIMEOUT", 0.03):
            started = time.monotonic()
            result = self.check(client).get_json()
            elapsed = time.monotonic() - started
            self.assertEqual(result["error"], "network_timeout")
            self.assertLess(elapsed, 0.2, "sync HTTP check exceeded wall-clock budget")
            # A timed-out worker is not duplicated while it is still blocked.
            result = self.check(client).get_json()
            self.assertEqual(result["error"], "network_busy")
            self.assertEqual(len(opener.calls), 1)
        resume.set()
        time.sleep(0.03)

    def test_api_rate_limit_falls_back_to_official_html_digest_and_exact_head_size(self):
        for status in (403, 429):
            with self.subTest(status=status):
                latest, assets, head = html_release_fixtures()
                fixture = github_release_fixture()
                _, manager, client, opener = self.make_app(
                    HTTPError("https://api.github.com/fixture", status, "fixture rate limit", {}, None),
                    latest, assets, head, FakeResponse(FIXTURE_BINARY,
                        fixture["assets"][0]["browser_download_url"]))
                result = self.check(client).get_json()
                self.assertEqual(result["state"], "available")
                self.assertEqual(result["latest_version"], "1.12")
                self.assertEqual(result["download_size"], len(FIXTURE_BINARY))
                self.assertEqual(manager._release.sha256, hashlib.sha256(FIXTURE_BINARY).hexdigest())
                self.assertEqual([call[0].get_method() for call in opener.calls], ["GET", "GET", "GET", "HEAD"])
                self.assertEqual(opener.calls[1][0].full_url,
                                 "https://github.com/yaroslav-softcode/PlannerTaTe/releases/latest")
                self.assertEqual(opener.calls[2][0].full_url,
                                 "https://github.com/yaroslav-softcode/PlannerTaTe/releases/expanded_assets/v1.12")
                self.assertEqual(client.post("/api/updates/download", headers=CLIENT_HEADER).status_code, 202)
                self.assertEqual(self.finish_download(manager)["state"], "ready")
                next(manager.updates_dir.glob("*.exe")).unlink()

    def test_html_fallback_never_offers_older_release_or_fetches_its_binary(self):
        latest, _, _ = html_release_fixtures("1.10")
        _, _, client, opener = self.make_app(
            HTTPError("https://api.github.com/fixture", 403, "fixture", {}, None), latest)
        result = self.check(client).get_json()
        self.assertEqual(result["state"], "current")
        self.assertFalse(result["available"])
        self.assertEqual(result["latest_version"], "1.10")
        self.assertEqual(len(opener.calls), 2)

    def test_html_fallback_requires_digest_bound_to_exact_asset_and_head_size(self):
        for digest, bad_label, size, error in (("", False, "379", "missing_digest"),
                ("sha256:" + "z" * 64, False, "379", "invalid_digest"),
                (None, True, "379", "missing_digest"),
                (None, False, None, "invalid_size"),
                (None, False, "536870913", "invalid_size"),
                (None, False, "55.3 MB", "invalid_size")):
            with self.subTest(error=error, size=size, bad_label=bad_label):
                latest, assets, head = html_release_fixtures(digest=digest, bad_label=bad_label)
                head.headers = {} if size is None else {"Content-Length": size}
                _, _, client, _ = self.make_app(
                    HTTPError("https://api.github.com/fixture", 403, "fixture", {}, None), latest, assets, head)
                result = self.check(client).get_json()
                self.assertEqual(result["state"], "error")
                self.assertEqual(result["error"], error)
                self.assertFalse(result["available"])

    def test_html_fallback_rejects_nonrepo_redirects_and_unstable_release_pages(self):
        for final_url, badge, error in (("https://evil.example/releases/tag/v1.12", "Latest", "unsafe_redirect"),
                ("https://github.com/other/repo/releases/tag/v1.12", "Latest", "unsafe_redirect"),
                ("https://github.com/yaroslav-softcode/PlannerTaTe/releases/tag/v2.0-rc1", "Latest", "unsafe_redirect"),
                ("https://github.com/yaroslav-softcode/PlannerTaTe/releases/tag/v1.12", "Pre-release", "release_not_stable"),
                ("https://github.com/yaroslav-softcode/PlannerTaTe/releases/tag/v1.12", "Draft", "release_not_stable")):
            with self.subTest(error=error, final_url=final_url, badge=badge):
                latest = FakeResponse(f'<span class="Label">{badge}</span>'.encode(), final_url)
                _, _, client, _ = self.make_app(
                    HTTPError("https://api.github.com/fixture", 403, "fixture", {}, None), latest)
                result = self.check(client).get_json()
                self.assertEqual(result["error"], error)
                self.assertFalse(result["available"])

    def test_app_download_api403_html_fallback_is_still_direct_and_cached(self):
        for app_id, repo, name in (("fair", "yaroslav-softcode/FAIR", "FAIR-Setup-2.0.exe"),
                                   ("pastepen", "yaroslav-softcode/paste-pen", "PastePen_v2.0.exe")):
            with self.subTest(app_id=app_id):
                latest, assets, _ = html_release_fixtures("2.0", repo, name)
                _, _, client, opener = self.make_app(
                    HTTPError("https://api.github.com/fixture", 403, "fixture", {}, None), latest, assets)
                result = client.get(f"/api/apps/{app_id}/download")
                self.assertEqual(result.location, f"https://github.com/{repo}/releases/download/v2.0/{name}")
                self.assertEqual(len(opener.calls), 3)
                self.assertEqual(client.get(f"/api/apps/{app_id}/download").location, result.location)
                self.assertEqual(len(opener.calls), 3)

    def test_origin_port_zero_is_not_treated_as_default_port(self):
        _, _, client, opener = self.make_app()
        response = client.post("/api/updates/check", base_url="http://localhost:0",
                               headers={**CLIENT_HEADER, "Origin": "http://localhost"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "origin_forbidden")
        self.assertFalse(opener.calls)

    def test_download_reports_tls_error_without_disabling_verification(self):
        _, manager, client, _ = self.make_app(api_fixture(github_release_fixture()),
            ssl.SSLCertVerificationError("fixture certificate failure"))
        self.check(client)
        self.assertEqual(client.post("/api/updates/download", headers=CLIENT_HEADER).status_code, 202)
        self.assertEqual(self.finish_download(manager)["error"], "tls_error")

    def test_download_response_reports_install_capability_consistently(self):
        exe = self.installed_fixture()
        fixture = github_release_fixture()
        _, manager, client, _ = self.make_app(api_fixture(fixture),
            FakeResponse(FIXTURE_BINARY, fixture["assets"][0]["browser_download_url"]),
            installed_exe=exe, on_exit=Mock())
        self.check(client)
        response = client.post("/api/updates/download", headers=CLIENT_HEADER)
        self.assertTrue(response.get_json()["can_install"])
        self.finish_download(manager)

    def test_blueprint_does_not_change_phone_or_other_existing_routes(self):
        module = self.module()
        app = Flask("unrelated-route-isolation-fixture")

        @app.get("/api/phone/state")
        def unrelated_phone_fixture():
            return {"fixture": "unrelated-existing-route"}

        module.register_updates(app, self.root / "data")
        client = app.test_client()
        response = client.get("/api/phone/state", headers={"Host": "192.168.1.5:5001"},
                              environ_overrides={"REMOTE_ADDR": "192.168.1.99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"fixture": "unrelated-existing-route"})
        self.assertNotIn("Cache-Control", response.headers)
        self.assertFalse((self.root / "data").exists())

    def test_registration_exposes_about_and_idle_status_without_writes(self):
        module = self.module()
        app = Flask(__name__)
        manager = module.register_updates(app, self.root / "data")
        client = app.test_client()
        about = client.get("/api/about").get_json()
        self.assertEqual(about["name"], "PlannerTaTe")
        self.assertEqual(about["current_version"], "1.11")
        self.assertEqual(module.APP_VERSION, "1.11")
        self.assertFalse(about["can_install"])
        self.assertEqual(about["repo_url"],
                         "https://github.com/yaroslav-softcode/PlannerTaTe")
        status = client.get("/api/updates/status").get_json()
        self.assertEqual(status["state"], "idle")
        self.assertEqual(status["current_version"], "1.11")
        self.assertFalse(status["available"])
        for key in ("latest_version", "download_size", "downloaded", "error",
                    "release_url", "can_install"):
            self.assertIn(key, status)
        self.assertIs(app.extensions["plannertate_updates"], manager)
        self.assertFalse((self.root / "data").exists())


if __name__ == "__main__":
    unittest.main()

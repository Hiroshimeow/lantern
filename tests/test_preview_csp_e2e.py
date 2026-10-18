"""Real Edge CSP profiles for server-classified Lantern preview kinds.

Opt in:
    LANTERN_E2E=1 python -m unittest -v tests.test_preview_csp_e2e
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tests.test_pdf_browser_e2e import make_pdf

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "requires Edge browser E2E")
class PreviewCspBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-csp-e2e-", ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name) / "files"
        cls.root.mkdir()
        (cls.root / "probe.md").write_text("# CSP probe\n\nEditable body.\n", encoding="utf-8")
        (cls.root / "probe.txt").write_text("read only\n", encoding="utf-8")
        (cls.root / "probe-evil.js").write_text("window.__lanternCspEvil = true;", encoding="utf-8")
        make_pdf(cls.root / "probe.pdf")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, LANTERN_WORK_DIR=str(Path(cls.tmp.name) / "work"))
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "main.py"),
                "--root",
                str(cls.root),
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--config",
                str(Path(cls.tmp.name) / "config.yaml"),
                "--cache-dir",
                str(Path(cls.tmp.name) / "cache"),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(120):
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("isolated CSP test server did not start")

        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.browser.close()
            cls.play.stop()
        finally:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
            cls.tmp.cleanup()

    def _probe_connections(self, page) -> dict:
        return page.evaluate(
            """async () => {
              const settleWs = url => new Promise(resolve => {
                let done = false;
                const finish = value => { if (!done) { done = true; resolve(value); } };
                try {
                  const ws = new WebSocket(url);
                  ws.onopen = () => { ws.close(); finish('opened'); };
                  ws.onerror = () => finish('blocked');
                  setTimeout(() => { try { ws.close(); } catch {} finish('timeout'); }, 1800);
                } catch (error) { finish('exception:' + error.name); }
              });
              const settleWorker = url => new Promise(resolve => {
                let done = false;
                const finish = value => { if (!done) { done = true; resolve(value); } };
                try {
                  const worker = new Worker(url);
                  worker.onmessage = event => {
                    worker.terminate();
                    const data = event.data || {};
                    finish(data.ok === true ? 'ready' : 'message-error');
                  };
                  worker.onerror = () => { worker.terminate(); finish('blocked'); };
                  worker.postMessage({id: 991, source: '# Worker probe\\n\\nbody\\n'});
                  setTimeout(() => { worker.terminate(); finish('timeout'); }, 2200);
                } catch (error) { finish('exception:' + error.name); }
              });
              let sameFetch;
              try {
                const response = await fetch('/api/info', {cache: 'no-store'});
                sameFetch = response.ok ? 'ok' : 'http-' + response.status;
              } catch (error) { sameFetch = 'blocked:' + error.name; }
              let externalFetch;
              try {
                await fetch('https://example.invalid/lantern-csp-probe');
                externalFetch = 'opened';
              } catch (error) { externalFetch = 'blocked:' + error.name; }
              return {
                sameFetch,
                sameWs: await settleWs('ws://' + location.host + '/ws'),
                sameWorker: await settleWorker('/static/vendor/lantern-md-segment-worker.min.js'),
                externalFetch,
                externalWs: await settleWs('wss://example.invalid/lantern-csp-probe'),
                externalWorker: await settleWorker('https://example.invalid/lantern-csp-worker.js'),
              };
            }"""
        )

    def test_read_only_blocks_connections_and_markdown_allows_only_same_origin(self) -> None:
        external_requests: list[str] = []
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        context.on(
            "request",
            lambda request: external_requests.append(request.url)
            if request.url.startswith(("https://example.invalid/", "wss://example.invalid/"))
            else None,
        )
        try:
            read_only = context.new_page()
            read_console: list[str] = []
            read_only.on("console", lambda message: read_console.append(message.text) if message.type == "error" else None)
            read_only.goto(self.base + "/api/plugin/preview?p=probe.txt", wait_until="domcontentloaded")
            strict = self._probe_connections(read_only)
            self.assertTrue(strict["sameFetch"].startswith("blocked:"), strict)
            self.assertEqual(strict["sameWs"], "blocked", strict)
            self.assertIn(strict["sameWorker"], {"blocked", "exception:SecurityError"}, strict)
            self.assertTrue(strict["externalFetch"].startswith("blocked:"), strict)
            self.assertIn(strict["externalWs"], {"blocked", "exception:SecurityError"}, strict)
            self.assertIn(strict["externalWorker"], {"blocked", "exception:SecurityError"}, strict)
            self.assertTrue(any("Content Security Policy" in line for line in read_console), read_console)

            markdown = context.new_page()
            md_console: list[str] = []
            markdown.on("console", lambda message: md_console.append(message.text) if message.type == "error" else None)
            markdown.goto(self.base + "/api/plugin/preview?p=probe.md", wait_until="domcontentloaded")
            markdown.wait_for_function("() => !!window.__lanternMdVisual?.state?.currentVersion", timeout=12000)
            interactive = self._probe_connections(markdown)
            self.assertEqual(interactive["sameFetch"], "ok", interactive)
            self.assertEqual(interactive["sameWs"], "opened", interactive)
            self.assertEqual(interactive["sameWorker"], "ready", interactive)
            self.assertTrue(interactive["externalFetch"].startswith("blocked:"), interactive)
            self.assertIn(interactive["externalWs"], {"blocked", "exception:SecurityError"}, interactive)
            self.assertIn(interactive["externalWorker"], {"blocked", "exception:SecurityError"}, interactive)

            markdown.evaluate(
                """() => {
                  window.__lanternCspEvil = false;
                  const script = document.createElement('script');
                  script.src = '/probe-evil.js';
                  document.body.appendChild(script);
                }"""
            )
            markdown.wait_for_timeout(350)
            self.assertFalse(markdown.evaluate("() => window.__lanternCspEvil"))
            self.assertTrue(any("Content Security Policy" in line for line in md_console), md_console)
            self.assertEqual(external_requests, [], external_requests)
        finally:
            context.close()

    def test_nonce_rotates_and_native_pdf_frame_loads(self) -> None:
        context = self.browser.new_context(viewport={"width": 1180, "height": 850})
        try:
            first = context.new_page()
            first.goto(self.base + "/api/plugin/preview?p=probe.md", wait_until="domcontentloaded")
            first_nonce = first.locator("script").first.get_attribute("nonce")
            first_policy = first.locator("meta[http-equiv='Content-Security-Policy']").get_attribute("content")
            self.assertIn("connect-src 'self'; worker-src 'self'", first_policy)
            self.assertNotIn("frame-src", first_policy)

            second = context.new_page()
            second.goto(self.base + "/api/plugin/preview?p=probe.md", wait_until="domcontentloaded")
            second_nonce = second.locator("script").first.get_attribute("nonce")
            self.assertNotEqual(first_nonce, second_nonce)

            pdf = context.new_page()
            responses: list[tuple[int, str, str]] = []
            pdf.on(
                "response",
                lambda response: responses.append(
                    (response.status, response.headers.get("content-type", ""), response.url)
                )
                if response.url.endswith("/probe.pdf") and "/api/" not in response.url
                else None,
            )
            pdf.goto(self.base + "/api/plugin/preview?p=probe.pdf", wait_until="domcontentloaded")
            policy = pdf.locator("meta[http-equiv='Content-Security-Policy']").get_attribute("content")
            self.assertIn("connect-src 'none'; frame-src 'self'", policy)
            self.assertNotIn("worker-src", policy)
            frame = pdf.locator("iframe.pdf-native")
            frame.wait_for(state="attached", timeout=10000)
            self.assertEqual(frame.get_attribute("src"), "/probe.pdf")
            pdf.wait_for_timeout(1800)
            self.assertTrue(
                any(status in {200, 206} and "application/pdf" in content_type
                    for status, content_type, _url in responses),
                responses,
            )
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

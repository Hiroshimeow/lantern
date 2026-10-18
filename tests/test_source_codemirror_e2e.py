"""Integrated CodeMirror Source editor acceptance for MD-T007."""
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

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class SourceCodeMirrorE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-source-cm-", ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name) / "root"
        cls.root.mkdir()
        cls.work = Path(cls.tmp.name) / "work"
        cls.work.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, LANTERN_WORK_DIR=str(cls.work))
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "main.py"), "--root", str(cls.root),
             "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(130):
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=.5):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Source CodeMirror E2E server did not start")
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.tmp.cleanup()

    def test_source_uses_one_codemirror_surface_and_canonical_hunk_ui(self):
        file = self.root / "source.md"
        before = "# Source\n\nFirst OLD.\n\nStable.\n\nLast OLD.\n"
        edited = "# Source\n\nFirst NEW.\n\nStable.\n\nLast NEW.\n"
        file.write_text(before, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1280, "height": 820})
        page = ctx.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=source.md")
            page.get_by_role("button", name="Source", exact=True).click()
            editor = page.get_by_role("textbox", name="Markdown source")
            editor.wait_for(timeout=12000)

            self.assertEqual(page.locator(".cm-editor").count(), 1)
            self.assertEqual(page.locator("textarea.md-source-area").count(), 0)
            self.assertEqual(page.locator(".md-source-diff-backdrop-content").count(), 0)
            self.assertEqual(page.locator(".md-source-deletions").count(), 0)
            self.assertTrue(editor.get_attribute("contenteditable") == "true")
            self.assertEqual(
                page.evaluate("() => window.__lanternMdVisual.state.instance.kind"),
                "codemirror-source",
            )

            editor.fill(edited)
            page.wait_for_function(
                "() => document.documentElement.dataset.mdPendingHunks === '2'",
                timeout=12000,
            )
            self.assertGreaterEqual(page.locator(".cm-lantern-diff-gutter .cm-gutterElement").count(), 2)
            self.assertGreaterEqual(page.locator(".cm-lantern-deletion").count(), 2)
            self.assertGreaterEqual(
                page.get_by_role("button", name="Accept").count(), 2
            )
            metrics = page.evaluate(
                "() => window.__lanternMdVisual.state.instance.debugMetrics()"
            )
            self.assertLessEqual(metrics["renderedLines"], metrics["docLines"])
            self.assertTrue(metrics["focused"])
        finally:
            ctx.close()

    def test_source_preview_source_preserves_text_and_keyboard_history(self):
        file = self.root / "switch.md"
        original = "# Switch\n\nBody.\n"
        edited = "# Switch\n\nBody edited.\n"
        file.write_text(original, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 760})
        page = ctx.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=switch.md")
            page.get_by_role("button", name="Source", exact=True).click()
            editor = page.get_by_role("textbox", name="Markdown source")
            editor.fill(edited)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Body edited.')",
                timeout=12000,
            )
            editor.press("Control+z")
            self.assertEqual(
                page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()"),
                original,
            )
            editor.press("Control+y")
            self.assertEqual(
                page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()"),
                edited,
            )
            page.get_by_role("button", name="Preview", exact=True).click()
            page.wait_for_function("() => !window.__lanternMdVisual.state.active", timeout=12000)
            page.get_by_role("button", name="Source", exact=True).click()
            page.get_by_role("textbox", name="Markdown source").wait_for(timeout=12000)
            self.assertEqual(
                page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()"),
                edited,
            )
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()

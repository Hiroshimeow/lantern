"""Opt-in real Edge acceptance for the offline in-preview Milkdown visual editor.

Run: set LANTERN_E2E=1 && uv run --with-requirements requirements.txt --with playwright python -m unittest -v test_md_visual_e2e
Uses only an isolated loopback server and temporary Markdown files, never FJP's live instance.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "set LANTERN_E2E=1 for real-browser tests")
class VisualMarkdownBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / "readme.md").write_bytes(b"# Lantern\n\nHello **world**.\n")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"), "--root", str(cls.root),
             "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic() + 12
        while time.monotonic() < until:
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            cls.proc.terminate()
            raise RuntimeError("isolated Lantern instance failed to become ready")
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
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
            cls.temp.cleanup()

    def test_preview_is_fast_until_edit_then_inline_editor_saves(self):
        context = self.browser.new_context()
        page = context.new_page()
        errors = []
        resources = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("request", lambda req: resources.append(req.url))
        try:
            page.goto(self.base + "/api/plugin/preview?p=readme.md", wait_until="load", timeout=15000)
            self.assertTrue(page.locator("article.md-preview").is_visible())
            self.assertTrue(page.get_by_role("button", name="Edit visually").is_visible())
            self.assertFalse(any("lantern-crepe.min.js" in u for u in resources))
            page.get_by_role("button", name="Edit visually").click()
            page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=35000)
            state = page.evaluate("""() => ({
              roundtripSafe: window.__lanternMdVisual.state.roundtripSafe,
              markdown: window.__lanternMdVisual.state.instance.getMarkdown(),
              loadMs: window.__lanternMdMetrics.loadMs,
              bytes: window.__lanternMdMetrics.editorBytes,
            })""")
            self.assertTrue(any("lantern-crepe.min.js" in u for u in resources))
            self.assertEqual(state["bytes"], (self.root / "readme.md").stat().st_size)
            print("EDITOR_BASELINE=" + json.dumps(state, ensure_ascii=False))
            paragraph = page.locator(".md-visual-host .ProseMirror p").first
            paragraph.click()
            # Editor retains focus and applies real keyboard input in place.
            page.keyboard.press("End")
            page.keyboard.type(" edited")
            page.wait_for_timeout(700)
            # Editor retains focus and applies real keyboard input in place.
            self.assertIn("edited", page.locator(".md-visual-host .ProseMirror").inner_text())
            if state["roundtripSafe"]:
                page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=15000)
            else:
                page.get_by_role("button", name="Save", exact=True).click()
                page.get_by_role("button", name="Accept conversion & Save").click()
                page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=15000)
            self.assertIn("edited", (self.root / "readme.md").read_text(encoding="utf-8"))
            self.assertEqual(errors, [], "browser JS exceptions: " + str(errors))
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

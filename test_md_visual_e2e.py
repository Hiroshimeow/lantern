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


    def test_two_visual_clients_conflict_without_overwriting(self):
        (self.root / "shared.md").write_bytes(b"# Shared\n\nOriginal.\n")
        context_a = self.browser.new_context()
        context_b = self.browser.new_context()
        try:
            pages = [context_a.new_page(), context_b.new_page()]
            for page in pages:
                page.goto(self.base + "/api/plugin/preview?p=shared.md", timeout=15000)
                page.get_by_role("button", name="Edit visually").click()
                page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=25000)
                self.assertTrue(page.evaluate("() => window.__lanternMdVisual.state.roundtripSafe"))
            a, b = pages
            for page, suffix in [(a, " A"), (b, " B")]:
                paragraph = page.locator(".md-visual-host .ProseMirror p").first
                paragraph.click()
                page.keyboard.press("End")
                page.keyboard.type(suffix)
                if page is a:
                    page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=15000)
                else:
                    page.locator(".md-visual-status").filter(has_text=re.compile(r"^Conflict")).wait_for(timeout=15000)
            saved = (self.root / "shared.md").read_text(encoding="utf-8")
            self.assertIn("Original. A", saved)
            self.assertNotIn("Original. B", saved)
            self.assertIn("Original. B", b.locator(".md-visual-host .ProseMirror").inner_text())
            self.assertTrue(b.evaluate("() => window.__lanternMdVisual.state.conflict"))
        finally:
            context_a.close()
            context_b.close()

    def test_opening_mermaid_and_tables_never_saves_a_normalized_file(self):
        content = (
            "# Complex\n\n"
            "- [x] done\n\n"
            "| Alpha | Beta |\n| --- | --- |\n| A | B |\n\n"
            "```mermaid\nflowchart LR\n A --> B\n```\n"
        )
        (self.root / "complex.md").write_bytes(content.encode("utf-8"))
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=complex.md", timeout=18000)
            self.assertTrue(page.locator(".mermaid-diagram").count() >= 1)
            page.get_by_role("button", name="Edit visually").click()
            page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=25000)
            current = page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()")
            self.assertIn("mermaid", current)
            self.assertIn("flowchart LR", current)
            self.assertIn("Alpha", page.locator(".md-visual-host .ProseMirror").inner_text())
            page.wait_for_timeout(2800)
            # Internal Milkdown table transactions must not flag a user edit.
            self.assertEqual((self.root / "complex.md").read_bytes(), content.encode("utf-8"),
                             "opening WYSIWYG must never rewrite original Markdown")
            self.assertFalse(page.evaluate("() => window.__lanternMdVisual.state.dirty"))
        finally:
            context.close()


    def test_browser_recovers_unsaved_draft_without_false_saved_state(self):
        original = b"# Draft\n\nHello.\n"
        (self.root / "draft.md").write_bytes(original)
        context = self.browser.new_context()
        try:
            first = context.new_page()
            first.route("**/api/md/save", lambda route: route.abort("failed"))
            first.goto(self.base + "/api/plugin/preview?p=draft.md", timeout=15000)
            first.get_by_role("button", name="Edit visually").click()
            first.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=25000)
            p = first.locator(".md-visual-host .ProseMirror p").first
            p.click()
            first.keyboard.press("End")
            first.keyboard.type(" pending")
            first.wait_for_timeout(1700)
            self.assertTrue(first.evaluate("() => window.__lanternMdVisual.state.dirty"))
            self.assertEqual((self.root / "draft.md").read_bytes(), original)
            first.close()
            second = context.new_page()
            second.on("dialog", lambda dialog: dialog.accept())
            second.goto(self.base + "/api/plugin/preview?p=draft.md", timeout=15000)
            second.get_by_role("button", name="Edit visually").click()
            second.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=25000)
            state = second.evaluate("""() => ({
              dirty:window.__lanternMdVisual.state.dirty,
              savedBaseline:window.__lanternMdVisual.state.lastSaved,
              recovered:window.__lanternMdVisual.state.instance.getMarkdown(),
              approved:window.__lanternMdVisual.state.approvedReformat,
            })""")
            self.assertTrue(state["dirty"])
            self.assertIn("pending", state["recovered"])
            self.assertNotIn("pending", state["savedBaseline"])
            self.assertFalse(state["approved"])
            self.assertEqual((self.root / "draft.md").read_bytes(), original)
            second.get_by_role("button", name="Save", exact=True).click()
            second.get_by_role("button", name="Accept conversion & Save").click()
            second.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=15000)
            self.assertIn("pending", (self.root / "draft.md").read_text(encoding="utf-8"))
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

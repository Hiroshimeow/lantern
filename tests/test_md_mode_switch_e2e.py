"""Real Edge regression for fast Preview / Edit Visually / Source switching.

All tests run with a temporary loopback Lantern server and disposable files.
"""
from __future__ import annotations
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "set LANTERN_E2E=1")
class MarkdownModesE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        import urllib.request
        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-mode-", ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"),
             "--root", str(cls.root), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(130):
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=.5):
                    break
            except OSError:
                time.sleep(.1)
        else:
            cls.proc.terminate()
            raise RuntimeError("Disposable server did not start")
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
            cls.tmp.cleanup()

    def test_three_modes_preserve_exact_source_and_render_mermaid(self):
        initial = (
            "# Three modes\n\n"
            "| Name | Value |\n| - | :-: |\n| escape \\| pipe | `x|y` |\n\n"
            "<!-- invisible comment -->\n\n"
            "```mermaid\nflowchart LR\n  A[Start] --> B[End]\n```\n\n"
            "```markdown\n<!-- literal code example -->\n```\n"
        )
        path = self.root / "modes.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1200, "height": 850})
        page = context.new_page()
        errors, navs, requests = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("framenavigated", lambda frame: navs.append(frame.url) if frame == page.main_frame else None)
        page.on("request", lambda request: requests.append(request.url))
        try:
            page.goto(self.base + "/api/plugin/preview?p=modes.md", wait_until="domcontentloaded", timeout=18000)
            preview = page.locator("article.md-preview")
            self.assertEqual(preview.locator("table").count(), 1)
            self.assertNotIn("invisible comment", preview.inner_text())
            self.assertIn("literal code example", preview.inner_text())
            page.locator(".mermaid-output svg").first.wait_for(timeout=15000)
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=11000)
            self.assertEqual(area.input_value(), initial)
            self.assertFalse(any("lantern-crepe.min.js" in url for url in requests))
            area.fill(initial.replace("Three modes", "Three modes updated"))
            page.keyboard.press("Control+s")
            page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=14000)
            saved = path.read_text(encoding="utf-8")
            self.assertIn("Three modes updated", saved)
            self.assertIn("<!-- invisible comment -->", saved)
            page.get_by_role("button", name="Preview", exact=True).click()
            preview.wait_for(state="visible", timeout=15000)
            page.get_by_role("heading", name="Three modes updated").wait_for(timeout=15000)
            self.assertNotIn("invisible comment", preview.inner_text())
            page.locator(".mermaid-output svg").first.wait_for(timeout=15000)
            navigations = len(navs)

            page.get_by_role("button", name="Edit visually", exact=True).click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            editor.wait_for(timeout=24000)
            self.assertIn("flowchart LR", editor.inner_text())
            self.assertIn("invisible comment", editor.inner_text())
            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=12000)
            self.assertEqual(area.input_value(), saved)
            page.get_by_role("button", name="Preview", exact=True).click()
            preview.wait_for(state="visible", timeout=12000)
            self.assertEqual(len(navs), navigations, "clean mode switching should not reload")
            self.assertEqual(path.read_text(encoding="utf-8"), saved)
            self.assertEqual(errors, [], errors)
        finally:
            context.close()

    def test_dirty_visual_to_source_retains_unsaved_edits(self):
        path = self.root / "visual-dirty.md"
        original = "# Visual draft\n\nOriginal text.\n"
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=visual-dirty.md", wait_until="domcontentloaded")
            page.get_by_role("button", name="Edit visually", exact=True).click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            editor.wait_for(timeout=23000)
            paragraph = editor.locator("p").first
            paragraph.click()
            page.keyboard.press("End")
            page.keyboard.type(" appended")
            self.assertIn("appended", page.evaluate(
                "() => window.__lanternMdVisual.state.instance.getMarkdown()"))
            # Switch before the 2.4-second autosave delay. It must be a local
            # mode transition, not a write or a guessed reconstruction.
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=16000)
            self.assertIn("appended", area.input_value())
            self.assertTrue(page.evaluate("window.__lanternMdVisual.state.dirty"))
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            page.keyboard.press("Control+s")
            page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=13000)
            self.assertIn("appended", path.read_text(encoding="utf-8"))
        finally:
            context.close()

    def test_source_two_clients_conflict_without_overwrite(self):
        path = self.root / "conflict.md"
        path.write_text("# Clients\n\nOriginal\n", encoding="utf-8")
        context = self.browser.new_context()
        a, b = context.new_page(), context.new_page()
        try:
            for page in (a, b):
                page.goto(self.base + "/api/plugin/preview?p=conflict.md", wait_until="domcontentloaded")
                page.get_by_role("button", name="Source", exact=True).click()
                page.get_by_role("textbox", name="Markdown source").wait_for(timeout=10000)
            a.get_by_role("textbox", name="Markdown source").fill("# Clients\n\nClient A\n")
            a.keyboard.press("Control+s")
            a.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=13000)
            b.get_by_role("textbox", name="Markdown source").fill("# Clients\n\nClient B\n")
            b.keyboard.press("Control+s")
            b.locator(".md-visual-status").filter(has_text="Conflict").wait_for(timeout=13000)
            self.assertEqual(path.read_text(encoding="utf-8"), "# Clients\n\nClient A\n")
            self.assertTrue(b.evaluate("window.__lanternMdVisual.state.conflict"))
        finally:
            context.close()

    def test_unsaved_source_returns_preview_with_local_draft(self):
        path = self.root / "draft.md"
        original = "# Draft\n\nOriginal\n"
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        navs = []
        page.on("framenavigated", lambda frame: navs.append(frame.url) if frame == page.main_frame else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=draft.md", wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=12000)
            area.fill("# Draft\n\nUncommitted draft\n")
            page.get_by_role("button", name="Edit visually", exact=True).click()
            self.assertEqual(page.evaluate("window.__lanternMdVisual.state.mode"), "source")
            self.assertIn("Save Source before", page.locator(".md-visual-status").inner_text())
            self.assertIn("Uncommitted draft", area.input_value())
            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible", timeout=13000)
            self.assertEqual(len(navs), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=14000)
            self.assertIn("Uncommitted draft", area.input_value())
            self.assertTrue(page.evaluate("window.__lanternMdVisual.state.dirty"))
        finally:
            context.close()

    def test_large_source_to_paged_visual_and_back(self):
        path = self.root / "large-switch.md"
        original = "# Large switch\n\n" + "".join(
            "## Section " + str(i) + "\n\n" + ("A" * 450) + "\n\n" for i in range(120)
        )
        self.assertGreater(len(original), 32 * 1024)
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        navs = []
        page.on("framenavigated", lambda frame: navs.append(frame.url)
                if frame == page.main_frame else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=large-switch.md", wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=17000)
            self.assertEqual(area.input_value(), original)
            page.get_by_role("button", name="Edit visually", exact=True).click()
            page.wait_for_function(
                "() => !!window.__lanternMdPaged?.active", timeout=33000)
            self.assertEqual(page.evaluate("window.__lanternMdVisual.state.mode"), "paged")
            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=20000)
            self.assertEqual(area.input_value(), original)
            self.assertEqual(page.evaluate("window.__lanternMdVisual.state.mode"), "source")
            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible", timeout=15000)
            self.assertEqual(len(navs), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
        finally:
            context.close()

    def test_paged_unsaved_section_cannot_disappear_into_source(self):
        path = self.root / "paged-dirty-switch.md"
        original = "# Paged switch\n\nFirst paragraph.\n\n" + "".join(
            "## Section " + str(i) + "\n\n" + ("A" * 450) + "\n\n" for i in range(120)
        )
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=paged-dirty-switch.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Edit visually", exact=True).click()
            page.wait_for_function("() => !!window.__lanternMdPaged?.active", timeout=32000)
            paragraph = page.locator(".md-visual-host .ProseMirror p").first
            paragraph.click()
            page.keyboard.press("End")
            page.keyboard.type(" DRAFT")
            page.wait_for_function("() => window.__lanternMdPaged.dirty", timeout=6000)
            page.get_by_role("button", name="Source", exact=True).click()
            page.wait_for_function(
                "() => (document.querySelector('.md-visual-status')?.textContent || '').includes('Save this section before switching')",
                timeout=7000,
            )
            self.assertTrue(page.evaluate("window.__lanternMdPaged.active"))
            self.assertFalse(page.get_by_role("textbox", name="Markdown source").count())
            self.assertIn("DRAFT", page.locator(".md-visual-host .ProseMirror").inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            page.get_by_role("button", name="Save", exact=True).click()
            review = page.get_by_role("button", name="Accept changes & Save")
            try:
                review.wait_for(timeout=1500)
                review.click()
            except Exception:
                pass  # No conversion review needed for a byte-safe section.
            # Autosave may have completed while the mode switch was blocked:
            # the disk source/version, not the status-label wording, is truth.
            page.wait_for_function(
                "() => { const p=window.__lanternMdPaged; "
                "return !!p && !p.dirty && p.source.includes('DRAFT'); }",
                timeout=16000,
            )
            self.assertIn("DRAFT", path.read_text(encoding="utf-8"))
            page.get_by_role("button", name="Source", exact=True).click()
            page.get_by_role("textbox", name="Markdown source").wait_for(timeout=17000)
            self.assertIn("DRAFT", page.get_by_role("textbox", name="Markdown source").input_value())
        finally:
            context.close()

    def test_legacy_editor_uses_versioned_saves(self):
        path = self.root / "legacy.md"
        path.write_text("# Legacy\n\nOriginal\n", encoding="utf-8")
        context = self.browser.new_context()
        a, b = context.new_page(), context.new_page()
        try:
            for page in (a, b):
                page.goto(self.base + "/legacy.md?edit=1", wait_until="domcontentloaded")
                page.locator("#editarea").wait_for(timeout=12000)
                self.assertTrue(page.get_by_role("link", name="Preview").is_visible())
            a.locator("#editarea").fill("# Legacy\n\nClient A\n")
            a.get_by_role("button", name="Save", exact=False).click()
            a.locator("#saveStatus").filter(has_text="Saved").wait_for(timeout=12000)
            b.locator("#editarea").fill("# Legacy\n\nClient B\n")
            b.get_by_role("button", name="Save", exact=False).click()
            b.locator("#saveStatus").filter(has_text="Conflict").wait_for(timeout=12000)
            self.assertEqual(path.read_text(encoding="utf-8"), "# Legacy\n\nClient A\n")
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

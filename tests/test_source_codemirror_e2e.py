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


    def test_source_persists_small_patch_without_normalizing_mixed_eol(self):
        file = self.root / "patch-source.md"
        before = b"# Mixed\r\n\r\nLine OLD.\nTail"
        expected = b"# Mixed\r\n\r\nLine NEW.\nTail"
        file.write_bytes(before)
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 760})
        page = ctx.new_page()
        posts = []
        page.on(
            "request",
            lambda request: posts.append({
                "url": request.url,
                "method": request.method,
                "data": request.post_data or "",
            }) if request.method == "POST" else None,
        )
        try:
            page.goto(self.base + "/api/plugin/preview?p=patch-source.md")
            page.get_by_role("button", name="Source", exact=True).click()
            editor = page.get_by_role("textbox", name="Markdown source")
            editor.wait_for(timeout=12000)
            state = page.evaluate(
                "async() => (await (await fetch('/api/work?p=patch-source.md')).json())"
            )
            temp = Path(state["tempPath"])
            self.assertEqual(temp.read_bytes(), before)
            posts.clear()

            page.evaluate("""() => window.__lanternMdVisual.state.instance.restoreBookmark({
              line:3, selectedText:'OLD'
            })""")
            page.keyboard.type("NEW")
            deadline = time.time() + 12
            while time.time() < deadline and file.read_bytes() != expected:
                time.sleep(.05)
            self.assertEqual(file.read_bytes(), expected)
            self.assertEqual(temp.read_bytes(), before)
            # Pump Playwright's event queue after the filesystem polling loop so
            # request callbacks are delivered before network assertions.
            page.wait_for_timeout(50)
            patch_posts = [item for item in posts if "/api/work/patch" in item["url"]]
            write_posts = [item for item in posts if "/api/work/write" in item["url"]]
            self.assertGreaterEqual(len(patch_posts), 1, posts)
            self.assertEqual(write_posts, [], posts)
            self.assertLess(max(len(item["data"].encode("utf-8")) for item in patch_posts), 2048)
            payload = __import__("json").loads(patch_posts[-1]["data"])
            self.assertEqual(payload["patches"][0]["from"]["line"], 3)
            self.assertEqual(payload["patches"][0]["expected"], "OLD")
            self.assertFalse(file.read_bytes().endswith((b"\n", b"\r")))
        finally:
            ctx.close()


    def test_source_external_refresh_keeps_editor_instance_and_ctrl_s_accepts(self):
        file = self.root / "external-source.md"
        original = "# External\n\nOld.\n"
        external = "# External\n\nVS Code.\n"
        local = "# External\n\nVS Code + local.\n"
        file.write_text(original, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 760})
        page = ctx.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=external-source.md")
            page.get_by_role("button", name="Source", exact=True).click()
            page.get_by_role("textbox", name="Markdown source").wait_for(timeout=12000)
            state = page.evaluate(
                "async() => (await (await fetch('/api/work?p=external-source.md')).json())"
            )
            temp = Path(state["tempPath"])
            accepted = temp.read_bytes()
            page.evaluate("() => { window.__sourceIdentity = window.__lanternMdVisual.state.instance; }")

            file.write_text(external, encoding="utf-8", newline="")
            page.evaluate("() => window.dispatchEvent(new Event('focus'))")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.instance.getMarkdown().includes('VS Code.')",
                timeout=5000,
            )
            self.assertTrue(page.evaluate(
                "() => window.__sourceIdentity === window.__lanternMdVisual.state.instance"
            ))
            self.assertEqual(page.locator(".cm-editor").count(), 1)
            self.assertEqual(temp.read_bytes(), accepted)

            editor = page.get_by_role("textbox", name="Markdown source")
            editor.fill(local)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('VS Code + local.')",
                timeout=12000,
            )
            self.assertEqual(file.read_text(encoding="utf-8"), local)
            self.assertEqual(temp.read_bytes(), accepted)
            page.keyboard.press("Control+s")
            page.wait_for_function(
                "() => document.documentElement.dataset.mdPendingHunks === '0'",
                timeout=12000,
            )
            self.assertEqual(temp.read_bytes(), file.read_bytes())
        finally:
            ctx.close()

    def test_source_stale_overlap_keeps_local_recovery_and_external_bytes(self):
        file = self.root / "source-stale.md"
        original = "# Stale\n\nOLD\n"
        first = "# Stale\n\nFIRST\n"
        second = "# Stale\n\nSECOND\n"
        file.write_text(original, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 760})
        a, b = ctx.new_page(), ctx.new_page()
        try:
            for page in (a, b):
                page.goto(self.base + "/api/plugin/preview?p=source-stale.md")
                page.get_by_role("button", name="Source", exact=True).click()
                page.get_by_role("textbox", name="Markdown source").wait_for(timeout=12000)
            state = a.evaluate(
                "async() => (await (await fetch('/api/work?p=source-stale.md')).json())"
            )
            temp = Path(state["tempPath"])
            accepted = temp.read_bytes()

            a.evaluate("""() => window.__lanternMdVisual.state.instance.restoreBookmark({
              line:3, selectedText:'OLD'
            })""")
            a.keyboard.type("FIRST")
            deadline = time.time() + 8
            while time.time() < deadline and file.read_text(encoding="utf-8") != first:
                time.sleep(.03)
            self.assertEqual(file.read_text(encoding="utf-8"), first)

            b.evaluate("""() => window.__lanternMdVisual.state.instance.restoreBookmark({
              line:3, selectedText:'OLD'
            })""")
            b.keyboard.type("SECOND")
            b.wait_for_function(
                "() => window.__lanternMdVisual.state.conflict === true",
                timeout=8000,
            )
            self.assertEqual(file.read_text(encoding="utf-8"), first)
            self.assertEqual(temp.read_bytes(), accepted)
            self.assertEqual(
                b.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()"),
                second,
            )
            self.assertIn(
                "Overlapping Source edits are retained locally",
                b.locator("[data-md-status]").inner_text(),
            )
        finally:
            ctx.close()


    def test_source_to_visual_keeps_changed_block_and_anchor(self):
        original = "# Source visual\n\n" + "\n\n".join(
            f"Paragraph {i} unique text." for i in range(150)
        ) + "\n"
        changed = original.replace(
            "Paragraph 100 unique text.",
            "Paragraph 100 changed in Source.",
        )
        file = self.root / "source-visual.md"
        file.write_text(original, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = ctx.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=source-visual.md")
            page.get_by_role("button", name="Source", exact=True).click()
            editor = page.get_by_role("textbox", name="Markdown source")
            editor.wait_for(timeout=12000)
            editor.fill(changed)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Paragraph 100 changed')",
                timeout=12000,
            )
            page.evaluate(
                "() => window.__lanternMdVisual.state.instance.restoreBookmark({line:203})"
            )
            page.get_by_role("button", name="Edit visually", exact=True).click()
            visual = page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            visual.wait_for(timeout=24000)
            target = visual.get_by_text("Paragraph 100 changed in Source.", exact=True)
            target.wait_for(timeout=12000)
            box = target.bounding_box()
            self.assertIsNotNone(box)
            self.assertGreater(page.evaluate("scrollY"), 800)
            self.assertLess(box["y"], 820)
            self.assertIn("Paragraph 100 changed in Source.", file.read_text(encoding="utf-8"))
        finally:
            ctx.close()

    def test_synthetic_composition_undo_redo_persists_one_patch_per_change(self):
        file = self.root / "composition.md"
        original = "# IME\n\n日本語\n"
        inserted = "# IME\n\n漢字日本語\n"
        file.write_text(original, encoding="utf-8", newline="")
        ctx = self.browser.new_context(viewport={"width": 1000, "height": 720})
        page = ctx.new_page()
        patch_posts = []
        page.on(
            "request",
            lambda req: patch_posts.append(req.post_data or "")
            if req.method == "POST" and "/api/work/patch" in req.url else None,
        )
        try:
            page.goto(self.base + "/api/plugin/preview?p=composition.md")
            page.get_by_role("button", name="Source", exact=True).click()
            page.get_by_role("textbox", name="Markdown source").wait_for(timeout=12000)
            page.evaluate(
                "() => window.__lanternMdVisual.state.instance.restoreBookmark({line:3,column:0})"
            )
            patch_posts.clear()
            page.evaluate("""() => {
              const area=document.querySelector('[data-lantern-source-content]');
              area.dispatchEvent(new CompositionEvent(
                'compositionstart',{bubbles:true,data:''}));
              area.dispatchEvent(new CompositionEvent(
                'compositionupdate',{bubbles:true,data:'漢字'}));
            }""")
            page.keyboard.insert_text("漢字")
            page.evaluate("""() => {
              const area=document.querySelector('[data-lantern-source-content]');
              area.dispatchEvent(new CompositionEvent(
                'compositionend',{bubbles:true,data:'漢字'}));
            }""")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('漢字日本語')",
                timeout=12000,
            )
            self.assertEqual(file.read_text(encoding="utf-8"), inserted)
            page.wait_for_timeout(100)
            self.assertEqual(len(patch_posts), 1, patch_posts)

            page.keyboard.press("Control+z")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved === '# IME\\n\\n日本語\\n'",
                timeout=12000,
            )
            self.assertEqual(file.read_text(encoding="utf-8"), original)
            page.keyboard.press("Control+y")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('漢字日本語')",
                timeout=12000,
            )
            self.assertEqual(file.read_text(encoding="utf-8"), inserted)
            page.wait_for_timeout(100)
            self.assertEqual(len(patch_posts), 3, patch_posts)
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

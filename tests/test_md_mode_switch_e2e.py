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
        env = dict(os.environ)
        env["LANTERN_WORK_DIR"] = str(cls.root / ".lantern-work")
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"),
             "--root", str(cls.root), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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

    def test_preview_underscores_comments_and_escapes_without_source_mutation(self):
        original = (
            "# Long_file_name_2026\n\n"
            "Identifiers: foo_bar_baz, module__name__suffix, data_set_01.csv.\n\n"
            "Escaped: \\*literal\\* and \\_underscored\\_.\n\n"
            "Normal: _italic_ and __strong__.\n\n"
            "<!-- private note that remains editable in Source -->\n\n"
            "Example: !<--not an HTML comment--> and plain \\*.\n"
        )
        path = self.root / "preview-escaping-regression.md"
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1250, "height": 800})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=preview-escaping-regression.md",
                      wait_until="domcontentloaded")
            preview = page.locator("article.md-preview")
            self.assertEqual(page.get_by_role("heading", level=1).inner_text(),
                             "Long_file_name_2026")
            self.assertIn("foo_bar_baz", preview.inner_text())
            self.assertIn("module__name__suffix", preview.inner_text())
            self.assertIn("data_set_01.csv", preview.inner_text())
            self.assertIn("Escaped: *literal* and _underscored_.",
                          preview.inner_text())
            self.assertIn("<em>italic</em>", preview.inner_html())
            self.assertIn("<strong>strong</strong>", preview.inner_html())
            self.assertNotIn("private note", preview.inner_text())
            self.assertIn("!<--not an HTML comment-->", preview.inner_text())
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for()
            self.assertEqual(source.input_value(), original)
            page.get_by_role("button", name="Preview", exact=True).click()
            preview.wait_for(state="visible")
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(errors, [])
        finally:
            context.close()

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

    def test_fixed_mode_bar_and_source_mapping_from_deep_preview_scroll(self):
        original = "# Navigation\n\n" + "\n\n".join(
            f"Block {i} content for source editing." for i in range(170)) + "\n"
        target = self.root / "deep-source-navigation.md"
        target.write_text(original, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 960, "height": 650})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=deep-source-navigation.md",
                      wait_until="domcontentloaded")
            marker = page.locator(".md-preview p").nth(120)
            marker.scroll_into_view_if_needed()
            page.evaluate("""() => {
                const node = document.querySelectorAll('.md-preview p')[120];
                const range = document.createRange();
                range.selectNodeContents(node);
                const selection = getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
            }""")
            self.assertGreater(page.evaluate("scrollY"), 400)
            self.assertLessEqual(abs(page.locator(".md-bar").bounding_box()["y"]), 2)
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=12000)
            self.assertFalse(page.locator('.content > .note').is_visible())
            self.assertFalse(page.locator('.content > .muted').is_visible())
            position = page.evaluate("""() => {
                const el = document.querySelector('.md-source-area');
                return {line:el.value.slice(0,el.selectionStart).split('\\n').length,
                  innerScroll:el.scrollTop, visible:el.getBoundingClientRect().top};
            }""")
            self.assertEqual(position["line"], 243)
            self.assertGreater(position["innerScroll"], 800)
            self.assertLessEqual(abs(page.locator(".md-bar").bounding_box()["y"]), 2)
            self.assertTrue(page.locator('[data-action="md-save"]').is_visible())
            self.assertTrue(page.locator('[data-action="md-download-draft"]').is_visible())
            self.assertTrue(page.locator('[data-action="md-back-preview"]').is_visible())
            self.assertTrue(page.get_by_role("button", name="Preview", exact=True).is_visible())
            page.get_by_role("button", name="Preview", exact=True).click()
            marker.wait_for(state="visible", timeout=12000)
            rect = marker.bounding_box()
            header = page.locator(".md-bar").bounding_box()
            self.assertGreater(rect["y"], header["height"] - 25)
            self.assertLess(rect["y"], 650)

            # A stale DOM selection from an older Preview visit must not win
            # over the block actually visible when switching modes again.
            page.evaluate("""() => {
                const stale = document.querySelector('.md-preview p:last-of-type');
                const range = document.createRange();
                range.selectNodeContents(stale);
                const selection = getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                document.querySelectorAll('.md-preview p')[120].scrollIntoView({block:'center'});
            }""")
            self.assertLess(page.locator(".md-preview p").nth(120).bounding_box()["y"], 650)
            expected_line = page.evaluate("""() => {
                const toolbar = document.querySelector('.md-bar').getBoundingClientRect().bottom;
                for (const el of document.querySelectorAll('.md-preview [data-l]')) {
                    const r = el.getBoundingClientRect();
                    if (r.bottom > toolbar && r.top < innerHeight) return Number(el.dataset.l);
                }
                return 1;
            }""")
            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=12000)
            repeated = page.evaluate("""() => {
                const el = document.querySelector('.md-source-area');
                return el.value.slice(0, el.selectionStart).split('\\n').length;
            }""")
            self.assertEqual(repeated, expected_line)
            page.get_by_role("button", name="Preview", exact=True).click()
            marker.wait_for(state="visible", timeout=12000)
            rect2 = marker.bounding_box()
            self.assertGreater(rect2["y"], header["height"] - 25)
            self.assertLess(rect2["y"], 650)
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_repeated_mode_roundtrip_keeps_same_preview_anchor(self):
        original = "# Roundtrip\n\n" + "\n\n".join(
            f"Unique block {i} for repeated mode navigation." for i in range(180)) + "\n"
        target = self.root / "repeated-mode-anchor.md"
        target.write_text(original, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=repeated-mode-anchor.md",
                      wait_until="domcontentloaded")
            marker = page.locator(".md-preview p").nth(118)
            marker.scroll_into_view_if_needed()
            page.evaluate("getSelection().removeAllRanges()")
            expected = page.evaluate(
                "() => window.LanternAnchorBridge.capture('preview').line")
            self.assertGreater(expected, 100)

            for cycle in range(3):
                page.get_by_role("button", name="Source", exact=True).click()
                page.locator("textarea.md-source-area").wait_for(timeout=12000)
                page.get_by_role("button", name="Preview", exact=True).click()
                page.locator("article.md-preview").wait_for(state="visible", timeout=12000)
                after_source = page.evaluate(
                    "() => window.LanternAnchorBridge.capture('preview').line")
                self.assertEqual(after_source, expected, f"Source roundtrip drifted on cycle {cycle}")

                page.get_by_role("button", name="Edit visually", exact=True).click()
                page.locator(".md-visual-host .ProseMirror").wait_for(timeout=24000)
                page.get_by_role("button", name="Preview", exact=True).click()
                page.locator("article.md-preview").wait_for(state="visible", timeout=12000)
                after_visual = page.evaluate(
                    "() => window.LanternAnchorBridge.capture('preview').line")
                self.assertEqual(after_visual, expected, f"Visual roundtrip drifted on cycle {cycle}")
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_preview_long_table_continuation_is_structured_in_real_edge(self):
        # The 160-row Markdown Preview budget must not spill subsequent rows
        # into a paragraph. This fixture also exceeds the separate 64 KiB
        # *visual editor* threshold, which must not affect Preview rendering.
        path = self.root / "preview-long-table.md"
        original = (
            "# Detailed table\n\n"
            "| Number | Key | Value |\n"
            "| --- | --- | --- |\n"
            + "".join(
                f"| {i} | ROW-{i:03d} | " + ("a" * 190) + " |\n"
                for i in range(1, 361)
            )
            + "\n## Following section\n\nStill readable.\n"
        )
        self.assertGreater(len(original.encode("utf-8")), 64 * 1024)
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=preview-long-table.md",
                      wait_until="domcontentloaded", timeout=20000)
            tables = page.locator("article.md-preview table")
            self.assertEqual(tables.count(), 3)
            self.assertEqual(tables.nth(0).locator("tbody tr").count(), 160)
            self.assertEqual(tables.nth(1).locator("tbody tr").count(), 160)
            self.assertEqual(tables.nth(2).locator("tbody tr").count(), 40)
            self.assertEqual(tables.nth(1).locator("thead th").first.inner_text(), "Number")
            self.assertEqual(tables.nth(2).locator("tbody tr").last.locator("td").nth(1).inner_text(), "ROW-360")
            self.assertTrue(page.get_by_role("heading", name="Following section").is_visible())
            paragraphs = page.locator("article.md-preview p").all_inner_texts()
            self.assertFalse(any("| 161 |" in text or "| 321 |" in text for text in paragraphs))
            self.assertIn("Still readable.", paragraphs)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(errors, [])
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


    def test_unsaved_source_moves_across_visual_preview_without_saving(self):
        path = self.root / "draft.md"
        original = "# Draft\n\nOriginal\n"
        draft = "# Draft\n\nUncommitted draft\n"
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        navs = []
        page.on("framenavigated", lambda frame: navs.append(frame.url) if frame == page.main_frame else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=draft.md", wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=12000)
            area.fill(draft)
            page.wait_for_function("() => !!window.__lanternMdVisual?.state?.workHash", timeout=10000)

            page.get_by_role("button", name="Edit visually", exact=True).click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            editor.wait_for(timeout=24000)
            self.assertIn("Uncommitted draft", editor.inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), original)

            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible", timeout=13000)
            self.assertIn("Uncommitted draft", page.locator("article.md-preview").inner_text())
            self.assertEqual(len(navs), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=14000)
            self.assertEqual(area.input_value(), draft)
            self.assertTrue(page.evaluate("() => window.__lanternMdVisual.state.dirty"))
        finally:
            context.close()
    def test_large_source_to_paged_visual_and_back(self):
        path = self.root / "large-switch.md"
        original = "# Large switch\n\n" + "".join(
            "## Section " + str(i) + "\n\n" + ("A" * 450) + "\n\n" for i in range(170)
        )
        self.assertGreater(len(original), 64 * 1024)
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
            "## Section " + str(i) + "\n\n" + ("A" * 450) + "\n\n" for i in range(170)
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

    def test_41_kib_document_opens_entire_visual_not_section_editor(self):
        path = self.root / "41k-complete.md"
        parts = ["# Complete visual file\n\n"]
        for i in range(400):
            part = f"## Section {i}\n\nParagraph {i}: " + (
                "mixed **bold** normal text and Unicode tiếng Việt. " * 3) + "\n\n"
            if len("".join(parts + [part]).encode("utf-8")) >= 41*1024:
                break
            parts.append(part)
        original = "".join(parts) + "\nEND-OF-41K-DOCUMENT\n"
        self.assertGreater(len(original.encode("utf-8")), 40*1024)
        self.assertLess(len(original.encode("utf-8")), 43*1024)
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1200, "height": 850})
        page = context.new_page()
        saves = []
        page.on("request", lambda request: saves.append(request.url)
                if "/api/md/save" in request.url else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=41k-complete.md", wait_until="domcontentloaded")
            self.assertIn("END-OF-41K-DOCUMENT",page.locator("article.md-preview").inner_text())
            page.get_by_role("button",name="Edit visually",exact=True).click()
            page.wait_for_function("""() => window.__lanternMdVisual.state.mode !== 'preview'
                && !window.__lanternMdVisual.state.loading""",timeout=30000)
            self.assertEqual(page.evaluate("window.__lanternMdVisual.state.mode"), "visual")
            self.assertFalse(page.evaluate("!!window.__lanternMdPaged?.active"))
            editor=page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            editor.wait_for(timeout=18000)
            self.assertIn("END-OF-41K-DOCUMENT", editor.inner_text())
            self.assertIn("Section 0",editor.inner_text())
            # Read-only visual mounting must not write even after autosave idle.
            page.wait_for_timeout(2850)
            self.assertEqual(path.read_text(encoding="utf-8"),original)
            self.assertEqual(saves,[])
            print("MD_41K_FULL_VISUAL_LOAD_MS",page.evaluate(
                "window.__lanternMdMetrics.loadMs"),flush=True)
        finally:
            context.close()

    def test_41_kib_visual_conversion_review_shows_complete_end(self):
        path=self.root/"41k-review.md"
        parts=["# Conversion review\n\n| Name | Value |\n| - | :-: |\n| a | b |\n\n"]
        for i in range(400):
            part=f"## Heading {i}\n\nText with **bold** {i} " + (
                "and regular text words with links [here](#anchor). " * 3) + "\n\n"
            if len("".join(parts+[part]).encode("utf-8"))>=41*1024:
                break
            parts.append(part)
        original="".join(parts)+"\nREVIEW-FILE-END-MARKER\n"
        self.assertGreater(len(original.encode()),40*1024)
        self.assertLess(len(original.encode()),43*1024)
        path.write_text(original,encoding="utf-8")
        context=self.browser.new_context()
        page=context.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=41k-review.md",wait_until="domcontentloaded")
            page.get_by_role("button",name="Edit visually",exact=True).click()
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.mode === 'visual' && !window.__lanternMdVisual.state.loading",
                timeout=30000)
            self.assertFalse(page.evaluate("window.__lanternMdVisual.state.roundtripSafe"))
            para=page.locator(".md-visual-host .ProseMirror p").first
            para.click()
            page.keyboard.press("End")
            page.keyboard.type(" EDIT")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.instance.getMarkdown() !== window.__lanternMdVisual.state.lastSaved",
                timeout=5000)
            page.get_by_role("button",name="Save",exact=True).click()
            review=page.locator("dialog.md-format-review")
            review.wait_for(timeout=15000)
            panels=review.locator("pre")
            self.assertEqual(panels.count(),2)
            self.assertIn("REVIEW-FILE-END-MARKER",panels.nth(0).inner_text())
            self.assertIn("REVIEW-FILE-END-MARKER",panels.nth(1).inner_text())
            review.get_by_role("button",name="Keep original / Cancel save").click()
            self.assertEqual(path.read_text(encoding="utf-8"),original)
        finally:
            context.close()


    def test_preview_keeps_source_working_copy_without_restore_prompt(self):
        path = self.root / "discard-source.md"
        original = "# Source draft\n\nKept disk version.\n"
        draft = "# Source draft\n\nUNSAVED-CACHE-MARKER\n"
        path.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        prompts = []
        page.on("dialog", lambda dlg: (prompts.append(dlg.message), dlg.dismiss()))
        try:
            page.goto(self.base + "/api/plugin/preview?p=discard-source.md")
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.fill(draft)
            page.wait_for_function("() => !!window.__lanternMdVisual?.state?.workHash", timeout=10000)

            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible", timeout=12000)
            self.assertIn("UNSAVED-CACHE-MARKER", page.locator("article.md-preview").inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(prompts, [])

            work = page.evaluate("""async () => {
                const r=await fetch('/api/work?p='+encodeURIComponent('discard-source.md'),
                  {cache:'no-store'});
                return await r.json();
            }""")
            self.assertEqual(work["state"], "pending")
            self.assertEqual(work["work"]["content"], draft)

            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for()
            self.assertEqual(area.input_value(), draft)
            self.assertEqual(prompts, [])
        finally:
            context.close()
    def test_declining_old_draft_restoration_forgets_it(self):
        path=self.root/"declined-old-cache.md"
        original="# Clean source\n\nReal disk content.\n"
        path.write_text(original,encoding="utf-8")
        context=self.browser.new_context()
        page=context.new_page()
        prompts=[]
        page.on("dialog",lambda dialog:(prompts.append(dialog.message),dialog.dismiss()))
        try:
            page.goto(self.base+"/api/plugin/preview?p=declined-old-cache.md")
            key=self.base+":declined-old-cache.md"
            page.evaluate("""key => new Promise((resolve,reject)=>{
                const req=indexedDB.open('lantern-md-drafts',1);
                req.onupgradeneeded=()=>req.result.createObjectStore('drafts');
                req.onerror=()=>reject(req.error);
                req.onsuccess=()=>{
                  const db=req.result;
                  const tx=db.transaction('drafts','readwrite');
                  tx.objectStore('drafts').put({
                    content:'# Clean source\\n\\nSTALE-CACHE-CONTENT\\n',
                    version:'old-version',at:Date.now()},key);
                  tx.oncomplete=()=>{db.close();resolve();};
                  tx.onerror=()=>reject(tx.error);
                };
            })""",key)
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for()
            self.assertEqual(area.input_value(),original)
            self.assertEqual(len(prompts),1)
            page.get_by_role("button",name="Preview",exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible")
            page.get_by_role("button",name="Source",exact=True).click()
            area.wait_for()
            self.assertEqual(area.input_value(),original)
            self.assertEqual(len(prompts),1,"Dismissed cache should not prompt again")
        finally:
            context.close()

    def test_paged_confirmed_exit_clears_draft_and_preserves_file(self):
        path=self.root/"discard-paged.md"
        original="# Paged discard\n\nFirst paragraph.\n\n" + "".join(
            f"## Part {i}\n\n" + ("Some original text. " * 32) + "\n\n"
            for i in range(150)
        )
        self.assertGreater(len(original.encode("utf-8")),64*1024)
        path.write_text(original,encoding="utf-8")
        context=self.browser.new_context()
        page=context.new_page()
        prompts=[]
        page.on("dialog",lambda dlg:(prompts.append(dlg.message),dlg.accept()))
        try:
            page.goto(self.base+"/api/plugin/preview?p=discard-paged.md",wait_until="domcontentloaded")
            # Hold backend writes so this specifically tests a dirty exit, not
            # an autosave that happened while Playwright was waiting on IndexedDB.
            page.route("**/api/md/save",lambda route: route.abort())
            page.get_by_role("button",name="Edit visually",exact=True).click()
            page.wait_for_function(
                "() => !!window.__lanternMdPaged?.active && !window.__lanternMdPaged.loadingPage && window.__lanternMdPaged.pageNumber >= 0",
                timeout=30000)
            para=page.locator(".md-visual-host .ProseMirror p").first
            para.click()
            page.keyboard.press("End")
            page.keyboard.type(" UNSAVED-PAGED-MARKER")
            key="paged:"+self.base+":discard-paged.md"
            page.wait_for_function("""key=>new Promise(resolve=>{
                const req=indexedDB.open('lantern-md-drafts',1);
                req.onsuccess=()=>{
                  const db=req.result;
                  const get=db.transaction('drafts','readonly').objectStore('drafts').get(key);
                  get.onsuccess=()=>{resolve(!!get.result?.content?.includes('UNSAVED-PAGED-MARKER'));db.close()};
                };
            })""",arg=key,timeout=7000)
            self.assertTrue(page.evaluate(
                "() => window.__lanternMdPaged.currentText() !== window.__lanternMdPaged.lastSaved"),
                "Changing editor text must be treated as unsaved even if the dirty flag races")
            page.get_by_role("button",name="Preview",exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible",timeout=12000)
            cached=page.evaluate("""key=>new Promise(resolve=>{
                const req=indexedDB.open('lantern-md-drafts',1);
                req.onsuccess=()=>{
                  const db=req.result;
                  const get=db.transaction('drafts','readonly').objectStore('drafts').get(key);
                  get.onsuccess=()=>{resolve(get.result||null);db.close()};
                };
            })""",arg=key)
            self.assertIsNone(cached)
            self.assertEqual(path.read_text(encoding="utf-8"),original)
            self.assertEqual(len(prompts),1)
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

    def test_source_changes_stay_off_disk_until_explicit_save(self):
        initial = "# Save only\n\nOriginal disk text.\n"
        changed = "# Save only\n\nPending browser draft.\n"
        path = self.root / "save-only-source.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1180, "height": 820})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=save-only-source.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(state="visible")
            source.fill(changed)
            page.wait_for_function("() => window.__lanternMdVisual?.state?.dirty === true")
            # Old autosave fired at about 2.4 seconds. Waiting longer proves that
            # typing now persists only to the local recovery draft, not disk.
            page.wait_for_timeout(3400)
            self.assertEqual(path.read_text(encoding="utf-8"), initial)
            self.assertTrue(page.evaluate("() => window.__lanternMdVisual.state.dirty"))

            page.keyboard.press("Control+S")
            page.wait_for_function(
                "() => { const s=window.__lanternMdVisual?.state; return !!s && !s.saving && !s.dirty; }",
                timeout=8000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), changed)
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_source_pending_diff_is_visual_only_and_clears_after_save(self):
        initial = (
            "# Diff review\n"
            "keep\n"
            "delete me\n"
            "anchor\n"
            "change me\n"
            "end\n"
        )
        changed = (
            "# Diff review\n"
            "keep\n"
            "anchor\n"
            "changed\n"
            "end\n"
            "added line\n"
        )
        path = self.root / "source-pending-diff.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1180, "height": 850})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=source-pending-diff.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(state="visible")
            source.fill(changed)
            page.wait_for_function(
                "() => Number(document.documentElement.dataset.mdPendingHunks || 0) >= 3",
                timeout=8000,
            )

            self.assertGreater(page.locator(".md-source-diff-line.md-diff-add").count(), 0)
            self.assertGreater(page.locator(".md-source-diff-line.md-diff-mod").count(), 0)
            deletion = page.locator(".md-source-deletion")
            self.assertGreater(deletion.count(), 0)
            deletion_text = "\n".join(deletion.all_inner_texts())
            self.assertIn("delete me", deletion_text)

            # Diff chrome is outside the draft value and never serializes.
            self.assertEqual(source.input_value(), changed)
            self.assertNotIn("Removed near line", source.input_value())
            self.assertEqual(path.read_text(encoding="utf-8"), initial)

            page.keyboard.press("Control+S")
            page.wait_for_function(
                "() => { const s=window.__lanternMdVisual?.state; return !!s && !s.saving && !s.dirty; }",
                timeout=8000,
            )
            page.wait_for_function(
                "() => Number(document.documentElement.dataset.mdPendingHunks || 0) === 0",
                timeout=5000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), changed)
            self.assertEqual(page.locator(".md-source-deletion").count(), 0)
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_pi_working_copy_merges_with_human_typing_without_touching_disk(self):
        initial = "# Pi merge\nalpha\nbeta\ngamma\nomega\n"
        path = self.root / "pi-working-merge.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1180, "height": 850})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=pi-working-merge.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(state="visible")

            async_write = """async ({text}) => {
              const state=await (await fetch('/api/work?p='+encodeURIComponent('pi-working-merge.md'),
                {cache:'no-store'})).json();
              const response=await fetch('/api/work/write',{
                method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                  path:'pi-working-merge.md',
                  content:text,
                  expectHash:state.work?.hash ?? null,
                  baseVersion:state.saved.version,
                })
              });
              const data=await response.json();
              if(!response.ok)throw new Error(data.error||'work write failed');
              return data;
            }"""

            # Pi turn starts from exactly the flushed editor state.
            work_hash = page.evaluate("() => window.__lanternMdVisual.beginBotTurn()")
            self.assertIsNone(work_hash)
            human = "# Pi merge\nalpha\nHUMAN BETA\ngamma\nomega\n"
            source.fill(human)

            # Pi changes a non-overlapping line in the same working copy.
            pi_work = "# Pi merge\nalpha\nbeta\ngamma\nPI OMEGA\n"
            update = page.evaluate(async_write, {"text": pi_work})
            page.evaluate(
                """async ({hash}) => await window.__lanternMdVisual.onWorkChanged(
                     'pi-working-merge.md',hash,true)""",
                {"hash": update["hash"]},
            )
            merged = "# Pi merge\nalpha\nHUMAN BETA\ngamma\nPI OMEGA\n"
            self.assertEqual(source.input_value(), merged)
            self.assertEqual(path.read_text(encoding="utf-8"), initial)
            working = page.evaluate("""async () =>
              await (await fetch('/api/work?p='+encodeURIComponent('pi-working-merge.md'),
                {cache:'no-store'})).json()""")
            self.assertEqual(working["work"]["content"], merged)

            # New turn: human and Pi modify the same line. Human text wins.
            page.evaluate("() => window.__lanternMdVisual.beginBotTurn()")
            human2 = "# Pi merge\nalpha\nHUMAN BETA\nHUMAN GAMMA\nPI OMEGA\n"
            source.fill(human2)
            pi2 = "# Pi merge\nalpha\nHUMAN BETA\nPI GAMMA\nPI OMEGA\n"
            update2 = page.evaluate(async_write, {"text": pi2})
            page.evaluate(
                """async ({hash}) => await window.__lanternMdVisual.onWorkChanged(
                     'pi-working-merge.md',hash,true)""",
                {"hash": update2["hash"]},
            )
            self.assertEqual(source.input_value(), human2)
            self.assertIn("overlapping hunk", page.locator(".md-visual-status").inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), initial)

            page.keyboard.press("Control+S")
            page.wait_for_function(
                "() => { const s=window.__lanternMdVisual?.state; return !!s && !s.saving && !s.dirty; }",
                timeout=10000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), human2)
            self.assertEqual(errors, [])
        finally:
            context.close()
    def test_dirty_source_can_switch_to_visual_without_saving_real_file(self):
        initial = "# Draft mode switch\n\nOriginal paragraph.\n"
        draft = "# Draft mode switch\n\nPending paragraph.\n"
        path = self.root / "dirty-source-visual.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=dirty-source-visual.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(timeout=12000)
            source.fill(draft)
            page.wait_for_function(
                "() => !!window.__lanternMdVisual?.state?.workHash",
                timeout=10000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), initial)

            page.get_by_role("button", name="Edit visually", exact=True).click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable=true]")
            editor.wait_for(timeout=24000)
            self.assertIn("Pending paragraph.", editor.inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), initial)
            self.assertEqual(page.evaluate("() => window.__lanternMdVisual.state.mode"), "visual")
            self.assertTrue(page.evaluate("() => !!window.__lanternMdVisual.state.workHash"))
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_preview_pending_diff_survives_reload_and_clears_after_save(self):
        baseline = (
            "# Preview diff\n\n"
            "Keep block.\n\n"
            "Old value.\n\n"
            "Stable block.\n\n"
            "Delete me.\n\n"
            "Tail block.\n"
        )
        draft = (
            "# Preview diff\n\n"
            "Keep block.\n\n"
            "New value.\n\n"
            "Stable block.\n\n"
            "Tail block.\n\n"
            "Added end.\n"
        )
        path = self.root / "preview-pending-diff.md"
        path.write_text(baseline, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=preview-pending-diff.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(timeout=12000)
            source.fill(draft)
            page.wait_for_function(
                "() => !!window.__lanternMdVisual?.state?.workHash",
                timeout=10000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), baseline)

            page.get_by_role("button", name="Preview", exact=True).click()
            article = page.locator("article.md-preview")
            article.wait_for(state="visible", timeout=12000)
            article.get_by_text("New value.", exact=True).wait_for(timeout=12000)
            mod = page.locator("article.md-preview .md-preview-diff-mod")
            added = page.locator("article.md-preview .md-preview-diff-add")
            ghost = page.locator("article.md-preview .md-preview-deletion")
            self.assertGreater(mod.count(), 0)
            self.assertIn("New value.", mod.all_inner_texts())
            self.assertGreater(added.count(), 0)
            self.assertTrue(any("Added end." in text for text in added.all_inner_texts()))
            ghost_text = "\n".join(ghost.all_inner_texts())
            self.assertIn("Old value.", ghost_text)
            self.assertIn("Delete me.", ghost_text)
            self.assertEqual(ghost.locator("[data-l]").count(), 0)
            self.assertGreater(
                int(page.evaluate("() => document.documentElement.dataset.mdPendingHunks || '0'")),
                0,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), baseline)

            page.reload(wait_until="domcontentloaded")
            article = page.locator("article.md-preview")
            article.wait_for(state="visible", timeout=12000)
            article.get_by_text("New value.", exact=True).wait_for(timeout=12000)
            self.assertGreater(page.locator("article.md-preview .md-preview-diff-mod").count(), 0)
            self.assertIn(
                "Delete me.",
                "\n".join(page.locator("article.md-preview .md-preview-deletion").all_inner_texts()),
            )
            self.assertEqual(path.read_text(encoding="utf-8"), baseline)

            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(timeout=12000)
            self.assertEqual(source.input_value(), draft)
            page.keyboard.press("Control+S")
            page.wait_for_function(
                "() => { const s=window.__lanternMdVisual?.state; return !!s && !s.saving && !s.dirty && !s.workHash; }",
                timeout=12000,
            )
            page.get_by_role("button", name="Preview", exact=True).click()
            article = page.locator("article.md-preview")
            article.wait_for(state="visible", timeout=12000)
            article.get_by_text("New value.", exact=True).wait_for(timeout=12000)
            self.assertEqual(page.locator("article.md-preview .md-preview-deletion").count(), 0)
            self.assertEqual(page.locator("article.md-preview .md-preview-diff-add").count(), 0)
            self.assertEqual(page.locator("article.md-preview .md-preview-diff-mod").count(), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), draft)
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_working_copy_survives_preview_and_only_save_changes_real_file(self):
        initial = "# Working copy\n\nSaved body\n"
        draft = "# Working copy changed\n\nPending body\n"
        path = self.root / "working-copy-preview.md"
        path.write_text(initial, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=working-copy-preview.md",
                      wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            source = page.get_by_role("textbox", name="Markdown source")
            source.wait_for(timeout=12000)
            source.fill(draft)

            page.wait_for_function(
                "() => !!window.__lanternMdVisual?.state?.workHash",
                timeout=10000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), initial)
            work = page.evaluate("""async () => {
                const r=await fetch('/api/work?p='+encodeURIComponent('working-copy-preview.md'),
                  {cache:'no-store'});
                return await r.json();
            }""")
            self.assertEqual(work["state"], "pending")
            self.assertEqual(work["work"]["content"], draft)

            page.get_by_role("button", name="Preview", exact=True).click()
            page.get_by_role("heading", name="Working copy changed").wait_for(timeout=12000)
            self.assertIn("Pending body", page.locator("article.md-preview").inner_text())
            self.assertEqual(path.read_text(encoding="utf-8"), initial)

            page.get_by_role("button", name="Source", exact=True).click()
            source.wait_for(timeout=12000)
            self.assertEqual(source.input_value(), draft)

            page.keyboard.press("Control+S")
            page.wait_for_function(
                "() => { const s=window.__lanternMdVisual?.state; return !!s && !s.saving && !s.dirty && !s.workHash; }",
                timeout=12000,
            )
            self.assertEqual(path.read_text(encoding="utf-8"), draft)
            clean = page.evaluate("""async () => {
                const r=await fetch('/api/work?p='+encodeURIComponent('working-copy-preview.md'),
                  {cache:'no-store'});
                return await r.json();
            }""")
            self.assertEqual(clean["state"], "clean")
            self.assertIsNone(clean["work"])
            self.assertEqual(errors, [])
        finally:
            context.close()

if __name__ == "__main__":
    unittest.main()

"""Opt-in real Edge acceptance for the offline in-preview Milkdown visual editor.

Run: set LANTERN_E2E=1 && uv run --with-requirements requirements.txt --with playwright python -m unittest -v tests.test_md_visual_e2e
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

ROOT = Path(__file__).resolve().parent.parent


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


    def test_markdown_images_render_in_preview_and_visual_edit_without_rewriting_paths(self):
        folder = self.root / "docs"
        images = folder / "assets"
        images.mkdir(parents=True, exist_ok=True)
        (images / "large.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="2200" height="1500">'
            '<rect width="2200" height="1500" fill="#58a"/></svg>',
            encoding="utf-8")
        content = "# Photos\n\n![Photo](assets/large.svg)\n"
        (folder / "images.md").write_text(content, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 390, "height": 800})
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=docs%2Fimages.md", timeout=15000)
            preview_image = page.locator(".md-preview img").first
            preview_image.wait_for()
            self.assertTrue(preview_image.evaluate("(img) => img.complete && img.naturalWidth === 2200"))
            width = preview_image.evaluate("(img) => img.getBoundingClientRect().width")
            self.assertLessEqual(width, 390, "preview image must fit a narrow viewport")
            self.assertLessEqual(preview_image.evaluate("(img) => img.getBoundingClientRect().right"), 391)
            page.get_by_role("button", name="Edit visually").click()
            page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=30000)
            edit_image = page.locator(".md-visual-host img:not(.ProseMirror-separator)").first
            edit_image.wait_for(timeout=10000)
            self.assertTrue(edit_image.evaluate("(img) => img.complete && img.naturalWidth === 2200"),
                            "visual editor should display same-origin relative Markdown images")
            markdown = page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()")
            self.assertIn("![Photo](assets/large.svg)", markdown,
                          "display-only URL resolution must retain the original image alt and relative path")
            self.assertTrue(page.evaluate("() => window.__lanternMdVisual.state.roundtripSafe"),
                            "ordinary untitled image Markdown must not trigger a lossy-format approval")
            page.wait_for_timeout(2900)
            self.assertEqual((folder / "images.md").read_text(encoding="utf-8"), content)
            # A real save must preserve alt text and the relative URL, not just display it.
            page.locator(".md-visual-host .ProseMirror h1").first.click()
            page.keyboard.press("End")
            page.keyboard.type(" updated")
            page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=15000)
            saved = (folder / "images.md").read_text(encoding="utf-8")
            self.assertIn("# Photos updated", saved)
            self.assertIn("![Photo](assets/large.svg)", saved)
        finally:
            context.close()

    def test_ctrl_v_image_clipboard_creates_real_file_and_durable_markdown(self):
        """Real Edge clipboard write + Ctrl+V; no blob URLs or silently lost data."""
        import re as _re
        from tests.test_image_cache_e2e import png_bytes

        folder = self.root / "paste # 1"
        folder.mkdir(exist_ok=True)
        document = folder / "notes 100%.md"
        document.write_text("# Pasted Photos\n\nClipboard begins here.\n", encoding="utf-8")
        image = png_bytes((12, 90, 220))
        context = self.browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        errors = []
        uploads = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: uploads.append(request.url)
                if "/api/upload?" in request.url else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=paste%20%23%201%2Fnotes%20100%25.md", timeout=16000)
            page.get_by_role("button", name="Edit visually").click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable='true']")
            editor.wait_for(timeout=33000)
            self.assertTrue(page.evaluate("() => window.__lanternMdVisual.state.roundtripSafe"))
            page.evaluate("""async bytes => {
                const blob = new Blob([Uint8Array.from(bytes)], {type:'image/png'});
                await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
            }""", list(image))
            editor.locator("p").first.click()
            page.keyboard.press("Control+V")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.instance.getMarkdown().includes('assets/pasted-')",
                timeout=20000)
            self.assertEqual(len(uploads), 1, uploads)
            page.locator(".md-visual-host img:not(.ProseMirror-separator)").first.wait_for(timeout=10000)
            page.locator(".md-visual-status").filter(has_text=_re.compile(r"^Saved")).wait_for(timeout=15000)
            saved = document.read_text(encoding="utf-8")
            path = _re.search(r"!\[([^\]]*)\]\((assets/pasted-[^)]+\.png)\)", saved)
            self.assertIsNotNone(path, saved)
            self.assertNotIn("blob:", saved)
            self.assertNotIn("data:image", saved)
            assets = list((folder / "assets").glob("*.png"))
            self.assertEqual(len(assets), 1, assets)
            self.assertTrue(assets[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            # Edge re-encodes clipboard images. Pixel content, not byte identity,
            # is the correct invariant across Paint/OS clipboard implementations.
            edit_img = page.locator(".md-visual-host img:not(.ProseMirror-separator)").first
            rgb = edit_img.evaluate("""img => {
                const c=document.createElement('canvas');c.width=1;c.height=1;
                c.getContext('2d').drawImage(img,0,0,1,1);
                return [...c.getContext('2d').getImageData(0,0,1,1).data].slice(0,3);
            }""")
            self.assertEqual(rgb, [12, 90, 220])
            self.assertEqual(path.group(2), "assets/" + assets[0].name)
            self.assertEqual(errors, [], errors)
            # An external reader reopening the Markdown sees the same image.
            page.reload(wait_until="domcontentloaded")
            preview = page.locator(".md-preview img").first
            preview.wait_for(timeout=9000)
            self.assertTrue(preview.evaluate("(img) => img.complete && img.naturalWidth === 40"))
        finally:
            context.close()

    def test_table_add_and_delete_controls_are_clickable(self):
        markdown = (
            "# Table\n\n| First | Second |\n| --- | --- |\n"
            "| A | B |\n| C | D |\n")
        (self.root / "table-actions.md").write_text(markdown, encoding="utf-8")
        context = self.browser.new_context(viewport={"width": 1100, "height": 850})
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=table-actions.md", timeout=15000)
            page.get_by_role("button", name="Edit visually").click()
            page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=30000)
            rows = lambda: page.locator(".md-visual-host .milkdown-table-block table.children tr").count()
            cols = lambda: page.locator(".md-visual-host .milkdown-table-block table.children tr").first.locator("th,td").count()
            before_rows, before_cols = rows(), cols()
            self.assertGreaterEqual(before_rows, 2)
            self.assertEqual(before_cols, 2)
            table_metrics = page.evaluate("""() => {
              const table = document.querySelector('.md-visual-host .milkdown-table-block table.children');
              const wrapper = table.closest('.table-wrapper');
              const cell = table.querySelector('th,td');
              return {
                tableWidth:table.getBoundingClientRect().width,
                wrapperWidth:wrapper.getBoundingClientRect().width,
                font:parseFloat(getComputedStyle(table).fontSize),
                padding:parseFloat(getComputedStyle(cell).paddingLeft),
                overflow:getComputedStyle(wrapper).overflowX
              };
            }""")
            self.assertLessEqual(table_metrics["font"], 13.5, table_metrics)
            self.assertLessEqual(table_metrics["padding"], 9, table_metrics)
            self.assertGreaterEqual(table_metrics["tableWidth"], table_metrics["wrapperWidth"] * 0.95, table_metrics)
            self.assertEqual(table_metrics["overflow"], "visible", table_metrics)
            def hover_cell(row_index, side):
                row = page.locator(".md-visual-host .milkdown-table-block table.children tr").nth(row_index)
                cell = row.locator("th,td").first
                box = cell.bounding_box()
                x = box["x"] + (box["width"] - 2 if side == "right" else box["width"] / 2)
                y = box["y"] + (box["height"] - 2 if side == "bottom" else box["height"] / 2)
                page.mouse.move(x, y)
                page.wait_for_timeout(100)

            # '+' handles appear only while hovering a cell boundary.
            hover_cell(before_rows - 1, "bottom")
            self.assertEqual(page.locator("[data-role='x-line-drag-handle']").first.get_attribute("data-show"), "true")
            page.locator(".md-visual-host [data-role='x-line-drag-handle'] .add-button").first.click(timeout=7000)
            self.assertEqual(rows(), before_rows + 1)
            # '-' appears after selecting the drag handle inside a data row.
            hover_cell(1, "center")
            page.locator(".md-visual-host [data-role='row-drag-handle']").first.click(timeout=7000)
            page.locator(".md-visual-host [data-role='row-drag-handle'] .button-group button").first.click(timeout=7000)
            self.assertEqual(rows(), before_rows)
            hover_cell(1, "right")
            self.assertEqual(page.locator("[data-role='y-line-drag-handle']").first.get_attribute("data-show"), "true")
            page.locator(".md-visual-host [data-role='y-line-drag-handle'] .add-button").first.click(timeout=7000)
            self.assertEqual(cols(), before_cols + 1)
            hover_cell(1, "center")
            page.locator(".md-visual-host [data-role='col-drag-handle']").first.click(timeout=7000)
            page.locator(".md-visual-host [data-role='col-drag-handle'] .button-group button").last.click(timeout=7000)
            self.assertEqual(cols(), before_cols)
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


    def test_crop_image_preserves_original_and_updates_markdown(self):
        from tests.test_image_cache_e2e import png_bytes

        folder = self.root / "crop photos"
        assets = folder / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        original_image = png_bytes((12, 90, 220))
        (assets / "original.png").write_bytes(original_image)
        document = folder / "photos.md"
        original = "# Photos\n\n![Original alt](assets/original.png)\n\nTail.\n"
        document.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=crop%20photos%2Fphotos.md")
            self.assertFalse(page.get_by_role("button", name="Crop image").count())
            page.get_by_role("button", name="Edit visually").click()
            image = page.locator(".md-visual-host img:not(.ProseMirror-separator)").first
            image.wait_for(timeout=18000)
            image.click()
            page.get_by_role("button", name="Crop image", exact=True).click()
            dialog = page.get_by_role("dialog", name="Crop image")
            dialog.wait_for()
            self.assertEqual(document.read_text(encoding="utf-8"), original)
            dialog.get_by_role("button", name="Cancel").click()
            self.assertEqual(list(assets.glob("cropped-*.png")), [])
            image.click()
            page.get_by_role("button", name="Crop image", exact=True).click()
            canvas = page.locator(".md-image-crop-canvas")
            box = canvas.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .15, box["y"] + box["height"] * .15)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .65, steps=8)
            page.mouse.up()
            dialog.get_by_role("button", name="Apply crop").click()
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.instance.getMarkdown().includes('assets/cropped-')",
                timeout=15000)
            page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=18000)
            saved = document.read_text(encoding="utf-8")
            match = re.search(r"!\[Original alt\]\((assets/cropped-[^)]+\.png)\)", saved)
            self.assertIsNotNone(match, saved)
            self.assertIn("Tail.", saved)
            output = folder / match.group(1)
            self.assertTrue(output.is_file())
            self.assertEqual((assets / "original.png").read_bytes(), original_image)
            data = output.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            self.assertGreater(min(width, height), 0)
            self.assertLess(max(width, height), 40)
            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview img").first.wait_for(timeout=14000)
            self.assertEqual(page.locator("article.md-preview img").first.get_attribute("alt"), "Original alt")
            self.assertEqual(errors, [])
        finally:
            context.close()

    def test_crop_paged_visual_preserves_unedited_sections(self):
        from tests.test_image_cache_e2e import png_bytes

        folder = self.root / "crop-paged-apply"
        assets = folder / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        original_image = png_bytes((12, 50, 120))
        (assets / "source.png").write_bytes(original_image)
        document = folder / "paged.md"
        original = "# Large\n\n![Picture](assets/source.png)\n\n" + "".join(
            f"## Part {i}\n\n" + "preserved words " * 55 + "\n\n" for i in range(85))
        self.assertGreater(len(original.encode("utf-8")), 32 * 1024)
        document.write_text(original, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(self.base + "/api/plugin/preview?p=crop-paged-apply%2Fpaged.md")
            page.get_by_role("button", name="Edit visually").click()
            page.wait_for_function("() => window.__lanternMdPaged?.active", timeout=30000)
            image = page.locator(".md-visual-host img:not(.ProseMirror-separator)").first
            image.wait_for(timeout=17000)
            image.click()
            page.get_by_role("button", name="Crop image", exact=True).click()
            page.get_by_role("dialog", name="Crop image").get_by_role("button", name="Apply crop").click()
            page.wait_for_function(
                "() => window.__lanternMdPaged.currentText().includes('assets/cropped-')",
                timeout=17000)
            page.get_by_role("button", name="Save", exact=True).click()
            review = page.get_by_role("button", name="Accept changes & Save")
            try:
                review.wait_for(timeout=1400)
                review.click()
            except Exception:
                pass
            # A late Milkdown display transaction can replace the Saved label;
            # the persisted source/version and clean state are authoritative.
            page.wait_for_function(
                "() => !window.__lanternMdPaged.dirty && window.__lanternMdPaged.source.includes('assets/cropped-')",
                timeout=17000)
            saved = document.read_text(encoding="utf-8")
            match = re.search(r"!\[Picture\]\((assets/cropped-[^)]+\.png)\)", saved)
            self.assertIsNotNone(match, saved)
            self.assertEqual((assets / "source.png").read_bytes(), original_image)
            cropped = (folder / match.group(1)).read_bytes()
            self.assertTrue(cropped.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertLess(int.from_bytes(cropped[16:20], "big"), 40)
            self.assertEqual(saved.split("## Part 84", 1)[1], original.split("## Part 84", 1)[1])
        finally:
            context.close()

    def test_crop_dialog_delete_only_removes_paged_markdown_reference(self):
        from tests.test_image_cache_e2e import png_bytes

        folder = self.root / "crop-paged"
        assets = folder / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        original_image = png_bytes((90, 120, 140))
        (assets / "existing.png").write_bytes(original_image)
        document = folder / "paged.md"
        content = "# Big\n\n![Keep asset](assets/existing.png)\n\n" + "".join(
            f"## Section {i}\n\n" + "Text " * 110 + "\n\n" for i in range(80))
        self.assertGreater(len(content.encode("utf-8")), 32 * 1024)
        document.write_text(content, encoding="utf-8")
        context = self.browser.new_context()
        page = context.new_page()
        deletes = []
        page.on("request", lambda request: deletes.append(request.url)
                if "/api/delete" in request.url else None)
        try:
            page.goto(self.base + "/api/plugin/preview?p=crop-paged%2Fpaged.md")
            page.get_by_role("button", name="Edit visually").click()
            page.wait_for_function("() => window.__lanternMdPaged?.active", timeout=30000)
            image = page.locator(".md-visual-host img:not(.ProseMirror-separator)").first
            image.wait_for(timeout=15000)
            image.click()
            page.get_by_role("button", name="Crop image", exact=True).click()
            page.get_by_role("dialog", name="Crop image").get_by_role("button", name="Delete image").click()
            page.wait_for_function(
                "() => !window.__lanternMdPaged.currentText().includes('assets/existing.png')",
                timeout=12000)
            # Paged editor requires explicit conversion review if the section's
            # original Markdown and Milkdown serialization differ.
            page.get_by_role("button", name="Save", exact=True).click()
            review = page.get_by_role("button", name="Accept changes & Save")
            try:
                review.wait_for(timeout=1400)
                review.click()
            except Exception:
                pass
            page.locator(".md-visual-status").filter(has_text=re.compile(r"^Saved")).wait_for(timeout=18000)
            self.assertEqual((assets / "existing.png").read_bytes(), original_image)
            self.assertEqual(deletes, [])
            self.assertNotIn("![Keep asset]", document.read_text(encoding="utf-8"))
            self.assertIn("## Section 79", document.read_text(encoding="utf-8"))
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

import hashlib
import re
import tempfile
import unittest
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import plugin


EXACT_CSP_PREFIX = "default-src 'none'; script-src 'nonce-"
EXACT_CSP_SUFFIX = "'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:; worker-src 'self' blob:; base-uri 'none'; object-src 'none'; form-action 'none'"


class HtmlAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class MarkdownPreviewTests(unittest.TestCase):
    def render_markdown(self, markdown: str, relative: str = "docs/readme.md") -> str:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8", errors="surrogateescape")
            return plugin.render_preview_page(path, root, app_title="Lantern Test").decode("utf-8", "surrogateescape")

    def render_file(self, suffix: str, body: str) -> str:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / ("sample" + suffix)
            path.write_text(body, encoding="utf-8")
            return plugin.render_preview_page(path, root, app_title="Lantern Test").decode("utf-8", "surrogateescape")

    def audit(self, page: str) -> HtmlAudit:
        parser = HtmlAudit()
        parser.feed(page)
        return parser

    def test_pdf_viewer_is_immediate_escaped_and_uses_native_browser(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "demo & #2026.pdf"
            path.write_bytes(b"%PDF-1.4" + b"X" * (16 * 1024 * 1024))
            with patch.object(plugin, "_pdftotext_bounded", side_effect=AssertionError("No eager text extraction")), \
                 patch.object(plugin, "_read_limited_bytes", side_effect=AssertionError("No eager file reads")):
                page = plugin.render_preview_page(path, root).decode("utf-8")
            audit = self.audit(page)
            frames = [attrs for tag, attrs in audit.tags if tag == "iframe"]
            self.assertEqual(len(frames), 1)
            self.assertEqual(frames[0].get("src"), "/demo%20%26%20%232026.pdf")
            self.assertEqual(frames[0].get("title"), "PDF document")
            metas = [attrs for tag, attrs in audit.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"]
            self.assertEqual(len(metas), 1)
            self.assertIn("frame-src 'self'; ", metas[0]["content"])
            self.assertIn("object-src 'none';", metas[0]["content"])
            self.assertNotIn("http://", frames[0]["src"])
            self.assertNotIn("https://", frames[0]["src"])
            self.assertIn("Extract text (slower)", page)
            self.assertIn("view=text", page)
            self.assertIn('Open PDF in a new tab', page)

    def test_pdf_text_extraction_requires_explicit_view(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "manual.pdf"
            path.write_bytes(b"%PDF-1.4")
            with patch.object(plugin, "_render_pdf", return_value=("PDF preview", "<pre class='text-preview'>hello</pre>")) as extract:
                page = plugin.render_preview_page(path, root, pdf_text=True).decode("utf-8")
            extract.assert_called_once_with(path)
            self.assertNotIn('<iframe', page)
            self.assertNotIn("frame-src 'self'", page)
            self.assertIn('View PDF pages', page)
            self.assertIn("hello", page)

    def test_limited_reader_never_reads_entire_large_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "large.log"
            sample.write_bytes(b"a" * (1024 * 1024))
            from unittest.mock import patch

            # Path.read_bytes() loads the whole file; the reader must use a bounded stream.
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded file read")):
                data, truncated = plugin._read_limited_bytes(sample, 4096)
            self.assertEqual(data, b"a" * 4096)
            self.assertTrue(truncated)

    def test_raw_html_nul_and_adversarial_targets_are_safe(self) -> None:
        page = self.render_markdown(
            "<script src='/owned.js'>boom</script>\n"
            "before\x00after\n"
            "[c0](\x01JaVaScRiPt:alert(1))\n"
            "[entity](&#106;avascript:alert(1))\n"
            "[data](data:text/html,boom)\n"
            "[proto](//evil.example/x)\n"
            "[encoded](%252e%252e%252fsecret.txt)\n"
        )
        self.assertIn("&lt;script src=", page)
        self.assertNotIn("<script src='/owned.js'>", page)
        self.assertIn("beforeafter", page)
        self.assertNotIn("\x00", page)
        audit = self.audit(page)
        hrefs = {attrs.get("href") for tag, attrs in audit.tags if tag == "a"}
        self.assertFalse(any(href and href.lower().startswith(("javascript:", "data:", "vbscript:", "//")) for href in hrefs))

    def test_link_allowlist_and_confined_local_rewrite(self) -> None:
        page = self.render_markdown(
            "[rel](../asset%20one.txt?x=1#frag) "
            "[root](/images/a%20b.png) "
            "[fragment](#section) "
            "[http](http://example.com/a) "
            "[https](https://example.com/b) "
            "[mail](mailto:user@example.com) "
            "[escape](../../outside.txt)"
        )
        hrefs = {attrs.get("href") for tag, attrs in self.audit(page).tags if tag == "a"}
        self.assertIn("/asset%20one.txt?x=1#frag", hrefs)
        self.assertIn("/images/a%20b.png", hrefs)
        self.assertIn("#section", hrefs)
        self.assertIn("http://example.com/a", hrefs)
        self.assertIn("https://example.com/b", hrefs)
        self.assertIn("mailto:user@example.com", hrefs)
        self.assertNotIn("../../outside.txt", hrefs)

    def test_author_images_are_local_only_and_images_parse_before_links(self) -> None:
        page = self.render_markdown(
            "![local](img/a%20b.png)\n"
            "![root](/assets/p.png)\n"
            "![remote](https://example.com/p.png)\n"
            "![data](data:image/svg+xml,<svg/>)\n"
            "![proto](//example.com/p.png)\n"
        )
        images = [attrs for tag, attrs in self.audit(page).tags if tag == "img"]
        self.assertEqual({x.get("src") for x in images}, {"/docs/img/a%20b.png", "/assets/p.png"})
        self.assertTrue(all(x.get("alt") in {"local", "root"} for x in images))
        self.assertFalse(any(tag == "a" and attrs.get("href", "").endswith("img/a%20b.png") for tag, attrs in self.audit(page).tags))

    def test_url_unquotes_and_encodes_exactly_once(self) -> None:
        page = self.render_markdown(
            "[once](./a%20b.txt) "
            "[double](./a%2520b.txt) "
            "[residue](./%252e%252e%252fsecret.txt)"
        )
        hrefs = {attrs.get("href") for tag, attrs in self.audit(page).tags if tag == "a"}
        self.assertIn("/docs/a%20b.txt", hrefs)
        self.assertIn("/docs/a%2520b.txt", hrefs)
        self.assertNotIn("/docs/%252e%252e%252fsecret.txt", hrefs)

    def test_no_base_and_nested_stash_restores_without_internal_tokens(self) -> None:
        page = self.render_markdown("[`x`](u) and **strong**")
        self.assertNotIn("<base", page.lower())
        self.assertNotIn("\x00MD", page)
        self.assertRegex(page, r'<a href="/docs/u"[^>]*><code>x</code></a>')
        self.assertIn("<strong>strong</strong>", page)

    def test_link_label_raw_html_is_escaped_in_block_contexts(self) -> None:
        page = self.render_markdown(
            "# [<meta http-equiv=\"refresh\" content=\"0;url=https://evil.example\">](https://example.com)\n\n"
            "Paragraph [<script>alert(1)</script>](https://example.com)\n\n"
            "- [<img src=x onerror=alert(1)>](https://example.com)\n"
        )
        self.assertNotIn("<meta http-equiv=\"refresh\"", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)
        self.assertIn("&lt;meta http-equiv=&quot;refresh&quot;", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)

    def test_mermaid_fence_creates_safe_container_without_executing_inline_html(self) -> None:
        page = self.render_markdown(
            "```mermaid\n"
            "flowchart TD\n"
            "A[\"<img src=x onerror=alert(1)>\"] --> B[\"</pre><script>alert(2)</script>\"]\n"
            "```\n"
        )
        self.assertIn('class="mermaid-diagram"', page)
        self.assertIn('class="mermaid-source"', page)
        self.assertIn('class="mermaid-output"', page)
        self.assertNotIn("<script>alert(2)</script>", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", page)

    def test_large_gfm_table_renders_completely_in_bounded_chunks(self) -> None:
        rows = 210
        source = (
            "| Col A | Col B |\n"
            "| --- | --- |\n"
            + "".join(f"| r{i} | v{i} |\n" for i in range(rows))
        )
        page = self.render_markdown(source)
        self.assertIn("<td>r0</td>", page)
        self.assertIn("<td>r209</td>", page)
        self.assertNotIn("Table preview stopped", page)
        self.assertGreaterEqual(page.count("<table>"), 2)

    def test_gfm_table_allows_single_column_escaped_pipes_and_code_pipes(self) -> None:
        page = self.render_markdown(
            "| Name | Value |\n"
            "| :--- | ---: |\n"
            r"| escaped \| pipe | `a|b` |" "\n"
        )
        # The Markdown source uses one backslash to escape the cell pipe.
        self.assertIn("<table>", page)
        self.assertIn("<th>Name</th>", page)
        self.assertIn("<td>escaped | pipe</td>", page)
        self.assertIn("<code>a|b</code>", page)
        self.assertEqual(page.count("<table>"), 1)

    def test_gfm_table_continues_past_160_rows_without_raw_markdown(self) -> None:
        # Regression: after 160 data rows, the renderer previously fell out of
        # table mode and displayed all remaining | ... | lines as one paragraph.
        for row_count in (159, 160, 161, 320, 321):
            with self.subTest(rows=row_count):
                source = (
                    "| ID | Parameter |\n"
                    "| --- | :--- |\n"
                    + "".join(f"| {i} | ROW-{i:03d} |\n" for i in range(1, row_count + 1))
                    + "\n## Following heading\n\nAfter the table.\n"
                )
                page = self.render_markdown(source)
                article = page.split("<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
                tables = re.findall(r"<table>(.*?)</table>", article, flags=re.DOTALL)
                expected_tables = (row_count + 159) // 160
                self.assertEqual(len(tables), expected_tables)
                self.assertEqual(article.count("<td>"), row_count * 2)
                self.assertEqual(article.count("<th>"), expected_tables * 2)
                self.assertEqual(article.count("<tbody>"), expected_tables)
                self.assertIn(f"<td>ROW-{row_count:03d}</td>", tables[-1])
                self.assertIn("<h2>Following heading</h2>", article)
                self.assertIn("<p>After the table.</p>", article)
                self.assertNotIn(f"<p>| {row_count} |", article)
                for chunk in tables:
                    self.assertLessEqual(chunk.count("<tr>") - 1, 160)
                if row_count > 160:
                    self.assertIn("<th>ID</th>", tables[-1],
                                  "Continuation table repeats the header")

    def test_large_gfm_table_70_kib_keeps_all_rows_structured_and_escaped(self) -> None:
        # Deliberately larger than the *editor* 64 KiB threshold. Preview
        # should not use that separate threshold or lose its Markdown context.
        rows = 400
        value = "long value " * 18
        source = (
            "# Table near the editor threshold\n\n"
            "| Index | Value | Code |\n"
            "| --- | --- | --- |\n"
            + "".join(
                f"| {i} | {value} ROW-{i:03d} | "
                + (r"escaped \| cell" if i == 161 else
                   "<script>alert(1)</script>" if i == 321 else
                   chr(96) + "a|b" + chr(96))
                + " |\n"
                for i in range(1, rows + 1)
            )
            + "\n## After large table\n\nDone.\n"
        )
        self.assertGreater(len(source.encode("utf-8")), 64 * 1024)
        self.assertLess(len(source.encode("utf-8")), plugin.MAX_PREVIEW_BYTES)
        page = self.render_markdown(source)
        article = page.split("<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        self.assertEqual(article.count("<table>"), 3)
        self.assertEqual(article.count("<tbody>"), 3)
        self.assertEqual(article.count("<td>"), rows * 3)
        self.assertEqual(article.count("<th>"), 9)
        self.assertIn("ROW-160", article)
        self.assertIn("ROW-161", article)
        self.assertIn("ROW-400", article)
        self.assertIn("<td>escaped | cell</td>", article)
        self.assertIn("<code>a|b</code>", article)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", article)
        self.assertNotIn("<script>alert(1)</script>", article)
        self.assertIn("<h2>After large table</h2>", article)
        self.assertNotIn("Preview truncated to keep", article)
        self.assertEqual(article.count("<p>Done.</p>"), 1)
        self.assertNotIn("<p>| 161 |", article)

    def test_table_continuation_stops_at_blank_or_fenced_block(self) -> None:
        first = "| A | B |\n| - | - |\n" + "".join(
            f"| x{i} | {i} |\n" for i in range(164)
        )
        source = (
            first + "\nParagraph after table.\n\n"
            "~~~markdown\n| code | is not table |\n| --- | --- |\n~~~\n\n"
            "| Second | Table |\n| --- | --- |\n| one | two |\n"
        )
        article = self.render_markdown(source).split("<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        self.assertEqual(article.count("<table>"), 3)
        self.assertEqual(article.count("<td>"), (164 + 1) * 2)
        self.assertIn("<p>Paragraph after table.</p>", article)
        self.assertIn("| code | is not table |", article)
        self.assertIn("<td>one</td>", article)

    def test_preview_preserves_underscores_in_identifiers_and_filenames(self) -> None:
        source = (
            "# module_name_with_underscores\n\n"
            "Identifiers: foo_bar_baz, module__name__suffix, my_file_2026.md, "
            "khong_mat_dau_gach_duoi, xin_chao_việt_nam.\n\n"
            "| Filename | Identifier |\n"
            "| --- | --- |\n"
            "| read_me_2026.md | user__id__token |\n\n"
            "_legitimate emphasis_ and __strong emphasis__.\n"
        )
        article = self.render_markdown(source).split(
            "<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        for term in (
            "module_name_with_underscores", "foo_bar_baz",
            "module__name__suffix", "my_file_2026.md",
            "khong_mat_dau_gach_duoi", "xin_chao_việt_nam",
            "read_me_2026.md", "user__id__token",
        ):
            self.assertIn(term, article)
        self.assertIn("<em>legitimate emphasis</em>", article)
        self.assertIn("<strong>strong emphasis</strong>", article)
        self.assertNotIn("<em>bar</em>", article)
        self.assertNotIn("<strong>name</strong>", article)

    def test_preview_escaped_punctuation_is_literal_but_not_markup(self) -> None:
        tick = chr(96)
        source = (
            r"Stars: \*literal\* and underscores: \_literal\_." "\n\n"
            r"Inline escaped: word\_part and word\*part." "\n\n"
            r"Brackets: \[not a link](file.txt)." "\n\n"
            f"Backticks: \\{tick}not code\\{tick} and code: {tick}literal \\_ \\*{tick}.\n\n"
            r"Escaped HTML opener: \<!-- visible as text -->" "\n"
        )
        article = self.render_markdown(source).split(
            "<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        self.assertIn("Stars: *literal* and underscores: _literal_.", article)
        self.assertIn("Inline escaped: word_part and word*part.", article)
        self.assertIn("[not a link](file.txt).", article)
        self.assertIn("Backticks: " + tick + "not code" + tick, article)
        self.assertIn("<code>literal \\_ \\*</code>", article)
        self.assertIn("&lt;!-- visible as text --&gt;", article)
        self.assertNotIn("<em>literal</em>", article)
        self.assertNotIn("<a href=", article)

    def test_preview_hides_only_real_html_comments_not_escape_markup(self) -> None:
        source = (
            "Before<!-- hidden internal comment -->After\n\n"
            "<!-- hidden multi\n"
            "line with _literal_ *markers* -->\n\n"
            "Escapes: \\* and \\_ are visible punctuation.\n\n"
            "Malformed syntax: !<--this is not a HTML comment-->.\n\n"
            "Real markup: <!-- hidden again -->done.\n"
        )
        article = self.render_markdown(source).split(
            "<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        self.assertIn("BeforeAfter", article)
        self.assertIn("Escapes: * and _ are visible punctuation.", article)
        self.assertIn("!&lt;--this is not a HTML comment--&gt;", article)
        self.assertIn("Real markup: done.", article)
        self.assertNotIn("hidden internal comment", article)
        self.assertNotIn("hidden multi", article)
        self.assertNotIn("hidden again", article)

    def test_preview_hides_html_comments_but_keeps_code_examples(self) -> None:
        page = self.render_markdown(
            "Before\n\n"
            "<!-- private note with **bold** -->\n\n"
            "<!--\n"
            "| invisible | table |\n"
            "| --- | --- |\n"
            "| 123 | 456 |\n"
            "-->\n\n"
            "After `<!-- literal inline -->`\n\n"
            "```markdown\n"
            "<!-- literal fenced -->\n"
            "```\n\n"
            "<div onclick='alert(1)'>Unsafe HTML stays escaped</div>\n"
        )
        article = page.split("<article class='md-preview'>", 1)[1].split("</article>", 1)[0]
        self.assertIn("Before", article)
        self.assertIn("After", article)
        self.assertNotIn("private note", article)
        self.assertNotIn("invisible", article)
        self.assertNotIn("<table>", article)
        self.assertIn("&lt;!-- literal inline --&gt;", article)
        self.assertIn("&lt;!-- literal fenced --&gt;", article)
        self.assertIn("&lt;div onclick=", article)
        self.assertNotIn("<div onclick=", article)

    def test_lightweight_table_task_image_and_fence_grammar(self) -> None:
        page = self.render_markdown(
            "| A | B |\n"
            "| --- | :---: |\n"
            "| 1 | **two** |\n\n"
            "- [x] done\n"
            "- [ ] todo\n\n"
            "![pic](pic.png)\n\n"
            "```python\nprint(1)\n```\n"
        )
        self.assertIn("<table", page)
        self.assertIn("<th>A</th>", page)
        self.assertIn("<strong>two</strong>", page)
        self.assertIn('type="checkbox"', page)
        self.assertIn("checked", page)
        self.assertIn('src="/docs/pic.png"', page)
        self.assertIn('data-language="python"', page)

    def test_structural_allowlist_on_adversarial_rendered_html(self) -> None:
        page = self.render_markdown(
            "# Heading\n"
            "<svg onload=alert(1)>\n"
            "[ok](https://example.com/?q=%22x%22&v=1)\n"
            "![ok](img.png)\n"
            "- [x] task\n"
            "```mermaid\nflowchart TD\nA-->B\n```\n"
        )
        allowed_attrs = {
            "html": {"lang"},
            "head": set(),
            "meta": {"charset", "name", "content", "http-equiv"},
            "title": set(),
            "link": {"rel", "href"},
            "style": set(),
            "body": {"data-lantern-chat-kind", "data-lantern-chat-path"},
            "div": {"class", "data-diagram-index", "data-doc-name", "role", "aria-label", "data-l", "hidden", "data-md-edit-actions"},
            "span": {"class", "data-md-status", "role", "aria-live", "hidden"},
            "br": set(),
            "button": {"class", "type", "data-action", "data-diagram-index", "data-path", "hidden", "aria-pressed"},
            "a": {"class", "href", "target", "rel"},
            "article": {"class"},
            "p": {"data-l"},
            "h1": {"data-l"}, "h2": {"data-l"}, "h3": {"data-l"}, "h4": {"data-l"}, "h5": {"data-l"}, "h6": {"data-l"},
            "hr": {"data-l"},
            "blockquote": set(),
            "ul": {"class"}, "ol": {"class"}, "li": {"class", "data-l"},
            "pre": {"class", "data-language", "data-l"},
            "code": set(),
            "table": set(), "thead": set(), "tbody": set(), "tr": {"data-l"}, "th": set(), "td": set(),
            "img": {"src", "alt", "title"},
            "input": {"type", "disabled", "checked", "aria-label"},
            "script": {"src", "nonce", "defer"},
        }
        audit = self.audit(page)
        for tag, attrs in audit.tags:
            self.assertIn(tag, allowed_attrs, f"unexpected tag {tag}")
            self.assertLessEqual(set(attrs), allowed_attrs[tag], f"unexpected attrs on {tag}: {attrs}")
            for key in ("href", "src"):
                value = attrs.get(key)
                if not value:
                    continue
                if tag == "script":
                    self.assertIn(value, {"/static/markdown_preview.js", "/static/vendor/mermaid-11.17.2.min.js", "/static/markdown_table_interactions.js", "/static/markdown_draft_diff.js", "/static/chatbot.js", "/static/markdown_visual_shell.js"})
                elif tag == "img":
                    self.assertTrue(value.startswith("/"), value)
                else:
                    split = urlsplit(value)
                    self.assertIn(split.scheme, {"", "http", "https", "mailto"}, value)
                    if not split.scheme:
                        self.assertTrue(value.startswith(("/", "#")), value)

    def test_exact_nonce_csp_profiles_and_normal_back(self) -> None:
        strict_tail = (
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; worker-src 'self' blob:; base-uri 'none'; object-src 'none'; form-action 'none'"
        )
        markdown_tail = (
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; worker-src 'self' blob:; base-uri 'none'; object-src 'none'; form-action 'none'"
        )
        pdf_tail = (
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; worker-src 'self' blob:; frame-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'"
        )
        markdown = self.render_markdown("# md")
        markdown_again = self.render_markdown("# md")
        text_page = self.render_file(".txt", "plain")
        csv_page = self.render_file(".csv", "a,b\n1,2\n")
        pdf_page = self.render_file(".pdf", "%PDF-1.4")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            with patch.object(plugin, "_render_pdf", return_value=("PDF preview", "<pre>text</pre>")):
                pdf_text_page = plugin.render_preview_page(pdf, root, pdf_text=True).decode("utf-8")

        cases = [
            ("markdown", markdown, markdown_tail),
            ("text", text_page, strict_tail),
            ("csv", csv_page, strict_tail),
            ("pdf-native", pdf_page, pdf_tail),
            ("pdf-text", pdf_text_page, strict_tail),
        ]
        nonces = {}
        for name, page, expected_tail in cases:
            audit = self.audit(page)
            metas = [
                attrs for tag, attrs in audit.tags
                if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
            ]
            self.assertEqual(len(metas), 1, name)
            csp = metas[0].get("content") or ""
            match = re.fullmatch(
                r"default-src 'none'; script-src 'nonce-([^']+)'; " + re.escape(expected_tail),
                csp,
            )
            self.assertIsNotNone(match, f"{name}: {csp}")
            nonce = match.group(1)
            nonces[name] = nonce
            scripts = [attrs for tag, attrs in audit.tags if tag == "script"]
            self.assertGreaterEqual(len(scripts), 1, name)
            self.assertTrue(all(attrs.get("nonce") == nonce for attrs in scripts), name)
            self.assertNotIn("javascript:", page.lower(), name)
            back = [
                attrs for tag, attrs in audit.tags
                if tag == "button" and attrs.get("data-action") == "back"
            ]
            self.assertEqual(len(back), 1, name)
            self.assertEqual(back[0].get("type"), "button", name)

        second = self.audit(markdown_again)
        second_meta = next(
            attrs for tag, attrs in second.tags
            if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
        )
        second_nonce = re.search(r"script-src 'nonce-([^']+)'", second_meta["content"]).group(1)
        self.assertNotEqual(nonces["markdown"], second_nonce)

    def test_same_origin_author_script_is_escaped_and_not_nonce_authorized(self) -> None:
        page = self.render_markdown("<script src='/uploads/owned.js'></script>")
        self.assertIn("&lt;script", page)
        scripts = [attrs for tag, attrs in self.audit(page).tags if tag == "script"]
        self.assertEqual({attrs.get("src") for attrs in scripts}, {"/static/markdown_preview.js", "/static/markdown_table_interactions.js", "/static/markdown_draft_diff.js", "/static/chatbot.js", "/static/markdown_visual_shell.js"})

    def test_mermaid_bundle_is_parser_discovered_only_on_mermaid_pages(self) -> None:
        mermaid_page = self.render_markdown("```mermaid\nflowchart TD\nA-->B\n```\n")
        plain_page = self.render_markdown("# Plain\n\nNo diagram.\n")
        self.assertIn('/static/vendor/mermaid-11.17.2.min.js', mermaid_page)
        self.assertNotIn('/static/vendor/mermaid-11.17.2.min.js', plain_page)

        head_end = mermaid_page.index("</head>")
        vendor_pos = mermaid_page.index('/static/vendor/mermaid-11.17.2.min.js')
        helper_pos = mermaid_page.index('/static/markdown_preview.js')
        self.assertLess(vendor_pos, helper_pos)
        self.assertLess(helper_pos, head_end)

        mermaid_scripts = [attrs for tag, attrs in self.audit(mermaid_page).tags if tag == "script"]
        self.assertEqual(
            [attrs.get("src") for attrs in mermaid_scripts],
            ["/static/vendor/mermaid-11.17.2.min.js", "/static/markdown_preview.js", "/static/markdown_table_interactions.js", "/static/markdown_draft_diff.js", "/static/chatbot.js", "/static/markdown_visual_shell.js"],
        )
        self.assertEqual(
            sum(attrs.get("src") == "/static/vendor/mermaid-11.17.2.min.js" for attrs in mermaid_scripts),
            1,
        )
        self.assertTrue(all(attrs.get("nonce") for attrs in mermaid_scripts))
        self.assertTrue(all("defer" in attrs for attrs in mermaid_scripts))

        plain_scripts = [attrs for tag, attrs in self.audit(plain_page).tags if tag == "script"]
        self.assertEqual([attrs.get("src") for attrs in plain_scripts], ["/static/markdown_preview.js", "/static/markdown_table_interactions.js", "/static/markdown_draft_diff.js", "/static/chatbot.js", "/static/markdown_visual_shell.js"])
        self.assertTrue(plain_scripts[0].get("nonce"))
        self.assertIn("defer", plain_scripts[0])
        self.assertLess(plain_page.index('/static/markdown_preview.js'), plain_page.index("</head>"))

    def test_print_css_keeps_mermaid_diagram_atomic_and_natural_size(self) -> None:
        page = self.render_markdown("## Diagram\n\n```mermaid\nflowchart LR\nA-->B\n```\n")
        self.assertIn(
            ".mermaid-output svg{width:auto!important;max-width:100%!important;max-height:85vh!important;height:auto!important}",
            page,
        )
        self.assertIn(
            ".md-preview h1,.md-preview h2,.md-preview h3{break-after:avoid-page}",
            page,
        )
        self.assertIn(
            ".mermaid-diagram{border:0;padding:0;break-inside:avoid-page;page-break-inside:avoid}",
            page,
        )
        self.assertIn(
            ".mermaid-output svg[aria-roledescription=\"gantt\"] text{font-size:20px!important}",
            page,
        )
        self.assertIn(
            ".mermaid-output svg[aria-roledescription=\"gantt\"] .titleText{font-size:24px!important}",
            page,
        )
        self.assertNotIn("break-before:page", page)

    def test_mermaid_vendor_uses_pinned_tiny_build_and_yielded_warm_parse(self) -> None:
        static = Path(plugin.__file__).resolve().parent / "static"
        asset = static / "vendor" / "mermaid-11.17.2.min.js"
        data = asset.read_bytes()
        self.assertLess(len(data), 2_600_000)
        self.assertIn(b"@mermaid-js/tiny@11.17.2", data[:512])
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd",
        )

        notice = (static / "vendor" / "mermaid-11.17.2.LICENSES.txt").read_text(encoding="utf-8")
        self.assertIn("@mermaid-js/tiny 11.17.2", notice)
        self.assertIn("9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd", notice)
        self.assertIn(
            "sha512-PmFr1c5cSfNf5AngLLR98DrbvR4U5KeD7I+hQkGqG5w5Veu3QT4dG0qu9f99cpn/sKj2XxRBK0q7EL6hr9NY/A==",
            notice,
        )

        helper = (static / "markdown_preview.js").read_text(encoding="utf-8")
        parse_pos = helper.index("await runtime.parse(source);")
        parse_yield_pos = helper.index("await yieldUi();", parse_pos)
        render_pos = helper.index("await runtime.render(", parse_yield_pos)
        self.assertLess(parse_pos, parse_yield_pos)
        self.assertLess(parse_yield_pos, render_pos)

    def test_markdown_helper_clears_opener_before_mermaid_work(self) -> None:
        helper = Path(plugin.__file__).resolve().parent / "static" / "markdown_preview.js"
        source = helper.read_text(encoding="utf-8")
        opener = source.index("window.opener = null")
        mermaid = source.find("mermaid")
        self.assertGreaterEqual(mermaid, 0)
        self.assertLess(opener, mermaid)


if __name__ == "__main__":
    unittest.main()

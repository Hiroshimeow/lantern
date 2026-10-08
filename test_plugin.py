from __future__ import annotations

import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import plugin


EXACT_CSP_PREFIX = "default-src 'none'; script-src 'nonce-"
EXACT_CSP_SUFFIX = "'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'"


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
            "| Label |\n"
            "| --- |\n"
            "| [<style>body{display:none}</style>](https://example.com) |\n\n"
            "[<img src=/probe onerror=alert(1)>](https://example.com)\n\n"
            "[<svg onload=alert(1)>](https://example.com)"
        )
        article_match = re.search(
            r"<article class=['\"]md-preview['\"]>(.*?)</article>",
            page,
            flags=re.S,
        )
        self.assertIsNotNone(article_match)
        audit = self.audit(article_match.group(1))
        injected = [tag for tag, _attrs in audit.tags if tag in {"meta", "style", "img", "svg"}]
        self.assertEqual(injected, [])
        article_html = article_match.group(1)
        for raw in (
            '<meta http-equiv="refresh"',
            "<style>",
            "<img src=/probe onerror=alert(1)>",
            "<svg onload=alert(1)>",
        ):
            self.assertNotIn(raw, article_html)
        self.assertIn("&lt;meta http-equiv=&quot;refresh&quot;", page)
        self.assertIn("&lt;style&gt;body{display:none}&lt;/style&gt;", page)
        self.assertIn("&lt;img src=/probe onerror=alert(1)&gt;", page)
        self.assertIn("&lt;svg onload=alert(1)&gt;", page)

    def test_url_attributes_are_quoted_escaped_after_classification(self) -> None:
        page = self.render_markdown('[mail](mailto:user@example.com?subject="x"&body=y)')
        self.assertIn('href="mailto:user@example.com?subject=&quot;x&quot;&amp;body=y"', page)

    def test_fence_rules_language_metadata_and_unclosed_mermaid(self) -> None:
        page = self.render_markdown(
            "````python extra\n"
            "print('<x>')\n"
            "```\n"
            "~~~\n"
            "```` trailing\n"
            "````\n"
            "\n"
            "```mermaid\n"
            "graph TD; A-->B\n"
        )
        self.assertIn('data-language="python"', page)
        self.assertIn("&lt;x&gt;", page)
        self.assertIn("```", page)
        self.assertIn("~~~", page)
        self.assertNotIn('class="mermaid-diagram"', page)
        self.assertIn("graph TD; A--&gt;B", page)

    def test_mermaid_first_info_token_is_case_insensitive_placeholder(self) -> None:
        page = self.render_markdown(
            "```MeRmAiD title=ignored\n"
            "flowchart TD\nA-->B\n"
            "```\n"
        )
        self.assertIn('class="mermaid-diagram"', page)
        self.assertIn('class="mermaid-source"', page)
        self.assertIn("flowchart TD", page)
        self.assertNotIn('data-language="MeRmAiD"', page)

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
            "style": set(),
            "body": set(),
            "div": {"class", "data-diagram-index", "data-doc-name"},
            "button": {"class", "type", "data-action", "data-diagram-index", "hidden"},
            "a": {"class", "href", "target", "rel"},
            "article": {"class"},
            "p": set(),
            "h1": set(), "h2": set(), "h3": set(), "h4": set(), "h5": set(), "h6": set(),
            "hr": set(),
            "blockquote": set(),
            "ul": {"class"}, "ol": {"class"}, "li": {"class"},
            "pre": {"class", "data-language"},
            "code": set(),
            "table": set(), "thead": set(), "tbody": set(), "tr": set(), "th": set(), "td": set(),
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
                    self.assertIn(value, {"/static/markdown_preview.js", "/static/vendor/mermaid-11.17.2.min.js"})
                elif tag == "img":
                    self.assertTrue(value.startswith("/"), value)
                else:
                    split = urlsplit(value)
                    self.assertIn(split.scheme, {"", "http", "https", "mailto"}, value)
                    if not split.scheme:
                        self.assertTrue(value.startswith(("/", "#")), value)

    def test_exact_nonce_csp_all_scripts_and_normal_back_for_all_preview_kinds(self) -> None:
        pages = [
            self.render_markdown("# md"),
            self.render_file(".txt", "plain"),
            self.render_file(".csv", "a,b\n1,2\n"),
        ]
        for page in pages:
            audit = self.audit(page)
            metas = [attrs for tag, attrs in audit.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"]
            self.assertEqual(len(metas), 1)
            csp = metas[0].get("content") or ""
            match = re.fullmatch(
                r"default-src 'none'; script-src 'nonce-([^']+)'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'",
                csp,
            )
            self.assertIsNotNone(match, csp)
            nonce = match.group(1)
            scripts = [attrs for tag, attrs in audit.tags if tag == "script"]
            self.assertGreaterEqual(len(scripts), 1)
            self.assertTrue(all(attrs.get("nonce") == nonce for attrs in scripts))
            self.assertNotIn("javascript:", page.lower())
            back = [attrs for tag, attrs in audit.tags if tag == "button" and attrs.get("data-action") == "back"]
            self.assertEqual(len(back), 1)
            self.assertEqual(back[0].get("type"), "button")

    def test_same_origin_author_script_is_escaped_and_not_nonce_authorized(self) -> None:
        page = self.render_markdown("<script src='/uploads/owned.js'></script>")
        self.assertIn("&lt;script", page)
        scripts = [attrs for tag, attrs in self.audit(page).tags if tag == "script"]
        self.assertEqual({attrs.get("src") for attrs in scripts}, {"/static/markdown_preview.js"})

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
            ["/static/vendor/mermaid-11.17.2.min.js", "/static/markdown_preview.js"],
        )
        self.assertEqual(
            sum(attrs.get("src") == "/static/vendor/mermaid-11.17.2.min.js" for attrs in mermaid_scripts),
            1,
        )
        self.assertTrue(all(attrs.get("nonce") for attrs in mermaid_scripts))
        self.assertTrue(all("defer" in attrs for attrs in mermaid_scripts))

        plain_scripts = [attrs for tag, attrs in self.audit(plain_page).tags if tag == "script"]
        self.assertEqual([attrs.get("src") for attrs in plain_scripts], ["/static/markdown_preview.js"])
        self.assertTrue(plain_scripts[0].get("nonce"))
        self.assertIn("defer", plain_scripts[0])
        self.assertLess(plain_page.index('/static/markdown_preview.js'), plain_page.index("</head>"))

    def test_markdown_helper_clears_opener_before_mermaid_work(self) -> None:
        helper = Path(plugin.__file__).resolve().parent / "static" / "markdown_preview.js"
        source = helper.read_text(encoding="utf-8")
        opener = source.index("window.opener = null")
        mermaid = source.find("mermaid")
        self.assertGreaterEqual(mermaid, 0)
        self.assertLess(opener, mermaid)


if __name__ == "__main__":
    unittest.main()



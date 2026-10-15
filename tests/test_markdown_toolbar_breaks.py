"""Regression requirements for compact fixed Markdown tools and safe line breaks."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import plugin


class MarkdownToolbarBreaksTests(unittest.TestCase):
    def preview(self, markdown: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.md"
            p.write_text(markdown, encoding="utf-8")
            return plugin.render_preview_page(p, Path(tmp)).decode("utf-8")

    def test_markdown_break_tag_renders_line_break_without_trusting_html(self):
        html = self.preview("Above<br>Below<br />After<br/>End\n\n"
                            "Code `<br>`, escaped \\<br>, entity &lt;br&gt; "
                            "and <img src=x onerror=alert(1)>.")
        self.assertIn("Above<br>Below<br>After<br>End", html)
        self.assertIn("<code>&lt;br&gt;</code>", html)
        self.assertIn("&lt;br&gt;", html)
        self.assertNotIn("<img src=x onerror=alert(1)>", html)

    def test_markdown_edit_actions_are_in_fixed_header_above_mode_row(self):
        html = self.preview("# Header\n\nLong content")
        self.assertIn('class="bar md-bar"', html)
        self.assertIn('class="bar-top"', html)
        self.assertIn('class="bar-bottom"', html)
        self.assertIn('data-action="md-save"', html)
        self.assertIn('data-action="md-download-draft"', html)
        self.assertIn('data-action="md-back-preview"', html)
        self.assertLess(html.index('data-action="print"'), html.index('data-action="md-save"'))
        self.assertLess(html.index('data-action="md-back-preview"'), html.index('class="bar-bottom"'))
        self.assertLess(html.index('class="bar-bottom"'), html.index('data-action="mode-source"'))
        self.assertIn('.bar.md-bar{position:fixed', html)


if __name__ == "__main__":
    unittest.main()

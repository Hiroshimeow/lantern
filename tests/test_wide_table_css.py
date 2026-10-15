"""Static regression contract for wide Markdown table styling.

Real browser layout/overlay tests require Edge/Chromium without a blocking policy.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent

class WideTableStyleTests(unittest.TestCase):
    def test_editor_not_forced_to_squeeze_columns(self):
        css=(ROOT/'static/markdown_visual_shell.css').read_text()
        rule=re.search(r'table\.children\s*\{([^}]+)\}',css).group(1)
        self.assertIn('width:max-content',rule)
        self.assertIn('min-width:100%',rule)
        self.assertNotRegex(rule,r'(?<!-)width:100%;')

    def test_wide_table_scroller_and_cell_minimum(self):
        css=(ROOT/'static/markdown_visual_shell.css').read_text()
        block=list(re.finditer(r'\.md-visual-host \.milkdown \.milkdown-table-block\s*\{([^}]+)\}',css))[-1].group(1)
        self.assertIn('overflow-x:auto',block)
        self.assertIn('max-width:100%',block)
        self.assertIn('min-width:10ch',css)
        self.assertIn('min-width:12ch',css)

    def test_gfm_renderer_keeps_30_columns(self):
        import plugin
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as dir:
            md=Path(dir)/'table.md'
            md.write_text('| '+' | '.join(f'Col {i}' for i in range(30))+' |\n'
              +'| '+' | '.join('---' for i in range(30))+' |\n'
              +'| '+' | '.join(f'Value {i}' for i in range(30))+' |\n')
            title,html=plugin._render_markdown(md,Path(dir))
            self.assertEqual(html.count('<th>'),30)
            self.assertEqual(html.count('<td>'),30)
            self.assertIn('class="table-wrap"',html)

if __name__=='__main__': unittest.main()

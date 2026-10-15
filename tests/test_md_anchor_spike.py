"""Optional renderer anchor mapping without changing legacy Preview output."""
from __future__ import annotations
import html.parser
import re
import tempfile
import time
import unittest
from pathlib import Path
import plugin

class AnchorCollector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__();self.anchors=[]
    def handle_starttag(self, tag, attrs):
        props=dict(attrs)
        if 'data-l' in props:
            self.anchors.append((tag,int(props['data-l'])))

class MarkdownAnchorSpikeTests(unittest.TestCase):
    def render(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'anchors.md';path.write_bytes(content.encode('utf-8'))
            title,baseline=plugin._render_markdown(path,Path(tmp))
            _,anchored=plugin._render_markdown(path,Path(tmp),anchors=True)
        return baseline,anchored

    def test_anchor_page_is_opt_in_and_keeps_default_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'document.md'
            target.write_text('# Title\n\nParagraph.\n',encoding='utf-8')
            default=plugin.render_preview_page(target,Path(tmp)).decode()
            spike=plugin.render_preview_page(target,Path(tmp),anchor_spike=True).decode()
            self.assertNotIn('markdown_anchor_bridge.js',default)
            self.assertNotIn('data-l=',default)
            self.assertIn('/static/markdown_anchor_bridge.js',spike)
            self.assertIn('<h1 data-l="1">Title</h1>',spike)
            self.assertIn('<p data-l="3">Paragraph.</p>',spike)

    def test_fallback_legacy_renderer_exact_without_metadata(self):
        content='# H1\n\nDuplicate text.\n\nDuplicate text.\n\n<!-- secret -->\n\n# H2\n'
        old,new=self.render(content)
        self.assertNotIn('data-l',old)
        self.assertEqual(new.count('data-l'),4)
        self.assertEqual(re.sub(r' data-l="\d+"','',new),old)
        parsed=AnchorCollector();parsed.feed(new)
        self.assertEqual(parsed.anchors,[('h1',1),('p',3),('p',5),('h1',9)])

    def test_table_321_rows_and_fences_have_stable_source_lines(self):
        rows=321
        content='## Title\n\n| N | Value |\n|---|---|\n'+''.join(f'| {i} | item_{i} |\n' for i in range(rows))+'\n~~~mermaid\nflowchart LR\nX-->Y\n~~~\n'
        old,new=self.render(content)
        parsed=AnchorCollector();parsed.feed(new)
        row_lines=[n for tag,n in parsed.anchors if tag=='tr']
        self.assertEqual(row_lines,list(range(5,rows+5)))
        self.assertEqual([n for tag,n in parsed.anchors if tag=='div'][:3],[3,165,325])
        self.assertIn(('div',327),parsed.anchors)
        self.assertEqual(re.sub(r' data-l="\d+"','',new),old)

    def test_crlf_bom_and_multiline_comments_keep_source_line_numbers(self):
        # BOM/CRLF and hidden comments must not shift the line anchors.
        content=("\ufeff# Title\r\n\r\n<!-- hidden\r\nsecret\r\n-->\r\n\r\n"
                 "Paragraph with escaped \\_ and _italic_.\r\n\r\n"
                 "# Next\r\n")
        original, anchored = self.render(content)
        parsed=AnchorCollector(); parsed.feed(anchored)
        self.assertEqual([x for x in parsed.anchors if x[0] in ('h1','p')],
                         [('h1',1),('p',7),('h1',9)])
        self.assertEqual(re.sub(r' data-l="\d+"','',anchored),original)

    def test_size_and_render_time_overhead_under_bounded_budget(self):
        # Controlled median-of-three Python renderer costs; not browser timing.
        payload='# Intro\n\n'+('## Section\n\n' + ('Sentence with _italic_ and some text. ' * 7) + '\n\n')*1100
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'long.md';path.write_text(payload)
            old=plugin._render_markdown(path,Path(tmp))[1]
            new=plugin._render_markdown(path,Path(tmp),anchors=True)[1]
            self.assertLess((len(new)-len(old))/len(old),0.12)
            samples=[]
            for anchored in (False,True):
                times=[]
                for _ in range(7):
                    start=time.perf_counter()
                    plugin._render_markdown(path,Path(tmp),anchors=anchored)
                    times.append(time.perf_counter()-start)
                samples.append(sorted(times)[3])
            print('ANCHOR_SERVER_BENCH',dict(baseMs=round(samples[0]*1000,2),anchoredMs=round(samples[1]*1000,2),htmlOverheadPct=round((len(new)/len(old)-1)*100,2)))

if __name__=='__main__':unittest.main()

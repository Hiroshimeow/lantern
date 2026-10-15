"""Isolated browser DOM regression: no live Lantern server or external requests.

Use LANTERN_BROWSER_UNIT=1 and optionally LANTERN_CHROMIUM=/usr/bin/chromium.
This checks mode-navigation and table pointer behavior with an in-memory editor
adapter; full Crepe E2E remains an independent Windows/Edge acceptance gate.
"""
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('LANTERN_BROWSER_UNIT') == '1', 'set LANTERN_BROWSER_UNIT=1')
class MarkdownInteractionsBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.play = sync_playwright().start()
        kwargs = {'headless': True, 'args': ['--no-sandbox']}
        if os.environ.get('LANTERN_CHROMIUM'):
            kwargs['executable_path'] = os.environ['LANTERN_CHROMIUM']
        cls.browser = cls.play.chromium.launch(**kwargs)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()

    def page(self, markup, source=''):
        page = self.browser.new_page(viewport={'width': 880, 'height': 700})
        page.set_content('<html><head><style>' + (ROOT / 'static/markdown_table_interactions.css').read_text(encoding='utf-8')
                         + (ROOT / 'static/markdown_visual_shell.css').read_text(encoding='utf-8')
                         + '</style></head><body>' + markup + '</body></html>')
        page.evaluate('''source => {
          Object.defineProperty(window, 'sessionStorage', {configurable:true,value:{
            getItem:()=>null, setItem:()=>{}, removeItem:()=>{}
          }});
          Object.defineProperty(window, 'indexedDB', {configurable:true,value:null});
          window.__source=source;
          window.fetch=async url=>({ok:true,json:async()=>({content:window.__source,bytes:new Blob([window.__source]).size,version:'v1'})});
          // Fake the DOM of the Crepe editor to keep this test independent of
          // heavy vendor bundles. No markdown is modified by these transitions.
          window.LanternCrepe={createVisualMarkdown:async (host,content)=>{
            const root=document.createElement('div');root.className='ProseMirror';root.contentEditable='true';
            for(const line of content.split('\\n')) {
              if(!line.trim())continue;
              const h=line.startsWith('# ');
              const item=document.createElement(h?'h1':'p');
              item.textContent=h?line.slice(2):line;
              root.append(item);
            }
            host.append(root);
            return {getMarkdown:()=>content,focus:()=>root.focus(),destroy:()=>root.remove()};
          }};
        }''', source)
        for file in ('markdown_anchor_bridge.js', 'markdown_table_interactions.js', 'markdown_visual_shell.js'):
            page.add_script_tag(content=(ROOT / 'static' / file).read_text(encoding='utf-8'))
        return page

    def test_preview_source_visual_location_without_file_write(self):
        source = '# Intro\n\n' + '\n\n'.join(f'Section {i} content.' for i in range(90)) + '\n'
        body = ''.join(f'<p data-l="{3+i*2}">Section {i} content.</p>' for i in range(90))
        markup = ('<div class="content"><button data-action="mode-preview">Preview</button>'
                  '<button data-action="mode-source">Source</button>'
                  '<button data-action="visual-edit" data-path="sample.md">Edit visually</button>'
                  '<article class="md-preview">' + body + '</article></div>')
        page = self.page(markup, source)
        try:
            page.evaluate('''() => {const p=document.querySelector('[data-l="107"]');
              const r=document.createRange();r.selectNodeContents(p);getSelection().removeAllRanges();getSelection().addRange(r);
            }''')
            page.locator('[data-action="mode-source"]').click()
            page.locator('.md-source-area').wait_for(timeout=3000)
            line = page.evaluate('''() => {let x=document.querySelector('textarea.md-source-area');
              return {line:x.value.slice(0,x.selectionStart).split('\\n').length,selection:x.value.slice(x.selectionStart,x.selectionEnd)}
            }''')
            self.assertEqual(line['line'],107)
            self.assertEqual(line['selection'], 'Section 52 content.')
            page.locator('[data-action="visual-edit"]').click()
            page.locator('.md-visual-host .ProseMirror').wait_for(timeout=3000)
            actual = page.evaluate('''() => {
              const s=getSelection();return s?.toString() || '';
            }''')
            # Source->Visual enters the same source block; the editor should
            # not jump to an unrelated duplicate line.
            self.assertTrue(page.locator('.md-visual-host p').nth(52).is_visible())
            page.locator('[data-action="mode-source"]').click()
            page.locator('.md-source-area').wait_for(timeout=3000)
            result = page.evaluate('''() => {
              const a=document.querySelector('textarea.md-source-area');
              return a.value.slice(0,a.selectionStart).split('\\n').length;
            }''')
            self.assertEqual(result, 107)
            self.assertEqual(page.evaluate('window.__source'), source)
        finally:
            page.close()

    def test_preview_wide_table_drag_and_resizing(self):
        cells = ''.join(f'<th>Column_{i:02d}</th>' for i in range(30))
        values = ''.join(f'<td>Val_{i:02d}</td>' for i in range(30))
        markup = ('<div class="content"><article class="md-preview">'
                  '<div class="table-wrap" style="width:460px"><table><thead><tr>' + cells +
                  '</tr></thead><tbody><tr>' + values + '</tr></tbody></table></div>'
                  '</article></div>')
        page = self.page(markup)
        try:
            pan = page.locator('.lantern-table-pan')
            pan.wait_for(state='visible',timeout=3000)
            initial = page.locator('.table-wrap th').first.bounding_box()
            edge = {'x': initial['x']+initial['width']-3,'y':initial['y']+initial['height']/2}
            page.mouse.move(edge['x'], edge['y'])
            page.mouse.down();page.mouse.move(edge['x']+45,edge['y'],steps=6);page.mouse.up()
            resized = page.locator('.table-wrap th').first.bounding_box()
            self.assertGreater(resized['width'],initial['width']+25)
            b=pan.bounding_box()
            self.assertIsNotNone(b)
            page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2)
            page.mouse.down();page.mouse.move(b['x']-100,b['y']+b['height']/2,steps=5);page.mouse.up()
            scrolled=page.locator('.table-wrap').evaluate('node=>node.scrollLeft')
            self.assertGreater(scrolled,40)
            self.assertEqual(page.locator('.table-wrap th').count(),30)
        finally:
            page.close()

    def test_table_handle_appears_after_delayed_table_mount_and_overflow(self):
        markup = ('<div class="content"><article class="md-preview">'
                  '<div class="table-wrap" style="width:460px"></div>'
                  '</article></div>')
        page = self.page(markup)
        try:
            page.evaluate("""() => {
                const wrapper = document.querySelector('.table-wrap');
                wrapper.innerHTML='<table><thead><tr><th>Short</th></tr></thead></table>';
            }""")
            page.locator('.lantern-table-pan').wait_for(state='attached', timeout=3000)
            self.assertTrue(page.locator('.lantern-table-pan').is_hidden())
            page.evaluate("""() => {
                document.querySelector('.table-wrap thead tr').innerHTML =
                    Array.from({length:30},(_,i)=>'<th>Column '+i+'</th>').join('');
            }""")
            page.locator('.lantern-table-pan').wait_for(state='visible', timeout=3000)
        finally:
            page.close()

    def test_position_restore_failure_keeps_source_editor_open(self):
        markup = ('<div class="content"><button data-action="mode-preview">Preview</button>'
                  '<button data-action="mode-source">Source</button>'
                  '<button data-action="visual-edit" data-path="sample.md">Edit visually</button>'
                  '<article class="md-preview"><p data-l="3">Second paragraph.</p></article></div>')
        page = self.page(markup, '# Title\n\nSecond paragraph.\n')
        try:
            page.evaluate('''() => {
              window.LanternAnchorBridge.restore=async () => { throw Error('synthetic mapping failure') };
            }''')
            page.locator('[data-action="mode-source"]').click()
            page.locator('textarea.md-source-area').wait_for(timeout=3000)
            self.assertTrue(page.evaluate('window.__lanternMdVisual.state.mode === "source"'))
            self.assertTrue(page.locator('article.md-preview').is_hidden())
        finally:
            page.close()

    def test_late_visual_table_mount_keeps_document_outside_resize(self):
        markup = '<div class="content"><article class="md-preview"></article></div>'
        page = self.page(markup, '| A | B |\n|---|---|\n| 1 | 2 |\n')
        try:
            page.evaluate('''() => {
              const host = document.createElement('div');
              host.className='md-visual-host';
              host.innerHTML='<div class="milkdown"><div class="milkdown-table-block" style="width:400px">'
                + '<div class="table-wrapper"><table class="children"><thead><tr>'
                + Array.from({length:20},(_,i)=>'<th>Column '+i+'</th>').join('')
                + '</tr></thead></table></div></div></div>';
              document.querySelector('.content').append(host);
            }''')
            pan = page.locator('.md-visual-host .lantern-table-pan')
            pan.wait_for(state='visible', timeout=3000)
            first = page.locator('.md-visual-host th').first.bounding_box()
            edge_y = first['y'] + first['height'] / 2
            edge_x = first['x'] + first['width'] - 3
            page.mouse.move(edge_x, edge_y)
            page.mouse.down()
            page.mouse.move(edge_x + 34, edge_y, steps=5)
            page.mouse.up()
            after = page.locator('.md-visual-host th').first.bounding_box()
            self.assertGreater(after['width'], first['width'] + 22)
            self.assertEqual(page.locator('.md-visual-host th').count(), 20)
            self.assertEqual(page.evaluate('window.__source'), '| A | B |\n|---|---|\n| 1 | 2 |\n')
        finally:
            page.close()

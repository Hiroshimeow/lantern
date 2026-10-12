"""Isolated Edge E2E for section-virtualized Markdown editing.

LANTERN_E2E=1 uv run --with-requirements requirements.txt --with playwright python -m unittest -v test_md_paged_e2e
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

ROOT=Path(__file__).resolve().parent

def sample(count: int) -> bytes:
    return (''.join(f'## Section {i:05d}\n\nParagraph {i:05d} lorem **bold** words.\n\n'
                    for i in range(count))).encode('utf-8')

@unittest.skipUnless(os.environ.get('LANTERN_E2E')=='1', 'requires LANTERN_E2E=1')
class PagedVisualE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.temp=tempfile.TemporaryDirectory(prefix='lantern-md-pages-')
        cls.root=Path(cls.temp.name)
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.base=f'http://127.0.0.1:{cls.port}'
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/'lan_drive.py'),
                                  '--root',str(cls.root),'--host','127.0.0.1','--port',str(cls.port)],
                                 cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        until=time.monotonic()+12
        while time.monotonic()<until:
            try:
                with urllib.request.urlopen(cls.base+'/api/info',timeout=.5):
                    break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('isolated server did not start')
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(channel='msedge',headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
        cls.proc.terminate()
        try:cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:cls.proc.kill();cls.proc.wait(timeout=5)
        try:cls.temp.cleanup()
        except PermissionError:pass # Windows delayed handle release by msedge/AV

    def open(self, context, path: str):
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(self.base+'/api/plugin/preview?p='+path,wait_until='domcontentloaded',timeout=30000)
        page.get_by_role('button',name='Edit visually').click()
        page.locator('.md-visual-host .ProseMirror[contenteditable=true], .md-oversized-code .cm-content[contenteditable=true]').first.wait_for(timeout=15000)
        return page,errors

    def test_multisection_edit_is_byte_exact_and_navigable(self):
        original=sample(4200)
        (self.root/'long.md').write_bytes(original)
        context=self.browser.new_context()
        try:
            page,errors=self.open(context,'long.md')
            info=page.evaluate("""() => ({
                pages:window.__lanternMdPaged.index.pages.length,
                oversized:window.__lanternMdPaged.index.oversized,
                roundtrip:window.__lanternMdPaged.roundtripSafe,
                first:window.__lanternMdPaged.pageOriginal.slice(0,70)
            })""")
            self.assertGreater(info['pages'],5)
            self.assertEqual(info['oversized'],0)
            self.assertTrue(info['roundtrip'],info)
            editor=page.locator('.md-visual-host .ProseMirror')
            first=editor.locator('p').first
            first.click();page.keyboard.press('End');page.keyboard.type(' MODIFIED')
            page.locator('.md-visual-status').filter(has_text=re.compile(r'^Saved')).wait_for(timeout=15000)
            expected=original.replace(b'Paragraph 00000 lorem **bold** words.',b'Paragraph 00000 lorem **bold** words. MODIFIED',1)
            self.assertEqual((self.root/'long.md').read_bytes(),expected,
                             'unmodified source pages must remain byte-identical')
            page.get_by_role('button',name='Next').click()
            page.locator('.md-page-number').wait_for()
            page.wait_for_timeout(650)
            self.assertEqual(page.evaluate('() => window.__lanternMdPaged.pageNumber'),1)
            self.assertEqual((self.root/'long.md').read_bytes(),expected)
            self.assertEqual(errors,[],str(errors))
        finally:context.close()

    def test_paged_markdown_image_keeps_relative_path_and_alt(self):
        sub = self.root / 'pages'
        assets = sub / 'assets'
        assets.mkdir(parents=True, exist_ok=True)
        (assets / 'wide.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1850" height="900">'
            '<rect width="1850" height="900" fill="navy"/></svg>', encoding='utf-8')
        original = b'# Pictures\n\n![Picture](assets/wide.svg)\n\n' + sample(700)
        (sub / 'large.md').write_bytes(original)
        context = self.browser.new_context(viewport={'width':800,'height':700})
        try:
            page,errors=self.open(context,'pages%2Flarge.md')
            self.assertTrue(page.evaluate('() => window.__lanternMdPaged.active'))
            picture=page.locator('.md-visual-host img:not(.ProseMirror-separator)').first
            picture.wait_for(timeout=13000)
            self.assertTrue(picture.evaluate('(img) => img.complete && img.naturalWidth === 1850'))
            self.assertIn('![Picture](assets/wide.svg)',
                          page.evaluate('() => window.__lanternMdPaged.currentText()'))
            self.assertTrue(page.evaluate('() => window.__lanternMdPaged.roundtripSafe'))
            page.wait_for_timeout(2750)
            self.assertEqual((sub/'large.md').read_bytes(),original)
            self.assertEqual(errors,[])
        finally: context.close()

    def test_two_large_clients_reject_stale_save(self):
        path=self.root/'shared.md';path.write_bytes(sample(1700))
        a=self.browser.new_context();b=self.browser.new_context()
        try:
            pa,ea=self.open(a,'shared.md')
            pb,eb=self.open(b,'shared.md')
            for page,suffix in ((pa,' CLIENT_A'),(pb,' CLIENT_B')):
                p=page.locator('.md-visual-host .ProseMirror p').first
                p.click();page.keyboard.press('End');page.keyboard.type(suffix)
                if page is pa:
                    page.locator('.md-visual-status').filter(has_text=re.compile(r'^Saved')).wait_for(timeout=15000)
                else:
                    page.locator('.md-visual-status').filter(has_text=re.compile(r'^Conflict')).wait_for(timeout=15000)
            data=path.read_text(encoding='utf-8')
            self.assertIn('CLIENT_A',data)
            self.assertNotIn('CLIENT_B',data)
            self.assertTrue(pb.evaluate('() => window.__lanternMdPaged.conflict'))
            self.assertEqual(ea+eb,[])
        finally:a.close();b.close()

    def test_oversized_fence_is_localized_and_preserved(self):
        content='# Fences\n\n```txt\n'+('CODE LINE\n'*9000)+'```\n\n## Following\n\nRegular text.\n'
        path=self.root/'huge.md';path.write_bytes(content.encode('utf-8'))
        context=self.browser.new_context()
        try:
            page,errors=self.open(context,'huge.md')
            self.assertGreater(page.evaluate('() => window.__lanternMdPaged.index.oversized'),0)
            if page.locator('.md-oversized-code .cm-content').count()==0:
                page.get_by_role('button',name='Next').click()
                page.locator('.md-oversized-code .cm-content').wait_for(timeout=14000)
            self.assertTrue(page.locator('.md-oversized-code .cm-content').count()>0)
            self.assertIn('```txt',page.evaluate('() => window.__lanternMdPaged.blockWrap.prefix'))
            viewport=page.evaluate('() => window.__lanternMdPaged.largeEditor.getViewport()')
            self.assertLess(viewport['to']-viewport['from'],90000)
            self.assertEqual(path.read_bytes(),content.encode('utf-8'))
            page.locator('.md-oversized-code .cm-content').click()
            page.keyboard.press('Control+Home')
            page.keyboard.type('EDITED ')
            page.locator('.md-visual-status').filter(has_text=re.compile(r'^Saved')).wait_for(timeout=16000)
            actual=path.read_bytes()
            expected=content.replace('CODE LINE','EDITED CODE LINE',1).encode('utf-8')
            if actual!=expected:
                first=next((i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y),min(len(actual),len(expected)))
                print('OVERSIZED_DIFF='+json.dumps({'actual_bytes':len(actual),'expected_bytes':len(expected),
                       'first_diff':first,'actual':repr(actual[max(0,first-35):first+75]),
                       'expected':repr(expected[max(0,first-35):first+75])}),flush=True)
            self.assertTrue(actual==expected,'saved fenced-block bytes differ')
            self.assertEqual(errors,[])
        finally:context.close()

    def test_large_document_4point9mb_stays_bounded(self):
        content=sample(100_000)
        # Target just under 5 MiB using complete Markdown block boundaries.
        content=content[:4_900_000].rsplit(b'\n\n',1)[0]+b'\n\n'
        path=self.root/'huge-many.md';path.write_bytes(content)
        context=self.browser.new_context()
        try:
            started=time.perf_counter()
            page,errors=self.open(context,'huge-many.md')
            elapsed=time.perf_counter()-started
            metrics=page.evaluate("""() => ({
                pages:window.__lanternMdPaged.index.pages.length,
                max:window.__lanternMdPaged.index.maxPageChars,
                heap:performance.memory?.usedJSHeapSize??null,
                nodes:document.querySelectorAll('.md-visual-host .ProseMirror p').length,
                roundtrip:window.__lanternMdPaged.roundtripSafe,
            })""")
            print('PAGED_4P9_MB='+json.dumps({'seconds':round(elapsed,2),**metrics}),flush=True)
            self.assertLess(elapsed,15,'large document needs viewport-sized render')
            self.assertGreater(metrics['pages'],200)
            self.assertLess(metrics['nodes'],300)
            if metrics['heap']: self.assertLess(metrics['heap'],180_000_000)
            self.assertEqual(path.read_bytes(),content)
            self.assertEqual(errors,[])
        finally:context.close()

if __name__=='__main__':
    unittest.main()

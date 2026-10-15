"""Cross-feature acceptance on a disposable FJP Edge instance only.

The production Lantern process / port 9999 must never be targeted.
"""
from __future__ import annotations
import base64
import os
import unittest
from tests.test_image_cache_e2e import png_bytes


@unittest.skipUnless(os.environ.get('LANTERN_E2E') == '1', 'Edge E2E opt-in')
class LanternVisualFeaturesE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_md_mode_switch_e2e import MarkdownModesE2E
        cls.fixture = MarkdownModesE2E
        cls.fixture.setUpClass()
        cls.root=cls.fixture.root;cls.base=cls.fixture.base;cls.browser=cls.fixture.browser

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def test_crop_overwrite_preserves_path_and_refreshes_viewer(self):
        folder=self.root/'OverwriteTest';folder.mkdir(exist_ok=True)
        target=folder/'original.png';old=png_bytes((19,95,200),size=230);target.write_bytes(old)
        context=self.browser.new_context(viewport={'width':1100,'height':850});page=context.new_page()
        errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
        page.on('dialog',lambda dialog:dialog.accept())
        try:
            page.goto(self.base+'/OverwriteTest/',wait_until='domcontentloaded')
            card=page.locator('.card[data-rel="OverwriteTest/original.png"]')
            card.wait_for(timeout=15000)
            page.evaluate('() => {if(state.previewPane)togglePreviewPane();}')
            card.locator('.card-main').click()
            page.locator('#modal.show.media-image').wait_for()
            # The normal Crop entry point must expose both persistence choices
            # inside the crop dialog, so Overwrite is not a hidden pre-crop mode.
            page.locator('#modalCropBtn').click()
            dialog=page.get_by_role('dialog',name='Crop image')
            dialog.wait_for(timeout=15000)
            page.locator('cropper-handle[action$="-resize"]').first.wait_for(timeout=15000)
            self.assertTrue(dialog.get_by_role('button',name='Save cropped copy').is_visible())
            overwrite=dialog.get_by_role('button',name='Overwrite original')
            self.assertTrue(overwrite.is_visible())

            # Paste a second image like Paint: it becomes a movable/resizable
            # overlay and is flattened into the crop result on persistence.
            pasted=base64.b64encode(png_bytes((235,30,40),size=96)).decode()
            page.evaluate("""encoded => {
              const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
              const file=new File([bytes],'clipboard.png',{type:'image/png'});
              const dt=new DataTransfer();dt.items.add(file);
              const dialog=document.querySelector('.lantern-crop-dialog');
              dialog.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:dt}));
            }""",pasted)
            layer=dialog.locator('.lantern-crop-paste-layer')
            layer.wait_for(state='visible',timeout=8000)
            self.assertTrue(layer.locator('.lantern-crop-paste-resize').is_visible())
            overwrite.click()
            page.wait_for_function(
                "() => !document.querySelector('.lantern-crop-dialog') &&"
                " document.querySelector('#modalBody img')?.src.includes('sha256')",
                timeout=23000)
            self.assertNotEqual(target.read_bytes(),old)
            self.assertEqual(sorted(x.name for x in folder.iterdir()),['original.png'])
            self.assertIn('original.png',page.locator('#modalTitle').inner_text())
            pixel=page.evaluate("""async () => {
              const img=document.querySelector('#modalBody img');await img.decode();
              const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
              const ctx=c.getContext('2d');ctx.drawImage(img,0,0);
              return [...ctx.getImageData(Math.floor(c.width/2),Math.floor(c.height/2),1,1).data];
            }""")
            self.assertGreater(pixel[0],180,pixel)
            self.assertLess(pixel[1],100,pixel)
            self.assertLess(pixel[2],120,pixel)
            self.assertEqual(errors,[])
        finally:context.close()

    def test_two_tabs_stale_crop_overwrite_is_refused(self):
        folder=self.root/'StaleCrop';folder.mkdir(exist_ok=True)
        target=folder/'sample.png';target.write_bytes(png_bytes((11,22,33),size=160))
        context=self.browser.new_context(viewport={'width':1000,'height':800})
        a,b=context.new_page(),context.new_page()
        a.on('dialog',lambda dialog:dialog.accept())
        b.on('dialog',lambda dialog:dialog.accept())
        def begin_crop(page):
            page.goto(self.base+'/StaleCrop/',wait_until='domcontentloaded')
            card=page.locator('.card[data-rel="StaleCrop/sample.png"]');card.wait_for(timeout=15000)
            page.evaluate('() => {if(state.previewPane)togglePreviewPane();}')
            card.locator('.card-main').click()
            page.locator('#modal.show.media-image').wait_for()
            page.locator('#modalCropOverwriteBtn').click()
            dialog=page.get_by_role('dialog',name='Crop image');dialog.wait_for(timeout=15000)
            page.locator('cropper-handle[action$="-resize"]').first.wait_for(timeout=15000)
            return dialog
        try:
            stale=begin_crop(b)
            current=begin_crop(a)
            current.get_by_role('button',name='Overwrite original').click()
            a.wait_for_function("() => document.querySelector('#modalBody img')?.src.includes('sha256')",timeout=23000)
            first_commit=target.read_bytes()
            stale.get_by_role('button',name='Overwrite original').click()
            b.wait_for_function("() => document.querySelector('#toast')?.textContent?.includes('image changed')",timeout=14000)
            self.assertEqual(target.read_bytes(),first_commit)
            self.assertEqual(sorted(p.name for p in folder.iterdir()),['sample.png'])
        finally:context.close()

    def test_30_column_table_horizontal_scroll_and_last_column_controls(self):
        columns=30
        source='# Wide Table\n\n|'+ '|'.join('Column_%02d'%i for i in range(columns))+'|\n'
        source+='|'+'|'.join('---' for _ in range(columns))+'|\n'
        source+='|'+'|'.join('A_%02d'%i for i in range(columns))+'|\n'
        source+='|'+'|'.join('B_%02d'%i for i in range(columns))+'|\n'
        source+='\nNo data should change merely from opening the visual editor.\n'
        target=self.root/'wide-table-e2e.md';target.write_bytes(source.encode())
        for width in (1080,390):
            with self.subTest(width=width):
                context=self.browser.new_context(viewport={'width':width,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                try:
                    page.goto(self.base+'/api/plugin/preview?p=wide-table-e2e.md',wait_until='domcontentloaded')
                    page.get_by_role('button',name='Edit visually').click()
                    table=page.locator('.md-visual-host .milkdown-table-block table.children')
                    table.wait_for(timeout=35000)
                    metrics=page.evaluate('''() => {
                      const root=document.querySelector('.md-visual-host .milkdown-table-block');
                      const scroller=root.querySelector('.table-wrapper');
                      const table=root.querySelector('table.children');
                      const last=table.querySelector('tr:nth-child(2) td:last-child');
                      return {clientWidth:scroller.clientWidth,scrollWidth:scroller.scrollWidth,
                              minCellWidth:Math.round(last.getBoundingClientRect().width),
                              rootOverflowX:getComputedStyle(root).overflowX,
                              rootOverflowY:getComputedStyle(root).overflowY,
                              scrollerOverflowX:getComputedStyle(scroller).overflowX,
                              rect:root.getBoundingClientRect().toJSON()};
                    }''')
                    self.assertGreater(metrics['scrollWidth'],metrics['clientWidth']+400,metrics)
                    self.assertGreater(metrics['minCellWidth'],45,metrics)
                    self.assertEqual(metrics['rootOverflowX'],'visible',metrics)
                    self.assertEqual(metrics['rootOverflowY'],'visible',metrics)
                    self.assertEqual(metrics['scrollerOverflowX'],'auto',metrics)
                    page.evaluate('''() => {const x=document.querySelector('.md-visual-host .milkdown-table-block .table-wrapper');x.scrollLeft=x.scrollWidth;}''')
                    page.wait_for_timeout(300)
                    last=page.locator('.md-visual-host .milkdown-table-block tr:nth-child(2) td:last-child')
                    box=last.bounding_box();self.assertIsNotNone(box)
                    self.assertGreaterEqual(box['x'],0,metrics)
                    self.assertLessEqual(box['x']+box['width'],width+35,metrics)
                    page.mouse.move(box['x']+box['width']-2,box['y']+box['height']/2)
                    page.wait_for_timeout(220)
                    shown=page.locator('[data-role="y-line-drag-handle"]').first.get_attribute('data-show')
                    self.assertEqual(shown,'true',f'Column handle not shown at column 30 ({metrics})')
                    # Activating the existing add-column control must not be
                    # prevented by the horizontal overflow clip.
                    page.locator('.md-visual-host [data-role="y-line-drag-handle"] .add-button').first.click(timeout=7000)
                    new_columns=page.locator('.md-visual-host .milkdown-table-block tr').first.locator('th,td').count()
                    self.assertEqual(new_columns,columns+1)

                    # Adding at the right edge must keep the new last column visible
                    # instead of resetting the nested table scroller to zero.
                    scroll_after_add=page.evaluate("""() => {
                      const x=document.querySelector('.md-visual-host .milkdown-table-block .table-wrapper');
                      return {left:x.scrollLeft,max:x.scrollWidth-x.clientWidth};
                    }""")
                    self.assertLessEqual(abs(scroll_after_add['max']-scroll_after_add['left']),6,scroll_after_add)

                    # Lantern exposes stable table actions instead of depending on
                    # Milkdown's transient drag-handle popover, which is replaced
                    # during wide-table re-renders.
                    last_header=page.locator('.md-visual-host .milkdown-table-block th').last
                    hbox=last_header.bounding_box();self.assertIsNotNone(hbox)
                    page.mouse.click(hbox['x']+hbox['width']/2,hbox['y']+hbox['height']/2)
                    tools=page.locator('.md-table-tools')
                    tools.wait_for(state='visible',timeout=7000)
                    self.assertTrue(tools.get_by_role('button',name='− Col',exact=True).is_visible())
                    tools.get_by_role('button',name='− Col',exact=True).click(timeout=7000)
                    page.wait_for_function(
                        "n => document.querySelector('.md-visual-host .milkdown-table-block tr')?.children.length === n",
                        arg=columns,timeout=7000)
                    self.assertEqual(
                        page.locator('.md-visual-host .milkdown-table-block tr').first.locator('th,td').count(),
                        columns)

                    body_cell=page.locator('.md-visual-host .milkdown-table-block tr:nth-child(2) td').first
                    body_cell.click(timeout=7000)
                    tools.wait_for(state='visible',timeout=7000)
                    rows_before=page.locator('.md-visual-host .milkdown-table-block tr').count()
                    tools.get_by_role('button',name='+ Row',exact=True).click(timeout=7000)
                    page.wait_for_function(
                        "n => document.querySelectorAll('.md-visual-host .milkdown-table-block tr').length === n+1",
                        arg=rows_before,timeout=7000)
                    body_cell=page.locator('.md-visual-host .milkdown-table-block tr:nth-child(2) td').first
                    body_cell.click(timeout=7000)
                    tools.get_by_role('button',name='− Row',exact=True).click(timeout=7000)
                    page.wait_for_function(
                        "n => document.querySelectorAll('.md-visual-host .milkdown-table-block tr').length === n",
                        arg=rows_before,timeout=7000)
                    self.assertEqual(errors,[])
                finally:context.close()
        # Changes above remain local drafts unless explicitly saved.
        self.assertEqual(target.read_bytes(),source.encode())

    def test_preview_anchor_to_source_line_and_visual_block(self):
        source=('# Start\n\nParagraph alpha.\n\n## Middle\n\nUnique alpha section text.\n\n## Ending\n\nEnd of document.\n'
                + ''.join(f'\nExtra paragraph {i}.\n' for i in range(60)))
        target=self.root/'anchor-e2e.md';target.write_bytes(source.encode())
        context=self.browser.new_context(viewport={'width':1000,'height':780});page=context.new_page()
        errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
        try:
            page.goto(self.base+'/api/plugin/preview?p=anchor-e2e.md',wait_until='domcontentloaded')
            para=page.locator('article.md-preview p[data-l="7"]')
            para.wait_for(timeout=8000)
            self.assertIsNotNone(page.evaluate('window.LanternAnchorBridge'))
            expected=page.evaluate('''() => {
              const target=document.querySelector('article.md-preview p[data-l="7"]');
              const pos=target.getBoundingClientRect().top+scrollY;
              let anchor=null;
              for(const offset of [84,95,110,130]){
                scrollTo(0,Math.max(0,pos-offset));
                anchor=window.LanternAnchorBridge.captureViewport(document.querySelector('article.md-preview'));
                if(anchor?.line===7)break;
              }
              return anchor;
            }''')
            self.assertEqual(expected['line'],7,expected)
            page.get_by_role('button',name='Source',exact=True).click()
            textarea=page.locator('textarea.md-source-area');textarea.wait_for(timeout=9000)
            page.wait_for_function('''expectedLine => {
              const x=document.querySelector('textarea.md-source-area');
              return !!x && x.value.slice(0,x.selectionStart).split(String.fromCharCode(10)).length===expectedLine;
            }''', arg=expected['line'], timeout=10000)
            state=textarea.evaluate('x=>({value:x.value,start:x.selectionStart})')
            self.assertEqual(state['value'],source)
            self.assertEqual(source[:state['start']].count('\n')+1,7)
            # A separate selection->Visual action must land in the chosen
            # unique block, never normalize or save the Markdown on toggle.
            page.goto(self.base+'/api/plugin/preview?p=anchor-e2e.md',wait_until='domcontentloaded')
            para=page.locator('article.md-preview p[data-l="7"]')
            para.wait_for(timeout=8000)
            page.evaluate('''() => {
              const p=document.querySelector('article.md-preview p[data-l="7"]');
              const range=document.createRange();range.selectNodeContents(p.firstChild);
              const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
              p.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2,clientX:220,clientY:210}));
            }''')
            page.get_by_role('button',name='Edit selection in Visual').click()
            visual=page.locator('.md-visual-host .ProseMirror')
            visual.wait_for(timeout=35000)
            self.assertTrue(visual.get_by_text('Unique alpha section text.').is_visible())
            self.assertEqual(target.read_bytes(),source.encode())
            self.assertEqual(errors,[])
        finally:context.close()

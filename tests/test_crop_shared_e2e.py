"""Shared Cropper UI in direct image viewer, without loading Milkdown.
Run only with LANTERN_E2E=1; independent loopback Lantern fixture.
"""
import os
import unittest

from tests.test_image_cache_e2e import png_bytes


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class SharedCropBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_md_mode_switch_e2e
        cls.modes = test_md_mode_switch_e2e.MarkdownModesE2E
        cls.modes.setUpClass()
        cls.root = cls.modes.root
        cls.base = cls.modes.base
        cls.browser = cls.modes.browser

    @classmethod
    def tearDownClass(cls):
        cls.modes.tearDownClass()

    def test_standalone_image_viewer_crop_save_as_no_milkdown(self):
        album = self.root / "Gallery"
        album.mkdir(exist_ok=True)
        original = png_bytes((45, 105, 204), size=120)
        (album / "picture.png").write_bytes(original)
        context = self.browser.new_context(viewport={"width": 1120, "height": 900})
        page = context.new_page()
        requests = []
        errors = []
        page.on("request", lambda request: requests.append(request.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(self.base + "/Gallery/", wait_until="domcontentloaded")
            card = page.locator('.card[data-rel="Gallery/picture.png"]')
            card.wait_for(timeout=15000)
            page.evaluate("() => {if(state.previewPane)togglePreviewPane();}")
            card.locator(".card-main").click()
            viewer = page.locator("#modal.show.media-image")
            viewer.wait_for(timeout=8000)
            page.locator("#modalCropBtn").click()
            dialog = page.get_by_role("dialog", name="Crop image")
            dialog.wait_for(timeout=15000)
            handles = page.locator("cropper-handle[action$='-resize']")
            handles.first.wait_for(timeout=16000)
            self.assertEqual(handles.count(), 4)
            stage = page.locator(".lantern-crop-stage")
            self.assertGreater(stage.bounding_box()["height"], 160)
            self.assertEqual((album / "picture.png").read_bytes(), original)

            # Viewer Escape must cancel crop, NOT close viewer.
            page.keyboard.press("Escape")
            dialog.wait_for(state="detached", timeout=7000)
            self.assertTrue(viewer.is_visible())
            self.assertEqual(list(album.glob("*cropped*")), [])

            page.locator("#modalCropBtn").click()
            dialog.wait_for()
            handle = handles.first
            box = handle.bounding_box()
            self.assertIsNotNone(box)
            page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"]/2 + 5, box["y"] + box["height"]/2 + 7, steps=7)
            page.mouse.up()
            # Focus one corner and verify keyboard resize is possible.
            corner=page.locator("cropper-handle[action='nw-resize']")
            corner.focus()
            prior=page.evaluate("() => document.querySelector('cropper-selection').width")
            page.keyboard.press("ArrowRight")
            changed=page.evaluate("() => document.querySelector('cropper-selection').width")
            scale=page.evaluate("() => Math.abs(document.querySelector('cropper-image').$getTransform()[0])")
            self.assertAlmostEqual(abs(changed-prior)/scale,1,delta=.15,
                msg="one arrow key must resize one source pixel, not twice via duplicate handlers")
            self.assertEqual(page.locator("#modalTitle").inner_text(), "picture.png")
            dialog.get_by_role("button", name="Save cropped copy").click()
            page.wait_for_function(
                "() => !!document.querySelector('#modalBody img')?.src.includes('-cropped-')",
                timeout=22000)
            created = list(album.glob("picture-cropped-*.png"))
            self.assertEqual(len(created), 1, created)
            self.assertEqual((album / "picture.png").read_bytes(), original)
            data = created[0].read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(int.from_bytes(data[16:20], "big"), 0)
            self.assertLess(int.from_bytes(data[16:20], "big"), 120)
            self.assertTrue(any("lantern-image-crop.min.js" in url for url in requests))
            self.assertFalse(any("lantern-crepe.min.js" in url for url in requests),
                             "gallery viewer must never load Milkdown")
            self.assertEqual(errors, [], errors)
        finally:
            context.close()

    def test_crop_full_image_initially_and_never_crosses_image_edges(self):
        folder=self.root/"CropBounds"
        folder.mkdir(exist_ok=True)
        source=folder/"edge.png"
        source.write_bytes(png_bytes((72,116,197),size=280))
        context=self.browser.new_context(viewport={"width":1100,"height":860})
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        metrics="""() => {
          const canvas=document.querySelector('cropper-canvas');
          const image=document.querySelector('cropper-image');
          const selection=document.querySelector('cropper-selection');
          if(!canvas||!image||!selection) return null;
          const area=canvas.getBoundingClientRect(),img=image.getBoundingClientRect();
          const sx=canvas.clientWidth/area.width,sy=canvas.clientHeight/area.height;
          return {
            image:{x:(img.left-area.left)*sx,y:(img.top-area.top)*sy,
              w:img.width*sx,h:img.height*sy},
            crop:{x:selection.x,y:selection.y,w:selection.width,h:selection.height}
          };
        }"""
        def contained(m):
            self.assertIsNotNone(m)
            image=m["image"]; crop=m["crop"]
            self.assertGreater(crop["w"],0)
            self.assertGreater(crop["h"],0)
            self.assertGreaterEqual(crop["x"],image["x"]-1,m)
            self.assertGreaterEqual(crop["y"],image["y"]-1,m)
            self.assertLessEqual(crop["x"]+crop["w"],image["x"]+image["w"]+1,m)
            self.assertLessEqual(crop["y"]+crop["h"],image["y"]+image["h"]+1,m)
        try:
            page.goto(self.base+"/CropBounds/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/CropBounds/edge.png',
              'edge.png','CropBounds/edge.png')""")
            page.locator("#modalCropBtn").click()
            page.locator("cropper-selection").wait_for(timeout=14000)
            page.wait_for_function("""() => {
              const s=document.querySelector('cropper-selection');
              return s?.width>100 && s?.height>100;
            }""",timeout=12000)
            page.wait_for_timeout(250)
            initial=page.evaluate(metrics)
            contained(initial)
            self.assertAlmostEqual(initial["crop"]["w"],initial["image"]["w"],delta=1.1)
            self.assertAlmostEqual(initial["crop"]["h"],initial["image"]["h"],delta=1.1)
            # Moving and resizing cannot expand past the displayed pixels.
            page.evaluate("""() => {
              const s=document.querySelector('cropper-selection');
              s.$move(10000,10000);
              s.$resize('nw-resize',-800,-800);
              s.$resize('se-resize',800,800);
            }""")
            page.wait_for_timeout(300)
            contained(page.evaluate(metrics))
            page.get_by_role("dialog",name="Crop image").get_by_role("button",name="−").click()
            page.wait_for_timeout(220)
            contained(page.evaluate(metrics))
            page.get_by_role("dialog",name="Crop image").get_by_role("button",name="Reset").click()
            page.wait_for_timeout(200)
            reset=page.evaluate(metrics)
            contained(reset)
            self.assertAlmostEqual(reset["crop"]["w"],reset["image"]["w"],delta=1.1)
            page.get_by_role("dialog",name="Crop image").get_by_role(
                "button",name="Save cropped copy").click()
            page.wait_for_function(
                "() => !!document.querySelector('#modalBody img')?.src.includes('-cropped-')",
                timeout=15000)
            self.assertEqual(source.read_bytes(),png_bytes((72,116,197),size=280))
            self.assertEqual(errors,[],errors)
        finally:context.close()

    def test_twenty_open_cancel_cycles_release_crop_dom(self):
        folder=self.root/"Cycle"
        folder.mkdir(exist_ok=True)
        (folder/"source.png").write_bytes(png_bytes((40,100,180),size=64))
        context=self.browser.new_context()
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        try:
            page.goto(self.base+"/Cycle/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/Cycle/source.png','source.png','Cycle/source.png')""")
            for _ in range(20):
                page.locator("#modalCropBtn").click()
                dialog=page.get_by_role("dialog",name="Crop image")
                dialog.wait_for(timeout=14000)
                page.locator("cropper-selection").wait_for(timeout=14000)
                dialog.get_by_role("button",name="Cancel").click()
                dialog.wait_for(state="detached",timeout=8000)
                self.assertEqual(page.locator("cropper-canvas").count(),0)
                self.assertEqual(page.locator(".lantern-crop-dialog").count(),0)
                self.assertTrue(page.locator("#modal.show.media-image").is_visible())
            self.assertEqual(errors,[])
            self.assertEqual(list(folder.glob("*cropped*")),[])
        finally:
            context.close()

    def test_mobile_touch_corner_handles_resize(self):
        # Chromium touch emulation on FJP. Browser-specific native devices
        # still require separate manual verification.
        folder=self.root/"Touch"
        folder.mkdir(exist_ok=True)
        (folder/"source.png").write_bytes(png_bytes((80,120,190),size=260))
        context=self.browser.new_context(
            viewport={"width":430,"height":880},device_scale_factor=2,
            is_mobile=True,has_touch=True)
        page=context.new_page()
        try:
            page.goto(self.base+"/Touch/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/Touch/source.png','source.png','Touch/source.png')""")
            page.locator("#modalCropBtn").click()
            handle=page.locator("cropper-handle[action='se-resize']")
            handle.wait_for(timeout=17000)
            box=handle.bounding_box()
            self.assertIsNotNone(box)
            self.assertGreaterEqual(box["width"],30)
            initial=page.evaluate("() => document.querySelector('cropper-selection').width")
            x=box["x"]+box["width"]/2
            y=box["y"]+box["height"]/2
            cdp=context.new_cdp_session(page)
            cdp.send("Input.dispatchTouchEvent",{
                "type":"touchStart","touchPoints":[{"x":x,"y":y,"id":1}]})
            cdp.send("Input.dispatchTouchEvent",{
                "type":"touchMove","touchPoints":[{"x":x-25,"y":y-25,"id":1}]})
            cdp.send("Input.dispatchTouchEvent",{
                "type":"touchEnd","touchPoints":[]})
            page.wait_for_timeout(200)
            after=page.evaluate("() => document.querySelector('cropper-selection').width")
            self.assertLess(after,initial,"dragging a mobile corner must resize the selection")
            self.assertTrue(page.get_by_role("dialog",name="Crop image").is_visible())
            self.assertEqual(list(folder.glob("*cropped*")),[])
        finally:
            context.close()

    def test_side_preview_opens_full_viewer_for_crop(self):
        album = self.root / "Gallery2"
        album.mkdir(exist_ok=True)
        (album / "picture.png").write_bytes(png_bytes((12, 32, 66), size=40))
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(self.base + "/Gallery2/", wait_until="domcontentloaded")
            page.locator('.card[data-rel="Gallery2/picture.png"]').wait_for(timeout=14000)
            # Toggle side preview if initially closed; clicking an image then
            # uses existing side preview and its new Open / Crop action.
            page.evaluate("() => {if(!state.previewPane) togglePreviewPane();}")
            page.locator('.card[data-rel="Gallery2/picture.png"] .card-main').click()
            open_button = page.get_by_role("button", name="Open / Crop")
            open_button.wait_for(timeout=10000)
            open_button.click()
            page.locator("#modal.show.media-image").wait_for(timeout=9000)
            self.assertTrue(page.locator("#modalCropBtn").is_visible())
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

"""Real Edge crop type/orientation/alpha acceptance with optional Pillow fixture.

Opt-in: LANTERN_E2E=1; requires Pillow to generate deterministic inputs.
"""
import os
import unittest
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1" and Image is not None,
                     "Edge + Pillow required for crop format tests")
class CropFormatsE2E(unittest.TestCase):
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

    def crop_viewer(self, relative, filename):
        context = self.browser.new_context(viewport={"width": 1100, "height": 820})
        page = context.new_page()
        page.goto(self.base + "/Formats/", wait_until="domcontentloaded")
        page.evaluate("""(values) => openPreview('image','/Formats/'+values[0],values[0],'Formats/'+values[0])""", [filename])
        page.locator("#modalCropBtn").click()
        page.get_by_role("dialog",name="Crop image").wait_for(timeout=16000)
        page.locator("cropper-selection").wait_for(timeout=16000)
        page.get_by_role("button",name=("Apply crop" if filename.endswith(".bmp") else "Save cropped copy")).click()
        page.wait_for_function(
            "() => !!document.querySelector('#modalBody img')?.src.includes('-cropped-')",
            timeout=25000)
        context.close()
        matches = list((self.root / "Formats").glob(relative))
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def test_exif_orientation_1_to_8_is_baked_into_jpeg_pixels(self):
        folder = self.root / "Formats"
        folder.mkdir(exist_ok=True)
        original = Image.new("RGB", (80, 50), (110, 95, 65))
        draw = ImageDraw.Draw(original)
        draw.rectangle((0, 0, 23, 49), fill=(255, 25, 60))
        draw.rectangle((56, 0, 79, 49), fill=(30, 20, 240))
        for orientation in range(1,9):
            with self.subTest(exif_orientation=orientation):
                filename=f"orient{orientation}.jpg"
                exif=Image.Exif()
                exif[274]=orientation
                original.save(folder/filename,"JPEG",quality=95,exif=exif)
                before=(folder/filename).read_bytes()
                output=self.crop_viewer(f"orient{orientation}-cropped-*.jpg",filename)
                self.assertEqual((folder/filename).read_bytes(),before)
                with Image.open(output) as cropped:
                    self.assertEqual(cropped.format,"JPEG")
                    self.assertTrue(cropped.width>0 and cropped.height>0)
                    if orientation in (5,6,7,8):
                        self.assertGreater(cropped.height,cropped.width)
                    else:
                        self.assertGreater(cropped.width,cropped.height)
                    self.assertNotEqual(cropped.getexif().get(274),orientation,
                                        "new pixels must not carry the old EXIF orientation")

    def test_png_transparency_and_mismatched_extension(self):
        folder=self.root / "Formats"
        folder.mkdir(exist_ok=True)
        src=Image.new("RGBA",(120,100),(180,90,150,120))
        src.save(folder / "alpha.jpg", "PNG")  # Deliberate MIME/path mismatch.
        before=(folder / "alpha.jpg").read_bytes()
        output=self.crop_viewer("alpha-cropped-*.png", "alpha.jpg")
        self.assertEqual((folder / "alpha.jpg").read_bytes(),before)
        with Image.open(output) as cropped:
            self.assertEqual(cropped.format,"PNG")
            self.assertEqual(cropped.mode,"RGBA")
            self.assertEqual(cropped.getpixel((cropped.width//2,cropped.height//2))[3],120)

    def test_static_webp_and_bmp_format_policy(self):
        folder=self.root/"Formats"
        folder.mkdir(exist_ok=True)
        cases=[
            ("webp-lossy.webp","WEBP","RGB","webp"),
            ("webp-lossless.webp","WEBP","RGB","webp"),
            ("webp-alpha.webp","WEBP","RGBA","png"),
            ("bitmap.bmp","BMP","RGB","png"),
        ]
        for filename,format_name,mode,expected_ext in cases:
            with self.subTest(filename=filename):
                color=(35,90,205,122) if mode=="RGBA" else (35,90,205)
                Image.new(mode,(96,70),color).save(
                    folder/filename,format_name,
                    **({"lossless":True} if filename=="webp-lossless.webp" else {}))
                original=(folder/filename).read_bytes()
                stem=filename.rsplit(".",1)[0]
                output=self.crop_viewer(stem+"-cropped-*."+expected_ext,filename)
                self.assertEqual((folder/filename).read_bytes(),original)
                with Image.open(output) as image:
                    self.assertEqual(image.format,{"png":"PNG","webp":"WEBP"}[expected_ext])
                    if mode=="RGBA":
                        self.assertEqual(image.convert("RGBA").getpixel((1,1))[3],122)

    def test_zoom_pan_crop_is_pixel_exact(self):
        folder=self.root/"Formats"
        folder.mkdir(exist_ok=True)
        original=Image.new("RGB",(240,160))
        pixels=original.load()
        for y in range(160):
            for x in range(240):
                pixels[x,y]=((x*13+y*7)%256,(y*17)%256,(x*11)%256)
        original.save(folder/"precision.png","PNG")
        before=(folder/"precision.png").read_bytes()
        context=self.browser.new_context(viewport={"width":1280,"height":900})
        page=context.new_page()
        try:
            page.goto(self.base+"/Formats/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/Formats/precision.png','precision.png','Formats/precision.png')""")
            page.locator("#modalCropBtn").click()
            page.locator("cropper-selection").wait_for(timeout=14000)
            coords=page.evaluate("""async()=>{
                const im=document.querySelector('cropper-image');
                const selection=document.querySelector('cropper-selection');
                await im.$ready();
                im.$zoom(.35);
                im.$move(13,-7);
                await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                const canvas=im.closest('cropper-canvas');
                const area=canvas.getBoundingClientRect(),box=im.getBoundingClientRect();
                const dx=canvas.clientWidth/area.width,dy=canvas.clientHeight/area.height;
                const x=(box.left-area.left)*dx,y=(box.top-area.top)*dy;
                const sx=box.width*dx/240,sy=box.height*dy/160;
                selection.$change(x+40*sx,y+30*sy,90*sx,70*sy);
                return [sx,sy,selection.x,selection.y,selection.width,selection.height];
            }""")
            page.get_by_role("button",name="Save cropped copy").click()
            page.wait_for_function(
                "() => !!document.querySelector('#modalBody img')?.src.includes('-cropped-')",
                timeout=20000)
            self.assertEqual((folder/"precision.png").read_bytes(),before)
            outputs=list(folder.glob("precision-cropped-*.png"))
            self.assertEqual(len(outputs),1)
            with Image.open(outputs[0]) as result:
                self.assertEqual(result.size,(90,70),coords)
                expected=original.crop((40,30,130,100))
                self.assertEqual(result.convert("RGB").tobytes(),expected.tobytes(),
                    "full-resolution crop must not resample or shift pixels after zoom/pan")
        finally:
            context.close()

    def test_animated_png_and_webp_are_rejected_without_upload(self):
        folder=self.root/"Formats"
        folder.mkdir(exist_ok=True)
        cases=[("animated.png","PNG"),("animated.webp","WEBP")]
        for filename,format_name in cases:
            with self.subTest(filename=filename):
                first=Image.new("RGBA",(90,64),(210,40,60,255))
                second=Image.new("RGBA",(90,64),(40,210,60,255))
                try:
                    first.save(folder/filename,format_name,save_all=True,
                               append_images=[second],duration=[100,100],loop=0)
                except (OSError,ValueError) as error:
                    self.skipTest(f"Pillow cannot encode animated {format_name}: {error}")
                with Image.open(folder/filename) as check:
                    self.assertTrue(getattr(check,"is_animated",False),filename)
                context=self.browser.new_context()
                page=context.new_page()
                try:
                    page.goto(self.base+"/Formats/",wait_until="domcontentloaded")
                    page.evaluate("""name=>openPreview('image','/Formats/'+name,name,'Formats/'+name)""",filename)
                    page.locator("#modalCropBtn").click()
                    dialog=page.get_by_role("dialog",name="Crop image")
                    dialog.wait_for(timeout=16000)
                    dialog.locator(".lantern-crop-status").filter(has_text="Animated").wait_for(timeout=14000)
                    self.assertTrue(dialog.get_by_role("button",name="Save cropped copy").is_disabled())
                    self.assertEqual(list(folder.glob(filename.rsplit('.',1)[0]+"-cropped-*")),[])
                finally:
                    context.close()

    def test_output_over_20mib_is_rejected_without_asset(self):
        folder=self.root/"Formats"
        folder.mkdir(exist_ok=True)
        width,height=4000,3000
        # Three independent noisy RGB planes resist lossless compression.
        channel=[Image.effect_noise((width,height),100) for _ in range(3)]
        image=Image.merge("RGB",tuple(channel))
        target=folder/"noisy.png"
        image.save(target,"PNG")
        page_context=self.browser.new_context(viewport={"width":1180,"height":850})
        page=page_context.new_page()
        try:
            page.goto(self.base+"/Formats/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/Formats/noisy.png','noisy.png','Formats/noisy.png')""")
            # Large PNG may be rejected at the image-version preflight,
            # before the crop dialog, rather than only at export.
            preflight=page.evaluate("""async() => (await fetch('/api/image/version?p=Formats/noisy.png')).status""")
            page.locator("#modalCropBtn").click()
            if preflight == 413:
                page.wait_for_timeout(250)
                self.assertEqual(page.get_by_role("dialog",name="Crop image").count(),0)
                self.assertEqual(list(folder.glob("noisy-cropped-*")),[])
                self.assertEqual(target.read_bytes()[:4],bytes([137,80,78,71]))
                return
            self.assertEqual(preflight,200)
            dialog=page.get_by_role("dialog",name="Crop image")
            dialog.wait_for(timeout=20000)
            page.locator("cropper-selection").wait_for(timeout=22000)
            dialog.get_by_role("button",name="Save cropped copy").click()
            dialog.locator(".lantern-crop-status").filter(has_text="20 MiB").wait_for(timeout=30000)
            self.assertEqual(list(folder.glob("noisy-cropped-*")),[])
            self.assertEqual(target.read_bytes()[:8],b"\x89PNG\r\n\x1a\n")
        finally:
            page_context.close()

    def test_gif_cannot_crop_or_write_new_asset(self):
        folder=self.root / "Formats"
        folder.mkdir(exist_ok=True)
        frame=Image.new("RGB",(48,48),(50,80,125))
        frame.save(folder/"moving.gif","GIF",save_all=True,append_images=[
            Image.new("RGB",(48,48),(180,130,80))],duration=100,loop=0)
        context=self.browser.new_context()
        page=context.new_page()
        try:
            page.goto(self.base+"/Formats/",wait_until="domcontentloaded")
            page.evaluate("""() => openPreview('image','/Formats/moving.gif','moving.gif','Formats/moving.gif')""")
            page.locator("#modalCropBtn").click()
            dialog=page.get_by_role("dialog",name="Crop image")
            dialog.wait_for(timeout=14000)
            dialog.locator(".lantern-crop-status").filter(has_text="Crop supports").wait_for(timeout=13000)
            self.assertTrue(dialog.get_by_role("button",name="Apply crop").is_disabled())
            self.assertEqual(list(folder.glob("moving-cropped-*")),[])
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()

"""Opt-in performance/correctness smoke on real Edge and 4K/8K/50MP JPEG.

Run with LANTERN_E2E=1 LANTERN_CROP_PERF=1 and Pillow installed.
Measurements are environment-specific, not universal performance guarantees.
"""
import json
import os
import time
import unittest

@unittest.skipUnless(
    os.environ.get("LANTERN_E2E")=="1" and os.environ.get("LANTERN_CROP_PERF")=="1",
    "Explicit opt-in to large-image Edge benchmark")
class CropPerformanceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_md_mode_switch_e2e
        cls.modes=test_md_mode_switch_e2e.MarkdownModesE2E
        cls.modes.setUpClass()
        cls.root=cls.modes.root
        cls.base=cls.modes.base
        cls.browser=cls.modes.browser

    @classmethod
    def tearDownClass(cls):
        cls.modes.tearDownClass()

    def test_edge_decode_pan_zoom_export_4k_8k_50mp(self):
        from PIL import Image, ImageDraw
        folder=self.root/"CropBench"
        folder.mkdir(exist_ok=True)
        samples=[("4k",(3840,2160)),("8k",(7680,4320)),("50mp",(10000,5000))]
        measurements=[]
        for label,(w,h) in samples:
            image=Image.new("RGB",(w,h),(88,152,208))
            draw=ImageDraw.Draw(image)
            draw.rectangle((w//5,h//5,w//3,h//3),fill=(224,28,84))
            target=folder/(label+".jpg")
            image.save(target,"JPEG",quality=88)
            image.close()
            context=self.browser.new_context(viewport={"width":1280,"height":920})
            page=context.new_page()
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            start=time.monotonic()
            try:
                page.goto(self.base+"/CropBench/",wait_until="domcontentloaded",timeout=20000)
                page.evaluate("""name=>openPreview('image','/CropBench/'+name+'.jpg',name+'.jpg','CropBench/'+name+'.jpg')""",label)
                page.locator("#modalCropBtn").click()
                page.locator("cropper-selection").wait_for(timeout=55000)
                load=time.monotonic()-start
                bench=page.evaluate("""async()=>{
                  const s=document.querySelector('cropper-selection');
                  const im=document.querySelector('cropper-image');
                  const frames=[];
                  for(let i=0;i<90;i++){
                    const before=performance.now();
                    s.$move(i%2===0?1:-1,0);
                    await new Promise(r=>requestAnimationFrame(r));
                    frames.push(performance.now()-before);
                  }
                  frames.sort((a,b)=>a-b);
                  im.$zoom(.15);
                  await new Promise(r=>requestAnimationFrame(r));
                  return {p50FrameMs:frames[Math.floor(frames.length*.5)],
                          p95FrameMs:frames[Math.floor(frames.length*.95)],
                          maxFrameMs:frames.at(-1),
                          canvasWidth:im.getBoundingClientRect().width,
                          matrix:im.$getTransform(),
                          selection:[s.x,s.y,s.width,s.height],
                          sourceDimensions:[im.$image.naturalWidth,im.$image.naturalHeight],
                          jsHeapBytes:performance.memory?.usedJSHeapSize??null};
                }""")
                print("CROP_BENCH_BEFORE_APPLY="+json.dumps({"case":label,"bench":bench}),flush=True)
                start_save=time.monotonic()
                page.get_by_role("button",name="Apply crop").click()
                try:
                    page.wait_for_function("""() => !!document.querySelector('#modalBody img')?.src.includes('-cropped-')""",timeout=25000)
                except Exception:
                    print("CROP_BENCH_ERROR="+json.dumps({"case":label,"status":page.evaluate(
                        "() => ({crop:document.querySelector('.lantern-crop-status')?.innerText,toast:document.querySelector('.toast')?.innerText, title:document.querySelector('#modalTitle')?.textContent, dim:document.querySelector('.lantern-crop-size')?.innerText})")},ensure_ascii=False),flush=True)
                    raise
                save=time.monotonic()-start_save
                copies=list(folder.glob(label+"-cropped-*.jpg"))
                self.assertEqual(len(copies),1,copies)
                self.assertTrue(copies[0].read_bytes().startswith(b"\xff\xd8\xff"))
                with Image.open(copies[0]) as cropped:
                    self.assertLess(cropped.width,w)
                    self.assertLess(cropped.height,h)
                    self.assertGreater(min(cropped.width,cropped.height),0)
                self.assertEqual(target.stat().st_size,target.read_bytes().__len__())
                self.assertEqual(errors,[],errors)
                measurements.append({"case":label,"pixels":w*h,"loadSeconds":round(load,3),
                                     "applySeconds":round(save,3),"fileBytes":copies[0].stat().st_size,**bench})
            finally:
                context.close()
        print("CROP_BENCH_FJP="+json.dumps(measurements,ensure_ascii=False),flush=True)


if __name__=="__main__":
    unittest.main()

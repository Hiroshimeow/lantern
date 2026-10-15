"""Safe in-place image overwrite. Runs an isolated server without a browser."""
from __future__ import annotations
import concurrent.futures
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from tests.test_image_cache_e2e import png_bytes

ROOT = Path(__file__).resolve().parents[1]

class CropOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        self.base=f'http://127.0.0.1:{port}'
        self.proc = subprocess.Popen([sys.executable,str(ROOT/'lan_drive.py'),
                     '--root',str(self.root),'--host','127.0.0.1','--port',str(port)],
                     cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for i in range(120):
            try:
                with urllib.request.urlopen(self.base+'/api/info',timeout=.3):break
            except Exception:
                if self.proc.poll() is not None:self.fail('Lantern stopped')
                time.sleep(.05)
        else:self.fail('Lantern failed to boot')
        self.orig=png_bytes((10,20,30))
        self.new=png_bytes((40,50,60))
        (self.root/'photo.png').write_bytes(self.orig)

    def tearDown(self):
        self.proc.terminate()
        try:self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=5)
        # Windows image/HTTP handles can linger briefly after server exit.
        # Retry only on an observed sharing violation; never hide a leak.
        for attempt in range(25):
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                if attempt == 24:
                    raise
                time.sleep(0.12)

    def request(self,method,endpoint,body=None,headers=None):
        req=urllib.request.Request(self.base+endpoint,data=body,method=method,headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=8) as res:return res.status,json.load(res)
        except urllib.error.HTTPError as exc:
            with exc:
                try:return exc.code,json.load(exc)
                except ValueError:return exc.code,{'error':str(exc)}

    def version(self):
        status,obj=self.request('GET','/api/image/version?p=photo.png')
        self.assertEqual(status,200,obj)
        return obj['version']

    def overwrite(self,data,expected,name='photo.png',ctype='image/png'):
        return self.request('POST','/api/image/overwrite?p='+urllib.parse.quote(name),
                         data,{'If-Match':expected,'Content-Type':ctype})

    def test_viewer_preserves_save_as_and_offers_separate_overwrite(self):
        with urllib.request.urlopen(self.base+'/',timeout=3) as response:
            page=response.read().decode('utf-8')
        self.assertIn('id="modalCropBtn"',page)
        self.assertIn('id="modalCropOverwriteBtn"',page)
        self.assertIn('onclick="cropViewedImage(true)"',page)
        self.assertIn('async function cropViewedImage(overwriteOriginal=false)',page)
        self.assertIn('original image?',page)

    def test_success_changes_original_without_new_file_and_cas(self):
        expected=self.version()
        status,result=self.overwrite(self.new,expected)
        self.assertEqual(status,200,result)
        self.assertEqual((self.root/'photo.png').read_bytes(),self.new)
        self.assertNotEqual(self.version(),expected)
        self.assertEqual(sorted(x.name for x in self.root.iterdir()),['photo.png'])
        status,result=self.overwrite(self.orig,expected)
        self.assertEqual(status,409,result)
        self.assertEqual((self.root/'photo.png').read_bytes(),self.new)

    def test_same_length_external_changes_are_detected(self):
        expected=self.version()
        changed=png_bytes((70,80,90))
        self.assertEqual(len(changed),len(self.orig))
        (self.root/'photo.png').write_bytes(changed)
        status,result=self.overwrite(self.new,expected)
        self.assertEqual(status,409,result)
        self.assertEqual((self.root/'photo.png').read_bytes(),changed)

    def test_concurrent_same_version_exactly_one_success(self):
        expected=self.version()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(self.overwrite,png_bytes((i,11,22)),expected) for i in range(1,9)]
            results=[f.result() for f in futures]
        self.assertEqual([code for code,_ in results].count(200),1,results)
        self.assertEqual([code for code,_ in results].count(409),7,results)
        self.assertEqual(list(self.root.glob('.lantern-uploading-*')),[])

    def test_mime_and_bytes_mismatch_no_change(self):
        expected=self.version()
        for payload,ctype in [(b'not an image'*5,'image/png'),
                  (self.new,'image/jpeg'),(b'BM'+bytes(50),'image/png')]:
            with self.subTest(body=payload[:8],content_type=ctype):
                code,_=self.overwrite(payload,expected,ctype=ctype)
                self.assertNotEqual(code,200)
                self.assertEqual((self.root/'photo.png').read_bytes(),self.orig)
        (self.root/'image.bmp').write_bytes(b'BM'+bytes(70))
        code,_=self.overwrite(self.new,expected,name='image.bmp')
        self.assertEqual(code,415)
        self.assertEqual((self.root/'image.bmp').read_bytes(),b'BM'+bytes(70))

    def test_parent_segment_cannot_be_normalized_to_another_file(self):
        # /api/image/overwrite must never redirect ../victim.png onto /victim.png.
        victim=self.root/'victim.png'
        victim.write_bytes(self.orig)
        code,_=self.overwrite(self.new,self.version(),name='../victim.png')
        self.assertNotEqual(code,200)
        self.assertEqual(victim.read_bytes(),self.orig)

    def test_symlink_inside_root_is_not_followed_by_crop(self):
        link=self.root/'alias.png'
        try:link.symlink_to(self.root/'photo.png')
        except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
        code,_=self.overwrite(self.new,self.version(),name='alias.png')
        self.assertNotEqual(code,200)
        self.assertTrue(link.is_symlink())
        self.assertEqual((self.root/'photo.png').read_bytes(),self.orig)
        code,_=self.request('GET','/api/image/version?p=alias.png')
        self.assertNotEqual(code,200)

    def test_hardlinked_image_is_not_silently_detached(self):
        expected=self.version()
        twin=self.root/'twin.png'
        import os
        try:os.link(self.root/'photo.png',twin)
        except (OSError,NotImplementedError):self.skipTest('hardlinks unavailable')
        code,_=self.overwrite(self.new,expected)
        self.assertNotEqual(code,200)
        self.assertEqual((self.root/'photo.png').read_bytes(),self.orig)
        self.assertEqual(twin.read_bytes(),self.orig)

    def test_thumbnail_reflects_overwrite_and_versioned_viewer_cache(self):
        # Ensure byte-for-byte changed thumb where PIL is installed and
        # explicit ?v=SHA versioned viewer refresh exists in HTML.
        try:
            with urllib.request.urlopen(self.base+'/api/thumb?p=photo.png',timeout=8) as response:
                old_thumb=response.read()
        except urllib.error.HTTPError as exc:
            self.skipTest('image thumbnail generation unavailable: '+str(exc))
        code,_=self.overwrite(self.new,self.version())
        self.assertEqual(code,200)
        with urllib.request.urlopen(self.base+'/api/thumb?p=photo.png',timeout=8) as response:
            new_thumb=response.read()
        self.assertNotEqual(old_thumb,new_thumb)
        with urllib.request.urlopen(self.base+'/',timeout=8) as response:
            html=response.read().decode('utf-8')
        self.assertIn('updated.url=refreshedUrl',html)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows sharing-lock behavior')
    def test_windows_reader_disallowing_delete_returns_423_untouched(self):
        # Reader disallows delete sharing; CAS read must succeed, replace 423.
        import ctypes
        expected=self.version()
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,
                                     ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.CreateFileW(str(self.root/'photo.png'),0x80000000,1,None,3,0,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value,'CreateFileW failed')
        try:
            code,_=self.overwrite(self.new,expected)
            self.assertEqual(code,423)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual((self.root/'photo.png').read_bytes(),self.orig)

    def test_missing_precondition_and_outside_root(self):
        code,_=self.overwrite(self.new,'')
        self.assertEqual(code,428)
        code,_=self.overwrite(self.new,self.version(),name='../other.png')
        self.assertNotEqual(code,200)
        self.assertEqual((self.root/'photo.png').read_bytes(),self.orig)

if __name__ == '__main__':unittest.main()

"""Upload finalization must be complete and no-clobber for rename/ask/skip."""
import concurrent.futures
import http.client
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

ROOT = Path(__file__).resolve().parent.parent


class UploadAtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"), "--root", str(self.root),
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.base + "/api/info", timeout=.5):
                    break
            except Exception:
                time.sleep(.08)
        else:
            self.fail("isolated server did not become ready")

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=4)
        # Windows can retain a just-closed server directory handle briefly.
        for attempt in range(15):
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if attempt == 14:
                    raise
                time.sleep(.15)

    def upload(self, filename, content, conflict="rename"):
        request = urllib.request.Request(
            self.base + f"/api/upload?name={filename}&conflict={conflict}",
            data=content, method="POST",
            headers={"Content-Type": "image/png"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_rename_concurrent_never_overwrites(self):
        bodies = [(f"payload-{i}-" * 1000).encode() for i in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda item: self.upload("same.png", item), bodies))
        self.assertTrue(all(code == 200 for code, _ in results), results)
        names = [urllib.parse.unquote(response["file"].lstrip("/")) for _, response in results]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(sorted((self.root / name).read_bytes() for name in names), sorted(bodies))
        self.assertEqual(list(self.root.glob(".lantern-uploading-*")), [])

    def test_incomplete_upload_is_not_exposed(self):
        data = b"crop-bytes" * 10000
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.putrequest("POST", "/api/upload?name=inprogress.png&conflict=rename")
            connection.putheader("Content-Type", "image/png")
            connection.putheader("Content-Length", str(len(data)))
            connection.endheaders()
            connection.send(data[:100])
            time.sleep(.3)
            self.assertFalse((self.root / "inprogress.png").exists())
            connection.send(data[100:])
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.load(response)["ok"])
            self.assertEqual((self.root / "inprogress.png").read_bytes(), data)
        finally:
            connection.close()

    def test_staging_filename_is_not_served(self):
        stage = self.root / ".lantern-uploading-publicprobe"
        stage.write_bytes(b"not complete")
        request = urllib.request.Request(self.base + "/" + stage.name)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        with urllib.request.urlopen(self.base + "/api/list?path=", timeout=3) as response:
            listing = json.load(response)
        self.assertNotIn(stage.name, str(listing))

    def test_interrupted_upload_never_publishes_partial_file(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        try:
            connection.putrequest("POST", "/api/upload?name=interrupted.png&conflict=rename")
            connection.putheader("Content-Type", "image/png")
            connection.putheader("Content-Length", "500000")
            connection.endheaders()
            connection.send(b"partial" * 40)
        finally:
            connection.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not list(self.root.glob(".lantern-uploading-*")):
                break
            time.sleep(.1)
        self.assertFalse((self.root / "interrupted.png").exists())
        self.assertEqual(list(self.root.glob(".lantern-uploading-*")), [])

    def test_ask_and_skip_never_overwrite_existing(self):
        original = self.root / "original.png"
        original.write_bytes(b"original")
        status, _ = self.upload("original.png", b"bad", conflict="ask")
        self.assertEqual(status, 409)
        status, result = self.upload("original.png", b"bad", conflict="skip")
        self.assertEqual(status, 200)
        self.assertTrue(result["skipped"])
        self.assertEqual(original.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()

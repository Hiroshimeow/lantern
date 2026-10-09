"""Markdown visual editor file-integrity and LAN conflict regression tests."""
from __future__ import annotations
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

from lantern_md_editor import MarkdownEditorError, read_document, save_document, MAX_MARKDOWN_EDITOR_BYTES

ROOT = Path(__file__).resolve().parent


class DocumentStoreTests(unittest.TestCase):
    def test_roundtrip_utf8_bom_crlf_and_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "readme.md"
            p.write_bytes(b"\xef\xbb\xbf# Title\r\n\r\nBefore\r\n")
            original = read_document(p)
            self.assertTrue(original["bom"])
            self.assertEqual(original["newline"], "crlf")
            saved = save_document(p, "# Title\n\nAfter\n", original["version"])
            self.assertEqual(p.read_bytes(), b"\xef\xbb\xbf# Title\r\n\r\nAfter\r\n")
            self.assertNotEqual(saved["version"], original["version"])
            with self.assertRaises(MarkdownEditorError) as ctx:
                save_document(p, "Overwrite!", original["version"])
            self.assertEqual(ctx.exception.status, 409)
            self.assertEqual(p.read_bytes(), b"\xef\xbb\xbf# Title\r\n\r\nAfter\r\n")

    def test_reject_lossy_binary_and_unbounded(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.md"
            p.write_bytes(b"\xff")
            with self.assertRaises(MarkdownEditorError) as ctx:
                read_document(p)
            self.assertEqual(ctx.exception.status, 415)
            p.write_bytes(b"x" * (MAX_MARKDOWN_EDITOR_BYTES + 1))
            with self.assertRaises(MarkdownEditorError) as ctx:
                read_document(p)
            self.assertEqual(ctx.exception.status, 413)
            p.write_text("valid", encoding="utf-8")
            snap = read_document(p)
            with self.assertRaises(MarkdownEditorError) as ctx:
                save_document(p, "changed", "")
            self.assertEqual(ctx.exception.status, 428)
            self.assertEqual(p.read_text(encoding="utf-8"), "valid")
            with self.assertRaises(MarkdownEditorError):
                save_document(p, "x" * (MAX_MARKDOWN_EDITOR_BYTES + 1), snap["version"])
            self.assertEqual(p.read_text(encoding="utf-8"), "valid")

    def test_external_changes_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.markdown"
            p.write_text("before", encoding="utf-8")
            initial = read_document(p)
            p.write_text("external edit", encoding="utf-8")
            with self.assertRaises(MarkdownEditorError) as ctx:
                save_document(p, "client edit", initial["version"])
            self.assertEqual(ctx.exception.status, 409)
            self.assertEqual(p.read_text(encoding="utf-8"), "external edit")


class DocumentHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        (cls.root / "readme.md").write_bytes(b"# Test\n\nHello")
        (cls.root / "other.txt").write_text("Other", encoding="utf-8")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"),
             "--root", str(cls.root), "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic() + 15
        while time.monotonic() < until:
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=0.5):
                    return
            except Exception:
                time.sleep(0.1)
        cls.tearDownClass()
        raise RuntimeError("isolated server failed to start")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "proc"):
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=4)
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def get(self, name):
        with urllib.request.urlopen(self.base + "/api/md/document?p=" + urllib.parse.quote(name), timeout=4) as res:
            return json.load(res)

    def save(self, path, content, version, origin=None):
        data = json.dumps({"path": path, "content": content, "version": version}).encode()
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + "/api/md/save", data=data, method="POST", headers=headers)
        with urllib.request.urlopen(request, timeout=4) as res:
            return json.load(res)

    def test_two_lan_clients_cannot_silently_overwrite(self):
        a = self.get("readme.md")
        b = self.get("readme.md")
        self.assertEqual(a["version"], b["version"])
        updated = self.save("readme.md", "# Test\n\nClient A", a["version"])
        self.assertNotEqual(updated["version"], a["version"])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.save("readme.md", "# Test\n\nClient B", b["version"])
        self.assertEqual(ctx.exception.code, 409)
        self.assertEqual(self.get("readme.md")["content"], "# Test\n\nClient A")

    def test_path_type_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("../not-in-root.md")
        self.assertIn(ctx.exception.code, [400, 403, 404])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("other.txt")
        self.assertEqual(ctx.exception.code, 400)
        snap = self.get("readme.md")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.save("readme.md", "Evil", snap["version"], origin="https://evil.example")
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(self.get("readme.md")["content"], snap["content"])


if __name__ == "__main__":
    unittest.main()

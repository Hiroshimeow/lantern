from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern.text_file import TextFileError, read_text_snapshot, save_text_cas


class GenericTextFileTests(unittest.TestCase):
    def test_txt_roundtrip_preserves_bom_crlf_and_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "notes.txt"
            path.write_bytes(b"\xef\xbb\xbfalpha\r\nbeta\r\n")
            before = read_text_snapshot(path)
            self.assertTrue(before["bom"])
            self.assertEqual(before["newline"], "crlf")

            saved = save_text_cas(path, "alpha\ngamma\n", before["version"])
            self.assertEqual(path.read_bytes(), b"\xef\xbb\xbfalpha\r\ngamma\r\n")
            self.assertNotEqual(saved["version"], before["version"])

            with self.assertRaises(TextFileError) as caught:
                save_text_cas(path, "stale", before["version"])
            self.assertEqual(caught.exception.status, 409)

    def test_python_and_json_are_not_suffix_restricted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            py = root / "app.py"
            js = root / "config.json"
            py.write_text("value = 1\n", encoding="utf-8")
            js.write_text('{"a": 1}\n', encoding="utf-8")

            py_snap = read_text_snapshot(py)
            json_snap = read_text_snapshot(js)
            save_text_cas(py, "value = 2\n", py_snap["version"])
            save_text_cas(js, '{"a": 2}\n', json_snap["version"])

            self.assertEqual(py.read_text(encoding="utf-8"), "value = 2\n")
            self.assertEqual(js.read_text(encoding="utf-8"), '{"a": 2}\n')

    def test_binary_nul_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "blob.txt"
            path.write_bytes(b"a\x00b")
            with self.assertRaises(TextFileError) as caught:
                read_text_snapshot(path)
            self.assertEqual(caught.exception.status, 415)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lantern.text_file import read_text_snapshot
from lantern.working_copy import WorkingCopyError, WorkingCopyStore


class WorkingCopyStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()
        self.work = Path(self.tmp.name) / "work"
        self.store = WorkingCopyStore(
            self.root,
            self.work,
            {".md", ".markdown", ".txt", ".py", ".json"},
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_save_preserves_real_file_until_explicit_save(self):
        path = self.root / "doc.md"
        path.write_bytes(b"\xef\xbb\xbf# Saved\r\n\r\nold\r\n")
        clean = self.store.get("doc.md")
        self.assertEqual(clean["state"], "clean")
        base = clean["saved"]["version"]

        written = self.store.write(
            "doc.md",
            "# Saved\n\nnew\n",
            expect_hash=None,
            base_version=base,
        )
        self.assertEqual(written["state"], "pending")
        self.assertEqual(path.read_bytes(), b"\xef\xbb\xbf# Saved\r\n\r\nold\r\n")

        pending = self.store.get("doc.md")
        self.assertEqual(pending["work"]["content"], "# Saved\n\nnew\n")
        saved = self.store.save(
            "doc.md",
            expect_hash=pending["work"]["hash"],
            expect_saved_version=base,
        )
        self.assertEqual(saved["state"], "clean")
        self.assertEqual(path.read_bytes(), b"\xef\xbb\xbf# Saved\r\n\r\nnew\r\n")
        self.assertIsNone(self.store.get("doc.md")["work"])

    def test_stale_write_and_discard_are_cas_guarded(self):
        path = self.root / "doc.md"
        path.write_text("saved\n", encoding="utf-8")
        base = self.store.get("doc.md")["saved"]["version"]
        first = self.store.write("doc.md", "draft 1\n", expect_hash=None, base_version=base)

        with self.assertRaises(WorkingCopyError) as caught:
            self.store.write("doc.md", "draft 2\n", expect_hash="0" * 64, base_version=base)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.details["reason"], "stale")

        with self.assertRaises(WorkingCopyError):
            self.store.discard("doc.md", expect_hash="0" * 64)
        self.assertEqual(path.read_text(encoding="utf-8"), "saved\n")

        self.store.discard("doc.md", expect_hash=first["hash"])
        self.assertEqual(self.store.get("doc.md")["state"], "clean")
        self.assertEqual(path.read_text(encoding="utf-8"), "saved\n")

    def test_external_real_change_blocks_save_but_keeps_work(self):
        path = self.root / "doc.md"
        path.write_text("saved\n", encoding="utf-8")
        clean = self.store.get("doc.md")
        base = clean["saved"]["version"]
        written = self.store.write("doc.md", "draft\n", expect_hash=None, base_version=base)
        path.write_text("external\n", encoding="utf-8")

        state = self.store.get("doc.md")
        self.assertEqual(state["state"], "external")
        with self.assertRaises(WorkingCopyError) as caught:
            self.store.save(
                "doc.md",
                expect_hash=written["hash"],
                expect_saved_version=base,
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.details["reason"], "external")
        self.assertEqual(path.read_text(encoding="utf-8"), "external\n")
        self.assertEqual(self.store.get("doc.md")["work"]["content"], "draft\n")

    def test_turn_lock_makes_pi_only_writer_and_guard_tracks_target(self):
        path = self.root / "doc.md"
        path.write_text("saved\n", encoding="utf-8")
        clean = self.store.get("doc.md")
        base = clean["saved"]["version"]
        draft = self.store.write("doc.md", "human draft\n", expect_hash=None, base_version=base)

        turn = self.store.begin_turn("doc.md", draft["hash"])
        working = Path(turn["workingPath"])
        guard = json.loads(self.store.guard_path.read_text(encoding="utf-8"))
        self.assertIn(str(working.resolve()).lower(), [p.lower() for p in guard["turnWritable"]])

        for action in (
            lambda: self.store.write("doc.md", "late human\n", expect_hash=draft["hash"], base_version=base),
            lambda: self.store.save("doc.md", expect_hash=draft["hash"], expect_saved_version=base),
            lambda: self.store.discard("doc.md", expect_hash=draft["hash"]),
        ):
            with self.assertRaises(WorkingCopyError) as caught:
                action()
            self.assertEqual(caught.exception.details["reason"], "pi_turn")

        working.write_text("pi edit\n", encoding="utf-8")
        ended = self.store.end_turn("doc.md")
        self.assertFalse(ended["realTouched"])
        self.assertNotEqual(ended["hash"], draft["hash"])
        self.assertEqual(path.read_text(encoding="utf-8"), "saved\n")
        self.assertEqual(self.store.get("doc.md")["work"]["content"], "pi edit\n")

    def test_clean_document_can_be_materialized_for_pi_turn(self):
        path = self.root / "doc.md"
        path.write_text("saved\n", encoding="utf-8")
        turn = self.store.begin_turn("doc.md", None)
        working = Path(turn["workingPath"])
        self.assertTrue(working.is_file())
        self.assertEqual(working.read_text(encoding="utf-8"), "saved\n")
        during = self.store.get("doc.md")
        self.assertTrue(during["turnActive"])
        self.assertIsNotNone(during["work"])
        self.store.end_turn("doc.md")
        # Once Pi made no change, a normal GET collapses the redundant work copy.
        self.assertEqual(self.store.get("doc.md")["state"], "clean")

    def test_generic_store_accepts_text_suffixes_and_rejects_unconfigured_binary(self):
        text = self.root / "notes.txt"
        py = self.root / "app.py"
        png = self.root / "image.png"
        text.write_text("one\n", encoding="utf-8")
        py.write_text("x = 1\n", encoding="utf-8")
        png.write_bytes(b"PNG")

        for rel in ("notes.txt", "app.py"):
            state = self.store.get(rel)
            result = self.store.write(
                rel,
                state["saved"]["content"] + "changed\n",
                expect_hash=None,
                base_version=state["saved"]["version"],
            )
            self.assertIsNotNone(result["hash"])

        with self.assertRaises(WorkingCopyError) as caught:
            self.store.get("image.png")
        self.assertEqual(caught.exception.status, 415)


if __name__ == "__main__":
    unittest.main()

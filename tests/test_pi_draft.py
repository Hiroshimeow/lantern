from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lantern.md_editor import read_document
from lantern.pi_draft import MAX_PI_DRAFT_BYTES, MarkdownDraftShadow


class MarkdownDraftShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.real = self.root / "docs" / "note.md"
        self.real.parent.mkdir(parents=True)
        self.real.write_text("# Saved\n\noriginal\n", encoding="utf-8")
        self.storage = self.root / "shadow"
        self.shadow = MarkdownDraftShadow(self.root, storage_dir=self.storage)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, text="# Saved\n\nunsaved browser draft\n"):
        version = read_document(self.real)["version"]
        return self.shadow.prepare(
            self.real,
            text,
            prompt_id="chat-test-1",
            base_version=version,
            draft_revision=9,
        )

    def test_prepare_stages_browser_draft_without_touching_real_file(self):
        active = self.prepare()
        self.assertEqual(self.real.read_text(encoding="utf-8"), "# Saved\n\noriginal\n")
        self.assertEqual(active.shadow_path.read_text(encoding="utf-8"),
                         "# Saved\n\nunsaved browser draft\n")
        state = json.loads(self.shadow.guard_path.read_text(encoding="utf-8"))
        self.assertTrue(state["active"])
        self.assertEqual(Path(state["realPath"]), self.real.resolve())
        self.assertEqual(Path(state["shadowPath"]), active.shadow_path.resolve())
        self.assertEqual(self.shadow.context_fields()["draftRevision"], 9)

    def test_shadow_changes_emit_updates_and_final_snapshot(self):
        active = self.prepare()
        active.shadow_path.write_text("# Saved\n\nPi changed draft\n", encoding="utf-8")
        update = self.shadow.read_update(final=False)
        self.assertEqual(update["type"], "chat_draft_update")
        self.assertEqual(update["text"], "# Saved\n\nPi changed draft\n")
        self.assertFalse(update["final"])
        self.assertIsNone(self.shadow.read_update(final=False))
        final = self.shadow.read_update(final=True)
        self.assertTrue(final["final"])
        self.assertEqual(final["text"], "# Saved\n\nPi changed draft\n")
        self.assertEqual(self.real.read_text(encoding="utf-8"), "# Saved\n\noriginal\n")

    def test_stale_browser_base_version_is_rejected(self):
        version = read_document(self.real)["version"]
        self.real.write_text("# external\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed on disk"):
            self.shadow.prepare(
                self.real,
                "# draft\n",
                prompt_id="chat-stale",
                base_version=version,
            )

    def test_external_real_file_change_is_reported(self):
        self.prepare()
        self.real.write_text("# external\n", encoding="utf-8")
        event = self.shadow.real_file_changed()
        self.assertEqual(event["type"], "chat_real_file_touched")
        self.assertNotEqual(event["baseVersion"], event["currentVersion"])

    def test_clear_disables_guard(self):
        self.prepare()
        self.shadow.clear()
        state = json.loads(self.shadow.guard_path.read_text(encoding="utf-8"))
        self.assertFalse(state["active"])
        self.assertIsNone(self.shadow.active)

    def test_size_limit_is_bounded_before_shadow_write(self):
        version = read_document(self.real)["version"]
        with self.assertRaisesRegex(ValueError, "too large"):
            self.shadow.prepare(
                self.real,
                "x" * (MAX_PI_DRAFT_BYTES + 1),
                prompt_id="chat-big",
                base_version=version,
            )


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class MarkdownSaveOnlyContractTests(unittest.TestCase):
    def test_full_editor_never_schedules_disk_autosave(self):
        script = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        self.assertNotIn("queueSave(", script)
        self.assertNotIn("saveTimer", script)
        self.assertNotIn("save(false)", script)
        self.assertIn("saveHeader?.addEventListener('click', () => { void save(true); })", script)
        self.assertIn("void save(true)", script)
        self.assertIn("durable local draft writes only", script)

    def test_paged_editor_never_schedules_disk_autosave(self):
        script = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertNotIn("queueSave(", script)
        self.assertNotIn("saveTimer", script)
        self.assertNotIn("save(false)", script)
        self.assertIn("void this.save(true)", script)
        self.assertIn("Save this section before navigating", script)

    def test_local_recovery_remains_enabled(self):
        full = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        paged = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertIn("indexedDB.open('lantern-md-drafts'", full)
        self.assertIn("indexedDB.open('lantern-md-drafts'", paged)
        self.assertIn("queueDraft()", full)
        self.assertIn("draftWrite()", paged)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class MarkdownLiveEditingContractTests(unittest.TestCase):
    def test_full_editor_writes_real_and_save_accepts_md_temp(self):
        script = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        self.assertNotIn("queueSave(", script)
        self.assertNotIn("saveTimer", script)
        self.assertNotIn("save(false)", script)
        self.assertIn("saveHeader?.addEventListener('click', () => { void save(true); })", script)
        self.assertIn("void save(true)", script)
        self.assertIn("flushWorkingCopy", script)
        self.assertIn("/api/work/write", script)
        self.assertIn("/api/work/save", script)

    def test_paged_editor_writes_real_and_save_accepts_md_temp(self):
        script = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertNotIn("queueSave(", script)
        self.assertNotIn("saveTimer", script)
        self.assertNotIn("save(false)", script)
        self.assertIn("void this.save(true)", script)
        self.assertIn("if(!this.botTurnActive)void this.flushReal(false)", script)
        self.assertIn("/api/md/save", script)
        self.assertIn("/api/work/save", script)
        self.assertIn("beginBotTurn()", script)
        self.assertIn("onBotWorkChanged(final)", script)

    def test_local_recovery_remains_enabled(self):
        full = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        paged = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertIn("indexedDB.open('lantern-md-drafts'", full)
        self.assertIn("indexedDB.open('lantern-md-drafts'", paged)
        self.assertIn("queueDraft()", full)
        self.assertIn("draftWrite()", paged)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is required")
class MarkdownDraftDiffTests(unittest.TestCase):
    def call(self, expression: str):
        script = (
            "const d=require('./static/markdown_draft_diff.js');"
            f"const r={expression};"
            "process.stdout.write(JSON.stringify(r));"
        )
        run = subprocess.run(
            [NODE, "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(run.stdout)

    def test_add_delete_and_modify_hunks(self):
        add = self.call("d.diffLines('a\\nc','a\\nb\\nc')")
        self.assertEqual(add[0]["kind"], "add")
        self.assertEqual(add[0]["draftText"], ["b"])

        delete = self.call("d.diffLines('a\\nb\\nc','a\\nc')")
        self.assertEqual(delete[0]["kind"], "del")
        self.assertEqual(delete[0]["baseText"], ["b"])

        mod = self.call("d.diffLines('a\\nb\\nc','a\\nB\\nc')")
        self.assertEqual(mod[0]["kind"], "mod")
        self.assertEqual(mod[0]["baseText"], ["b"])
        self.assertEqual(mod[0]["draftText"], ["B"])

    def test_non_overlapping_human_and_pi_changes_merge(self):
        result = self.call(
            "d.merge3('a\\nb\\nc\\nd','a\\nH\\nc\\nd','a\\nb\\nc\\nP')"
        )
        self.assertEqual(result["text"], "a\nH\nc\nP")
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["appliedPiHunks"], 1)

    def test_overlapping_change_keeps_human_text(self):
        result = self.call(
            "d.merge3('a\\nb\\nc','a\\nHUMAN\\nc','a\\nPI\\nc')"
        )
        self.assertEqual(result["text"], "a\nHUMAN\nc")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["appliedPiHunks"], 0)

    def test_identical_change_is_not_applied_twice(self):
        result = self.call(
            "d.merge3('a\\nb\\nc','a\\nSAME\\nc','a\\nSAME\\nc')"
        )
        self.assertEqual(result["text"], "a\nSAME\nc")
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["appliedPiHunks"], 0)

    def test_multiple_separated_hunks(self):
        hunks = self.call(
            "d.diffLines('a\\nb\\nc\\nd\\ne','a\\nB\\nc\\nD\\ne')"
        )
        self.assertEqual(len(hunks), 2)
        self.assertTrue(all(item["kind"] == "mod" for item in hunks))

    def test_trailing_newline_survives_merge(self):
        result = self.call(
            "d.merge3('a\\nb\\n','a\\nb\\n','a\\nB\\n')"
        )
        self.assertEqual(result["text"], "a\nB\n")


if __name__ == "__main__":
    unittest.main()

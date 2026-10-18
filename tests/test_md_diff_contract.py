from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def _slice_utf16(text: str, start: int, end: int) -> str:
    raw = text.encode("utf-16-le")
    return raw[start * 2:end * 2].decode("utf-16-le")


@unittest.skipUnless(NODE, "node is required")
class MarkdownDiffContractTests(unittest.TestCase):
    def call(self, method: str, *args):
        script = r"""
const d=require('./static/markdown_draft_diff.js');
let input='';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  const {method,args}=JSON.parse(input);
  try {
    const result=d[method](...args);
    process.stdout.write(JSON.stringify({ok:true,result}));
  } catch (error) {
    process.stdout.write(JSON.stringify({ok:false,error:String(error.message||error)}));
  }
});
"""
        run = subprocess.run(
            [NODE, "-e", script],
            cwd=ROOT,
            input=json.dumps({"method": method, "args": args}, ensure_ascii=False),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(run.stdout)
        if not result["ok"]:
            self.fail(result["error"])
        return result["result"]

    def assert_roundtrip_one_hunk(self, base: str, draft: str) -> dict:
        hunks = self.call("diffLines", base, draft)
        self.assertEqual(len(hunks), 1, hunks)
        hunk = hunks[0]
        self.assertEqual(hunk["offsetUnit"], "utf16-code-unit")
        self.assertIn("baseSpan", hunk)
        self.assertIn("draftSpan", hunk)
        self.assertEqual(
            _slice_utf16(
                base,
                hunk["baseSpan"]["start"],
                hunk["baseSpan"]["end"],
            ),
            hunk["baseSpan"]["text"],
        )
        self.assertEqual(
            _slice_utf16(
                draft,
                hunk["draftSpan"]["start"],
                hunk["draftSpan"]["end"],
            ),
            hunk["draftSpan"]["text"],
        )
        self.assertEqual(self.call("applyHunk", base, hunk, "forward"), draft)
        self.assertEqual(self.call("applyHunk", draft, hunk, "reverse"), base)
        return hunk

    def test_modify_hunk_uses_exact_source_spans_without_normalizing_mixed_eol(self):
        base = "A\r\nB\nC"
        draft = "A\r\nBX\nC"
        hunk = self.assert_roundtrip_one_hunk(base, draft)
        self.assertEqual(hunk["kind"], "mod")
        self.assertEqual(hunk["baseSpan"]["text"], "B")
        self.assertEqual(hunk["draftSpan"]["text"], "BX")
        self.assertEqual(base[:hunk["baseSpan"]["start"]], "A\r\n")
        self.assertEqual(base[hunk["baseSpan"]["end"]:], "\nC")

    def test_modify_preserves_target_eol_even_when_draft_was_globally_normalized(self):
        base = "A\r\nB\nC\r\nD"
        normalized_draft = "A\nBX\nC\nD"
        hunk = self.call("diffLines", base, normalized_draft)[0]
        applied = self.call("applyHunk", base, hunk, "forward")
        self.assertEqual(applied, "A\r\nBX\nC\r\nD")

    def test_exact_apply_handles_boundaries_and_final_newline(self):
        cases = [
            ("b\r\nc", "a\r\nb\r\nc"),
            ("a\r\nb\r\nc", "b\r\nc"),
            ("a\r\nb", "a\r\nb\r\nc"),
            ("a\r\nb\r\nc", "a\r\nb"),
            ("a\r\nb", "a\r\nb\r\n"),
            ("a\r\nb\r\n", "a\r\nb"),
        ]
        for base, draft in cases:
            with self.subTest(base=repr(base), draft=repr(draft)):
                self.assert_roundtrip_one_hunk(base, draft)

    def test_separated_hunks_preserve_untouched_prefix_suffix_and_unicode(self):
        base = "🏮 head\r\nB old\n中間\r\nD old"
        draft = "🏮 head\r\nB NEW\n中間\r\nD NEW"
        hunks = self.call("diffLines", base, draft)
        self.assertEqual(len(hunks), 2)
        first = self.call("applyHunk", base, hunks[0], "forward")
        self.assertEqual(first, "🏮 head\r\nB NEW\n中間\r\nD old")
        second = self.call("applyHunk", base, hunks[1], "forward")
        self.assertEqual(second, "🏮 head\r\nB old\n中間\r\nD NEW")



    def test_checked_in_mixed_eol_fixture_changes_only_marker_span(self):
        raw = (ROOT / "tests/fixtures/md-fidelity/mixed-eol-no-final.md").read_bytes()
        base = raw.decode("utf-8")
        draft = base.replace("EDIT_TARGET", "EDIT_TARGET_X", 1)
        hunk = self.assert_roundtrip_one_hunk(base, draft)
        applied = self.call("applyHunk", base, hunk, "forward")
        marker = raw.index(b"EDIT_TARGET")
        self.assertEqual(applied.encode("utf-8")[:marker], raw[:marker])
        self.assertEqual(
            applied.encode("utf-8")[marker + len(b"EDIT_TARGET_X"):],
            raw[marker + len(b"EDIT_TARGET"):],
        )
        self.assertFalse(applied.endswith(("\n", "\r")))

    def test_bom_crlf_and_nonbmp_content_roundtrip(self):
        base = "\ufeff# BOM\r\n🏮 old\r\nTail\r\n"
        draft = "\ufeff# BOM\r\n🏮 NEW\r\nTail\r\n"
        hunk = self.assert_roundtrip_one_hunk(base, draft)
        self.assertEqual(hunk["baseText"], ["🏮 old"])
        self.assertEqual(hunk["draftText"], ["🏮 NEW"])
        self.assertTrue(
            self.call("applyHunk", base, hunk, "forward").startswith("\ufeff")
        )

    def test_merge3_preserves_base_eol_and_no_final_newline(self):
        base = "A\r\nB\nC\r\nD"
        ours = "A\nOURS\nC\nD"
        theirs = "A\r\nB\nC\r\nTHEIRS"
        result = self.call("merge3", base, ours, theirs)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["text"], "A\r\nOURS\nC\r\nTHEIRS")
        self.assertFalse(result["text"].endswith(("\n", "\r")))
        self.assertEqual(result["appliedPiHunks"], 1)


    def test_merge3_boundary_insert_delete_and_trailing_newline(self):
        begin = self.call(
            "merge3",
            "b\r\nc",
            "a\r\nb\r\nc",
            "b\r\nC",
        )
        self.assertEqual(begin["conflicts"], [])
        self.assertEqual(begin["text"], "a\r\nb\r\nC")

        end_delete = self.call(
            "merge3",
            "a\r\nb",
            "a",
            "A\r\nb",
        )
        self.assertEqual(end_delete["conflicts"], [])
        self.assertEqual(end_delete["text"], "A")

        trailing = self.call(
            "merge3",
            "a\r\nb",
            "A\r\nb",
            "a\r\nb\r\n",
        )
        self.assertEqual(trailing["conflicts"], [])
        self.assertEqual(trailing["text"], "A\r\nb\r\n")

        identical_add = self.call(
            "merge3",
            "a\nb",
            "a\nX\nb",
            "a\r\nX\r\nb",
        )
        self.assertEqual(identical_add["conflicts"], [])
        self.assertEqual(identical_add["text"], "a\nX\nb")
        self.assertEqual(identical_add["appliedPiHunks"], 0)

    def test_merge3_identical_overlap_and_add_delete_collisions(self):
        identical = self.call(
            "merge3",
            "a\r\nb\nc",
            "a\nSAME\nc",
            "a\r\nSAME\nc",
        )
        self.assertEqual(identical["conflicts"], [])
        self.assertEqual(identical["text"], "a\r\nSAME\nc")
        self.assertEqual(identical["appliedPiHunks"], 0)

        overlap = self.call(
            "merge3",
            "a\nb\nc",
            "a\nOURS\nc",
            "a\nTHEIRS\nc",
        )
        self.assertEqual(len(overlap["conflicts"]), 1)
        self.assertEqual(overlap["text"], "a\nOURS\nc")

        add_collision = self.call(
            "merge3",
            "a\nb",
            "a\nOURS\nb",
            "a\nTHEIRS\nb",
        )
        self.assertEqual(len(add_collision["conflicts"]), 1)

        delete_modify = self.call(
            "merge3",
            "a\nb\nc",
            "a\nc",
            "a\nB2\nc",
        )
        self.assertEqual(len(delete_modify["conflicts"]), 1)


    def test_adjacent_modifications_preserve_internal_target_separators(self):
        base = "a\r\nb\r\nc\nD"
        normalized_draft = "A\nB\nc\nD"
        hunk = self.call("diffLines", base, normalized_draft)[0]
        applied = self.call("applyHunk", base, hunk, "forward")
        self.assertEqual(applied, "A\r\nB\r\nc\nD")

    def test_multiple_adjacent_modifications_form_one_exact_hunk(self):
        base = "a\r\nb\nc\r\nd"
        draft = "A\r\nB\nc\r\nd"
        hunk = self.assert_roundtrip_one_hunk(base, draft)
        self.assertEqual(hunk["baseStart"], 0)
        self.assertEqual(hunk["baseEnd"], 2)
        self.assertEqual(hunk["draftStart"], 0)
        self.assertEqual(hunk["draftEnd"], 2)


if __name__ == "__main__":
    unittest.main()

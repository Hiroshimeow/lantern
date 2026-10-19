from pathlib import Path

path = Path(r"E:\git-project\lantern\tests\test_md_source_merge_e2e.py")
text = path.read_text(encoding="utf-8")
start = text.index("        raw = (\n", text.index("def test_unified_merge_poc"))
end = text.index("        page = self._new_page()\n", start)

replacement = r'''        marker = "EDIT_TARGET"
        replacement = "EDIT_TARGET_X"
        source_text = (
            "# T\n"
            "\u65e5\u672c\u8a9e \U0001f3ee\n"
            "EDIT_TARGET\r\n"
            "Tail LF\n"
            "Final"
        )
        raw = b"\xef\xbb\xbf" + source_text.encode("utf-8")
        decoded = raw[3:].decode("utf-8")

        page = self._new_page()
        try:
            selection = page.evaluate(
                """({text,marker}) => {
                  CMPoc.createUnified(
                    document.getElementById('app'),
                    text,
                    text
                  );
                  const doc=CMPoc.view.state.doc.toString();
                  const start=doc.indexOf(marker);
                  if(start < 0) throw new Error('marker missing');
                  CMPoc.setSelection(start,start+marker.length);
                  CMPoc.clearCapturedChanges();
                  CMPoc.view.focus();
                  return {start,end:start+marker.length};
                }""",
                {"text": decoded, "marker": marker},
            )
            page.keyboard.insert_text(replacement)
            transaction_result = page.evaluate(
                """() => ({
                  doc:CMPoc.getDoc(),
                  changes:CMPoc.getCapturedChanges()
                })"""
            )
        finally:
            page.close()

        self.assertEqual(len(transaction_result["changes"]), 1)
        change = transaction_result["changes"][0]
        self.assertEqual(change["from"], selection["start"])
        self.assertEqual(change["to"], selection["end"])
        self.assertEqual(change["inserted"], replacement)
        self.assertEqual(
            change["toNew"] - change["fromNew"],
            len(replacement),
        )
        self.assertTrue(
            _valid_utf16_boundary(decoded, change["from"])
        )
        self.assertTrue(
            _valid_utf16_boundary(decoded, change["to"])
        )

        raw_start, raw_end = _raw_utf8_span(
            raw,
            change["from"],
            change["to"],
        )
        self.assertEqual(
            raw[raw_start:raw_end],
            marker.encode("utf-8"),
        )
        patched = _raw_patch_utf8(
            raw,
            change["from"],
            change["to"],
            change["inserted"],
        )
        expected = raw.replace(
            marker.encode("utf-8"),
            replacement.encode("utf-8"),
            1,
        )
        self.assertEqual(patched, expected)
        self.assertTrue(patched.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            patched[:raw_start],
            raw[:raw_start],
        )
        patched_suffix_start = raw_start + len(
            replacement.encode("utf-8")
        )
        self.assertEqual(
            patched[patched_suffix_start:],
            raw[raw_end:],
        )
        self.assertEqual(_eol_tokens(patched), _eol_tokens(raw))
        self.assertFalse(raw.endswith((b"\n", b"\r")))
        self.assertFalse(patched.endswith((b"\n", b"\r")))
        self.assertIn(
            "\u65e5\u672c\u8a9e \U0001f3ee".encode("utf-8"),
            patched,
        )
        report["byteStrategy"] = {
            "bomPreserved": True,
            "mixedEolUntouchedBytesPreserved": True,
            "noFinalNewlinePreserved": True,
            "nonBmpBeforeEditCovered": True,
            "surrogateBoundaryPreserved": True,
            "capturedChange": change,
            "strategy": (
                "captured CodeMirror transaction UTF-16 range -> "
                "authoritative raw UTF-8 byte patch; never whole-document "
                "serialization"
            ),
        }

'''

path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")

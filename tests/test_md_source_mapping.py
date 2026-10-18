"""MD-T002 deterministic Markdown source-range <-> ProseMirror mapping proof.

Opt in:
    set LANTERN_E2E=1
    python -m unittest -v tests.test_md_source_mapping

This is a proof harness, not a dirty-segment writer.  A green harness may
record NO-GO/stale/nested-unproved cases.  It must never guess by text match.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "md-fidelity"
EVIDENCE = ROOT / ".plan" / "lantern-markdown-main-20261018" / "dev_turn9_md_source_mapping.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _js_slice(text: str, start: int, end: int) -> str:
    """Slice a Python string using JavaScript UTF-16 code-unit offsets."""
    raw = text.encode("utf-16-le")
    return raw[start * 2:end * 2].decode("utf-16-le")


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class MarkdownSourceMappingProofE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-map-p0-", ignore_cleanup_errors=True)
        cls.temp = Path(cls.tmp.name)
        cls.root = cls.temp / "root"
        cls.root.mkdir()
        cls.work = cls.temp / "work"
        cls.work.mkdir()

        for fixture in FIXTURES.glob("*.md"):
            shutil.copyfile(fixture, cls.root / fixture.name)

        cls.extra: dict[str, bytes] = {
            "canonical.md": b"# Heading\n\nParagraph text.\n",
            "unicode.md": "# Unicode\n\nCJK 日本語 emoji 🏮 end\n".encode("utf-8"),
            "bom-lf.md": b"\xef\xbb\xbf" + "# BOM\n\nCJK 日本語 emoji 🏮 end\n".encode("utf-8"),
            "alias-list.md": b"# Alias\n\n+ one\n+ two\n",
            "duplicates-canonical.md": (
                "# Same Heading\n\n"
                "Same paragraph text.\n\n"
                "# Same Heading\n\n"
                "Same paragraph text.\n"
            ).encode("utf-8"),
            "nested-canonical.md": (
                "# Nested\n\n"
                "* alpha\n"
                "  * beta\n"
                "    1. gamma\n"
                "    2. delta\n"
                "* omega\n"
            ).encode("utf-8"),
            "table-canonical.md": (
                "# Table\n\n"
                "| A | B |\n"
                "| --- | --- |\n"
                "| one | two |\n"
                "| three | four |\n"
            ).encode("utf-8"),
        }
        for name, raw in cls.extra.items():
            (cls.root / name).write_bytes(raw)

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, LANTERN_WORK_DIR=str(cls.work / "state"))
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "main.py"),
                "--root",
                str(cls.root),
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--config",
                str(cls.work / "config.yaml"),
                "--cache-dir",
                str(cls.work / "cache"),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(150):
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                if cls.proc.poll() is not None:
                    raise RuntimeError("disposable mapping server exited")
                time.sleep(0.1)
        else:
            raise RuntimeError("disposable mapping server did not start")

        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(channel="msedge", headless=True)
        cls.browser_version = cls.browser.version

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.browser.close()
            cls.play.stop()
        finally:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
            cls.tmp.cleanup()

    def _probe(self, name: str) -> dict[str, object]:
        raw = (self.root / name).read_bytes()
        context = self.browser.new_context(viewport={"width": 1280, "height": 840})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=" + name, wait_until="domcontentloaded")
            state = page.evaluate(
                """name => fetch('/api/work?p=' + encodeURIComponent(name))
                   .then(response => response.json())""",
                name,
            )
            source = (state.get("work") or state["saved"])["content"]
            meta = state["saved"]
            page.get_by_role("button", name="Edit visually", exact=True).click()
            page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(
                timeout=30000
            )
            result = page.evaluate(
                """({source, bom, version}) => {
                  const instance = window.__lanternMdVisual?.state?.instance;
                  if (!instance?.debugSourceMap)
                    throw new Error('debugSourceMap mapping evidence API missing');
                  return instance.debugSourceMap(source, {
                    encoding:'utf-8', bom, version
                  });
                }""",
                {
                    "source": source,
                    "bom": bool(meta["bom"]),
                    "version": state["currentVersion"],
                },
            )
            units = result.get("units") or result.get("sourceUnits") or []
            for unit in units:
                start = unit["sourceStart"]
                end = unit["sourceEnd"]
                expected_text = _js_slice(source, start, end)
                raw_start = unit["rawByteStart"]
                raw_end = unit["rawByteEnd"]
                actual = raw[raw_start:raw_end].decode("utf-8")
                self.assertEqual(actual, expected_text, (name, unit))
                self.assertEqual(unit["revision"], state["currentVersion"])
                self.assertEqual(unit["mdastType"], unit["type"])
                self.assertEqual(unit["sourceOffsetUnit"], "utf16-code-unit")
                self.assertEqual(unit["rawOffsetUnit"], "utf8-byte")
                self.assertEqual(unit["encoding"], "utf-8")
            result["fixture"] = name
            result["sourceVersion"] = state["currentVersion"]
            result["rawSha256"] = _sha(raw)
            result["rawBytes"] = len(raw)
            result["bom"] = bool(meta["bom"])
            result["newline"] = meta["newline"]
            result["pageErrors"] = errors
            return result
        finally:
            context.close()

    def test_mapping_matrix(self) -> None:
        names = [
            "canonical.md",
            "unicode.md",
            "bom-lf.md",
            "duplicates-canonical.md",
            "duplicates.md",
            "nested-canonical.md",
            "table-canonical.md",
            "wide-table.md",
            "constructs.md",
            "bom-crlf.md",
            "mixed-eol-no-final.md",
            "alias-list.md",
        ]
        report = {
            "schema": 1,
            "browser": {"channel": "msedge", "version": self.browser_version},
            "offsetContract": {
                "decoded": "JavaScript UTF-16 code units over exact decoded source string",
                "raw": "UTF-8 bytes; add three leading bytes only when source snapshot has BOM",
            },
            "cases": [],
        }
        try:
            for name in names:
                item = self._probe(name)
                report["cases"].append(item)
                print("SOURCE_MAP=" + json.dumps(item, ensure_ascii=True), flush=True)
        finally:
            EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")

        by_name = {item["fixture"]: item for item in report["cases"]}
        for item in report["cases"]:
            self.assertEqual(item["sourceVersion"], item["rawSha256"])
            self.assertEqual(item["pageErrors"], [])
            self.assertIn(
                item["classification"],
                {"block-only", "stale", "unmapped", "ambiguous"},
            )

        # Canonical simple and Unicode documents prove exact top-level ranges.
        for name in (
            "canonical.md", "unicode.md", "bom-lf.md", "duplicates-canonical.md"
        ):
            item = by_name[name]
            self.assertTrue(item["mapped"], item)
            self.assertEqual(item["classification"], "block-only", item)
            self.assertGreater(len(item["units"]), 0)
            for unit in item["units"]:
                self.assertEqual(unit["proof"], "exact-block")
                self.assertEqual(unit["nestedProof"], "unproved")
                self.assertGreater(unit["rawByteEnd"], unit["rawByteStart"])

        # BOM is stripped from decoded Markdown, so the first raw range starts
        # after the three BOM bytes rather than at decoded offset zero.
        bom_first = by_name["bom-lf.md"]["units"][0]
        self.assertEqual(bom_first["sourceStart"], 0)
        self.assertEqual(bom_first["rawByteStart"], 3)

        # Non-ASCII/non-BMP content proves mdast offsets are not raw byte offsets.
        unicode_para = by_name["unicode.md"]["units"][1]
        self.assertGreater(
            unicode_para["rawByteEnd"] - unicode_para["rawByteStart"],
            unicode_para["sourceEnd"] - unicode_para["sourceStart"],
        )

        # Duplicate content is resolved by ordered AST/PM identity, never first
        # or Nth text search. Equal source text still has distinct exact ranges.
        duplicate_units = by_name["duplicates-canonical.md"]["units"]
        ranges = [(u["rawByteStart"], u["rawByteEnd"]) for u in duplicate_units]
        self.assertEqual(len(ranges), len(set(ranges)))
        raw = (self.root / "duplicates-canonical.md").read_bytes()
        slices = [raw[start:end] for start, end in ranges]
        self.assertGreaterEqual(max(slices.count(value) for value in slices), 2)

        # Nested list/table blocks may have an exact outer block range but this
        # proof deliberately refuses to claim cell/list-child/inline identity.
        nested_results = [
            by_name["nested-canonical.md"],
            by_name["table-canonical.md"],
            by_name["wide-table.md"],
            by_name["constructs.md"],
        ]
        self.assertTrue(any(item["mapped"] for item in nested_results))
        for item in nested_results:
            if item["mapped"]:
                self.assertEqual(item["classification"], "block-only")
                self.assertTrue(all(u["nestedProof"] == "unproved" for u in item["units"]))

        # CRLF/mixed-EOL and source aliases are intentionally allowed to fail
        # closed when Milkdown normalizes representation. Source offsets are
        # still parsed from the authoritative source and raw byte conversion is
        # proven, but no PM mapping may be guessed.
        for name in (
            "bom-crlf.md", "mixed-eol-no-final.md", "alias-list.md", "duplicates.md"
        ):
            item = by_name[name]
            self.assertFalse(item["mapped"], item)
            self.assertEqual(item["classification"], "stale", item)
            self.assertEqual(item["reason"], "stale", item)
            self.assertGreater(len(item["sourceUnits"]), 0)

        # GO/NO-GO conclusion of MD-T002.
        report["conclusion"] = {
            "blockLevelDirtySegmentPatching": "GO_WITH_EXACT_SOURCE_IDENTITY_ONLY",
            "nestedTableListInlinePatching": "NO_GO_UNPROVED",
            "fallback": "EXACT_SOURCE_MODE_FOR_STALE_UNMAPPED_AMBIGUOUS",
        }
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

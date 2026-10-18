"""Exact-byte Markdown fidelity corpus and Phase-0 browser characterization.

The checked-in fixtures are protected with a fixture-only .gitattributes -text
rule so BOM/CRLF/mixed-EOL/no-final-newline bytes are test data, not Git text.

Opt-in browser characterization:
    set LANTERN_E2E=1
    python -m unittest -v tests.test_markdown_roundtrip_corpus

A green harness does not mean every product case passes. Per-case PASS/FAIL is
written to raw JSON using exact expected bytes outside the intended edit.
"""
from __future__ import annotations

import hashlib
import json
import os
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
EVIDENCE = ROOT / ".plan" / "lantern-markdown-main-20261018" / "dev_turn6_markdown_roundtrip.json"
MARKER = b"EDIT_TARGET"
SOURCE_REPLACEMENT = b"EDIT_TARGET_SRC"
VISUAL_REPLACEMENT = b"EDIT_TARGET_VIS"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _byte_state(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"sha256": _sha(raw), "bytes": len(raw)}


def _diff_summary(
    original: bytes,
    actual: bytes,
    intended_start: int,
    intended_old: bytes,
    intended_new: bytes,
) -> dict[str, object]:
    expected = (
        original[:intended_start]
        + intended_new
        + original[intended_start + len(intended_old):]
    )
    prefix = original[:intended_start]
    suffix = original[intended_start + len(intended_old):]
    actual_prefix = actual[:len(prefix)]
    actual_suffix = actual[-len(suffix):] if suffix else b""
    first = None
    common = min(len(expected), len(actual))
    for index in range(common):
        if expected[index] != actual[index]:
            first = index
            break
    if first is None and len(expected) != len(actual):
        first = common
    last_from_end = None
    for offset in range(1, common + 1):
        if expected[-offset] != actual[-offset]:
            last_from_end = offset
            break
    return {
        "expected_sha256": _sha(expected),
        "actual_sha256": _sha(actual),
        "expected_bytes": len(expected),
        "actual_bytes": len(actual),
        "intended_start": intended_start,
        "intended_old_bytes": len(intended_old),
        "intended_new_bytes": len(intended_new),
        "prefix_sha256": _sha(prefix),
        "actual_prefix_sha256": _sha(actual_prefix),
        "suffix_sha256": _sha(suffix),
        "actual_suffix_sha256": _sha(actual_suffix),
        "prefix_identical": actual_prefix == prefix,
        "suffix_identical": actual_suffix == suffix,
        "outside_intended_identical": actual == expected,
        "first_unexpected_diff_offset": first,
        "last_unexpected_diff_from_end": last_from_end,
    }


class MarkdownFidelityFixtureBytes(unittest.TestCase):
    def test_checked_in_fixture_byte_contract(self) -> None:
        names = {
            "bom-crlf.md",
            "mixed-eol-no-final.md",
            "no-final-newline.md",
            "constructs.md",
            "duplicates.md",
            "wide-table.md",
        }
        self.assertEqual({path.name for path in FIXTURES.glob("*.md")}, names)

        raw = (FIXTURES / "bom-crlf.md").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", raw)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))

        mixed = (FIXTURES / "mixed-eol-no-final.md").read_bytes()
        self.assertIn(b"\r\n", mixed)
        self.assertGreater(mixed.count(b"\n"), mixed.count(b"\r\n"))
        self.assertNotIn(mixed[-1:], {b"\n", b"\r"})

        no_final = (FIXTURES / "no-final-newline.md").read_bytes()
        self.assertNotIn(no_final[-1:], {b"\n", b"\r"})

        constructs = (FIXTURES / "constructs.md").read_bytes().decode("utf-8")
        for token in (
            "---\ntitle:",
            "<!-- keep this exact comment -->",
            "<div data-lantern=\"raw\">",
            chr(96) * 3 + "python",
            "日本語の段落",
            "Repeated identical paragraph.",
            "| row | duplicate | duplicate |",
        ):
            self.assertIn(token, constructs)
        self.assertGreaterEqual(constructs.count("# Repeated Heading"), 2)
        self.assertGreaterEqual(constructs.count("Repeated identical paragraph."), 2)

        duplicates = (FIXTURES / "duplicates.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(duplicates.count("# Same Heading"), 2)
        self.assertGreaterEqual(duplicates.count("Same paragraph text."), 2)
        self.assertGreaterEqual(duplicates.count("| same | same | same |"), 2)

        wide = (FIXTURES / "wide-table.md").read_text(encoding="utf-8")
        self.assertEqual(wide.splitlines()[2].count("|") - 1, 30)

        for path in FIXTURES.glob("*.md"):
            self.assertEqual(path.read_bytes().count(MARKER), 1, path.name)


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class MarkdownRoundtripCorpusE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-fidelity-p0-", ignore_cleanup_errors=True)
        cls.temp = Path(cls.tmp.name)
        cls.root = cls.temp / "root"
        cls.root.mkdir()
        cls.work = cls.temp / "work"
        cls.work.mkdir()
        cls.originals: dict[str, bytes] = {}
        for fixture in sorted(FIXTURES.glob("*.md")):
            raw = fixture.read_bytes()
            cls.originals[fixture.name] = raw
            (cls.root / ("source-" + fixture.name)).write_bytes(raw)
            if fixture.name in {"constructs.md", "wide-table.md"}:
                (cls.root / ("visual-" + fixture.name)).write_bytes(raw)

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
                    raise RuntimeError("disposable fidelity server exited")
                time.sleep(0.1)
        else:
            raise RuntimeError("disposable fidelity server did not start")

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

    def _state(self, page, rel: str) -> dict[str, object]:
        return page.evaluate(
            """rel => fetch('/api/work?p=' + encodeURIComponent(rel))
               .then(response => response.json())""",
            rel,
        )

    def _source_case(self, fixture_name: str) -> dict[str, object]:
        rel = "source-" + fixture_name
        target = self.root / rel
        original = self.originals[fixture_name]
        intended_start = original.index(MARKER)
        context = self.browser.new_context(viewport={"width": 1260, "height": 820})
        page = context.new_page()
        requests: list[tuple[str, str]] = []
        errors: list[str] = []
        page.on("request", lambda req: requests.append((req.method, req.url.split("?")[0])))
        page.on("pageerror", lambda err: errors.append(str(err)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=" + rel, wait_until="domcontentloaded")
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=20000)
            initial_state = self._state(page, rel)
            temp_path = Path(initial_state["tempPath"])
            real_initial = _byte_state(target)
            temp_initial = _byte_state(temp_path)
            before_noop_writes = sum(
                method == "POST" and url.endswith("/api/work/write")
                for method, url in requests
            )

            page.get_by_role("button", name="Preview", exact=True).click()
            page.locator("article.md-preview").wait_for(state="visible", timeout=15000)
            page.get_by_role("button", name="Source", exact=True).click()
            area.wait_for(timeout=15000)
            page.wait_for_timeout(350)
            after_noop_writes = sum(
                method == "POST" and url.endswith("/api/work/write")
                for method, url in requests
            )
            no_op_real = target.read_bytes()
            no_op_temp = temp_path.read_bytes()

            value = area.input_value()
            self.assertEqual(value.count("EDIT_TARGET"), 1, fixture_name)
            edited = value.replace("EDIT_TARGET", SOURCE_REPLACEMENT.decode("ascii"), 1)
            area.fill(edited)
            page.wait_for_function(
                "() => !!window.__lanternMdVisual?.state?.workHash",
                timeout=20000,
            )
            page.wait_for_timeout(300)
            final_state = self._state(page, rel)
            actual = target.read_bytes()
            temp_after = temp_path.read_bytes()
            diff = _diff_summary(
                original, actual, intended_start, MARKER, SOURCE_REPLACEMENT
            )
            no_op_writes = after_noop_writes - before_noop_writes
            return {
                "fixture": fixture_name,
                "original": {"sha256": _sha(original), "bytes": len(original)},
                "initial_real": real_initial,
                "initial_real_version": initial_state["currentVersion"],
                "initial_md_temp": temp_initial,
                "initial_md_temp_version": initial_state["saved"]["version"],
                "no_op": {
                    "write_post_count": no_op_writes,
                    "real_sha256": _sha(no_op_real),
                    "md_temp_sha256": _sha(no_op_temp),
                    "bytes_unchanged": no_op_real == original and no_op_temp == original,
                    "classification": (
                        "PASS"
                        if no_op_writes == 0
                        and no_op_real == original
                        and no_op_temp == original
                        else "FAIL"
                    ),
                },
                "edit": {
                    **diff,
                    "real_current_version": final_state["currentVersion"],
                    "saved_md_temp_version": final_state["saved"]["version"],
                    "md_temp_sha256_after": _sha(temp_after),
                    "md_temp_unchanged": temp_after == original,
                    "classification": (
                        "PASS"
                        if diff["outside_intended_identical"] and temp_after == original
                        else "FAIL"
                    ),
                },
                "page_errors": errors,
            }
        finally:
            context.close()

    def _visual_case(self, fixture_name: str) -> dict[str, object]:
        rel = "visual-" + fixture_name
        target = self.root / rel
        original = self.originals[fixture_name]
        intended_start = original.index(MARKER)
        context = self.browser.new_context(viewport={"width": 1260, "height": 860})
        page = context.new_page()
        requests: list[tuple[str, str]] = []
        errors: list[str] = []
        page.on("request", lambda req: requests.append((req.method, req.url.split("?")[0])))
        page.on("pageerror", lambda err: errors.append(str(err)))
        try:
            page.goto(self.base + "/api/plugin/preview?p=" + rel, wait_until="domcontentloaded")
            page.get_by_role("button", name="Edit visually", exact=True).click()
            editor = page.locator(".md-visual-host .ProseMirror[contenteditable='true']")
            editor.wait_for(timeout=35000)
            initial_state = self._state(page, rel)
            temp_path = Path(initial_state["tempPath"])
            temp_initial = temp_path.read_bytes()
            real_initial = target.read_bytes()
            serialized_before = page.evaluate(
                "() => window.__lanternMdVisual.state.instance.getMarkdown()"
            )
            roundtrip_safe = page.evaluate(
                "() => window.__lanternMdVisual.state.roundtripSafe"
            )
            page.wait_for_timeout(450)
            no_op_writes = sum(
                method == "POST" and url.endswith("/api/work/write")
                for method, url in requests
            )
            no_op_real = target.read_bytes()
            no_op_temp = temp_path.read_bytes()

            marker = editor.get_by_text("Edit marker: EDIT_TARGET", exact=True)
            marker.wait_for(timeout=15000)
            marker.click()
            page.keyboard.press("End")
            page.keyboard.type("_VIS")
            review = page.locator("dialog.md-format-review")
            review_visible = False
            try:
                review.wait_for(state="visible", timeout=5000)
                review_visible = True
            except Exception:
                pass
            serialized_after = page.evaluate(
                "() => window.__lanternMdVisual.state.instance.getMarkdown()"
            )
            if review_visible:
                review.get_by_role("button", name="Accept conversion & Save").click()
                review.wait_for(state="detached", timeout=10000)
            page.wait_for_function(
                "() => !!window.__lanternMdVisual?.state?.workHash",
                timeout=20000,
            )
            page.wait_for_timeout(300)
            final_state = self._state(page, rel)
            actual = target.read_bytes()
            temp_after = temp_path.read_bytes()
            diff = _diff_summary(
                original, actual, intended_start, MARKER, VISUAL_REPLACEMENT
            )
            serialization_raw = serialized_after.encode("utf-8")
            return {
                "fixture": fixture_name,
                "original": {"sha256": _sha(original), "bytes": len(original)},
                "initial_real": {"sha256": _sha(real_initial), "bytes": len(real_initial)},
                "initial_real_version": initial_state["currentVersion"],
                "initial_md_temp": {"sha256": _sha(temp_initial), "bytes": len(temp_initial)},
                "initial_md_temp_version": initial_state["saved"]["version"],
                "no_op": {
                    "roundtrip_safe": bool(roundtrip_safe),
                    "serialized_sha256": _sha(serialized_before.encode("utf-8")),
                    "serialized_matches_decoded_original": (
                        serialized_before == original.decode("utf-8-sig")
                    ),
                    "write_post_count": no_op_writes,
                    "real_sha256": _sha(no_op_real),
                    "md_temp_sha256": _sha(no_op_temp),
                    "bytes_unchanged": no_op_real == original and no_op_temp == original,
                    "classification": (
                        "PASS"
                        if no_op_writes == 0
                        and no_op_real == original
                        and no_op_temp == original
                        else "FAIL"
                    ),
                },
                "edit": {
                    **diff,
                    "format_review_required": review_visible,
                    "visual_serialized_sha256": _sha(serialization_raw),
                    "visual_serialized_bytes": len(serialization_raw),
                    "real_current_version": final_state["currentVersion"],
                    "saved_md_temp_version": final_state["saved"]["version"],
                    "md_temp_sha256_after": _sha(temp_after),
                    "md_temp_unchanged": temp_after == original,
                    "classification": (
                        "PASS"
                        if diff["outside_intended_identical"] and temp_after == original
                        else "FAIL"
                    ),
                },
                "page_errors": errors,
            }
        finally:
            context.close()

    def test_roundtrip_byte_characterization(self) -> None:
        report: dict[str, object] = {
            "schema": 1,
            "browser": {"channel": "msedge", "version": self.browser_version},
            "source_cases": [],
            "visual_cases": [],
        }
        try:
            for fixture_name in sorted(self.originals):
                item = self._source_case(fixture_name)
                report["source_cases"].append(item)
                print("FIDELITY_SOURCE=" + json.dumps(item, ensure_ascii=False), flush=True)
            for fixture_name in ("constructs.md", "wide-table.md"):
                item = self._visual_case(fixture_name)
                report["visual_cases"].append(item)
                print("FIDELITY_VISUAL=" + json.dumps(item, ensure_ascii=False), flush=True)
        finally:
            EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self.assertEqual(len(report["source_cases"]), len(self.originals))
        self.assertEqual(
            {item["fixture"] for item in report["visual_cases"]},
            {"constructs.md", "wide-table.md"},
        )
        for item in report["source_cases"] + report["visual_cases"]:
            self.assertEqual(item["initial_real"], item["original"])
            self.assertEqual(item["initial_md_temp"], item["original"])
            self.assertEqual(item["initial_real_version"], item["original"]["sha256"])
            self.assertEqual(item["initial_md_temp_version"], item["original"]["sha256"])
            self.assertEqual(item["edit"]["real_current_version"], item["edit"]["actual_sha256"])
            self.assertEqual(item["edit"]["saved_md_temp_version"], item["original"]["sha256"])
            self.assertEqual(item["page_errors"], [])
            no_op = item["no_op"]
            self.assertEqual(
                no_op["classification"],
                "PASS"
                if no_op["write_post_count"] == 0 and no_op["bytes_unchanged"]
                else "FAIL",
            )
            edit = item["edit"]
            self.assertEqual(
                edit["classification"],
                "PASS"
                if edit["outside_intended_identical"] and edit["md_temp_unchanged"]
                else "FAIL",
            )


if __name__ == "__main__":
    unittest.main()

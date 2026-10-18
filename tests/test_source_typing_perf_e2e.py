"""Phase-0 characterization of the real Lantern Source editor typing path.

Opt in:
    set LANTERN_E2E=1
    python -m unittest -v tests.test_source_typing_perf_e2e

The test harness may be green while product acceptance is red.  The JSON result
contains the binding `within_budget` / `acceptance` classification; this module
must not weaken the 5,500-line p95 <40 ms and no-full-backdrop-rebuild target.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tests._markdown_characterization_settle import wait_for_stable_markdown_write

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / ".plan" / "lantern-markdown-main-20261018" / "dev_turn6_source_typing_perf.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 3)


def _fixed_lines(lines: int, *, cjk: bool = False) -> str:
    prefix = "段落 日本語 한글 中文" if cjk else "Source latency Markdown benchmark"
    rows = ["# Source characterization", ""]
    rows.extend(
        f"{prefix} line {index:06d} token {index * 7:08d}"
        for index in range(max(0, lines - len(rows)))
    )
    text = "\n".join(rows) + "\n"
    assert len(text.splitlines()) == lines
    return text


def _sized_markdown(target_bytes: int) -> str:
    header = "# Sized Source characterization\n\n"
    row = "Payload line {i:05d} " + ("abcdefghij0123456789" * 120) + "\n"
    parts = [header]
    size = len(header.encode("utf-8"))
    index = 0
    while size < target_bytes:
        line = row.format(i=index)
        encoded = line.encode("utf-8")
        remaining = target_bytes - size
        if len(encoded) > remaining:
            if remaining > 1:
                parts.append("x" * (remaining - 1) + "\n")
            break
        parts.append(line)
        size += len(encoded)
        index += 1
    return "".join(parts)


def _wide_table() -> str:
    columns = [f"Column_{i:02d}" for i in range(30)]
    out = [
        "# Wide Source characterization",
        "",
        "|" + "|".join(columns) + "|",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in range(90):
        out.append("|" + "|".join(f"R{row:02d}C{col:02d}" for col in range(30)) + "|")
    out.extend(["", "Trailing paragraph for source typing.", ""])
    return "\n".join(out)


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class SourceTypingPerformanceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.tmp = tempfile.TemporaryDirectory(prefix="lantern-source-p0-", ignore_cleanup_errors=True)
        cls.temp = Path(cls.tmp.name)
        cls.root = cls.temp / "root"
        cls.root.mkdir()
        cls.work = cls.temp / "work"
        cls.work.mkdir()
        cls.workloads = {
            "lines-900": _fixed_lines(900),
            "lines-5500": _fixed_lines(5500),
            "bytes-500k": _sized_markdown(500_000),
            "bytes-5m": _sized_markdown(4_800_000),
            "cjk-ime": _fixed_lines(900, cjk=True),
            "wide-30col": _wide_table(),
        }
        for name, text in cls.workloads.items():
            (cls.root / f"{name}.md").write_text(text, encoding="utf-8", newline="")

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
                    raise RuntimeError("disposable Source server exited")
                time.sleep(0.1)
        else:
            raise RuntimeError("disposable Source server did not start")

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

    def _snapshot(self, path: Path) -> dict[str, object]:
        raw = path.read_bytes()
        return {"sha256": _sha(raw), "bytes": len(raw)}

    def _install_observers(self, page) -> dict[str, int]:
        return page.evaluate(
            """() => {
              const area = document.querySelector('textarea.md-source-area');
              const backdrop = document.querySelector('.md-source-diff-backdrop-content');
              if (!area || !backdrop) throw new Error('Source instrumentation target missing');
              const data = window.__sourceP0 = {
                inputs: 0, paintMs: [], longTasks: [], mutationRecords: 0,
                added: 0, removed: 0, maxAdded: 0, maxRemoved: 0,
                focusLost: false, caretStarts: [], caretEnds: []
              };
              try {
                const po = new PerformanceObserver(list => {
                  for (const entry of list.getEntries())
                    data.longTasks.push({start: entry.startTime, duration: entry.duration});
                });
                po.observe({type:'longtask', buffered:true});
                data.longTaskObserver = po;
              } catch (_) {}
              data.mutationObserver = new MutationObserver(records => {
                data.mutationRecords += records.length;
                for (const mutation of records) {
                  const added = mutation.addedNodes.length;
                  const removed = mutation.removedNodes.length;
                  data.added += added;
                  data.removed += removed;
                  data.maxAdded = Math.max(data.maxAdded, added);
                  data.maxRemoved = Math.max(data.maxRemoved, removed);
                }
              });
              data.mutationObserver.observe(backdrop, {childList:true, subtree:false});
              area.addEventListener('input', () => {
                const begin = performance.now();
                data.inputs += 1;
                data.caretStarts.push(area.selectionStart);
                requestAnimationFrame(() => {
                  data.paintMs.push(performance.now() - begin);
                  if (document.activeElement !== area) data.focusLost = true;
                  data.caretEnds.push(area.selectionStart);
                });
              }, true);
              return {backdropLines: backdrop.children.length, valueBytes: new Blob([area.value]).size};
            }"""
        )

    def _composition_insert(self, page, value: str) -> float:
        begin = time.perf_counter()
        page.evaluate(
            """value => {
              const area = document.querySelector('textarea.md-source-area');
              area.focus();
              const start = area.selectionStart;
              const end = area.selectionEnd;
              area.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true, data:''}));
              area.dispatchEvent(new CompositionEvent('compositionupdate', {bubbles:true, data:value}));
              area.setRangeText(value, start, end, 'end');
              area.dispatchEvent(new InputEvent('input', {
                bubbles:true, inputType:'insertCompositionText', data:value, isComposing:true
              }));
              area.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:value}));
            }""",
            value,
        )
        return round((time.perf_counter() - begin) * 1000, 3)

    def _probe(self, name: str) -> dict[str, object]:
        target = self.root / f"{name}.md"
        context = self.browser.new_context(viewport={"width": 1340, "height": 850})
        page = context.new_page()
        navigations: list[str] = []
        requests: list[tuple[str, str]] = []
        page_errors: list[str] = []
        page.on("framenavigated", lambda frame: navigations.append(frame.url) if frame == page.main_frame else None)
        page.on("request", lambda req: requests.append((req.method, req.url.split("?")[0])))
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        try:
            page.goto(
                self.base + f"/api/plugin/preview?p={name}.md",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            page.get_by_role("button", name="Source", exact=True).click()
            area = page.get_by_role("textbox", name="Markdown source")
            area.wait_for(timeout=45000)
            page.wait_for_function("() => !!window.__lanternMdVisual?.state?.currentVersion", timeout=20000)

            state = page.evaluate(
                """name => fetch('/api/work?p=' + encodeURIComponent(name + '.md'))
                   .then(response => response.json())""",
                name,
            )
            temp_path = Path(state["tempPath"])
            real_before = self._snapshot(target)
            temp_before = self._snapshot(temp_path)
            initial = self._install_observers(page)

            # Ignore the initial document navigation and startup API traffic.
            navigations.clear()
            requests.clear()
            area.click()
            page.keyboard.press("Control+Home")
            wall_ms: list[float] = []
            text = "漢字入力試験" if name == "cjk-ime" else "benchmark"
            method = "composition-events" if name == "cjk-ime" else "playwright-keyboard"
            for character in text:
                if name == "cjk-ime":
                    wall_ms.append(self._composition_insert(page, character))
                else:
                    begin = time.perf_counter()
                    page.keyboard.type(character)
                    wall_ms.append(round((time.perf_counter() - begin) * 1000, 3))
                # Deliberately allow the product's existing 90/110/120 ms timers
                # to fire.  Do not mask the full-backdrop cost with a long debounce.
                page.wait_for_timeout(330)

            final_value = area.input_value()
            settled = wait_for_stable_markdown_write(
                page,
                rel=name + ".md",
                target=target,
                expected_content=final_value,
                requests=requests,
                expected_saved_version=state["saved"]["version"],
                timeout_s=30.0,
            )
            final_state = settled["state"]
            write_settled = settled["settled"]
            observed = page.evaluate(
                """() => {
                  const data = window.__sourceP0;
                  const area = document.querySelector('textarea.md-source-area');
                  const backdrop = document.querySelector('.md-source-diff-backdrop-content');
                  return {
                    inputs:data.inputs, paintMs:data.paintMs, longTasks:data.longTasks,
                    mutationRecords:data.mutationRecords, added:data.added, removed:data.removed,
                    maxAdded:data.maxAdded, maxRemoved:data.maxRemoved,
                    focusLost:data.focusLost, caretStarts:data.caretStarts, caretEnds:data.caretEnds,
                    backdropLines:backdrop.children.length,
                    activeClass:document.activeElement?.className || '',
                    selectionStart:area.selectionStart, valuePrefix:area.value.slice(0,40),
                    currentVersion:window.__lanternMdVisual?.state?.currentVersion,
                    savedVersion:window.__lanternMdVisual?.state?.version,
                    workHash:window.__lanternMdVisual?.state?.workHash
                  };
                }"""
            )
            stable_raw = settled["raw"]
            real_after = {"sha256": _sha(stable_raw), "bytes": len(stable_raw)}
            temp_after = self._snapshot(temp_path)
            post_write = settled["write_post_count"]
            get_work = sum(
                method_name == "GET" and url.endswith("/api/work")
                for method_name, url in requests
            )
            backdrop_reference = max(1, int(initial["backdropLines"]))
            full_rebuild = (
                observed["maxAdded"] >= math.floor(backdrop_reference * 0.9)
                and observed["maxRemoved"] >= math.floor(backdrop_reference * 0.9)
            )
            p50 = _percentile(wall_ms, 0.50)
            p95 = _percentile(wall_ms, 0.95)
            paint_p95 = _percentile([float(x) for x in observed["paintMs"]], 0.95)
            focus_preserved = (
                not observed["focusLost"]
                and "md-source-area" in observed["activeClass"]
                and len(observed["caretEnds"]) == observed["inputs"]
            )
            write_through = real_after["sha256"] != real_before["sha256"] and post_write >= 1
            temp_unchanged = temp_after == temp_before
            no_navigation = len(navigations) == 0
            fixed_target = name == "lines-5500"
            within_budget = (
                bool(p95 is not None and p95 < 40.0 and not full_rebuild)
                if fixed_target else None
            )
            contract_ok = (
                write_through
                and write_settled
                and temp_unchanged
                and no_navigation
                and focus_preserved
            )
            if fixed_target:
                acceptance = "PASS" if within_budget and contract_ok else "FAIL"
            else:
                acceptance = "MEASURED_NO_FIXED_THRESHOLD" if contract_ok else "FAIL"
            return {
                "case": name,
                "input_method": method,
                "source_lines": len(self.workloads[name].splitlines()),
                "source_bytes_before": real_before["bytes"],
                "sample_count": len(wall_ms),
                "key_wall_ms": wall_ms,
                "key_wall_p50_ms": p50,
                "key_wall_p95_ms": p95,
                "key_wall_max_ms": max(wall_ms),
                "input_to_next_paint_p95_ms": paint_p95,
                "input_to_next_paint_ms": observed["paintMs"],
                "long_tasks": observed["longTasks"],
                "long_task_count": len(observed["longTasks"]),
                "mutation_records": observed["mutationRecords"],
                "backdrop_dom_added": observed["added"],
                "backdrop_dom_removed": observed["removed"],
                "backdrop_max_added_one_record": observed["maxAdded"],
                "backdrop_max_removed_one_record": observed["maxRemoved"],
                "backdrop_lines_before": initial["backdropLines"],
                "backdrop_lines_after": observed["backdropLines"],
                "full_backdrop_rebuild": full_rebuild,
                "main_document_navigation_count": len(navigations),
                "write_post_count": post_write,
                "work_get_count": get_work,
                "write_settle_poll_count": settled["poll_count"],
                "write_settle_quiet_ms": settled["quiet_ms"],
                "write_settled": write_settled,
                "focus_preserved": focus_preserved,
                "active_class": observed["activeClass"],
                "selection_start": observed["selectionStart"],
                "typed_inputs": observed["inputs"],
                "real_before": real_before,
                "real_after": real_after,
                "initial_real_version": state["currentVersion"],
                "current_real_version": final_state.get("currentVersion"),
                "md_temp_before": temp_before,
                "md_temp_after": temp_after,
                "initial_md_temp_version": state["saved"]["version"],
                "current_md_temp_version": (final_state.get("saved") or {}).get("version"),
                "write_through": write_through,
                "md_temp_unchanged": temp_unchanged,
                "within_budget": within_budget,
                "acceptance": acceptance,
                "page_errors": page_errors,
            }
        finally:
            context.close()

    def test_source_typing_characterization(self) -> None:
        result: dict[str, object] = {
            "schema": 1,
            "browser": {"channel": "msedge", "version": self.browser_version},
            "target": {
                "case": "lines-5500",
                "key_wall_p95_lt_ms": 40.0,
                "full_backdrop_rebuild": False,
            },
            "cases": [],
        }
        try:
            for name in self.workloads:
                case = self._probe(name)
                result["cases"].append(case)
                print("SOURCE_P0_CASE=" + json.dumps(case, ensure_ascii=False), flush=True)
        finally:
            EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        by_name = {item["case"]: item for item in result["cases"]}
        self.assertEqual(set(by_name), set(self.workloads))
        measured_5500 = by_name["lines-5500"]
        expected_budget = (
            measured_5500["key_wall_p95_ms"] < 40.0
            and not measured_5500["full_backdrop_rebuild"]
        )
        self.assertEqual(measured_5500["within_budget"], expected_budget)
        self.assertEqual(
            measured_5500["acceptance"],
            "PASS"
            if expected_budget
            and measured_5500["write_through"]
            and measured_5500["write_settled"]
            and measured_5500["md_temp_unchanged"]
            and measured_5500["main_document_navigation_count"] == 0
            and measured_5500["focus_preserved"]
            else "FAIL",
        )
        for case in result["cases"]:
            self.assertGreater(case["sample_count"], 0)
            self.assertIsNotNone(case["key_wall_p95_ms"])
            self.assertEqual(case["real_before"], case["md_temp_before"])
            self.assertEqual(case["md_temp_before"], case["md_temp_after"])
            self.assertEqual(case["initial_real_version"], case["real_before"]["sha256"])
            self.assertEqual(case["current_real_version"], case["real_after"]["sha256"])
            self.assertEqual(case["initial_md_temp_version"], case["md_temp_before"]["sha256"])
            self.assertEqual(case["current_md_temp_version"], case["md_temp_after"]["sha256"])
            self.assertTrue(case["write_settled"])
            self.assertGreaterEqual(case["write_settle_quiet_ms"], 600)
            self.assertEqual(case["page_errors"], [])


if __name__ == "__main__":
    unittest.main()

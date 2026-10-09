"""Real-browser listing regression tests.

Run with LANTERN_E2E=1 and a Python environment containing Playwright.
Only a private temporary file tree and a dedicated loopback server are used.
LANTERN_E2E_CHANNEL=msedge selects an installed Edge instead of Chromium.
"""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "set LANTERN_E2E=1 for browser E2E")
class ListRefreshE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.temp = tempfile.TemporaryDirectory(prefix="lantern-r1-e2e-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.shared = Path(cls.temp.name) / "shared"
        cls.shared.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        config = Path(cls.temp.name) / "config.yaml"
        config.write_text("\n".join([
            f'root: "{cls.shared.as_posix()}"', f'port: {port}',
            'host: "127.0.0.1"', 'title: "R1 isolated E2E"',
            f'cache_dir: "{(Path(cls.temp.name) / "cache").as_posix()}"',
            'terminal_enabled: false', 'default_view: "list"',
            'page_limit: 100', 'folder_preview_enabled: false',
        ]) + "\n", encoding="utf-8")
        cls.server_log = open(Path(cls.temp.name) / "server.log", "w", encoding="utf-8")
        cls.addClassCleanup(cls.server_log.close)
        cls.server = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"), "--config", str(config)],
            cwd=ROOT, stdout=cls.server_log, stderr=subprocess.STDOUT,
        )
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                if cls.server.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Isolated Lantern did not start: " +
                                       (Path(cls.temp.name) / "server.log").read_text(encoding="utf-8"))
                time.sleep(0.05)
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        options = {"headless": True}
        if os.environ.get("LANTERN_E2E_CHANNEL"):
            options["channel"] = os.environ["LANTERN_E2E_CHANNEL"]
        cls.browser = cls.pw.chromium.launch(**options)
        cls.addClassCleanup(cls.browser.close)
        cls.artifacts = Path(os.environ.get("LANTERN_E2E_ARTIFACTS", ROOT / ".plan" / "lantern-r1-20261009" / "e2e"))
        cls.artifacts.mkdir(parents=True, exist_ok=True)
        cls.case_number = 0

    @classmethod
    def stop_server(cls) -> None:
        if cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=5)

    def setUp(self) -> None:
        type(self).case_number += 1
        self.case = f"case{self.case_number:02d}"
        self.folder = self.shared / self.case
        self.folder.mkdir()
        self.add_files(1, 500)
        self.context = self.browser.new_context(viewport={"width": 1360, "height": 850})
        self.addCleanup(self.context.close)
        # The app persists preferences to its server config; isolate each case.
        self.context.add_init_script("""try {
            localStorage.setItem('lanDrive:sort', 'name-asc');
            localStorage.setItem('lanDrive:page_limit', '100');
            localStorage.setItem('lanDrive:view', 'list');
            localStorage.setItem('lanDrive:folders_first', 'true');
            localStorage.setItem('lanDrive:folder_preview_enabled', 'false');
        } catch (_) {}""")
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors: list[str] = []
        self.requests: list[str] = []
        self.responses: list[dict] = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.requests.append(request.url) if "/api/list?" in request.url else None)
        self.page.on("response", self.record_response)
        self.started = time.perf_counter()

    def record_response(self, response) -> None:
        if "/api/list?" in response.url:
            self.responses.append({"url": response.url, "status": response.status,
                                   "bytes": int(response.headers.get("content-length", 0))})

    def add_files(self, first: int, last: int) -> None:
        for number in range(first, last + 1):
            (self.folder / f"file{number:04d}.txt").write_text(f"fixture {number}\n", encoding="utf-8")

    def card(self, filename: str):
        return self.page.locator(f'#grid .card[data-rel="{self.case}/{filename}"]')

    def open_listing(self, count: int = 500) -> None:
        self.page.goto(f"{self.base}/{self.case}/")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("typeof state !== 'undefined' && !state.loading && state.offset >= 100")
        self.load_until(count)

    def load_until(self, count: int) -> None:
        while self.page.locator('#grid .card[data-isdir="0"]').count() < count:
            previous = self.page.locator('#grid .card[data-isdir="0"]').count()
            self.page.locator("#loader").scroll_into_view_if_needed()
            self.page.wait_for_function("n => !state.loading && state.items.filter(x=>!x.special).length > n", arg=previous)
        self.page.wait_for_function("!state.loading")

    def refresh(self) -> None:
        # DOM click avoids Playwright scrolling a toolbar into view before the action.
        self.page.get_by_role('button', name='↻ Refresh', exact=True).evaluate("button => button.click()")
        self.page.wait_for_function("!state.loading")

    def focus_file(self, name: str = "file0450.txt") -> dict:
        self.card(name).evaluate("card => card.scrollIntoView({block:'center'})")
        return self.page.evaluate("""() => {
            const card = [...document.querySelectorAll('#grid .card[data-isdir="0"]')]
              .find(c => c.getBoundingClientRect().top >= 180 && c.getBoundingClientRect().bottom < innerHeight);
            return {rel:card.dataset.rel, top:card.getBoundingClientRect().top, scroll:scrollY};
        }""")

    def assert_anchor(self, anchor: dict) -> None:
        current = self.page.locator(f'#grid .card[data-rel="{anchor["rel"]}"]')
        self.assertEqual(current.count(), 1)
        self.assertLessEqual(abs(current.evaluate("c=>c.getBoundingClientRect().top") - anchor["top"]), 2)
        self.assertGreater(self.page.evaluate("scrollY"), 1000, "refresh must not reset to page one")

    def assert_listing(self, count: int | None = None) -> None:
        expected = sorted(f"{self.case}/{p.name}" for p in self.folder.iterdir() if p.is_file())
        if count is not None:
            expected = expected[:count]
        actual = self.page.locator('#grid .card[data-isdir="0"]').evaluate_all("cards=>cards.map(c=>c.dataset.rel)")
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), len(actual), "duplicate entries")
        self.assertEqual(self.page.evaluate("state.offset"), len(expected))
        cached = self.page.evaluate("JSON.parse(sessionStorage.getItem(cacheKey())).items.filter(x=>!x.special).map(x=>x.rel)")
        self.assertEqual(cached, expected)
        self.assertEqual(self.page.locator('#grid .card[data-name=".."]').count(), 1)

    def tearDown(self) -> None:
        name = self._testMethodName
        self.page.screenshot(path=str(self.artifacts / f"{name}.png"))
        result = {"test": name, "browser": self.browser.version,
                  "seconds": round(time.perf_counter() - self.started, 3),
                  "requests": self.requests, "responses": self.responses, "page_errors": self.errors}
        (self.artifacts / f"{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.assertEqual(self.errors, [], "uncaught browser errors")

    def test_external_delete_deep_page_manual_refresh(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        (self.folder / "file0450.txt").unlink()
        self.refresh()
        self.assertEqual(self.card("file0450.txt").count(), 0, "R1: page-five deleted file must disappear")
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_ui_rename_deep_page_preserves_position(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        self.card("file0450.txt").locator(".check").click()
        self.page.once("dialog", lambda dialog: dialog.accept("file0450-renamed.txt"))
        self.page.locator("#renameBtn").evaluate("button=>button.click()")
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assertTrue((self.folder / "file0450-renamed.txt").exists())
        self.assertEqual(self.card("file0450-renamed.txt").count(), 1)
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_ui_delete_deep_page_updates_cache(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        self.card("file0450.txt").locator(".check").click()
        self.page.once("dialog", lambda dialog: dialog.accept())
        self.page.locator("#deleteBtn").evaluate("button=>button.click()")
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assertFalse((self.folder / "file0450.txt").exists())
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_unchanged_refresh_keeps_nodes_selection_and_scroll(self) -> None:
        self.open_listing()
        self.card("file0449.txt").locator(".check").click()
        anchor = self.focus_file()
        self.page.evaluate("window.r1Nodes = [...document.querySelectorAll('#grid .card')]")
        self.refresh()
        self.assertTrue(self.page.evaluate("window.r1Nodes.every((node,i)=>node===document.querySelectorAll('#grid .card')[i])"))
        self.assertTrue(self.card("file0449.txt").evaluate("c=>c.classList.contains('selected')"))
        self.assert_anchor(anchor)
        self.assert_listing()

    def test_cache_restoration_revalidates_all_loaded_pages(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        self.page.goto("about:blank")
        (self.folder / "file0450.txt").unlink()
        self.page.goto(f"{self.base}/{self.case}/")
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_focus_handler_revalidates_deep_page(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        (self.folder / "file0450.txt").unlink()
        self.page.clock.install()
        self.page.clock.fast_forward(5100)
        self.page.evaluate("window.dispatchEvent(new Event('focus'))")
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_refresh_over_server_limit_preserves_continuation(self) -> None:
        self.add_files(501, 1205)
        self.open_listing(1100)
        self.focus_file("file1050.txt")
        (self.folder / "file1050.txt").unlink()
        start = len(self.requests)
        self.refresh()
        self.assert_listing(1100)
        refresh_requests = self.requests[start:]
        self.assertGreaterEqual(len(refresh_requests), 2, "loaded range above server cap must be revalidated")
        self.load_until(1204)
        self.assert_listing()
        self.assertFalse(self.page.evaluate("state.hasMore"))

    def test_mutation_during_refresh_cannot_commit_stale_response(self) -> None:
        self.open_listing()
        self.focus_file()
        held = []
        def hold_first(route):
            if held:
                route.continue_()
            else:
                held.append((route, route.fetch()))
        self.page.route("**/api/list?*", hold_first)
        self.page.locator('[onclick="refreshFolder()"]').evaluate("button=>button.click()")
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            self.page.wait_for_timeout(10)
        self.assertTrue(held, "refresh response was not intercepted")
        self.card("file0450.txt").locator(".check").click()
        self.page.once("dialog", lambda dialog: dialog.accept("file0450-renamed.txt"))
        with self.page.expect_response("**/api/rename"):
            self.page.locator("#renameBtn").evaluate("button=>button.click()")
        self.page.wait_for_function("document.querySelector('#renameBtn') !== null")
        held[0][0].fulfill(response=held[0][1])
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assert_listing()

    def test_sort_change_during_refresh_discards_old_result(self) -> None:
        self.open_listing()
        held = []
        def hold_first(route):
            if held:
                route.continue_()
            else:
                held.append((route, route.fetch()))
        self.page.route("**/api/list?*", hold_first)
        self.page.locator('[onclick="refreshFolder()"]').evaluate("button=>button.click()")
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            self.page.wait_for_timeout(10)
        self.assertTrue(held)
        self.page.locator("#sortSelect").select_option("name-desc")
        held[0][0].fulfill(response=held[0][1])
        self.page.wait_for_function("!state.loading && state.items.some(x=>x.name==='file0500.txt')")
        actual = self.page.locator('#grid .card[data-isdir="0"]').evaluate_all("cards=>cards.map(c=>c.dataset.rawname)")
        self.assertEqual(actual, [f"file{i:04d}.txt" for i in range(500, 500-len(actual), -1)])

    def test_lazy_timer_no_four_second_rebuild_and_deep_refresh(self) -> None:
        # Install before page scripts create timers, not after navigation.
        self.page.clock.install()
        self.open_listing()
        self.focus_file()
        count = len(self.requests)
        self.page.evaluate("window.r1Nodes = [...document.querySelectorAll('#grid .card')]")
        self.page.clock.fast_forward(4500)
        self.assertEqual(len(self.requests), count, "four-second polling must not return")
        self.assertTrue(self.page.evaluate("window.r1Nodes.every((n,i)=>n===document.querySelectorAll('#grid .card')[i])"))
        (self.folder / "file0450.txt").unlink()
        self.page.clock.fast_forward(31000)
        self.page.wait_for_function("!state.loading && !state.items.some(x=>x.name==='file0450.txt')")
        self.assert_listing()

    def test_later_page_failure_keeps_complete_old_window(self) -> None:
        self.add_files(501, 1205)
        self.open_listing(1100)
        self.focus_file("file1050.txt")
        self.page.evaluate("window.r1Nodes=[...document.querySelectorAll('#grid .card')]")
        old = self.page.evaluate("JSON.stringify(state.items)")
        (self.folder / "file1050.txt").unlink()
        def fail_second(route):
            if "offset=1000" in route.request.url:
                route.fulfill(status=503, content_type="application/json", body='{"error":"test outage"}')
            else:
                route.continue_()
        self.page.route("**/api/list?*", fail_second)
        self.refresh()
        self.assertEqual(self.page.evaluate("JSON.stringify(state.items)"), old, "partial window must not commit")
        self.assertTrue(self.page.evaluate("r1Nodes.every((n,i)=>n===document.querySelectorAll('#grid .card')[i])"))
        self.assertIn("test outage", self.page.locator("#toast").inner_text())
        self.page.unroute("**/api/list?*", fail_second)
        self.refresh()
        self.assert_listing(1100)

    def test_new_tail_updates_pagination_without_replacing_nodes(self) -> None:
        self.open_listing()
        self.focus_file()
        self.page.evaluate("window.r1Nodes=[...document.querySelectorAll('#grid .card')]")
        self.add_files(501, 501)
        self.refresh()
        self.assertTrue(self.page.evaluate("state.hasMore"))
        self.assertTrue(self.page.evaluate("r1Nodes.every((n,i)=>n===document.querySelectorAll('#grid .card')[i])"))
        self.assert_listing(500)
        self.load_until(501)
        self.assert_listing()

    def test_append_failure_stops_until_explicit_retry(self) -> None:
        self.open_listing(100)
        failed = []
        def fail_append(route):
            failed.append(route.request.url)
            route.fulfill(status=503, content_type='application/json', body='{"error":"append outage"}')
        self.page.route('**/api/list?*', fail_append)
        self.page.locator('#loader').scroll_into_view_if_needed()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('append outage')")
        # Leave many animation frames for an accidental observer re-registration.
        self.page.wait_for_timeout(600)
        self.assertEqual(len(failed), 1, 'append failure must not retry on every animation frame')
        self.assertEqual(self.page.locator('#toast > div').count(), 1)
        self.assert_listing(100)
        self.page.unroute('**/api/list?*', fail_append)
        self.page.locator('#loader button').click()
        self.page.wait_for_function('!state.loading && state.offset >= 200')
        self.load_until(500)
        self.assert_listing()

    def test_insert_before_loaded_window_repairs_append_once(self) -> None:
        self.open_listing(300)
        (self.folder / 'file0000a.txt').write_text('inserted before the loaded window', encoding='utf-8')
        start = len(self.requests)
        self.page.locator('#loader').scroll_into_view_if_needed()
        self.page.wait_for_timeout(600)
        self.assertLessEqual(len(self.requests)-start, 3, 'one append, one repair refresh, one corrected append')
        self.page.wait_for_function('!state.loading && state.offset >= 400')
        self.load_until(501)
        self.assert_listing()
        self.assertEqual(self.page.locator('#toast > div').count(), 0)

    def test_initial_empty_root_shows_empty_state(self) -> None:
        # Only this suite's temporary fixtures are hidden; no operator files.
        for child in self.shared.iterdir():
            if not child.name.startswith('.'):
                child.rename(child.with_name('.hidden-' + child.name))
        self.page.goto(self.base + '/')
        self.page.wait_for_load_state('networkidle')
        self.page.wait_for_function("typeof state!=='undefined' && !state.loading")
        self.assertEqual(self.page.evaluate('state.offset'), 0)
        self.assertEqual(self.page.locator('#grid .empty').count(), 1)
        self.assertEqual(self.page.locator('#loader').count(), 0)

    def test_shrink_to_empty_does_not_count_parent_as_file(self) -> None:
        self.open_listing()
        for item in self.folder.iterdir():
            item.unlink()
        self.refresh()
        self.assert_listing()
        self.assertEqual(self.page.evaluate("state.offset"), 0)
        self.assertFalse(self.page.evaluate("state.hasMore"))
        self.page.goto("about:blank")
        self.page.goto(f"{self.base}/{self.case}/")
        self.page.wait_for_function("typeof state!=='undefined' && !state.loading")
        self.assert_listing()

    def test_changed_refresh_preserves_other_selected_file(self) -> None:
        self.open_listing()
        self.card("file0449.txt").locator(".check").click()
        anchor = self.focus_file()
        (self.folder / "file0450.txt").unlink()
        self.refresh()
        self.assertTrue(self.card("file0449.txt").evaluate("c=>c.classList.contains('selected')"))
        self.assert_listing()
        self.assert_anchor(anchor)

    def test_mkdir_preserves_loaded_depth_and_position(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        self.page.once("dialog", lambda dialog: dialog.accept("new-folder"))
        self.page.locator('[onclick="mkdir()"]').evaluate("button=>button.click()")
        self.page.wait_for_function("!state.loading && state.items.some(x=>x.name==='new-folder')")
        self.assertEqual(self.page.evaluate("state.offset"), 500)
        self.assertEqual(self.card("file0450.txt").count(), 1)
        self.assert_anchor(anchor)

    def test_upload_completion_preserves_loaded_depth(self) -> None:
        self.open_listing()
        anchor = self.focus_file()
        self.page.locator("#fileInput").set_input_files({
            "name": "file0450-uploaded.txt", "mimeType": "text/plain", "buffer": b"R1 upload fixture\n"})
        self.page.locator('[onclick="startUploadQueue()"]').evaluate("button=>button.click()")
        self.page.wait_for_function("!uploadState.running && !state.loading && uploadState.queue.some(x=>x.state==='done')")
        self.assertTrue((self.folder / "file0450-uploaded.txt").exists())
        self.assertEqual(self.page.evaluate("state.offset"), 500)
        self.assertEqual(self.card("file0450-uploaded.txt").count(), 1)
        self.assert_anchor(anchor)

    def test_measure_unchanged_loaded_window_refresh(self) -> None:
        import statistics
        self.open_listing()
        self.focus_file()
        timings, sizes, counts = [], [], []
        for _ in range(15):
            first = len(self.responses)
            start = time.perf_counter()
            self.refresh()
            timings.append((time.perf_counter()-start)*1000)
            replies = self.responses[first:]
            sizes.append(sum(reply["bytes"] for reply in replies))
            counts.append(len(replies))
        metrics = {"loaded_files": 500, "runs": 15, "scope": "loopback, unchanged loaded window",
                   "p50_ms": round(statistics.median(timings), 2),
                   "p95_ms": round(sorted(timings)[14], 2), "response_bytes_median": statistics.median(sizes),
                   "requests_per_refresh": counts, "samples_ms": timings}
        (self.artifacts / "refresh_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        self.assertEqual(counts, [1]*15)
        self.assertEqual(self.page.locator('#grid .card[data-isdir="0"]').count(), 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)

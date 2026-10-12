"""Isolated real-Edge terminal lifecycle checks (never connects to the live Lantern service).

LANTERN_E2E=1 uv run --with-requirements requirements.txt --with playwright python -m unittest -v test_terminal_e2e
"""
from __future__ import annotations

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


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "requires LANTERN_E2E=1")
class TerminalLifecycleBrowserE2E(unittest.TestCase):
    def test_failed_spawn_then_real_terminal_and_stale_input(self):
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory(prefix="lantern-terminal-e2e-", ignore_cleanup_errors=True) as tmp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "lan_drive.py"), "--root", tmp,
                 "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=0.5):
                            break
                    except Exception:
                        time.sleep(0.1)
                else:
                    self.fail("isolated terminal server did not start")

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge", headless=True)
                    try:
                        page = browser.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                        page.wait_for_function("() => !!window.__lanternTerminalScm?.state.termListReady", timeout=15000)
                        page.evaluate("""() => {
                          window.__terminalEvents = [];
                          window.__lanternTerminalScm.state.ws.addEventListener('message', e => {
                            const data = JSON.parse(e.data);
                            if (data.type === 'terminal_error' || data.type === 'terminal_created')
                              window.__terminalEvents.push(data);
                          });
                        }""")

                        # Force one rejected start; the optimistic tab must disappear,
                        # leaving a useful error rather than a ghost session.
                        page.evaluate("() => {window.APP.currentPath='../outside'; window.newTerminalSession()}")
                        page.wait_for_function("""() => window.__terminalEvents.some(
                          e => e.type==='terminal_error' && e.code==='terminal_start_failed')""", timeout=13000)
                        self.assertEqual(page.evaluate("() => window.__lanternTerminalScm.state.terms.size"), 0)
                        self.assertFalse(page.evaluate("() => window.__lanternTerminalScm.state.active"))

                        # A normal terminal must still start and accept real PTY input.
                        page.evaluate("() => {window.APP.currentPath=''; window.newTerminalSession()}")
                        page.wait_for_function("""() => [...window.__lanternTerminalScm.state.terms.values()].some(
                          t => !t.pending && t.meta.running && t.meta.generation)""", timeout=16000)
                        term_id = page.evaluate("() => window.__lanternTerminalScm.state.active")
                        self.assertTrue(page.evaluate("() => window.__terminalEvents.some(e => e.type==='terminal_created')"))
                        terminal = page.locator(".lx-xterm-host:not(.hidden) .xterm-helper-textarea").first
                        terminal.focus()
                        page.keyboard.type("echo LANTERN_SESSION_PROOF\n", delay=15)
                        page.wait_for_function("""() => {
                          const s=window.__lanternTerminalScm.state,t=s.terms.get(s.active);
                          const b=t?.term?.buffer?.active;
                          return b && Array.from({length:b.length},(_,i)=>b.getLine(i)?.translateToString())
                            .join(' ').includes('LANTERN_SESSION_PROOF');
                        }""", timeout=12000)

                        # An old tab sending input after a session is killed should get
                        # a correlated terminal_not_running event, not an unexplained toast.
                        page.locator("#lxKillTerm").click()
                        page.wait_for_function("() => window.__lanternTerminalScm.state.terms.size===0", timeout=10000)
                        page.evaluate("(id) => window.__lanternTerminalScm.state.ws.send(JSON.stringify({type:'terminal_input',terminalId:id,data:'x'}))", term_id)
                        page.wait_for_function("""() => window.__terminalEvents.some(
                          e => e.type==='terminal_error' && e.code==='terminal_not_running')""", timeout=10000)
                        self.assertEqual(errors, [], "Browser JS errors: " + repr(errors))
                    finally:
                        browser.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

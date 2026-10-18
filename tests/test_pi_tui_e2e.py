"""Native Pi TUI proof through TerminalManager + real WinConPty.

Run explicitly on Windows with:
  LANTERN_PI_TUI_E2E=1 uv run python -m unittest -v tests.test_pi_tui_e2e

This proof sends only local Pi slash commands and local shell input; it never sends
an AI prompt. Browser/WS/reconnect/physical IME coverage belongs to later gates.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from lantern.terminal import TerminalManager, WinConPty


def _pi_argv(session_dir: Path) -> list[str]:
    node = shutil.which("node")
    appdata = os.environ.get("APPDATA")
    if not node or not appdata:
        raise unittest.SkipTest("node/APPDATA required for native Pi TUI proof")
    cli = (
        Path(appdata)
        / "npm"
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "bundle"
        / "cli.js"
    )
    if not cli.is_file():
        raise unittest.SkipTest(f"installed Pi CLI bundle not found: {cli}")
    return [
        node,
        str(cli),
        "--offline",
        "--approve",
        "--no-mcp",
        "--session-dir",
        str(session_dir),
        "--session-id",
        "7b40cb7d-871a-4c92-8a38-6dc223709703",
        "--tui-mode",
        "regular",
    ]


@unittest.skipUnless(os.name == "nt", "WinConPty proof requires Windows")
@unittest.skipUnless(
    os.environ.get("LANTERN_PI_TUI_E2E") == "1",
    "set LANTERN_PI_TUI_E2E=1 to run native Pi TUI proof",
)
class NativePiTerminalManagerE2E(unittest.TestCase):
    def test_terminal_manager_hosts_native_pi_tui_without_shell_wrapping(self) -> None:
        events: list[dict] = []

        with tempfile.TemporaryDirectory(
            prefix="lantern-pi-tui-e2e-", ignore_cleanup_errors=True
        ) as tmp:
            root = Path(tmp)
            session_dir = root / "sessions"
            session_dir.mkdir()
            argv = _pi_argv(session_dir)
            spawned: list[list[str]] = []

            def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
                self.assertIsNone(command, "Pi proof must not use shell command wrapping")
                spawned.append(argv.copy())
                return WinConPty(argv, str(cwd), cols, rows, on_data, on_exit)

            manager = TerminalManager(
                root,
                events.append,
                pty_factory=factory,
                flush_ms=0.01,
            )
            term_id = "pi-native-poc"

            def replay() -> tuple[dict, str, int]:
                return manager.replay_one(term_id)

            def wait_for(
                needle: str,
                *,
                timeout: float = 10.0,
                count: int = 1,
            ) -> str:
                deadline = time.monotonic() + timeout
                last = ""
                while time.monotonic() < deadline:
                    _, last, _ = replay()
                    if last.count(needle) >= count:
                        return last
                    time.sleep(0.05)
                self.fail(f"Pi TUI output did not contain {needle!r}; tail={last[-1200:]!r}")

            try:
                info = manager.create(term_id, root, 100, 32, "Native Pi POC")
                self.assertTrue(info["running"])
                self.assertTrue(info["generation"])
                self.assertEqual((info["cols"], info["rows"]), (100, 32))
                self.assertEqual(spawned, [argv])
                self.assertNotIn("-Command", argv)
                self.assertNotIn("/C", argv)

                # Allow startup/extensions to settle before opening local UI.
                time.sleep(8.0)

                manager.input(term_id, "/settings\r")
                settings = wait_for("Auto-resize images")
                self.assertIn("Skill commands", settings)
                manager.input(term_id, "\x1b")
                time.sleep(0.5)

                manager.input(term_id, "/resume\r")
                resume = wait_for("Resume Session (Current Folder)")
                self.assertIn("No sessions in current folder", resume)
                manager.input(term_id, "\x1b")
                time.sleep(0.5)

                marker = "PI_NATIVE_SHELL_PROOF"
                manager.input(term_id, f"!!echo {marker}\r")
                shell = wait_for(marker, count=2)
                self.assertGreaterEqual(
                    shell.count(marker),
                    2,
                    "expect displayed local command plus its native shell output",
                )

                pasted = "PASTE 日本語 tiếng Việt 😀"
                manager.input(term_id, f"\x1b[200~{pasted}\x1b[201~")
                wait_for(pasted)
                manager.input(term_id, "\x15")

                typed = "Unicode 日本語 tiếng Việt 😀"
                manager.input(term_id, typed)
                wait_for(typed)
                manager.input(term_id, "\x15")
                manager.input(term_id, "\x1bf")
                manager.input(term_id, "\x03")

                manager.input(term_id, "/new\r")
                wait_for("New session started")

                manager.input(term_id, "/session\r")
                session = wait_for("Messages")
                self.assertIn("Tools:", session)
                self.assertIn("Status:", session)

                manager.resize(term_id, 120, 40)
                listed = {item["id"]: item for item in manager.list()}
                self.assertEqual(
                    (listed[term_id]["cols"], listed[term_id]["rows"]),
                    (120, 40),
                )

                meta, output, seq = replay()
                self.assertEqual(meta["generation"], info["generation"])
                self.assertGreater(seq, 0)
                self.assertIn(marker, output)
                output_events = [
                    e for e in events
                    if e.get("type") == "terminal_output"
                    and e.get("terminalId") == term_id
                ]
                self.assertGreater(len(output_events), 0)
                self.assertTrue(
                    all(e.get("generation") == info["generation"] for e in output_events)
                )
                seqs = [int(e["seq"]) for e in output_events]
                self.assertEqual(seqs, sorted(seqs))
                self.assertEqual(len(seqs), len(set(seqs)))
            finally:
                manager.kill(term_id)
                deadline = time.monotonic() + 3.0
                while manager.list() and time.monotonic() < deadline:
                    time.sleep(0.05)

            self.assertEqual(manager.list(), [])
            self.assertTrue(
                any(
                    e.get("type") == "terminal_exit"
                    and e.get("terminalId") == term_id
                    for e in events
                )
            )


if __name__ == "__main__":
    unittest.main()

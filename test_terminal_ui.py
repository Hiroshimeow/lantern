from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "lan_drive.py"
CLIENT = ROOT / "static" / "terminal_scm.js"


class TerminalUiParityTests(unittest.TestCase):
    def test_legacy_fake_terminal_is_retired(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        forbidden = [
            "termAppend(", "termCSI(", "TerminalSession", "terminal_run_command",
            "/api/term/read", "/api/term/new", "terminal_poll_ms",
        ]
        for token in forbidden:
            self.assertNotIn(token, source, token)
        self.assertIn('parsed.path == "/ws"', source)
        self.assertIn('/static/vendor/xterm.js', source)
        self.assertIn('/static/vendor/addon-fit.js', source)
        self.assertIn('/static/terminal_scm.js', source)

    def test_browser_client_uses_xterm_websocket_and_scm_correlation(self) -> None:
        js = CLIENT.read_text(encoding="utf-8")
        self.assertIn("new WebSocket", js)
        self.assertIn("new Terminal(", js)
        self.assertIn("new FitAddon.FitAddon()", js)
        self.assertIn("scrollback:8000", js)
        self.assertIn("terminal_snapshot", js)
        self.assertIn("terminal_run", js)
        self.assertIn("function activeLive()", js)
        self.assertIn("t.meta.running!==false", js)
        self.assertIn("scm_data", js)
        self.assertIn("reqId", js)
        self.assertIn("setInterval", js)
        self.assertNotIn("/api/term/read", js)
        self.assertNotIn("setInterval(termPoll", js)

    def test_browser_client_parses_as_javascript(self) -> None:
        result = subprocess.run(
            ["node", "--check", str(CLIENT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

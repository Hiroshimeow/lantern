from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern.pi_sessions import PiSessionRegistry
from lantern.terminal import TerminalManager
from lantern.ws import WebSocketHub, dispatch


class _FakePty:
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit
        self.writes = []
        self.resizes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def resize(self, cols, rows):
        self.resizes.append((cols, rows))

    def close(self, graceful=True):
        self.closed = True


class _Peer:
    def __init__(self):
        self.protocol = "v2"
        self.subscriptions = set()
        self.messages = []

    def can_terminal(self):
        return True

    def send(self, message):
        self.messages.append(message)


class NativePiRuntimeWiringTests(unittest.TestCase):
    def test_sync_create_attach_input_and_stop_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="lantern-native-pi-wire-") as td:
            root = Path(td) / "root"
            docs = root / "docs"
            docs.mkdir(parents=True)
            state = Path(td) / "state"
            hub = WebSocketHub()
            spawned = {}

            def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **kwargs):
                pty = _FakePty(on_data, on_exit)
                spawned[term_id] = pty
                return pty

            terminal = TerminalManager(root, hub.broadcast, pty_factory=factory, flush_ms=0)
            registry = PiSessionRegistry(
                root,
                state,
                terminal,
                ["node", "pi.js"],
                id_factory=lambda: "nativeA",
                context_prompt_factory=lambda context: (
                    "Lantern context: " + str(context.get("path") or context.get("folder") or "/")
                ),
            )
            peer = _Peer()
            hub.add(peer)
            try:
                dispatch(
                    peer,
                    {"type": "pi_session_sync"},
                    terminal,
                    None,
                    hub,
                    pi=registry,
                )
                self.assertEqual(peer.messages[-1], {"type": "pi_session_state", "sessions": []})

                context = {"kind": "markdown", "path": "docs/spec with space.md", "line": 7}
                dispatch(
                    peer,
                    {
                        "type": "pi_session_create",
                        "context": context,
                        "cols": 101,
                        "rows": 33,
                    },
                    terminal,
                    None,
                    hub,
                    pi=registry,
                )
                created = peer.messages[-1]
                self.assertEqual(created["type"], "pi_session_created")
                session = created["session"]
                self.assertEqual(session["sessionId"], "nativeA")
                self.assertEqual(Path(session["cwd"]), docs.resolve())
                self.assertEqual(session["contextRef"], context)
                argv = terminal.live[session["terminalId"]].pty.argv if hasattr(terminal.live[session["terminalId"]].pty, "argv") else None
                # Structured argv itself is characterized by PiSessionRegistry tests.

                dispatch(
                    peer,
                    {
                        "type": "pi_session_attach",
                        "sessionId": session["sessionId"],
                        "generation": session["generation"],
                    },
                    terminal,
                    None,
                    hub,
                    pi=registry,
                )
                replay = peer.messages[-1]
                self.assertEqual(replay["type"], "pi_session_replay")
                self.assertEqual(replay["role"], "writer")

                dispatch(
                    peer,
                    {
                        "type": "pi_session_input",
                        "sessionId": session["sessionId"],
                        "generation": session["generation"],
                        "ownershipEpoch": replay["ownershipEpoch"],
                        "data": "/model\r",
                    },
                    terminal,
                    None,
                    hub,
                    pi=registry,
                )
                self.assertEqual(spawned[session["terminalId"]].writes, ["/model\r"])

                dispatch(
                    peer,
                    {
                        "type": "pi_session_stop",
                        "sessionId": session["sessionId"],
                        "generation": session["generation"],
                    },
                    terminal,
                    None,
                    hub,
                    pi=registry,
                )
                self.assertEqual(peer.messages[-1]["type"], "pi_session_stopped")
                self.assertFalse(peer.messages[-1]["session"]["running"])
            finally:
                registry.close()
                terminal.kill_all()

    def test_context_cwd_stays_inside_root(self):
        with tempfile.TemporaryDirectory(prefix="lantern-native-pi-context-") as td:
            root = Path(td) / "root"
            root.mkdir()
            state = Path(td) / "state"
            terminal = TerminalManager(root, lambda _event: None)
            registry = PiSessionRegistry(root, state, terminal, ["pi"], id_factory=lambda: "x")
            with self.assertRaisesRegex(ValueError, "inside"):
                registry.context_cwd({"kind": "folder", "folder": "../outside"})


if __name__ == "__main__":
    unittest.main()

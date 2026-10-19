[Reading 200 lines from start (total: 1744 lines, 1544 remaining)]

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from lantern.pi_sessions import PiSessionRegistry
from lantern.terminal import TerminalManager
from lantern.ws import WebSocketHub, _legacy_snapshot_payload, dispatch


class FakePty:
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit
        self.writes: list[str] = []
        self.keys: list[tuple[str, dict]] = []
        self.resizes: list[tuple[int, int]] = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def key(self, key, modifiers):
        self.keys.append((key, dict(modifiers)))

    def resize(self, cols, rows):
        self.resizes.append((cols, rows))

    def close(self, graceful=True):
        self.closed = True

    def emit(self, data):
        self.on_data(data)


class Peer:
    def __init__(self, *, allowed=True):
        self.protocol = "v2"
        self.subscriptions = set()
        self.messages: list[dict] = []
        self.allowed = allowed

    def can_terminal(self):
        return self.allowed

    def send(self, message):
        self.messages.append(message)


class PiWsContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "root"
        self.state = Path(self.tmp.name) / "state"
        self.root.mkdir()
        self.spawned: dict[str, FakePty] = {}
        self.hub = WebSocketHub()

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **kwargs):
            pty = FakePty(on_data, on_exit)
            self.spawned[term_id] = pty
            return pty

        self.terminal = TerminalManager(
            self.root, self.hub.broadcast, pty_factory=factory, flush_ms=0
        )
        ids = iter(["sessA", "sessB"])
        self.registry = PiSessionRegistry(
            self.root,
            self.state,
            self.terminal,
            ["node", "pi.js"],
            id_factory=lambda: next(ids),
        )
        self.a = self.registry.create(cwd=self.root, context_ref={"path": "a.md"})
        self.b = self.registry.create(cwd=self.root, context_ref={"path": "b.md"})

    def tearDown(self):
        self.registry.close()
        self.tmp.cleanup()

    def attach(self, peer, session):
        self.hub.add(peer)
        dispatch(
            peer,
            {
                "type": "pi_session_attach",
                "sessionId": session["sessionId"],
                "generation": session["generation"],
            },
            self.terminal,
            None,
            self.hub,
            pi=self.registry,
        )
        return peer.messages[-1]

    def op(self, peer, message):
        dispatch(
            peer,
            message,
            self.terminal,
            None,
            self.hub,
            pi=self.registry,
        )

    def test_first_attach_writer_second_viewer_replay_and_output_scope(self):
        writer, viewer, unrelated = Peer(), Peer(), Peer()
        replay_a = self.attach(writer, self.a)
        replay_a_again = self.attach(writer, self.a)
        replay_b = self.attach(viewer, self.a)
        self.hub.add(unrelated)

        self.assertEqual(replay_a["type"], "pi_session_replay")
        self.assertEqual(replay_a["sessionId"], self.a["sessionId"])
        self.assertEqual(replay_a["generation"], self.a["generation"])
        self.assertEqual(replay_a["role"], "writer")
        self.assertEqual(replay_a_again["role"], "writer")
        self.assertEqual(replay_a_again["ownershipEpoch"], replay_a["ownershipEpoch"])
        self.assertEqual(replay_b["role"], "viewer")
        self.assertEqual(replay_b["ownershipEpoch"], replay_a["ownershipEpoch"])
        self.assertNotIn("terminalId", replay_a)
        self.assertEqual(replay_a["seq"], 0)
        self.assertEqual((replay_a["replayStartUtf8"], replay_a["replayEndUtf8"]), (0, 0))

        self.spawned[self.a["terminalId"]].emit("A-output")
        a_events = [m for m in writer.messages if m["type"] == "pi_session_output"]
        b_events = [m for m in viewer.messages if m["type"] == "pi_session_output"]
        self.assertEqual(len(a_events), 1)
        self.assertEqual(len(b_events), 1)
        self.assertEqual(a_events[0]["data"], "A-output")
        self.assertEqual(a_events[0]["sessionId"], self.a["sessionId"])
        self.assertNotIn("terminalId", a_events[0])
        self.assertFalse(any(m.get("type") == "terminal_output" for m in writer.messages))
        self.assertFalse(any(m.get("type") == "pi_session_output" for m in unrelated.messages))

    def test_writer_input_key_resize_viewer_denied_and_takeover_epoch(self):
        writer, viewer = Peer(), Peer()
        first = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        epoch = first["ownershipEpoch"]
        common = {
            "sessionId": self.a["sessionId"],
            "generation": self.a["generation"],
            "ownershipEpoch": epoch,
        }
        self.op(writer, {**common, "type": "pi_session_input", "data": "x"})
        self.op(writer, {**common, "type": "pi_session_key", "key": "Enter", "modifiers": {}})
        self.op(writer, {**common, "type": "pi_session_resize", "cols": 111, "rows": 37})
        pty = self.spawned[self.a["terminalId"]]
        self.assertEqual(pty.writes, ["x", "\r"])
        self.assertEqual(pty.keys, [])
        self.assertEqual(pty.resizes, [(111, 37)])

        for typ in ("pi_session_input", "pi_session_key", "pi_session_resize"):
            with self.assertRaisesRegex(PermissionError, "writer"):
                self.op(viewer, {**common, "type": typ, "data": "bad", "key": "x", "cols": 2, "rows": 2})

        self.op(
            viewer,
            {
                "type": "pi_session_takeover",
                "sessionId": self.a["sessionId"],
                "generation": self.a["generation"],
            },
        )
        notice_writer = [m for m in writer.messages if m["type"] == "pi_session_ownership"][-1]
        notice_viewer = [m for m in viewer.messages if m["type"] == "pi_session_ownership"][-1]
        self.assertEqual(notice_writer["role"], "viewer")
        self.assertEqual(notice_viewer["role"], "writer")
        epoch2 = notice_viewer["ownershipEpoch"]
        self.assertGreater(epoch2, epoch)

        with self.assertRaisesRegex(PermissionError, "stale owner"):
            self.op(writer, {**common, "type": "pi_session_input", "data": "stale"})
        with self.assertRaisesRegex(PermissionError, "writer"):
            self.op(writer, {**common, "ownershipEpoch": epoch2, "type": "pi_session_input", "data": "no"})
        self.op(viewer, {**common, "ownershipEpoch": epoch2, "type": "pi_session_input", "data": "y"})
        self.assertEqual(pty.writes, ["x", "\r", "y"])

    def test_detach_and_disconnect_release_writer_without_killing_process(self):
        writer, viewer = Peer(), Peer()
        first = self.attach(writer, self.a)
        self.attach(viewer, self.a)
        self.op(writer, {"type": "pi_session_detach", "sessionId": self.a["sessionId"]})

        self.assertTrue(self.registry.get(self.a["sessionId"])["running"])
        self.spawned[self.a["terminalId"]].emit("still-live")
        self.assertTrue(any(m.get("data") == "still-live" for m in viewer.messages))
        with self.assertRaisesRegex(PermissionError, "writer"):
            self.op(
                viewer,
                {
                    "type": "pi_session_input",
                    "sessionId": self.a["sessionId"],
                    "generation": self.a["generation"],
                    "ownershipEpoch": first["ownershipEpoch"] + 1    def test_attach_replay_cannot_regress_ownership_after_takeover(self):
        writer_a, viewer_b = Peer(), Peer()
        self.hub.add(writer_a)
        self.hub.add(viewer_b)

        attach_published = threading.Event()
        viewer_started = threading.Event()
        writer_errors = []
        viewer_errors = []
        original_attach = self.hub.pi_attach
        writer_a._pi_notice_lock = threading.Lock()
        writer_a._pi_notice_lock.acquire()

        def signaled_attach(*args, **kwargs):
            result = original_attach(*args, **kwargs)
            if args and args[0] is writer_a:
                attach_published.set()
            return result

        self.hub.pi_attach = signaled_attach

        def attach_writer():
            try:
                self.op(
                    writer_a,
                    {
                        "type": "pi_session_attach",
                        "sessionId": self.a["sessionId"],
                        "generation": self.a["generation"],
                    },
                )
            except Exception as exc:
                writer_errors.append(exc)

        def attach_viewer():
            viewer_started.set()
            try:
                self.op(
                    viewer_b,
                    {
                        "type": "pi_session_attach",
                        "sessionId": self.a["sessionId"],
                        "generation": self.a["generation"],
                    },
                )
            except Exception as exc:
                viewer_errors.append(exc)

        writer_thread = threading.Thread(target=attach_writer)
        writer_thread.start()
        self.assertTrue(
            attach_published.wait(2),
            "writer attach never published route state",
        )

        viewer_thread = threading.Thread(target=attach_viewer)
        viewer_thread.start()
        self.assertTrue(viewer_started.wait(2))
        self.assertTrue(
            viewer_thread.is_alive(),
            "viewer attach must wait until writer replay initialization releases terminal ownership",
        )

        writer_a._pi_notice_lock.release()
        writer_thread.join(2)
        viewer_thread.join(2)
        self.assertFalse(writer_thread.is_alive())
        self.assertFalse(viewer_thread.is_alive())
        self.assertEqual(writer_errors, [])
        self.assertEqual(viewer_errors, [])

        replay_b = next(
            message
            for message in viewer_b.messages
            if message.get("type") == "pi_session_replay"
        )
        self.assertEqual(replay_b["role"], "viewer")

        self.op(
            viewer_b,
            {
                "type": "pi_session_takeover",
                "sessionId": self.a["sessionId"],
                "generation": self.a["generation"],
            },
        )

        route = self.hub.pi_routes[self.a["sessionId"]]
        states = [
            (
                message.get("type"),
                message.get("ownershipEpoch"),
                message.get("role"),
            )
            for message in writer_a.messages
            if message.get("type")
            in {"pi_session_replay", "pi_session_ownership"}
            and message.get("sessionId") == self.a["sessionId"]
        ]
        epochs = [state[1] for state in states]
        self.assertTrue(states)
        self.assertEqual(epochs, sorted(epochs))
        self.assertEqual(states[-1][1], route["epoch"])
        self.assertEqual(states[-1][2], "viewer")
        self.assertIs(route["writer"], viewer_b)

,
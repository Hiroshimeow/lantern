from __future__ import annotations

import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from lantern_terminal import TerminalManager, WinConPty, encode_terminal_key
from lantern_scm import ScmService, build_git_command
from lantern_ws import WebSocketPeer, dispatch


class FakePty:
    def __init__(self, on_data, on_exit):
        self.on_data = on_data
        self.on_exit = on_exit
        self.writes = []
        self.resizes = []
        self.closed = False

    def write(self, data: str) -> None:
        self.writes.append(data)

    def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    def close(self, graceful: bool = True) -> None:
        self.closed = True

    def emit(self, data: str) -> None:
        self.on_data(data)

    def exit(self, code: int = 0) -> None:
        self.on_exit(code)


class TerminalParityTests(unittest.TestCase):
    def test_reference_key_encoding(self) -> None:
        self.assertEqual(encode_terminal_key("ArrowUp", {"ctrl": True}), "\x1b[1;5A")
        self.assertEqual(encode_terminal_key("Enter", {"ctrl": True}), "\x1b[13;5u")
        self.assertEqual(encode_terminal_key("ArrowRight", {"ctrl": True}), "\x1b[1;5C")
        self.assertEqual(encode_terminal_key("ArrowUp"), "\x1b[A")
        self.assertEqual(encode_terminal_key("ArrowUp", {"alt": True}), "\x1b[1;3A")
        self.assertEqual(encode_terminal_key("ArrowUp", {"ctrl": True, "shift": True}), "\x1b[1;6A")
        self.assertEqual(encode_terminal_key("Tab", {"shift": True}), "\x1b[Z")
        self.assertEqual(encode_terminal_key("Backspace", {"alt": True}), "\x1b\x7f")
        self.assertEqual(encode_terminal_key("Backspace", {"ctrl": True}), "\x08")
        self.assertEqual(encode_terminal_key("Delete", {"ctrl": True}), "\x1b[3;5~")
        self.assertEqual(encode_terminal_key("PageUp", {"shift": True}), "\x1b[5;2~")
        self.assertEqual(encode_terminal_key("Enter"), "\r")
        self.assertEqual(encode_terminal_key("c", {"ctrl": True}), "\x03")
        self.assertEqual(encode_terminal_key("c", {"alt": True}), "\x1bc")
        with self.assertRaises(ValueError):
            encode_terminal_key("F20")

    def test_conpty_startup_da1_filter_handles_split_query(self) -> None:
        class Proc:
            def __init__(self) -> None:
                self.writes = []

            def write(self, data: str) -> None:
                self.writes.append(data)

        pty = WinConPty.__new__(WinConPty)
        pty._proc = Proc()
        pty._filter_da1 = True
        pty._da1_carry = ""
        pty._da1_deadline = time.monotonic() + 1.0
        self.assertEqual(pty._filter_startup_da1("\x1b[1tprefix\x1b["), "\x1b[1tprefix")
        self.assertEqual(pty._proc.writes, [], "DA1 response must not be sent before the query is observed")
        self.assertEqual(pty._filter_startup_da1("c\x1b[?1004h"), "\x1b[?1004h")
        self.assertEqual(pty._proc.writes, ["\x1b[?1;2c"])
        self.assertFalse(pty._filter_da1)
        self.assertEqual(pty._filter_startup_da1("\x1b[c-live"), "\x1b[c-live")

    def test_live_limit_history_replay_and_output_before_exit(self) -> None:
        events = []
        spawned = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned[term_id] = p
            return p

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(
                Path(td),
                events.append,
                pty_factory=factory,
                max_live=2,
                max_history=2,
                max_output=32,
                flush_ms=0.01,
            )
            manager.create("one", td, 80, 24, "One")
            manager.create("two", td, 80, 24, "Two")
            with self.assertRaises(RuntimeError):
                manager.create("three", td, 80, 24, "Three")
            self.assertFalse(spawned["one"].closed, "limit must never evict oldest live PTY")

            spawned["one"].emit("abcdef")
            spawned["one"].exit(7)
            time.sleep(0.04)
            kinds = [e["type"] for e in events if e.get("terminalId") == "one"]
            self.assertLess(kinds.index("terminal_output"), kinds.index("terminal_exit"))
            info = {t["id"]: t for t in manager.list()}
            self.assertFalse(info["one"]["running"])
            self.assertTrue(info["two"]["running"])

            replay = dict(manager.replay())
            self.assertEqual(replay["one"], "abcdef")
            manager.create("three", td, 80, 24, "Three")
            with self.assertRaises(RuntimeError):
                manager.create("one", td, 80, 24, "One again")

    def test_disabled_manager_rejects_terminal_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), lambda _event: None, pty_factory=lambda *args: None, enabled=False)
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                manager.create("disabled", td)

    def test_synchronous_spawn_output_is_not_lost(self) -> None:
        events = []

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            on_data("EARLY-BANNER")
            return FakePty(on_data, on_exit)

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), events.append, pty_factory=factory, flush_ms=0.005)
            manager.create("early", td)
            time.sleep(0.02)
            self.assertEqual(dict(manager.replay())["early"], "EARLY-BANNER")
            self.assertTrue(any(e.get("type") == "terminal_output" and e.get("data") == "EARLY-BANNER" for e in events))

    def test_bounded_replay_keeps_tail_only(self) -> None:
        events = []
        spawned = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned[term_id] = p
            return p

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), events.append, pty_factory=factory, max_output=16, flush_ms=0.005)
            manager.create("tail", td)
            spawned["tail"].emit("0123456789abcdefghijkl")
            time.sleep(0.02)
            self.assertEqual(dict(manager.replay())["tail"], "6789abcdefghijkl")

    def test_resize_rename_input_and_restart_exited_id(self) -> None:
        events = []
        spawned = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned.setdefault(term_id, []).append(p)
            return p

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), events.append, pty_factory=factory, flush_ms=0.005)
            manager.create("t", td, 80, 24, "Terminal")
            manager.input("t", "echo hi\r")
            manager.key("t", "ArrowUp", {"ctrl": True})
            manager.resize("t", 120, 40)
            manager.resize("t", 120, 40)
            manager.rename("t", "Renamed")
            first = spawned["t"][0]
            self.assertEqual(first.writes, ["echo hi\r", "\x1b[1;5A"])
            self.assertEqual(first.resizes, [(120, 40)], "identical resize requests must be ignored")
            self.assertEqual(next(x for x in manager.list() if x["id"] == "t")["title"], "Renamed")
            first.exit(0)
            time.sleep(0.02)
            manager.create("t", td, 80, 24, "Restarted")
            self.assertEqual(len(spawned["t"]), 2)
            self.assertTrue(next(x for x in manager.list() if x["id"] == "t")["running"])


class ScmParityTests(unittest.TestCase):
    def git(self, cwd: Path, *args: str) -> str:
        import subprocess
        return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()

    def make_repo(self, root: Path) -> Path:
        import subprocess
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        (repo / "a.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo

    def test_status_history_diff_and_non_repo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self.make_repo(root)
            (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            svc = ScmService(root, lambda _msg: None)
            st = svc.status(repo)
            self.assertEqual(st["branch"], "main")
            self.assertEqual({f["path"] for f in st["files"]}, {"a.txt", "new.txt"})
            self.assertIn("a.txt", st["stats"])
            self.assertTrue(any(b["name"] == "main" and b["current"] for b in st["branches"]))
            subprocess.run(["git", "update-ref", "refs/remotes/origin/feature", "HEAD"], cwd=repo, check=True)
            st_remote = svc.status(repo)
            self.assertTrue(any(b["name"] == "origin/feature" and b.get("remote") == "origin" for b in st_remote["branches"]))
            diff = svc.file_diff(repo, "a.txt")
            self.assertIn("+two", diff["worktree"])
            hist = svc.history(repo)
            self.assertEqual(hist[0]["subject"], "init")
            self.assertTrue(svc.status(root)["notRepo"])

    def test_diff_path_cannot_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = self.make_repo(root)
            svc = ScmService(root, lambda _msg: None)
            with self.assertRaises(ValueError):
                svc.file_diff(repo, "../outside.txt")
            with self.assertRaises(ValueError):
                svc.file_diff(repo, str(root / "outside.txt"))

    def test_watcher_debounce_emits_one_change(self) -> None:
        events = []
        with tempfile.TemporaryDirectory() as td:
            svc = ScmService(Path(td), events.append)
            svc._schedule_changed()
            svc._schedule_changed()
            svc._schedule_changed()
            deadline = time.time() + 2.0
            while time.time() < deadline and not events:
                time.sleep(0.02)
            self.assertEqual([e for e in events if e.get("type") == "scm_changed"], [{"type": "scm_changed"}])
            svc.close()

    def test_git_write_command_generation_matches_reference(self) -> None:
        self.assertEqual(build_git_command("stage", path="a b.txt"), "git add -- 'a b.txt'")
        self.assertEqual(build_git_command("unstage", path="a b.txt"), "git reset HEAD -- 'a b.txt'")
        self.assertEqual(build_git_command("push"), "git push")
        self.assertEqual(build_git_command("pull"), "git pull")
        self.assertEqual(build_git_command("checkout", branch="feature"), "git checkout 'feature'")
        self.assertEqual(
            build_git_command("checkout_remote", branch="origin/feature", remote="origin"),
            "git checkout -b 'feature' 'origin/feature' || git checkout 'origin/feature'",
        )
        self.assertEqual(build_git_command("commit", message="it's done"), "git commit -m 'it'\"'\"'s done'")


class WsProtocolTests(unittest.TestCase):
    def test_slow_peer_overflow_stops_writer_thread(self) -> None:
        class Handler:
            pass

        server, client = socket.socketpair()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        handler = Handler()
        handler.connection = server
        handler.rfile = server.makefile("rb", buffering=0)
        handler.wfile = server.makefile("wb", buffering=0)
        peer = WebSocketPeer(handler)
        try:
            payload = "x" * 65536
            with self.assertRaises(ConnectionError):
                for _ in range(300):
                    peer.send({"type": "terminal_output", "terminalId": "t", "data": payload})
            deadline = time.time() + 3.0
            while peer._writer.is_alive() and time.time() < deadline:
                time.sleep(0.02)
            self.assertFalse(peer._writer.is_alive(), "overflowed slow peer writer must terminate")
        finally:
            try:
                peer.close()
            except Exception:
                pass
            for stream in (handler.rfile, handler.wfile):
                try:
                    stream.close()
                except Exception:
                    pass
            server.close()
            client.close()

    class Peer:
        def __init__(self):
            self.messages = []

        def send(self, message):
            self.messages.append(message)

    class Scm:
        def __init__(self, fail=False):
            self.fail = fail
            self.calls = []

        def query(self, kind, cwd, payload):
            self.calls.append((kind, cwd, payload.get("reqId")))
            if self.fail:
                raise RuntimeError("boom")
            return {"branch": "main"}

    def test_scm_reqid_gets_exactly_one_correlated_response(self) -> None:
        for fail in (False, True):
            peer = self.Peer()
            scm = self.Scm(fail=fail)
            dispatch(peer, {"type": "scm_status", "reqId": "req-7", "cwd": ""}, object(), scm)
            self.assertEqual(len(peer.messages), 1)
            message = peer.messages[0]
            self.assertEqual(message["type"], "scm_data")
            self.assertEqual(message["reqId"], "req-7")
            self.assertEqual(message["kind"], "status")
            self.assertEqual(message["ok"], not fail)
            self.assertEqual(scm.calls, [("status", "", "req-7")])


if __name__ == "__main__":
    unittest.main()

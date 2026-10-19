from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from lantern.terminal import TerminalManager, WinConPty, encode_terminal_key, resolve_shell
from lantern.scm import ScmService, build_git_command
from lantern.ws import WebSocketHub, WebSocketPeer, dispatch, _terminal_error_reply


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
    @unittest.skipUnless(os.name == "nt", "Windows native shell preference")
    def test_windows_defaults_native_shell_even_with_git_bash_or_shell_env(self) -> None:
        with patch.dict(os.environ, {
            "SHELL": r"C:\Program Files\Git\bin\bash.exe",
            "LANTERN_SHELL": "",
            "PI_WEB_SHELL": "",
            "COMSPEC": r"C:\Windows\System32\cmd.exe",
        }):
            with patch("lantern.terminal.shutil.which", side_effect=lambda name:
                       r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
                       if name == "powershell" else None):
                shell, args, family = resolve_shell()
                self.assertEqual(family, "powershell")
                self.assertIn("-NoProfile", args)
                self.assertTrue(shell.lower().endswith("powershell.exe"))

            with patch("lantern.terminal.shutil.which", return_value=None):
                shell, args, family = resolve_shell()
                self.assertEqual(family, "cmd")
                self.assertTrue(shell.lower().endswith("cmd.exe"))
                self.assertEqual(args, [])

            os.environ["LANTERN_SHELL"] = r"C:\Program Files\Git\bin\bash.exe"
            shell, args, family = resolve_shell()
            self.assertEqual((family, args), ("bash", ["-i"]))
            self.assertTrue(shell.lower().endswith("bash.exe"))

            os.environ["LANTERN_SHELL"] = "pwsh.exe"
            shell, args, family = resolve_shell()
            self.assertEqual((shell, family), ("pwsh.exe", "powershell"))
            self.assertIn("-NoProfile", args)

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
            first = manager.create("one", td, 80, 24, "One")
            manager.create("two", td, 80, 24, "Two")
            with self.assertRaises(RuntimeError):
                manager.create("three", td, 80, 24, "Three")
            self.assertFalse(spawned["one"].closed, "limit must never evict oldest live PTY")

            spawned["one"].emit("abcdef")
            spawned["one"].exit(7)
            time.sleep(0.04)
            one_events = [e for e in events if e.get("terminalId") == "one"]
            kinds = [e["type"] for e in one_events]
            self.assertLess(kinds.index("terminal_output"), kinds.index("terminal_exit"))
            exit_event = next(e for e in one_events if e["type"] == "terminal_exit")
            self.assertEqual(exit_event["generation"], first["generation"])
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
            _meta, output, seq, start, end = manager.replay_view("tail")
            self.assertEqual((output, seq, start, end), ("6789abcdefghijkl", 1, 6, 22))


    def test_replay_view_tracks_utf8_retention_and_generation_reset(self) -> None:
        events = []
        spawned = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned[term_id] = p
            return p

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(
                Path(td), events.append, pty_factory=factory, max_output=5, flush_ms=0
            )
            first = manager.create("utf8", td)
            spawned["utf8"].emit("A\u65e5\U0001F642BCDEF")
            meta, output, seq, start, end = manager.replay_view("utf8")
            self.assertEqual(meta["generation"], first["generation"])
            self.assertEqual((output, seq), ("BCDEF", 1))
            self.assertEqual(start, len("A\u65e5\U0001F642".encode("utf-8")))
            self.assertEqual(end, len("A\u65e5\U0001F642BCDEF".encode("utf-8")))
            self.assertEqual(manager.replay_one("utf8"), (meta, output, seq))

            manager.kill("utf8")
            second = manager.create("utf8", td)
            self.assertNotEqual(second["generation"], first["generation"])
            _meta, output, seq, start, end = manager.replay_view("utf8")
            self.assertEqual((output, seq, start, end), ("", 0, 0, 0))

    def test_websocket_replay_offsets_cover_actual_sent_suffix(self) -> None:
        class Peer:
            def __init__(self):
                self.subscriptions = set()
                self.messages = []
                self.protocol = "v2"

            def send(self, message):
                self.messages.append(message)

        spawned = {}
        hub = WebSocketHub()

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned[term_id] = p
            return p

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(
                Path(td), hub.broadcast, pty_factory=factory, max_output=100, flush_ms=0
            )
            manager.create("cap", td)
            spawned["cap"].emit("A\u65e5\U0001F642BC")

            uncapped = Peer()
            hub.add(uncapped)
            with patch("lantern.ws._MAX_ACTIVE_REPLAY_CHARS", 100):
                dispatch(
                    uncapped,
                    {"type": "terminal_subscribe", "terminalId": "cap"},
                    manager,
                    None,
                    hub,
                )
            replay = next(m for m in uncapped.messages if m["type"] == "terminal_replay")
            self.assertEqual(replay["output"], "A\u65e5\U0001F642BC")
            self.assertFalse(replay["truncated"])
            self.assertEqual(replay["replayStartUtf8"], 0)
            self.assertEqual(replay["replayEndUtf8"], len("A\u65e5\U0001F642BC".encode("utf-8")))

            hub.unsubscribe(uncapped, "cap")
            capped = Peer()
            hub.add(capped)
            with patch("lantern.ws._MAX_ACTIVE_REPLAY_CHARS", 4):
                dispatch(
                    capped,
                    {"type": "terminal_subscribe", "terminalId": "cap"},
                    manager,
                    None,
                    hub,
                )
            replay = next(m for m in capped.messages if m["type"] == "terminal_replay")
            self.assertEqual(replay["output"], "\u65e5\U0001F642BC")
            self.assertTrue(replay["truncated"])
            self.assertEqual(replay["replayStartUtf8"], len("A".encode("utf-8")))
            self.assertEqual(replay["replayEndUtf8"], len("A\u65e5\U0001F642BC".encode("utf-8")))


    def test_structured_spawn_preserves_exact_argv_cwd_and_env_without_shell(self) -> None:
        spawned = []

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, *, argv=None, env=None):
            spawned.append({
                "cwd": str(cwd),
                "command": command,
                "argv": list(argv) if argv is not None else None,
                "env": dict(env) if env is not None else None,
            })
            return FakePty(on_data, on_exit)

        argv = [
            r"C:\Program Files\nodejs\node.exe",
            "cli with spaces.js",
            "日本語",
            'quote"inside',
            "a&b",
            "semi;colon",
            "single'quote",
        ]
        overlay = {"LANTERN_PI_TEST": "値🙂", "TERM": "pi-term"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cwd = root / "child"
            cwd.mkdir()
            before = os.environ.copy()
            manager = TerminalManager(root, lambda _event: None, pty_factory=factory)
            info = manager.create_argv(
                "structured",
                cwd,
                argv,
                90,
                30,
                "Structured",
                env=overlay,
            )
            self.assertTrue(info["running"])
            self.assertEqual(len(spawned), 1)
            self.assertEqual(spawned[0]["argv"], argv)
            self.assertIsNone(spawned[0]["command"])
            self.assertEqual(Path(spawned[0]["cwd"]), cwd.resolve())
            self.assertEqual(spawned[0]["env"], overlay)
            self.assertEqual(os.environ, before)
            self.assertNotIn("argv", info)
            self.assertNotIn("env", info)

    def test_structured_spawn_rejects_empty_argv_command_mix_and_outside_cwd(self) -> None:
        calls = []

        def factory(*args, **kwargs):
            calls.append((args, kwargs))
            return FakePty(args[4], args[5])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manager = TerminalManager(root, lambda _event: None, pty_factory=factory)
            with self.assertRaisesRegex(ValueError, "argv"):
                manager.create_argv("empty", root, [])
            with self.assertRaisesRegex(TypeError, "argv"):
                manager.create_argv("string-is-not-argv", root, "node")
            with self.assertRaisesRegex(ValueError, "both"):
                manager.create(
                    "both",
                    root,
                    command="echo no",
                    argv=["node", "cli.js"],
                )
            with self.assertRaisesRegex(ValueError, "inside"):
                manager.create_argv("outside", root.parent, ["node"])
            self.assertEqual(calls, [])

    def test_structured_spawn_env_overlay_inherits_defaults_without_parent_mutation(self) -> None:
        from lantern.terminal import _build_pty_env

        with patch.dict(os.environ, {}, clear=True):
            defaults = _build_pty_env()
            self.assertEqual(defaults["TERM"], "xterm-256color")
            self.assertEqual(defaults["LANG"], "en_US.UTF-8")

        with patch.dict(os.environ, {"LANTERN_PARENT_SENTINEL": "present"}, clear=False):
            before = os.environ.copy()
            child = _build_pty_env({"TERM": "custom-term", "PI_UNICODE": "Việt🙂"})
            self.assertEqual(child["LANTERN_PARENT_SENTINEL"], "present")
            self.assertEqual(child["TERM"], "custom-term")
            self.assertEqual(child["LANG"], os.environ.get("LANG", "en_US.UTF-8"))
            self.assertEqual(child["PI_UNICODE"], "Việt🙂")
            self.assertEqual(os.environ, before)
            child["LANTERN_PARENT_SENTINEL"] = "changed"
            self.assertEqual(os.environ["LANTERN_PARENT_SENTINEL"], "present")

        with self.assertRaisesRegex(TypeError, "strings"):
            _build_pty_env({"BAD": 1})


    def test_structured_spawn_dispatches_same_argv_env_contract_to_native_backend(self) -> None:
        captured = []

        def backend(argv, cwd, cols, rows, on_data, on_exit, env_overlay=None):
            captured.append((list(argv), cwd, cols, rows, dict(env_overlay or {})))
            return FakePty(on_data, on_exit)

        argv = ["node", "cli.js", "a&b", "日本語"]
        overlay = {"TERM": "custom", "PI_FLAG": "値"}
        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), lambda _event: None)
            for platform, target in (("nt", "WinConPty"), ("posix", "PosixPty")):
                captured.clear()
                with patch("lantern.terminal.os.name", platform), patch(
                    f"lantern.terminal.{target}", side_effect=backend
                ):
                    manager._spawn_native(
                        "x",
                        Path(td),
                        80,
                        24,
                        lambda _data: None,
                        lambda _code: None,
                        argv=argv,
                        env=overlay,
                    )
                self.assertEqual(
                    captured,
                    [(argv, str(Path(td)), 80, 24, overlay)],
                    f"{target} must receive the same structured argv/env contract",
                )

    def test_ordinary_create_keeps_legacy_factory_signature(self) -> None:
        calls = []

        def legacy_factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            calls.append((term_id, str(cwd), cols, rows, command))
            return FakePty(on_data, on_exit)

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(Path(td), lambda _event: None, pty_factory=legacy_factory)
            manager.create("shell", td, 80, 24, "Shell")
            manager.run_command("cmd", td, "echo hi", "Command")
            self.assertEqual(calls[0][-1], None)
            self.assertEqual(calls[1][-1], "echo hi")


    def test_kill_if_generation_never_kills_replacement_generation(self) -> None:
        spawned = {}

        def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None):
            p = FakePty(on_data, on_exit)
            spawned.setdefault(term_id, []).append(p)
            return p

        with tempfile.TemporaryDirectory() as td:
            events = []
            manager = TerminalManager(Path(td), events.append, pty_factory=factory)
            first = manager.create("same-id", td)
            manager.kill("same-id")
            second = manager.create("same-id", td)
            self.assertNotEqual(first["generation"], second["generation"])

            self.assertFalse(
                manager.kill_if_generation("same-id", first["generation"]),
                "stale registry generation must not kill a replacement PTY",
            )
            live = {item["id"]: item for item in manager.list()}
            self.assertTrue(live["same-id"]["running"])
            self.assertEqual(live["same-id"]["generation"], second["generation"])
            self.assertFalse(spawned["same-id"][1].closed)

            self.assertTrue(manager.kill_if_generation("same-id", second["generation"]))
            self.assertTrue(spawned["same-id"][1].closed)
            exit_events = [
                event
                for event in events
                if event.get("type") == "terminal_exit"
                and event.get("terminalId") == "same-id"
            ]
            self.assertEqual(
                [event.get("generation") for event in exit_events],
                [first["generation"], second["generation"]],
            )

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


    def test_websocket_terminal_create_ack_and_correlated_failure(self) -> None:
        class Peer:
            def __init__(self):
                self.messages = []

            def send(self, message):
                self.messages.append(message)

        with tempfile.TemporaryDirectory() as td:
            manager = TerminalManager(
                Path(td), lambda _event: None,
                pty_factory=lambda _id, _cwd, _cols, _rows, on_data, on_exit, _command=None: FakePty(on_data, on_exit),
            )
            peer = Peer()
            dispatch(peer, {"type": "terminal_create", "terminalId": "alpha",
                            "cwd": td, "cols": 80, "rows": 24}, manager, None)
            self.assertEqual(len(peer.messages), 1)
            self.assertEqual(peer.messages[0]["type"], "terminal_created")
            self.assertEqual(peer.messages[0]["terminalId"], "alpha")
            self.assertTrue(peer.messages[0]["meta"]["generation"])

            with self.assertRaises(ValueError) as failure:
                dispatch(peer, {"type": "terminal_create", "terminalId": "invalid",
                                "cwd": str(Path(td).parent)}, manager, None)
            error = _terminal_error_reply({"type": "terminal_create", "terminalId": "invalid"},
                                          failure.exception)
            self.assertEqual(error["code"], "terminal_start_failed")
            self.assertEqual(error["terminalId"], "invalid")
            self.assertEqual([x["id"] for x in manager.list()], ["alpha"])

            manager.kill("alpha")
            with self.assertRaises(KeyError) as stopped:
                dispatch(peer, {"type": "terminal_input", "terminalId": "alpha", "data": "x"}, manager, None)
            unavailable = _terminal_error_reply({"type": "terminal_input", "terminalId": "alpha"},
                                                stopped.exception)
            self.assertEqual(unavailable["code"], "terminal_not_running")
            self.assertEqual(unavailable["terminalId"], "alpha")


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
            nested = repo / ".plan" / "review"
            nested.mkdir(parents=True)
            (nested / "report.md").write_text("# Review\n\nall green\n", encoding="utf-8")
            svc = ScmService(root, lambda _msg: None)
            st = svc.status(repo)
            self.assertEqual(st["branch"], "main")
            self.assertEqual(
                {f["path"] for f in st["files"]},
                {"a.txt", "new.txt", ".plan/review/report.md"},
                "untracked directories must expand to individual files",
            )
            self.assertIn("a.txt", st["stats"])
            self.assertTrue(any(b["name"] == "main" and b["current"] for b in st["branches"]))
            subprocess.run(["git", "update-ref", "refs/remotes/origin/feature", "HEAD"], cwd=repo, check=True)
            st_remote = svc.status(repo)
            self.assertTrue(any(b["name"] == "origin/feature" and b.get("remote") == "origin" for b in st_remote["branches"]))
            diff = svc.file_diff(repo, "a.txt")
            self.assertIn("+two", diff["worktree"])
            new_diff = svc.file_diff(repo, ".plan/review/report.md")
            self.assertIn("new file mode", new_diff["worktree"])
            self.assertIn("+++ b/.plan/review/report.md", new_diff["worktree"])
            self.assertIn("+# Review", new_diff["worktree"])
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

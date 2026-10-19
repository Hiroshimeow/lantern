from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from lantern.pi_sessions import PiSessionRegistry
from lantern.terminal import TerminalManager


class FakeTerminalManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.created: list[dict] = []
        self.terminals: dict[str, dict] = {}
        self.killed: list[str] = []
        self.conditional_kills: list[tuple[str, str]] = []
        self.fail_next = False

    def create_argv(self, term_id, cwd, argv, cols=80, rows=24, title="Terminal", *, env=None, control_owner=None):
        cwd = Path(cwd).resolve()
        if self.root not in (cwd, *cwd.parents):
            raise ValueError("Terminal cwd must be inside the configured root")
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("spawn failed")
        generation = f"gen-{len(self.created) + 1}"
        record = {
            "id": term_id,
            "cwd": str(cwd),
            "argv": list(argv),
            "cols": cols,
            "rows": rows,
            "title": title,
            "env": dict(env or {}),
            "control_owner": control_owner,
            "generation": generation,
            "running": True,
            "exitCode": None,
        }
        self.created.append(record)
        self.terminals[term_id] = record.copy()
        return {
            "id": term_id,
            "cwd": str(cwd),
            "cols": cols,
            "rows": rows,
            "title": title,
            "generation": generation,
            "running": True,
            "exitCode": None,
            "command": None,
        }

    def list(self):
        return [item.copy() for item in self.terminals.values()]

    def kill(self, term_id, *, emit_exit=True):
        self.killed.append(term_id)
        item = self.terminals.get(term_id)
        if item:
            item["running"] = False

    def kill_if_generation(self, term_id, expected_generation, *, emit_exit=True):
        item = self.terminals.get(term_id)
        if not item or item.get("generation") != expected_generation or not item.get("running"):
            return False
        self.conditional_kills.append((term_id, expected_generation))
        item["running"] = False
        return True


class PiSessionRegistryTests(unittest.TestCase):
    def _registry(self, root: Path, state: Path, terminal: FakeTerminalManager, ids):
        iterator = iter(ids)
        return PiSessionRegistry(
            root,
            state,
            terminal,
            ["node", "pi-cli.js", "--approve"],
            env={"PI_ENV": "server-owned"},
            id_factory=lambda: next(iterator),
        )

    def test_create_uses_opaque_identity_exact_native_argv_and_defensive_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            doc = root / "docs" / "recognizable-file.md"
            doc.parent.mkdir()
            doc.write_text("# x", encoding="utf-8")
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["opaqueA123"])

            context = {"path": "docs/recognizable-file.md", "selection": {"line": 7}}
            session = registry.create(
                cwd=doc.parent,
                context_ref=context,
                cols=101,
                rows=33,
                title="Human title",
            )

            self.assertEqual(session["sessionId"], "opaqueA123")
            self.assertEqual(session["terminalId"], "pi:opaqueA123")
            self.assertNotEqual(session["sessionId"], context["path"])
            self.assertNotIn("recognizable", session["terminalId"])
            self.assertEqual(Path(session["sessionDir"]).name, "opaqueA123")
            self.assertEqual(session["generation"], "gen-1")
            self.assertEqual((session["cols"], session["rows"]), (101, 33))
            self.assertTrue(session["running"])
            self.assertNotIn("argv", session)
            self.assertNotIn("env", session)
            self.assertNotIn("controlOwner", session)

            created = terminal.created[0]
            self.assertEqual(
                created["argv"],
                [
                    "node",
                    "pi-cli.js",
                    "--approve",
                    "--session-id",
                    "opaqueA123",
                    "--session-dir",
                    str(state.resolve() / "opaqueA123"),
                    "--tui-mode",
                    "regular",
                ],
            )
            self.assertEqual(created["env"], {"PI_ENV": "server-owned"})
            self.assertEqual(created["control_owner"], "pi")
            self.assertNotIn("--offline", created["argv"])
            self.assertNotIn("--model", created["argv"])
            self.assertNotIn("-Command", created["argv"])

            context["selection"]["line"] = 99
            session["contextRef"]["selection"]["line"] = 88
            self.assertEqual(registry.get("opaqueA123")["contextRef"]["selection"]["line"], 7)

    def test_two_same_document_sessions_are_independent_and_stop_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["sameA", "sameB"])
            context = {"path": "same.md", "selection": {"line": 1}}

            a = registry.create(cwd=root, context_ref=context)
            b = registry.create(cwd=root, context_ref=context)

            self.assertNotEqual(a["sessionId"], b["sessionId"])
            self.assertNotEqual(a["terminalId"], b["terminalId"])
            self.assertNotEqual(a["generation"], b["generation"])
            self.assertNotEqual(a["sessionDir"], b["sessionDir"])
            self.assertEqual(a["contextRef"], b["contextRef"])
            self.assertIsNot(a["contextRef"], b["contextRef"])

            registry.stop(a["sessionId"])
            registry.stop(a["sessionId"])
            self.assertFalse(registry.get(a["sessionId"])["running"])
            self.assertTrue(registry.get(b["sessionId"])["running"])
            self.assertEqual(terminal.conditional_kills, [(a["terminalId"], a["generation"])])
            self.assertEqual(terminal.killed, [])

    def test_different_documents_remain_bound_to_creation_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["docA", "docB"])

            a = registry.create(cwd=root, context_ref={"path": "a.md"})
            b = registry.create(cwd=root, context_ref={"path": "b.md"})
            listed = {item["sessionId"]: item for item in registry.list()}

            self.assertEqual(listed[a["sessionId"]]["contextRef"], {"path": "a.md"})
            self.assertEqual(listed[b["sessionId"]]["contextRef"], {"path": "b.md"})
            listed[b["sessionId"]]["contextRef"]["path"] = "mutated.md"
            self.assertEqual(registry.get(a["sessionId"])["contextRef"], {"path": "a.md"})
            self.assertEqual(registry.get(b["sessionId"])["contextRef"], {"path": "b.md"})


    def test_context_snapshot_failure_happens_before_session_dir_or_spawn(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["ctxFail"])

            context = MappingProxyType({"path": "file.md"})
            with self.assertRaises(TypeError):
                registry.create(cwd=root, context_ref=context)

            self.assertEqual(registry.list(), [])
            self.assertEqual(terminal.created, [])
            self.assertEqual(terminal.terminals, {})
            self.assertFalse((state / "ctxFail").exists())

    def test_create_failure_is_atomic_and_collision_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["bad", "dup", "dup"])

            terminal.fail_next = True
            with self.assertRaisesRegex(RuntimeError, "spawn failed"):
                registry.create(cwd=root, context_ref={"path": "bad.md"})
            self.assertEqual(registry.list(), [])
            self.assertFalse((state / "bad").exists())

            registry.create(cwd=root, context_ref={"path": "one.md"})
            with self.assertRaisesRegex(ValueError, "collision"):
                registry.create(cwd=root, context_ref={"path": "two.md"})
            self.assertEqual(len(registry.list()), 1)
            self.assertEqual(len(terminal.created), 1)

    def test_cwd_failure_leaves_no_session_and_close_kills_only_owned_terminals(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "project"
            state = base / "state"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            terminal = FakeTerminalManager(root)
            terminal.terminals["ordinary"] = {
                "id": "ordinary",
                "running": True,
                "generation": "ordinary-gen",
                "cwd": str(root),
                "cols": 80,
                "rows": 24,
                "exitCode": None,
            }
            registry = self._registry(root, state, terminal, ["outside", "ownedA", "ownedB"])

            with self.assertRaisesRegex(ValueError, "inside"):
                registry.create(cwd=outside, context_ref={"path": "x"})
            self.assertEqual(registry.list(), [])
            self.assertFalse((state / "outside").exists())

            a = registry.create(cwd=root, context_ref={"path": "a"})
            b = registry.create(cwd=root, context_ref={"path": "b"})
            registry.close()
            self.assertCountEqual(
                terminal.conditional_kills,
                [(a["terminalId"], a["generation"]), (b["terminalId"], b["generation"])],
            )
            self.assertEqual(terminal.killed, [])
            self.assertNotIn("ordinary", [item[0] for item in terminal.conditional_kills])


    def test_stop_and_close_do_not_kill_replacement_generations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["raceStop", "raceClose"])

            stop_session = registry.create(cwd=root, context_ref={"path": "stop.md"})
            close_session = registry.create(cwd=root, context_ref={"path": "close.md"})

            self.assertTrue(registry.get(stop_session["sessionId"])["running"])
            self.assertTrue(registry.get(close_session["sessionId"])["running"])

            stop_replacement = terminal.terminals[stop_session["terminalId"]].copy()
            stop_replacement["generation"] = "replacement-stop"
            terminal.terminals[stop_session["terminalId"]] = stop_replacement

            close_replacement = terminal.terminals[close_session["terminalId"]].copy()
            close_replacement["generation"] = "replacement-close"
            terminal.terminals[close_session["terminalId"]] = close_replacement

            registry.stop(stop_session["sessionId"])
            registry.close()

            self.assertTrue(terminal.terminals[stop_session["terminalId"]]["running"])
            self.assertTrue(terminal.terminals[close_session["terminalId"]]["running"])
            self.assertEqual(terminal.conditional_kills, [])
            self.assertEqual(terminal.killed, [])


    def test_real_terminal_create_emit_failure_rolls_back_published_generation(self):
        class Pty:
            def __init__(self, on_data, on_exit):
                self.on_data = on_data
                self.on_exit = on_exit
                self.closed = False

            def write(self, _data):
                pass

            def resize(self, _cols, _rows):
                pass

            def close(self, graceful=True):
                self.closed = True

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            spawned = {}
            fail_lists = {"enabled": False}

            def factory(term_id, cwd, cols, rows, on_data, on_exit, command=None, **_kwargs):
                pty = Pty(on_data, on_exit)
                spawned.setdefault(term_id, []).append(pty)
                return pty

            def emit(event):
                if fail_lists["enabled"] and event.get("type") == "terminal_list":
                    raise RuntimeError("emit failed")

            terminal = TerminalManager(root, emit, pty_factory=factory)
            ordinary = terminal.create("ordinary", root)
            registry = self._registry(root, state, terminal, ["orphan"])

            fail_lists["enabled"] = True
            with self.assertRaisesRegex(RuntimeError, "emit failed"):
                registry.create(cwd=root, context_ref={"path": "orphan.md"})

            self.assertEqual(registry.list(), [])
            self.assertFalse((state / "orphan").exists())
            live = {item["id"]: item for item in terminal.list() if item["running"]}
            self.assertIn("ordinary", live)
            self.assertEqual(live["ordinary"]["generation"], ordinary["generation"])
            self.assertNotIn("pi:orphan", live)
            self.assertNotIn("pi:orphan", terminal.history)
            self.assertTrue(spawned["pi:orphan"][0].closed)

    def test_running_status_follows_terminal_manager_not_registry_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            state = Path(td) / "state"
            root.mkdir()
            terminal = FakeTerminalManager(root)
            registry = self._registry(root, state, terminal, ["exitA"])

            created = registry.create(cwd=root, context_ref={"path": "a"})
            terminal.terminals[created["terminalId"]]["running"] = False
            terminal.terminals[created["terminalId"]]["exitCode"] = 17

            view = registry.get(created["sessionId"])
            self.assertFalse(view["running"])
            self.assertEqual(view["exitCode"], 17)


if __name__ == "__main__":
    unittest.main()

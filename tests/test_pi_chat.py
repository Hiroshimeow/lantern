from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from lantern.pi_chat import LanternBotManager
from lantern.bot_config import LanternBotConfig
from lantern.working_copy import WorkingCopyStore


class LanternBotManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()
        self.events = []
        self.settled = threading.Event()
        self.work = WorkingCopyStore(
            self.root,
            Path(self.tmp.name) / "work",
            {".md", ".markdown"},
        )
        fake = Path(__file__).with_name("fake_pi_rpc.py")

        def emit(event):
            self.events.append(event)
            if (event.get("type") == "chat_bot_event"
                    and event.get("event", {}).get("type") == "agent_settled"):
                self.settled.set()

        self.manager = LanternBotManager(
            self.root,
            emit,
            work_store=self.work,
            session_dir=Path(self.tmp.name) / "sessions",
            argv_override=[sys.executable, "-u", str(fake)],
            request_timeout=3,
            usage_path=Path(self.tmp.name) / "usage.json",
        )

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def test_state_starts_process_and_persists_session(self):
        state = self.manager.get_state()
        self.assertEqual(state["sessionId"], "fake-session-1")
        self.assertTrue(self.manager.summary()["running"])
        saved = json.loads(
            (Path(self.tmp.name) / "sessions" / "lantern-active.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(saved["sessionId"], "fake-session-1")

    def test_model_inventory_uses_native_inventory_without_hardcoded_limit(self):
        models = self.manager.available_models()
        self.assertEqual(len(models), 6)
        self.assertEqual(
            [item["id"] for item in models],
            [
                "gpt-6.1-sol",
                "gpt-6-astra",
                "claude-opus-5-5-high",
                "claude-sonnet-5-5-high",
                "gemini-3.1-pro-low",
                "extra-model",
            ],
        )

    def test_native_default_is_not_changed_when_yaml_selection_is_empty(self):
        state = self.manager.bootstrap_state()
        self.assertEqual(state["model"]["provider"], "fake")
        self.assertEqual(state["model"]["id"], "gpt-6.1-sol")
        self.assertEqual(self.manager.get_messages(), [])

    def test_policy_without_explicit_selection_moves_off_disallowed_native_model(self):
        fake = Path(__file__).with_name("fake_pi_rpc.py")
        manager = LanternBotManager(
            self.root,
            lambda _event: None,
            work_store=self.work,
            session_dir=Path(self.tmp.name) / "policy-auto-sessions",
            usage_path=Path(self.tmp.name) / "policy-auto-usage.json",
            argv_override=[sys.executable, "-u", str(fake)],
            request_timeout=3,
            bot_config=LanternBotConfig.from_mapping({
                "policy": {"allowed_models": ["fake/claude-*"]},
            }),
        )
        try:
            state = manager.bootstrap_state("lan")
            self.assertTrue(state["model"]["id"].startswith("claude-"))
            self.assertNotEqual(state["model"]["id"], "gpt-6.1-sol")
        finally:
            manager.close()

    def test_yaml_policy_filters_inventory_and_can_lock_model(self):
        fake = Path(__file__).with_name("fake_pi_rpc.py")
        manager = LanternBotManager(
            self.root,
            lambda _event: None,
            work_store=self.work,
            session_dir=Path(self.tmp.name) / "policy-sessions",
            usage_path=Path(self.tmp.name) / "policy-usage.json",
            argv_override=[sys.executable, "-u", str(fake)],
            request_timeout=3,
            bot_config=LanternBotConfig.from_mapping({
                "selection": {
                    "provider": "fake",
                    "model": "claude-opus-5-5-high",
                    "lock_provider": True,
                    "lock_model": True,
                },
                "policy": {
                    "allowed_models": ["fake/claude-*"],
                },
            }),
        )
        try:
            models = manager.available_models()
            self.assertEqual([item["id"] for item in models], ["claude-opus-5-5-high"])
            state = manager.bootstrap_state()
            self.assertEqual(state["model"]["id"], "claude-opus-5-5-high")
            with self.assertRaises(PermissionError):
                manager.set_model("fake", "gpt-6.1-sol")
        finally:
            manager.close()

    def test_model_switch_uses_same_session(self):
        before = self.manager.get_state()["sessionId"]
        self.manager.set_model("fake", "claude-opus-5-5-high")
        after = self.manager.get_state()
        self.assertEqual(after["sessionId"], before)
        self.assertEqual(after["model"]["id"], "claude-opus-5-5-high")

    def test_new_session_changes_pi_session_but_keeps_working_copy(self):
        target = self.root / "draft.md"
        target.write_text("saved\n", encoding="utf-8")
        state = self.work.get("draft.md")
        pending = self.work.write(
            "draft.md",
            "pending\n",
            expect_hash=None,
            base_version=state["saved"]["version"],
        )

        before = self.manager.get_state()
        proc = self.manager.proc
        after = self.manager.new_session()

        self.assertNotEqual(after["sessionId"], before["sessionId"])
        self.assertIs(self.manager.proc, proc)
        self.assertTrue(self.manager.summary()["running"])
        self.assertEqual(self.work.get("draft.md")["work"]["hash"], pending["hash"])

    def test_prompt_wraps_logical_and_working_paths_and_streams_events(self):
        target = self.root / "docs" / "spec.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Spec\n\nold text\n", encoding="utf-8")
        state = self.work.get("docs/spec.md")
        pending = self.work.write(
            "docs/spec.md",
            "# Spec\n\nunsaved working copy\n",
            expect_hash=None,
            base_version=state["saved"]["version"],
        )

        self.manager.prompt(
            "Fix this paragraph",
            {
                "kind": "markdown",
                "path": "docs/spec.md",
                "folder": "docs",
                "markdownMode": "source",
                "line": 243,
                "selectedText": "old text",
            },
            work_hash=pending["hash"],
        )
        self.assertTrue(self.settled.wait(2))

        messages = self.manager.get_messages()
        self.assertGreaterEqual(len(messages), 2)
        prompt = messages[0]["content"]
        working = self.work.working_path("docs/spec.md")
        self.assertIsNotNone(working)
        self.assertIn("<lantern_context>", prompt)
        self.assertIn("path: " + str(target.resolve()), prompt)
        self.assertIn("folder: " + str((self.root / "docs").resolve()), prompt)
        self.assertIn("logicalPath: docs/spec.md", prompt)
        self.assertIn("workingPath: " + str(working), prompt)
        self.assertIn("markdownMode: source", prompt)
        self.assertIn("line: 243", prompt)
        self.assertIn("selectedText:\nold text", prompt)
        self.assertNotIn("draftPath:", prompt)
        self.assertNotIn("savedPath:", prompt)
        self.assertIn("<user_request>\nFix this paragraph", prompt)
        self.assertEqual(target.read_text(encoding="utf-8"), "# Spec\n\nold text\n")
        self.assertEqual(
            self.work.get("docs/spec.md")["work"]["content"],
            "# Spec\n\nunsaved working copy\n",
        )
        # Verify session .jsonl file persisted both user and assistant messages
        jsonl_file = Path(self.tmp.name) / "sessions" / "fake-session-1.jsonl"
        self.assertTrue(jsonl_file.is_file())
        jsonl_lines = [json.loads(line) for line in jsonl_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        roles = [entry.get("message", {}).get("role") for entry in jsonl_lines if entry.get("type") == "message"]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        work_events = [item for item in self.events if item.get("type") == "chat_work_changed"]
        self.assertTrue(work_events)
        self.assertTrue(work_events[-1]["final"])
        pi_events = [item["event"] for item in self.events if item.get("type") == "chat_bot_event"]
        self.assertTrue(any(item.get("type") == "message_update" for item in pi_events))
        self.assertTrue(any(item.get("type") == "agent_settled" for item in pi_events))

    def test_fake_pi_edits_working_copy_without_touching_real_file(self):
        target = self.root / "docs" / "work.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Work\n\nreal saved text\n", encoding="utf-8")
        state = self.work.get("docs/work.md")
        pending = self.work.write(
            "docs/work.md",
            "# Work\n\nunsaved working copy\n",
            expect_hash=None,
            base_version=state["saved"]["version"],
        )

        self.manager.prompt(
            "FAKE_EDIT_WORK",
            {"kind": "markdown", "path": "docs/work.md", "markdownMode": "source"},
            work_hash=pending["hash"],
        )
        self.assertTrue(self.settled.wait(2))

        updates = [item for item in self.events if item.get("type") == "chat_work_changed"]
        self.assertTrue(any(not item["final"] for item in updates))
        self.assertTrue(updates[-1]["final"])
        self.assertEqual(
            self.work.get("docs/work.md")["work"]["content"],
            "# Work\n\nfake Pi working edit\n",
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "# Work\n\nreal saved text\n")

    def test_attachments_are_hidden_context_and_usage_is_recorded(self):
        attachment = self.root / "notes.txt"
        attachment.write_text("context\n", encoding="utf-8")
        self.manager.prompt(
            "Use the selected file",
            {"kind": "folder", "folder": ".", "attachments": ["notes.txt"]},
        )
        self.assertTrue(self.settled.wait(2))
        prompt = self.manager.get_messages()[0]["content"]
        self.assertIn("attachments:\n- " + str(attachment.resolve()), prompt)
        self.assertEqual(self.manager.usage.snapshot()["prompts"], 1)
        self.assertEqual(self.manager.usage.snapshot()["tokens"], 7)

    def test_daily_prompt_limit_is_enforced_before_runtime_turn(self):
        fake = Path(__file__).with_name("fake_pi_rpc.py")
        manager = LanternBotManager(
            self.root,
            lambda _event: None,
            work_store=self.work,
            session_dir=Path(self.tmp.name) / "quota-sessions",
            usage_path=Path(self.tmp.name) / "quota-usage.json",
            argv_override=[sys.executable, "-u", str(fake)],
            request_timeout=3,
            bot_config=LanternBotConfig.from_mapping({
                "policy": {"max_prompts_per_day": 1},
            }),
        )
        try:
            manager.prompt("first", {"kind": "folder"})
            for _ in range(40):
                if manager.usage.snapshot()["prompts"] == 1:
                    break
                threading.Event().wait(0.025)
            with self.assertRaisesRegex(RuntimeError, "prompt limit"):
                manager.prompt("second", {"kind": "folder"})
        finally:
            manager.close()

    def test_empty_message_is_rejected_before_start(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.manager.prompt("  ", {"kind": "folder"})
        self.assertIsNone(self.manager.proc)

    def test_selected_text_is_bounded(self):
        prompt = self.manager.build_prompt("go", {"selectedText": "x" * 9000})
        self.assertLess(prompt.count("x"), 8100)

    def test_context_cannot_escape_lantern_root(self):
        with self.assertRaisesRegex(ValueError, "inside the configured root"):
            self.manager.normalize_context({"kind": "file", "path": "../outside.txt"})

    def test_persisted_session_file_is_used_for_restart(self):
        saved = Path(self.tmp.name) / "sessions2" / "saved.jsonl"
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text('{"type":"session"}\n', encoding="utf-8")
        store = WorkingCopyStore(
            self.root,
            Path(self.tmp.name) / "work2",
            {".md", ".markdown"},
        )
        manager = LanternBotManager(
            self.root,
            lambda _event: None,
            work_store=store,
            session_dir=saved.parent,
        )
        manager._persist_state({
            "sessionId": "session-persisted",
            "sessionFile": str(saved),
            "model": {"provider": "fake", "id": "gpt-6.1-sol"},
        })
        command = manager._command()
        self.assertIn("--session", command)
        self.assertIn("--extension", command)
        # v7 default localhost runs in Full / YOLO mode ("*") without restrictive flags
        self.assertNotIn("--tools", command)
        self.assertNotIn("--no-extensions", command)
        self.assertNotIn("--no-mcp", command)
        self.assertIn("pi_working_copy_guard.ts", " ".join(command))
        self.assertEqual(command[command.index("--session") + 1], str(saved.resolve()))
        state = json.loads(manager.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["sessionFile"], str(saved))
        manager.close()

        # Verify explicit YAML restrictions inject --tools, --no-extensions, --no-mcp
        restricted_mgr = LanternBotManager(
            self.root,
            lambda _event: None,
            work_store=store,
            session_dir=saved.parent,
            bot_config=LanternBotConfig.from_mapping({
                "access": {
                    "localhost": {
                        "enabled": True,
                        "tools": ["read", "grep", "find", "ls"],
                        "extensions": False,
                        "mcp": False,
                    }
                }
            }),
        )
        restricted_cmd = restricted_mgr._command()
        self.assertIn("--tools", restricted_cmd)
        self.assertEqual(restricted_cmd[restricted_cmd.index("--tools") + 1], "read,grep,find,ls")
        self.assertIn("--no-extensions", restricted_cmd)
        self.assertIn("--no-mcp", restricted_cmd)
        restricted_mgr.close()

    def test_corrupted_session_file_is_auto_repaired_and_quarantined(self):
        sdir = Path(self.tmp.name) / "sessions_repair"
        sdir.mkdir(parents=True, exist_ok=True)
        # Create a session file containing valid Pi entries plus a corrupted v7 line missing id/parentId
        corrupt_file = sdir / "2026-10-20T06-29-12-989Z_01a157ff-ee9c-76e5-a1c9-ee6b94ed7772.jsonl"
        corrupt_file.write_text(
            "{\"type\":\"session\",\"version\":3,\"id\":\"01a157ff\"}\n"
            "{\"type\":\"message\",\"id\":\"m1\",\"parentId\":null,\"message\":{\"role\":\"user\",\"content\":\"hello\"}}\n"
            "{\"type\":\"message\",\"sessionId\":\"01a157ff\",\"role\":\"user\",\"content\":\"corrupt_line_without_id\"}\n",
            encoding="utf-8"
        )
        store = WorkingCopyStore(self.root, Path(self.tmp.name) / "work_repair", {".md"})
        manager = LanternBotManager(self.root, lambda _event: None, work_store=store, session_dir=sdir)
        manager._persist_state({
            "sessionId": "01a157ff",
            "sessionFile": str(corrupt_file),
            "model": {"provider": "fake", "id": "gpt-6.1-sol"},
        })
        # _saved_session_file must auto-repair the file by dropping the malformed line
        sf = manager._saved_session_file()
        self.assertEqual(sf, str(corrupt_file.resolve()))
        repaired_lines = [json.loads(l) for l in corrupt_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(repaired_lines), 2)
        self.assertEqual(repaired_lines[0]["type"], "session")
        self.assertEqual(repaired_lines[1]["id"], "m1")
        manager.close()

        # If a session file has completely non-Pi content, it must be quarantined and sessionFile cleared
        bad_file = sdir / "completely_broken.jsonl"
        bad_file.write_text("NOT_JSON_OR_SESSION\n", encoding="utf-8")
        manager2 = LanternBotManager(self.root, lambda _event: None, work_store=store, session_dir=sdir)
        manager2._persist_state({
            "sessionId": "broken-id",
            "sessionFile": str(bad_file),
            "model": {"provider": "fake", "id": "gpt-6.1-sol"},
        })
        sf2 = manager2._saved_session_file()
        self.assertEqual(sf2, "")
        cmd2 = manager2._command()
        self.assertNotIn("--session", cmd2)
        self.assertTrue(any(f.name.startswith("completely_broken.corrupted") for f in sdir.glob("*.bak")))
        manager2.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lantern.pi_chat import PiChatManager


class PiChatManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.events = []
        self.settled = threading.Event()
        fake = Path(__file__).with_name("fake_pi_rpc.py")

        def emit(event):
            self.events.append(event)
            if (event.get("type") == "chat_pi_event"
                    and event.get("event", {}).get("type") == "agent_settled"):
                self.settled.set()

        self.manager = PiChatManager(
            self.root,
            emit,
            session_dir=self.root / "sessions",
            argv_override=[sys.executable, "-u", str(fake)],
            request_timeout=3,
        )

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def test_state_starts_process_and_persists_session(self):
        state = self.manager.get_state()
        self.assertEqual(state["sessionId"], "fake-session-1")
        self.assertTrue(self.manager.summary()["running"])
        saved = json.loads((self.root / "sessions" / "lantern-active.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["sessionId"], "fake-session-1")

    def test_model_inventory_is_bounded_to_five_priorities(self):
        models = self.manager.available_models()
        self.assertEqual(len(models), 5)
        self.assertEqual(
            [item["id"] for item in models],
            [
                "gpt-6.1-sol",
                "gpt-6-astra",
                "claude-opus-5-5-high",
                "claude-sonnet-5-5-high",
                "gemini-3.1-pro-low",
            ],
        )

    def test_model_switch_uses_same_session(self):
        before = self.manager.get_state()["sessionId"]
        self.manager.set_model("fake", "claude-opus-5-5-high")
        after = self.manager.get_state()
        self.assertEqual(after["sessionId"], before)
        self.assertEqual(after["model"]["id"], "claude-opus-5-5-high")

    def test_new_session_changes_session_without_restarting_process(self):
        before = self.manager.get_state()
        proc = self.manager.proc
        after = self.manager.new_session()
        self.assertNotEqual(after["sessionId"], before["sessionId"])
        self.assertIs(self.manager.proc, proc)
        self.assertTrue(self.manager.summary()["running"])

    def test_prompt_wraps_latest_lantern_context_and_streams_events(self):
        target = self.root / "docs" / "spec.md"
        self.manager.prompt(
            "Fix this paragraph",
            {
                "kind": "markdown",
                "path": str(target.relative_to(self.root)),
                "folder": "docs",
                "markdownMode": "source",
                "line": 243,
                "selectedText": "old text",
            },
        )
        self.assertTrue(self.settled.wait(2))
        messages = self.manager.get_messages()
        prompt = messages[0]["content"]
        self.assertIn("<lantern_context>", prompt)
        self.assertIn("path: " + str(target.resolve()), prompt)
        self.assertIn("folder: " + str((self.root / "docs").resolve()), prompt)
        self.assertIn("markdownMode: source", prompt)
        self.assertIn("line: 243", prompt)
        self.assertIn("selectedText:\nold text", prompt)
        self.assertIn("<user_request>\nFix this paragraph", prompt)
        pi_events = [item["event"] for item in self.events if item.get("type") == "chat_pi_event"]
        self.assertTrue(any(item.get("type") == "message_update" for item in pi_events))
        self.assertTrue(any(item.get("type") == "agent_settled" for item in pi_events))

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
        saved = self.root / "sessions" / "saved.jsonl"
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text('{"type":"session"}\n', encoding="utf-8")
        manager = PiChatManager(self.root, lambda _event: None, session_dir=saved.parent)
        manager._persist_state({
            "sessionId": "session-persisted",
            "sessionFile": str(saved),
            "model": {"provider": "fake", "id": "gpt-6.1-sol"},
        })
        command = manager._command()
        self.assertIn("--session", command)
        self.assertEqual(command[command.index("--session") + 1], str(saved.resolve()))
        state = json.loads(manager.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["sessionFile"], str(saved))


if __name__ == "__main__":
    unittest.main()

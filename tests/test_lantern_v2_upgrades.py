from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern.pi_chat import (
    LanternBotManager,
    build_prompt,
    export_session_html,
    extract_message_structured,
    extract_message_text,
)
from lantern.system_telemetry import get_system_telemetry
from lantern.working_copy import WorkingCopyStore

ROOT = Path(__file__).resolve().parent.parent


class LanternV2UpgradesTests(unittest.TestCase):
    def test_system_telemetry_returns_cpu_ram_gpu_structure(self):
        stats = get_system_telemetry(force=True)
        self.assertIn("cpu", stats)
        self.assertIn("memory", stats)
        self.assertIn("gpus", stats)
        self.assertIn("primaryGpu", stats)
        self.assertIsInstance(stats["gpus"], list)

    def test_extract_message_structured_avoids_object_object_and_parses_subagents(self):
        raw_message = {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Spawning 4 luna subagents..."},
                {
                    "type": "text",
                    "text": (
                        "Đã spawn 4 subagent chạy song song với model `6-luna`:\n"
                        "- `luna-1`: `11980108-75ed-425`\n\n"
                        "<task-notification>\n"
                        "<task-id>e49f1242-6d58-4a8</task-id>\n"
                        "<tool-use-id>call_KXbnsUAAtTUeqsqAednCFT5k</tool-use-id>\n"
                        "<output-file>/tmp/e49f1242-6d58-4a8.output</output-file>\n"
                        "<status>Done</status>\n"
                        "<summary>Agent \"Test subagent three\" completed</summary>\n"
                        "<result>luna-3 online. I can inspect the workspace.</result>\n"
                        "<usage><total_tokens>7350</total_tokens><tool_uses>0</tool_uses>"
                        "<context_percent>2</context_percent><duration_ms>2481</duration_ms></usage>\n"
                        "</task-notification>\n"
                        "Full transcript available at: /tmp/e49f1242-6d58-4a8.output"
                    ),
                },
                {
                    "type": "toolCall",
                    "id": "call_1",
                    "name": "subagent",
                    "arguments": {"model": "6-luna", "count": 4},
                },
                {"nested": [{"text": "extra block"}, {"content": "clean string"}]},
            ],
        }
        text = extract_message_text(raw_message)
        self.assertNotIn("[object Object]", text)
        structured = extract_message_structured(raw_message)
        self.assertNotIn("[object Object]", structured["text"])
        self.assertEqual(len(structured["subagents"]), 1)
        sub = structured["subagents"][0]
        self.assertEqual(sub["taskId"], "e49f1242-6d58-4a8")
        self.assertEqual(sub["status"], "Done")
        self.assertEqual(sub["summary"], 'Agent "Test subagent three" completed')
        self.assertIn("luna-3 online", sub["result"])
        self.assertEqual(sub["usage"]["totalTokens"], 7350)
        self.assertEqual(sub["usage"]["durationMs"], 2481)

    def test_slash_commands_bypass_lantern_context_envelope(self):
        ctx = {
            "kind": "markdown",
            "path": "docs/spec.md",
            "line": 42,
            "selectedText": "hello",
            "attachments": ["a.py"],
        }
        self.assertEqual(build_prompt("/model", ctx), "/model")
        self.assertEqual(build_prompt("  /mcp list  ", ctx), "/mcp list")
        normal = build_prompt("Explain this section", ctx)
        self.assertIn("<lantern_context>", normal)
        self.assertIn("- a.py", normal)

    def test_export_session_html_preserves_full_unabbreviated_context(self):
        long_text = "FULL_CONTENT_LINE_" + ("A" * 5000)
        snapshot = {
            "sessionName": "Deep Audit Session",
            "sessionFile": "/tmp/session-test.jsonl",
            "scope": "local",
            "model": {"provider": "anthropic", "id": "claude-sonnet-4-5", "name": "claude-sonnet-4-5"},
            "thinkingLevel": "high",
            "toolMode": "full",
            "contextUsage": {"messageCount": 2, "estimatedTokens": 1400},
            "messages": [
                {"role": "user", "text": "Inspect my code", "context": {"path": "lantern/pi_chat.py", "line": 10}},
                {
                    "role": "assistant",
                    "text": long_text,
                    "thinking": "Full reasoning log without truncation",
                    "toolCalls": [{"id": "t1", "name": "read", "arguments": {"path": "lantern/pi_chat.py"}}],
                },
            ],
            "activity": [{"kind": "tool", "title": "read", "detail": "200 lines read", "status": "done"}],
        }
        html_doc = export_session_html(snapshot)
        self.assertIn(long_text, html_doc)
        self.assertIn("Full reasoning log without truncation", html_doc)
        self.assertIn("FULL UNABBREVIATED CONTEXT", html_doc)

    def test_favorite_models_toggle_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            mgr = LanternBotManager(root, lambda _: None, work_store=work, session_dir=root / ".lantern" / "sessions")
            res1 = mgr.toggle_favorite_model("openai", "gpt-5")
            self.assertIn("openai/gpt-5", res1["favorites"])
            res2 = mgr.toggle_favorite_model("openai", "gpt-5")
            self.assertNotIn("openai/gpt-5", res2["favorites"])

    def test_markdown_split_view_and_wrap_controls_exist_in_shell(self):
        js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        paged = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertIn("applySplitMode", js)
        self.assertIn("splitSwap", js)
        self.assertIn("syncWrapBtn", js)
        self.assertIn("md-split-active", css)
        self.assertIn("md-sticky-diff-bar", css)
        self.assertIn("Section Editing Live Diff", paged)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern.live_markdown import LiveMarkdownStore
from lantern.working_copy import WorkingCopyError


class LiveMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.files = root / "docs"
        self.files.mkdir()
        self.target = self.files / "report.md"
        self.target.write_text("# Report\n\nOriginal\n", encoding="utf-8")
        self.store = LiveMarkdownStore(self.files, root / "work", {".md", ".markdown"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_browser_writes_real_immediately_and_accept_only_changes_md_temp(self):
        initial = self.store.get("report.md")
        self.assertEqual(initial["state"], "clean")
        self.assertEqual(initial["saved"]["content"].replace("\r\n", "\n"), "# Report\n\nOriginal\n")
        temp = Path(initial["tempPath"])
        original_temp = temp.read_bytes()

        changed = self.store.write("report.md", "# Report\n\nEdited\n",
                                   expect_hash=None, base_version=initial["saved"]["version"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# Report\n\nEdited\n")
        self.assertEqual(temp.read_bytes(), original_temp)
        self.assertEqual(self.store.get("report.md")["work"]["hash"], changed["hash"])

        accepted = self.store.save("report.md", expect_hash=changed["hash"],
                                   expect_saved_version=initial["saved"]["version"])
        self.assertEqual(accepted["state"], "clean")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# Report\n\nEdited\n")
        self.assertEqual(temp.read_bytes(), self.target.read_bytes())
        self.assertIsNone(self.store.get("report.md")["work"])

    def test_vscode_change_is_detected_without_lantern_save(self):
        initial = self.store.get("report.md")
        self.target.write_text("# Report\n\nVS Code edit\n", encoding="utf-8")
        new = self.store.get("report.md")
        self.assertEqual(new["state"], "pending")
        self.assertEqual(new["work"]["content"].replace("\r\n", "\n"), "# Report\n\nVS Code edit\n")
        self.assertEqual(new["saved"], initial["saved"])
        with self.assertRaises(WorkingCopyError) as ctx:
            self.store.write("report.md", "stale Lantern", expect_hash=None,
                             base_version=initial["saved"]["version"])
        self.assertEqual(ctx.exception.details["reason"], "stale")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# Report\n\nVS Code edit\n")

    def test_restore_all_requires_exact_real_version(self):
        initial = self.store.get("report.md")
        change = self.store.write("report.md", "Changed\n", expect_hash=None,
                                  base_version=initial["saved"]["version"])
        with self.assertRaises(WorkingCopyError):
            self.store.discard("report.md", expect_hash="f" * 64)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "Changed\n")
        self.store.discard("report.md", expect_hash=change["hash"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# Report\n\nOriginal\n")

    def test_pi_edits_same_real_path_with_no_private_copy(self):
        state = self.store.get("report.md")
        turn = self.store.begin_turn("report.md", None)
        self.assertTrue(Path(turn["workingPath"]).samefile(self.target))
        self.assertTrue(self.store.get("report.md")["turnActive"])
        self.target.write_text("Edited by LanternBot\n", encoding="utf-8")
        self.assertNotEqual(self.store.peek_hash("report.md"), state["currentVersion"])
        ended = self.store.end_turn("report.md")
        self.assertTrue(ended["realTouched"])
        self.assertEqual(self.store.get("report.md")["work"]["content"].replace("\r\n", "\n"),
                         "Edited by LanternBot\n")

    def test_does_not_silently_lose_legacy_pending_draft(self):
        logical, real, identifier, temp = self.store._resolve("report.md")
        legacy_dir = self.store.legacy_dir / identifier
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy = legacy_dir / real.name
        legacy.write_text("old unsaved edit\n", encoding="utf-8")
        (legacy_dir / "meta.json").write_text('{"v":1}', encoding="utf-8")
        with self.assertRaises(WorkingCopyError) as ctx:
            self.store.get("report.md")
        self.assertEqual(ctx.exception.details["reason"], "legacy_pending")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# Report\n\nOriginal\n")
        self.assertTrue(legacy.exists())

    def test_fake_lanternbot_edits_real_path_and_md_temp_stays_old(self):
        import json
        import sys
        import threading
        from lantern.pi_chat import LanternBotManager
        from lantern.bot_config import LanternBotConfig

        original = "# Real\n\nunsaved working copy\n"
        self.target.write_text(original, encoding="utf-8", newline="")
        initial = self.store.get("report.md")
        events = []
        settled = threading.Event()

        def emit(event):
            events.append(event)
            if event.get("type") == "chat_bot_event" and (
                event.get("event", {}).get("type") == "agent_settled"
            ):
                settled.set()

        fake = Path(__file__).with_name("fake_pi_rpc.py")
        manager = LanternBotManager(
            self.files, emit, work_store=self.store,
            session_dir=Path(self.tmp.name) / "sessions",
            argv_override=[sys.executable, "-u", str(fake)],
            bot_config=LanternBotConfig.from_mapping({"access": {
                "localhost": {"tools": ["*"], "extensions": True},
                "lan": {"tools": ["read", "grep", "find", "ls"]},
            }}),
            request_timeout=3,
            usage_path=Path(self.tmp.name) / "usage.json",
        )
        try:
            manager.prompt("FAKE_EDIT_WORK", {"kind": "markdown", "path": "report.md"},
                           work_hash=None, scope="local")
            self.assertTrue(settled.wait(4))
            self.assertIn("fake Pi working edit",
                          self.target.read_text(encoding="utf-8"))
            state = self.store.get("report.md")
            self.assertEqual(state["saved"]["content"].replace("\r\n", "\n"), original)
            self.assertIn("fake Pi working edit", state["work"]["content"])
            guard = json.loads(self.store.guard_path.read_text(encoding="utf-8"))
            self.assertEqual(guard["activeScope"], "lan")
            self.assertEqual(guard["allowedTools"], ["read", "grep", "find", "ls"])
            self.assertTrue(any(e.get("type") == "chat_work_changed" for e in events))
        finally:
            manager.close()

    def test_newline_and_bom_are_preserved_on_browser_write_and_accept(self):
        self.target.write_bytes(b"\\xef\\xbb\\xbf# Title\\r\\n\\r\\nBefore\\r\\n".decode("unicode_escape").encode("latin1"))
        state = self.store.get("report.md")
        result = self.store.write("report.md", "# Title\n\nAfter\n",
                                  expect_hash=None, base_version=state["saved"]["version"])
        self.assertEqual(self.target.read_bytes(), b"\\xef\\xbb\\xbf# Title\\r\\n\\r\\nAfter\\r\\n".decode("unicode_escape").encode("latin1"))
        self.store.save("report.md", expect_hash=result["hash"],
                        expect_saved_version=state["saved"]["version"])
        self.assertEqual(Path(state["tempPath"]).read_bytes(), self.target.read_bytes())


    def test_accept_copies_external_mixed_eol_bytes_exactly_without_rewriting_real(self):
        original = b"\xef\xbb\xbf# Title\r\n\nBefore\r\nTail"
        changed = b"\xef\xbb\xbf# Title\r\n\nAfter\r\nTail"
        self.target.write_bytes(original)
        initial = self.store.get("report.md")
        temp = Path(initial["tempPath"])
        self.assertEqual(temp.read_bytes(), original)

        self.target.write_bytes(changed)
        pending = self.store.get("report.md")
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(temp.read_bytes(), original)

        accepted = self.store.save(
            "report.md",
            expect_hash=pending["currentVersion"],
            expect_saved_version=initial["saved"]["version"],
        )
        self.assertEqual(accepted["state"], "clean")
        self.assertEqual(self.target.read_bytes(), changed)
        self.assertEqual(temp.read_bytes(), changed)
        self.assertFalse(changed.endswith((b"\n", b"\r")))


    def test_patch_preserves_bom_mixed_eol_unicode_and_is_atomic(self):
        self.assertTrue(hasattr(self.store, "patch"), "LiveMarkdownStore.patch is required")
        original = (
            b"\xef\xbb\xbfHead\r\n" +
            "日本語🏮 here\n".encode("utf-8") +
            b"Tail"
        )
        self.target.write_bytes(original)
        state = self.store.get("report.md")
        temp = Path(state["tempPath"])
        self.assertEqual(temp.read_bytes(), original)

        result = self.store.patch(
            "report.md",
            [
                {
                    "from": {"line": 1, "column": 0},
                    "to": {"line": 1, "column": 4},
                    "insert": "HEAD",
                    "expected": "Head",
                },
                {
                    "from": {"line": 2, "column": 6},
                    "to": {"line": 2, "column": 10},
                    "insert": "HERE\n新行",
                    "expected": "here",
                },
                {
                    "from": {"line": 3, "column": 0},
                    "to": {"line": 3, "column": 4},
                    "insert": "TailX",
                    "expected": "Tail",
                },
            ],
            expect_hash=state["currentVersion"],
            base_version=state["saved"]["version"],
        )
        expected = (
            b"\xef\xbb\xbfHEAD\r\n" +
            "日本語🏮 HERE\n新行\n".encode("utf-8") +
            b"TailX"
        )
        self.assertEqual(self.target.read_bytes(), expected)
        self.assertEqual(temp.read_bytes(), original)
        self.assertEqual(result["currentVersion"], self.store.get("report.md")["currentVersion"])

        before_stale = self.target.read_bytes()
        with self.assertRaises(WorkingCopyError) as ctx:
            self.store.patch(
                "report.md",
                [{
                    "from": {"line": 1, "column": 0},
                    "to": {"line": 1, "column": 4},
                    "insert": "FAIL",
                    "expected": "HEAD",
                }],
                expect_hash="0" * 64,
                base_version=state["saved"]["version"],
            )
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(self.target.read_bytes(), before_stale)

    def test_patch_uses_local_newline_policy_and_rejects_surrogate_split(self):
        self.assertTrue(hasattr(self.store, "patch"), "LiveMarkdownStore.patch is required")
        self.target.write_bytes(b"A\r\nB\r\n")
        state = self.store.get("report.md")
        self.store.patch(
            "report.md",
            [{
                "from": {"line": 2, "column": 1},
                "to": {"line": 2, "column": 1},
                "insert": "\nC",
                "expected": "",
            }],
            expect_hash=state["currentVersion"],
            base_version=state["saved"]["version"],
        )
        self.assertEqual(self.target.read_bytes(), b"A\r\nB\r\nC\r\n")

        self.target.write_bytes("X🏮Y\n".encode("utf-8"))
        state2 = self.store.get("report.md")
        before = self.target.read_bytes()
        with self.assertRaises(WorkingCopyError) as ctx:
            self.store.patch(
                "report.md",
                [{
                    "from": {"line": 1, "column": 2},
                    "to": {"line": 1, "column": 2},
                    "insert": "!",
                    "expected": "",
                }],
                expect_hash=state2["currentVersion"],
                base_version=state2["saved"]["version"],
            )
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(self.target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

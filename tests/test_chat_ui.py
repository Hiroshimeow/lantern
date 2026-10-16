from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lan_drive
import plugin


class ChatUiTests(unittest.TestCase):
    def test_file_manager_shell_loads_shared_chat_assets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = lan_drive.AppConfig(
                root=root,
                port=9999,
                host="127.0.0.1",
                title="Lantern Test",
                cache_dir=root / ".cache",
                config_path=root / "config.yaml",
            )
            with patch.object(lan_drive, "CONFIG", cfg, create=True):
                html = lan_drive.page_shell("Lantern Test", "<main>body</main>", "/docs").decode("utf-8")
        self.assertIn('/static/chatbot.css?v=', html)
        self.assertIn('/static/chatbot.js?v=', html)
        self.assertIn('"currentPath":"docs"', html)

    def test_markdown_preview_loads_chat_assets_and_path_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "docs"
            folder.mkdir()
            md = folder / "spec.md"
            md.write_text("# Title\n\nBody", encoding="utf-8")
            html = plugin.render_preview_page(md, root, anchor_spike=True).decode("utf-8")
        self.assertIn('/static/chatbot.css', html)
        self.assertIn('/static/chatbot.js', html)
        self.assertIn('data-lantern-chat-kind="markdown"', html)
        self.assertIn('data-lantern-chat-path="docs/spec.md"', html)

    def test_shared_chat_script_has_session_model_context_and_lock_controls(self):
        script = (Path(__file__).parents[1] / "static" / "chatbot.js").read_text(encoding="utf-8")
        for token in (
            "chat_sync",
            "chat_prompt",
            "chat_new",
            "chat_abort",
            "chat_set_model",
            "terminal_auth",
            "LanternAnchorBridge",
            "__lanternMdVisual",
            "selectedArray",
            "currentPath",
            "captureMarkdownDraft",
            "chat_draft_update",
            "beginPiDraft",
            "applyPiDraft",
            "New chat",
            "Stop",
        ):
            self.assertIn(token, script)

    def test_chat_drawer_is_side_panel_not_full_screen_modal(self):
        css = (Path(__file__).parents[1] / "static" / "chatbot.css").read_text(encoding="utf-8")
        self.assertIn(".lantern-chat-drawer", css)
        self.assertIn("width:min(", css)
        self.assertIn("@media(max-width:", css)


if __name__ == "__main__":
    unittest.main()

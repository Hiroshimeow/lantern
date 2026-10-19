from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import plugin
from lantern.config import AppConfig
from lantern.filesystem import FileService
from lantern.media import MediaService
from lantern.views import ViewService


class ChatUiTests(unittest.TestCase):
    def test_file_manager_shell_loads_shared_chat_assets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = AppConfig(
                root=root,
                port=9999,
                host="127.0.0.1",
                title="Lantern Test",
                cache_dir=root / ".cache",
                config_path=root / "config.yaml",
            )
            files = FileService(cfg, plugin)
            views = ViewService(cfg, files, MediaService(cfg, files))
            html = views.page_shell("Lantern Test", "<main>body</main>", "/docs").decode("utf-8")
        self.assertIn('/static/chatbot.css?v=', html)
        self.assertIn('/static/chatbot.js?v=', html)
        self.assertIn('/static/vendor/xterm.js?v=', html)
        self.assertIn('/static/vendor/addon-fit.js?v=', html)
        self.assertIn('"currentPath":"docs"', html)

    def test_markdown_preview_loads_chat_assets_and_path_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "docs"
            folder.mkdir()
            md = folder / "spec.md"
            md.write_text("# Title\n\nBody", encoding="utf-8")
            html = plugin.render_preview_page(md, root, anchor_spike=True).decode("utf-8")
        self.assertIn('/static/vendor/xterm.css', html)
        self.assertIn('/static/vendor/xterm.js', html)
        self.assertIn('/static/vendor/addon-fit.js', html)
        self.assertIn('/static/chatbot.css', html)
        self.assertIn('/static/chatbot.js', html)
        self.assertIn('data-lantern-chat-kind="markdown"', html)
        self.assertIn('data-lantern-chat-path="docs/spec.md"', html)

    def test_shared_chat_script_hosts_native_pi_tui_and_protocol(self):
        script = (Path(__file__).parents[1] / "static" / "chatbot.js").read_text(encoding="utf-8")
        for token in (
            "new Terminal",
            "FitAddon.FitAddon",
            "pi_session_sync",
            "pi_session_create",
            "pi_session_attach",
            "pi_session_detach",
            "pi_session_input",
            "pi_session_resize",
            "pi_session_takeover",
            "pi_session_stop",
            "pi_session_replay",
            "pi_session_output",
            "pi_session_ownership",
            "terminal_auth",
            "LanternAnchorBridge",
            "__lanternMdVisual",
            "selectedArray",
            "currentPath",
            "New Pi",
            "Take over",
        ):
            self.assertIn(token, script)
        for legacy in (
            "chat_prompt",
            "chat_sync",
            "chat_set_model",
            "lanternChatProvider",
            "lanternChatModel",
            "lantern-chat-msg",
            "lantern-chat-tool",
        ):
            self.assertNotIn(legacy, script)

    def test_chat_drawer_is_native_tui_panel_with_expand_mode(self):
        css = (Path(__file__).parents[1] / "static" / "chatbot.css").read_text(encoding="utf-8")
        self.assertIn(".lantern-chat-drawer", css)
        self.assertIn(".lantern-pi-host", css)
        self.assertIn('.lantern-chat-drawer[data-expanded="true"]', css)
        self.assertIn("width:min(", css)
        self.assertIn("@media(max-width:", css)


if __name__ == "__main__":
    unittest.main()

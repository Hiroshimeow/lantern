from __future__ import annotations
import sys
from lantern.live_markdown import LiveMarkdownStore

import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lantern.bot_config import LanternBotConfig
from lantern.http.routes.chatbot import ChatbotRoutes
from lantern.pi_chat import LanternBotManager, build_prompt
from lantern.working_copy import WorkingCopyStore
from lantern.ws import dispatch

ROOT = Path(__file__).resolve().parent.parent


class _DummyApp:
    def __init__(self, root: Path, bot: LanternBotManager):
        self.config = type("Cfg", (), {"root": root})()
        self.bot = bot
        self.terminal_access = None


class _DummyHandler(ChatbotRoutes):
    def __init__(self, app: _DummyApp, body: dict | None = None):
        self.app = app
        self.client_address = ("127.0.0.1", 55000)
        self.headers = {}
        self._body = body or {}
        self.sent_status = None
        self.sent_json = None
        self.sent_bytes = None

    def read_json(self, max_bytes: int = 0) -> dict:
        return self._body

    def send_json(self, status: int, data: dict) -> None:
        self.sent_status = status
        self.sent_json = data

    def send_bytes(self, status: int, body: bytes, ctype: str = "", extra: dict | None = None) -> None:
        self.sent_status = status
        self.sent_bytes = body


class LanternV4UpgradesTests(unittest.TestCase):
    def test_windows_shim_unwrapping_and_dict_attachment_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            mgr = LanternBotManager(
                root,
                lambda _: None,
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
            )
            img_dir = root / ".lantern_uploads" / "20261020"
            img_dir.mkdir(parents=True, exist_ok=True)
            img_file = img_dir / "pasted.png"
            img_file.write_bytes(b"\x89PNG\r\n\x1a\n")

            doc_file = root / "notes.md"
            doc_file.write_text("# Notes\n", encoding="utf-8")

            ctx = mgr.normalize_context({
                "kind": "files",
                "folder": ".",
                "attachments": [
                    {"path": ".lantern_uploads/20261020/pasted.png", "name": "pasted.png", "isImage": True},
                    "notes.md",
                ],
            })
            self.assertEqual(ctx["kind"], "folder")
            self.assertEqual(len(ctx["attachments"]), 2)
            self.assertEqual(Path(ctx["attachments"][0]), img_file.resolve())
            self.assertEqual(Path(ctx["attachments"][1]), doc_file.resolve())

            prompt_str = build_prompt("Analyze this pasted screenshot", ctx)
            self.assertIn("<lantern_context>", prompt_str)
            self.assertIn("pasted.png", prompt_str)
            self.assertIn("notes.md", prompt_str)

    def test_chatbot_upload_and_settings_endpoints_work_without_client_ip_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            mgr = LanternBotManager(
                root,
                lambda _: None,
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
            )
            app = _DummyApp(root, mgr)
            png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b64_data = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
            handler = _DummyHandler(
                app,
                body={
                    "files": [
                        {
                            "name": "clipboard screenshot (1).png",
                            "type": "image/png",
                            "source": "paste",
                            "dataBase64": b64_data,
                        },
                        {
                            "name": "spec-snippet.txt",
                            "type": "text/plain",
                            "source": "drop",
                            "dataBase64": base64.b64encode(b"hello world").decode("ascii"),
                        },
                    ]
                },
            )
            # Also verify string self.app._client_ip does not raise "'str' object has no attribute '_client_ip'"
            app._client_ip = "127.0.0.1"
            handler.api_chatbot_upload()
            self.assertEqual(handler.sent_status, 200)
            self.assertTrue(handler.sent_json["ok"])
            atts = handler.sent_json["attachments"]
            self.assertEqual(len(atts), 2)
            self.assertTrue(atts[0]["isImage"])
            self.assertFalse(atts[1]["isImage"])
            saved_img = root / atts[0]["path"]
            self.assertTrue(saved_img.is_file())
            self.assertEqual(saved_img.read_bytes(), png_bytes)

            # Test Custom System Prompt & Skills settings endpoint
            skill_dir = root / "custom_skills" / "demo-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo custom skill\n---\n# Body\n", encoding="utf-8")

            settings_handler = _DummyHandler(
                app,
                body={
                    "customSystemPrompt": "Always respond concisely in English.",
                    "useGlobalSkills": True,
                    "customSkillPaths": ["custom_skills"],
                },
            )
            settings_handler.api_chatbot_prefs_post()
            self.assertEqual(settings_handler.sent_status, 200)
            self.assertTrue(settings_handler.sent_json["ok"])
            prefs = settings_handler.sent_json["prefs"]
            self.assertEqual(prefs["customSystemPrompt"], "Always respond concisely in English.")
            self.assertTrue(any(s["name"] == "demo-skill" for s in settings_handler.sent_json["skills"]))

    def test_unknown_option_no_mcp_is_stripped_automatically_on_retry(self):
        import os
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_pi = root / "fake_pi_no_mcp.py"
            fake_pi.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "if '--help' in sys.argv:\n"
                "    sys.stdout.write('Usage: pi [--mode rpc] [--session file]\\n')\n"
                "    sys.exit(0)\n"
                "if '--no-mcp' in sys.argv:\n"
                "    sys.stderr.write('Error: Unknown option: --no-mcp\\n')\n"
                "    sys.exit(1)\n"
                "for line in sys.stdin:\n"
                "    req = json.loads(line)\n"
                "    if req.get('type') == 'get_state':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':req['id'],'command':'get_state','success':True,'data':{'sessionId':'s1','sessionFile':None,'model':{'provider':'openai','id':'gpt-5','name':'gpt-5'}}}) + '\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif req.get('type') == 'get_available_models':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':req['id'],'command':'get_available_models','success':True,'data':{'models':[{'provider':'openai','id':'gpt-5','name':'gpt-5'}]}})+ '\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif req.get('type') == 'get_messages':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':req['id'],'command':'get_messages','success':True,'data':{'messages':[]}})+ '\\n')\n"
                "        sys.stdout.flush()\n",
                encoding="utf-8",
            )
            fake_pi.chmod(0o755)
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            old_env = os.environ.get("LANTERN_PI_COMMAND")
            os.environ["LANTERN_PI_COMMAND"] = str(fake_pi)
            mgr = LanternBotManager(
                root,
                lambda _: None,
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
                bot_config=LanternBotConfig.from_mapping({
                    "access": {"localhost": {"enabled": True, "tools": ["*"], "extensions": True, "mcp": False}},
                }),
            )
            try:
                snap = mgr.bootstrap_state()
                self.assertIn("--no-mcp", mgr.unsupported_cli_flags)
                self.assertEqual(snap["sessionId"], "s1")
            finally:
                if old_env is None:
                    os.environ.pop("LANTERN_PI_COMMAND", None)
                else:
                    os.environ["LANTERN_PI_COMMAND"] = old_env
                mgr.close()

    def test_steer_queue_and_ws_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            events = []
            mgr = LanternBotManager(
                root,
                lambda ev: events.append(ev),
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
            )
            mgr._turn_in_progress = True  # Simulate active bot turn
            res = mgr.steer("Focus on section 2 only", {"kind": "folder", "folder": "."})
            self.assertTrue(res["queued"])
            self.assertEqual(res["queueSize"], 1)
            self.assertTrue(any(e.get("type") == "chat_steer_queued" for e in events))

    def test_100_percent_english_ui_and_no_redundant_vietnamese_labels(self):
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        paged_js = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")

        for forbidden in (
            "Nội dung cũ",
            "Kéo rèm",
            "Đóng rèm",
            "Đính kèm",
            "Mức suy luận",
            "Bản nháp đang sửa",
            "Đoạn sửa trước",
            "Đoạn sửa tiếp theo",
        ):
            self.assertNotIn(forbidden, chat_js)
            self.assertNotIn(forbidden, shell_js)
            self.assertNotIn(forbidden, paged_js)

    def test_gfm_table_rendering_in_deleted_markdown_visual_mode(self):
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        self.assertIn("md-del-rendered-table", shell_js)
        self.assertIn("splitPipeRow", shell_js)
        self.assertIn("lantern-md-diff-view-mode", shell_js)
        self.assertIn("md-hunk-floating-pill", shell_js)
        self.assertIn("mdDiffHunkPickerBtn", shell_js)
        self.assertIn("md-diff-hunk-dropdown", shell_js)
        self.assertIn("flashFocusSyncTarget", shell_js)
        self.assertIn("syncSplitScrollFrom", shell_js)
        self.assertNotIn("renderCurtainCompare", shell_js)

    def test_no_strikethrough_and_30_percent_smaller_deletion_font(self):
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        chat_css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        self.assertNotIn("text-decoration:line-through", shell_css.replace(" ", ""))
        self.assertNotIn("text-decoration:line-through", chat_css.replace(" ", ""))
        for cls in (
            ".md-diff-word-del",
            ".md-diff-word-add",
            ".md-del-rendered-table",
            ".md-hunk-floating-pill",
            ".md-diff-hunk-dropdown",
            ".md-focus-sync-flash",
            ".md-ghost-cursor-badge",
            "font-size:11.5px!important",
        ):
            self.assertIn(cls, shell_css)
        for chat_cls in (
            ".lc-lantern-svg",
            ".lc-activity-ticker",
            ".lc-send-btn.is-steer",
            ".lc-citation-pill",
        ):
            self.assertIn(chat_cls, chat_css)

    def test_diff_words_table_parser_and_merge3_conflicts_in_node(self):
        script = f"""
        const diff = require({json.dumps(str(ROOT / "static" / "markdown_draft_diff.js"))});
        const w = diff.diffWords("Hello old world", "Hello new world");
        const cells = diff.parseTableRowCells("| Col A | Col B | 120 |");
        const sep = diff.parseTableRowCells("| --- | :---: | ---: |");
        const m = diff.merge3("line 1\\nline 2\\nline 3", "line 1\\nuser edit\\nline 3", "line 1\\nbot edit\\nline 3");
        console.log(JSON.stringify({{ w, cells, sep, conflicts: m.conflicts }}));
        """
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout.strip())
        self.assertEqual(out["cells"], ["Col A", "Col B", "120"])
        self.assertIsNone(out["sep"])
        self.assertTrue(any(tok["type"] == "del" and "old" in tok["text"] for tok in out["w"]))
        self.assertTrue(any(tok["type"] == "add" and "new" in tok["text"] for tok in out["w"]))
        self.assertEqual(len(out["conflicts"]), 1)

    def test_lanbot_features_in_chatbot_js(self):
        js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        for token in (
            "Lanbot",
            "LANTERN_SVG",
            "cachedSelection",
            "chat_steer",
            "Send ↵",
            "↳ [Steer]",
            "lcActivityTicker",
            "lcCustomPromptInput",
            "lcUseGlobalSkillsCheck",
            "lcCustomSkillPathsInput",
            "lc-citation-pill",
            "uploadClientFiles",
            "/api/chatbot/upload",
        ):
            self.assertIn(token, js)

    def test_v6_ten_fixes_verification(self):
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        chat_css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        src_vendor = (ROOT / "static" / "vendor" / "lantern-source-editor.min.js").read_text(encoding="utf-8")

        # 1-3: Split pane independent viewport containers & full-height Source editor
        self.assertIn('[data-pane-role="primary"]', shell_css)
        self.assertIn("height:calc(100dvh", shell_css.replace(" ", ""))
        self.assertNotIn('height:"min(74vh, 1000px)"', src_vendor)
        self.assertIn('minHeight:"78vh"', src_vendor)

        # 4: Slash commands executed via Pi core / local handlers
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / ".pi" / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("---\ndescription: Demo skill\n---\n# Demo Skill Instructions\nRun demo step.", encoding="utf-8")
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            events = []
            mgr = LanternBotManager(root, lambda ev: events.append(ev), work_store=work, session_dir=root / ".lantern" / "sessions")
            res_think = mgr.execute_slash_command("/thinking high")
            self.assertTrue(res_think["ok"])
            self.assertEqual(res_think["thinkingLevel"], "high")
            res_tools = mgr.execute_slash_command("/tools readonly")
            self.assertTrue(res_tools["ok"])
            self.assertEqual(res_tools["toolPreset"], "readonly")
            res_skills = mgr.execute_slash_command("/skills")
            self.assertTrue(res_skills["success"])
            res_skill_run = mgr.execute_slash_command("/demo-skill check table")
            self.assertIn("_expanded_prompt", res_skill_run)
            self.assertIn("Demo Skill Instructions", res_skill_run["_expanded_prompt"])

        # 5: Scroll isolation inside Lanbot drawer
        self.assertIn("overscroll-behavior: contain", chat_css)
        self.assertIn("drawer.addEventListener('wheel'", chat_js)

        # 6: Export HTML button moved inside Settings only (not in top header actions)
        self.assertNotIn('id="lcExportBtn"', chat_js)
        self.assertIn('id="lcExportFullBtn"', chat_js)

        # 7 & 9: Visual mode E diff block mapping + Milkdown redundant escape stripper
        self.assertIn("stripRedundantMilkdownEscapes", shell_js)
        self.assertIn("reconcileVisualMarkdown", shell_js)
        self.assertIn("parseTopLevelMarkdownBlocks", shell_js)
        self.assertIn("md-visual-dom-pill-anchor", shell_js)

        # 8: Multi-line table diff in Source mode S renders per-row without nowrap truncation
        self.assertIn(".join(\"\\n\")", src_vendor)
        self.assertIn("white-space:pre-wrap!important", shell_css)

        # 10: 5-row default prompt box + vertical resizer + hidden provider on pill
        self.assertIn('rows="5"', chat_js)
        self.assertIn('id="lcInputResizer"', chat_js)
        self.assertIn("#lcModelBtn .lc-provider-tag", chat_css)

    def test_v7_four_core_pillars_verification(self):
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        crepe_vendor = (ROOT / "static" / "vendor" / "lantern-crepe.min.js").read_text(encoding="utf-8")
        yaml_copy = (ROOT / "lan_drive_config.yaml_copy").read_text(encoding="utf-8")

        # Pillar 1: YAML-based Backend Policy (no editable tool mode in UI Settings, default Localhost Full/YOLO '*')
        self.assertNotIn("lcToolModeSelect", chat_js)
        self.assertIn("lcYamlPolicySummary", chat_js)
        self.assertIn("lan_drive_config.yaml", chat_js)
        cfg = LanternBotConfig.from_mapping({})
        self.assertEqual(cfg.access.localhost.tools, ("*",))
        self.assertTrue(cfg.access.localhost.is_full_tools)
        self.assertTrue(cfg.access.localhost.extensions)
        self.assertTrue(cfg.access.localhost.mcp)
        self.assertEqual(cfg.access.lan.tools, ("read", "grep", "find", "ls"))
        self.assertFalse(cfg.access.lan.extensions)
        self.assertFalse(cfg.access.lan.mcp)
        self.assertIn('tools: ["*"]', yaml_copy)

        # Pillar 2: Milkdown Raw Format Protection (AST/Block-level + Line-level reconciliation in Node)
        self.assertIn("isCleanFromMount", crepe_vendor)
        self.assertIn("LanternReconcileMarkdown", shell_js)
        node_test = """
        global.window = {};
        global.document = {
          querySelector: () => null,
          querySelectorAll: () => [],
          addEventListener: () => {},
        };
        global.localStorage = { getItem: () => null, setItem: () => {} };
        require("./static/markdown_visual_shell.js");
        const { reconcileVisualMarkdown } = global.window.LanternReconcileMarkdown;

        const base = [
          "---",
          "title: v7_spec -- full_test & check",
          "---",
          "",
          "# Heading_One -- Overview & Scope",
          "",
          "* Bullet_item_1 with snake_case_var and --flag_name & [ref]",
          "* Bullet_item_2 untouched",
          "",
          "| Col_A | Col_B |",
          "| --- | --- |",
          "| val_1 | val_2 |"
        ].join("\\n");

        // Case A: Milkdown re-serializes untouched markdown with escapes, '-' bullets, and expanded tables
        const milkdownUntouched = [
          "# Heading\\\\_One \\\\-- Overview \\\\& Scope",
          "",
          "- Bullet\\\\_item\\\\_1 with snake\\\\_case\\\\_var and \\\\--flag\\\\_name \\\\& \\\\[ref\\\\]&#x20;",
          "- Bullet\\\\_item\\\\_2 untouched",
          "",
          "| Col\\\\_A   | Col\\\\_B   |",
          "| :------- | :------- |",
          "| val\\\\_1   | val\\\\_2   |"
        ].join("\\n");

        const outUntouched = reconcileVisualMarkdown(milkdownUntouched, base);

        // Case B: User edits only Bullet_item_1; Bullet_item_2, frontmatter, and table remain untouched
        const milkdownEdited = [
          "# Heading\\\\_One \\\\-- Overview \\\\& Scope",
          "",
          "- Bullet\\\\_item\\\\_1 UPDATED with snake\\\\_case\\\\_var and \\\\--flag\\\\_name",
          "- Bullet\\\\_item\\\\_2 untouched",
          "",
          "| Col\\\\_A   | Col\\\\_B   |",
          "| :------- | :------- |",
          "| val\\\\_1   | val\\\\_2   |"
        ].join("\\n");

        const outEdited = reconcileVisualMarkdown(milkdownEdited, base);
        console.log(JSON.stringify({ outUntouched, outEdited }));
        """
        proc = subprocess.run(["node", "-e", node_test], cwd=str(ROOT), capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())
        self.assertIn("* Bullet_item_1 with snake_case_var and --flag_name & [ref]", res["outUntouched"])
        self.assertNotIn("\\_", res["outUntouched"])
        self.assertNotIn("\\--", res["outUntouched"])
        # In edited case, the edited bullet keeps its original '*' marker and strips redundant escapes!
        self.assertIn("* Bullet_item_1 UPDATED with snake_case_var and --flag_name", res["outEdited"])
        self.assertIn("* Bullet_item_2 untouched", res["outEdited"])
        self.assertIn("| Col_A | Col_B |", res["outEdited"])
        self.assertIn("title: v7_spec -- full_test & check", res["outEdited"])

        # Pillar 3: Chatbot State Persistence (client streamTurn + recordAssistantTurnInState + backend .jsonl)
        self.assertIn("recordAssistantTurnInState", chat_js)
        self.assertIn("resetStreamTurn", chat_js)

        # Pillar 4: Double-Click to Jump (independent pane scrolling, no auto scroll-lock, Mode S 100% height)
        self.assertIn("resolveLineFromPaneEvent", shell_js)
        self.assertIn("dblclick", shell_js)
        self.assertNotIn("scrollLock:", shell_js)
        self.assertIn("flex:1 1 auto", shell_css)

    def test_v7_1_five_user_reported_bugs_fixed(self):
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        chat_css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        src_vendor = (ROOT / "static" / "vendor" / "lantern-source-editor.min.js").read_text(encoding="utf-8")

        # Bug 1: Visual Edit bundle (lantern-crepe.min.js) loads and exports createVisualMarkdown without SyntaxError
        crepe_check = """
        const el = () => ({ style: {}, setAttribute: () => {}, appendChild: () => {}, innerHTML: "", textContent: "" });
        global.window = { customElements: { get: () => true, define: () => {} } };
        global.customElements = global.window.customElements;
        global.HTMLElement = class {};
        global.document = { documentElement: el(), createElement: el, head: el(), body: el() };
        global.navigator = { userAgent: "Mozilla/5.0" };
        require("./static/vendor/lantern-crepe.min.js");
        require("./static/vendor/lantern-source-editor.min.js");
        if (typeof global.window.LanternCrepe?.createVisualMarkdown !== "function") process.exit(1);
        if (typeof global.window.LanternSourceEditor?.createSourceMarkdown !== "function") process.exit(1);
        """
        subprocess.run(["node", "-e", crepe_check], cwd=str(ROOT), check=True)

        # Bug 2: flashFocusSyncTarget never appends 📍 Line X DOM badges into CodeMirror / ProseMirror contenteditable
        self.assertNotIn("📍 Line", shell_js)
        self.assertNotIn("targetEl.appendChild(badge)", shell_js)
        self.assertIn('targetEl.closest(\x27.cm-editor, .ProseMirror, [contenteditable="true"]\x27)', shell_js)

        # Bug 3: Stop button hidden when [hidden] is set; turn_end releases _turn_in_progress; New Conversation resets state
        self.assertIn(".lc-stop-btn[hidden]", chat_css)
        self.assertIn("display: none !important", chat_css)
        self.assertIn("snap.isNew || sessionChanged || snap.messages.length === 0", chat_js)

        # Bug 4: Redundant 🎯 Double-Click Jump button removed from toolbar
        self.assertNotIn("🎯 Double-Click Jump", shell_js)
        self.assertNotIn("dblClickJumpBtn", shell_js)

        # Bug 5: Instantaneous hover (0.02s), Start-of-Line (left:0) & Above-Line (top:-26px) in Preview/Visual, and Start-of-Line in Source & Tables
        self.assertIn("top:-26px;left:0;right:auto", shell_css.replace(" ", ""))
        self.assertIn("transition:opacity .02s linear", shell_css)
        self.assertIn("order:-1;position:sticky;left:6px", shell_css.replace(" ", ""))
        self.assertIn("return e.append(i,t),e", src_vendor)
        self.assertIn("firstCell.prepend(actWrap)", shell_js)



    def test_v7_2_multiturn_tools_and_session_tokens(self):
        """Verify v7.2 fixes:
        1. Multi-turn tool calls (read -> turn_end -> edit -> turn_end -> final answer) keep local tool scope active
           and coalesce into a single assistant message without empty Lanbot bubbles.
        2. IPv4-mapped IPv6 loopback (::ffff:127.0.0.1) is recognized as local scope.
        3. sessionTokens resets to 0 on New Chat even when daily usage.tokens is large (e.g. 285,871).
        4. _repair_pi_session_file promotes buried session headers and cleans invalid entries.
        """
        from types import SimpleNamespace
        from lantern.ws import _chat_scope
        from lantern.pi_chat import LanternBotManager

        # 1. IPv4-mapped IPv6 loopback check
        peer_v6_loop = SimpleNamespace(client_ip="::ffff:127.0.0.1")
        self.assertEqual(_chat_scope(peer_v6_loop), "local")
        peer_lan = SimpleNamespace(client_ip="192.168.1.99")
        self.assertEqual(_chat_scope(peer_lan), "lan")

        # 2. Coalescing multi-turn assistant + toolResult messages (no empty Lanbot bubbles)
        raw_turns = [
            {"role": "user", "content": "Delete first 3 lines"},
            {"role": "assistant", "content": [{"type": "toolCall", "id": "c1", "name": "read", "arguments": {"path": "a.md"}}]},
            {"role": "toolResult", "toolCallId": "c1", "toolName": "read", "content": [{"type": "text", "text": "line1\nline2"}]},
            {"role": "assistant", "content": [{"type": "toolCall", "id": "c2", "name": "edit", "arguments": {"path": "a.md"}}]},
            {"role": "toolResult", "toolCallId": "c2", "toolName": "edit", "content": [{"type": "text", "text": "ok"}]},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": [{"type": "text", "text": "Deleted first 3 lines."}]},
        ]
        coalesced = LanternBotManager._coalesce_transcript_list(raw_turns)
        self.assertEqual(len(coalesced), 2)
        self.assertEqual(coalesced[0]["role"], "user")
        self.assertEqual(coalesced[1]["role"], "assistant")

        # 3. Buried session header auto-repair
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "2026-10-20T06-29-12-989Z_test.jsonl"
            p.write_text(
                '{"type":"message","sessionId":"s1","role":"user","content":"hi"}\n'
                '{"type":"session","version":3,"id":"s1","timestamp":"2026-10-20T06:29:12Z","cwd":"."}\n'
                '{"type":"message","id":"m1","parentId":null,"message":{"role":"user","content":"hi"}}\n',
                encoding="utf-8",
            )
            self.assertTrue(LanternBotManager._repair_pi_session_file(p))
            repaired = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(repaired[0]["type"], "session")
            self.assertEqual(len(repaired), 2)

        # 4. chatbot.js uses estimateSessionTokens instead of daily usage.tokens
        chatbot_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        self.assertIn("function estimateSessionTokens(", chatbot_js)
        self.assertIn("function updateTokenBadgeDisplay(", chatbot_js)
        self.assertNotIn("estimatedTokens: Number(snap.summary.usage.tokens", chatbot_js)



    def test_v73_live_markdown_hard_lock_during_bot_turn(self):
        import tempfile
        from lantern.live_markdown import LiveMarkdownStore
        from lantern.working_copy import WorkingCopyError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            work = Path(tmp) / "work"
            root.mkdir()
            md = root / "spec.md"
            md.write_text("# Title\n\nOriginal row\n", encoding="utf-8")

            store = LiveMarkdownStore(root, work, {".md"})
            state0 = store.get("spec.md")
            base_ver = state0["saved"]["version"]

            # Start bot turn
            turn_info = store.begin_turn("spec.md", None)
            self.assertEqual(turn_info["path"], "spec.md")
            self.assertTrue(store.get("spec.md")["turnActive"])

            # Any browser HTTP write/patch/save/discard while bot turn is active must fail with 409 pi_turn
            with self.assertRaises(WorkingCopyError) as ctx_w:
                store.write("spec.md", "# Title\n\nBrowser overwrite\n", expect_hash=None, base_version=base_ver)
            self.assertEqual(ctx_w.exception.status, 409)
            self.assertEqual(ctx_w.exception.details.get("reason"), "pi_turn")

            with self.assertRaises(WorkingCopyError) as ctx_p:
                store.patch("spec.md", [], expect_hash=None, base_version=base_ver)
            self.assertEqual(ctx_p.exception.status, 409)
            self.assertEqual(ctx_p.exception.details.get("reason"), "pi_turn")

            # Meanwhile Pi can edit the real file on disk directly
            md.write_text("# Title\n\nBot updated row\n", encoding="utf-8")

            # End bot turn -> unlocks file
            end_info = store.end_turn("spec.md")
            self.assertTrue(end_info["realTouched"])
            self.assertFalse(store.get("spec.md")["turnActive"])

            # Now browser write succeeds again
            state1 = store.get("spec.md")
            res = store.write(
                "spec.md",
                "# Title\n\nBot updated row + user edit\n",
                expect_hash=state1["work"]["hash"],
                base_version=state1["saved"]["version"],
            )
            self.assertEqual(res["state"], "pending")

    def test_v73_localhost_master_lan_lock(self):
        from lantern.terminal_auth import TerminalAccess, hash_password

        pw_hash = hash_password("correct-horse-battery")
        access = TerminalAccess(pw_hash, local_bypass=True)

        # LAN client logs in
        code, tok = access.login("192.168.1.50", "correct-horse-battery")
        self.assertEqual(code, 200)
        cookie = f"lantern_terminal={tok}"
        self.assertTrue(access.permitted("192.168.1.50", cookie))
        self.assertEqual(access.active_lan_sessions(), 1)

        # Localhost revokes all LAN sessions & hard-locks LAN
        revoked = access.revoke_all_lan(hard_lock=True)
        self.assertEqual(revoked, 1)
        self.assertEqual(access.active_lan_sessions(), 0)
        self.assertTrue(access.lan_locked)

        # LAN client's old cookie is immediately revoked and password is required
        self.assertFalse(access.permitted("192.168.1.50", cookie))
        self.assertTrue(access.required("192.168.1.50"))
        # Entering the valid password after Lock succeeds
        code2, tok2 = access.login("192.168.1.50", "correct-horse-battery")
        self.assertEqual(code2, 200)
        self.assertTrue(access.permitted("192.168.1.50", f"lantern_terminal={tok2}"))

        # Localhost itself remains unrestricted
        self.assertFalse(access.required("127.0.0.1"))
        self.assertTrue(access.permitted("127.0.0.1", ""))
        self.assertTrue(access.permitted("::ffff:127.0.0.1", ""))

        # Localhost unlocks LAN (hard_lock=False) -> LAN can access without password
        access.revoke_all_lan(hard_lock=False)
        self.assertFalse(access.lan_locked)
        self.assertFalse(access.required("192.168.1.50"))
        self.assertTrue(access.permitted("192.168.1.50", ""))



    def test_v73_plugin_csp_allows_websockets_for_chatbot(self):
        import plugin
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir()
            md = root / "test.md"
            md.write_text("# Test\n", encoding="utf-8")
            html = plugin.render_preview_page(md, root, anchor_spike=True).decode("utf-8")
            self.assertIn("ws: wss:", html)

    def test_v73_switch_session_loads_jsonl(self):
        import tempfile, sys
        from lantern.pi_chat import LanternBotManager
        from lantern.bot_config import LanternBotConfig
        from lantern.live_markdown import LiveMarkdownStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            root.mkdir()
            sdir = Path(tmp) / "sessions"
            sdir.mkdir()
            f1 = sdir / "session-aaa.jsonl"
            f1.write_text('{"type": "message", "sessionId": "session-aaa", "message": {"role": "user", "content": "Question 1"}}\n{"type": "message", "sessionId": "session-aaa", "message": {"role": "assistant", "content": "Answer 1"}}\n', encoding="utf-8")

            fake_pi = root / "fake_pi.py"
            fake_pi.write_text(
                "import sys, json\n"
                "if '--help' in sys.argv:\n"
                "    print('Usage: pi --mode --session --session-dir', flush=True)\n"
                "    sys.exit(0)\n"
                "while True:\n"
                "    line = sys.stdin.readline()\n"
                "    if not line:\n"
                "        break\n"
                "    line = line.strip()\n"
                "    if not line:\n"
                "        continue\n"
                "    try:\n"
                "        data = json.loads(line)\n"
                "        req_id = data.get('id')\n"
                "        if data.get('type') == 'get_state':\n"
                "            print(json.dumps({'type': 'response', 'id': req_id, 'success': True, 'data': {'sessionId': 'session-aaa', 'sessionFile': 'session-aaa.jsonl', 'model': {'provider': 'fake', 'id': 'm1'}}}), flush=True)\n"
                "        else:\n"
                "            print(json.dumps({'type': 'response', 'id': req_id, 'success': True, 'data': {}}), flush=True)\n"
                "    except Exception:\n"
                "        pass\n",
                encoding="utf-8",
            )
            cfg = LanternBotConfig.from_mapping({})
            mgr = LanternBotManager(
                root,
                lambda e: None,
                argv_override=[sys.executable, str(fake_pi)],
                bot_config=cfg,
                session_dir=sdir,
                work_store=LiveMarkdownStore(root, Path(tmp) / "work", {".md"}),
            )
            try:
                res = mgr.switch_session(str(f1))
                self.assertEqual(res.get("sessionId"), "session-aaa")
                msgs = mgr.get_messages()
                self.assertEqual(len(msgs), 2)
                self.assertIn("Question 1", str(msgs[0]))
            finally:
                mgr.close()



    def test_v74_multi_session_isolation_and_popout_and_smart_scroll(self):
        """Verify v7.4 upgrades:
        1. Multi-session / multi-tab isolation (get_session_bot + WebSocketHub clientSessionId routing).
        2. Switching session in Tab 2 does not overwrite or kill Tab 1's active session.
        3. Standalone Pop-out route (/chat) and BroadcastChannel context sync.
        4. Smart Auto-Scroll (isUserScrolledUp) and grouped live tool card (ensureStreamingToolCard) in chatbot.js.
        """
        import tempfile, sys
        from lantern.pi_chat import LanternBotManager
        from lantern.bot_config import LanternBotConfig
        from lantern.live_markdown import LiveMarkdownStore
        from lantern.ws import WebSocketHub, dispatch

        # Check frontend v7.4 features in static/chatbot.js
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        self.assertIn("function ensureStreamingToolCard()", chat_js)
        self.assertIn("function scrollTranscriptToBottom(force = false)", chat_js)
        self.assertIn("isUserScrolledUp = dist > 48", chat_js)
        self.assertIn("BroadcastChannel('lantern_chat_context_v74')", chat_js)
        self.assertIn('id="lcPopoutBtn"', chat_js)
        self.assertIn("loadTabCache()", chat_js)
        self.assertIn("lastTranscriptFingerprint", chat_js)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            sdir = Path(tmp) / "sessions"
            sdir.mkdir()
            saved_sess = sdir / "saved-folder-b.jsonl"
            saved_sess.write_text(
                '{"type": "session", "version": 3, "id": "saved-folder-b", "lantern": true}\n'
                '{"type": "message", "id": "m1", "parentId": null, "sessionId": "saved-folder-b", "message": {"role": "user", "content": "Hello Folder B"}}\n'
                '{"type": "message", "id": "m2", "parentId": "m1", "sessionId": "saved-folder-b", "message": {"role": "assistant", "content": "Reply Folder B"}}\n',
                encoding="utf-8",
            )

            fake_pi = root / "fake_pi_v74.py"
            fake_pi.write_text(
                "import sys, json, uuid\n"
                "sid = 'sid-' + uuid.uuid4().hex[:6]\n"
                "msgs = []\n"
                "if '--help' in sys.argv:\n"
                "    print('Usage: pi --mode --session --session-dir', flush=True)\n"
                "    sys.exit(0)\n"
                "while True:\n"
                "    line = sys.stdin.readline()\n"
                "    if not line:\n"
                "        break\n"
                "    line = line.strip()\n"
                "    if not line:\n"
                "        continue\n"
                "    try:\n"
                "        req = json.loads(line)\n"
                "        rid = req.get('id')\n"
                "        typ = req.get('type')\n"
                "        if typ == 'get_state':\n"
                "            print(json.dumps({'type': 'response', 'id': rid, 'success': True, 'data': {'sessionId': sid, 'model': {'provider': 'fake', 'id': 'gpt-6.1'}}}), flush=True)\n"
                "        elif typ == 'get_available_models':\n"
                "            print(json.dumps({'type': 'response', 'id': rid, 'success': True, 'data': {'models': [{'provider': 'fake', 'id': 'gpt-6.1'}]}}), flush=True)\n"
                "        elif typ == 'get_messages':\n"
                "            print(json.dumps({'type': 'response', 'id': rid, 'success': True, 'data': {'messages': msgs}}), flush=True)\n"
                "        elif typ == 'prompt':\n"
                "            txt = req.get('message', '')\n"
                "            msgs.append({'role': 'user', 'content': txt})\n"
                "            print(json.dumps({'type': 'response', 'id': rid, 'success': True}), flush=True)\n"
                "            ans = 'ANS:' + txt[-20:]\n"
                "            msgs.append({'role': 'assistant', 'content': ans})\n"
                "            print(json.dumps({'type': 'message_end', 'message': {'role': 'assistant', 'content': ans, 'stopReason': 'stop'}}), flush=True)\n"
                "            print(json.dumps({'type': 'agent_settled'}), flush=True)\n"
                "        else:\n"
                "            print(json.dumps({'type': 'response', 'id': rid, 'success': True, 'data': {}}), flush=True)\n"
                "    except Exception:\n"
                "        pass\n",
                encoding="utf-8",
            )

            hub = WebSocketHub()
            work_store = LiveMarkdownStore(root, Path(tmp) / "work", {".md"})
            root_bot = LanternBotManager(
                root,
                hub.broadcast,
                work_store=work_store,
                session_dir=sdir,
                argv_override=[sys.executable, str(fake_pi)],
                bot_config=LanternBotConfig.from_mapping({}),
            )

            class DummyPeer:
                def __init__(self, name: str):
                    self.name = name
                    self.client_ip = "127.0.0.1"
                    self.inbox = []
                    self.subscriptions = set()
                    self.protocol = "v2"
                def can_terminal(self):
                    return True
                def send(self, payload):
                    self.inbox.append(payload)
                def close(self):
                    pass

            peer_a = DummyPeer("tab_A")
            peer_b = DummyPeer("tab_B")
            hub.add(peer_a)
            hub.add(peer_b)

            try:
                # Tab A syncs with clientSessionId='tab-A'
                dispatch(peer_a, {"type": "chat_sync", "clientSessionId": "tab-A"}, None, None, hub=hub, chat=root_bot)
                # Tab B syncs with clientSessionId='tab-B'
                dispatch(peer_b, {"type": "chat_sync", "clientSessionId": "tab-B"}, None, None, hub=hub, chat=root_bot)

                bot_a = root_bot.get_session_bot("tab-A")
                bot_b = root_bot.get_session_bot("tab-B")
                self.assertIsNot(bot_a, bot_b)

                peer_a.inbox.clear()
                peer_b.inbox.clear()

                # Tab A sends prompt in Folder A
                dispatch(
                    peer_a,
                    {"type": "chat_prompt", "clientSessionId": "tab-A", "message": "Prompt from Folder A", "reqId": "rA"},
                    None, None, hub=hub, chat=root_bot,
                )
                import time
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline and not any(m.get("type") == "chat_bot_event" for m in peer_a.inbox):
                    time.sleep(0.02)

                # Verify Tab A received streaming events, while Tab B received ZERO events from Tab A!
                self.assertTrue(any(m.get("type") == "chat_bot_event" for m in peer_a.inbox))
                self.assertFalse(any(m.get("type") == "chat_bot_event" for m in peer_b.inbox))

                # Tab B switches session to saved-folder-b.jsonl
                dispatch(
                    peer_b,
                    {"type": "chat_switch_session", "clientSessionId": "tab-B", "sessionPath": str(saved_sess)},
                    None, None, hub=hub, chat=root_bot,
                )
                b_msgs = bot_b.get_messages()
                self.assertEqual(len(b_msgs), 2)
                self.assertIn("Hello Folder B", str(b_msgs[0]))

                # Verify Tab A's messages and process were NOT overwritten by Tab B's session switch!
                a_msgs = bot_a.get_messages()
                self.assertTrue(any("Prompt from Folder A" in str(m) for m in a_msgs))
                self.assertFalse(any("Hello Folder B" in str(m) for m in a_msgs))
            finally:
                root_bot.close()


    def test_v75_version_diff_image_audit_overwrite_undo_and_lan_isolation(self):
        """Verify all v7.5 upgrades:
        1. Version Diff snapshots on save (no duplicate on unchanged save) + restore_version into real .md.
        2. Image audit (missing vs unreferenced images).
        3. Image overwrite backup + undo in CropService.
        4. Lanbot checkpoint fork (upto_index), session rename, skill preamble cleanup, and Localhost vs LAN isolation.
        5. Non-Markdown preview pages include Lanbot assets and data-lantern-chat-path.
        """
        from lantern.live_markdown import LiveMarkdownStore
        from lantern.http.routes.markdown import MarkdownRoutes
        from lantern.filesystem import FileService
        from lantern.config import AppConfig
        from lantern.crop import CropService
        import plugin
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir(parents=True, exist_ok=True)
            from lantern.live_markdown import LiveMarkdownStore
            work_dir = Path(tmp) / "work"
            store = LiveMarkdownStore(root, work_dir, {".md", ".markdown"})

            md_file = root / "doc.md"
            (root / "assets").mkdir()
            valid_img = root / "assets" / "valid.png"
            unused_img = root / "assets" / "unused.png"
            png_bytes_1 = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"A" * 32
            png_bytes_2 = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"B" * 32
            valid_img.write_bytes(png_bytes_1)
            unused_img.write_bytes(png_bytes_1)

            md_file.write_text("# V1\n\n![ok](assets/valid.png)\n![missing](assets/ghost.png)\n", encoding="utf-8")

            # 1. Version Diff: initial baseline + save v2 + duplicate save check + restore v1
            s1 = store.get("doc.md")
            v1_hash = s1["saved"]["version"]

            w_res = store.write("doc.md", "# V2 Edited\n\n![ok](assets/valid.png)\n", expect_hash=None, base_version=v1_hash)
            save_res1 = store.save("doc.md", expect_hash=w_res["hash"], expect_saved_version=v1_hash)
            v2_hash = save_res1["version"]
            self.assertEqual(len(store.list_versions("doc.md")["versions"]), 2)

            # Saving again with no content change must NOT create a duplicate version
            save_res2 = store.save("doc.md", expect_hash=None, expect_saved_version=v2_hash)
            self.assertEqual(len(store.list_versions("doc.md")["versions"]), 2)

            vlist = store.list_versions("doc.md")
            self.assertEqual(len(vlist["versions"]), 2)
            self.assertTrue(any(g["dateLabel"] == "Today" for g in vlist["groups"]))

            # Restore V1: writes V1 into real .md while leaving md_temp at V2 so live diff triggers immediately
            restored = store.restore_version("doc.md", version_hash=v1_hash)
            self.assertEqual(restored["state"], "pending")
            self.assertEqual(restored["saved"]["version"], v2_hash)
            self.assertEqual(restored["currentVersion"], v1_hash)
            self.assertIn("# V1", md_file.read_text(encoding="utf-8"))

            # 2. Image Audit helper check
            refs = MarkdownRoutes._extract_markdown_image_refs(md_file.read_text(encoding="utf-8"))
            self.assertEqual(refs, ["assets/valid.png", "assets/ghost.png"])

            # 3. CropService Overwrite Backup + Undo
            cfg = AppConfig(root=root, port=0, host="127.0.0.1", title="Test", cache_dir=Path(tmp)/"cache", config_path=Path(tmp)/"cfg.yaml")
            fsvc = FileService(cfg, plugin)
            crop = CropService(fsvc)
            self.assertFalse(crop.has_backup(valid_img))
            crop.save_backup(valid_img, png_bytes_1)
            valid_img.write_bytes(png_bytes_2)
            self.assertTrue(crop.has_backup(valid_img))
            restored_bytes = crop.pop_backup(valid_img)
            self.assertEqual(restored_bytes, png_bytes_1)
            self.assertFalse(crop.has_backup(valid_img))

            # 4. Non-Markdown preview page includes Lanbot assets & data-lantern-chat-path
            py_file = root / "script.py"
            py_file.write_text("print('hello')\n", encoding="utf-8")
            py_html = plugin.render_preview_page(py_file, root).decode("utf-8")
            self.assertIn('/static/chatbot.js', py_html)
            self.assertIn('/static/chatbot.css', py_html)
            self.assertIn('data-lantern-chat-kind="file"', py_html)
            self.assertIn('data-lantern-chat-path="script.py"', py_html)

            # 5. Lanbot Checkpoint Fork, Session Rename, Skill Preamble Cleanup, and LAN vs Localhost Isolation
            sdir = Path(tmp) / "pi_sessions"
            sdir.mkdir(parents=True, exist_ok=True)
            fake_pi = Path(__file__).with_name("fake_pi_rpc.py")
            bot = LanternBotManager(
                root,
                lambda _e: None,
                work_store=store,
                session_dir=sdir,
                argv_override=[sys.executable, "-u", str(fake_pi)],
                bot_config=LanternBotConfig.from_mapping({}),
            )
            try:
                # Skill preamble cleanup check
                cleaned = bot._clean_user_preview_text(
                    "<user_request>\nTrước khi thực hiện, hãy đọc skill liên quan trong: C:\\Users\\demo\\skills\\my-workflow\\SKILL.md\nHãy kiểm tra bảng 1\n</user_request>"
                )
                self.assertEqual(cleaned, "[my-workflow] Hãy kiểm tra bảng 1")

                # Seed 4 messages (2 turns) in a session and fork after index 1 (turn #1)
                wf_sess = sdir / "workflow-root.jsonl"
                wf_lines = [
                    json.dumps({"type": "session", "version": 3, "id": "workflow-root", "cwd": str(root), "lantern": True}),
                    json.dumps({"type": "message", "id": "m1", "parentId": None, "sessionId": "workflow-root", "role": "user", "message": {"role": "user", "content": "Load workflow X"}}),
                    json.dumps({"type": "message", "id": "m2", "parentId": "m1", "sessionId": "workflow-root", "role": "assistant", "message": {"role": "assistant", "content": "Workflow X loaded and ready."}}),
                    json.dumps({"type": "message", "id": "m3", "parentId": "m2", "sessionId": "workflow-root", "role": "user", "message": {"role": "user", "content": "Edit file 1"}}),
                    json.dumps({"type": "message", "id": "m4", "parentId": "m3", "sessionId": "workflow-root", "role": "assistant", "message": {"role": "assistant", "content": "Edited file 1."}}),
                ]
                wf_sess.write_text("\n".join(wf_lines) + "\n", encoding="utf-8")

                tab2 = bot.get_session_bot("tab-2", scope="local")
                fork_state = tab2.fork_session(
                    "local",
                    upto_index=1,
                    source_session_path=str(wf_sess),
                    custom_name="Tab 2 - File 2 Branch",
                )
                fork_msgs = tab2.get_messages()
                self.assertEqual(len(fork_msgs), 2)
                self.assertIn("Workflow X loaded", str(fork_msgs[1]))
                self.assertNotIn("Edit file 1", str(fork_msgs))

                # Verify custom session name appears in list_sessions(scope="local")
                local_sessions = tab2.list_sessions(scope="local")
                self.assertTrue(any(s.get("name") == "Tab 2 - File 2 Branch" for s in local_sessions))

                # Verify LAN scope is isolated and does NOT see localhost sessions
                lan_bot = bot.get_session_bot("lan-tab-1", scope="lan")
                self.assertNotEqual(lan_bot.session_dir, tab2.session_dir)
                self.assertNotEqual(lan_bot.bot_cwd, tab2.bot_cwd)
                self.assertEqual(lan_bot.list_sessions(scope="lan"), [])
            finally:
                bot.close()

    def test_v76_session_switch_version_dedup_non_md_context_and_reset_bot(self):
        """Verify all v7.6 fixes:
        1. ws.dispatch chat_list_sessions does not raise UnboundLocalError for scope, and chat_reset_bot works.
        2. Version deduplication on Save: restoring older version B and pressing Save promotes B to C and removes old B.
        3. Old session switching hydrates conversation history and responds cleanly to prompts.
        4. Context: ON in non-.md files populates logicalPath and workingPath.
        5. Markdown top bar has Terminal button (#mdTerminalBtn), removes CPU/RAM pill, renames Version Diff -> Version, and Settings has Reset Lanbot (#lcResetBotBtn).
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            work_dir = Path(tmp) / "work"
            store = LiveMarkdownStore(root, work_dir, {".md", ".markdown"})

            # 1. Version deduplication when restoring an older version B and saving as C
            md_file = root / "doc.md"
            md_file.write_text("# Version B (11h52)\nOriginal text.\n", encoding="utf-8")
            st0 = store.get("doc.md")
            v_b_hash = st0["saved"]["version"]

            store.write("doc.md", "# Version A (11h59)\nModified text.\n", expect_hash=None, base_version=v_b_hash)
            saved_a = store.save("doc.md", expect_hash=store.get("doc.md")["currentVersion"], expect_saved_version=v_b_hash)
            v_a_hash = saved_a["version"]
            self.assertEqual(len(store.list_versions("doc.md")["versions"]), 2)

            # Now user selects older version B (11h52) and presses Save (Ctrl+S) -> becomes C (12h01)
            store.restore_version("doc.md", version_hash=v_b_hash)
            st_restored = store.get("doc.md")
            saved_c = store.save("doc.md", expect_hash=st_restored["currentVersion"], expect_saved_version=v_a_hash)
            self.assertEqual(saved_c["version"], v_b_hash)

            v_list = store.list_versions("doc.md")["versions"]
            # B and C have the same content hash; old B must be removed so only C (Current/Saved) and A remain!
            self.assertEqual(len(v_list), 2)
            self.assertEqual(v_list[0]["version"], v_b_hash)
            self.assertTrue(v_list[0]["isCurrent"] and v_list[0]["isBaseline"])
            self.assertEqual(v_list[1]["version"], v_a_hash)
            self.assertFalse(v_list[1]["isCurrent"] or v_list[1]["isBaseline"])

            # 2. Old session switching + hydration + non-.md Context: ON + Reset Lanbot via ws.dispatch
            py_script = root / "app.py"
            py_script.write_text("def hello():\n    return 42\n", encoding="utf-8")

            sdir = Path(tmp) / "pi_sessions"
            sdir.mkdir(parents=True, exist_ok=True)
            old_sess = sdir / "old-session-1.jsonl"
            old_sess.write_text(
                json.dumps({"type": "session", "version": 3, "id": "old-session-1", "cwd": str(root), "lantern": True}) + "\n"
                + json.dumps({"type": "message", "id": "m1", "parentId": None, "sessionId": "old-session-1", "role": "user", "message": {"role": "user", "content": "<user_request>\nRemember code word ALPHA-99\n</user_request>"}}) + "\n"
                + json.dumps({"type": "message", "id": "m2", "parentId": "m1", "sessionId": "old-session-1", "role": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "I will remember ALPHA-99."}]}}) + "\n",
                encoding="utf-8",
            )

            fake_pi = Path(__file__).with_name("fake_pi_rpc.py")
            bot = LanternBotManager(
                root,
                lambda _e: None,
                work_store=store,
                session_dir=sdir,
                argv_override=[sys.executable, "-u", str(fake_pi)],
                bot_config=LanternBotConfig.from_mapping({}),
            )
            try:
                from lantern.ws import dispatch

                class DummyPeer:
                    def __init__(self):
                        self.client_ip = "127.0.0.1"
                        self.sent = []
                    def can_terminal(self):
                        return True
                    def send(self, payload):
                        self.sent.append(payload)

                peer = DummyPeer()
                # Verify chat_list_sessions does not raise UnboundLocalError: scope
                dispatch(peer, {"type": "chat_list_sessions", "clientSessionId": "tab-v76"}, None, None, chat=bot)
                self.assertEqual(peer.sent[-1]["type"], "chat_sessions_list")
                self.assertTrue(any(s["id"] == "old-session-1" for s in peer.sent[-1]["sessions"]))

                # Switch to old-session-1 and send a prompt with non-.md file Context: ON
                dispatch(peer, {"type": "chat_switch_session", "clientSessionId": "tab-v76", "sessionPath": str(old_sess)}, None, None, chat=bot)
                tab_bot = bot.get_session_bot("tab-v76", scope="local")
                self.assertTrue(tab_bot._needs_history_hydration)

                dispatch(
                    peer,
                    {
                        "type": "chat_prompt",
                        "clientSessionId": "tab-v76",
                        "reqId": "r1",
                        "message": "Check this python file",
                        "context": {"kind": "file", "path": "app.py", "line": 1, "selectedText": "def hello():"},
                    },
                    None,
                    None,
                    chat=bot,
                )
                self.assertEqual(peer.sent[-1]["type"], "chat_prompt_accepted")
                self.assertFalse(tab_bot._needs_history_hydration)
                # Verify last user message stored in session has logicalPath and workingPath for non-.md file
                user_msgs = [m for m in tab_bot._session_messages if m.get("role") == "user"]
                self.assertIn("logicalPath: app.py", str(user_msgs[-1].get("content", "")))
                self.assertIn("workingPath:", str(user_msgs[-1].get("content", "")))

                # Verify conversation token estimation uses latest_reported + trailing_chars // 4 (v7.7)
                tab_bot._session_messages = [
                    {"role": "user", "content": "<lantern_context>\nkind: markdown\n</lantern_context>\n\n<user_request>\nhi\n</user_request>"},
                    {"role": "assistant", "content": [{"type": "text", "text": "Hi! What would you like to work on in lantern/README.md?"}], "usage": {"totalTokens": 11259}},
                ]
                est_tokens = tab_bot._estimate_session_tokens()
                self.assertEqual(est_tokens, 11259)

                # Verify chat_reset_bot clears stuck locks, sends chat_bot_reset WITHOUT history first, then chat_history_page
                store.turns["stale_lock_id"] = "deadbeef"
                peer.sent.clear()
                dispatch(peer, {"type": "chat_reset_bot", "clientSessionId": "tab-v76"}, None, None, chat=bot)
                self.assertTrue(any(m.get("type") == "chat_bot_reset" and "messages" not in m for m in peer.sent))
                self.assertTrue(any(m.get("type") == "chat_history_page" for m in peer.sent))
                self.assertEqual(len(store.turns), 0)

                # Verify chat_delete_session deletes old-session-1
                dispatch(peer, {"type": "chat_delete_session", "clientSessionId": "tab-v76", "sessionId": "old-session-1", "sessionPath": str(old_sess)}, None, None, chat=bot)
                self.assertEqual(peer.sent[-1]["type"], "chat_sessions_list")
                self.assertFalse(old_sess.exists())
            finally:
                bot.close()

            # 3. Verify static JS & CSS updates
            shell_js = (Path(__file__).resolve().parents[1] / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
            self.assertNotIn("mdSysTelemetryPill", shell_js)
            self.assertIn("mdTerminalBtn", shell_js)
            self.assertIn("🕒 Version ▾", shell_js)
            self.assertNotIn("🕒 Version Diff ▾", shell_js)

            chat_js = (Path(__file__).resolve().parents[1] / "static" / "chatbot.js").read_text(encoding="utf-8")
            self.assertIn("isSelectionInsideChatDrawer", chat_js)
            self.assertIn("lcResetBotBtn", chat_js)
            self.assertIn("chat_reset_bot", chat_js)
            self.assertIn("chat_delete_session", chat_js)
            self.assertIn("ensureStreamingTurnCard", chat_js)

            chat_css = (Path(__file__).resolve().parents[1] / "static" / "chatbot.css").read_text(encoding="utf-8")
            self.assertIn("flex-shrink: 0;", chat_css)


    def test_v77_decoupled_sync_paginated_history_tool_preview_and_msg_menu(self):
        """Verify all v7.7 architectural fixes:
        1. Decoupled chat_sync(separateHistory=True): sends chat_state (runtime + provider/model, NO messages)
           independently of chat_history_page, so a huge 23 MB history never blocks provider/model initialization
           or exceeds the 8 MiB WebSocket limit.
        2. Paginated history (get_messages_page) with message count + byte limits, 'Load older messages'
           (chat_load_history), and non-destructive tool output preview (truncated=True + get_tool_output_full)
           that NEVER mutates original session data.
        3. Per-message '...' dropdown menu (Raw, Copy, Fork, Re-run on assistant only) & chat_rerun handler.
        4. Folder-view attachment chip fix in captureContext() and explicit Reset timeout / bounded reconnects.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            work_dir = Path(tmp) / "work"
            store = LiveMarkdownStore(root, work_dir, {".md", ".markdown"})
            sdir = Path(tmp) / "pi_sessions"
            sdir.mkdir(parents=True, exist_ok=True)

            fake_pi = Path(__file__).with_name("fake_pi_rpc.py")
            bot = LanternBotManager(
                root,
                lambda _e: None,
                work_store=store,
                session_dir=sdir,
                argv_override=[sys.executable, "-u", str(fake_pi)],
                bot_config=LanternBotConfig.from_mapping({}),
            )
            try:
                from lantern.ws import dispatch
                tab_bot = bot.get_session_bot("tab-v77", scope="local")

                # Populate 40 messages including a massive 50 KB tool output
                huge_tool_output = "LINE_DATA_0123456789\n" * 2600  # ~54 KB
                msgs = []
                for i in range(19):
                    msgs.append({"role": "user", "content": f"User question #{i+1}"})
                    msgs.append({"role": "assistant", "content": [{"type": "text", "text": f"Assistant answer #{i+1}"}]})
                msgs.append({"role": "user", "content": "Run big tool"})
                msgs.append({
                    "role": "assistant",
                    "content": [
                        {"type": "toolCall", "id": "tc-big", "name": "bash", "arguments": {"cmd": "cat huge.log"}},
                        {"type": "toolResult", "toolUseId": "tc-big", "toolName": "bash", "content": huge_tool_output},
                        {"type": "text", "text": "Here is the summary of huge.log."},
                    ],
                })
                tab_bot._session_messages = msgs

                class DummyPeer:
                    def __init__(self):
                        self.client_ip = "127.0.0.1"
                        self.sent = []
                    def can_terminal(self):
                        return True
                    def send(self, payload):
                        self.sent.append(payload)

                peer = DummyPeer()
                # 1. Decoupled chat_sync with separateHistory=True
                dispatch(
                    peer,
                    {"type": "chat_sync", "clientSessionId": "tab-v77", "separateHistory": True, "historyLimit": 10},
                    None, None, chat=bot,
                )
                self.assertGreaterEqual(len(peer.sent), 2)
                state_pkt = peer.sent[0]
                hist_pkt = peer.sent[1]
                self.assertEqual(state_pkt["type"], "chat_state")
                self.assertTrue(state_pkt.get("historySeparate"))
                self.assertNotIn("messages", state_pkt)
                self.assertTrue(state_pkt.get("models"))

                # 2. Verify paginated history & non-destructive tool output preview
                self.assertEqual(hist_pkt["type"], "chat_history_page")
                self.assertTrue(hist_pkt["hasMoreOlder"])
                self.assertEqual(hist_pkt["totalMessages"], 40)
                self.assertEqual(len(hist_pkt["messages"]), 10)
                self.assertEqual(hist_pkt["oldestIndex"], 30)

                last_msg_transport = hist_pkt["messages"][-1]
                tool_res_item = [c for c in last_msg_transport["toolCalls"] if "result" in c][0]
                self.assertTrue(tool_res_item.get("truncated"))
                self.assertEqual(tool_res_item.get("fullLength"), len(huge_tool_output))
                self.assertLess(len(tool_res_item.get("result", "")), 2000)

                # Original _session_messages MUST NOT be mutated or truncated!
                orig_tool_res = [c for c in tab_bot._session_messages[-1]["content"] if c.get("type") == "toolResult"][0]
                self.assertEqual(orig_tool_res["content"], huge_tool_output)
                self.assertFalse(orig_tool_res.get("truncated", False))

                # Full tool output retrieval on demand (tool index 1 has the toolResult)
                full_res = tab_bot.get_tool_output_full(39, int(tool_res_item.get("toolIndex", 1)))
                self.assertTrue(full_res["ok"])
                self.assertEqual(full_res["content"], huge_tool_output)

                # Load older messages page
                peer.sent.clear()
                dispatch(
                    peer,
                    {"type": "chat_load_history", "clientSessionId": "tab-v77", "beforeIndex": 30, "limit": 15},
                    None, None, chat=bot,
                )
                older_pkt = peer.sent[-1]
                self.assertEqual(older_pkt["type"], "chat_history_page")
                self.assertTrue(older_pkt["prepend"])
                self.assertEqual(len(older_pkt["messages"]), 15)
                self.assertEqual(older_pkt["oldestIndex"], 15)
                self.assertTrue(older_pkt["hasMoreOlder"])

                # 3. Verify Re-run from assistant turn
                peer.sent.clear()
                dispatch(
                    peer,
                    {
                        "type": "chat_rerun",
                        "clientSessionId": "tab-v77",
                        "reqId": "rerun-1",
                        "turnIndex": 38,
                        "message": "Run big tool again",
                        "context": {},
                    },
                    None, None, chat=bot,
                )
                self.assertEqual(peer.sent[-1]["type"], "chat_prompt_accepted")
                self.assertTrue( peer.sent[-1].get("rerun"))
            finally:
                bot.close()

            chat_js = (Path(__file__).resolve().parents[1] / "static" / "chatbot.js").read_text(encoding="utf-8")
            self.assertIn("lc-msg-more-btn", chat_js)
            self.assertIn("lc-msg-rerun-btn", chat_js)
            self.assertIn("lc-load-older-btn", chat_js)
            self.assertIn("lc-tool-load-full-btn", chat_js)
            self.assertIn("/api/chatbot/reset", chat_js)
            self.assertIn("MAX_RECONNECT_ATTEMPTS", chat_js)



class DummySharedPeer:
    def __init__(self, client_ip: str = "127.0.0.1", cid: str = ""):
        self.client_ip = client_ip
        self.chat_session_id = cid
        self.inbox: list[dict] = []
        self.subscriptions: set[str] = set()
        self.protocol = "v2"

    def can_terminal(self) -> bool:
        return True

    def send(self, payload: dict) -> None:
        self.inbox.append(payload)

    def close(self) -> None:
        pass


class SharedSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_dir = Path(self.tmp.name) / "work"
        self.session_dir = Path(self.tmp.name) / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.store = LiveMarkdownStore(self.root, self.work_dir, {".md", ".markdown"})
        self.fake_pi = Path(__file__).with_name("fake_pi_rpc.py")
        from lantern.ws import WebSocketHub
        self.hub = WebSocketHub()
        self.bot_config = LanternBotConfig.from_mapping({
            "access": {
                "localhost": {
                    "provider_mode": "all",
                    "model_mode": "all",
                    "tools": ["*"],
                },
                "lan": {
                    "provider_mode": "whitelist",
                    "providers": ["fake"],
                    "model_mode": "whitelist",
                    "models": ["fake/claude-*"],
                    "tools": ["read", "grep", "find", "ls"],
                },
            }
        })
        import sys
        self.root_bot = LanternBotManager(
            self.root,
            self.hub.broadcast,
            work_store=self.store,
            session_dir=self.session_dir,
            argv_override=[sys.executable, "-u", str(self.fake_pi)],
            bot_config=self.bot_config,
            usage_path=Path(self.tmp.name) / "usage.json",
        )
        self.hub.chat = self.root_bot

    def tearDown(self) -> None:
        self.root_bot.close()
        self.tmp.cleanup()

    def _seed_session(self, sdir: Path, sid: str, user_msg: str, assistant_msg: str, cwd: Path) -> Path:
        sdir.mkdir(parents=True, exist_ok=True)
        fp = sdir / f"{sid}.jsonl"
        lines = [
            json.dumps({"type": "session", "version": 3, "id": sid, "cwd": str(cwd), "lantern": True}),
            json.dumps({"type": "message", "id": "m1", "parentId": None, "sessionId": sid, "role": "user", "message": {"role": "user", "content": user_msg}}),
            json.dumps({"type": "message", "id": "m2", "parentId": "m1", "sessionId": sid, "role": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": assistant_msg}]}}),
        ]
        fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return fp

    def test_v78_share_and_unshare_visibility_for_lan(self) -> None:
        self._seed_session(self.session_dir, "local-s1", "Local secret task", "Done", self.root)
        lan_list_before = self.root_bot.list_sessions("lan")
        self.assertFalse(any(s["id"] == "local-s1" for s in lan_list_before))

        res = self.root_bot.set_session_shared("local-s1", True)
        self.assertTrue(res["shared"])
        lan_list_after = self.root_bot.list_sessions("lan")
        shared_entry = next((s for s in lan_list_after if s["id"] == "local-s1"), None)
        self.assertIsNotNone(shared_entry)
        self.assertTrue(shared_entry["shared"])
        self.assertEqual(shared_entry["sessionScope"], "local")

        self.root_bot.set_session_shared("local-s1", False)
        lan_list_unshared = self.root_bot.list_sessions("lan")
        self.assertFalse(any(s["id"] == "local-s1" for s in lan_list_unshared))

    def test_v78_host_and_lan_receive_same_manager_and_host_leaving_does_not_switch_guest(self) -> None:
        from lantern.ws import dispatch
        f_shared = self._seed_session(self.session_dir, "shared-main", "Hello shared", "Hi shared", self.root)
        f_other = self._seed_session(self.session_dir, "local-other", "Other local", "Hi other", self.root)

        host_peer = DummySharedPeer("127.0.0.1", "host-tab-1")
        lan_peer = DummySharedPeer("192.168.1.55", "lan-tab-1")
        self.hub.add(host_peer)
        self.hub.add(lan_peer)

        dispatch(host_peer, {"type": "chat_switch_session", "clientSessionId": "host-tab-1", "sessionId": "shared-main", "sessionPath": str(f_shared)}, None, None, hub=self.hub, chat=self.root_bot)
        dispatch(host_peer, {"type": "chat_share_session", "clientSessionId": "host-tab-1", "sessionId": "shared-main", "shared": True}, None, None, hub=self.hub, chat=self.root_bot)
        dispatch(lan_peer, {"type": "chat_switch_session", "clientSessionId": "lan-tab-1", "sessionId": "shared-main"}, None, None, hub=self.hub, chat=self.root_bot)

        host_mgr = self.root_bot.get_session_bot("host-tab-1", scope="local")
        lan_mgr = self.root_bot.get_session_bot("lan-tab-1", scope="lan")
        self.assertIs(host_mgr, lan_mgr)
        self.assertEqual(lan_mgr.current_session_id(), "shared-main")

        dispatch(host_peer, {"type": "chat_switch_session", "clientSessionId": "host-tab-1", "sessionId": "local-other", "sessionPath": str(f_other)}, None, None, hub=self.hub, chat=self.root_bot)
        host_mgr_after = self.root_bot.get_session_bot("host-tab-1", scope="local")
        lan_mgr_after = self.root_bot.get_session_bot("lan-tab-1", scope="lan")
        self.assertIsNot(host_mgr_after, lan_mgr_after)
        self.assertEqual(host_mgr_after.current_session_id(), "local-other")
        self.assertEqual(lan_mgr_after.current_session_id(), "shared-main")
        self.assertIs(lan_mgr_after, lan_mgr)

    def test_v78_guest_prompt_uses_shared_localhost_session_scope_and_broadcasts_to_both_viewers(self) -> None:
        import time
        from lantern.ws import dispatch
        f_shared = self._seed_session(self.session_dir, "shared-work", "Init", "Ready", self.root)
        host_peer = DummySharedPeer("127.0.0.1", "host-1")
        lan_peer = DummySharedPeer("192.168.1.55", "guest-1")
        private_peer = DummySharedPeer("127.0.0.1", "private-tab-2")
        self.hub.add(host_peer)
        self.hub.add(lan_peer)
        self.hub.add(private_peer)

        dispatch(private_peer, {"type": "chat_sync", "clientSessionId": "private-tab-2"}, None, None, hub=self.hub, chat=self.root_bot)
        dispatch(host_peer, {"type": "chat_switch_session", "clientSessionId": "host-1", "sessionId": "shared-work", "sessionPath": str(f_shared)}, None, None, hub=self.hub, chat=self.root_bot)
        dispatch(host_peer, {"type": "chat_share_session", "clientSessionId": "host-1", "sessionId": "shared-work", "shared": True}, None, None, hub=self.hub, chat=self.root_bot)
        dispatch(lan_peer, {"type": "chat_switch_session", "clientSessionId": "guest-1", "sessionId": "shared-work"}, None, None, hub=self.hub, chat=self.root_bot)

        shared_mgr = self.root_bot.get_session_bot("guest-1", scope="lan")
        shared_mgr.set_model("fake", "gpt-6.1-sol", scope="local")

        host_peer.inbox.clear()
        lan_peer.inbox.clear()
        private_peer.inbox.clear()

        dispatch(lan_peer, {"type": "chat_prompt", "clientSessionId": "guest-1", "reqId": "g-req-1", "message": "Hello from guest"}, None, None, hub=self.hub, chat=self.root_bot)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not any(m.get("type") == "chat_bot_event" and m.get("event", {}).get("type") == "agent_settled" for m in host_peer.inbox):
            time.sleep(0.02)

        self.assertTrue(any(m.get("type") == "chat_bot_event" for m in host_peer.inbox))
        self.assertTrue(any(m.get("type") == "chat_bot_event" for m in lan_peer.inbox))
        self.assertFalse(any(m.get("type") == "chat_bot_event" for m in private_peer.inbox))

        dispatch(host_peer, {"type": "chat_share_session", "clientSessionId": "host-1", "sessionId": "shared-work", "shared": False}, None, None, hub=self.hub, chat=self.root_bot)
        lan_peer.inbox.clear()
        dispatch(host_peer, {"type": "chat_prompt", "clientSessionId": "host-1", "reqId": "h-req-2", "message": "Host only after unshare"}, None, None, hub=self.hub, chat=self.root_bot)
        time.sleep(0.25)
        self.assertFalse(any(m.get("type") == "chat_bot_event" for m in lan_peer.inbox))

    def test_v78_registry_reload_and_localhost_sees_lan_sessions_without_losing_local_sessions(self) -> None:
        import sys
        from lantern.ws import dispatch
        f_local = self._seed_session(self.session_dir, "host-own-1", "Host task", "Host reply", self.root)
        lan_sdir = self.session_dir / "lan"
        f_lan = self._seed_session(lan_sdir, "lan-guest-s1", "LAN question", "LAN answer", self.root / ".lantern" / "lan_workspace")

        self.root_bot.set_session_shared("host-own-1", True, session_path=str(f_local))
        reloaded_bot = LanternBotManager(
            self.root,
            lambda _e: None,
            work_store=self.store,
            session_dir=self.session_dir,
            argv_override=[sys.executable, "-u", str(self.fake_pi)],
            bot_config=self.bot_config,
        )
        try:
            self.assertIn("host-own-1", reloaded_bot.shared_sessions())
            shared_mgr = reloaded_bot.select_shared_session("guest-reload", "lan", "host-own-1")
            self.assertIsNotNone(shared_mgr)
            self.assertEqual(len(shared_mgr.get_messages()), 2)
        finally:
            reloaded_bot.close()

        local_sessions = self.root_bot.list_sessions("local")
        local_ids = {s["id"]: s for s in local_sessions}
        self.assertIn("host-own-1", local_ids)
        self.assertIn("lan-guest-s1", local_ids)
        self.assertTrue(local_ids["lan-guest-s1"]["label"].startswith("[Lan]-"))
        self.assertEqual(local_ids["lan-guest-s1"]["sessionScope"], "lan")
        self.assertFalse(local_ids["lan-guest-s1"]["shared"])

        host_peer = DummySharedPeer("127.0.0.1", "host-viewer")
        dispatch(host_peer, {"type": "chat_switch_session", "clientSessionId": "host-viewer", "sessionId": "lan-guest-s1", "sessionPath": str(f_lan), "sessionScope": "lan"}, None, None, hub=self.hub, chat=self.root_bot)
        switch_pkt = host_peer.inbox[-1]
        self.assertEqual(switch_pkt["type"], "chat_state")
        session_ids_after_switch = {s["id"] for s in switch_pkt["sessions"]}
        self.assertIn("host-own-1", session_ids_after_switch)
        self.assertIn("lan-guest-s1", session_ids_after_switch)

        host_peer.inbox.clear()
        dispatch(host_peer, {"type": "chat_rename_session", "clientSessionId": "host-viewer", "sessionId": "lan-guest-s1", "sessionPath": str(f_lan), "sessionScope": "lan", "name": "Renamed LAN Chat"}, None, None, hub=self.hub, chat=self.root_bot)
        list_pkt = [m for m in host_peer.inbox if m.get("type") == "chat_sessions_list"][-1]
        ids_after_rename = {s["id"]: s for s in list_pkt["sessions"]}
        self.assertIn("host-own-1", ids_after_rename)
        self.assertIn("lan-guest-s1", ids_after_rename)
        self.assertEqual(ids_after_rename["lan-guest-s1"]["label"], "[Lan]-Renamed LAN Chat")

        lan_peer = DummySharedPeer("192.168.1.99", "lan-hacker")
        with self.assertRaises(PermissionError):
            dispatch(lan_peer, {"type": "chat_share_session", "clientSessionId": "lan-hacker", "sessionId": "host-own-1", "shared": True}, None, None, hub=self.hub, chat=self.root_bot)


class LanternV79HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        import sys
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "project"
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_dir = self.base / "work"
        self.session_dir = self.base / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.store = LiveMarkdownStore(self.root, self.work_dir, {".md", ".markdown"})
        self.fake_pi = Path(__file__).with_name("fake_pi_rpc.py").resolve()
        self.events: list[dict] = []
        self.bot = LanternBotManager(
            self.root,
            self.events.append,
            work_store=self.store,
            session_dir=self.session_dir,
            argv_override=[sys.executable, "-u", str(self.fake_pi)],
            bot_config=LanternBotConfig.from_mapping({
                "enabled": True,
                "access": {
                    "localhost": {"tools": ["*"], "extensions": True, "mcp": True},
                    "lan": {"tools": ["read", "grep", "find", "ls"], "extensions": False, "mcp": False},
                },
            }),
        )

    def tearDown(self) -> None:
        self.bot.close()
        self.tmp.cleanup()

    def test_v79_scroll_bottom_button_and_zero_tug_of_war_contracts(self) -> None:
        css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        # 1. Transcript uses scroll-behavior: auto (not smooth) and overflow-anchor: none on streaming cards
        self.assertIn("scroll-behavior: auto;", css)
        self.assertIn(".lc-msg.streaming", css)
        self.assertIn("overflow-anchor: none;", css)
        # 2. Floating Scroll-to-Bottom button exists in CSS and JS
        self.assertIn(".lc-scroll-bottom-btn", css)
        self.assertIn("border-radius: 50%;", css)
        self.assertIn('id="lcScrollBottomBtn"', js)
        self.assertIn("updateScrollBottomButton()", js)
        # 3. Immediate wheel / touch upward intent freezes scroll without fighting
        self.assertIn("els.transcript.addEventListener('wheel'", js)
        self.assertIn("els.transcript.addEventListener('touchmove'", js)
        self.assertIn("jumpToLatestMessage()", js)

    def test_v79_harness_init_and_zero_reload_skill_discovery(self) -> None:
        # Initially no skills
        self.assertEqual(self.bot.discover_skills(), [])
        # Run /harness status
        status_res = self.bot.execute_slash_command("/harness status", scope="local")
        self.assertIsNotNone(status_res)
        self.assertTrue(status_res.get("success"))
        # Run /harness init to scaffold starter skills (.pi/skills/verify-loop, checkpoint, planner)
        init_res = self.bot.execute_slash_command("/harness init", scope="local")
        self.assertIsNotNone(init_res)
        self.assertTrue(init_res.get("success"))
        self.assertEqual(sorted(init_res.get("created", [])), ["/checkpoint", "/planner", "/verify-loop"])
        # Re-running /harness init preserves existing skills without overwriting
        custom_md = self.root / ".pi" / "skills" / "verify-loop" / "SKILL.md"
        custom_md.write_text("---\nname: verify-loop\ndescription: Custom user verify skill\n---\nCustom body\n", encoding="utf-8")
        init_res2 = self.bot.execute_slash_command("/harness init", scope="local")
        self.assertEqual(init_res2.get("created"), [])
        self.assertIn("/verify-loop", init_res2.get("existing", []))
        self.assertIn("Custom user verify skill", custom_md.read_text(encoding="utf-8"))

        # Verify discover_skills extracts descriptions and emits chat_commands_changed
        skills = self.bot.discover_skills()
        by_cmd = {s["command"]: s for s in skills}
        self.assertIn("/verify-loop", by_cmd)
        self.assertIn("/checkpoint", by_cmd)
        self.assertIn("/planner", by_cmd)
        self.assertEqual(by_cmd["/verify-loop"]["description"], "Custom user verify skill")
        self.assertTrue(any(e.get("type") == "chat_commands_changed" for e in self.events))

        # Invoking /verify-loop expands skill prompt and sets _include_context=True
        expanded = self.bot.execute_slash_command("/verify-loop Check unit tests", scope="local")
        self.assertIsNotNone(expanded)
        self.assertIn('<skill_invocation name="verify-loop"', expanded.get("_expanded_prompt", ""))
        self.assertTrue(expanded.get("_include_context"))

    def test_v79_unopened_unattached_markdown_edit_creates_baseline_and_emits_lock(self) -> None:
        unopened = self.root / "unopened_guide.md"
        original_text = "# Original Guide\nBefore bot edit.\n"
        unopened.write_text(original_text, encoding="utf-8")

        # Simulate Pi tool_execution_start targeting unopened_guide.md before any browser open
        self.events.clear()
        self.bot._on_markdown_tool_target("unopened_guide.md", is_write=True)
        # Verify chat_work_locked(locked=True) was emitted and store reports turnActive/botLocked=True
        self.assertTrue(any(
            e.get("type") == "chat_work_locked" and e.get("path") == "unopened_guide.md" and e.get("locked") is True
            for e in self.events
        ))
        mid_state = self.store.get("unopened_guide.md")
        self.assertTrue(mid_state["turnActive"])
        self.assertTrue(mid_state["turnActive"])

        # Simulate bot writing new content to disk during turn
        unopened.write_text("# Updated Guide\nEdited by Lanbot in background.\n", encoding="utf-8")

        # Finish turn: _emit_work_update(final=True) unlocks and emits chat_work_changed
        self.bot._emit_work_update(final=True)
        self.assertTrue(any(
            e.get("type") == "chat_work_locked" and e.get("path") == "unopened_guide.md" and e.get("locked") is False
            for e in self.events
        ))
        self.assertTrue(any(
            e.get("type") == "chat_work_changed" and e.get("path") == "unopened_guide.md" and e.get("final") is True
            for e in self.events
        ))

        # Now user opens unopened_guide.md for the VERY FIRST TIME in Lantern:
        # Baseline (saved) must still be original_text, and work must show the pending diff!
        first_open_state = self.store.get("unopened_guide.md")
        self.assertFalse(first_open_state["turnActive"])
        self.assertFalse(first_open_state["turnActive"])
        self.assertEqual(first_open_state["state"], "pending")
        self.assertEqual(first_open_state["saved"]["content"], original_text)
        self.assertIsNotNone(first_open_state["work"])
        self.assertIn("Edited by Lanbot in background.", first_open_state["work"]["content"])

    def test_v79_skill_context_preservation_and_on_work_locked_frontend_hooks(self) -> None:
        js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        mvs = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        mpe = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        self.assertIn("function isPureAdminSlashCommand(rawText)", js)
        self.assertIn("const isAdminSlash = isPureAdminSlashCommand(text);", js)
        self.assertIn("msg.type === 'chat_work_locked'", js)
        self.assertIn("msg.type === 'chat_commands_changed'", js)
        self.assertIn("const onWorkLocked = (eventPath, locked) =>", mvs)
        self.assertIn("onBotWorkLocked(eventPath, locked)", mpe)


    def test_v791_slash_sync_multi_tab_running_isolation_and_mode_e_fixes(self) -> None:
        from lantern.ws import WebSocketHub, dispatch
        css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        mcss = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        mvs = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        mpe = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")

        # 1. Compact circular arrow-only button & no 🏮 Lanbot / 👤 You inside bubble .lc-msg-head
        self.assertNotIn("↓ Latest", js)
        self.assertNotIn("lc-scroll-bottom-dot", js)
        self.assertNotIn("head.innerHTML = `<span>🏮 Lanbot</span>`", js)
        self.assertNotIn("head.innerHTML = `<span>${msg.role ===", js)
        self.assertIn("triggerLazyLoadOlderHistory()", js)
        self.assertIn("lantern_tab_cid_guard_v791", js)

        # 2. Mode E fixes: sticky pagination bar below --md-bar-height + bottom nav + long table visual support
        self.assertIn("top:var(--md-bar-height,82px);z-index:45", mcss)
        self.assertIn(".md-paged-bottom-nav", mcss)
        self.assertIn("LanternPrepareVisualMarkdown", mvs)
        self.assertIn("syncMdBarHeightVar", mvs)
        self.assertIn("if(p.oversized && (fenceMatch || !hasPipeTable))", mpe)

        # 3. Synchronous /harness command via WebSocket sets slashHandled=True (never leaves UI stuck in Stop/Sending)
        hub = WebSocketHub()
        hub.chat = self.bot
        peer1 = DummySharedPeer("127.0.0.1", "tab-one")
        hub.add(peer1)
        dispatch(
            peer1,
            {"type": "chat_prompt", "clientSessionId": "tab-one", "reqId": "req-h", "message": "/harness status"},
            None, None, hub=hub, chat=self.bot,
        )
        accepted = [m for m in peer1.inbox if m.get("type") == "chat_prompt_accepted"][-1]
        self.assertTrue(accepted.get("slashHandled"))

        # 4. Switching session while a turn is running parks the running bot (does NOT abort and does NOT bleed content)
        s1_file = self.session_dir / "sess-running-1.jsonl"
        s2_file = self.session_dir / "sess-other-2.jsonl"
        s1_file.write_text(
            json.dumps({"type": "session", "version": 3, "id": "sess-running-1", "lantern": True}) + "\n" +
            json.dumps({"type": "message", "id": "u1", "parentId": None, "sessionId": "sess-running-1", "role": "user", "message": {"role": "user", "content": "Task in S1"}}) + "\n",
            encoding="utf-8",
        )
        s2_file.write_text(
            json.dumps({"type": "session", "version": 3, "id": "sess-other-2", "lantern": True}) + "\n" +
            json.dumps({"type": "message", "id": "u2", "parentId": None, "sessionId": "sess-other-2", "role": "user", "message": {"role": "user", "content": "Hello in S2"}}) + "\n",
            encoding="utf-8",
        )
        dispatch(peer1, {"type": "chat_switch_session", "clientSessionId": "tab-one", "sessionId": "sess-running-1", "sessionPath": str(s1_file)}, None, None, hub=hub, chat=self.bot)
        bot_s1 = self.bot.get_session_bot("tab-one", scope="local")
        # Simulate an active streaming turn on bot_s1
        bot_s1.streaming = True
        bot_s1._turn_in_progress = True
        bot_s1._active_turn_session_id = "sess-running-1"
        bot_s1._active_turn_session_file = s1_file

        # Now user switches tab-one to sess-other-2 while sess-running-1 is still running!
        dispatch(peer1, {"type": "chat_switch_session", "clientSessionId": "tab-one", "sessionId": "sess-other-2", "sessionPath": str(s2_file)}, None, None, hub=hub, chat=self.bot)
        bot_s2 = self.bot.get_session_bot("tab-one", scope="local")
        self.assertIsNot(bot_s1, bot_s2)
        self.assertTrue(bot_s1.streaming, "Running session S1 must NOT be aborted when switching to S2")
        self.assertEqual(bot_s2.current_session_id(), "sess-other-2")

        # Now S1 finishes its response in the background: it must write ONLY to sess-running-1, NEVER to sess-other-2!
        bot_s1._append_message_to_session_jsonl({"role": "assistant", "content": "Completed S1 background answer"})
        bot_s1.streaming = False
        bot_s1._turn_in_progress = False

        s2_msgs = bot_s2.get_messages()
        self.assertFalse(any("Completed S1 background answer" in str(m) for m in s2_msgs))
        s1_disk_msgs = self.bot._load_messages_from_jsonl(s1_file)
        self.assertTrue(any("Completed S1 background answer" in str(m) for m in s1_disk_msgs))


if __name__ == "__main__":
    unittest.main()

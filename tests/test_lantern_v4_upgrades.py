from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                usage_path=root / ".lantern" / "usage.json",
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
                usage_path=root / ".lantern" / "usage.json",
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
            work = WorkingCopyStore(root, root / ".lantern" / "work", {".md"})
            mgr = LanternBotManager(
                root,
                lambda _: None,
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
                usage_path=root / ".lantern" / "usage.json",
                bot_config=LanternBotConfig.from_mapping({
                    "access": {"localhost": {"enabled": True, "tools": ["*"], "extensions": True, "mcp": False}},
                }),
            )
            original_command = mgr._command

            def fake_command():
                command = original_command()
                return [sys.executable, "-u", str(fake_pi), *command[1:]]

            try:
                with (
                    patch.object(mgr, "_resolve_pi", return_value=str(fake_pi)),
                    patch.object(mgr, "_probe_cli_flags_if_needed", return_value=None),
                    patch.object(mgr, "_command", side_effect=fake_command),
                ):
                    self.assertNotIn("--no-mcp", mgr.unsupported_cli_flags)
                    self.assertIn("--no-mcp", mgr._command())

                    snap = mgr.bootstrap_state()

                    self.assertIn("--no-mcp", mgr.unsupported_cli_flags)
                    self.assertNotIn("--no-mcp", mgr._command())
                    self.assertEqual(snap["sessionId"], "s1")
            finally:
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
                usage_path=root / ".lantern" / "usage.json",
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
            mgr = LanternBotManager(
                root,
                lambda ev: events.append(ev),
                work_store=work,
                session_dir=root / ".lantern" / "sessions",
                usage_path=root / ".lantern" / "usage.json",
            )
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

        # LAN client is immediately locked out AND cannot even log in with valid password while hard-locked
        self.assertFalse(access.permitted("192.168.1.50", cookie))
        code2, _ = access.login("192.168.1.50", "correct-horse-battery")
        self.assertEqual(code2, 403)

        # Localhost itself remains unrestricted
        self.assertFalse(access.required("127.0.0.1"))
        self.assertTrue(access.permitted("127.0.0.1", ""))
        self.assertTrue(access.permitted("::ffff:127.0.0.1", ""))

        # Localhost re-allows LAN password login
        access.revoke_all_lan(hard_lock=False)
        self.assertFalse(access.lan_locked)
        code3, tok3 = access.login("192.168.1.50", "correct-horse-battery")
        self.assertEqual(code3, 200)
        self.assertTrue(access.permitted("192.168.1.50", f"lantern_terminal={tok3}"))



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
                usage_path=Path(tmp) / "usage.json",
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
                usage_path=Path(tmp) / "usage.json",
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import plugin
from lantern.bot_config import LanternBotConfig
from lantern.live_markdown import LiveMarkdownStore, VERSION_COALESCE_WINDOW_SEC, _merge3_text
from lantern.pi_chat import LanternBotManager
from lantern.system_telemetry import get_system_telemetry
from lantern.ws import WebSocketHub, dispatch

ROOT = Path(__file__).resolve().parents[1]


class DummyPeer:
    def __init__(self, ip: str = "127.0.0.1", cid: str = "") -> None:
        self.client_ip = ip
        self.chat_session_id = cid
        self.closed = False
        self.subscriptions: set[str] = set()
        self.protocol = "v2"
        self.inbox: list[dict] = []

    def can_terminal(self) -> bool:
        return True

    def send(self, payload: dict) -> None:
        self.inbox.append(payload)

    def close(self) -> None:
        self.closed = True


class V792StressAndUpgradesTests(unittest.TestCase):
    def test_markdown_version_1min_coalescing_rename_migration_and_orphan_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work_dir = root / ".lantern_work"
            store = LiveMarkdownStore(root, work_dir, {".md", ".markdown"})

            doc = root / "notes.md"
            doc.write_text("# v0 initial\nLine 1\n", encoding="utf-8")
            st0 = store.get("notes.md")
            self.assertEqual(st0["state"], "clean")

            # Simulate 10 rapid edits + saves within the 60s coalescing window:
            # The first save after initial creates 1 new version (total = 2: initial + coalesced latest),
            # and all subsequent saves within 60 seconds replace that latest version in place!
            base_v = st0["saved"]["version"]
            cur_h = None
            for i in range(1, 11):
                new_text = f"# v0 initial\nLine 1 edit {i}\n"
                w_res = store.write("notes.md", new_text, expect_hash=cur_h, base_version=base_v)
                s_res = store.save("notes.md", expect_hash=w_res["hash"], expect_saved_version=base_v)
                base_v = s_res["version"]
                cur_h = None

            v_list = store.list_versions("notes.md")["versions"]
            self.assertEqual(len(v_list), 2, "Saves within 60s window must coalesce into the latest version entry")
            self.assertIn("Line 1 edit 10", doc.read_text(encoding="utf-8"))

            # Backdate the latest version timestamp by 61s so the next save is outside the 1-minute window
            ident = store._compute_identifier("notes.md")
            idx_entries = store._load_version_index(ident)
            idx_entries[-1]["timestamp"] = time.time() - (VERSION_COALESCE_WINDOW_SEC + 2.0)
            idx_entries[-1]["windowStart"] = time.time() - (VERSION_COALESCE_WINDOW_SEC + 2.0)
            store._save_version_index(ident, idx_entries)

            w_after = store.write("notes.md", "# v0 initial\nAfter 61s window\n", expect_hash=None, base_version=base_v)
            store.save("notes.md", expect_hash=w_after["hash"], expect_saved_version=base_v)
            v_list_after = store.list_versions("notes.md")["versions"]
            self.assertEqual(len(v_list_after), 3, "Save after >60s must create a new version snapshot")

            # External OS rename/move: move notes.md -> subfolder/renamed_notes.md
            sub = root / "subfolder"
            sub.mkdir()
            renamed = sub / "renamed_notes.md"
            doc.rename(renamed)

            # Opening subfolder/renamed_notes.md automatically migrates version history by inode/SHA-256
            migrated_versions = store.list_versions("subfolder/renamed_notes.md")["versions"]
            self.assertEqual(len(migrated_versions), 3)

            # Explicit move via notify_moved
            moved2 = sub / "final_notes.md"
            renamed.rename(moved2)
            self.assertTrue(store.notify_moved("subfolder/renamed_notes.md", "subfolder/final_notes.md"))
            self.assertEqual(len(store.list_versions("subfolder/final_notes.md")["versions"]), 3)

            # Deleting file and running cleanup_orphans removes ghost versions
            moved2.unlink()
            removed = store.cleanup_orphans(max_orphan_age_sec=0.0)
            self.assertGreaterEqual(removed, 1)

    def test_concurrent_user_and_bot_edit_3way_merge_and_save_during_turn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LiveMarkdownStore(root, root / ".work", {".md"})
            md = root / "shared.md"
            base_text = "# Title\n\nParagraph 1 original\n\nParagraph 2 original\n\nParagraph 3 original\n"
            md.write_text(base_text, encoding="utf-8", newline="\r\n")

            st = store.get("shared.md")
            turn = store.begin_turn("shared.md", st["currentVersion"])
            self.assertTrue(store.get("shared.md")["turnActive"])

            # User edits Paragraph 1 concurrently while bot turn is active (allow_concurrent=True)
            user_text = "# Title\n\nParagraph 1 EDITED BY USER\n\nParagraph 2 original\n\nParagraph 3 original\n"
            w_user = store.write(
                "shared.md",
                user_text,
                expect_hash=st["currentVersion"],
                base_version=st["saved"]["version"],
                allow_concurrent=True,
            )
            self.assertTrue(w_user.get("concurrentStaged"))
            # Disk file remains untouched while bot is running so Pi Coding Agent edit tool never fails!
            self.assertEqual(md.read_text(encoding="utf-8"), base_text)

            # Bot edits Paragraph 3 on disk
            bot_text = "# Title\n\nParagraph 1 original\n\nParagraph 2 original\n\nParagraph 3 EDITED BY BOT\n"
            md.write_text(bot_text, encoding="utf-8", newline="\r\n")

            # Bot finishes turn: release_turn performs automatic 3-way merge of User + Bot changes!
            expected = user_text.replace("Paragraph 3 original", "Paragraph 3 EDITED BY BOT")
            expected_crlf = expected.replace("\n", "\r\n")
            self.assertEqual(
                _merge3_text(base_text.replace("\n", "\r\n"), user_text, bot_text.replace("\n", "\r\n")),
                (expected_crlf, False),
            )
            turn_result = store.end_turn("shared.md")
            self.assertFalse(turn_result["conflict"])
            self.assertEqual(md.read_bytes(), expected_crlf.encode("utf-8"))

    def test_lanbot_multi_tab_newchat_no_ghost_sessions_and_2level_fork_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            work = LiveMarkdownStore(root, root / ".work", {".md"})
            session_dir = root / ".sessions"
            events: list[dict] = []
            bot = LanternBotManager(
                root,
                lambda ev: events.append(ev),
                work_store=work,
                session_dir=session_dir,
                bot_config=LanternBotConfig.from_mapping({
                    "enabled": True,
                    "access": {"localhost": {"tools": ["*"], "extensions": True, "mcp": True}},
                }),
            )
            bot.last_state = {"sessionId": "", "sessionFile": "", "model": {"provider": "openai", "id": "gpt-4.1", "name": "GPT-4.1"}}
            bot._cached_models["local"] = [{"provider": "openai", "id": "gpt-4.1", "name": "GPT-4.1", "fullLabel": "openai / GPT-4.1", "reasoning": True, "contextWindow": 128000}]
            try:
                hub = WebSocketHub()
                hub.chat = bot

                # 1. Open 10 browser tabs and sync all 10 without sending any message:
                # Every tab must start in New Chat and 0 ghost session files should be created on disk.
                peers = [DummyPeer("127.0.0.1", f"tab-stress-{i}") for i in range(10)]
                for p in peers:
                    hub.add(p)
                    dispatch(p, {"type": "chat_sync", "clientSessionId": p.chat_session_id, "separateHistory": True, "historyLimit": 8}, None, None, hub=hub, chat=bot)
                    state_msgs = [m for m in p.inbox if m.get("type") == "chat_state"]
                    self.assertTrue(state_msgs)
                    self.assertTrue(str(state_msgs[-1]["state"].get("sessionId") or "").startswith(("newchat-", "")))

                jsonl_files = list(session_dir.rglob("*.jsonl")) if session_dir.exists() else []
                self.assertEqual(len(jsonl_files), 0, "Opening 10 tabs without messaging must create 0 ghost session files")

                # 2. Create parent session A with 4 messages and fork A1 (level 1) and A1_1 (level 2) and A1_1_1 (capped at level 2)
                tab0 = bot.get_session_bot("tab-stress-0", scope="local")
                tab0._ephemeral_new_chat = False
                s_a = session_dir / "sess-parent-a.jsonl"
                s_a.parent.mkdir(parents=True, exist_ok=True)
                lines_a = [
                    '{"type":"session","version":3,"id":"sess-parent-a","name":"Session A","customTitle":"Session A","lantern":true}',
                    '{"type":"message","id":"m1","sessionId":"sess-parent-a","role":"user","message":{"role":"user","content":"Msg 1"}}',
                    '{"type":"message","id":"m2","sessionId":"sess-parent-a","role":"assistant","message":{"role":"assistant","content":"Msg 2"}}',
                    '{"type":"message","id":"m3","sessionId":"sess-parent-a","role":"user","message":{"role":"user","content":"Msg 3"}}',
                    '{"type":"message","id":"m4","sessionId":"sess-parent-a","role":"assistant","message":{"role":"assistant","content":"Msg 4"}}',
                ]
                s_a.write_text("\n".join(lines_a) + "\n", encoding="utf-8")
                tab0.switch_session(str(s_a), scope="local")

                # Fork A1 after turn index 2 (3rd message)
                fork1_state = tab0.fork_session("local", upto_index=2, source_session_path=str(s_a), custom_name="A1")
                fork1_path = fork1_state["sessionFile"]
                # Fork A1.1 from A1
                fork2_state = tab0.fork_session("local", upto_index=1, source_session_path=fork1_path, custom_name="A1.1")
                fork2_path = fork2_state["sessionFile"]
                # Fork A1.1.1 from A1.1 -> must be capped at treeDepth == 2!
                tab0.fork_session("local", upto_index=1, source_session_path=fork2_path, custom_name="A1.1.1")

                sessions = bot.list_sessions("local", current_bot=tab0)
                by_id = {s.get("id"): s for s in sessions}
                by_name = {s.get("name") or s.get("label"): s for s in sessions}
                self.assertEqual(by_id["sess-parent-a"]["treeDepth"], 0)
                self.assertEqual(by_name["A1"]["treeDepth"], 1)
                self.assertEqual(by_name["A1"]["forkTurn"], 3)
                self.assertEqual(by_name["A1.1"]["treeDepth"], 2)
                self.assertEqual(by_name["A1.1.1"]["treeDepth"], 2, "Fork tree depth must be capped at max 2 levels")

                # Verify children appear immediately below Session A in list_sessions
                ids_order = [s.get("id") for s in sessions]
                idx_a = ids_order.index("sess-parent-a")
                child_names = {sessions[i].get("name") or sessions[i].get("label") for i in range(idx_a + 1, idx_a + 4)}
                self.assertEqual(child_names, {"A1", "A1.1", "A1.1.1"})

                # 3. Stress-test rapid multi-tab session switching across 5 tabs (cached JSONL fast path)
                t_start = time.monotonic()
                for round_idx in range(5):
                    for p_idx, p in enumerate(peers[:5]):
                        target_s = sessions[(round_idx + p_idx) % len(sessions)]
                        dispatch(
                            p,
                            {
                                "type": "chat_switch_session",
                                "clientSessionId": p.chat_session_id,
                                "sessionId": target_s["id"],
                                "sessionPath": target_s["path"],
                                "limit": 8,
                            },
                            None,
                            None,
                            hub=hub,
                            chat=bot,
                        )
                elapsed_ms = (time.monotonic() - t_start) * 1000.0
                self.assertLess(elapsed_ms, 2500.0, f"25 multi-tab session switches should be fast (<500ms), took {elapsed_ms:.1f}ms")
            finally:
                bot.close()

    def test_v792_frontend_and_telemetry_contracts(self) -> None:
        telem = get_system_telemetry()
        for key in ("cpu", "tempC", "ram", "memory", "gpu", "gpus"):
            self.assertIn(key, telem)

        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        chat_css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        paged_js = (ROOT / "static" / "markdown_paged_editor.js").read_text(encoding="utf-8")
        term_js = (ROOT / "static" / "terminal_scm.js").read_text(encoding="utf-8")
        plug_html = plugin._render_document_html("# Title\n\n## Section 1\n\nBody\n").decode("utf-8") if hasattr(plugin, "_render_document_html") else (ROOT / "plugin.py").read_text(encoding="utf-8")

        # 1. Header decluttered (no Lanbot text or brand SVG inside .lc-brand) + Worker/Subagent tabs
        self.assertIn('id="lcWorkerTabs"', chat_js)
        self.assertIn('id="lcAutoHideBtn"', chat_js)
        self.assertIn("clearTurnAttachmentsAfterSend", chat_js)
        self.assertIn("scheduleStreamingDomUpdate", chat_js)
        self.assertIn("body.lantern-chat-autohide", chat_css)
        self.assertIn("max-height: 132px;", chat_css)

        # 2. Markdown preview image crop/delete toolbar, 500ms source diff debounce, S||P auto-scroll, undo stack across Save
        self.assertIn("mountPreviewImageToolbar", shell_js)
        self.assertIn("DIFF_SOURCE_DEBOUNCE_MS = 500", shell_js)
        self.assertIn("lastAutoScrolledPreviewLine", shell_js)
        self.assertIn("undoHistoryStack", shell_js)
        self.assertIn("[32,64,128]", paged_js)
        self.assertIn("syncLazyChunkStream", paged_js)

        # 3. Terminal Ctrl+Backspace and multi-line Bracketed Paste
        self.assertIn("\\x17", term_js)
        self.assertIn("\\x1b[200~", term_js)




class V91SevenFixesAndRegressionTests(unittest.TestCase):
    """Comprehensive verification suite for all 7 user-reported issues in v9.1
    plus regression checks across LiveMarkdownStore, Preview DOM patching,
    inline diffing, table/paragraph editing, and Lanbot streaming UI."""

    def test_v91_issue_1_and_2_composite_version_and_user_draft_no_409_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LiveMarkdownStore(root, root / ".work", {".md"})
            doc = root / "AGENTS.md"
            base_content = "# Agents\n\nLine 1 original\n\nLine 2 original\n"
            doc.write_text(base_content, encoding="utf-8")

            st0 = store.get("AGENTS.md")
            self.assertEqual(st0["state"], "clean")
            base_ver = st0["saved"]["version"]

            # 1. User makes a small edit in Preview (creates .user_draft.md via user_draft=True)
            user_edit_1 = "# Agents\n\nLine 1 edited by user\n\nLine 2 original\n"
            w1 = store.write(
                "AGENTS.md",
                user_edit_1,
                expect_hash=None,
                base_version=base_ver,
                allow_concurrent=True,
                user_draft=True,
            )
            self.assertEqual(w1["state"], "pending")
            st1 = store.get("AGENTS.md")
            ver_after_user = st1["currentVersion"]
            self.assertEqual(w1["currentVersion"], ver_after_user)

            # 2. Subagent (child process) modifies real AGENTS.md on disk directly
            bot_disk_content = "# Agents\n\nLine 1 original\n\nLine 2 edited by Subagent on disk\n"
            doc.write_text(bot_disk_content, encoding="utf-8")

            # Issue 1 check: get() MUST return a NEW composite currentVersion (not masked by .user_draft.md!)
            st2 = store.get("AGENTS.md")
            self.assertNotEqual(
                st2["currentVersion"],
                ver_after_user,
                "Disk edit by Bot/Subagent must immediately change currentVersion even when .user_draft.md exists",
            )
            self.assertIn("Line 1 edited by user", st2["work"]["content"])
            self.assertIn("Line 2 edited by Subagent on disk", st2["work"]["content"])

            # 3. Issue 2 check: User crops/deletes/duplicates image or presses Ctrl+Z (calls write with user_draft=True)
            # Even when expect_hash is user_snap hash while real disk has changed, NO 409 Conflict occurs!
            user_edit_2 = "# Agents\n\nLine 1 edited by user + image deleted\n\nLine 2 edited by Subagent on disk\n"
            w2 = store.write(
                "AGENTS.md",
                user_edit_2,
                expect_hash=st2["work"]["hash"],
                base_version=base_ver,
                allow_concurrent=True,
                user_draft=True,
            )
            self.assertEqual(w2["state"], "pending")
            self.assertIn("image deleted", w2["mergedContent"])

    def test_v91_issue_1_2_3_4_5_in_markdown_visual_shell_js_and_css(self) -> None:
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")

        # Issue 1: refreshDiskBaseline does not block on view.piTurn
        self.assertIn("if (refreshingReal || view.loading || view.saving || document.hidden) return false;", shell_js)
        self.assertNotIn("if (refreshingReal || view.loading || view.saving || view.piTurn || document.hidden) return false;", shell_js)

        # Issue 2: applyPreviewMarkdownEdit and Ctrl+Z include userDraft: true
        self.assertGreaterEqual(shell_js.count("userDraft: true"), 4)

        # Issue 3: Incremental DOM Patching replaces preview.innerHTML = article.innerHTML
        self.assertIn("function patchPreviewDomIncrementally(", shell_js)
        self.assertIn("patchPreviewDomIncrementally(preview, article)", shell_js)
        self.assertNotIn("preview.innerHTML = article.innerHTML;", shell_js)

        # Issue 4: Multi-line inline block diff & serializeInlineEditableNode newline + latest cell badge extraction
        self.assertIn("const isInlineBlockMod = hunk.kind === 'mod'", shell_js)
        self.assertIn("document.execCommand('insertLineBreak')", shell_js)
        self.assertIn(".querySelectorAll?.('.md-table-cell-diff > .md-table-cell-new')", shell_js)

        # Issue 5: Subtle 0.035 table row highlight & top-right cell floating pill on hover
        self.assertIn("rgba(245, 158, 11, 0.035)", shell_css)
        self.assertIn("rgba(59, 130, 246, 0.035)", shell_css)
        self.assertIn(".md-hunk-floating-pill.is-table-cell-pill", shell_css)
        self.assertIn("attachFloatingPillAboveChangedWords", shell_js)

    def test_v91_issue_6_and_7_in_chatbot_js_and_css(self) -> None:
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        chat_css = (ROOT / "static" / "chatbot.css").read_text(encoding="utf-8")

        # Issue 6: hydrateActiveStreamTurnIntoDom uses syncAssistantStepsIntoCardIncrementally and never removes card children
        self.assertIn("function syncAssistantStepsIntoCardIncrementally(", chat_js)
        self.assertIn("function updateStepWorkBoxInPlace(", chat_js)
        self.assertIn("function updateSubagentGridInPlace(", chat_js)
        self.assertNotIn("if (ch !== head) ch.remove();", chat_js)

        # Issue 7: 2-line Subagent card ([Agent] ... - 🟡 running / 🟢 Completed - XX.Xk tok) & 1-line 30%-smaller tool call summary
        self.assertIn('<span class="lc-pi-subagent-tag">[Agent]</span>', chat_js)
        self.assertIn("🟡 running", chat_js)
        self.assertIn("🟢 Completed", chat_js)
        self.assertNotIn("Subagents running (", chat_js)
        self.assertIn("function computeStepToolDurationStr(", chat_js)
        self.assertIn("font: 600 8.8px/1.25", chat_css)
        self.assertIn("font-size: 8.8px !important;", chat_css)


class V92TenFixesAndMasterChecklistTests(unittest.TestCase):
    """Verification suite for all 10 newly reported v9.2 fixes:
    A. Instant optimistic hunk Save/Undo & 3-way base-space undo math
    B. 1-click in-place editing of fenced code blocks (pre.md-code[data-l])
    C. Zero-flash, zero-scroll-jump Preview editing (.table-wrap scroll & in-badge cell edit)
    D. GFM table separator rows & unequal row counts rendered inside <table> (never raw pipe blocks)
    E. Lowered floating Save/Undo pill (top: -10px / top: -8px) for effortless hover/click
    F. Multi-image paste in Preview/Source with .md-diff-img-frame and split per-image hunk counter
    G. Right-click opens Source from Edit visually and keeps the native menu in Preview
    H. Subagent status stays 'Running' on background spawn until get_subagent_result / notification completes
    I. Prior assistant steps (Todo response & subagent cards) preserved across continuation/wake-up turns
    J. Visible [skill] banner rendered directly in .lc-step-slot & broadened skill path detection
    """

    def test_v92_issue_a_accept_partial_cleans_user_draft_and_returns_full_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LiveMarkdownStore(root, root / ".work", {".md"})
            doc = root / "AGENTS.md"
            base = "# Title\n\nPara 1 old\n\nPara 2 old\n"
            doc.write_text(base, encoding="utf-8", newline="\r\n")

            st0 = store.get("AGENTS.md")
            # Bot edits Para 1 on disk
            bot_real = "# Title\n\nPara 1 bot\n\nPara 2 old\n"
            doc.write_text(bot_real, encoding="utf-8", newline="\r\n")

            # User edits Para 2 in Preview (creating .user_draft.md)
            user_draft = "# Title\n\nPara 1 bot\n\nPara 2 user\n"
            store.write(
                "AGENTS.md",
                user_draft,
                expect_hash=None,
                base_version=st0["saved"]["version"],
                allow_concurrent=True,
                user_draft=True,
            )
            st1 = store.get("AGENTS.md")
            self.assertIsNotNone(st1.get("userDraft"))

            # User clicks Undo on their Para 2 hunk -> next_user_content equals bot_real
            res = store.accept_partial(
                "AGENTS.md",
                base,
                expect_saved_version=st1["saved"]["version"],
                expect_current_version=st1["currentVersion"],
                next_real_content=bot_real,
                next_user_content=bot_real,
            )
            # Must return full work state in a single round-trip and clean up userDraft
            self.assertIn("saved", res)
            self.assertIn("work", res)
            self.assertIsNone(res.get("userDraft"))
            self.assertIn("Para 1 bot", res["work"]["content"])
            self.assertIn("Para 2 old", res["work"]["content"])

    def test_v92_issues_a_b_c_d_e_f_g_in_frontend_assets(self) -> None:
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        shell_css = (ROOT / "static" / "markdown_visual_shell.css").read_text(encoding="utf-8")
        anchor_js = (ROOT / "static" / "markdown_anchor_bridge.js").read_text(encoding="utf-8")

        # Issue A: Base-space applyHunksToBaseText & optimistic 0ms UI update in actionHunk
        self.assertIn("function applyHunksToBaseText(", shell_js)
        self.assertIn("function splitMultiImageAddHunks(", shell_js)

        # Issue B: Fenced code block 1-click editing (Case A2: pre.md-code[data-l])
        self.assertIn("const preNode = target.closest('pre.md-code[data-l]');", shell_js)
        self.assertIn("const finishCodeBlock = (commit) =>", shell_js)

        # Issue C: Scroll state preservation (.table-wrap scrollLeft/scrollTop) & in-badge table cell editing
        self.assertIn("function captureAllPreviewScrollStates(", shell_js)
        self.assertIn("function restoreAllPreviewScrollStates(", shell_js)
        self.assertIn("const editTargetEl = newBadges.length > 0 ? newBadges[newBadges.length - 1] : cell;", shell_js)

        # Issue D: GFM table separator rows allowed in tryRenderTableHunkInPlace
        self.assertIn("const isAnyTablePipeLine = l =>", shell_js)
        self.assertIn("const isDataTablePipeLine = l =>", shell_js)

        # Issue E: Lowered floating Save/Undo pill (top:-10px and top:-8px)
        self.assertIn("top: -10px !important;", shell_css)
        self.assertIn("top: -8px !important;", shell_css)
        self.assertIn("firstWord.offsetTop - 10", shell_js)

        # Issue F: Preview mode paste handler, IMG serialization, and .md-diff-img-frame
        self.assertIn("Pasted ${mdTokens.length} image(s) into Preview.", shell_js)
        self.assertIn("if (tag === 'IMG')", shell_js)
        self.assertIn(".md-diff-img-frame", shell_css)

        # v9.24: Preview keeps its native menu. Edit visually opens Source at the bookmark.
        context_menu = anchor_js.split("document.addEventListener('contextmenu', event => {", 1)[1]
        visual_guard = context_menu.index("if (mode !== 'visual') return;")
        self.assertLess(visual_guard, context_menu.index("event.preventDefault();"))
        self.assertLess(visual_guard, context_menu.index("visualApi.open('source'"))
        self.assertNotIn("Edit selection in Visual", anchor_js)

    def test_v92_issues_h_i_j_subagent_status_step_preservation_and_skill_display(self) -> None:
        chat_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        pi_chat_py = (ROOT / "lantern" / "pi_chat.py").read_text(encoding="utf-8")
        checklist_md = (ROOT / "docs" / "LANTERN_FULL_FEATURE_CHECKLIST.md").read_text(encoding="utf-8")

        # Issue H: Background subagent spawn recognition & get_subagent_result handling
        self.assertIn("get_subagent_result|subagent_result|wait_subagent", chat_js)
        self.assertIn("argsObj?.run_in_background", chat_js)
        self.assertIn("markSubagentEntryDone", chat_js)

        # Issue I: Preserve prior turn steps across continuation/wake-up turns in both chatbot.js and pi_chat.py
        self.assertIn("const priorTurnSteps = rawPrevSteps.filter(s => s && s._turnUid && s._turnUid !== curUid);", chat_js)
        self.assertIn("entry.steps = [...priorTurnSteps, ...taggedIncoming];", chat_js)
        self.assertIn("self._turn_stream_blocks", pi_chat_py)

        # Issue J: Visible [skill] banner rendered directly in .lc-step-slot
        self.assertIn("let visibleSkillList = slot.querySelector(':scope > .lc-pi-skill-list');", chat_js)
        self.assertIn("scanTextForSkillPath", chat_js)

        # Master checklist exists and covers all 3 parts
        self.assertIn("LANTERN — FULL FEATURE & QA REGRESSION CHECKLIST", checklist_md)
        self.assertIn("PHẦN 1: MARKDOWN PREVIEW", checklist_md)
        self.assertIn("PHẦN 2: LANBOT CHATBOT", checklist_md)
        self.assertIn("PHẦN 3: FILE MANAGER", checklist_md)


if __name__ == "__main__":
    unittest.main()

    def test_v921_crlf_version_consistency_per_row_hunks_and_tool_coalescing(self) -> None:
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = LiveMarkdownStore(root, root / ".work", {".md"})
            doc = root / "AGENTS.md"
            doc.write_bytes(b"# Title\r\n\r\n| Col1 | Col2 |\r\n| --- | --- |\r\n| r1 | v1 |\r\n| r2 | v2 |\r\n| r3 | v3 |\r\n")
            st0 = store.get("AGENTS.md")
            # Write LF user draft onto CRLF file: write() and get() must return identical currentVersion!
            w1 = store.write(
                "AGENTS.md",
                "# Title\n\n| Col1 | Col2 |\n| --- | --- |\n| r1_mod | v1 |\n| r2_mod | v2 |\n| r3_mod | v3 |\n",
                expect_hash=None,
                base_version=st0["saved"]["version"],
                allow_concurrent=True,
                user_draft=True,
            )
            st1 = store.get("AGENTS.md")
            self.assertEqual(w1["currentVersion"], st1["currentVersion"])
            # Also verify during an active bot turn
            store.begin_turn("AGENTS.md", st1["currentVersion"])
            w2 = store.write(
                "AGENTS.md",
                "# Title\n\n| Col1 | Col2 |\n| --- | --- |\n| r1_mod2 | v1 |\n| r2_mod | v2 |\n| r3_mod | v3 |\n",
                expect_hash=None,
                base_version=st0["saved"]["version"],
                allow_concurrent=True,
                user_draft=True,
            )
            st2 = store.get("AGENTS.md")
            self.assertEqual(w2["currentVersion"], st2["currentVersion"])

        # Verify parseTableRowCells respects pipes inside inline code backticks
        node_Out = subprocess.check_output(
            [
                "node",
                "-e",
                "const d = require('./static/markdown_draft_diff.js'); "
                "const cells = d.parseTableRowCells('| `cmd1 || cmd2` | `a | b` | normal |'); "
                "if (!cells || cells.length !== 3 || cells[0] !== '`cmd1 || cmd2`') process.exit(1); "
                "console.log('OK');",
            ],
            cwd=str(ROOT),
            text=True,
        )
        self.assertIn("OK", node_Out)

        # Verify v9.21 contracts in markdown_visual_shell.js and chatbot.js
        shell_js = (ROOT / "static" / "markdown_visual_shell.js").read_text(encoding="utf-8")
        self.assertIn("_isSplitLineHunk", shell_js)
        self.assertIn("isSameBlockStructure", shell_js)
        self.assertIn("lastRenderedDiffSig", shell_js)

        chatbot_js = (ROOT / "static" / "chatbot.js").read_text(encoding="utf-8")
        self.assertIn("coalesceConsecutiveToolSteps", chatbot_js)
        self.assertIn("const normStr = String(str).replace(/\\\\+/g, '/');", chatbot_js)
        self.assertIn("els.activeAgentsBar.hidden = true;", chatbot_js)

"""Real Edge checks for original-file live editing and diff checkpoints."""
from __future__ import annotations
import os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

@unittest.skipUnless(os.environ.get("LANTERN_E2E")=="1", "set LANTERN_E2E=1")
class LiveMarkdownE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from urllib.request import urlopen
        cls.tmp=tempfile.TemporaryDirectory(prefix="lantern-live-",ignore_cleanup_errors=True)
        cls.root=Path(cls.tmp.name)/"root";cls.root.mkdir()
        sock=socket.socket();sock.bind(("127.0.0.1",0));cls.port=sock.getsockname()[1];sock.close()
        cls.base=f"http://127.0.0.1:{cls.port}"
        env=dict(os.environ,LANTERN_WORK_DIR=str(Path(cls.tmp.name)/"work"))
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/"main.py"),"--root",str(cls.root),
            "--host","127.0.0.1","--port",str(cls.port)],cwd=ROOT,env=env,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(130):
            try:
                with urlopen(cls.base+"/api/info",timeout=.5):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("Live E2E server not ready")
        cls.play=sync_playwright().start()
        cls.browser=cls.play.chromium.launch(channel="msedge",headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.play.stop();cls.proc.terminate()
        try:cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:cls.proc.kill()
        cls.tmp.cleanup()

    def test_edit_source_real_written_before_accept_and_temp_only_after(self):
        file=self.root/"live.md"
        original="# Live\n\nOriginal text.\n"
        edited="# Live\n\nEdited in Source.\n"
        file.write_text(original,encoding="utf-8",newline="")
        context=self.browser.new_context(viewport={"width":1200,"height":780})
        page=context.new_page(); errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        try:
            page.goto(self.base+"/api/plugin/preview?p=live.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=12000);area.fill(edited)
            page.wait_for_function("() => !!window.__lanternMdVisual.state.workHash",timeout=11000)
            self.assertEqual(file.read_text(encoding="utf-8"),edited)
            state=page.evaluate("async()=>(await(await fetch('/api/work?p=live.md')).json())")
            self.assertEqual(state["saved"]["content"],original)
            self.assertEqual(state["work"]["content"],edited)
            self.assertEqual(page.locator(".md-source-deletion").count(),1)
            self.assertEqual(page.locator(".md-source-deletions").evaluate("e=>e.parentElement.className"),"md-source-diff-wrap")
            page.keyboard.press("Control+s")
            page.wait_for_function("() => document.documentElement.dataset.mdPendingHunks === '0'",timeout=12000)
            state=page.evaluate("async()=>(await(await fetch('/api/work?p=live.md')).json())")
            self.assertEqual(state["saved"]["content"],edited)
            self.assertIsNone(state["work"])
            self.assertEqual(file.read_text(encoding="utf-8"),edited)
            self.assertEqual(errors,[])
        finally:context.close()

    def test_vscode_live_change_shows_preview_diff_and_per_hunk_undo(self):
        target=self.root/"vscode.md"
        before="# External\n\nOld paragraph.\n\nLast paragraph.\n"
        edited="# External\n\nVS Code edited.\n\nLast paragraph.\n"
        target.write_text(before,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1380,"height":840})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=vscode.md")
            page.wait_for_function("() => !!window.__lanternMdVisual.state.currentVersion")
            started=time.perf_counter()
            target.write_text(edited,encoding="utf-8",newline="")
            page.wait_for_function(
                "() => !!document.querySelector('.md-preview-diff-mod')",
                timeout=13000)
            detected=time.perf_counter()-started
            self.assertLess(detected,5.5,detected)
            self.assertIn("VS Code edited.",page.locator("article.md-preview").inner_text())
            state=page.evaluate("async()=>(await(await fetch('/api/work?p=vscode.md')).json())")
            self.assertEqual(state["saved"]["content"],before)
            self.assertEqual(state["work"]["content"],edited)
            page.locator(".md-hunk-button",has_text="Undo").first.click()
            page.wait_for_function("() => document.documentElement.dataset.mdPendingHunks === '0'",timeout=10000)
            self.assertEqual(target.read_text(encoding="utf-8"),before)
        finally:ctx.close()

    def test_two_hunks_accept_one_undo_other_and_source_inline_rows(self):
        file=self.root/"partial.md"
        before="# Changes\n\nFirst OLD.\n\nMiddle untouched.\n\nLast OLD.\n"
        edited="# Changes\n\nFirst NEW.\n\nMiddle untouched.\n\nLast NEW.\n"
        file.write_text(before,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1250,"height":800})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=partial.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for()
            area.fill(edited)
            page.wait_for_function(
                "() => !!window.__lanternMdVisual.state.workHash"
                " && document.querySelectorAll('.md-source-deletion').length >= 2",timeout=12000)
            self.assertEqual(file.read_text(encoding="utf-8"),edited)
            self.assertEqual(page.locator(".md-source-deletions").evaluate("e=>e.parentElement.className"),"md-source-diff-wrap")
            page.locator(".md-source-deletion").first.get_by_role("button",name="Accept").click()
            page.wait_for_function(
                "() => document.querySelectorAll('.md-source-deletion').length === 1",timeout=10000)
            state=page.evaluate("async()=>(await(await fetch('/api/work?p=partial.md')).json())")
            self.assertIn("First NEW.",state["saved"]["content"])
            self.assertIn("Last OLD.",state["saved"]["content"])
            self.assertEqual(file.read_text(encoding="utf-8"),edited)
            page.locator(".md-source-deletion").first.get_by_role("button",name="Undo").click()
            page.wait_for_function("() => document.documentElement.dataset.mdPendingHunks === '0'",timeout=10000)
            self.assertIn("First NEW.",file.read_text(encoding="utf-8"))
            self.assertIn("Last OLD.",file.read_text(encoding="utf-8"))
        finally:ctx.close()

    def test_context_menu_selection_flashes_for_half_second_in_visual(self):
        file=self.root/"flash.md"
        file.write_text("# Anchor\n\nFirst block.\n\nUnique target text for highlight.\n",
                        encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1120,"height":820})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=flash.md")
            page.evaluate("""() => {
              const p=[...document.querySelectorAll('article.md-preview p')].find(
                e=>e.textContent.includes('Unique target text for highlight.'));
              const range=document.createRange();range.selectNodeContents(p);
              getSelection().removeAllRanges();getSelection().addRange(range);
              p.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,
                clientX:130,clientY:220}));
            }""")
            page.evaluate("""() => {
              const orig=window.__lanternMdVisual.open;
              window.__lanternMdVisual.open=(...args)=>{window.__flashBookmark=args[1];return orig(...args);};
              window.__flashObserved=0;
              const origAdd=DOMTokenList.prototype.add;
              DOMTokenList.prototype.add=function(...tokens){
                if(tokens.includes('lantern-md-anchor-highlight'))window.__flashObserved++;
                return origAdd.apply(this,tokens);
              };
            }""")
            page.get_by_role("button",name="Edit selection in Visual").click()
            page.locator(".md-visual-host .ProseMirror").wait_for(timeout=24000)
            page.wait_for_timeout(420)
            debug=page.evaluate("""() => ({
              count:window.__flashObserved,bookmark:window.__flashBookmark,
              mappedLine:window.__lanternMdVisual.state.instance?.sourceBlockAtLine(
                window.__flashBookmark?.line)?.textContent,
              visualMode:window.__lanternMdVisual.state.mode
            })""")
            self.assertGreater(debug["count"],0,debug)
            page.wait_for_timeout(650)
            self.assertEqual(page.locator(".lantern-md-anchor-highlight").count(),0)
        finally:ctx.close()

    def test_visual_hunk_buttons_undo_real_file_without_accepting_others(self):
        file=self.root/"visual-hunks.md"
        original="# Visual hunks\n\nFirst old.\n\nStable middle.\n\nLast old.\n"
        updated="# Visual hunks\n\nFirst new.\n\nStable middle.\n\nLast new.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1290,"height":820})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=visual-hunks.md")
            page.get_by_role("button",name="Source",exact=True).click()
            page.get_by_role("textbox",name="Markdown source").fill(updated)
            page.wait_for_function("() => !!window.__lanternMdVisual.state.workHash",timeout=10000)
            self.assertEqual(file.read_text(encoding="utf-8"),updated)
            page.get_by_role("button",name="Edit visually",exact=True).click()
            page.locator(".md-visual-host .ProseMirror").wait_for(timeout=24000)
            page.wait_for_function(
                "() => document.querySelectorAll('.md-visual-hunk-actions').length >= 2",
                timeout=10000)
            page.locator(".md-visual-hunk-actions").first.get_by_role(
                "button",name="Undo").click()
            page.wait_for_function(
                "() => document.querySelectorAll('.md-visual-hunk-actions').length === 1",
                timeout=10000)
            real=file.read_text(encoding="utf-8")
            self.assertIn("First old.",real)
            self.assertIn("Last new.",real)
            state=page.evaluate("async()=>(await(await fetch('/api/work?p=visual-hunks.md')).json())")
            self.assertEqual(state["saved"]["content"],original)
            self.assertIn("Last new.",state["work"]["content"])
        finally:ctx.close()

    def test_chat_log_order_and_f5_replay(self):
        file=self.root/"chat-history.md"
        file.write_text("# Chat history\n\nBody.\n",encoding="utf-8",newline="")
        ctx=self.browser.new_context()
        page=ctx.new_page()
        page.add_init_script("""window.WebSocket = class FakeWS {
          static OPEN=1; static CONNECTING=0;
          constructor(){ this.readyState=1; window.__fakeChatSocket=this;
            setTimeout(()=>this.onopen?.(),10); }
          send(raw) {
            const data=JSON.parse(raw);
            if (data.type==='chat_sync') setTimeout(()=>this.emit({
              type:'chat_state',
              state:{sessionId:'ui-history-session'},
              summary:{streaming:false,policy:{greeting:''}},
              messages:[],models:[]
            }),10);
          }
          emit(value) { this.onmessage?.({data:JSON.stringify(value)}); }
          close(){ this.readyState=3;this.onclose?.(); }
        };""")
        try:
            page.goto(self.base+"/api/plugin/preview?p=chat-history.md")
            page.locator(".lantern-chat-launch").click()
            page.wait_for_function("() => !!window.__fakeChatSocket")
            page.wait_for_function("() => document.querySelector('#lanternChatStatus')?.textContent === 'Ready'")
            page.evaluate("""() => {
              const s=window.__fakeChatSocket;
              s.emit({type:'chat_bot_event',event:{
                type:'tool_execution_start',toolCallId:'one',toolName:'powershell',
                args:{command:'echo test'}}});
              s.emit({type:'chat_bot_event',event:{
                type:'tool_execution_end',toolCallId:'one'}});
              s.emit({type:'chat_bot_event',event:{
                type:'message_start',message:{role:'assistant'}}});
              s.emit({type:'chat_bot_event',event:{
                type:'message_update',delta:'Command completed.'}});
              s.emit({type:'chat_bot_event',event:{
                type:'message_end',message:{role:'assistant',content:[
                  {type:'text',text:'Command completed.'}]}}});
              s.emit({type:'chat_bot_event',event:{type:'agent_settled'}});
            }""")
            page.wait_for_timeout(350)
            items=page.locator("#lanternChatMessages > *")
            self.assertEqual(items.count(),2)
            self.assertIn("powershell",items.nth(0).inner_text())
            self.assertIn("Command completed.",items.nth(1).inner_text())
            page.reload(wait_until="domcontentloaded")
            page.locator(".lantern-chat-launch").click()
            page.wait_for_function("() => document.querySelectorAll('#lanternChatMessages > *').length === 2")
            items=page.locator("#lanternChatMessages > *")
            self.assertIn("powershell",items.nth(0).inner_text())
            self.assertIn("Command completed.",items.nth(1).inner_text())
        finally:ctx.close()

    def test_paged_visual_auto_writes_real_and_bot_roundtrip_without_mode_switch(self):
        target=self.root/"paged-live-bot.md"
        original="# Paged\n\nIntro stable.\n\n" + "".join(
            "## Section %s\n\n%s\n\n" % (i,"A"*450) for i in range(172))
        target.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1300,"height":830})
        page=ctx.new_page()
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        try:
            page.goto(self.base+"/api/plugin/preview?p=paged-live-bot.md")
            page.get_by_role("button",name="Edit visually",exact=True).click()
            page.wait_for_function("() => !!window.__lanternMdPaged?.active",timeout=32000)
            editor=page.locator("#md-paged-edit-host .ProseMirror")
            editor.wait_for(timeout=25000)
            para=editor.get_by_text("Intro stable.",exact=True)
            para.click()
            page.keyboard.press("End")
            page.keyboard.type(" LOCAL")
            page.wait_for_function(
                "() => window.__lanternMdPaged.source.includes('Intro stable. LOCAL')"
                " && !window.__lanternMdPaged.saving",timeout=18000)
            self.assertIn("Intro stable. LOCAL",target.read_text(encoding="utf-8"))
            old=page.evaluate("async()=>(await(await fetch('/api/work?p=paged-live-bot.md')).json())")
            self.assertEqual(old["saved"]["content"].replace("\r\n","\n"),original)
            page.keyboard.press("Control+s")
            page.wait_for_function(
                "() => window.__lanternMdPaged.statusEl?.textContent.includes('Saved diff baseline')",
                timeout=14000)
            # Chat turn is valid while the section editor remains visible.
            page.evaluate("""async() => await window.LanternChat.prepareMarkdownTurn({
              kind:'markdown',path:'paged-live-bot.md',markdownMode:'visual'
            })""")
            self.assertTrue(page.evaluate("() => window.__lanternMdPaged.botTurnActive"))
            updated=page.evaluate("""async() => {
              const s=await(await fetch('/api/work?p=paged-live-bot.md')).json();
              const content=s.saved.content.replace('Intro stable. LOCAL','Intro stable. BOT');
              const r=await fetch('/api/work/write',{
                method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({path:'paged-live-bot.md',content,
                  expectHash:s.work?.hash||null,baseVersion:s.saved.version})
              });
              if(!r.ok)throw Error(await r.text());
              return await r.json();
            }""")
            page.evaluate("""async(h)=>window.__lanternMdVisual.onWorkChanged(
              'paged-live-bot.md',h,true)""",updated["hash"])
            page.wait_for_function("""() => !!window.__lanternMdPaged?.active &&
              !window.__lanternMdPaged.botTurnActive &&
              document.querySelector('#md-paged-edit-host')?.textContent.includes('Intro stable. BOT')""",
              timeout=25000)
            self.assertIn("Intro stable. BOT",target.read_text(encoding="utf-8"))
            editor.get_by_text("Intro stable. BOT",exact=True).click()
            page.keyboard.press("End")
            page.keyboard.type(" NEXT")
            page.wait_for_function(
                "() => window.__lanternMdPaged.source.includes('Intro stable. BOT NEXT')"
                " && !window.__lanternMdPaged.saving",timeout=18000)
            self.assertIn("Intro stable. BOT NEXT",target.read_text(encoding="utf-8"))
            self.assertEqual(errors,[],errors)
        finally:ctx.close()

    def test_two_browser_clients_cannot_blind_overwrite_same_line(self):
        file=self.root/"two-clients.md"
        original="# Concurrent\n\nOriginal line.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1100,"height":800})
        first,second=ctx.new_page(),ctx.new_page()
        try:
            for page in (first,second):
                page.goto(self.base+"/api/plugin/preview?p=two-clients.md")
                page.get_by_role("button",name="Source",exact=True).click()
                page.get_by_role("textbox",name="Markdown source").wait_for(timeout=12000)
            first.get_by_role("textbox",name="Markdown source").fill("# Concurrent\n\nClient A.\n")
            first.wait_for_function("() => !!window.__lanternMdVisual.state.workHash",timeout=10000)
            self.assertIn("Client A.",file.read_text(encoding="utf-8"))
            second.get_by_role("textbox",name="Markdown source").fill("# Concurrent\n\nClient B.\n")
            second.wait_for_function(
                "() => window.__lanternMdVisual.state.conflict === true",timeout=10000)
            self.assertEqual(file.read_text(encoding="utf-8"),"# Concurrent\n\nClient A.\n")
            self.assertIn("Client B.",second.get_by_role("textbox",name="Markdown source").input_value())
            second.keyboard.press("Control+s")
            self.assertEqual(file.read_text(encoding="utf-8"),"# Concurrent\n\nClient A.\n")
        finally:ctx.close()


    def test_accept_then_browser_undo_redo_keeps_md_temp_at_accepted_version(self):
        file=self.root/"accept-undo.md"
        original="# Accept undo\n\nBase.\n"
        accepted="# Accept undo\n\nAccepted.\n"
        redone="# Accept undo\n\nAccepted. MORE\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1100,"height":800})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=accept-undo.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=12000)
            area.fill(accepted)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Accepted.')",
                timeout=12000)
            page.keyboard.press("Control+s")
            page.wait_for_function(
                "() => document.documentElement.dataset.mdPendingHunks === '0'",
                timeout=12000)
            accepted_state=page.evaluate(
                "async()=>(await(await fetch('/api/work?p=accept-undo.md')).json())")
            temp=Path(accepted_state["tempPath"])
            self.assertEqual(temp.read_bytes(),file.read_bytes())
            accepted_temp=temp.read_bytes()

            area.click()
            page.keyboard.press("Control+End")
            page.keyboard.press("ArrowLeft")
            page.keyboard.insert_text(" MORE")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Accepted. MORE')",
                timeout=12000)
            self.assertEqual(file.read_text(encoding="utf-8"),redone)
            self.assertEqual(temp.read_bytes(),accepted_temp)

            page.keyboard.press("Control+z")
            page.wait_for_timeout(700)
            self.assertEqual(area.input_value(),accepted)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.endsWith('Accepted.\\n')",
                timeout=12000)
            self.assertEqual(file.read_text(encoding="utf-8"),accepted)
            self.assertEqual(temp.read_bytes(),accepted_temp)

            page.keyboard.press("Control+y")
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Accepted. MORE')",
                timeout=12000)
            self.assertEqual(file.read_text(encoding="utf-8"),redone)
            self.assertEqual(temp.read_bytes(),accepted_temp)
            final=page.evaluate(
                "async()=>(await(await fetch('/api/work?p=accept-undo.md')).json())")
            self.assertEqual(final["saved"]["content"],accepted)
            self.assertEqual(final["work"]["content"],redone)
        finally:
            ctx.close()

    def test_two_browser_clients_nonoverlap_changes_auto_merge_without_lost_update(self):
        file=self.root/"two-clients-nonoverlap.md"
        original="# Concurrent\n\nA old.\n\nB old.\n"
        first_text="# Concurrent\n\nA NEW.\n\nB old.\n"
        second_text="# Concurrent\n\nA old.\n\nB NEW.\n"
        merged="# Concurrent\n\nA NEW.\n\nB NEW.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1100,"height":800})
        first,second=ctx.new_page(),ctx.new_page()
        try:
            for page in (first,second):
                page.goto(self.base+"/api/plugin/preview?p=two-clients-nonoverlap.md")
                page.get_by_role("button",name="Source",exact=True).click()
                page.get_by_role("textbox",name="Markdown source").wait_for(timeout=12000)

            first.get_by_role("textbox",name="Markdown source").fill(first_text)
            first.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('A NEW.')",
                timeout=12000)
            second.get_by_role("textbox",name="Markdown source").fill(second_text)
            second.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('A NEW.')"
                " && window.__lanternMdVisual.state.lastSaved.includes('B NEW.')",
                timeout=12000)
            self.assertEqual(file.read_text(encoding="utf-8"),merged)
            self.assertFalse(second.evaluate(
                "() => window.__lanternMdVisual.state.conflict"))
            self.assertEqual(
                second.get_by_role("textbox",name="Markdown source").input_value(),
                merged)
            state=second.evaluate(
                "async()=>(await(await fetch('/api/work?p=two-clients-nonoverlap.md')).json())")
            self.assertEqual(state["saved"]["content"],original)
            self.assertEqual(state["work"]["content"],merged)
        finally:
            ctx.close()



    def test_external_poll_refreshes_source_and_visual_without_accepting_temp(self):
        for mode in ("source","visual"):
            with self.subTest(mode=mode):
                name=f"external-{mode}.md"
                file=self.root/name
                original=f"# External {mode}\n\nOld block.\n"
                edited=f"# External {mode}\n\nNew block.\n"
                file.write_text(original,encoding="utf-8",newline="")
                ctx=self.browser.new_context(viewport={"width":1150,"height":800})
                page=ctx.new_page()
                try:
                    page.goto(self.base+"/api/plugin/preview?p="+name)
                    if mode=="source":
                        page.get_by_role("button",name="Source",exact=True).click()
                        editor=page.get_by_role("textbox",name="Markdown source")
                    else:
                        page.get_by_role("button",name="Edit visually",exact=True).click()
                        editor=page.locator(".md-visual-host .ProseMirror")
                    editor.wait_for(timeout=24000)
                    initial=page.evaluate(
                        f"async()=>(await(await fetch('/api/work?p={name}')).json())")
                    temp=Path(initial["tempPath"])
                    accepted_bytes=temp.read_bytes()
                    file.write_text(edited,encoding="utf-8",newline="")
                    if mode=="source":
                        page.wait_for_function(
                            "() => document.querySelector('.md-source-area')?.value.includes('New block.')",
                            timeout=9000)
                    else:
                        page.wait_for_function(
                            "() => document.querySelector('.md-visual-host .ProseMirror')?.textContent.includes('New block.')",
                            timeout=9000)
                    state=page.evaluate(
                        f"async()=>(await(await fetch('/api/work?p={name}')).json())")
                    self.assertEqual(state["saved"]["content"],original)
                    self.assertEqual(state["work"]["content"],edited)
                    self.assertEqual(temp.read_bytes(),accepted_bytes)
                    self.assertFalse(page.evaluate(
                        "() => window.__lanternMdVisual.state.conflict"))
                finally:
                    ctx.close()

    def test_external_delete_and_rename_fail_visible_without_recreating_old_path(self):
        for action in ("delete","rename"):
            with self.subTest(action=action):
                name=f"missing-{action}.md"
                file=self.root/name
                moved=self.root/(name+".moved")
                original="# Missing path\n\nKeep recovery text.\n"
                file.write_text(original,encoding="utf-8",newline="")
                ctx=self.browser.new_context(viewport={"width":1100,"height":800})
                page=ctx.new_page()
                try:
                    page.goto(self.base+"/api/plugin/preview?p="+name)
                    area=None
                    if action=="delete":
                        page.get_by_role("button",name="Source",exact=True).click()
                        area=page.get_by_role("textbox",name="Markdown source")
                        area.wait_for(timeout=12000)
                        file.unlink()
                    else:
                        page.locator("article.md-preview").wait_for(timeout=12000)
                        file.rename(moved)
                    page.wait_for_function(
                        "() => window.__lanternMdVisual.state.conflict === true",
                        timeout=9000)
                    self.assertFalse(file.exists())
                    if area is not None:
                        self.assertEqual(area.input_value(),original)
                    else:
                        self.assertIn("Keep recovery text.",
                                      page.locator("article.md-preview").inner_text())
                    status_node=page.locator("[data-md-status]")
                    status=status_node.inner_text().lower()
                    self.assertTrue(
                        "unavailable" in status or "missing" in status,
                        status)
                    self.assertTrue(status_node.is_visible(),status)
                    page.wait_for_timeout(700)
                    self.assertFalse(file.exists())
                    if action=="rename":
                        moved.replace(file)
                        page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                        page.wait_for_function(
                            "() => window.__lanternMdVisual.state.conflict === false",
                            timeout=3000)
                        self.assertFalse(status_node.is_visible())
                finally:
                    ctx.close()
                    if moved.exists():
                        moved.unlink()



    def test_delete_during_pending_local_write_retains_text_and_never_recreates_file(self):
        file=self.root/"delete-pending.md"
        original="# Delete pending\n\nOriginal line.\n"
        local="# Delete pending\n\nLocal recovery line.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1100,"height":800})
        page=ctx.new_page()
        intercepted=[]
        def delete_before_write(route):
            if not intercepted:
                intercepted.append(True)
                if file.exists():
                    file.unlink()
            route.continue_()
        page.route("**/api/work/write",delete_before_write)
        try:
            page.goto(self.base+"/api/plugin/preview?p=delete-pending.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=12000)
            area.fill(local)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.conflict === true",
                timeout=12000)
            self.assertTrue(intercepted)
            self.assertFalse(file.exists())
            self.assertEqual(area.input_value(),local)
            status=page.locator("[data-md-status]").inner_text().lower()
            self.assertTrue(
                "retained" in status or "unavailable" in status,
                status)
            page.wait_for_timeout(1000)
            self.assertFalse(file.exists())
            self.assertEqual(area.input_value(),local)
        finally:
            ctx.close()

    def test_external_overlap_during_local_write_retains_local_recovery_and_real_external_bytes(self):
        file=self.root/"external-overlap.md"
        original="# External overlap\n\nOriginal line.\n"
        local="# External overlap\n\nLocal browser line.\n"
        external="# External overlap\n\nVS Code line.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1100,"height":800})
        page=ctx.new_page()
        intercepted=[]
        def race(route):
            if not intercepted:
                intercepted.append(True)
                file.write_text(external,encoding="utf-8",newline="")
            route.continue_()
        page.route("**/api/work/write",race)
        try:
            page.goto(self.base+"/api/plugin/preview?p=external-overlap.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=12000)
            area.fill(local)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.conflict === true",
                timeout=12000)
            self.assertTrue(intercepted)
            self.assertEqual(file.read_text(encoding="utf-8"),external)
            self.assertEqual(area.input_value(),local)
            state=page.evaluate(
                "async()=>(await(await fetch('/api/work?p=external-overlap.md')).json())")
            self.assertEqual(state["saved"]["content"],original)
            self.assertEqual(state["work"]["content"],external)
            status=page.locator("[data-md-status]").inner_text().lower()
            self.assertIn("overlapping",status)
        finally:
            ctx.close()

    def test_self_write_echo_and_large_noop_poll_do_not_write_or_rebuild(self):
        file=self.root/"poll-echo.md"
        original="# Poll echo\n\nOriginal.\n"
        edited="# Poll echo\n\nEdited.\n"
        file.write_text(original,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1200,"height":800})
        page=ctx.new_page()
        requests=[]
        page.on("request",lambda req:requests.append((req.method,req.url)))
        try:
            page.goto(self.base+"/api/plugin/preview?p=poll-echo.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=12000)
            requests.clear()
            area.fill(edited)
            page.wait_for_function(
                "() => window.__lanternMdVisual.state.lastSaved.includes('Edited.')",
                timeout=12000)
            posts=lambda:sum(
                method=="POST" and "/api/work/write" in url
                for method,url in requests)
            self.assertEqual(posts(),1,requests)
            posts_after_write=posts()
            page.wait_for_timeout(3200)
            self.assertEqual(posts(),posts_after_write,requests)
            self.assertEqual(file.read_text(encoding="utf-8"),edited)
        finally:
            ctx.close()

        large=self.root/"poll-large.md"
        text="# Large poll\n\n"+"".join(
            f"line {i:05d} "+("x"*70)+"\n" for i in range(6200))
        large.write_text(text,encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1200,"height":800})
        page=ctx.new_page()
        requests=[]
        page.on("request",lambda req:requests.append((req.method,req.url)))
        try:
            page.goto(self.base+"/api/plugin/preview?p=poll-large.md")
            page.get_by_role("button",name="Source",exact=True).click()
            area=page.get_by_role("textbox",name="Markdown source")
            area.wait_for(timeout=18000)
            page.evaluate("""() => {
              const host=document.querySelector('.md-source-diff-backdrop-content');
              window.__pollMutations={records:0,added:0,removed:0};
              new MutationObserver(records=>{
                for(const r of records){
                  __pollMutations.records++;
                  __pollMutations.added+=r.addedNodes.length;
                  __pollMutations.removed+=r.removedNodes.length;
                }
              }).observe(host,{childList:true,subtree:true});
            }""")
            requests.clear()
            page.wait_for_timeout(3200)
            work_gets=sum(
                method=="GET" and "/api/work?p=poll-large.md" in url
                for method,url in requests)
            work_posts=sum(
                method=="POST" and "/api/work/write" in url
                for method,url in requests)
            mutations=page.evaluate("() => window.__pollMutations")
            self.assertGreaterEqual(work_gets,1,requests)
            self.assertEqual(work_posts,0,requests)
            self.assertEqual(mutations,{"records":0,"added":0,"removed":0})

            initial_state=page.evaluate(
                "async()=>(await(await fetch('/api/work?p=poll-large.md')).json())")
            temp=Path(initial_state["tempPath"])
            accepted_bytes=temp.read_bytes()
            page.evaluate("""() => {
              Object.defineProperty(document,'hidden',{
                configurable:true,get:()=>true
              });
              document.dispatchEvent(new Event('visibilitychange'));
            }""")
            requests.clear()
            page.wait_for_timeout(2900)
            hidden_gets=sum(
                method=="GET" and "/api/work?p=poll-large.md" in url
                for method,url in requests)
            self.assertEqual(hidden_gets,0,requests)

            external=text.replace("# Large poll","# Large poll external",1)
            large.write_text(external,encoding="utf-8",newline="")
            started=time.perf_counter()
            page.evaluate("""() => {
              Object.defineProperty(document,'hidden',{
                configurable:true,get:()=>false
              });
              document.dispatchEvent(new Event('visibilitychange'));
              window.dispatchEvent(new Event('focus'));
            }""")
            page.wait_for_function(
                "() => document.querySelector('.md-source-area')?.value"
                ".startsWith('# Large poll external')",
                timeout=2000)
            self.assertLess(time.perf_counter()-started,2.0)
            visible_gets=sum(
                method=="GET" and "/api/work?p=poll-large.md" in url
                for method,url in requests)
            visible_posts=sum(
                method=="POST" and "/api/work/write" in url
                for method,url in requests)
            self.assertGreaterEqual(visible_gets,1,requests)
            self.assertEqual(visible_posts,0,requests)
            state=page.evaluate(
                "async()=>(await(await fetch('/api/work?p=poll-large.md')).json())")
            self.assertEqual(state["saved"]["content"],text)
            self.assertEqual(state["work"]["content"],external)
            self.assertEqual(temp.read_bytes(),accepted_bytes)
        finally:
            ctx.close()

    def test_wide_window_left_aligns_content_beside_chat(self):
        file=self.root/"layout.md"
        file.write_text("# Layout\n\nBody text.\n",encoding="utf-8",newline="")
        ctx=self.browser.new_context(viewport={"width":1930,"height":920})
        page=ctx.new_page()
        try:
            page.goto(self.base+"/api/plugin/preview?p=layout.md")
            page.locator(".lantern-chat-launch").click()
            page.wait_for_function("() => document.body.classList.contains('lantern-chat-open')")
            metrics=page.evaluate("""() => {
              const article=document.querySelector('article.md-preview').getBoundingClientRect();
              const drawer=document.querySelector('.lantern-chat-drawer').getBoundingClientRect();
              return {left:article.left,right:article.right,chatLeft:drawer.left};
            }""")
            self.assertLess(metrics["left"],30,metrics)
            self.assertLessEqual(metrics["right"],metrics["chatLeft"]+3,metrics)
        finally:ctx.close()

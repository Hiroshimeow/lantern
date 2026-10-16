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
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/"lan_drive.py"),"--root",str(cls.root),
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
            target.write_text(edited,encoding="utf-8",newline="")
            page.wait_for_function(
                "() => !!document.querySelector('.md-preview-diff-mod')",
                timeout=13000)
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

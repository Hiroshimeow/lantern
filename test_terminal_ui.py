from __future__ import annotations

import json
import socket
import subprocess
import sys
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "lan_drive.py"
CLIENT = ROOT / "static" / "terminal_scm.js"


class TerminalUiParityTests(unittest.TestCase):
    def test_legacy_fake_terminal_is_retired(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        forbidden = [
            "termAppend(", "termCSI(", "TerminalSession", "terminal_run_command",
            "/api/term/read", "/api/term/new", "terminal_poll_ms",
        ]
        for token in forbidden:
            self.assertNotIn(token, source, token)
        self.assertIn('parsed.path == "/ws"', source)

    def test_browser_client_uses_xterm_websocket_and_scm_correlation(self) -> None:
        js = CLIENT.read_text(encoding="utf-8")
        self.assertIn("new WebSocket", js)
        self.assertIn("new Terminal(", js)
        self.assertIn("new FitAddon.FitAddon()", js)
        self.assertIn("scrollback:8000", js)
        self.assertIn("terminal_snapshot", js)
        self.assertIn("terminal_run", js)
        self.assertIn("function activeLive()", js)
        self.assertIn("t.meta.running!==false", js)
        self.assertIn("scm_data", js)
        self.assertIn("reqId", js)
        self.assertIn("setInterval", js)
        self.assertNotIn("/api/term/read", js)
        self.assertNotIn("setInterval(termPoll", js)

    def test_replay_guard_is_per_terminal_and_callback_driven(self) -> None:
        js = CLIENT.read_text(encoding="utf-8")
        self.assertIn("replaying:false,replayTok:0", js)
        self.assertIn("if(state.replaying)return", js)
        self.assertIn("const tok=t.replayTok=(t.replayTok||0)+1", js)
        self.assertIn("if(t.replayTok===tok)t.replaying=false", js)
        self.assertNotIn("S.replaying", js)
        self.assertNotIn("setTimeout(finish,80)", js)
        self.assertIn("document.hidden&&data!=='\\x1b[O'", js)

    def test_second_snapshot_cannot_be_unlocked_by_old_replay_callback(self) -> None:
        client = json.dumps(str(CLIENT))
        script = textwrap.dedent(f"""
            const assert = require('assert');
            global.location = {{protocol:'http:', host:'lantern.test'}};
            global.document = {{querySelector:()=>null, addEventListener:()=>{{}}, hidden:false}};
            global.addEventListener = ()=>{{}};
            global.setInterval = ()=>0;
            class FakeWebSocket {{
              static OPEN = 1;
              constructor() {{ this.readyState = 1; this.sent = []; }}
              send(raw) {{ this.sent.push(JSON.parse(raw)); }}
              close() {{}}
            }}
            global.WebSocket = FakeWebSocket;
            require({client});
            const api = global.__lanternTerminalScm;
            const callbacks = [];
            const writes = [];
            const term = {{
              resetCount: 0,
              reset() {{ this.resetCount++; }},
              write(data, cb) {{ writes.push(data); callbacks.push(cb); }},
            }};
            const t = {{
              meta: {{id:'b', title:'B', running:true}},
              term,
              host: {{offsetWidth:0, offsetHeight:0, classList:{{toggle:()=>{{}},contains:()=>false}}}},
              ro: {{disconnect:()=>{{}}}},
              pending:false, replaying:false, replayTok:0, fitQueued:false,
            }};
            api.state.terms.set('b', t);
            api.state.active = 'b';
            api.handleMessage({{type:'terminal_snapshot', terminals:[{{id:'b',title:'B',running:true}}], output:{{b:'first'}}}});
            assert.equal(t.replaying, true);
            assert.equal(t.replayTok, 1);
            api.handleMessage({{type:'terminal_snapshot', terminals:[{{id:'b',title:'B',running:true}}], output:{{b:'second'}}}});
            assert.equal(t.replaying, true);
            assert.equal(t.replayTok, 2);
            assert.deepEqual(writes, ['first','second']);
            callbacks[0]();
            assert.equal(t.replaying, true, 'old replay callback must not unlock newer snapshot');
            callbacks[1]();
            assert.equal(t.replaying, false);
            assert.equal(term.resetCount, 2);
        """)
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_browser_client_parses_as_javascript(self) -> None:
        result = subprocess.run(
            ["node", "--check", str(CLIENT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_history_reloads_after_visible_git_terminal_exit(self) -> None:
        client = json.dumps(str(CLIENT))
        script = textwrap.dedent(f"""
            const assert = require('assert');
            global.location = {{protocol:'http:', host:'lantern.test'}};
            global.document = {{querySelector:()=>null, addEventListener:()=>{{}}, hidden:false}};
            global.addEventListener = ()=>{{}};
            global.setInterval = ()=>0;
            global.testCwd = 'repo-a';
            global.currentPath = ()=>global.testCwd;
            class FakeWebSocket {{
              static OPEN = 1;
              constructor() {{ this.readyState = 1; this.sent = []; }}
              send(raw) {{ this.sent.push(JSON.parse(raw)); }}
              close() {{}}
            }}
            global.WebSocket = FakeWebSocket;
            require({client});
            const api = global.__lanternTerminalScm;
            const state = api.state;
            const sleep = ms => new Promise(r=>setTimeout(r, ms));
            const latest = type => [...state.ws.sent].reverse().find(m=>m.type===type);
            (async()=>{{
              state.scm.cwd = 'repo-a';
              state.scm.tab = 'history';
              state.scm.status = {{branch:'main', files:[]}};
              state.scm.history = [{{subject:'init'}}];
              state.terms.set('git-commit', {{
                meta: {{command:\"git add -A && git commit -m 'next'\", running:true}},
                term: {{write:()=>{{}}}}
              }});
              api.handleMessage({{type:'terminal_exit', terminalId:'git-commit', exitCode:0}});
              await sleep(160);
              const statusReq = latest('scm_status');
              assert(statusReq, 'git terminal exit must silently refresh SCM status');
              assert.equal(statusReq.cwd, 'repo-a');
              api.handleMessage({{type:'scm_data', reqId:statusReq.reqId, ok:true, data:{{branch:'main', files:[]}}}});
              await sleep(10);
              const historyReq = latest('scm_history');
              assert(historyReq, 'git terminal exit must invalidate/reload loaded history');
              assert.equal(historyReq.cwd, 'repo-a');
              api.handleMessage({{type:'scm_data', reqId:historyReq.reqId, ok:true, data:{{history:[{{subject:'next'}},{{subject:'init'}}]}}}});
              await sleep(10);
              assert.deepEqual(state.scm.history.map(x=>x.subject), ['next','init']);

              state.scm.history = [{{subject:'repo-a'}}];
              global.testCwd = 'repo-b';
              const refresh = api.refreshScm(true, true);
              await sleep(5);
              const repoBStatus = latest('scm_status');
              assert.equal(repoBStatus.cwd, 'repo-b');
              assert.equal(state.scm.history, null, 'cwd switch must invalidate prior history immediately');
              api.handleMessage({{type:'scm_data', reqId:repoBStatus.reqId, ok:true, data:{{branch:'main', files:[]}}}});
              await sleep(5);
              const repoBHistory = latest('scm_history');
              assert.equal(repoBHistory.cwd, 'repo-b');
              api.handleMessage({{type:'scm_data', reqId:repoBHistory.reqId, ok:true, data:{{history:[{{subject:'repo-b'}}]}}}});
              await refresh;
              assert.deepEqual(state.scm.history.map(x=>x.subject), ['repo-b']);

              state.view = 'git';
              state.scm.history = [{{subject:'stale'}}];
              api.handleMessage({{type:'scm_changed'}});
              await sleep(5);
              const changedStatus = latest('scm_status');
              api.handleMessage({{type:'scm_data', reqId:changedStatus.reqId, ok:true, data:{{branch:'main', files:[]}}}});
              await sleep(5);
              const changedHistory = latest('scm_history');
              api.handleMessage({{type:'scm_data', reqId:changedHistory.reqId, ok:true, data:{{history:[{{subject:'external'}}]}}}});
              await sleep(5);
              assert.deepEqual(state.scm.history.map(x=>x.subject), ['external']);
            }})().catch(e=>{{console.error(e); process.exit(1)}});
        """)
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_page_references_versioned_terminal_assets(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        proc = subprocess.Popen(
            [
                sys.executable,
                str(SOURCE),
                "--root",
                str(ROOT),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 8
            html = None
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.5) as response:
                        html = response.read().decode("utf-8")
                    break
                except Exception:
                    time.sleep(0.1)
            self.assertIsNotNone(html, "Lantern test server did not become ready")
            assert html is not None
            self.assertRegex(html, r'/static/terminal_scm\.css\?v=[0-9a-f]{16}')
            self.assertRegex(html, r'/static/terminal_scm\.js\?v=[0-9a-f]{16}')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def test_app_static_assets_revalidate_instead_of_going_stale(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        proc = subprocess.Popen(
            [
                sys.executable,
                str(SOURCE),
                "--root",
                str(ROOT),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 8
            response = None
            while time.time() < deadline:
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/static/terminal_scm.js",
                        method="HEAD",
                    )
                    response = urllib.request.urlopen(request, timeout=0.5)
                    break
                except Exception:
                    time.sleep(0.1)
            self.assertIsNotNone(response, "Lantern test server did not become ready")
            assert response is not None
            with response:
                self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def test_websocket_open_does_not_request_redundant_terminal_snapshot(self) -> None:
        client = json.dumps(str(CLIENT))
        script = textwrap.dedent(f"""
            const assert = require('assert');
            global.location = {{protocol:'http:', host:'lantern.test'}};
            global.document = {{querySelector:()=>null, addEventListener:()=>{{}}, hidden:false}};
            global.addEventListener = ()=>{{}};
            global.setInterval = ()=>0;
            class FakeWebSocket {{
              static OPEN = 1;
              constructor() {{ this.readyState = 1; this.sent = []; }}
              send(raw) {{ this.sent.push(JSON.parse(raw)); }}
              close() {{}}
            }}
            global.WebSocket = FakeWebSocket;
            require({client});
            const state = global.__lanternTerminalScm.state;
            state.ws.onopen();
            assert.equal(
              state.ws.sent.filter(m=>m.type==='terminal_sync').length,
              0,
              'server sends terminal_snapshot on upgrade; client must not request a duplicate replay',
            );
        """)
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reopening_existing_terminal_refocuses_xterm(self) -> None:
        client = json.dumps(str(CLIENT))
        script = textwrap.dedent(f"""
            const assert = require('assert');
            class ClassList {{
              constructor() {{ this.s = new Set(); }}
              add(...xs) {{ xs.forEach(x=>this.s.add(x)); }}
              remove(...xs) {{ xs.forEach(x=>this.s.delete(x)); }}
              contains(x) {{ return this.s.has(x); }}
              toggle(x, force) {{
                if (force === true) {{ this.s.add(x); return true; }}
                if (force === false) {{ this.s.delete(x); return false; }}
                if (this.s.has(x)) {{ this.s.delete(x); return false; }}
                this.s.add(x); return true;
              }}
            }}
            class El {{
              constructor(id='') {{
                this.id=id; this.classList=new ClassList(); this.style={{setProperty:()=>{{}}}};
                this.dataset={{}}; this.children=[]; this.offsetWidth=1200; this.offsetHeight=360;
                this.clientWidth=1200; this.value=''; this.innerHTML=''; this.textContent='';
              }}
              addEventListener() {{}}
              appendChild(x) {{ this.children.push(x); return x; }}
              insertAdjacentElement() {{}}
              remove() {{}}
              getBoundingClientRect() {{ return {{width:1200,height:360}}; }}
              closest() {{ return null; }}
            }}
            const ids = ['termDrawer','lxResize','lxViewTerm','lxViewGit','lxNewTerm','lxKillTerm',
              'lxRenameTerm','lxFull','lxHide','lxScmRefresh','lxPull','lxPush','lxSwitchBranch',
              'lxCommit','lxCommitAll','lxScmView','lxTerminalView','lxTermStack','lxTermTabs',
              'lxConn','lxDims','lxScmDivider','lxScmBody','lxScmSidebar','lxScmList',
              'lxScmDetail','lxBranchChip','lxBranchSelect','lxCommitMsg'];
            const els = new Map(ids.map(id=>['#'+id,new El(id)]));
            global.document = {{
              hidden:false,
              querySelector:(s)=>els.get(s)||null,
              createElement:()=>new El(),
              addEventListener:()=>{{}},
            }};
            global.location = {{protocol:'http:',host:'lantern.test'}};
            global.addEventListener=()=>{{}};
            global.removeEventListener=()=>{{}};
            global.innerHeight=900;
            global.localStorage={{getItem:()=>null,setItem:()=>{{}}}};
            global.crypto={{randomUUID:()=> 'focus-term'}};
            global.ResizeObserver=class {{ observe(){{}} disconnect(){{}} }};
            class FakeTerminal {{
              constructor() {{
                this.cols=80; this.rows=24; this.textarea={{}}; this.focusCount=0;
                this.buffer={{active:{{length:0,getLine:()=>null}}}};
              }}
              loadAddon(){{}} open(){{}} reset(){{}} write(){{}} dispose(){{}}
              attachCustomKeyEventHandler(){{}}
              onData(){{ return {{dispose:()=>{{}}}}; }}
              hasSelection(){{ return false; }}
              focus(){{ this.focusCount++; }}
            }}
            global.Terminal=FakeTerminal;
            global.FitAddon={{FitAddon:class {{ fit(){{}} }}}};
            class FakeWebSocket {{
              static OPEN=1;
              constructor(){{this.readyState=1;this.sent=[];}}
              send(raw){{this.sent.push(JSON.parse(raw));}}
              close(){{}}
            }}
            global.WebSocket=FakeWebSocket;
            global.setInterval=()=>0;
            require({client});
            const sleep=ms=>new Promise(r=>setTimeout(r,ms));
            (async()=>{{
              global.newTerminalSession();
              await sleep(60);
              const state=global.__lanternTerminalScm.state;
              const t=state.terms.get(state.active);
              assert(t, 'terminal should exist');
              const before=t.term.focusCount;
              assert(before>0, 'new terminal should initially focus xterm');
              global.openTerminal();
              await sleep(60);
              assert(t.term.focusCount>before, 'reopening an existing live terminal must refocus xterm');
            }})().catch(e=>{{console.error(e);process.exit(1)}});
        """)
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
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
        self.assertIn('/static/vendor/xterm.js', source)
        self.assertIn('/static/vendor/addon-fit.js', source)
        self.assertIn('/static/terminal_scm.js', source)

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


if __name__ == "__main__":
    unittest.main()

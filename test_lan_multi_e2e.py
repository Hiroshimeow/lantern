"""Opt-in two-browser W1 handshake/navigation E2E; no real terminal spawned."""
from __future__ import annotations
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent

@unittest.skipUnless(os.environ.get("LANTERN_E2E")=="1", "set LANTERN_E2E=1")
class LanMultipleBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp=tempfile.TemporaryDirectory()
        cls.shared=Path(cls.tmp.name)
        (cls.shared/"sub").mkdir()
        with socket.socket() as s:
            s.bind(("127.0.0.1",0))
            cls.port=s.getsockname()[1]
        cls.base=f"http://127.0.0.1:{cls.port}"
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/"lan_drive.py"),
                  "--root",str(cls.shared),"--host","127.0.0.1","--port",str(cls.port)],
                  cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            try:
                with urllib.request.urlopen(cls.base+"/",timeout=0.5): break
            except Exception: time.sleep(0.1)
        else: raise RuntimeError("isolated server did not start")
        cls.play=sync_playwright().start()
        cls.browser=cls.play.chromium.launch(channel="msedge",headless=True)
        cls.c1=cls.browser.new_context()
        cls.c2=cls.browser.new_context()
        cls.a=cls.c1.new_page()
        cls.b=cls.c2.new_page()
        for page in (cls.a,cls.b):
            page.goto(cls.base+"/")
            page.wait_for_function("window.__lanternTerminalScm?.state.connected===true")
            page.evaluate("""() => {
              window.lanProbeMessages=[];
              window.lanProbeWs=new WebSocket('ws://'+location.host+'/ws?v=2');
              window.lanProbeWs.onopen=()=>window.lanProbeWs.send(JSON.stringify({type:'terminal_client_v2'}));
              window.lanProbeWs.onmessage=e=>{try{window.lanProbeMessages.push(JSON.parse(e.data))}catch{}};
            }""")
            page.wait_for_function("window.lanProbeMessages.some(x=>x.type==='terminal_list')")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.c1.close();cls.c2.close();cls.browser.close();cls.play.stop()
        finally:
            cls.proc.terminate()
            try: cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired: cls.proc.kill();cls.proc.wait(timeout=5)
            cls.tmp.cleanup()

    def test_two_contexts_metadata_only_and_lazy_xterm(self):
        for page in (self.a,self.b):
            result=page.evaluate("""() => ({
              metadata:window.lanProbeMessages.filter(x=>x.type==='terminal_list').length,
              snapshots:window.lanProbeMessages.filter(x=>x.type==='terminal_snapshot').length,
              mounted:[...window.__lanternTerminalScm.state.terms.values()].filter(x=>!!x.term).length
            })""")
            self.assertGreaterEqual(result["metadata"],1)
            self.assertEqual(result["snapshots"],0)
            self.assertEqual(result["mounted"],0)
        self.b.goto(self.base+"/sub/")
        self.b.wait_for_function("window.__lanternTerminalScm?.state.connected===true")
        self.assertEqual(self.b.evaluate("()=>[...window.__lanternTerminalScm.state.terms.values()].filter(x=>!!x.term).length"),0)
        self.assertEqual(self.a.evaluate("()=>window.__lanternTerminalScm.state.connected"),True)

    def test_stale_browser_ws_receives_one_legacy_snapshot(self):
        self.a.evaluate("""() => {
            window.legacyFrames=[];
            const ws=new WebSocket('ws://'+location.host+'/ws');
            window.legacyWs=ws;
            ws.onmessage=e=>{try{window.legacyFrames.push(JSON.parse(e.data))}catch{}};
        }""")
        self.a.wait_for_function("window.legacyFrames.some(x=>x.type==='terminal_snapshot')",timeout=4000)
        self.a.wait_for_timeout(400)
        self.assertEqual(self.a.evaluate("()=>window.legacyFrames.filter(x=>x.type==='terminal_snapshot').length"),1)
        self.a.evaluate("window.legacyWs.close()")
        self.a.wait_for_timeout(200)
        for page in (self.a,self.b):
            self.assertEqual(page.evaluate("()=>[...window.__lanternTerminalScm.state.terms.values()].filter(x=>!!x.term).length"),0)


if __name__=="__main__":
    unittest.main()

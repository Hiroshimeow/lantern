"""Edge E2E for remote-only Terminal auth. Runs on isolated 127.0.0.1 server.

The fixture forces remote policy on loopback via terminal_local_bypass: false;
the production default retains localhost's existing no-password behavior.
"""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from lantern.terminal_auth import hash_password

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "Edge E2E opt-in")
class TerminalRemoteAuthBrowserE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lantern-auth-",ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.password = "long-unique-terminal-password"
        self.yaml = self.root / "lan_drive_config.yaml"
        self.yaml.write_text("terminal_local_bypass: false\nterminal_password_hash: \""+
                             hash_password(self.password)+"\"\n",encoding="utf-8")
        (self.root/"visible-file.txt").write_text("FILES STAY OPEN",encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            self.port=sock.getsockname()[1]
        self.url=f"http://127.0.0.1:{self.port}"
        self.proc=subprocess.Popen(
            [sys.executable,str(ROOT/"lan_drive.py"),"--config",str(self.yaml),
             "--root",str(self.root),"--host","127.0.0.1","--port",str(self.port)],
            cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urllib.request.urlopen(self.url+"/api/info",timeout=.5):
                    break
            except Exception:
                time.sleep(.1)
        else:
            self.fail("isolated remote-auth fixture never started")

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.tmp.cleanup()

    def test_explicit_no_password_grants_terminal_without_login(self):
        """Even with loopback bypass disabled, no-password means open Terminal."""
        from playwright.sync_api import sync_playwright
        root=self.root/"passwordless-root"
        root.mkdir()
        config=self.root/"passwordless.yaml"
        config.write_text("terminal_local_bypass: false\nterminal_password_hash: no-password\n",
                          encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            port=sock.getsockname()[1]
        url=f"http://127.0.0.1:{port}"
        proc=subprocess.Popen(
            [sys.executable,str(ROOT/"lan_drive.py"),"--config",str(config),
             "--root",str(root),"--host","127.0.0.1","--port",str(port)],
            cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+"/api/terminal/auth",timeout=.5) as response:
                        status=json.load(response)
                    break
                except Exception:
                    time.sleep(.1)
            else:
                self.fail("isolated no-password fixture never started")
            self.assertEqual(status,{"required":False,"authenticated":True,"configured":False})
            with sync_playwright() as play:
                browser=play.chromium.launch(channel="msedge",headless=True)
                context=browser.new_context()
                try:
                    page=context.new_page()
                    page.goto(url,wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => {const s=window.__lanternTerminalScm?.state;"
                        "return !!s && !s.auth.required && s.auth.authenticated && s.termListReady;}",
                        timeout=18000)
                    self.assertFalse(page.locator("#lxTermAuth").is_visible())
                    page.evaluate("window.newTerminalSession()")
                    page.wait_for_function(
                        "() => [...window.__lanternTerminalScm.state.terms.values()].some("
                        "t=>!t.pending&&t.meta.running&&t.meta.generation)",
                        timeout=18000)
                    self.assertFalse(any(c["name"]=="lantern_terminal" for c in context.cookies()))
                finally:
                    context.close()
                    browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def test_two_ports_same_yaml_cli_no_password_only_unprotects_own_port(self):
        """One process uses the stored hash; --no-password bypasses only its port."""
        from playwright.sync_api import sync_playwright
        original_yaml = self.yaml.read_bytes()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            other_port = sock.getsockname()[1]
        other_url = f"http://127.0.0.1:{other_port}"
        other = subprocess.Popen(
            [sys.executable, str(ROOT / "lan_drive.py"),
             "--config", str(self.yaml), "--root", str(self.root),
             "--host", "127.0.0.1", "--port", str(other_port),
             "--no-password"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(other_url+"/api/terminal/auth", timeout=.5) as res:
                        unprotected = json.load(res)
                    break
                except Exception:
                    if other.poll() is not None:
                        self.fail("Second Lantern process stopped before accepting connections")
                    time.sleep(.1)
            else:
                self.fail("Second Lantern process never started")
            with urllib.request.urlopen(self.url+"/api/terminal/auth", timeout=2) as res:
                protected = json.load(res)
            self.assertEqual(protected,
                             {"required":True,"authenticated":False,"configured":True})
            self.assertEqual(unprotected,
                             {"required":False,"authenticated":True,"configured":False})
            self.assertEqual(self.yaml.read_bytes(),original_yaml,
                             "--no-password must never change the shared configuration")
            with sync_playwright() as play:
                browser=play.chromium.launch(channel="msedge",headless=True)
                try:
                    locked=browser.new_page()
                    locked.goto(self.url,wait_until="domcontentloaded")
                    locked.wait_for_function("() => window.__lanternTerminalScm?.state.auth.required",
                                             timeout=18000)
                    locked.evaluate("window.toggleTerminal()")
                    locked.locator("#lxTermAuth").wait_for(state="visible",timeout=10000)
                    opened=browser.new_page()
                    opened.goto(other_url,wait_until="domcontentloaded")
                    opened.wait_for_function("""() => {
                        const s=window.__lanternTerminalScm?.state;
                        return !!s && !s.auth.required && s.auth.authenticated && s.termListReady;
                    }""",timeout=18000)
                    opened.evaluate("window.toggleTerminal()")
                    self.assertFalse(opened.locator("#lxTermAuth").is_visible())
                    self.assertEqual(self.yaml.read_bytes(), original_yaml)
                finally:
                    browser.close()
        finally:
            other.terminate()
            try:
                other.wait(timeout=6)
            except subprocess.TimeoutExpired:
                other.kill()
                other.wait(timeout=5)

    def test_locked_ws_unlocked_terminal_logout_files_remain_open(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser=play.chromium.launch(channel="msedge",headless=True)
            context=browser.new_context()
            page=context.new_page()
            js_errors=[]
            page.on("pageerror",lambda err:js_errors.append(str(err)))
            try:
                page.goto(self.url,wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__lanternTerminalScm?.state.auth.required === true && "
                    "window.__lanternTerminalScm?.state.auth.configured === true",timeout=18000)
                state=page.evaluate("""() => {
                    const s=window.__lanternTerminalScm.state;
                    return {authed:s.auth.authenticated,ready:s.termListReady,count:s.terms.size}
                }""")
                self.assertEqual(state,{"authed":False,"ready":False,"count":0})
                # No auth is needed for normal file access.
                with urllib.request.urlopen(self.url+"/visible-file.txt") as response:
                    self.assertEqual(response.read(),b"FILES STAY OPEN")
                with urllib.request.urlopen(self.url+"/api/config") as response:
                    self.assertNotIn("terminal_password_hash",response.read().decode())
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(self.url+"/lan_drive_config.yaml")
                self.assertEqual(denied.exception.code,403)
                denied.exception.close()
                with urllib.request.urlopen(self.url+"/api/list?path=") as response:
                    names=json.dumps(json.load(response))
                    self.assertIn("visible-file.txt",names)
                    self.assertNotIn("lan_drive_config.yaml",names)

                page.evaluate("""() => {
                    window.__denied=[];
                    window.__lanternTerminalScm.state.ws.addEventListener('message',e=>{
                        try{window.__denied.push(JSON.parse(e.data))}catch(_){}
                    });
                    window.__lanternTerminalScm.state.ws.send(JSON.stringify({
                        type:'terminal_create',terminalId:'unauthorized',cwd:''}));
                    window.__lanternTerminalScm.state.ws.send(JSON.stringify({
                        type:'terminal_sync'}));
                    window.__lanternTerminalScm.state.ws.send(JSON.stringify({
                        type:'scm_status',reqId:'probe',cwd:''}));
                }""")
                page.wait_for_function(
                    "() => window.__denied.some(m=>m.type==='terminal_error')"
                    " && window.__denied.some(m=>m.type==='scm_data')",timeout=12000)
                events=page.evaluate("window.__denied")
                self.assertFalse(any(m.get("type") in ("terminal_list","terminal_replay","terminal_snapshot") for m in events))
                self.assertFalse(any(m.get("type")=="terminal_created" for m in events))
                page.evaluate("window.toggleTerminal()")
                panel=page.locator("#lxTermAuth")
                panel.wait_for(state="visible",timeout=6000)
                self.assertTrue(page.locator("#lxNewTerm").is_disabled())
                page.locator("#lxTermPassword").fill("wrong-secret")
                page.locator("#lxTermAuthSubmit").click()
                page.locator("#lxTermAuthMessage").filter(has_text="Incorrect password").wait_for(timeout=15000)
                self.assertFalse(page.evaluate("() => document.cookie.includes('lantern_terminal')"))

                page.locator("#lxTermPassword").fill(self.password)
                page.locator("#lxTermAuthSubmit").click()
                page.wait_for_function(
                    "() => window.__lanternTerminalScm.state.auth.authenticated && "
                    "window.__lanternTerminalScm.state.termListReady",timeout=15000)
                panel.wait_for(state="hidden")
                self.assertFalse(page.evaluate("() => document.cookie.includes('lantern_terminal')"))
                cookies=context.cookies()
                secret_cookie=[c for c in cookies if c["name"]=="lantern_terminal"]
                self.assertEqual(len(secret_cookie),1)
                self.assertTrue(secret_cookie[0]["httpOnly"])
                self.assertEqual(secret_cookie[0]["sameSite"],"Strict")
                page.evaluate("window.newTerminalSession()")
                page.wait_for_function(
                    "() => [...window.__lanternTerminalScm.state.terms.values()].some("
                    "t=>!t.pending&&t.meta.running&&t.meta.generation)",timeout=18000)
                self.assertFalse(any("terminal_auth" in str(err) for err in js_errors))

                page.locator("#lxTermLock").click()
                page.wait_for_function(
                    "() => window.__lanternTerminalScm.state.auth.required"
                    " && !window.__lanternTerminalScm.state.auth.authenticated",timeout=15000)
                panel.wait_for(state="visible",timeout=15000)
                page.wait_for_function(
                    "() => window.__lanternTerminalScm.state.terms.size===0",timeout=8000)
                self.assertEqual(js_errors,[],js_errors)
            finally:
                context.close();browser.close()


if __name__ == "__main__":
    unittest.main()

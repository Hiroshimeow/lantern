from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from lantern.application import make_application
from lantern.http.server import LanternHTTPServer, Handler
from lantern.config import AppConfig

ROOT = Path(__file__).resolve().parent.parent


class LanbotV4RealUserE2ETests(unittest.TestCase):
    """End-to-End (E2E) test simulating a real user interacting with Lantern & Lanbot v4
    over live HTTP and WebSocket connections."""

    def test_real_user_e2e_workflow_http_markdown_diff_and_lanbot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)
            spec_md = docs_dir / "architecture.md"
            spec_md.write_text(
                "# Verified ownership\n\n"
                "| Area | Owner / boundary |\n"
                "| --- | --- |\n"
                "| Browser terminal input | `static/terminal_scm.js` |\n"
                "| Vendored xterm internals | `static/vendor/xterm.js` |\n",
                encoding="utf-8",
            )

            # Create fake Pi CLI that also rejects --no-mcp initially to test auto-recovery E2E
            fake_pi = root / "fake_pi_e2e.py"
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
                "    rtype = req.get('type')\n"
                "    rid = req.get('id', '1')\n"
                "    if rtype == 'get_state':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':rid,'command':'get_state','success':True,'data':{'sessionId':'e2e-sess-1','sessionFile':None,'model':{'provider':'anthropic','id':'claude-sonnet-4-5','name':'Claude Sonnet 4.5'}}}) + '\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif rtype == 'get_available_models':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':rid,'command':'get_available_models','success':True,'data':{'models':[{'provider':'anthropic','id':'claude-sonnet-4-5','name':'Claude Sonnet 4.5','reasoning':True}]}}) + '\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif rtype == 'get_messages':\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':rid,'command':'get_messages','success':True,'data':{'messages':[{'role':'user','content':'Hello Lanbot'},{'role':'assistant','content':[{'type':'thinking','thinking':'Analyzing table...'},{'type':'text','text':'I reviewed `docs/architecture.md` at line 5.'}]}]}}) + '\\n')\n"
                "        sys.stdout.flush()\n"
                "    else:\n"
                "        sys.stdout.write(json.dumps({'type':'response','id':rid,'command':str(rtype),'success':True,'data':{}}) + '\\n')\n"
                "        sys.stdout.flush()\n",
                encoding="utf-8",
            )
            fake_pi.chmod(0o755)

            old_env = os.environ.get("LANTERN_PI_COMMAND")
            os.environ["LANTERN_PI_COMMAND"] = str(fake_pi)
            cfg = AppConfig(
                root=root,
                host="127.0.0.1",
                port=0,
                title="Lantern E2E",
                cache_dir=root / ".cache",
                config_path=root / "config.yaml",
            )
            app = make_application(cfg)
            server = LanternHTTPServer(('127.0.0.1', 0), Handler, app)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            base_url = f"http://127.0.0.1:{port}"
            try:
                # 1. User opens Markdown preview page
                with urllib.request.urlopen(f"{base_url}/api/plugin/preview?p=docs/architecture.md") as resp:
                    self.assertEqual(resp.status, 200)
                    html = resp.read().decode("utf-8")
                    self.assertIn("/static/chatbot.js", html)
                    self.assertIn("/static/markdown_visual_shell.js", html)

                # 2. User checks system telemetry (/api/sysstats)
                with urllib.request.urlopen(f"{base_url}/api/sysstats") as resp:
                    self.assertEqual(resp.status, 200)
                    stats = json.loads(resp.read().decode("utf-8"))
                    self.assertIn("cpu", stats)
                    self.assertIn("memory", stats)

                # 3. User updates Lanbot Custom System Prompt & Skills in Settings (/api/chatbot/prefs)
                prefs_req = urllib.request.Request(
                    f"{base_url}/api/chatbot/prefs",
                    data=json.dumps({
                        "customSystemPrompt": "Always reply in clear English.",
                        "useGlobalSkills": True,
                        "customSkillPaths": ["skills/custom"],
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Origin": base_url},
                    method="POST",
                )
                with urllib.request.urlopen(prefs_req) as resp:
                    self.assertEqual(resp.status, 200)
                    prefs_data = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(prefs_data["ok"])
                    self.assertEqual(prefs_data["prefs"]["customSystemPrompt"], "Always reply in clear English.")

                # 4. User pastes an image into Lanbot (/api/chatbot/upload)
                png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                up_req = urllib.request.Request(
                    f"{base_url}/api/chatbot/upload",
                    data=json.dumps({
                        "files": [{
                            "name": "pasted-e2e.png",
                            "type": "image/png",
                            "source": "paste",
                            "dataBase64": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
                        }]
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Origin": base_url},
                    method="POST",
                )
                with urllib.request.urlopen(up_req) as resp:
                    self.assertEqual(resp.status, 200)
                    up_data = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(up_data["ok"])
                    self.assertEqual(len(up_data["attachments"]), 1)

                # 5. User edits Markdown in Visual/Source mode (/api/work/write) without conversion popup
                with urllib.request.urlopen(f"{base_url}/api/work?p=docs/architecture.md") as resp:
                    w_state = json.loads(resp.read().decode("utf-8"))
                base_ver = w_state["saved"]["version"]

                edited_md = (
                    "# Verified ownership\n\n"
                    "| Area | Owner / boundary |\n"
                    "| --- | --- |\n"
                    "| Browser terminal input | `static/terminal_scm.js` (Updated in v4) |\n"
                    "| Vendored xterm internals | `static/vendor/xterm.js` |\n"
                )
                write_req = urllib.request.Request(
                    f"{base_url}/api/work/write",
                    data=json.dumps({
                        "path": "docs/architecture.md",
                        "content": edited_md,
                        "expectHash": None,
                        "baseVersion": base_ver,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Origin": base_url},
                    method="POST",
                )
                with urllib.request.urlopen(write_req) as resp:
                    self.assertEqual(resp.status, 200)
                    w_res = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(w_res["state"], "pending")

                # 6. User exports full unabbreviated HTML session transcript (/api/chatbot/export)
                with urllib.request.urlopen(f"{base_url}/api/chatbot/export") as resp:
                    self.assertEqual(resp.status, 200)
                    export_html = resp.read().decode("utf-8")
                    self.assertIn("e2e-sess-1", export_html)
                    self.assertIn("Hello Lanbot", export_html)
                    self.assertIn("Analyzing table...", export_html)
                    self.assertIn("docs/architecture.md", export_html)

                # 7. User opens standalone Pop-out Lanbot window (/chat)
                with urllib.request.urlopen(f"{base_url}/chat?client_session=tab-e2e&path=docs/architecture.md&kind=markdown") as resp:
                    self.assertEqual(resp.status, 200)
                    chat_html = resp.read().decode("utf-8")
                    self.assertIn("lantern-chat-standalone", chat_html)
                    self.assertIn("tab-e2e", chat_html)
                    self.assertIn("/static/chatbot.js", chat_html)
            finally:
                server.shutdown()
                server.server_close()
                app.close()
                if old_env is None:
                    os.environ.pop("LANTERN_PI_COMMAND", None)
                else:
                    os.environ["LANTERN_PI_COMMAND"] = old_env


if __name__ == "__main__":
    unittest.main()

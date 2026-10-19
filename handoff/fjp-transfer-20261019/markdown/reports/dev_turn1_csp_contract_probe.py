"""DEV turn 1: nondestructive browser proof of 001 CSP vs interactive Markdown contract."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("dev_turn1_csp_contract_probe.json")
result = {"cases": {}, "identity": {"python": sys.version.split()[0]}, "errors": []}


class PageTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def meta_contract(body):
    parser = PageTags()
    parser.feed(body)
    metas = [attrs for tag, attrs in parser.tags if tag == "meta" and
             attrs.get("http-equiv", "").lower() == "content-security-policy"]
    scripts = [attrs for tag, attrs in parser.tags if tag == "script"]
    assert len(metas) == 1, f"expected 1 CSP meta, got {len(metas)}"
    policy = metas[0]["content"]
    token = re.search(r"script-src 'nonce-([^']+)'", policy)
    assert token, policy
    assert scripts and all(a.get("nonce") == token.group(1) for a in scripts), scripts
    return {"csp_meta": policy, "script_count": len(scripts),
            "all_nonce_match": True, "csp_response_header": ""}


JS_PROBE = """async () => {
  const result = {};
  result.websocket = await new Promise(resolve => {
    let done = false;
    const finish = v => { if (done) return; done = true; resolve(v); };
    try {
      const ws = new WebSocket('ws://' + location.host + '/ws');
      ws.onopen = () => { ws.close(); finish('opened'); };
      ws.onerror = () => finish('blocked');
      setTimeout(() => { try { ws.close(); } catch {} finish('timeout'); }, 1800);
    } catch (error) { finish('exception:' + error.name); }
  });
  try {
    const resp = await fetch('/api/info', {cache: 'no-store'});
    result.fetch = resp.ok ? 'ok' : 'http-' + resp.status;
  } catch (error) { result.fetch = 'blocked:' + error.name; }
  try {
    const worker = new Worker('/static/vendor/lantern-md-segment-worker.min.js');
    worker.terminate();
    result.worker = 'created';
  } catch (error) { result.worker = 'blocked:' + error.name; }
  return result;
}"""


with tempfile.TemporaryDirectory(prefix="lantern-csp-contract-") as td:
    folder = Path(td)
    root = folder / "files"
    root.mkdir()
    (root / "probe.md").write_text("# CSP probe\n\nThis document must be editable.\n", encoding="utf-8")
    (root / "probe.txt").write_text("CSP read-only probe\n", encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    cmd = [sys.executable, str(REPO / "main.py"), "--root", str(root),
           "--host", "127.0.0.1", "--port", str(port),
           "--config", str(folder / "config.yaml"), "--cache-dir", str(folder / "cache")]
    proc = subprocess.Popen(cmd, cwd=REPO,
                            env={**os.environ, "LANTERN_WORK_DIR": str(folder / "work")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for attempt in range(100):
            try:
                with urllib.request.urlopen(base + "/api/info", timeout=.7) as response:
                    assert response.status == 200
                break
            except Exception:
                if proc.poll() is not None:
                    raise RuntimeError(f"disposable server exited: {proc.returncode}")
                time.sleep(.1)
        else:
            raise RuntimeError("disposable server did not start")
        result["identity"]["ephemeral_port"] = port
        for key, path in [("read_only_text", "/api/plugin/preview?p=probe.txt"),
                          ("interactive_markdown", "/api/plugin/preview?p=probe.md")]:
            with urllib.request.urlopen(base + path, timeout=5) as response:
                body = response.read().decode("utf-8")
                headers = response.headers
            result["cases"][key] = meta_contract(body)
            result["cases"][key]["csp_response_header"] = headers.get("content-security-policy", "")
            result["cases"][key]["has_three_modes"] = 'data-action="mode-source"' in body
        # A new server render must have a new, unique per-response nonce.
        with urllib.request.urlopen(base + "/api/plugin/preview?p=probe.md", timeout=5) as response:
            other = meta_contract(response.read().decode("utf-8"))
        assert result["cases"]["interactive_markdown"]["csp_meta"] != other["csp_meta"]
        result["fresh_nonce"] = True
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            result["identity"]["edge"] = browser.version
            try:
                for key, url in [
                    ("read_only_text", "/api/plugin/preview?p=probe.txt"),
                    ("interactive_markdown", "/api/plugin/preview?p=probe.md"),
                    ("forced_001_on_markdown", "/api/plugin/preview?p=probe.md")
                ]:
                    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                    try:
                        if key == "forced_001_on_markdown":
                            def substitute(route):
                                response = route.fetch()
                                raw = response.text()
                                old = "connect-src &#x27;self&#x27;; worker-src &#x27;self&#x27;; "
                                assert old in raw, "target policy not found"
                                route.fulfill(response=response, body=raw.replace(
                                    old, "connect-src &#x27;none&#x27;; ", 1))
                            ctx.route("**/api/plugin/preview?*", substitute)
                        page = ctx.new_page()
                        console = []
                        page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:220]}) if msg.type == "error" else None)
                        page.goto(base + url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(300)
                        data = page.evaluate(JS_PROBE)
                        data["meta_csp"] = page.locator("meta[http-equiv='Content-Security-Policy']").get_attribute("content")
                        data["has_source_button"] = page.locator('[data-action="mode-source"]').count() == 1
                        data["console_errors"] = console[:12]
                        result["cases"].setdefault(key, {}).update(data)
                    finally:
                        ctx.close()
            finally:
                browser.close()
        plain = result["cases"]["read_only_text"]
        normal = result["cases"]["interactive_markdown"]
        forced = result["cases"]["forced_001_on_markdown"]
        assert "connect-src 'none'" in plain["csp_meta"]
        assert plain["websocket"] == "blocked", plain
        assert plain["fetch"].startswith("blocked"), plain
        assert normal["has_source_button"] and "connect-src 'self'" in normal["csp_meta"]
        assert normal["websocket"] == "opened" and normal["fetch"] == "ok", normal
        assert normal["worker"] == "created", normal
        assert forced["has_source_button"] and "connect-src 'none'" in forced["meta_csp"]
        assert forced["websocket"] == "blocked" and forced["fetch"].startswith("blocked"), forced
        assert any("Creating a worker" in err["text"] for err in forced["console_errors"]), forced
        result["proven"] = "spec conflict: restrictive 001 policy breaks interactive 003 dependencies"
    except Exception as error:
        result["errors"].append(repr(error))
        raise
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))

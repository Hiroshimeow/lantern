"""Frozen black-box behavior captured from original lan_drive.py at fb06c40.

Do not rewrite the oracle when refactoring main.py. Recording requires an
explicit --record-legacy argument, and only reads the original entrypoint.
"""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "tests" / "fixtures" / "foundation_http_oracle.json"


def probe(entry: Path):
    with tempfile.TemporaryDirectory(prefix="lantern-foundation-oracle-") as tmp:
        root = Path(tmp) / "files"
        root.mkdir()
        (root / "doc.md").write_bytes(b"# Test heading\n\nOriginal body.\n")
        (root / "note.txt").write_bytes(b"File bytes 0123456789.")
        with socket.socket() as sk:
            sk.bind(("127.0.0.1", 0))
            port = sk.getsockname()[1]
        cmd = [sys.executable, str(entry), "--root", str(root), "--port", str(port),
               "--host", "127.0.0.1", "--cache-dir", str(Path(tmp) / "cache"),
               "--config", str(Path(tmp) / "machine.yaml")]
        process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        def request(method, target, data=None, headers=None):
            payload = None if data is None else json.dumps(data).encode("utf-8")
            rh = dict(headers or {})
            if payload is not None:
                rh["Content-Type"] = "application/json"
            req = urllib.request.Request(base + target, data=payload, headers=rh,
                                         method=method)
            try:
                response = urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body = response.read()
                return {
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "accept_ranges": response.headers.get("Accept-Ranges", ""),
                    "cache_control": response.headers.get("Cache-Control", ""),
                    "body": body,
                }
        try:
            for _ in range(120):
                try:
                    candidate = request("GET", "/api/info")
                    if candidate["status"] == 200:
                        break
                except (OSError, TimeoutError):
                    if process.poll() is not None:
                        raise AssertionError(f"App exited unexpectedly: {process.returncode}")
                    time.sleep(.1)
            else:
                raise AssertionError("App failed to bind test port")
            record = {}
            for name, endpoint in (
                ("info", "/api/info"), ("terminal_auth", "/api/terminal/auth"),
                ("plugin_info", "/api/plugin/info"),
                ("list", "/api/list?p=/"),
                ("work", "/api/work?p=doc.md"),
                ("md_document", "/api/md/document?p=doc.md"),
                ("plugin_preview", "/api/plugin/preview?p=doc.md"),
                ("browse", "/"),
                ("direct_file", "/note.txt"),
                ("range_file", "/note.txt"),
                ("chat_asset", "/static/chatbot.js"),
                ("missing", "/file-missing.txt"),
            ):
                headers = {"Range": "bytes=3-7"} if name == "range_file" else {}
                item = request("GET", endpoint, headers=headers)
                if item["status"] >= 500:
                    raise AssertionError(f"{name}: " + item["body"][:1200].decode("utf-8", "replace"))
                rep = {
                    "status": item["status"],
                    "content_type": item["content_type"],
                    "accept_ranges": item["accept_ranges"],
                    "cache_control": item["cache_control"],
                }
                if name in ("direct_file", "range_file", "chat_asset"):
                    rep["sha256"] = hashlib.sha256(item["body"]).hexdigest()
                if name in ("info", "terminal_auth", "plugin_info", "list", "work", "md_document"):
                    data = json.loads(item["body"])
                    rep["top_keys"] = sorted(data)
                    if name == "info":
                        rep["app"] = data["app"]
                        rep["defaults"] = data["defaults"]
                        rep["terminal"] = data["terminal"]
                        rep["plugin_enabled"] = data["plugin"]["enabled"]
                    elif name == "list":
                        rep["items_names"] = sorted(x.get("name") for x in data.get("items", []))
                    elif name == "work":
                        rep["state"] = data.get("state")
                        rep["content"] = (data.get("work") or data.get("saved") or {}).get("content")
                    elif name == "md_document":
                        rep["content"] = data.get("content")
                if name in ("browse", "plugin_preview"):
                    rep["has_chat_script"] = b"/static/chatbot.js" in item["body"]
                record[name] = rep
            first = request("GET", "/api/work?p=doc.md")
            state = json.loads(first["body"])
            before = b"# Test heading\n\nOriginal body.\n"
            edited = "# Test heading\n\nUpdated body.\n"
            written = request("POST", "/api/work/write", {
                "path": "doc.md", "content": edited, "baseVersion": state["saved"]["version"],
                "expectHash": state.get("work", {}).get("hash") if state.get("work") else None,
            })
            record["write"] = {
                "status": written["status"],
                "top_keys": sorted(json.loads(written["body"])),
                "disk_updated": (root / "doc.md").read_text(encoding="utf-8") == edited,
            }
            current = json.loads(request("GET", "/api/work?p=doc.md")["body"])
            record["before_accept"] = {
                "state": current["state"],
                "md_temp_unchanged": current["saved"]["content"].encode("utf-8") == before,
            }
            saved = request("POST", "/api/work/save", {
                "path": "doc.md",
                "expectHash": json.loads(written["body"])["hash"],
                "expectSavedVersion": current["saved"]["version"],
            })
            after = json.loads(request("GET", "/api/work?p=doc.md")["body"])
            record["accept"] = {
                "status": saved["status"],
                "top_keys": sorted(json.loads(saved["body"])),
                "state": after["state"],
                "saved_updated": after["saved"]["content"] == edited,
            }
            return record
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


class AppHttpContractTests(unittest.TestCase):
    def test_refactor_matches_frozen_legacy_server_oracle(self):
        expected = json.loads(ORACLE.read_text(encoding="utf-8"))
        got = probe(ROOT / "main.py")
        for key in expected:
            with self.subTest(key=key):
                self.assertEqual(got.get(key), expected[key])


if __name__ == "__main__":
    unittest.main()

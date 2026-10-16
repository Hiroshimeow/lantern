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
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WorkingCopyHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.root = base / "root"
        cls.root.mkdir()
        cls.work = base / "work"
        (cls.root / "doc.md").write_text("# Saved\n\nold\n", encoding="utf-8")
        (cls.root / "paged.md").write_text("# Paged\n\nreal\n", encoding="utf-8")
        (cls.root / "notes.txt").write_text("text\n", encoding="utf-8")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ)
        env["LANTERN_WORK_DIR"] = str(cls.work)
        cls.proc = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "lan_drive.py"),
                "--root",
                str(cls.root),
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(cls.base + "/api/info", timeout=0.5):
                    return
            except Exception:
                time.sleep(0.1)
        cls.tearDownClass()
        raise RuntimeError("working-copy API server did not start")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "proc"):
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=4)
        if hasattr(cls, "tmp"):
            for attempt in range(8):
                try:
                    cls.tmp.cleanup()
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(0.25)

    def get_work(self, path: str):
        url = self.base + "/api/work?p=" + urllib.parse.quote(path)
        with urllib.request.urlopen(url, timeout=4) as response:
            return json.load(response)

    def post(self, route: str, payload: dict):
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.load(response)

    def error(self, route: str, payload: dict):
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=4)
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.load(exc)
            finally:
                exc.close()
        self.fail("expected HTTP error")

    def test_http_working_copy_save_and_discard(self):
        real = self.root / "doc.md"
        original = real.read_text(encoding="utf-8")
        clean = self.get_work("doc.md")
        self.assertEqual(clean["state"], "clean")
        self.assertIsNone(clean["work"])

        write = self.post(
            "/api/work/write",
            {
                "path": "doc.md",
                "content": "# Saved\n\nfirst draft\n",
                "expectHash": None,
                "baseVersion": clean["saved"]["version"],
            },
        )
        self.assertEqual(real.read_text(encoding="utf-8"), original)
        pending = self.get_work("doc.md")
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(pending["work"]["hash"], write["hash"])

        code, stale = self.error(
            "/api/work/write",
            {
                "path": "doc.md",
                "content": "# Saved\n\nstale\n",
                "expectHash": "0" * 64,
                "baseVersion": clean["saved"]["version"],
            },
        )
        self.assertEqual(code, 409)
        self.assertEqual(stale["reason"], "stale")

        saved = self.post(
            "/api/work/save",
            {
                "path": "doc.md",
                "expectHash": pending["work"]["hash"],
                "expectSavedVersion": clean["saved"]["version"],
            },
        )
        self.assertEqual(saved["state"], "clean")
        self.assertEqual(real.read_text(encoding="utf-8"), "# Saved\n\nfirst draft\n")
        self.assertEqual(self.get_work("doc.md")["state"], "clean")

        base = self.get_work("doc.md")["saved"]["version"]
        second = self.post(
            "/api/work/write",
            {
                "path": "doc.md",
                "content": "# Saved\n\nsecond draft\n",
                "expectHash": None,
                "baseVersion": base,
            },
        )
        self.post(
            "/api/work/discard",
            {"path": "doc.md", "expectHash": second["hash"]},
        )
        self.assertEqual(real.read_text(encoding="utf-8"), "# Saved\n\nfirst draft\n")
        self.assertEqual(self.get_work("doc.md")["state"], "clean")

    def test_legacy_markdown_save_refuses_pending_working_copy(self):
        real = self.root / "paged.md"
        original = real.read_text(encoding="utf-8")
        clean = self.get_work("paged.md")
        pending = self.post(
            "/api/work/write",
            {
                "path": "paged.md",
                "content": "# Paged\n\npending\n",
                "expectHash": None,
                "baseVersion": clean["saved"]["version"],
            },
        )
        code, payload = self.error(
            "/api/md/save",
            {
                "path": "paged.md",
                "content": "# Paged\n\nsection editor overwrite\n",
                "version": clean["saved"]["version"],
            },
        )
        self.assertEqual(code, 409)
        self.assertEqual(payload["reason"], "working_copy_pending")
        self.assertEqual(real.read_text(encoding="utf-8"), original)
        self.post(
            "/api/work/discard",
            {"path": "paged.md", "expectHash": pending["hash"]},
        )

    def test_runtime_allowlist_is_markdown_only_for_now(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get_work("notes.txt")
        self.assertEqual(caught.exception.code, 415)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()

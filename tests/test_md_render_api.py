from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class MarkdownDraftRenderApiTests(unittest.TestCase):
    def test_unsaved_markdown_renders_with_anchors_without_touching_real_file(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            shared = Path(tmp) / "shared"
            shared.mkdir()
            target = shared / "doc.md"
            saved = "# Saved\n\nOriginal body\n"
            target.write_text(saved, encoding="utf-8")

            config = Path(tmp) / "config.yaml"
            port = free_port()
            config.write_text(
                "\n".join(
                    [
                        f'root: "{shared.as_posix()}"',
                        f"port: {port}",
                        'host: "127.0.0.1"',
                        'title: "Lantern Draft Render Test"',
                        'cache_dir: ""',
                        "terminal_enabled: false",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "lan_drive.py"), "--config", str(config)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                deadline = time.time() + 8
                while True:
                    try:
                        with urllib.request.urlopen(base + "/api/info", timeout=0.5) as response:
                            if response.status == 200:
                                break
                    except Exception:
                        if time.time() >= deadline:
                            self.fail("Lantern draft render test server did not become ready")
                        time.sleep(0.1)

                draft = "# Draft heading\n\nChanged body\n\n[local](./asset.txt)\n"
                body = json.dumps({"path": "doc.md", "content": draft}).encode("utf-8")
                request = urllib.request.Request(
                    base + "/api/md/render",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    payload = json.load(response)

                html = payload["html"]
                self.assertIn("Draft heading", html)
                self.assertIn("Changed body", html)
                self.assertNotIn("Original body", html)
                self.assertIn('data-l="1"', html)
                self.assertIn('href="/asset.txt"', html)
                self.assertEqual(target.read_text(encoding="utf-8"), saved)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()

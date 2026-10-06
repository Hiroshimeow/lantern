import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class HttpMutationSecurityTests(unittest.TestCase):
    def test_cross_origin_post_is_rejected_without_breaking_cli_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared"
            shared.mkdir()
            config = Path(tmp) / "config.yaml"
            port = free_port()
            config.write_text(
                "\n".join(
                    [
                        f'root: "{shared.as_posix()}"',
                        f"port: {port}",
                        'host: "127.0.0.1"',
                        'title: "Lantern Security Test"',
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
                            self.fail("Lantern security test server did not become ready")
                        time.sleep(0.1)

                evil_body = json.dumps({"path": "", "name": "evil.txt"}).encode()
                evil = urllib.request.Request(
                    base + "/api/newfile",
                    data=evil_body,
                    method="POST",
                    headers={
                        "Content-Type": "text/plain",
                        "Origin": "http://evil.example",
                    },
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(evil, timeout=2)
                self.assertEqual(caught.exception.code, 403)
                caught.exception.close()
                self.assertFalse((shared / "evil.txt").exists())

                cli_body = json.dumps({"path": "", "name": "cli.txt"}).encode()
                cli = urllib.request.Request(
                    base + "/api/newfile",
                    data=cli_body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(cli, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                self.assertTrue((shared / "cli.txt").exists())
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()

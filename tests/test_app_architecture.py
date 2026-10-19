"""Lantern composition and module boundaries (no legacy facade)."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_single_entrypoint_and_no_module_runtime_globals(self):
        self.assertFalse((ROOT / "lan_drive.py").exists())
        self.assertTrue((ROOT / "main.py").is_file())
        names = {"CONFIG", "WS_HUB", "TERM_MANAGER", "CHAT_MANAGER",
                 "SCM_SERVICE", "WORK_STORE", "HEAVY_PREVIEW_SLOTS"}
        for path in (
            ROOT / "lantern" / "application.py",
            ROOT / "lantern" / "filesystem.py",
            ROOT / "lantern" / "media.py",
            ROOT / "lantern" / "views.py",
            ROOT / "lantern" / "crop.py",
            ROOT / "lantern" / "http" / "server.py",
        ):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, str(path))
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                self.assertNotIn(target.id, names)
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(node.module, "lan_drive")
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--help"],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--set-terminal-password", result.stdout)

    def test_two_servers_use_independent_root_and_runtime(self):
        from lantern.config import AppConfig
        from lantern.application import make_application
        from lantern.http.server import LanternHTTPServer, Handler

        with tempfile.TemporaryDirectory(prefix="lantern-isolation-") as temp:
            apps = []
            servers = []
            threads = []
            try:
                for i in range(2):
                    root = Path(temp) / f"root-{i}"
                    root.mkdir()
                    (root / f"only-{i}.txt").write_text(f"{i}", encoding="utf-8")
                    cfg = AppConfig(
                        root=root, port=0, host="127.0.0.1", title=f"Instance {i}",
                        cache_dir=Path(temp) / f"cache-{i}",
                        config_path=Path(temp) / f"config-{i}.yaml",
                    )
                    app = make_application(cfg)
                    server = LanternHTTPServer(("127.0.0.1", 0), Handler, app)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    apps.append(app)
                    servers.append(server)
                    threads.append(thread)

                self.assertIsNot(apps[0].ws, apps[1].ws)
                self.assertIsNot(apps[0].terminal, apps[1].terminal)
                self.assertIsNot(apps[0].bot, apps[1].bot)
                self.assertIsNot(apps[0].pi, apps[1].pi)
                self.assertNotEqual(apps[0].pi.state_dir, apps[1].pi.state_dir)
                self.assertIsNot(apps[0].work, apps[1].work)
                self.assertIsNot(apps[0].heavy_preview_slots, apps[1].heavy_preview_slots)
                self.assertIsNot(apps[0].crop.lock, apps[1].crop.lock)
                self.assertIn('.png', apps[0].crop.mimes)
                for i, server in enumerate(servers):
                    url = f"http://127.0.0.1:{server.server_address[1]}"
                    with urllib.request.urlopen(url + "/api/info", timeout=5) as reply:
                        info = json.load(reply)
                    self.assertEqual(Path(info["root"]).resolve(), apps[i].config.root.resolve())
                    self.assertEqual(info["defaults"]["default_sort"], "name-asc")
                    with urllib.request.urlopen(url + "/api/list?p=/", timeout=5) as reply:
                        listing = json.load(reply)
                    self.assertEqual({x["name"] for x in listing["items"]}, {f"only-{i}.txt"})
            finally:
                for server in servers:
                    server.shutdown()
                    server.server_close()
                for thread in threads:
                    thread.join(timeout=5)
                for app in apps:
                    app.close()


if __name__ == "__main__":
    unittest.main()

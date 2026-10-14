"""Windows click-to-run launcher: three-action config and mode acceptance tests.

Tests use an isolated disposable checkout and -SetupOnly; they never start the
production server or modify the machine's existing Lantern configuration.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "run.bat only supports Windows")
class WindowsRunLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="lantern launcher ", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "clone with spaces"
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "lan_drive.py").write_text("# fixture marker\n", encoding="utf-8")
        shutil.copy2(ROOT / "run.bat", self.repo / "run.bat")
        shutil.copy2(ROOT / "tools" / "run_lantern.ps1", self.repo / "tools" / "run_lantern.ps1")
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            self.port = server.getsockname()[1]
        template = (ROOT / "lan_drive_config.yaml_copy").read_text(encoding="utf-8")
        self.template = template.replace("port: 9999", f"port: {self.port}")
        (self.repo / "lan_drive_config.yaml_copy").write_text(self.template, encoding="utf-8")
        self.share = Path(self.temp.name) / "user shared folder"
        self.share.mkdir()

    def launch(self, prompts: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["cmd.exe", "/d", "/c", "run.bat", "-SetupOnly"],
            input=prompts, text=True, encoding="utf-8", errors="replace",
            cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        )

    def test_fresh_clone_generates_yaml_and_nohop_without_installing_or_starting(self) -> None:
        response = self.launch(str(self.share) + "\n1\n")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        config = self.repo / "lan_drive_config.yaml"
        self.assertTrue(config.is_file())
        saved = config.read_text(encoding="utf-8")
        self.assertTrue(os.path.samefile(re.search(r'^root: "([^"]+)"', saved, re.M).group(1), self.share))
        self.assertIn(f"port: {self.port}", saved)
        self.assertIn('host: "127.0.0.1"', saved)
        self.assertIn("terminal_enabled: true", saved)
        self.assertEqual((self.repo / "lan_drive_config.yaml_copy").read_text(encoding="utf-8"), self.template)
        self.assertIn("Mode:   Nohup", response.stdout)
        self.assertIn("Setup-only verification complete", response.stdout)
        self.assertFalse((self.repo / ".venv").exists())

    def test_blank_root_uses_user_profile_and_nohop_alias(self) -> None:
        response = self.launch("\nnohop\n")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        content = (self.repo / "lan_drive_config.yaml").read_text(encoding="utf-8")
        picked = re.search(r'^root: "([^"]+)"', content, re.M).group(1)
        self.assertTrue(os.path.samefile(picked, os.environ["USERPROFILE"]))
        self.assertIn("Mode:   Nohup", response.stdout)

    def test_existing_machine_config_retains_settings_when_root_or_mode_changes(self) -> None:
        config = self.repo / "lan_drive_config.yaml"
        existing = self.template.replace("port: " + str(self.port), "port: " + str(self.port))
        existing = existing.replace("terminal_enabled: true", "terminal_enabled: false")
        existing += "\n# preserved user preference\nmy_custom_setting: \"hello\"\n"
        config.write_text(existing, encoding="utf-8")
        response = self.launch(str(self.share) + "\n2\n")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        saved = config.read_text(encoding="utf-8")
        self.assertIn("terminal_enabled: false", saved)
        self.assertIn("my_custom_setting: \"hello\"", saved)
        self.assertIn(f"port: {self.port}", saved)
        self.assertIn("Mode:   Terminal", response.stdout)
        self.assertFalse((self.repo / ".venv").exists())

    def test_invalid_root_retry_and_default_root(self) -> None:
        response = self.launch("Z:\\Lantern\\Path\\Not\\Existing\n" + str(self.share) + "\n2\n")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertIn("Directory does not exist:", response.stdout)
        self.assertIn("Mode:   Terminal", response.stdout)

    @unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "opt-in real background process + uv bootstrap")
    def test_real_fresh_clone_nohup_survives_launcher_exit_and_reuses_server(self) -> None:
        # A fully isolated clone, port and data directory. Do not touch the
        # production service, its YAML or any running terminal.
        files = (
            "lan_drive.py", "plugin.py", "requirements.txt",
        )
        for name in files:
            shutil.copy2(ROOT / name, self.repo / name)
        shutil.copytree(ROOT / "lantern", self.repo / "lantern")
        shutil.copytree(ROOT / "static", self.repo / "static")

        pid = None
        transcript = self.repo / "test-launcher-output.txt"
        try:
            command = ["cmd.exe", "/d", "/c", "run.bat", "-NoBrowser"]

            def launch_to_file(timeout: int) -> tuple[int, str]:
                # A detached Windows child can retain an inherited console pipe.
                # A regular file captures the launcher without blocking on the
                # background server's unrelated handle lifetime.
                with transcript.open("w", encoding="utf-8") as capture:
                    process = subprocess.run(
                        command, cwd=self.repo, text=True,
                        input=str(self.share) + "\n1\n",
                        stdout=capture, stderr=subprocess.STDOUT, timeout=timeout,
                    )
                return process.returncode, transcript.read_text(encoding="utf-8", errors="replace")

            status, message = launch_to_file(125)
            match = re.search(r"Server PID:\s*(\d+)", message)
            if match:
                pid = int(match.group(1))
            self.assertEqual(status, 0, message)
            self.assertIsNotNone(pid, message)
            self.assertIn("Ready:", message)
            self.assertTrue((self.repo / ".venv" / "Scripts" / "python.exe").is_file())
            config = self.repo / "lan_drive_config.yaml"
            self.assertTrue(config.is_file())
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/info", timeout=5,
            ) as web:
                info = json.load(web)
            self.assertEqual(info["app"], "LAN Drive OneFile")
            self.assertTrue(os.path.samefile(info["root"], self.share))
            self.assertTrue(os.path.samefile(info["config"], config))

            again_status, again_message = launch_to_file(20)
            self.assertEqual(again_status, 0, again_message)
            self.assertIn("Not launching a duplicate", again_message)
        finally:
            if pid is None and transcript.exists():
                match = re.search(r"Server PID:\s*(\d+)", transcript.read_text(encoding="utf-8", errors="replace"))
                if match:
                    pid = int(match.group(1))
            if pid is not None:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15, check=False)
                time.sleep(0.3)

    def test_local_config_is_respected_when_standard_config_missing(self) -> None:
        local = self.repo / "lan_drive_config.local.yaml"
        local.write_text(self.template.replace("terminal_enabled: true", "terminal_enabled: false"), encoding="utf-8")
        response = self.launch(str(self.share) + "\n1\n")
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertFalse((self.repo / "lan_drive_config.yaml").exists())
        self.assertTrue(os.path.samefile(re.search(r'^root: "([^"]+)"', local.read_text(encoding="utf-8"), re.M).group(1), self.share))
        self.assertIn("terminal_enabled: false", local.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

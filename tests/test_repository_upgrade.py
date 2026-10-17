"""Local-only proof that legacy tracked YAML survives the template migration."""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPDATER = ROOT / "tools" / "safe_pull.py"


def run(*args: str | Path, cwd: Path | None = None, ok: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [str(arg) for arg in args], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )
    if ok and proc.returncode:
        raise AssertionError((proc.stdout + "\n" + proc.stderr)[-2400:])
    return proc


def git(repo: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    return run("git", "-C", repo, *args, ok=ok)


class ProductionConfigUpgradeTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        remote, writer, old = root / "remote.git", root / "publisher", root / "legacy"
        run("git", "init", "--bare", "--initial-branch=main", remote)
        run("git", "clone", remote, writer)
        (writer / "lan_drive_config.yaml").write_text('root: "."\nhost: "0.0.0.0"\n', encoding="utf-8")
        git(writer, "add", "lan_drive_config.yaml")
        git(writer, "-c", "user.name=Lantern CI", "-c", "user.email=ci@example.invalid",
            "commit", "-m", "old layout")
        git(writer, "push", "origin", "main")
        run("git", "clone", remote, old)

        git(writer, "mv", "lan_drive_config.yaml", "lan_drive_config.yaml_copy")
        (writer / "lan_drive_config.yaml_copy").write_text(
            'root: "."\nhost: "127.0.0.1"\n', encoding="utf-8",
        )
        (writer / ".gitignore").write_text("lan_drive_config.yaml\n", encoding="utf-8")
        git(writer, "add", ".gitignore", "lan_drive_config.yaml_copy")
        git(writer, "-c", "user.name=Lantern CI", "-c", "user.email=ci@example.invalid",
            "commit", "-m", "template and ignored user settings")
        git(writer, "push", "origin", "main")
        return writer, old

    @unittest.skipUnless(run("git", "--version", ok=False).returncode == 0, "Git is required")
    def test_legacy_dirty_config_migrates_losslessly_and_ignores_local_copy(self):
        with tempfile.TemporaryDirectory(prefix="lantern-config-update-") as tmp:
            writer, old = self.fixture(Path(tmp))
            original = b'# local machine\r\nroot: "C:/Users/special"\r\nhost: "0.0.0.0"\r\n'
            (old / "lan_drive_config.yaml").write_bytes(original)
            (old / "private.txt").write_bytes(b"not tracked or deleted")
            run(sys.executable, UPDATER, "--repo", old, "--backup-dir", Path(tmp) / "backups")
            self.assertEqual((old / "lan_drive_config.yaml").read_bytes(), original)
            self.assertEqual((old / "private.txt").read_bytes(), b"not tracked or deleted")
            self.assertTrue((old / "lan_drive_config.yaml_copy").is_file())
            self.assertEqual(git(old, "check-ignore", "lan_drive_config.yaml").returncode, 0)
            self.assertEqual(git(old, "status", "--porcelain", "--", "lan_drive_config.yaml").stdout.strip(), "")
            self.assertEqual(git(old, "rev-parse", "HEAD").stdout, git(writer, "rev-parse", "HEAD").stdout)
            # Re-running must preserve machine-local settings without a second migration.
            run(sys.executable, UPDATER, "--repo", old, "--backup-dir", Path(tmp) / "backups")
            self.assertEqual((old / "lan_drive_config.yaml").read_bytes(), original)

    def test_runtime_cli_overrides_do_not_write_yaml_without_save_config(self):
        with tempfile.TemporaryDirectory(prefix="lantern-config-override-", ignore_cleanup_errors=True) as tmp:
            temp = Path(tmp)
            for save in (False, True):
                with self.subTest(save=save):
                    config = temp / ("saved.yaml" if save else "runtime-only.yaml")
                    with socket.socket() as sock:
                        sock.bind(("127.0.0.1", 0))
                        port = sock.getsockname()[1]
                    command = [
                        sys.executable, str(ROOT / "main.py"),
                        "--config", str(config), "--root", str(temp),
                        "--host", "127.0.0.1", "--port", str(port),
                    ]
                    if save:
                        command.append("--save-config")
                    proc = subprocess.Popen(
                        command, cwd=ROOT, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    try:
                        for _ in range(100):
                            try:
                                with urllib.request.urlopen(
                                    f"http://127.0.0.1:{port}/api/info", timeout=0.4
                                ):
                                    break
                            except OSError:
                                time.sleep(0.08)
                        else:
                            self.fail("Isolated server did not become ready")
                        self.assertEqual(config.is_file(), save)
                    finally:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
        # Windows may hold a just-exited child's cwd handle briefly.
        # Retry instead of leaving a stale fixture or failing after assertions.
        for attempt in range(12):
            if not Path(tmp).exists():
                break
            try:
                shutil.rmtree(tmp)
                break
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(0.25)

    @unittest.skipUnless(run("git", "--version", ok=False).returncode == 0, "Git is required")
    def test_staged_config_aborts_before_writing_or_updating(self):
        with tempfile.TemporaryDirectory(prefix="lantern-config-upgrade-abort-") as tmp:
            _, old = self.fixture(Path(tmp))
            modified = b'host: "192.168.1.9"\n'
            (old / "lan_drive_config.yaml").write_bytes(modified)
            git(old, "add", "lan_drive_config.yaml")
            before = git(old, "rev-parse", "HEAD").stdout
            result = run(sys.executable, UPDATER, "--repo", old, ok=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("staged changes", result.stderr)
            self.assertEqual(git(old, "rev-parse", "HEAD").stdout, before)
            self.assertEqual((old / "lan_drive_config.yaml").read_bytes(), modified)


if __name__ == "__main__":
    unittest.main()

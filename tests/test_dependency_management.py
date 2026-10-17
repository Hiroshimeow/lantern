"""Canonical uv project and launcher smoke regression tests."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencySetupContract(unittest.TestCase):
    def test_single_dependency_source_is_uv_project(self):
        manifest = ROOT / "pyproject.toml"
        self.assertTrue(manifest.is_file(), "uv run main.py needs pyproject.toml")
        self.assertTrue((ROOT / "uv.lock").is_file(), "uv sync needs reproducible lock")
        self.assertFalse((ROOT / "requirements.txt").exists(), "Do not maintain duplicate dependency manifests")
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        deps = " ".join(data["project"]["dependencies"]).lower()
        for package in ("pyyaml", "watchdog", "pywinpty"):
            with self.subTest(package=package):
                self.assertIn(package, deps)

    def test_launchers_use_locked_uv_dependencies(self):
        launcher = (ROOT / "tools" / "run_lantern.ps1").read_text(encoding="utf-8").lower()
        installer = (ROOT / "install.ps1").read_text(encoding="utf-8").lower()
        for name, script in (("launcher", launcher), ("installer", installer)):
            with self.subTest(name=name):
                self.assertIn("uv", script)
                self.assertIn(" sync ", script)
                self.assertIn("--locked", script)
                self.assertNotIn("requirements.txt", script)
        self.assertIn("tools\\run_lantern.ps1", (ROOT / "run.bat").read_text(encoding="utf-8").lower())

    @unittest.skipUnless(shutil.which("uv"), "uv not available")
    def test_uv_run_main_help(self):
        run = subprocess.run(
            ["uv", "run", "--locked", "main.py", "--help"],
            cwd=ROOT, text=True, capture_output=True, timeout=40,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("--root", run.stdout)
        self.assertIn("--config", run.stdout)


if __name__ == "__main__":
    unittest.main()

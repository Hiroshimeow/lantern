"""Guard Lantern's clean source layout and backwards-compatible launch entrypoints.

Do not move main.py (CLI/installer) or plugin.py (optional preview API).
Internal runtime code belongs under the lantern package.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("md_editor", "scm", "terminal", "terminal_auth", "ws")


class RepositoryLayoutTests(unittest.TestCase):
    def test_internal_python_modules_live_in_package(self):
        self.assertTrue((ROOT / "lantern" / "__init__.py").is_file())
        for name in MODULES:
            with self.subTest(name=name):
                self.assertTrue((ROOT / "lantern" / f"{name}.py").is_file())
                self.assertFalse((ROOT / f"lantern_{name}.py").exists())
                imported = importlib.import_module(f"lantern.{name}")
                self.assertTrue(Path(imported.__file__).resolve().is_relative_to(
                    (ROOT / "lantern").resolve()))

    def test_canonical_cli_and_domain_modules_are_importable(self):
        self.assertTrue((ROOT / "main.py").is_file())
        self.assertFalse((ROOT / "lan_drive.py").exists())
        self.assertTrue((ROOT / "plugin.py").is_file())
        import plugin
        from lantern.application import make_application
        from lantern.config import AppConfig
        from lantern.filesystem import FileService
        from lantern.media import MediaService
        from lantern.views import ViewService
        from lantern.crop import CropService
        from lantern.http.server import Handler
        for item in (make_application, AppConfig, FileService, MediaService,
                     ViewService, CropService, Handler):
            self.assertTrue(callable(item))
        self.assertTrue(callable(plugin.render_preview_page))
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--no-password", proc.stdout)

    def test_architecture_docs_are_under_docs_and_readme_links_resolve(self):
        self.assertFalse((ROOT / "LANTERN_SYSTEM_ARCHITECTURE.md").exists())
        self.assertFalse((ROOT / "LANTERN_FUNCTION_FLOWS.md").exists())
        for name in ("LANTERN_SYSTEM_ARCHITECTURE.md", "LANTERN_FUNCTION_FLOWS.md"):
            self.assertTrue((ROOT / "docs" / "architecture" / name).is_file())
            self.assertIn(f"docs/architecture/{name}",
                          (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_fresh_checkout_launcher_fixture_copies_package(self):
        # Installer copies all source recursively; the real fresh-clone test
        # builds an intentionally tiny repository and must copy this package.
        fixture = (ROOT / "tests" / "test_run_launcher.py").read_text(encoding="utf-8")
        self.assertIn('copytree(ROOT / "lantern"', fixture)


if __name__ == "__main__":
    unittest.main()

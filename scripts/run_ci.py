#!/usr/bin/env python3
"""Run JavaScript syntax, unit, contract and fake-Pi HTTP integration checks.

Browser E2E and corpus suites are separate release checks, not run here.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print("=== [1/3] Checking JavaScript syntax across static assets ===")
    js_files = [
        ROOT / "static" / "chatbot.js",
        ROOT / "static" / "markdown_visual_shell.js",
        ROOT / "static" / "markdown_paged_editor.js",
        ROOT / "static" / "markdown_draft_diff.js",
        ROOT / "static" / "markdown_preview.js",
        ROOT / "static" / "markdown_table_interactions.js",
    ]
    for jf in js_files:
        subprocess.run(["node", "--check", str(jf)], check=True)
        print(f"  OK: {jf.relative_to(ROOT)}")

    subprocess.run([
        "node", "--test", str(ROOT / "tests" / "test_source_v74_characterization.cjs"),
    ], check=True)

    print("\n=== [2/3] Running Unit, Contract & v4 Upgrade Tests ===")
    sys.path.insert(0, str(ROOT))
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for tf in sorted((ROOT / "tests").glob("test_*.py")):
        if ("e2e" in tf.name and tf.name != "test_lanbot_v4_e2e.py") or "corpus" in tf.name:
            continue
        suite.addTests(loader.discover(str(ROOT / "tests"), pattern=tf.name))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        return 1

    print("\n=== [3/3] Selected CI checks passed (browser E2E and corpus excluded) ===")
    return 0


if __name__ == "__main__":
    # Application tests must never read or repair the developer's real sessions.
    with tempfile.TemporaryDirectory(prefix="lantern-ci-home-") as temporary_home:
        with (
            patch.dict(os.environ, {
                "HOME": temporary_home,
                "USERPROFILE": temporary_home,
                "PI_CODING_AGENT_DIR": str(Path(temporary_home) / ".pi" / "agent"),
                "LANTERN_WORK_DIR": str(Path(temporary_home) / "work"),
            }),
            patch.object(Path, "home", return_value=Path(temporary_home)),
        ):
            raise SystemExit(main())

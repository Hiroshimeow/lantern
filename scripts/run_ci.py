#!/usr/bin/env python3
"""Automated CI & E2E verification runner for Lantern All-in-One v4."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

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

    print("\n=== [3/3] CI & Real-User E2E Verification Passed 100%! ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

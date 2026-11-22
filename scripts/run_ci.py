#!/usr/bin/env python3
"""Automated CI & Regression Verification Runner for Lantern All-in-One v9.25.

Runs:
  1. Node syntax check across all static/*.js and tools/*.mjs files.
  2. Python bytecode compilation across main.py, plugin.py, and lantern/**/*.py.
  3. Full repository-native `unittest discover -s tests` or the named
     acceptance cases supplied with --browser-case.
  4. The named acceptance selection fails on any skip. Strict full discovery
     permits explicitly opt-in crop benchmarks and retired Markdown cases.
"""
from __future__ import annotations

import argparse
import os
import py_compile
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lantern v9.25 full CI gate")
    parser.add_argument(
        "--require-browser",
        action="store_true",
        default=os.environ.get("LANTERN_CI_REQUIRE_BROWSER") == "1",
        help="Fail if browser E2E tests are skipped or unavailable.",
    )
    parser.add_argument(
        "--browser-case",
        action="append",
        default=[],
        metavar="NAME",
        help="Run a named mandatory browser test, class, or module. Repeat for multiple cases.",
    )
    args = parser.parse_args(argv)
    if args.browser_case and not args.require_browser:
        parser.error("--browser-case requires --require-browser")

    print("=== [1/4] Checking JavaScript syntax across ALL static & tool assets ===")
    js_files = sorted(
        list((ROOT / "static").glob("*.js"))
        + list((ROOT / "tools").glob("*.mjs"))
    )
    for jf in js_files:
        subprocess.run(["node", "--check", str(jf)], check=True)
        print(f"  OK: {jf.relative_to(ROOT)}")

    print("\n=== [2/4] Compiling all Python modules (py_compile) ===")
    py_files = sorted(
        [ROOT / "main.py", ROOT / "plugin.py"]
        + list((ROOT / "lantern").rglob("*.py"))
    )
    for pf in py_files:
        py_compile.compile(str(pf), doraise=True)
    print(f"  OK: {len(py_files)} Python files compiled cleanly.")

    sys.path.insert(0, str(ROOT))
    loader = unittest.defaultTestLoader
    if args.browser_case:
        print("\n=== [3/4] Running explicitly selected mandatory browser cases ===")
        suite = unittest.TestSuite()
        for name in args.browser_case:
            cases = loader.loadTestsFromName(name)
            if not cases.countTestCases():
                parser.error(f"mandatory browser case did not resolve to any tests: {name}")
            suite.addTests(cases)
    else:
        print("\n=== [3/4] Running FULL repository unittest discover -s tests ===")
        suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    ran = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = ran - failures - errors - skipped
    print(
        f"\nSummary: ran={ran}, passed={passed}, failures={failures}, "
        f"errors={errors}, skipped={skipped}"
    )

    if args.require_browser:
        browser_skips = result.skipped if args.browser_case else [
            (test, reason)
            for test, reason in result.skipped
            if "cropperformancee2e" not in str(test).lower()
            and not (
                "markdownmodese2e" in str(test).lower()
                and "removed; replaced" in str(reason).lower()
            )
            and any(k in str(test).lower() or k in str(reason).lower() for k in ("browser", "e2e", "chromium", "playwright"))
        ]
        if browser_skips:
            print(f"\nFAIL: --require-browser set, but {len(browser_skips)} browser test(s) were skipped:")
            for test, reason in browser_skips[:10]:
                print(f"  SKIPPED: {test} — {reason}")
            return 2

    if not result.wasSuccessful():
        return 1

    completed_gate = "Mandatory Browser Acceptance" if args.browser_case else "Full Repository Discovery"
    print(f"\n=== [4/4] {completed_gate} Passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

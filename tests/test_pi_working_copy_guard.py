from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "lantern" / "pi_working_copy_guard.ts"
HARNESS = ROOT / "tests" / "pi_working_copy_guard_harness.mjs"


@unittest.skipUnless(shutil.which("node"), "Node is required for Pi guard contract test")
class PiWorkingCopyGuardTests(unittest.TestCase):
    def test_guard_blocks_saved_and_private_paths_but_allows_active_working_path(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            private = base / ".lantern"
            work_dir = private / "work" / "doc"
            project.mkdir()
            work_dir.mkdir(parents=True)
            real = project / "doc.md"
            working = work_dir / "doc.md"
            other = project / "other.py"
            guard = private / "work" / "guard-test.json"
            real.write_text("saved\n", encoding="utf-8")
            working.write_text("pending\n", encoding="utf-8")
            other.write_text("x=1\n", encoding="utf-8")
            guard.write_text(
                json.dumps(
                    {
                        "staged": [{"real": str(real.resolve()), "working": str(working.resolve())}],
                        "turnWritable": [str(working.resolve())],
                        "protectedDir": str(private.resolve()),
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    shutil.which("node"),
                    "--experimental-strip-types",
                    str(HARNESS),
                    str(EXTENSION),
                    str(guard),
                    str(real),
                    str(working),
                    str(guard),
                    str(other),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertTrue(result["realRead"]["block"])
            self.assertTrue(result["realEdit"]["block"])
            self.assertIsNone(result["workRead"])
            self.assertIsNone(result["workEdit"])
            self.assertTrue(result["privateRead"]["block"])
            self.assertTrue(result["privateWrite"]["block"])
            self.assertIsNone(result["otherRead"])
            self.assertIsNone(result["otherEdit"])

    def test_guard_fails_closed_when_state_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            real = project / "doc.md"
            work = base / "work.md"
            private = base / "private.json"
            other = project / "other.py"
            for path in (real, work, private, other):
                path.write_text("x\n", encoding="utf-8")
            missing = base / "missing-guard.json"

            proc = subprocess.run(
                [
                    shutil.which("node"),
                    "--experimental-strip-types",
                    str(HARNESS),
                    str(EXTENSION),
                    str(missing),
                    str(real),
                    str(work),
                    str(private),
                    str(other),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            for key, value in result.items():
                self.assertTrue(value["block"], key)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "lantern" / "pi_working_copy_guard.ts"
HARNESS = ROOT / "tests" / "pi_working_copy_guard_harness.mjs"


def _node_cmd(*args: str) -> list[str]:
    node = shutil.which("node") or "node"
    probe = subprocess.run(
        [node, "--experimental-strip-types", "-e", ""],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return [node, "--experimental-strip-types", *args]
    return [node, *args]


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
                _node_cmd(
                    str(HARNESS),
                    str(EXTENSION),
                    str(guard),
                    str(real),
                    str(working),
                    str(guard),
                    str(other),
                ),
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
                _node_cmd(
                    str(HARNESS),
                    str(EXTENSION),
                    str(missing),
                    str(real),
                    str(work),
                    str(private),
                    str(other),
                ),
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

    def test_live_scope_allows_local_shell_and_blocks_lan_shell_or_extensions(self):
        from lantern.live_markdown import LiveMarkdownStore
        from lantern.bot_config import LanternBotConfig
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = Path(td) / "project"
            project.mkdir()
            real = project / "doc.md"
            real.write_text("# Test\n", encoding="utf-8")
            private = base / "work"
            store = LiveMarkdownStore(project, private, {".md"})
            store.get("doc.md")
            cfg = LanternBotConfig.from_mapping({"access": {
                "localhost": {"tools": ["*"], "extensions": True},
                "lan": {"tools": ["read", "grep", "find", "ls"], "extensions": False},
            }})
            self.assertEqual(cfg.local_access.tools, ("*",))
            self.assertEqual(cfg.lan_access.tools, ("read", "grep", "find", "ls"))

            def run(scope, tools):
                store.set_runtime_scope(scope, tools)
                result = subprocess.run(
                    _node_cmd(
                        str(HARNESS),
                        str(EXTENSION),
                        str(store.guard_path),
                        str(real),
                        str(real),
                        str(store.guard_path),
                        str(real),
                    ),
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            local = run("local", cfg.local_access.tools)
            self.assertIsNone(local["powershell"])
            self.assertIsNone(local["bash"])
            self.assertIsNone(local["extensionTool"])
            self.assertIsNone(local["realEdit"])
            self.assertTrue(local["privateWrite"]["block"])

            lan = run("lan", cfg.lan_access.tools)
            self.assertTrue(lan["powershell"]["block"])
            self.assertTrue(lan["bash"]["block"])
            self.assertTrue(lan["extensionTool"]["block"])
            self.assertTrue(lan["realEdit"]["block"])
            self.assertIsNone(lan["realRead"])
            self.assertTrue(lan["privateWrite"]["block"])


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import os, subprocess, sys

root = Path(r"E:\git-project\lantern")
bundle = root / "static/vendor/lantern-crepe.min.js"
scratch = root / ".plan/lantern-markdown-main-20261018"
current = scratch / "dev_turn9_current_bundle_backup.js"
baseline = scratch / "dev_turn9_head_bundle_baseline.js"
current.write_bytes(bundle.read_bytes())
baseline.write_bytes(subprocess.check_output([
    "git", "show", "HEAD:static/vendor/lantern-crepe.min.js"
], cwd=root))
bundle.write_bytes(baseline.read_bytes())
env = dict(os.environ, LANTERN_E2E="1")
log = scratch / "dev_turn9_visual_open_head_bundle.log"
try:
    with log.open("wb") as fh:
        cp = subprocess.run([
            r"C:\Users\admin\miniconda3\python.exe",
            "-m","unittest","-v",
            "tests.test_md_visual_e2e.VisualMarkdownBrowserE2E.test_opening_mermaid_and_tables_never_saves_a_normalized_file"
        ], cwd=root, env=env, stdout=fh, stderr=subprocess.STDOUT)
    raise SystemExit(cp.returncode)
finally:
    bundle.write_bytes(current.read_bytes())

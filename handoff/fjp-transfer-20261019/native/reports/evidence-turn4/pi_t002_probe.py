from __future__ import annotations
import json, os, shutil, tempfile, threading, time
from pathlib import Path
import sys

ROOT = Path(r"E:\git-project\lantern\.wt\lantern-bot")
sys.path.insert(0, str(ROOT))
from lantern.terminal import WinConPty

node = shutil.which("node")
cli = Path(os.environ["APPDATA"]) / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
assert node and cli.is_file(), (node, cli)

chunks: list[str] = []
exit_codes: list[int] = []
lock = threading.Lock()
done = threading.Event()

def on_data(data: str) -> None:
    with lock:
        chunks.append(data)

def on_exit(code: int) -> None:
    exit_codes.append(code)
    done.set()

with tempfile.TemporaryDirectory(prefix="lantern-pi-t002-") as tmp:
    session_dir = Path(tmp) / "sessions"
    session_dir.mkdir()
    argv = [
        node, str(cli),
        "--offline", "--approve", "--no-mcp",
        "--session-dir", str(session_dir),
        "--session-id", "7b40cb7d-871a-4c92-8a38-6dc223709703",
        "--tui-mode", "regular",
    ]
    pty = WinConPty(argv, tmp, 100, 32, on_data, on_exit)
    try:
        time.sleep(8.0)
        steps = [
            ("settings", "/settings\r", 0.8),
            ("escape-settings", "\x1b", 0.4),
            ("resume", "/resume\r", 0.8),
            ("escape-resume", "\x1b", 0.4),
            ("shell-local", "!!echo PI_NATIVE_SHELL_PROOF\r", 1.0),
            ("bracketed-paste", "\x1b[200~PASTE 日本語 tiếng Việt 😀\x1b[201~", 0.5),
            ("clear-line", "\x15", 0.3),
            ("unicode-editor", "Unicode 日本語 tiếng Việt 😀", 0.4),
            ("clear-line-2", "\x15", 0.3),
            ("alt-word-key", "\x1bf", 0.3),
            ("ctrl-c", "\x03", 0.4),
            ("new", "/new\r", 0.8),
            ("session", "/session\r", 0.8),
            ("escape-session", "\x1b", 0.3),
        ]
        snapshots = []
        for name, data, wait in steps:
            pty.write(data)
            time.sleep(wait)
            with lock:
                text = "".join(chunks)
            snapshots.append({"step": name, "chars": len(text), "tail": text[-1500:]})
        pty.resize(120, 40)
        time.sleep(0.4)
        with lock:
            full = "".join(chunks)
        result = {
            "argv": argv,
            "cwd": tmp,
            "chunks": len(chunks),
            "chars": len(full),
            "contains_shell_proof": "PI_NATIVE_SHELL_PROOF" in full,
            "contains_ansi": "\x1b[" in full or "\x1b]" in full,
            "contains_unicode_input": "日本語" in full or "tiếng Việt" in full,
            "session_files": [str(p.relative_to(session_dir)) for p in session_dir.rglob("*") if p.is_file()],
            "snapshots": snapshots,
        }
        evidence = ROOT / ".plan" / "lantern-pi-native-20261018" / "evidence-turn4"
        (evidence / "pi-t002-g6-winconpty-raw.txt").write_text(full, encoding="utf-8", errors="replace")
        (evidence / "pi-t002-g6-winconpty.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k != "snapshots"}, ensure_ascii=False, indent=2))
    finally:
        pty.close(graceful=True)
        done.wait(3)
        print("exit_codes", exit_codes)

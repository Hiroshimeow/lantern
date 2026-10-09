from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from uuid import uuid4
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

MAX_TERMINALS = 16
MAX_HISTORY = 32
MAX_OUTPUT = 200 * 1024
OUTPUT_FLUSH_MS = 0.016
_VALID_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,80}$")


def encode_terminal_key(key: str, modifiers: Optional[Dict[str, bool]] = None) -> str:
    modifiers = modifiers or {}
    ctrl = bool(modifiers.get("ctrl"))
    alt = bool(modifiers.get("alt"))
    shift = bool(modifiers.get("shift"))
    modifier = 1 + (1 if shift else 0) + (2 if alt else 0) + (4 if ctrl else 0)
    named = {
        "Enter": "\r", "Return": "\r", "Tab": "\t", "Backspace": "\x7f", "Escape": "\x1b",
        "Up": "\x1b[A", "ArrowUp": "\x1b[A", "Down": "\x1b[B", "ArrowDown": "\x1b[B",
        "Left": "\x1b[D", "ArrowLeft": "\x1b[D", "Right": "\x1b[C", "ArrowRight": "\x1b[C",
        "Home": "\x1b[H", "End": "\x1b[F", "Delete": "\x1b[3~", "Insert": "\x1b[2~",
        "PageUp": "\x1b[5~", "PageDown": "\x1b[6~",
        "F1": "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
    }
    if key == "Tab" and shift and not ctrl and not alt:
        return "\x1b[Z"
    if key == "Backspace":
        data = "\x08" if ctrl else "\x7f"
        return ("\x1b" if alt else "") + data
    if key in {"Insert", "Delete", "PageUp", "PageDown"} and modifier != 1:
        code = {"Insert": 2, "Delete": 3, "PageUp": 5, "PageDown": 6}[key]
        return f"\x1b[{code};{modifier}~"
    data = named.get(key, key if len(key) == 1 else "")
    if not data:
        raise ValueError(f"Unsupported terminal key: {key}")
    arrow = re.match(r"^\x1b\[([A-DHF])$", data)
    function_key = re.match(r"^\x1bO([P-S])$", data)
    named_code = {
        "Enter": 13, "Return": 13, "Tab": 9, "Backspace": 127, "Escape": 27,
        "Insert": 2, "Delete": 3, "Home": 1, "End": 4, "PageUp": 5, "PageDown": 6,
    }
    if arrow and modifier != 1:
        return f"\x1b[1;{modifier}{arrow.group(1)}"
    if function_key and modifier != 1:
        return f"\x1b[1;{modifier}{function_key.group(1)}"
    if key in named_code and modifier != 1:
        return f"\x1b[{named_code[key]};{modifier}u"
    if ctrl:
        if len(key) != 1:
            raise ValueError(f"Unsupported Ctrl key: {key}")
        code = ord(key.upper())
        if 64 <= code <= 95:
            data = chr(code - 64)
        else:
            raise ValueError(f"Unsupported Ctrl key: {key}")
    elif shift and len(key) == 1:
        data = key.upper()
    if alt:
        data = "\x1b" + data
    return data


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_shell() -> tuple[str, list[str], str]:
    """Resolve an interactive shell using the same Windows preference as pi-web-ui."""
    if os.name == "nt":
        explicit = os.environ.get("LANTERN_SHELL") or os.environ.get("PI_WEB_SHELL")
        if explicit:
            return explicit, ["-i"] if explicit.lower().endswith(("bash", "bash.exe")) else [], "bash" if "bash" in Path(explicit).name.lower() else "native"
        env_shell = os.environ.get("SHELL")
        if env_shell and Path(env_shell).exists():
            return env_shell, ["-i"] if "bash" in Path(env_shell).name.lower() else [], "bash" if "bash" in Path(env_shell).name.lower() else "native"
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if not base:
                continue
            candidate = Path(base) / "Git" / "bin" / "bash.exe"
            if candidate.exists():
                return str(candidate), ["-i"], "bash"
        comspec = os.environ.get("COMSPEC")
        if comspec:
            return comspec, [], "cmd"
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        return pwsh, [], "powershell"
    shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
    args = ["-i"] if Path(shell).name in {"bash", "zsh", "fish"} else []
    return shell, args, "posix"


class NativePty:
    def write(self, data: str) -> None:
        raise NotImplementedError

    def resize(self, cols: int, rows: int) -> None:
        raise NotImplementedError

    def close(self, graceful: bool = True) -> None:
        raise NotImplementedError


class WinConPty(NativePty):
    def __init__(
        self,
        argv: list[str],
        cwd: str,
        cols: int,
        rows: int,
        on_data: Callable[[str], None],
        on_exit: Callable[[int], None],
    ) -> None:
        try:
            from winpty import Backend, PtyProcess
        except ImportError as exc:
            raise RuntimeError("Windows terminal requires pywinpty (pip install -r requirements.txt)") from exc
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("LANG", "en_US.UTF-8")
        requested = os.environ.get("LANTERN_PTY_BACKEND", "conpty").strip().lower()
        if requested not in {"conpty", "winpty"}:
            raise RuntimeError("LANTERN_PTY_BACKEND must be 'conpty' or 'winpty'")
        backend = Backend.ConPTY if requested == "conpty" else Backend.WinPTY
        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols), backend=backend)
        self._on_data = on_data
        self._on_exit = on_exit
        self._closed = False
        self._filter_da1 = backend == Backend.ConPTY
        self._da1_carry = ""
        self._da1_deadline = time.monotonic() + 1.0
        self._reader = threading.Thread(target=self._read_loop, name=f"conpty-{id(self)}", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        code = 0
        try:
            while not self._closed:
                try:
                    data = self._proc.read(65536)
                except EOFError:
                    break
                except Exception:
                    if not self._proc.isalive():
                        break
                    time.sleep(0.02)
                    continue
                if data:
                    data = self._filter_startup_da1(data)
                    if data:
                        self._on_data(data)
                if not self._proc.isalive():
                    break
            try:
                self._proc.wait()
            except Exception:
                pass
            code = int(self._proc.exitstatus or 0)
        finally:
            self._on_exit(code)

    def _filter_startup_da1(self, data: str) -> str:
        if not self._filter_da1:
            return data
        combined = self._da1_carry + data
        marker = "\x1b[c"
        index = combined.find(marker)
        if index >= 0:
            self._filter_da1 = False
            self._da1_carry = ""
            # pywinpty's out-of-band OpenConsole host asks DA1 before the child
            # prints its prompt. Reply only after observing that exact query so
            # a future backend build that omits it never receives unsolicited
            # bytes. The query itself is hidden from xterm to avoid a second
            # browser-generated DA1 response entering the child.
            try:
                self._proc.write("\x1b[?1;2c")
            except Exception:
                pass
            return combined[:index] + combined[index + len(marker):]
        if time.monotonic() >= self._da1_deadline:
            self._filter_da1 = False
            self._da1_carry = ""
            return combined
        keep = min(len(marker) - 1, len(combined))
        self._da1_carry = combined[-keep:] if keep else ""
        return combined[:-keep] if keep else combined

    def write(self, data: str) -> None:
        self._proc.write(data)

    def resize(self, cols: int, rows: int) -> None:
        self._proc.setwinsize(rows, cols)

    def close(self, graceful: bool = True) -> None:
        if self._closed:
            return
        if graceful and self._proc.isalive():
            try:
                self._proc.write("\x03exit\r")
            except Exception:
                pass
            deadline = time.time() + 0.3
            while self._proc.isalive() and time.time() < deadline:
                time.sleep(0.02)
        if self._proc.isalive():
            try:
                self._proc.terminate(force=True)
            except TypeError:
                self._proc.terminate()
            except Exception:
                pass
        self._closed = True
        try:
            self._proc.close()
        except Exception:
            pass


class PosixPty(NativePty):
    def __init__(
        self,
        argv: list[str],
        cwd: str,
        cols: int,
        rows: int,
        on_data: Callable[[str], None],
        on_exit: Callable[[int], None],
    ) -> None:
        import fcntl
        import pty
        import struct
        import termios

        master, slave = pty.openpty()
        self._fd = master
        self._closed = False
        self._fcntl = fcntl
        self._struct = struct
        self._termios = termios
        self.resize(cols, rows)
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("LANG", "en_US.UTF-8")
        self._proc = subprocess.Popen(
            argv, cwd=cwd, stdin=slave, stdout=slave, stderr=slave, env=env,
            close_fds=True, preexec_fn=os.setsid,
        )
        os.close(slave)
        self._on_data = on_data
        self._on_exit = on_exit
        self._reader = threading.Thread(target=self._read_loop, name=f"pty-{self._proc.pid}", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    raw = os.read(self._fd, 65536)
                except OSError:
                    break
                if not raw:
                    break
                self._on_data(raw.decode("utf-8", "replace"))
        finally:
            code = self._proc.wait()
            self._on_exit(int(code))

    def write(self, data: str) -> None:
        os.write(self._fd, data.encode("utf-8", "surrogatepass"))

    def resize(self, cols: int, rows: int) -> None:
        self._fcntl.ioctl(self._fd, self._termios.TIOCSWINSZ, self._struct.pack("HHHH", rows, cols, 0, 0))

    def close(self, graceful: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        if self._proc.poll() is None:
            try:
                if graceful:
                    self.write("\x03exit\r")
                    self._proc.wait(timeout=0.3)
                else:
                    raise subprocess.TimeoutExpired([], 0)
            except Exception:
                try:
                    os.killpg(os.getpgid(self._proc.pid), 15)
                except Exception:
                    self._proc.terminate()
        try:
            os.close(self._fd)
        except OSError:
            pass


@dataclass
class TerminalEntry:
    id: str
    title: str
    cwd: str
    cols: int
    rows: int
    pty: NativePty
    running: bool = True
    exit_code: Optional[int] = None
    output: str = ""
    output_offset: int = 0
    command: Optional[str] = None
    generation: str = field(default_factory=lambda: uuid4().hex)
    seq: int = 0


class TerminalManager:
    def __init__(
        self,
        root: Path,
        emit: Callable[[Dict[str, Any]], None],
        *,
        pty_factory: Optional[Callable[..., NativePty]] = None,
        enabled: bool = True,
        max_live: int = MAX_TERMINALS,
        max_history: int = MAX_HISTORY,
        max_output: int = MAX_OUTPUT,
        flush_ms: float = OUTPUT_FLUSH_MS,
    ) -> None:
        self.root = root.resolve()
        self.emit = emit
        self.pty_factory = pty_factory or self._spawn_native
        self.enabled = enabled
        self.max_live = max_live
        self.max_history = max_history
        self.max_output = max_output
        self.flush_ms = flush_ms
        self.live: "OrderedDict[str, TerminalEntry]" = OrderedDict()
        self.history: "OrderedDict[str, TerminalEntry]" = OrderedDict()
        self.lock = threading.RLock()

    def rebind_emit(self, emit: Callable[[Dict[str, Any]], None]) -> None:
        self.emit = emit

    def _safe_cwd(self, cwd: str | Path) -> Path:
        raw = Path(cwd)
        candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        if not _inside(self.root, candidate):
            raise ValueError("Terminal cwd must be inside the configured root")
        if not candidate.is_dir():
            candidate = candidate.parent
        return candidate

    def _spawn_native(self, term_id, cwd, cols, rows, on_data, on_exit, command=None):
        shell, args, family = resolve_shell()
        argv = [shell, *args]
        if command:
            if family in {"bash", "posix"}:
                argv = [shell, "-lc", command]
            elif family == "cmd":
                argv = [shell, "/D", "/S", "/C", command]
            elif family == "powershell":
                argv = [shell, "-NoProfile", "-Command", command]
        cls = WinConPty if os.name == "nt" else PosixPty
        return cls(argv, str(cwd), cols, rows, on_data, on_exit)

    def _validate_id(self, term_id: str) -> None:
        if not _VALID_ID.fullmatch(term_id or ""):
            raise ValueError("Terminal id must be 1-80 characters using letters, numbers, . _ : / -")

    def _ensure_slot(self, term_id: str) -> None:
        if term_id in self.live:
            return
        if len(self.live) >= self.max_live:
            raise RuntimeError(f"Terminal limit reached ({self.max_live})")

    def create(self, term_id: str, cwd: str | Path, cols: int = 80, rows: int = 24, title: str = "Terminal", command: Optional[str] = None) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Terminal is disabled in config")
        self._validate_id(term_id)
        with self.lock:
            if term_id in self.live:
                return self._info(self.live[term_id])
            self._ensure_slot(term_id)
            self.history.pop(term_id, None)
            safe_cwd = self._safe_cwd(cwd)
            cols = max(2, int(cols or 80))
            rows = max(2, int(rows or 24))
            holder: Dict[str, Any] = {"early_data": []}

            def on_data(data: str) -> None:
                entry = holder.get("entry")
                if entry is not None:
                    self._queue_output(entry, data)
                else:
                    holder["early_data"].append(data)

            def on_exit(code: int) -> None:
                entry = holder.get("entry")
                if entry is not None:
                    self._handle_exit(entry, code)
                else:
                    holder["early_exit"] = code

            pty_obj = self.pty_factory(term_id, safe_cwd, cols, rows, on_data, on_exit, command)
            entry = TerminalEntry(term_id, title.strip() or "Terminal", str(safe_cwd), cols, rows, pty_obj, command=command)
            holder["entry"] = entry
            self.live[term_id] = entry
            for data in holder["early_data"]:
                self._queue_output(entry, data)
            if "early_exit" in holder:
                self._handle_exit(entry, int(holder["early_exit"]))
            else:
                self._emit_list()
            return self._info(entry)

    def run_command(self, term_id: str, cwd: str | Path, command: str, title: str, cols: int = 80, rows: int = 24) -> Dict[str, Any]:
        self.kill(term_id, emit_exit=False)
        return self.create(term_id, cwd, cols, rows, title, command=command)

    def _append_retained(self, entry: TerminalEntry, data: str) -> None:
        entry.output += data
        if len(entry.output) > self.max_output:
            drop = len(entry.output) - self.max_output
            entry.output = entry.output[drop:]
            entry.output_offset += drop

    def _queue_output(self, entry: TerminalEntry, data: str) -> None:
        if not data:
            return
        with self.lock:
            if self.live.get(entry.id) is not entry:
                return
            self._append_retained(entry, data)
            entry.seq += 1
            seq = entry.seq
        self.emit({"type": "terminal_output", "terminalId": entry.id, "generation": entry.generation, "seq": seq, "data": data})

    def _handle_exit(self, entry: TerminalEntry, code: int) -> None:
        evicted = []
        with self.lock:
            current = self.live.get(entry.id)
            if current is not entry:
                return
            entry.running = False
            entry.exit_code = code
            self.live.pop(entry.id, None)
            self.history[entry.id] = entry
            while len(self.history) > self.max_history:
                _, old = self.history.popitem(last=False)
                evicted.append(old)
        for old in evicted:
            try:
                old.pty.close(graceful=False)
            except Exception:
                pass
        self.emit({"type": "terminal_exit", "terminalId": entry.id, "exitCode": code})
        self._emit_list()

    def input(self, term_id: str, data: str) -> None:
        with self.lock:
            entry = self.live.get(term_id)
        if not entry:
            raise KeyError("Terminal not found or exited")
        entry.pty.write(data)

    def key(self, term_id: str, key: str, modifiers: Optional[Dict[str, bool]] = None) -> None:
        self.input(term_id, encode_terminal_key(key, modifiers))

    def resize(self, term_id: str, cols: int, rows: int) -> None:
        cols = max(2, int(cols or 80))
        rows = max(2, int(rows or 24))
        with self.lock:
            entry = self.live.get(term_id)
            if not entry or (entry.cols == cols and entry.rows == rows):
                return
            entry.cols, entry.rows = cols, rows
        entry.pty.resize(cols, rows)

    def rename(self, term_id: str, title: str) -> None:
        title = (title or "").strip()
        if not title:
            return
        with self.lock:
            entry = self.live.get(term_id) or self.history.get(term_id)
            if not entry:
                return
            entry.title = title
        self._emit_list()

    def kill(self, term_id: str, *, emit_exit: bool = True) -> None:
        with self.lock:
            entry = self.live.pop(term_id, None)
            if entry:
                entry.running = False
            hist = None if entry else self.history.pop(term_id, None)
        if entry:
            try:
                entry.pty.close(graceful=True)
            except Exception:
                pass
            if emit_exit:
                self.emit({"type": "terminal_exit", "terminalId": term_id, "exitCode": None})
            self._emit_list()
            return
        if hist:
            try:
                hist.pty.close(graceful=False)
            except Exception:
                pass
            self._emit_list()

    def kill_all(self) -> None:
        with self.lock:
            ids = list(self.live)
        for term_id in ids:
            self.kill(term_id)
        with self.lock:
            history = list(self.history.values())
            self.history.clear()
        for entry in history:
            try:
                entry.pty.close(graceful=False)
            except Exception:
                pass
        self._emit_list()

    def _info(self, entry: TerminalEntry) -> Dict[str, Any]:
        return {
            "id": entry.id,
            "title": entry.title,
            "cwd": entry.cwd,
            "cols": entry.cols,
            "rows": entry.rows,
            "running": entry.running,
            "exitCode": entry.exit_code,
            "command": entry.command,
            "generation": entry.generation,
        }

    def list(self) -> list[Dict[str, Any]]:
        with self.lock:
            return [self._info(x) for x in [*self.live.values(), *self.history.values()]]

    def replay_one(self, term_id: str) -> tuple[Dict[str, Any], str, int]:
        """Capture one bounded PTY tail and its output sequence atomically."""
        with self.lock:
            entry = self.live.get(term_id) or self.history.get(term_id)
            if entry is None:
                raise ValueError("Unknown terminal id")
            return self._info(entry), entry.output, entry.seq

    def replay(self) -> Iterable[tuple[str, str]]:
        with self.lock:
            return [(e.id, e.output) for e in [*self.live.values(), *self.history.values()] if e.output]

    def _emit_list(self) -> None:
        self.emit({"type": "terminal_list", "terminals": self.list()})

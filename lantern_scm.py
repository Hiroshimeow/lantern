from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

GIT_TIMEOUT = 15
MAX_GIT_OUTPUT = 16 * 1024 * 1024
_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


def _quote_shell(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_git_command(
    op: str,
    *,
    path: Optional[str] = None,
    branch: Optional[str] = None,
    remote: Optional[str] = None,
    message: Optional[str] = None,
) -> str:
    if op == "stage" and path is not None:
        return f"git add -- {_quote_shell(path)}"
    if op == "unstage" and path is not None:
        return f"git reset HEAD -- {_quote_shell(path)}"
    if op == "commit" and message is not None:
        return f"git commit -m {_quote_shell(message)}"
    if op == "commit_all" and message is not None:
        return f"git add -A && git commit -m {_quote_shell(message)}"
    if op == "push":
        return "git push"
    if op == "pull":
        return "git pull"
    if op == "checkout" and branch is not None:
        return f"git checkout {_quote_shell(branch)}"
    if op == "checkout_remote" and branch is not None and remote:
        prefix = remote + "/"
        local = branch[len(prefix):] if branch.startswith(prefix) else branch.rsplit("/", 1)[-1]
        return f"git checkout -b {_quote_shell(local)} {_quote_shell(branch)} || git checkout {_quote_shell(branch)}"
    raise ValueError(f"Unsupported git write operation: {op}")


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _unquote_path(value: str) -> str:
    if not value.startswith('"'):
        return value
    inner = value[1:-1] if value.endswith('"') else value[1:]
    replacements = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "a": "\a", "f": "\f", "v": "\v", "\\": "\\", '"': '"'}
    return re.sub(r"\\(.)", lambda m: replacements.get(m.group(1), m.group(1)), inner)


class ScmService:
    def __init__(self, root: Path, emit: Callable[[Dict[str, Any]], None]) -> None:
        self.root = root.resolve()
        self.emit = emit
        self._watcher = None
        self._watch_path: Optional[Path] = None
        self._watch_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()
        self._poll_stop = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_signature: Optional[tuple] = None

    def _git(self, cwd: Path, args: list[str], *, allow_failure: bool = False) -> str:
        try:
            proc = subprocess.run(
                ["git", "-c", "core.quotepath=false", *args],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GIT_TIMEOUT,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("git command not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("git command timed out") from exc
        if proc.returncode != 0 and not allow_failure:
            detail = (proc.stderr or proc.stdout or "git command failed").strip().splitlines()
            raise RuntimeError(detail[0] if detail else "git command failed")
        output = proc.stdout or ""
        if len(output.encode("utf-8", "replace")) > MAX_GIT_OUTPUT:
            raise RuntimeError("git output exceeded limit")
        return output

    def _safe_cwd(self, cwd: str | Path) -> Path:
        candidate = Path(cwd)
        candidate = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        if not _is_inside(self.root, candidate):
            raise ValueError("SCM cwd must be inside configured root")
        if not candidate.is_dir():
            candidate = candidate.parent
        return candidate

    def git_dir_of(self, cwd: str | Path) -> Optional[Path]:
        safe = self._safe_cwd(cwd)
        try:
            out = self._git(safe, ["rev-parse", "--absolute-git-dir"])
        except RuntimeError:
            return None
        text = out.strip()
        return Path(text).resolve() if text else None

    @staticmethod
    def _is_not_repo_error(exc: Exception) -> bool:
        return "not a git repository" in str(exc).lower()

    def status(self, cwd: str | Path) -> Dict[str, Any]:
        safe = self._safe_cwd(cwd)
        try:
            status_text = self._git(safe, ["status", "--porcelain=v1", "-b", "--find-renames"])
        except RuntimeError as exc:
            if self._is_not_repo_error(exc):
                self.stop_watch()
                return {
                    "notRepo": True, "branch": "", "detached": False, "upstream": None,
                    "ahead": 0, "behind": 0, "upstreamGone": False, "files": [], "branches": [], "stats": {},
                }
            raise
        branch_text = self._git(safe, ["for-each-ref", "refs/heads", "refs/remotes", "--format=%(refname)%09%(HEAD)"])
        work_stats = self._git(safe, ["diff", "--numstat"], allow_failure=True)
        staged_stats = self._git(safe, ["diff", "--cached", "--numstat"], allow_failure=True)
        result = {
            "notRepo": False,
            **self._parse_status_header(next((x[3:] for x in status_text.splitlines() if x.startswith("## ")), "")),
            "files": self._parse_status_files(status_text),
            "branches": self._parse_branches(branch_text),
            "stats": self._merge_stats(self._parse_numstat(work_stats), self._parse_numstat(staged_stats)),
        }
        self.ensure_watch(safe)
        return result

    def history(self, cwd: str | Path) -> list[Dict[str, Any]]:
        safe = self._safe_cwd(cwd)
        text = self._git(
            safe,
            [
                "log", "--all", "--graph", "--decorate=short", "--date=short",
                "--pretty=format:%H%x09%h%x09%an%x09%ad%x09%s%x09%D", "-n", "120",
            ],
        )
        out = []
        for line in text.splitlines():
            tab = line.find("\t")
            if tab < 0:
                continue
            prefix_hash = line[:tab]
            match = re.search(r"([0-9a-fA-F]{7,40})$", prefix_hash)
            if not match:
                continue
            fields = line[tab + 1:].split("\t")
            if len(fields) < 4:
                continue
            out.append({
                "hash": match.group(1),
                "shortHash": fields[0],
                "author": fields[1],
                "date": fields[2],
                "subject": fields[3],
                "decorations": fields[4] if len(fields) > 4 else "",
                "graph": prefix_hash[:match.start()],
            })
        return out

    def _safe_diff_path(self, cwd: Path, value: str) -> str:
        raw = Path(value)
        if raw.is_absolute():
            raise ValueError("SCM diff path must be relative to workspace")
        resolved = (cwd / raw).resolve()
        if not _is_inside(cwd, resolved):
            raise ValueError("SCM diff path escapes workspace")
        return resolved.relative_to(cwd.resolve()).as_posix()

    def file_diff(self, cwd: str | Path, path: str) -> Dict[str, str]:
        safe = self._safe_cwd(cwd)
        rel = self._safe_diff_path(safe, path)
        staged = self._git(safe, ["diff", "--cached", "--no-color", "--no-ext-diff", "--", rel], allow_failure=True)
        worktree = self._git(safe, ["diff", "--no-color", "--no-ext-diff", "--", rel], allow_failure=True)
        return {"staged": staged, "worktree": worktree}

    def commit_detail(self, cwd: str | Path, commit_hash: str) -> str:
        if not _HASH_RE.fullmatch(commit_hash or ""):
            raise ValueError("Invalid commit hash")
        safe = self._safe_cwd(cwd)
        return self._git(
            safe,
            ["show", "--no-color", "--no-ext-diff", "--find-renames", "--format=fuller", "--stat", "--patch", commit_hash],
        )

    def query(self, kind: str, cwd: str | Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        if kind == "status":
            return self.status(cwd)
        if kind == "history":
            return {"history": self.history(cwd)}
        if kind == "filediff":
            return self.file_diff(cwd, str(payload.get("path") or ""))
        if kind == "commit":
            return {"detail": self.commit_detail(cwd, str(payload.get("hash") or ""))}
        raise ValueError(f"Unknown SCM query: {kind}")

    @staticmethod
    def _parse_status_header(rest: str) -> Dict[str, Any]:
        out = {"branch": "HEAD", "detached": False, "upstream": None, "ahead": 0, "behind": 0, "upstreamGone": False}
        branch_part = rest
        flags = ""
        idx = rest.find(" [")
        if idx >= 0:
            branch_part, flags = rest[:idx], rest[idx + 2:]
            if flags.endswith("]"):
                flags = flags[:-1]
        if branch_part in {"HEAD (no branch)", "HEAD"}:
            out["detached"] = True
        else:
            if branch_part.startswith("No commits yet on "):
                branch_part = branch_part[len("No commits yet on "):]
            up = branch_part.find("...")
            if up >= 0:
                out["branch"] = branch_part[:up]
                out["upstream"] = branch_part[up + 3:]
            else:
                out["branch"] = branch_part
        for part in flags.split(","):
            part = part.strip()
            m = re.match(r"^(ahead|behind) (\d+)$", part)
            if m:
                out[m.group(1)] = int(m.group(2))
            elif part == "gone":
                out["upstreamGone"] = True
        return out

    @staticmethod
    def _parse_status_files(text: str) -> list[Dict[str, str]]:
        files = []
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line or line.startswith("## ") or len(line) < 3:
                continue
            path = line[3:]
            arrow = path.find(" -> ")
            if arrow >= 0:
                path = path[arrow + 4:]
            files.append({"path": _unquote_path(path), "x": line[0], "y": line[1]})
        return files

    @staticmethod
    def _parse_branches(text: str) -> list[Dict[str, Any]]:
        out = []
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            ref, head = parts[0], parts[1] == "*"
            if ref.startswith("refs/heads/"):
                out.append({"name": ref[len("refs/heads/"):], "current": head})
            elif ref.startswith("refs/remotes/"):
                short = ref[len("refs/remotes/"):]
                if short.endswith("/HEAD"):
                    continue
                slash = short.find("/")
                out.append({"name": short, "current": False, "remote": short[:slash] if slash > 0 else True})
        return out

    @staticmethod
    def _parse_numstat(text: str) -> Dict[str, tuple[int, int]]:
        out: Dict[str, tuple[int, int]] = {}
        for line in text.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            try:
                added = int(parts[0])
            except ValueError:
                added = 0
            try:
                deleted = int(parts[1])
            except ValueError:
                deleted = 0
            path = _unquote_path(parts[2].strip())
            old = out.get(path, (0, 0))
            out[path] = (old[0] + added, old[1] + deleted)
        return out

    @staticmethod
    def _merge_stats(a: Dict[str, tuple[int, int]], b: Dict[str, tuple[int, int]]) -> Dict[str, list[int]]:
        out: Dict[str, list[int]] = {}
        for source in (a, b):
            for path, pair in source.items():
                current = out.setdefault(path, [0, 0])
                current[0] += pair[0]
                current[1] += pair[1]
        return out

    def _schedule_changed(self) -> None:
        with self._lock:
            if self._watch_timer:
                self._watch_timer.cancel()
            self._watch_timer = threading.Timer(0.6, self._emit_changed)
            self._watch_timer.daemon = True
            self._watch_timer.start()

    def _emit_changed(self) -> None:
        with self._lock:
            self._watch_timer = None
        self.emit({"type": "scm_changed"})

    def ensure_watch(self, cwd: str | Path) -> None:
        git_dir = self.git_dir_of(cwd)
        if not git_dir:
            self.stop_watch()
            return
        with self._lock:
            if self._watch_path == git_dir and (self._watcher is not None or self._poll_thread is not None):
                return
        self.stop_watch()
        self._watch_path = git_dir
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            service = self

            class Handler(FileSystemEventHandler):
                def on_any_event(self, event) -> None:
                    service._schedule_changed()

            observer = Observer()
            observer.schedule(Handler(), str(git_dir), recursive=True)
            observer.daemon = True
            observer.start()
            self._watcher = observer
            return
        except Exception:
            self._watcher = None
        self._start_poll_fallback(git_dir)

    def _git_signature(self, git_dir: Path) -> tuple:
        paths = [git_dir / "HEAD", git_dir / "index", git_dir / "packed-refs"]
        refs = git_dir / "refs"
        if refs.exists():
            paths.extend(x for x in refs.rglob("*") if x.is_file())
        sig = []
        for path in paths:
            try:
                st = path.stat()
                sig.append((str(path.relative_to(git_dir)), st.st_mtime_ns, st.st_size))
            except OSError:
                pass
        return tuple(sorted(sig))

    def _start_poll_fallback(self, git_dir: Path) -> None:
        self._poll_stop.clear()
        self._poll_signature = self._git_signature(git_dir)

        def loop() -> None:
            while not self._poll_stop.wait(30):
                signature = self._git_signature(git_dir)
                if signature != self._poll_signature:
                    self._poll_signature = signature
                    self.emit({"type": "scm_changed"})

        self._poll_thread = threading.Thread(target=loop, name="scm-git-poll", daemon=True)
        self._poll_thread.start()

    def stop_watch(self) -> None:
        with self._lock:
            if self._watch_timer:
                self._watch_timer.cancel()
                self._watch_timer = None
            watcher = self._watcher
            self._watcher = None
            self._watch_path = None
            self._poll_stop.set()
            poll = self._poll_thread
            self._poll_thread = None
        if watcher:
            try:
                watcher.stop()
                watcher.join(timeout=1)
            except Exception:
                pass
        if poll and poll is not threading.current_thread():
            poll.join(timeout=0.2)
        self._poll_stop = threading.Event()

    def close(self) -> None:
        self.stop_watch()

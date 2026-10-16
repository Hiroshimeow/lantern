from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from .working_copy import WorkingCopyError, WorkingCopyStore

SYSTEM_PROMPT = """You are embedded in Lantern's chatbot.
The newest <lantern_context> block is authoritative for the user's current location.
When the user says this file, here, or this markdown, use that newest context.
For an active document with workingPath, read and edit only workingPath. logicalPath
is the saved project location and must not be read, edited, or written directly;
Lantern commits it only when the user explicitly chooses Save. Other project files
may be edited normally. Prefer native edit/write for mutations, preserve unrelated
content and formatting, and never claim tests passed unless you actually ran them."""

DEFAULT_MODEL_PRIORITY = (
    "gpt-6.1-sol",
    "gpt-6-astra",
    "claude-opus-5-5-high",
    "claude-sonnet-5-5-high",
    "gemini-3.1-pro-low",
)
PREFERRED_PROVIDER = "cliproxy-2080"


@dataclass
class _Pending:
    event: threading.Event
    response: Optional[dict[str, Any]] = None
    error: Optional[BaseException] = None


class PiChatManager:
    """One persistent native Pi RPC session for Lantern.

    The process uses pipes because Pi's rpc mode is JSONL, while Lantern's normal
    terminals stay on PTY/ConPTY. The browser transport and access gate are shared
    with Terminal; this class only owns the Pi child/session protocol.
    """

    def __init__(
        self,
        root: Path,
        emit: Callable[[dict[str, Any]], None],
        *,
        work_store: WorkingCopyStore,
        session_dir: Optional[Path] = None,
        argv_override: Optional[list[str]] = None,
        request_timeout: float = 15.0,
        max_models: int = 5,
    ) -> None:
        self.root = Path(root).resolve()
        self.emit = emit
        self.session_dir = (Path(session_dir) if session_dir else
                            Path.home() / ".lantern" / "pi-sessions").resolve()
        self.state_path = self.session_dir / "lantern-active.json"
        self.work_store = work_store
        self.guard_extension = Path(__file__).with_name("pi_working_copy_guard.ts").resolve()
        self.argv_override = list(argv_override) if argv_override else None
        self.request_timeout = max(1.0, float(request_timeout))
        self.max_models = max(1, min(int(max_models), 8))
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.turn_lock = threading.RLock()
        self.turn_rel: Optional[str] = None
        self.turn_last_hash: Optional[str] = None
        self.proc: Optional[subprocess.Popen[str]] = None
        self.reader: Optional[threading.Thread] = None
        self.stderr_reader: Optional[threading.Thread] = None
        self.pending: dict[str, _Pending] = {}
        self.stderr_tail: deque[str] = deque(maxlen=120)
        self.last_state: dict[str, Any] = {}
        self.streaming = False
        self.closed = False

    def rebind_emit(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self.emit = emit

    def _saved_session_file(self) -> str:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            value = str(raw.get("sessionFile") or "").strip()
            if not value:
                return ""
            path = Path(value).expanduser().resolve()
            path.relative_to(self.session_dir)
            if path.suffix.lower() != ".jsonl" or not path.is_file():
                return ""
            return str(path)
        except Exception:
            return ""

    def _persist_state(self, state: dict[str, Any]) -> None:
        session_id = str(state.get("sessionId") or "")
        if not session_id:
            return
        self.session_dir.mkdir(parents=True, exist_ok=True)
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        session_file = str(state.get("sessionFile") or "").strip()
        payload = {
            "sessionId": session_id,
            "sessionFile": session_file,
            "model": {
                "provider": str(model.get("provider") or ""),
                "id": str(model.get("id") or ""),
            },
            "updatedAt": time.time(),
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.state_path)

    @staticmethod
    def _resolve_pi() -> str:
        explicit = os.environ.get("LANTERN_PI_COMMAND", "").strip()
        if explicit:
            return explicit
        if os.name == "nt":
            return (shutil.which("pi.cmd") or shutil.which("pi.exe") or
                    shutil.which("pi") or "pi.cmd")
        return shutil.which("pi") or "pi"

    def _command(self) -> list[str]:
        if self.argv_override:
            return list(self.argv_override)
        pi = self._resolve_pi()
        prefix = [pi]
        if os.name == "nt" and Path(pi).suffix.lower() in {".cmd", ".bat"}:
            # npm's pi.cmd is only a wrapper around Node. Prefer the real JS entry
            # so spaces/quotes do not pass through cmd.exe and corrupt CLI values.
            cli = (Path(pi).resolve().parent / "node_modules" / "@earendil-works"
                   / "pi-coding-agent" / "dist" / "bundle" / "cli.js")
            node = shutil.which("node.exe") or shutil.which("node")
            if node and cli.is_file():
                prefix = [node, str(cli)]
        if not self.guard_extension.is_file():
            raise RuntimeError("Lantern Pi working-copy guard extension is missing")
        args = prefix + [
            "--mode", "rpc",
            "--session-dir", str(self.session_dir),
            "--name", "LanternChat",
            "--append-system-prompt", SYSTEM_PROMPT,
            "--tools", "read,edit,write,grep,find,ls",
            "--no-extensions",
            "--extension", str(self.guard_extension),
            "--no-mcp",
        ]
        session_file = self._saved_session_file()
        if session_file:
            args.extend(["--session", session_file])
        if os.name == "nt" and len(prefix) == 1 and Path(pi).suffix.lower() in {".cmd", ".bat"}:
            comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
            return [comspec, "/D", "/C", subprocess.list2cmdline(args)]
        return args

    def ensure_started(self) -> None:
        with self.lock:
            if self.closed:
                raise RuntimeError("Pi chat manager is closed")
            if self.proc is not None and self.proc.poll() is None:
                return
            self.session_dir.mkdir(parents=True, exist_ok=True)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            child_env = dict(os.environ)
            child_env["LANTERN_PI_GUARD_STATE"] = str(self.work_store.guard_path)
            self.proc = subprocess.Popen(
                self._command(),
                cwd=str(self.root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                env=child_env,
            )
            self.reader = threading.Thread(target=self._reader_loop, name="lantern-pi-rpc", daemon=True)
            self.stderr_reader = threading.Thread(target=self._stderr_loop, name="lantern-pi-stderr", daemon=True)
            self.reader.start()
            self.stderr_reader.start()

    def _stderr_loop(self) -> None:
        proc = self.proc
        if not proc or not proc.stderr:
            return
        try:
            for line in proc.stderr:
                line = line.rstrip("\r\n")
                if line:
                    self.stderr_tail.append(line)
        except Exception:
            pass

    def _reader_loop(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    self.emit({"type": "chat_protocol_warning", "line": line[:2000]})
                    continue
                if not isinstance(event, dict):
                    continue
                req_id = str(event.get("id") or "")
                pending = None
                if event.get("type") == "response" and req_id:
                    with self.lock:
                        pending = self.pending.pop(req_id, None)
                    if pending is not None:
                        pending.response = event
                        pending.event.set()
                        continue
                typ = str(event.get("type") or "")
                if typ == "message_update":
                    self.streaming = True
                elif typ == "agent_settled":
                    self.streaming = False
                if typ == "tool_execution_end":
                    self._emit_work_update(final=False)
                elif typ == "agent_settled":
                    self._emit_work_update(final=True)
                self.emit({"type": "chat_pi_event", "event": event})
        finally:
            self._emit_work_update(final=True)
            code = proc.poll()
            if code is None:
                try:
                    code = proc.wait(timeout=0.5)
                except Exception:
                    code = None
            error = RuntimeError(f"Pi RPC exited ({code})")
            with self.lock:
                waiting = list(self.pending.values())
                self.pending.clear()
                if self.proc is proc:
                    self.proc = None
            for item in waiting:
                item.error = error
                item.event.set()
            self.streaming = False
            self.emit({"type": "chat_process_exit", "exitCode": code})

    def request(self, command: dict[str, Any], *, timeout: Optional[float] = None) -> dict[str, Any]:
        self.ensure_started()
        payload = dict(command)
        req_id = str(payload.get("id") or uuid4().hex)
        payload["id"] = req_id
        pending = _Pending(threading.Event())
        with self.lock:
            self.pending[req_id] = pending
            proc = self.proc
        if not proc or not proc.stdin:
            with self.lock:
                self.pending.pop(req_id, None)
            raise RuntimeError("Pi RPC stdin unavailable")
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self.write_lock:
                proc.stdin.write(raw)
                proc.stdin.flush()
        except Exception:
            with self.lock:
                self.pending.pop(req_id, None)
            raise
        wait = self.request_timeout if timeout is None else max(0.1, float(timeout))
        if not pending.event.wait(wait):
            with self.lock:
                self.pending.pop(req_id, None)
            raise TimeoutError(f"Pi RPC request timed out: {payload.get('type')}")
        if pending.error:
            raise pending.error
        response = pending.response or {}
        if response.get("success") is False:
            raise RuntimeError(str(response.get("error") or f"Pi RPC failed: {payload.get('type')}"))
        return response

    def _emit_work_update(self, *, final: bool) -> None:
        with self.turn_lock:
            rel = self.turn_rel
            if not rel:
                return
            if not final:
                try:
                    current_hash = self.work_store.peek_hash(rel)
                except Exception as exc:
                    self.emit({"type": "chat_work_error", "path": rel, "error": str(exc), "final": False})
                    return
                if current_hash == self.turn_last_hash:
                    return
                self.turn_last_hash = current_hash
                self.emit({
                    "type": "chat_work_changed",
                    "path": rel,
                    "hash": current_hash,
                    "final": False,
                })
                return

            try:
                result = self.work_store.end_turn(rel)
            except Exception as exc:
                self.emit({"type": "chat_work_error", "path": rel, "error": str(exc), "final": True})
                self.turn_rel = None
                self.turn_last_hash = None
                return

            self.turn_rel = None
            self.turn_last_hash = None
            self.emit({
                "type": "chat_work_changed",
                "path": rel,
                "hash": result.get("hash"),
                "final": True,
            })
            if result.get("realTouched"):
                self.emit({
                    "type": "chat_real_file_touched",
                    "path": rel,
                    "error": "Saved project file changed while Pi was editing the working copy.",
                })

    def get_state(self) -> dict[str, Any]:
        response = self.request({"type": "get_state"})
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        self.last_state = dict(data)
        self._persist_state(data)
        return data

    def get_messages(self) -> list[dict[str, Any]]:
        response = self.request({"type": "get_messages"})
        data = response.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return [item for item in data["messages"] if isinstance(item, dict)]
        return []

    def available_models(self) -> list[dict[str, Any]]:
        response = self.request({"type": "get_available_models"})
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        raw = data.get("models") if isinstance(data.get("models"), list) else []
        models = [m for m in raw if isinstance(m, dict) and m.get("id") and m.get("provider")]
        selected: list[dict[str, Any]] = []
        used: set[tuple[str, str]] = set()
        for wanted in DEFAULT_MODEL_PRIORITY:
            candidates = [m for m in models if str(m.get("id")) == wanted]
            candidates.sort(key=lambda m: 0 if str(m.get("provider")) == PREFERRED_PROVIDER else 1)
            if candidates:
                item = candidates[0]
                key = (str(item.get("provider")), str(item.get("id")))
                if key not in used:
                    selected.append(self._model_public(item))
                    used.add(key)
            if len(selected) >= self.max_models:
                break
        if len(selected) < self.max_models:
            for item in models:
                key = (str(item.get("provider")), str(item.get("id")))
                if key in used:
                    continue
                selected.append(self._model_public(item))
                used.add(key)
                if len(selected) >= self.max_models:
                    break
        return selected

    @staticmethod
    def _model_public(model: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": str(model.get("provider") or ""),
            "id": str(model.get("id") or ""),
            "name": str(model.get("name") or model.get("id") or ""),
            "reasoning": bool(model.get("reasoning")),
            "contextWindow": int(model.get("contextWindow") or 0),
        }

    def set_model(self, provider: str, model_id: str) -> dict[str, Any]:
        if not provider or not model_id:
            raise ValueError("provider and modelId are required")
        response = self.request({"type": "set_model", "provider": provider, "modelId": model_id})
        try:
            self.get_state()
        except Exception:
            pass
        return response

    def new_session(self) -> dict[str, Any]:
        response = self.request({"type": "new_session"})
        state = self.get_state()
        self.emit({"type": "chat_session_changed", "state": state})
        return state

    def normalize_context(self, context: Optional[dict[str, Any]]) -> dict[str, Any]:
        source = context if isinstance(context, dict) else {}
        result: dict[str, Any] = {}
        kind = str(source.get("kind") or "unknown").strip().lower()
        result["kind"] = kind if kind in {"folder", "file", "markdown"} else "unknown"

        def canonical(value: Any) -> str:
            raw = str(value or "").strip()
            if not raw:
                return ""
            cleaned = raw.replace("\\", os.sep).replace("/", os.sep)
            candidate = Path(cleaned)
            if not candidate.is_absolute():
                candidate = self.root / cleaned.lstrip("\\/")
            candidate = candidate.resolve()
            try:
                candidate.relative_to(self.root)
            except ValueError as exc:
                raise ValueError("Chat context path must stay inside the configured root") from exc
            return str(candidate)

        for key in ("path", "folder"):
            value = canonical(source.get(key))
            if value:
                result[key] = value

        mode = str(source.get("markdownMode") or "").strip().lower()
        if mode in {"preview", "visual", "source"}:
            result["markdownMode"] = mode
        if source.get("line") not in (None, ""):
            try:
                line = int(source["line"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Chat context line must be an integer") from exc
            if line > 0:
                result["line"] = min(line, 10_000_000)
        selected = str(source.get("selectedText") or "")
        if selected:
            result["selectedText"] = selected[:8000]
        return result

    @staticmethod
    def build_prompt(message: str, context: Optional[dict[str, Any]] = None) -> str:
        text = str(message or "").strip()
        if not text:
            raise ValueError("Chat message is empty")
        if len(text) > 200_000:
            raise ValueError("Chat message is too large")
        context = context if isinstance(context, dict) else {}
        fields = []
        for key in ("kind", "folder", "path", "logicalPath", "workingPath",
                    "markdownMode", "line"):
            value = context.get(key)
            if value is not None and value != "":
                fields.append(f"{key}: {value}")
        selected = str(context.get("selectedText") or "")
        if selected:
            fields.append("selectedText:\n" + selected[:8000])
        block = "\n".join(fields) if fields else "kind: unknown"
        return f"<lantern_context>\n{block}\n</lantern_context>\n\n<user_request>\n{text}\n</user_request>"

    def prompt(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        work_hash: Optional[str] = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_context(context)
        if normalized.get("kind") == "markdown":
            real_path = normalized.get("path")
            if not real_path:
                raise ValueError("Markdown chat context is missing its path")
            real = Path(str(real_path)).resolve()
            try:
                rel = real.relative_to(self.root).as_posix()
            except ValueError as exc:
                raise ValueError("Markdown chat path must stay inside the configured root") from exc
            with self.turn_lock:
                if self.turn_rel:
                    raise RuntimeError("A Pi working-copy turn is already active")
                try:
                    turn = self.work_store.begin_turn(rel, work_hash)
                except WorkingCopyError as exc:
                    raise RuntimeError(str(exc)) from exc
                self.turn_rel = rel
                self.turn_last_hash = str(turn.get("hash") or "") or None
            normalized["logicalPath"] = rel
            normalized["workingPath"] = str(turn["workingPath"])
        elif self.turn_rel:
            raise RuntimeError("A Pi working-copy turn is already active")

        wrapped = self.build_prompt(message, normalized)
        try:
            return self.request({"type": "prompt", "message": wrapped})
        except Exception:
            self._emit_work_update(final=True)
            raise

    def abort(self) -> dict[str, Any]:
        response = self.request({"type": "abort"}, timeout=5.0)
        self._emit_work_update(final=True)
        return response

    def summary(self) -> dict[str, Any]:
        state = dict(self.last_state)
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        with self.lock:
            running = self.proc is not None and self.proc.poll() is None
        return {
            "running": running,
            "streaming": bool(self.streaming),
            "sessionId": str(state.get("sessionId") or ""),
            "model": self._model_public(model) if model else None,
            "terminalId": "pi_chat",
        }

    def close(self) -> None:
        self._emit_work_update(final=True)
        with self.lock:
            self.closed = True
            proc = self.proc
            self.proc = None
            waiting = list(self.pending.values())
            self.pending.clear()
        for item in waiting:
            item.error = RuntimeError("Pi chat manager closed")
            item.event.set()
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass
        current = threading.current_thread()
        for thread in (self.reader, self.stderr_reader):
            if thread and thread is not current and thread.is_alive():
                thread.join(timeout=0.5)

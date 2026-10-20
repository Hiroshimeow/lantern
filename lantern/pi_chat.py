from __future__ import annotations

import html
import json
import os
import re
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
from .bot_config import LanternBotConfig
from .bot_usage import LanternBotUsage


@dataclass
class _Pending:
    event: threading.Event
    response: Optional[dict[str, Any]] = None
    error: Optional[BaseException] = None


def extract_message_structured(msg: dict[str, Any]) -> dict[str, Any]:
    """Safely extract text, thinking, tool calls, tool results, and subagent notifications
    from any Pi RPC or JSONL message without ever producing '[object Object]'."""
    if not isinstance(msg, dict):
        return {"role": "system", "text": str(msg or ""), "thinking": "", "tools": [], "subagents": []}

    role = str(msg.get("role") or "system")
    content = msg.get("content")
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tools: list[dict[str, Any]] = []

    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                btype = str(item.get("type") or "")
                if btype == "text":
                    text_parts.append(str(item.get("text") or item.get("content") or ""))
                elif btype in ("thinking", "reasoning"):
                    thinking_parts.append(str(item.get("thinking") or item.get("text") or ""))
                elif btype in ("toolCall", "tool_use", "tool_call"):
                    tools.append({
                        "id": str(item.get("id") or item.get("toolCallId") or ""),
                        "name": str(item.get("name") or item.get("toolName") or "tool"),
                        "arguments": item.get("arguments") or item.get("input") or item.get("args") or {},
                    })
                elif btype in ("toolResult", "tool_result"):
                    inner = item.get("content")
                    if isinstance(inner, list):
                        inner_txt = "\n".join(
                            str(p.get("text") or "") if isinstance(p, dict) else str(p)
                            for p in inner
                        )
                    else:
                        inner_txt = str(inner or item.get("text") or "")
                    tools.append({
                        "id": str(item.get("toolUseId") or item.get("toolCallId") or ""),
                        "name": str(item.get("toolName") or "result"),
                        "result": inner_txt,
                        "isError": bool(item.get("isError")),
                    })
                elif isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    text_parts.append(item["content"])
                elif isinstance(item.get("nested"), list):
                    for sub_item in item["nested"]:
                        if isinstance(sub_item, dict):
                            sub_txt = sub_item.get("text") or sub_item.get("content")
                            if isinstance(sub_txt, str):
                                text_parts.append(sub_txt)
    elif isinstance(content, dict):
        if isinstance(content.get("text"), str):
            text_parts.append(content["text"])
        else:
            text_parts.append(json.dumps(content, ensure_ascii=False))

    if not text_parts and isinstance(msg.get("text"), str):
        text_parts.append(msg["text"])
    if not text_parts and isinstance(msg.get("displayText"), str):
        text_parts.append(msg["displayText"])
    if not thinking_parts and isinstance(msg.get("thinking"), str) and msg["thinking"]:
        thinking_parts.append(msg["thinking"])
    if not tools and isinstance(msg.get("tools"), list):
        tools.extend(t for t in msg["tools"] if isinstance(t, dict))
    if not tools and isinstance(msg.get("toolCalls"), list):
        tools.extend(t for t in msg["toolCalls"] if isinstance(t, dict))

    full_text = "\n".join(p for p in text_parts if p is not None)
    subagents = parse_task_notifications(full_text)
    return {
        "id": str(msg.get("id") or ""),
        "role": role,
        "text": full_text,
        "thinking": "\n".join(t for t in thinking_parts if t),
        "tools": tools,
        "subagents": subagents,
        "timestamp": msg.get("timestamp") or msg.get("createdAt"),
        "usage": msg.get("usage") if isinstance(msg.get("usage"), dict) else None,
    }


_TASK_NOTIFICATION_RE = re.compile(
    r"<task-notification>([\s\S]*?)</task-notification>"
    r"(?:\s*Full transcript available at:\s*([^\r\n<]+))?",
    re.IGNORECASE,
)


def _xml_tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", block, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_task_notifications(text: str) -> list[dict[str, Any]]:
    """Parse <task-notification> blocks from subagent outputs into structured dicts."""
    if not text or "<task-notification>" not in text:
        return []
    results: list[dict[str, Any]] = []
    for match in _TASK_NOTIFICATION_RE.finditer(text):
        body = match.group(1) or ""
        transcript_tail = (match.group(2) or "").strip()
        usage_raw = _xml_tag(body, "usage")
        output_file = _xml_tag(body, "output-file") or transcript_tail
        results.append({
            "taskId": _xml_tag(body, "task-id"),
            "toolUseId": _xml_tag(body, "tool-use-id"),
            "outputFile": output_file,
            "status": _xml_tag(body, "status") or "Done",
            "summary": _xml_tag(body, "summary"),
            "result": _xml_tag(body, "result"),
            "usage": {
                "totalTokens": int(_xml_tag(usage_raw, "total_tokens") or 0) if _xml_tag(usage_raw, "total_tokens").isdigit() else 0,
                "toolUses": int(_xml_tag(usage_raw, "tool_uses") or 0) if _xml_tag(usage_raw, "tool_uses").isdigit() else 0,
                "contextPercent": int(_xml_tag(usage_raw, "context_percent") or 0) if _xml_tag(usage_raw, "context_percent").isdigit() else 0,
                "durationMs": int(_xml_tag(usage_raw, "duration_ms") or 0) if _xml_tag(usage_raw, "duration_ms").isdigit() else 0,
            },
        })
    return results


class LanternBotManager:
    """Persistent native Pi runtime session manager for LanternBot on port 9999.

    Supports:
    - Real-time JSONL RPC over pipes with working-copy guard
    - YAML-driven access policies for localhost (Full/YOLO '*' by default) and LAN
    - Reliable .jsonl session transcript persistence for both User and Assistant turns
    - Robust Windows & POSIX Pi CLI discovery (.cmd shim unwrapping, NVM/Volta/npm paths)
    - Favorite models & Last-Selected default model persistence
    - Automatic stale turn recovery (prevents stuck 'Markdown turn is already active')
    - Fire-and-forget extension_ui_response (prevents RPC timeout crashes)
    - Duplicate empty session prevention ('newchat' guard)
    - Full-context HTML transcript export & Subagent transcript inspection
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
        bot_config: Optional[LanternBotConfig] = None,
        usage_path: Optional[Path] = None,
        client_session_id: str = "",
        parent_bot: Optional["LanternBotManager"] = None,
    ) -> None:
        self.root = Path(root).resolve()
        self._raw_emit = emit
        safe_cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        if safe_cid == "default":
            safe_cid = ""
        self.client_session_id: str = safe_cid
        self._parent_bot: Optional["LanternBotManager"] = parent_bot
        self._child_bots: dict[str, "LanternBotManager"] = {}
        if self.client_session_id:
            def _scoped_emit(payload: dict[str, Any]) -> None:
                enriched = dict(payload)
                enriched.setdefault("clientSessionId", self.client_session_id)
                emit(enriched)
            self.emit = _scoped_emit
        else:
            self.emit = emit
        self.session_dir = (Path(session_dir) if session_dir else
                            Path.home() / ".lantern" / "pi-sessions").resolve()
        state_fname = f"lantern-active-{self.client_session_id}.json" if self.client_session_id else "lantern-active.json"
        self.state_path = self.session_dir / state_fname
        self.prefs_path = self.session_dir / "lantern-model-prefs.json"
        self.work_store = work_store
        self.guard_extension = Path(__file__).with_name("pi_working_copy_guard.ts").resolve()
        self.argv_override = list(argv_override) if argv_override else None
        self.request_timeout = max(1.0, float(request_timeout))
        self.bot_config = bot_config or LanternBotConfig()
        self.usage = LanternBotUsage(
            usage_path or (Path.home() / ".lantern" / "lanternbot-usage.json")
        )
        self.selection_initialized: set[str] = set()
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.turn_lock = threading.RLock()
        self.turn_rel: Optional[str] = None
        self.turn_last_hash: Optional[str] = None
        self.turn_started_at: float = 0.0
        self.proc: Optional[subprocess.Popen[str]] = None
        self.reader: Optional[threading.Thread] = None
        self.stderr_reader: Optional[threading.Thread] = None
        self.pending: dict[str, _Pending] = {}
        self.stderr_tail: deque[str] = deque(maxlen=120)
        self.last_state: dict[str, Any] = {}
        self.streaming = False
        self.closed = False
        self._turn_in_progress = False
        self.thinking_level: str = "medium"
        self.tool_preset: str = "full"
        self.steer_queue: deque[dict[str, Any]] = deque()
        self.unsupported_cli_flags: set[str] = set()
        self._cli_probed: bool = False
        self._session_messages: list[dict[str, Any]] = []
        self._turn_stream_text: list[str] = []
        self._turn_stream_thinking: list[str] = []
        self._subturn_stream_text: list[str] = []
        self._subturn_stream_thinking: list[str] = []
        self._turn_stream_tools: list[dict[str, Any]] = []
        self._turn_assistant_saved: bool = False
        self._active_turn_scope: str = "local"
        self._turn_had_tool_call: bool = False
        self._last_stop_reason: str = ""
        self._switched_session_override: Optional[dict[str, str]] = None

    def _load_prefs(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "favorites": [],
            "lastModel": None,
            "thinkingLevel": "medium",
            "toolPreset": "full",
            "customSystemPrompt": "",
            "useGlobalSkills": True,
            "customSkillPaths": [],
        }
        try:
            if self.prefs_path.is_file():
                data = json.loads(self.prefs_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception:
            pass
        if not isinstance(defaults.get("customSkillPaths"), list):
            raw_paths = str(defaults.get("customSkillPaths") or "")
            defaults["customSkillPaths"] = [p.strip() for p in re.split(r"[\r\n,;]+", raw_paths) if p.strip()]
        defaults["useGlobalSkills"] = bool(defaults.get("useGlobalSkills", True))
        defaults["customSystemPrompt"] = str(defaults.get("customSystemPrompt") or "")
        return defaults

    def _save_prefs(self, patch: dict[str, Any]) -> dict[str, Any]:
        prefs = self._load_prefs()
        prefs.update(patch)
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.prefs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.prefs_path)
        except Exception:
            pass
        return prefs

    def toggle_favorite_model(self, provider: str, model_id: str) -> dict[str, Any]:
        p = provider.strip()
        m = model_id.strip()
        key = f"{p}/{m}" if p else m
        prefs = self._load_prefs()
        favs = [str(x) for x in prefs.get("favorites") or [] if isinstance(x, str)]
        if key in favs:
            favs.remove(key)
            is_fav = False
        else:
            favs.insert(0, key)
            is_fav = True
        self._save_prefs({"favorites": favs})
        return {"ok": True, "key": key, "favorite": is_fav, "favorites": favs}

    def set_thinking_level(self, level: str) -> dict[str, Any]:
        clean = str(level or "medium").strip().lower()
        if clean not in {"off", "minimal", "low", "medium", "high", "xhigh"}:
            clean = "medium"
        self.thinking_level = clean
        self._save_prefs({"thinkingLevel": clean})
        try:
            with self.lock:
                running = self.proc is not None and self.proc.poll() is None
            if running:
                self.send_fire_and_forget({"type": "set_thinking_level", "level": clean})
        except Exception:
            pass
        return {"ok": True, "thinkingLevel": clean}

    def set_tool_preset(self, preset: str) -> dict[str, Any]:
        clean = str(preset or "full").strip().lower()
        if clean not in {"full", "code", "readonly", "none"}:
            clean = "full"
        self.tool_preset = clean
        self._save_prefs({"toolPreset": clean})
        return {"ok": True, "toolPreset": clean}

    def update_custom_settings(
        self,
        *,
        custom_system_prompt: Optional[str] = None,
        use_global_skills: Optional[bool] = None,
        custom_skill_paths: Any = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if custom_system_prompt is not None:
            patch["customSystemPrompt"] = str(custom_system_prompt).strip()[:16000]
        if use_global_skills is not None:
            patch["useGlobalSkills"] = bool(use_global_skills)
        if custom_skill_paths is not None:
            if isinstance(custom_skill_paths, str):
                paths = [p.strip() for p in re.split(r"[\r\n,;]+", custom_skill_paths) if p.strip()]
            elif isinstance(custom_skill_paths, list):
                paths = [str(p).strip() for p in custom_skill_paths if str(p).strip()]
            else:
                paths = []
            patch["customSkillPaths"] = paths[:24]
        prefs = self._save_prefs(patch)
        return {
            "ok": True,
            "prefs": prefs,
            "skills": self.discover_skills(),
        }

    @staticmethod
    def _extract_skill_description(skill_md: Path, fallback_name: str) -> str:
        try:
            head = skill_md.read_text(encoding="utf-8", errors="ignore")[:2000]
            m = re.search(r"^description:\s*(.+)$", head, re.MULTILINE | re.IGNORECASE)
            if m:
                return m.group(1).strip().strip("\"'")[:140]
        except Exception:
            pass
        return f"Run skill {fallback_name}"

    def discover_skills(self) -> list[dict[str, str]]:
        prefs = self._load_prefs()
        use_global = bool(prefs.get("useGlobalSkills", True))
        custom_paths = prefs.get("customSkillPaths") or []
        candidate_roots: list[tuple[str, Path]] = [
            ("workspace", (self.root / ".pi" / "skills").resolve()),
        ]
        if use_global:
            candidate_roots.append(("global", (Path.home() / ".pi" / "agent" / "skills").resolve()))
            candidate_roots.append(("global", (Path.home() / ".pi" / "skills").resolve()))
        for raw_p in custom_paths:
            expanded = os.path.expandvars(str(raw_p or "").strip())
            if not expanded:
                continue
            cand = Path(expanded).expanduser()
            if not cand.is_absolute():
                cand = (self.root / cand).resolve()
            else:
                cand = cand.resolve()
            candidate_roots.append(("custom", cand))

        skills: list[dict[str, str]] = []
        seen_names: set[str] = set()
        for scope_label, sroot in candidate_roots:
            try:
                if not sroot.exists() or not sroot.is_dir():
                    continue
                direct_md = sroot / "SKILL.md"
                if direct_md.is_file():
                    sname = sroot.name
                    if sname not in seen_names:
                        seen_names.add(sname)
                        skills.append({
                            "name": sname,
                            "command": f"/{sname}",
                            "category": "skill",
                            "scope": scope_label,
                            "path": str(direct_md),
                            "description": self._extract_skill_description(direct_md, sname),
                        })
                for item in sorted(sroot.iterdir()):
                    if item.is_dir():
                        sub_md = item / "SKILL.md"
                        if sub_md.is_file() and item.name not in seen_names:
                            seen_names.add(item.name)
                            skills.append({
                                "name": item.name,
                                "command": f"/{item.name}",
                                "category": "skill",
                                "scope": scope_label,
                                "path": str(sub_md),
                                "description": self._extract_skill_description(sub_md, item.name),
                            })
            except Exception:
                continue
        return skills

    def _all_bot_instances(self) -> list["LanternBotManager"]:
        root_bot = self._parent_bot or self
        with root_bot.lock:
            return [root_bot] + [b for b in root_bot._child_bots.values() if not b.closed]

    def get_session_bot(self, client_session_id: Optional[str] = None) -> "LanternBotManager":
        """Return or lazily create an isolated LanternBotManager for a specific tab/client session ID."""
        root_bot = self._parent_bot or self
        cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        if not cid or cid == "default":
            return root_bot
        with root_bot.lock:
            child = root_bot._child_bots.get(cid)
            if child is None or child.closed:
                child = LanternBotManager(
                    root_bot.root,
                    root_bot._raw_emit,
                    work_store=root_bot.work_store,
                    session_dir=root_bot.session_dir,
                    argv_override=root_bot.argv_override,
                    request_timeout=root_bot.request_timeout,
                    bot_config=root_bot.bot_config,
                    usage_path=root_bot.usage.path,
                    client_session_id=cid,
                    parent_bot=root_bot,
                )
                root_bot._child_bots[cid] = child
            return child

    def list_sessions(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        active_file = self._saved_session_file()
        current_sid = str((self._switched_session_override or {}).get("sessionId") or self.last_state.get("sessionId") or "").strip()
        busy_session_ids: set[str] = set()
        active_session_ids: set[str] = set()
        for bot_inst in self._all_bot_instances():
            bsid = str((bot_inst._switched_session_override or {}).get("sessionId") or bot_inst.last_state.get("sessionId") or "").strip()
            if bsid:
                active_session_ids.add(bsid)
                if bot_inst.streaming or bot_inst._turn_in_progress:
                    busy_session_ids.add(bsid)
        try:
            if not self.session_dir.is_dir():
                return results
            files = sorted(
                self.session_dir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
                reverse=True,
            )
            seen_ids: dict[str, dict[str, Any]] = {}
            for fpath in files[:60]:
                try:
                    if ".corrupted-" in fpath.name:
                        continue
                    stat = fpath.stat()
                    if stat.st_size == 0:
                        continue
                    resolved_str = str(fpath.resolve())
                    preview = ""
                    session_id = fpath.stem
                    is_native_pi = False
                    msg_count = 0
                    with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                        for idx, line in enumerate(fh):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict):
                                    if idx == 0 and obj.get("type") == "session":
                                        if obj.get("id"):
                                            session_id = str(obj["id"])
                                        if not obj.get("lantern"):
                                            is_native_pi = True
                                    if obj.get("sessionId"):
                                        session_id = str(obj["sessionId"])
                                    msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
                                    role = str(msg.get("role") or "")
                                    if role in ("user", "assistant"):
                                        msg_count += 1
                                    if role == "user" and not preview:
                                        txt = extract_message_structured(msg).get("text", "")
                                        req_m = re.search(r"<user_request>\s*([\s\S]*?)\s*</user_request>", txt)
                                        preview = (req_m.group(1) if req_m else txt).strip()[:80]
                            except Exception:
                                pass
                    is_cur = bool(
                        (current_sid and session_id == current_sid)
                        or (active_file and Path(active_file).resolve() == fpath.resolve())
                    )
                    entry = {
                        "id": session_id,
                        "name": preview or fpath.stem,
                        "label": preview or fpath.stem,
                        "path": resolved_str,
                        "updatedAt": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                        "current": is_cur,
                        "busy": session_id in busy_session_ids,
                        "activeInTab": session_id in active_session_ids,
                        "messageCount": msg_count,
                        "_isNative": is_native_pi,
                    }
                    if session_id in seen_ids:
                        existing = seen_ids[session_id]
                        if not existing["name"] or existing["name"] == existing["id"]:
                            if preview:
                                existing["name"] = preview
                                existing["label"] = preview
                        if msg_count > existing.get("messageCount", 0):
                            existing["messageCount"] = msg_count
                            existing["path"] = resolved_str
                        elif is_native_pi and not existing.get("_isNative") and msg_count == existing.get("messageCount", 0):
                            existing["path"] = resolved_str
                            existing["_isNative"] = True
                        if is_cur:
                            existing["current"] = True
                    else:
                        seen_ids[session_id] = entry
                        results.append(entry)
                except Exception:
                    continue
            for item in results:
                item.pop("_isNative", None)
        except Exception:
            pass
        return results[:40]

    def _reset_tool_scope(self) -> None:
        with self.turn_lock:
            self._turn_in_progress = False
            # Do not downgrade shared work_store scope to 'lan' if another tab's bot is actively in a local turn
            any_local_turn = any(
                b is not self and b._turn_in_progress and b._active_turn_scope == "local"
                for b in self._all_bot_instances()
            )
            if not any_local_turn:
                setter = getattr(self.work_store, 'set_runtime_scope', None)
                if callable(setter):
                    setter('lan', self.bot_config.lan_access.tools)

    def rebind_emit(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self._raw_emit = emit
        if self.client_session_id:
            cid = self.client_session_id
            def _scoped_emit(payload: dict[str, Any]) -> None:
                enriched = dict(payload)
                enriched.setdefault("clientSessionId", cid)
                emit(enriched)
            self.emit = _scoped_emit
        else:
            self.emit = emit
        for child in list(self._child_bots.values()):
            child.rebind_emit(emit)

    @staticmethod
    def _repair_pi_session_file(path: Path) -> bool:
        """Validate and auto-repair a Pi session .jsonl file. Removes any corrupted
        lines (such as malformed non-Pi entries missing id/parentId) and promotes a buried
        session header if needed to prevent 'Error: Session file is not a valid pi session'."""
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return False
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                raw_lines = [l.strip() for l in fh if l.strip()]
            if not raw_lines:
                return False
            header_idx = -1
            for idx, l in enumerate(raw_lines):
                try:
                    obj = json.loads(l)
                    if isinstance(obj, dict) and obj.get("type") == "session":
                        header_idx = idx
                        break
                except Exception:
                    continue
            if header_idx < 0:
                return False
            valid_lines = [raw_lines[header_idx]]
            modified = header_idx != 0
            for idx, l in enumerate(raw_lines):
                if idx == header_idx:
                    continue
                try:
                    obj = json.loads(l)
                    if not isinstance(obj, dict):
                        modified = True
                        continue
                    otype = obj.get("type")
                    if otype == "session":
                        modified = True
                        continue
                    if otype == "message":
                        if "id" not in obj and "parentId" not in obj:
                            modified = True
                            continue
                    elif otype not in (
                        "model_change", "thinking_level_change", "usage",
                        "compaction", "context_edit", "branch_summary",
                        "custom", "custom_message", "label", "session_info"
                    ):
                        modified = True
                        continue
                    valid_lines.append(l)
                except Exception:
                    modified = True
                    continue
            if modified:
                tmp = path.with_suffix(".repaired.tmp")
                tmp.write_text("\n".join(valid_lines) + "\n", encoding="utf-8")
                tmp.replace(path)
            return True
        except Exception:
            return False

    def _clear_session_file(self) -> None:
        with self.lock:
            self.last_state["sessionFile"] = None
            try:
                if self.state_path.is_file():
                    raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                    raw["sessionFile"] = ""
                    tmp = self.state_path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    tmp.replace(self.state_path)
            except Exception:
                pass

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
            if not self._repair_pi_session_file(path):
                try:
                    bak = path.with_suffix(f".corrupted-{int(time.time())}.bak")
                    path.rename(bak)
                except Exception:
                    pass
                self._clear_session_file()
                return ""
            return str(path)
        except Exception:
            return ""

    def _resolve_session_jsonl_path(self, session_id: str = "", session_file: str = "") -> Optional[Path]:
        raw_file = str(session_file or self.last_state.get("sessionFile") or "").strip()
        if raw_file:
            try:
                cand = Path(raw_file).expanduser().resolve()
                cand.relative_to(self.session_dir)
                if cand.suffix.lower() == ".jsonl":
                    return cand
            except Exception:
                pass
        saved_file = self._saved_session_file()
        if saved_file:
            try:
                saved_path = Path(saved_file).resolve()
                cur_sid = str(session_id or self.last_state.get("sessionId") or "").strip()
                if not cur_sid or saved_path.stem == cur_sid:
                    return saved_path
            except Exception:
                pass
        sid = str(session_id or self.last_state.get("sessionId") or "").strip()
        if not sid:
            return None
        safe_sid = re.sub(r"[^A-Za-z0-9._-]+", "-", sid).strip("-") or "default-session"
        return (self.session_dir / f"{safe_sid}.jsonl").resolve()

    @staticmethod
    def _load_messages_from_jsonl(jsonl_path: Optional[Path]) -> list[dict[str, Any]]:
        if not jsonl_path or not jsonl_path.is_file():
            return []
        loaded: list[dict[str, Any]] = []
        try:
            with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
                    role = str(msg.get("role") or "")
                    if role in ("user", "assistant"):
                        loaded.append(dict(msg))
        except Exception:
            pass
        return loaded

    def _append_message_to_session_jsonl(self, msg: dict[str, Any]) -> None:
        if not isinstance(msg, dict):
            return
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            return
        with self.lock:
            # Coalesce consecutive assistant messages or duplicate entries in _session_messages
            msg_struct = extract_message_structured(msg)
            if role == "assistant" and not msg_struct["text"] and not msg_struct["thinking"] and not msg_struct["tools"] and not msg.get("errorMessage"):
                return
            if self._session_messages:
                last_struct = extract_message_structured(self._session_messages[-1])
                if (
                    last_struct["role"] == msg_struct["role"]
                    and last_struct["text"] == msg_struct["text"]
                    and last_struct["thinking"] == msg_struct["thinking"]
                    and len(last_struct["tools"]) == len(msg_struct["tools"])
                ):
                    self._session_messages[-1] = dict(msg)
                elif role == "assistant" and last_struct["role"] == "assistant":
                    # Merge consecutive assistant sub-turns (e.g. tool call + final text) into one card
                    merged_tools = list(last_struct["tools"])
                    existing_ids = {t.get("id") for t in merged_tools if t.get("id") and "result" in t}
                    for t in msg_struct["tools"]:
                        if t.get("id") and "result" in t and t.get("id") in existing_ids:
                            continue
                        merged_tools.append(t)
                    merged_thinking = "\n".join(x for x in (last_struct["thinking"], msg_struct["thinking"]) if x).strip()
                    merged_text = msg_struct["text"] if msg_struct["text"] == last_struct["text"] else "\n\n".join(x for x in (last_struct["text"], msg_struct["text"]) if x).strip()
                    blocks: list[dict[str, Any]] = []
                    if merged_thinking:
                        blocks.append({"type": "thinking", "thinking": merged_thinking})
                    for t in merged_tools:
                        if "result" in t:
                            blocks.append({
                                "type": "toolResult",
                                "toolCallId": t.get("id", ""),
                                "toolName": t.get("name", "tool"),
                                "content": t.get("result", ""),
                                "isError": bool(t.get("isError")),
                            })
                        else:
                            blocks.append({
                                "type": "toolCall",
                                "id": t.get("id", ""),
                                "name": t.get("name", "tool"),
                                "arguments": t.get("arguments") or {},
                            })
                    if merged_text:
                        blocks.append({"type": "text", "text": merged_text})
                    merged_msg = dict(self._session_messages[-1])
                    merged_msg["content"] = blocks if (merged_thinking or merged_tools) else merged_text
                    if isinstance(msg.get("usage"), dict):
                        merged_msg["usage"] = msg["usage"]
                    if msg.get("errorMessage"):
                        merged_msg["errorMessage"] = msg["errorMessage"]
                    self._session_messages[-1] = merged_msg
                    msg = merged_msg
                else:
                    self._session_messages.append(dict(msg))
            else:
                self._session_messages.append(dict(msg))

            sid = str(self.last_state.get("sessionId") or "").strip()
            safe_sid = re.sub(r"[^A-Za-z0-9._-]+", "-", sid).strip("-") if sid else ""
            jsonl_path = (self.session_dir / f"{safe_sid}.jsonl").resolve() if safe_sid else self._resolve_session_jsonl_path()
            if not jsonl_path:
                return
            # Never append custom lines into a native Pi CLI sessionFile (even before Pi CLI creates it on disk)
            native_sf = str(self.last_state.get("sessionFile") or "").strip()
            if native_sf:
                try:
                    if Path(native_sf).expanduser().resolve() == jsonl_path:
                        return
                except Exception:
                    pass
            if jsonl_path.is_file():
                try:
                    with jsonl_path.open("r", encoding="utf-8", errors="ignore") as rfh:
                        first_line = rfh.readline().strip()
                    if "\"type\":\"session\"" in first_line.replace(" ", "") and "version" in first_line and not first_line.endswith("\"lantern\":true}"):
                        # Native Pi CLI session file: do not write custom lines
                        if "_" in jsonl_path.stem:
                            return
                except Exception:
                    pass
            try:
                self.session_dir.mkdir(parents=True, exist_ok=True)
                existing = self._load_messages_from_jsonl(jsonl_path)
                if existing:
                    last_disk = extract_message_structured(existing[-1])
                    if (
                        last_disk["role"] == msg_struct["role"]
                        and last_disk["text"] == msg_struct["text"]
                        and last_disk["thinking"] == msg_struct["thinking"]
                    ):
                        return
                sid = str(self.last_state.get("sessionId") or jsonl_path.stem)
                need_header = not jsonl_path.is_file() or jsonl_path.stat().st_size == 0
                entry_id = uuid4().hex[:8]
                record = {
                    "type": "message",
                    "id": entry_id,
                    "parentId": None,
                    "sessionId": sid,
                    "timestamp": int(time.time() * 1000),
                    "role": role,
                    "content": msg.get("content", msg.get("text", "")),
                    "message": msg,
                }
                with jsonl_path.open("a", encoding="utf-8") as fh:
                    if need_header:
                        header = {
                            "type": "session",
                            "version": 3,
                            "id": sid,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "cwd": str(self.root),
                            "lantern": True,
                        }
                        fh.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
                    fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            except Exception:
                pass

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
        for env_key in ("LANTERN_PI_COMMAND", "PI_CLI_PATH"):
            explicit = os.environ.get(env_key, "").strip()
            if explicit:
                return explicit
        if os.name == "nt":
            found = shutil.which("pi.cmd") or shutil.which("pi.exe") or shutil.which("pi")
            if found:
                return found
            win_dirs = [
                Path(os.environ.get("APPDATA", "")) / "npm",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Volta" / "bin",
                Path(os.environ.get("NVM_SYMLINK", "")),
                Path(os.environ.get("PNPM_HOME", "")),
                Path(os.environ.get("LOCALAPPDATA", "")) / "pnpm",
                Path.home() / "AppData" / "Roaming" / "npm",
                Path.home() / ".volta" / "bin",
                Path.home() / ".bun" / "bin",
            ]
            for d in win_dirs:
                if not str(d) or not d.is_dir():
                    continue
                for name in ("pi.cmd", "pi.exe", "pi.bat", "pi"):
                    cand = d / name
                    if cand.is_file():
                        return str(cand)
            return "pi.cmd"
        found_posix = shutil.which("pi")
        if found_posix:
            return found_posix
        for cand in (
            Path.home() / ".local" / "bin" / "pi",
            Path.home() / ".volta" / "bin" / "pi",
            Path("/usr/local/bin/pi"),
        ):
            if cand.is_file():
                return str(cand)
        return "pi"

    @staticmethod
    def _resolve_node_for_win_shim(shim_path: Path) -> Optional[list[str]]:
        """Unwrap Windows .cmd/.bat shims into [node_exe, cli_js] so multi-line
        system prompts and special characters never pass through cmd.exe."""
        shim_dir = shim_path.resolve().parent
        node = shutil.which("node.exe") or shutil.which("node")
        if not node:
            for nd in (
                shim_dir / "node.exe",
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Volta" / "bin" / "node.exe",
                Path(os.environ.get("NVM_SYMLINK", "")) / "node.exe",
            ):
                if str(nd) and nd.is_file():
                    node = str(nd)
                    break
        if not node:
            return None

        cli_candidates = [
            shim_dir / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js",
            shim_dir / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js",
            shim_dir / "node_modules" / "@mariozechner" / "pi-coding-agent" / "dist" / "cli.js",
            shim_dir / "node_modules" / "@mariozechner" / "pi-coding-agent" / "dist" / "bundle" / "cli.js",
        ]
        for cli in cli_candidates:
            if cli.is_file():
                return [node, str(cli)]

        try:
            if shim_path.is_file():
                raw = shim_path.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r'(?:%~dp0|%dp0%)\\?([^\r\n"\']*?node_modules[^\r\n"\']*?\.js)', raw, re.IGNORECASE):
                    rel_js = m.group(1).lstrip("\\/")
                    cand_js = (shim_dir / rel_js).resolve()
                    if cand_js.is_file():
                        return [node, str(cand_js)]
        except Exception:
            pass
        return None

    def _command(self) -> list[str]:
        if self.argv_override:
            return list(self.argv_override)
        pi = self._resolve_pi()
        prefix = [pi]
        if os.name == "nt" and Path(pi).suffix.lower() in {".cmd", ".bat"}:
            unwrapped = self._resolve_node_for_win_shim(Path(pi))
            if unwrapped:
                prefix = unwrapped
        if not self.guard_extension.is_file():
            raise RuntimeError("Lanbot working-copy guard extension is missing")
        local = self.bot_config.local_access
        use_cmd_wrapper = (
            os.name == "nt"
            and len(prefix) == 1
            and Path(pi).suffix.lower() in {".cmd", ".bat"}
        )
        # If cmd.exe /C must be used as a fallback on Windows, collapse literal newlines in
        # the system prompt so cmd.exe does not truncate the command at the first newline.
        sys_prompt = (
            " ".join(line.strip() for line in self.bot_config.system_prompt.splitlines() if line.strip())
            if use_cmd_wrapper
            else self.bot_config.system_prompt
        )
        args = list(prefix) + ["--mode", "rpc"]
        if "--session-dir" not in self.unsupported_cli_flags:
            args.extend(["--session-dir", str(self.session_dir)])
        if "--name" not in self.unsupported_cli_flags:
            args.extend(["--name", "LanternBot"])
        if "--append-system-prompt" not in self.unsupported_cli_flags:
            args.extend(["--append-system-prompt", sys_prompt])
        # Step 1 (v7): On localhost, when running in Full / YOLO mode ("*"), do NOT inject
        # restrictive --tools, --no-extensions, or --no-mcp flags unless explicitly specified in YAML.
        if not local.is_full_tools and "--tools" not in self.unsupported_cli_flags:
            args.extend(["--tools", ",".join(local.tools)])
        if not local.extensions and "--no-extensions" not in self.unsupported_cli_flags:
            args.append("--no-extensions")
        if "--extension" not in self.unsupported_cli_flags:
            args.extend(["--extension", str(self.guard_extension)])
        if not local.mcp and "--no-mcp" not in self.unsupported_cli_flags:
            args.append("--no-mcp")
        session_file = self._saved_session_file()
        if session_file and "--session" not in self.unsupported_cli_flags:
            args.extend(["--session", session_file])
        if use_cmd_wrapper:
            comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
            return [comspec, "/D", "/C", subprocess.list2cmdline(args)]
        return args

    _PROBED_FLAG_CACHE: dict[tuple[str, ...], set[str]] = {}

    def _probe_cli_flags_if_needed(self) -> None:
        if self._cli_probed or self.argv_override:
            return
        self._cli_probed = True
        try:
            pi = self._resolve_pi()
            prefix = [pi]
            if os.name == "nt":
                cand_path = Path(pi)
                if cand_path.suffix.lower() in {".cmd", ".bat"}:
                    unwrapped = self._resolve_node_for_win_shim(cand_path)
                    if unwrapped:
                        prefix = unwrapped
                else:
                    found_cmd = shutil.which("pi.cmd") or shutil.which("pi")
                    if found_cmd and Path(found_cmd).suffix.lower() in {".cmd", ".bat"}:
                        unwrapped = self._resolve_node_for_win_shim(Path(found_cmd))
                        if unwrapped:
                            prefix = unwrapped

            # Fast static inspection of cli.js if unwrapped node was found
            if len(prefix) >= 2 and prefix[1].endswith(".js"):
                try:
                    js_code = Path(prefix[1]).read_text(encoding="utf-8", errors="ignore")
                    if "--no-mcp" not in js_code and "no-mcp" not in js_code:
                        self.unsupported_cli_flags.add("--no-mcp")
                except Exception:
                    pass

            cache_key = tuple(prefix)
            if cache_key in self._PROBED_FLAG_CACHE:
                self.unsupported_cli_flags.update(self._PROBED_FLAG_CACHE[cache_key])
                return

            probe_cmd = list(prefix) + ["--help"]
            if os.name == "nt" and len(prefix) == 1:
                comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
                probe_cmd = [comspec, "/D", "/C", subprocess.list2cmdline(probe_cmd)]
            startupinfo = None
            if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
                startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            res = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8.0,
                startupinfo=startupinfo,
            )
            help_out = (res.stdout or "") + "\n" + (res.stderr or "")
            unsupported: set[str] = set()
            if "--mode" in help_out or "Usage:" in help_out or "Options:" in help_out:
                for opt in ("--no-mcp", "--no-extensions", "--name", "--extension", "--append-system-prompt", "--tools", "--session-dir", "--session"):
                    if opt not in help_out:
                        unsupported.add(opt)
            self._PROBED_FLAG_CACHE[cache_key] = unsupported
            self.unsupported_cli_flags.update(unsupported)
        except Exception:
            pass

    def ensure_started(self) -> None:
        with self.lock:
            if self.closed:
                raise RuntimeError("Lanbot manager is closed")
            if self.proc is not None and self.proc.poll() is None:
                return
            self._probe_cli_flags_if_needed()
            self.session_dir.mkdir(parents=True, exist_ok=True)
            try:
                for sf in list(self.session_dir.glob("*.jsonl")):
                    if not self._repair_pi_session_file(sf):
                        # Only quarantine if the file is not valid JSON message records either
                        loaded_check = self._load_messages_from_jsonl(sf)
                        if not loaded_check:
                            try:
                                sf.replace(sf.with_suffix(f".corrupted-{int(time.time())}.bak"))
                            except Exception:
                                pass
            except Exception:
                pass
            # On Windows, use STARTUPINFO(SW_HIDE) instead of CREATE_NO_WINDOW so child
            # processes keep a valid hidden console station; this prevents MSYS2/Git Bash
            # fork() from failing with exit code 0xC0000142 (STATUS_DLL_INIT_FAILED).
            startupinfo = None
            if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
                startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            child_env = dict(os.environ)
            child_env["LANTERN_PI_GUARD_STATE"] = str(self.work_store.guard_path)

            max_attempts = 4
            for attempt in range(max_attempts):
                cmd = self._command()
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.root),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    startupinfo=startupinfo,
                    env=child_env,
                )
                early_code = None
                for _ in range(8):
                    early_code = proc.poll()
                    if early_code is not None:
                        break
                    time.sleep(0.04)
                if early_code is not None and early_code != 0:
                    err_lines = []
                    try:
                        if proc.stderr:
                            err_lines = [l.strip() for l in proc.stderr.readlines() if l.strip()]
                    except Exception:
                        pass
                    err_text = " ".join(err_lines)
                    unknown_flags = set(re.findall(r"Unknown option:\s*(--[A-Za-z0-9_-]+)", err_text, re.IGNORECASE))
                    if ("--no-mcp" in err_text or "Unknown option:" in err_text) and not unknown_flags:
                        unknown_flags.add("--no-mcp")
                    if unknown_flags and attempt < max_attempts - 1:
                        for uf in unknown_flags:
                            self.unsupported_cli_flags.add(uf)
                        continue
                    if "not a valid pi session" in err_text.lower() or "session file is not" in err_text.lower():
                        bad_m = re.search(r"not a valid pi session:\s*([^\r\n|]+)", err_text, re.IGNORECASE)
                        bad_target = bad_m.group(1).strip() if bad_m else self._saved_session_file()
                        if bad_target:
                            try:
                                bp = Path(bad_target)
                                if bp.is_file():
                                    if not self._repair_pi_session_file(bp):
                                        bp.rename(bp.with_suffix(f".corrupted-{int(time.time())}.bak"))
                            except Exception:
                                pass
                        self._clear_session_file()
                        if attempt < max_attempts - 1:
                            continue
                self.proc = proc
                self.reader = threading.Thread(target=self._reader_loop, name="lanternbot-rpc", daemon=True)
                self.stderr_reader = threading.Thread(target=self._stderr_loop, name="lanternbot-stderr", daemon=True)
                self.reader.start()
                self.stderr_reader.start()
                break

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

    @staticmethod
    def _extract_stream_deltas(event: dict[str, Any]) -> tuple[str, str]:
        """Return (text_delta, thinking_delta) from a Pi RPC stream event."""
        text_delta = ""
        thinking_delta = ""
        ev_type = str(event.get("type") or "")
        if ev_type in ("message_update", "assistant_delta") and isinstance(event.get("delta"), str):
            text_delta = event["delta"]
        elif ev_type == "thinking_delta" and isinstance(event.get("delta"), str):
            thinking_delta = event["delta"]
        inner = event.get("assistantMessageEvent") or event.get("event")
        if isinstance(inner, dict):
            itype = str(inner.get("type") or "")
            if itype == "text_delta":
                text_delta = str(inner.get("delta") or inner.get("text") or text_delta)
            elif itype in ("thinking_delta", "reasoning_delta"):
                thinking_delta = str(inner.get("delta") or inner.get("thinking") or inner.get("text") or thinking_delta)
        return text_delta, thinking_delta

    def _build_turn_assistant_message(self, raw_msg: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        base = dict(raw_msg) if isinstance(raw_msg, dict) else {}
        parsed = extract_message_structured(base) if base else {"text": "", "thinking": "", "tools": []}
        sub_txt = "".join(getattr(self, "_subturn_stream_text", [])).strip()
        sub_thk = "".join(getattr(self, "_subturn_stream_thinking", [])).strip()
        text_parts = list(self._turn_stream_text)
        if sub_txt and (not text_parts or text_parts[-1] != sub_txt):
            text_parts.append(sub_txt)
        if parsed.get("text") and (not text_parts or text_parts[-1] != parsed["text"].strip()):
            text_parts.append(parsed["text"].strip())
        think_parts = list(self._turn_stream_thinking)
        if sub_thk and (not think_parts or think_parts[-1] != sub_thk):
            think_parts.append(sub_thk)
        if parsed.get("thinking") and (not think_parts or think_parts[-1] != parsed["thinking"].strip()):
            think_parts.append(parsed["thinking"].strip())
        combined_text = "\n\n".join(p for p in text_parts if p)
        combined_thinking = "\n\n".join(p for p in think_parts if p)
        combined_tools = list(self._turn_stream_tools) if self._turn_stream_tools else (parsed.get("tools") or [])
        if not combined_text and not combined_thinking and not combined_tools and not base.get("errorMessage"):
            return None

        content_blocks: list[dict[str, Any]] = []
        if combined_thinking:
            content_blocks.append({"type": "thinking", "thinking": combined_thinking})
        for t in combined_tools:
            if "result" in t:
                content_blocks.append({
                    "type": "toolResult",
                    "toolCallId": t.get("id", ""),
                    "toolName": t.get("name", "tool"),
                    "content": t.get("result", ""),
                    "isError": bool(t.get("isError")),
                })
            else:
                content_blocks.append({
                    "type": "toolCall",
                    "id": t.get("id", ""),
                    "name": t.get("name", "tool"),
                    "arguments": t.get("arguments") or {},
                })
        if combined_text:
            content_blocks.append({"type": "text", "text": combined_text})

        result_msg: dict[str, Any] = {
            "role": "assistant",
            "content": content_blocks if (combined_thinking or combined_tools) else combined_text,
            "timestamp": base.get("timestamp") or int(time.time() * 1000),
        }
        if isinstance(base.get("usage"), dict):
            result_msg["usage"] = base["usage"]
        if base.get("errorMessage"):
            result_msg["errorMessage"] = base["errorMessage"]
        return result_msg

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
                if typ == "agent_start":
                    self.streaming = True
                    self._turn_had_tool_call = False
                    self._last_stop_reason = ""
                    self._turn_stream_text.clear()
                    self._turn_stream_thinking.clear()
                    self._subturn_stream_text.clear()
                    self._subturn_stream_thinking.clear()
                    self._turn_stream_tools.clear()
                    self._turn_assistant_saved = False
                elif typ == "turn_start":
                    self.streaming = True
                    self._turn_had_tool_call = False
                    self._last_stop_reason = ""
                    self._subturn_stream_text.clear()
                    self._subturn_stream_thinking.clear()
                    # Re-assert active turn scope so multi-turn tool execution (read -> edit -> write)
                    # never loses its localhost/full tool permissions!
                    with self.turn_lock:
                        self._turn_in_progress = True
                        setter = getattr(self.work_store, "set_runtime_scope", None)
                        if callable(setter):
                            try:
                                active_sc = self._active_turn_scope or "local"
                                setter(active_sc, self.bot_config.access_policy(active_sc).tools)
                            except Exception:
                                pass
                elif typ in ("message_update", "assistant_delta", "thinking_delta"):
                    self.streaming = True
                    txt_d, think_d = self._extract_stream_deltas(event)
                    if txt_d:
                        self._subturn_stream_text.append(txt_d)
                    if think_d:
                        self._subturn_stream_thinking.append(think_d)
                elif typ == "tool_execution_start":
                    self.streaming = True
                    self._turn_had_tool_call = True
                    tc_id = str(event.get("toolCallId") or event.get("id") or "")
                    existing_call_ids = {t.get("id") for t in self._turn_stream_tools if "result" not in t and t.get("id")}
                    if not tc_id or tc_id not in existing_call_ids:
                        self._turn_stream_tools.append({
                            "id": tc_id,
                            "name": str(event.get("toolName") or event.get("name") or "tool"),
                            "arguments": event.get("args") or event.get("arguments") or {},
                        })
                elif typ == "tool_execution_end":
                    self._turn_had_tool_call = True
                    self._turn_stream_tools.append({
                        "id": str(event.get("toolCallId") or event.get("id") or ""),
                        "name": str(event.get("toolName") or event.get("name") or "result"),
                        "result": str(event.get("result") or ""),
                        "isError": bool(event.get("isError") or event.get("error")),
                    })
                    self._emit_work_update(final=False)
                elif typ == "message_end":
                    self._record_event_usage(event)
                    raw_msg = event.get("message") if isinstance(event.get("message"), dict) else None
                    role = str((raw_msg or {}).get("role") or "assistant")
                    if role == "assistant":
                        stop_reason = str((raw_msg or {}).get("stopReason") or "").lower()
                        self._last_stop_reason = stop_reason
                        parsed_m = extract_message_structured(raw_msg) if raw_msg else {"text": "", "thinking": "", "tools": []}
                        sub_txt = (parsed_m.get("text") or "".join(self._subturn_stream_text)).strip()
                        sub_thk = (parsed_m.get("thinking") or "".join(self._subturn_stream_thinking)).strip()
                        self._subturn_stream_text.clear()
                        self._subturn_stream_thinking.clear()
                        if sub_thk and (not self._turn_stream_thinking or self._turn_stream_thinking[-1] != sub_thk):
                            self._turn_stream_thinking.append(sub_thk)
                        if sub_txt and (not self._turn_stream_text or self._turn_stream_text[-1] != sub_txt):
                            self._turn_stream_text.append(sub_txt)
                        if parsed_m.get("tools"):
                            self._turn_had_tool_call = True
                            existing_call_ids = {t.get("id") for t in self._turn_stream_tools if "result" not in t and t.get("id")}
                            for t in parsed_m["tools"]:
                                tid = t.get("id")
                                if "result" in t or not tid or tid not in existing_call_ids:
                                    self._turn_stream_tools.append(t)
                                    if tid and "result" not in t:
                                        existing_call_ids.add(tid)
                        is_tool_subturn = stop_reason in ("tooluse", "tool_use") or (bool(parsed_m.get("tools")) and not parsed_m.get("text"))
                        if not is_tool_subturn:
                            built = self._build_turn_assistant_message(raw_msg)
                            if built is not None:
                                self._append_message_to_session_jsonl(built)
                                self._turn_assistant_saved = True
                                event = dict(event)
                                event["message"] = built
                            if stop_reason in ("stop", "end_turn", "length", "error", "aborted"):
                                self.streaming = False
                elif typ == "turn_end":
                    # If this turn executed tools or had stopReason=toolUse, Pi CLI is immediately
                    # starting the next sub-turn (e.g. edit after read). Keep turn scope & lock alive!
                    if self._turn_had_tool_call or self._last_stop_reason in ("tooluse", "tool_use"):
                        self._emit_work_update(final=False)
                        self._turn_had_tool_call = False
                    else:
                        self.streaming = False
                        if not self._turn_assistant_saved:
                            built = self._build_turn_assistant_message(None)
                            if built is not None:
                                self._append_message_to_session_jsonl(built)
                                self._turn_assistant_saved = True
                        self._turn_stream_text.clear()
                        self._turn_stream_thinking.clear()
                        self._turn_stream_tools.clear()
                        self._emit_work_update(final=True)
                        self._reset_tool_scope()
                        self._schedule_next_steer()
                elif typ in ("agent_settled", "agent_end"):
                    self.streaming = False
                    self._turn_had_tool_call = False
                    self._last_stop_reason = ""
                    if not self._turn_assistant_saved:
                        built = self._build_turn_assistant_message(None)
                        if built is not None:
                            self._append_message_to_session_jsonl(built)
                            self._turn_assistant_saved = True
                    self._turn_stream_text.clear()
                    self._turn_stream_thinking.clear()
                    self._turn_stream_tools.clear()
                    self._emit_work_update(final=True)
                    self._reset_tool_scope()
                    self._schedule_next_steer()
                self.emit({"type": "chat_bot_event", "event": event})
        finally:
            self._emit_work_update(final=True)
            self._reset_tool_scope()
            code = proc.poll()
            if code is None:
                try:
                    code = proc.wait(timeout=0.5)
                except Exception:
                    code = None
            stderr_lines = list(self.stderr_tail)
            stderr_hint = " | ".join(stderr_lines[-3:]) if stderr_lines else ""
            newly_unsupported: set[str] = set()
            is_bad_session = False
            for sline in stderr_lines:
                if "not a valid pi session" in sline.lower() or "session file is not" in sline.lower():
                    is_bad_session = True
                for m in re.finditer(r"Unknown option:\s*(--[A-Za-z0-9_-]+)", sline, re.IGNORECASE):
                    flag = m.group(1)
                    if flag not in self.unsupported_cli_flags:
                        self.unsupported_cli_flags.add(flag)
                        newly_unsupported.add(flag)
            if is_bad_session:
                bad_m = re.search(r"not a valid pi session:\s*([^\r\n|]+)", stderr_hint, re.IGNORECASE)
                bad_target = bad_m.group(1).strip() if bad_m else self._saved_session_file()
                if bad_target:
                    try:
                        bp = Path(bad_target)
                        if bp.is_file() and not self._repair_pi_session_file(bp):
                            bp.rename(bp.with_suffix(f".corrupted-{int(time.time())}.bak"))
                    except Exception:
                        pass
                self._clear_session_file()
            msg_suffix = f": {stderr_hint}" if stderr_hint else ""
            error = RuntimeError(f"Lanbot runtime exited ({code}){msg_suffix}")
            if newly_unsupported:
                setattr(error, "_retry_without_flags", True)
            with self.lock:
                waiting = list(self.pending.values())
                self.pending.clear()
                if self.proc is proc:
                    self.proc = None
            for item in waiting:
                item.error = error
                item.event.set()
            self.streaming = False
            if newly_unsupported or is_bad_session:
                threading.Thread(target=self.ensure_started, daemon=True).start()
            else:
                self.emit({"type": "chat_process_exit", "exitCode": code, "stderr": stderr_hint})

    def send_fire_and_forget(self, payload: dict[str, Any]) -> bool:
        """Send a payload to Pi stdin that does not expect a response frame
        (e.g. extension_ui_response). Prevents RPC timeout crashes (Issue 15)."""
        self.ensure_started()
        with self.lock:
            proc = self.proc
        if not proc or not proc.stdin:
            return False
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self.write_lock:
                proc.stdin.write(raw)
                proc.stdin.flush()
            return True
        except Exception:
            return False

    def respond_extension_ui(self, request_id: str, value: Any) -> dict[str, Any]:
        ok = self.send_fire_and_forget({
            "type": "extension_ui_response",
            "id": str(request_id or ""),
            "value": value,
        })
        return {"ok": ok, "requestId": str(request_id or "")}

    def request(self, command: dict[str, Any], *, timeout: Optional[float] = None) -> dict[str, Any]:
        # Never block waiting for a response on extension_ui_response
        if command.get("type") == "extension_ui_response":
            self.send_fire_and_forget(command)
            return {"type": "response", "success": True}

        self.ensure_started()
        payload = {k: v for k, v in command.items() if k != "_retried_flags"}
        req_id = str(payload.get("id") or uuid4().hex)
        payload["id"] = req_id
        pending = _Pending(threading.Event())
        with self.lock:
            self.pending[req_id] = pending
            proc = self.proc
        if not proc or not proc.stdin:
            with self.lock:
                self.pending.pop(req_id, None)
            raise RuntimeError("LanternBot runtime stdin unavailable")
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
            raise TimeoutError(f"LanternBot runtime request timed out: {payload.get('type')}")
        if pending.error:
            if getattr(pending.error, "_retry_without_flags", False) and not command.get("_retried_flags"):
                self.stderr_tail.clear()
                retry_cmd = dict(command)
                retry_cmd["_retried_flags"] = True
                return self.request(retry_cmd, timeout=timeout)
            raise pending.error
        response = pending.response or {}
        if response.get("success") is False:
            raise RuntimeError(str(response.get("error") or f"LanternBot runtime failed: {payload.get('type')}"))
        return response

    def _record_event_usage(self, event: dict[str, Any]) -> None:
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        raw = usage.get("totalTokens", usage.get("total_tokens"))
        if raw in (None, ""):
            return
        try:
            tokens = int(raw)
        except (TypeError, ValueError):
            return
        if tokens > 0:
            self.usage.record_tokens(tokens)

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
                    "workHash": current_hash,
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
            final_hash = result.get("hash")
            self.emit({
                "type": "chat_work_changed",
                "path": rel,
                "hash": final_hash,
                "workHash": final_hash,
                "final": True,
            })
            if result.get("realTouched") and not getattr(self.work_store, "live", False):
                self.emit({
                    "type": "chat_real_file_touched",
                    "path": rel,
                    "error": "Saved project file changed while LanternBot was editing the working copy.",
                })

    def get_state(self) -> dict[str, Any]:
        response = self.request({"type": "get_state"})
        data = dict(response.get("data")) if isinstance(response.get("data"), dict) else {}
        if self._switched_session_override:
            data["sessionId"] = self._switched_session_override["sessionId"]
            data["sessionFile"] = self._switched_session_override["sessionFile"]
        prev_sid = str(self.last_state.get("sessionId") or "")
        new_sid = str(data.get("sessionId") or "")
        self.last_state = dict(data)
        if new_sid and new_sid != prev_sid and not self._session_messages:
            jsonl_path = self._resolve_session_jsonl_path(
                session_id=new_sid,
                session_file=str(data.get("sessionFile") or ""),
            )
            loaded = self._load_messages_from_jsonl(jsonl_path)
            if loaded:
                self._session_messages = loaded
        self._persist_state(data)
        return data

    @staticmethod
    @staticmethod
    def _coalesce_transcript_list(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Coalesce consecutive assistant / toolResult sub-turns into a single unified assistant
        message per user prompt and drop empty assistant placeholders."""
        out: list[dict[str, Any]] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "assistant")
            struct = extract_message_structured(item)
            if role in ("toolResult", "tool"):
                tool_entry = {
                    "id": str(item.get("toolCallId") or item.get("toolUseId") or ""),
                    "name": str(item.get("toolName") or item.get("name") or "result"),
                    "result": struct["text"],
                    "isError": bool(item.get("isError")),
                }
                if out and str(out[-1].get("role") or "") == "assistant":
                    prev_s = extract_message_structured(out[-1])
                    prev_tools = list(prev_s["tools"])
                    prev_tools.append(tool_entry)
                    blocks: list[dict[str, Any]] = []
                    if prev_s["thinking"]:
                        blocks.append({"type": "thinking", "thinking": prev_s["thinking"]})
                    for t in prev_tools:
                        if "result" in t:
                            blocks.append({
                                "type": "toolResult",
                                "toolCallId": t.get("id", ""),
                                "toolName": t.get("name", "tool"),
                                "content": t.get("result", ""),
                                "isError": bool(t.get("isError")),
                            })
                        else:
                            blocks.append({
                                "type": "toolCall",
                                "id": t.get("id", ""),
                                "name": t.get("name", "tool"),
                                "arguments": t.get("arguments") or {},
                            })
                    if prev_s["text"]:
                        blocks.append({"type": "text", "text": prev_s["text"]})
                    updated = dict(out[-1])
                    updated["content"] = blocks
                    out[-1] = updated
                continue
            if role == "assistant":
                if not struct["text"] and not struct["thinking"] and not struct["tools"] and not item.get("errorMessage"):
                    continue
                if out and str(out[-1].get("role") or "") == "assistant":
                    prev_s = extract_message_structured(out[-1])
                    merged_tools = list(prev_s["tools"]) + list(struct["tools"])
                    merged_thinking = "\n".join(x for x in (prev_s["thinking"], struct["thinking"]) if x).strip()
                    merged_text = struct["text"] if struct["text"] == prev_s["text"] else "\n\n".join(x for x in (prev_s["text"], struct["text"]) if x).strip()
                    blocks = []
                    if merged_thinking:
                        blocks.append({"type": "thinking", "thinking": merged_thinking})
                    for t in merged_tools:
                        if "result" in t:
                            blocks.append({
                                "type": "toolResult",
                                "toolCallId": t.get("id", ""),
                                "toolName": t.get("name", "tool"),
                                "content": t.get("result", ""),
                                "isError": bool(t.get("isError")),
                            })
                        else:
                            blocks.append({
                                "type": "toolCall",
                                "id": t.get("id", ""),
                                "name": t.get("name", "tool"),
                                "arguments": t.get("arguments") or {},
                            })
                    if merged_text:
                        blocks.append({"type": "text", "text": merged_text})
                    updated = dict(out[-1])
                    updated["content"] = blocks if (merged_thinking or merged_tools) else merged_text
                    if isinstance(item.get("usage"), dict):
                        updated["usage"] = item["usage"]
                    out[-1] = updated
                    continue
            out.append(dict(item))
        return out

    @classmethod
    def _reconcile_transcript(
        cls,
        rpc_msgs: list[dict[str, Any]],
        local_msgs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        c_rpc = cls._coalesce_transcript_list(rpc_msgs)
        c_local = cls._coalesce_transcript_list(local_msgs)
        if not c_local:
            return c_rpc
        if not c_rpc:
            return c_local
        rpc_assistant_count = sum(1 for m in c_rpc if str(m.get("role") or "") == "assistant")
        local_assistant_count = sum(1 for m in c_local if str(m.get("role") or "") == "assistant")
        if local_assistant_count > rpc_assistant_count or len(c_local) > len(c_rpc):
            return c_local
        return c_rpc

    def get_messages(self) -> list[dict[str, Any]]:
        rpc_msgs: list[dict[str, Any]] = []
        try:
            response = self.request({"type": "get_messages"})
            data = response.get("data")
            if isinstance(data, list):
                rpc_msgs = [item for item in data if isinstance(item, dict)]
            elif isinstance(data, dict) and isinstance(data.get("messages"), list):
                rpc_msgs = [item for item in data["messages"] if isinstance(item, dict)]
        except Exception:
            rpc_msgs = []

        with self.lock:
            if not self._session_messages:
                jsonl_path = self._resolve_session_jsonl_path()
                disk_msgs = self._load_messages_from_jsonl(jsonl_path)
                if disk_msgs:
                    self._session_messages = disk_msgs
            if self._switched_session_override:
                return self._coalesce_transcript_list(self._session_messages)
            merged = self._reconcile_transcript(rpc_msgs, self._session_messages)
            if len(merged) > len(self._session_messages):
                for m in merged[len(self._session_messages):]:
                    self._append_message_to_session_jsonl(m)
            return merged

    def available_models(self, scope: str = "local") -> list[dict[str, Any]]:
        response = self.request({"type": "get_available_models"})
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        raw = data.get("models") if isinstance(data.get("models"), list) else []
        selected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        policy = self.bot_config.access_policy(scope)
        prefs = self._load_prefs()
        fav_set = set(str(x) for x in (prefs.get("favorites") or []))

        for item in raw:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider") or "")
            model_id = str(item.get("id") or "")
            if not provider or not model_id:
                continue
            if not policy.allows_model(provider, model_id):
                continue
            key = (provider, model_id)
            if key in seen:
                continue
            seen.add(key)
            pub = self._model_public(item)
            if f"{provider}/{model_id}" in fav_set:
                pub["favorite"] = True
            selected.append(pub)
        return selected

    @staticmethod
    def _model_public(model: dict[str, Any]) -> dict[str, Any]:
        provider = str(model.get("provider") or "")
        model_id = str(model.get("id") or "")
        name = str(model.get("name") or model_id or "")
        return {
            "provider": provider,
            "id": model_id,
            "name": name,
            "fullLabel": f"{provider} / {name}" if provider else name,
            "reasoning": bool(model.get("reasoning")),
            "contextWindow": int(model.get("contextWindow") or 0),
        }

    def _configured_target(
        self,
        state: dict[str, Any],
        models: list[dict[str, Any]],
        policy,
    ) -> dict[str, Any] | None:
        provider = policy.provider
        model_id = policy.model
        if not provider and not model_id:
            # Check user's last-selected model preference if not locked by policy
            prefs = self._load_prefs()
            last_model = prefs.get("lastModel")
            if isinstance(last_model, dict):
                lp = str(last_model.get("provider") or "")
                lid = str(last_model.get("id") or "")
                if lp and lid and policy.allows_model(lp, lid):
                    matches = [m for m in models if m["provider"] == lp and m["id"] == lid]
                    if matches:
                        return matches[0]
            return None

        current = state.get("model") if isinstance(state.get("model"), dict) else {}
        current_provider = str(current.get("provider") or "")
        current_id = str(current.get("id") or "")
        if ((not provider or current_provider == provider)
                and (not model_id or current_id == model_id)
                and policy.allows_model(current_provider, current_id)):
            return self._model_public(current)

        matches = [
            item for item in models
            if (not provider or item["provider"] == provider)
            and (not model_id or item["id"] == model_id)
        ]
        if not matches:
            wanted = "/".join(part for part in (provider, model_id) if part) or "configured selection"
            raise RuntimeError(
                f"LanternBot configured provider/model is unavailable on this machine: {wanted}"
            )
        return matches[0]

    def bootstrap_state(self, scope: str = "local") -> dict[str, Any]:
        state = self.get_state()
        policy = self.bot_config.access_policy(scope)
        models = self.available_models(scope)
        current = state.get("model") if isinstance(state.get("model"), dict) else {}
        current_provider = str(current.get("provider") or "")
        current_id = str(current.get("id") or "")
        current_allowed = policy.allows_model(current_provider, current_id)

        should_apply_selection = (
            scope not in self.selection_initialized
            or policy.lock_provider
            or policy.lock_model
        )
        target = self._configured_target(state, models, policy) if should_apply_selection else None
        if target is None and not current_allowed:
            if not models:
                raise RuntimeError(
                    f"LanternBot {scope} policy allows no model available on this machine"
                )
            target = models[0]

        if target is not None and (
            current_provider != target["provider"] or current_id != target["id"]
        ):
            self.request({
                "type": "set_model",
                "provider": target["provider"],
                "modelId": target["id"],
            })
            state = self.get_state()
        self.selection_initialized.add(scope)
        return state

    def set_model(self, provider: str, model_id: str, scope: str = "local") -> dict[str, Any]:
        provider = str(provider or "").strip()
        model_id = str(model_id or "").strip()
        if not provider or not model_id:
            raise ValueError("provider and modelId are required")
        policy = self.bot_config.access_policy(scope)
        if policy.lock_provider and provider != policy.provider:
            raise PermissionError("LanternBot provider is locked for this access scope")
        if policy.lock_model and (provider != policy.provider or model_id != policy.model):
            raise PermissionError("LanternBot model is locked for this access scope")
        allowed = {
            (item["provider"], item["id"])
            for item in self.available_models(scope)
        }
        if (provider, model_id) not in allowed:
            raise PermissionError("LanternBot provider/model is not allowed by configuration")
        response = self.request({"type": "set_model", "provider": provider, "modelId": model_id})
        if scope == "local":
            self._save_prefs({"lastModel": {"provider": provider, "id": model_id}})
        self.last_state = {}
        self.get_state()
        self.selection_initialized.add(scope)
        return response

    def new_session(self, scope: str = "local", *, skip_if_empty: bool = False) -> dict[str, Any]:
        """Start a new Pi session and forcibly clear any stale turn lock."""
        if self.streaming or self._turn_in_progress:
            try:
                self.send_fire_and_forget({"type": "abort"})
            except Exception:
                pass
        self.streaming = False
        with self.turn_lock:
            self._turn_in_progress = False
            self.steer_queue.clear()
        self._emit_work_update(final=True)
        self._reset_tool_scope()
        if skip_if_empty and not self._session_messages:
            try:
                msgs = self.get_messages()
                if len(msgs) == 0:
                    state = self.bootstrap_state(scope)
                    state["alreadyNew"] = True
                    return state
            except Exception:
                pass
        with self.lock:
            self._switched_session_override = None
            self._session_messages.clear()
            self._turn_stream_text.clear()
            self._turn_stream_thinking.clear()
            self._turn_stream_tools.clear()
            self._turn_assistant_saved = False
        try:
            self.request({"type": "new_session"}, timeout=6.0)
        except Exception:
            pass
        self.selection_initialized.clear()
        state = self.bootstrap_state(scope)
        self.emit({"type": "chat_session_changed", "state": state})
        return state

    def fork_session(self, scope: str = "local") -> dict[str, Any]:
        """Fork the current session into a new branch."""
        self._emit_work_update(final=True)
        self._reset_tool_scope()
        prior_messages = list(self._session_messages) or self.get_messages()
        fork_sid = f"fork-{int(time.time())}-{uuid4().hex[:6]}"
        fork_path = self.session_dir / f"{fork_sid}.jsonl"
        try:
            self.request({"type": "fork_session"})
            self._switched_session_override = None
        except Exception:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            with fork_path.open("w", encoding="utf-8") as fh:
                header = {
                    "type": "session",
                    "version": 3,
                    "id": fork_sid,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "cwd": str(self.root),
                    "lantern": True,
                }
                fh.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
                for m in prior_messages:
                    rec = {
                        "type": "message",
                        "id": uuid4().hex[:8],
                        "parentId": None,
                        "sessionId": fork_sid,
                        "timestamp": int(time.time() * 1000),
                        "role": str(m.get("role") or "assistant"),
                        "content": m.get("content", m.get("text", "")),
                        "message": m,
                    }
                    fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            with self.lock:
                self._session_messages = list(prior_messages)
                self._switched_session_override = {
                    "sessionId": fork_sid,
                    "sessionFile": str(fork_path),
                }
                self._persist_state({
                    "sessionId": fork_sid,
                    "sessionFile": str(fork_path),
                    "model": self.last_state.get("model") or {},
                })
        state = self.bootstrap_state(scope)
        self.emit({"type": "chat_session_changed", "state": state})
        return state

    def switch_session(self, session_path: str, scope: str = "local") -> dict[str, Any]:
        """Switch to another saved session JSONL file inside session_dir."""
        self._emit_work_update(final=True)
        self._reset_tool_scope()
        raw = str(session_path or "").strip()
        if raw:
            cand = (self.session_dir / Path(raw).name).resolve()
            if not cand.is_file() and not raw.endswith(".jsonl"):
                cand = (self.session_dir / f"{Path(raw).name}.jsonl").resolve()
            if not cand.is_file():
                cand = Path(raw).expanduser().resolve()
            if not cand.is_file() and self.session_dir.is_dir():
                matches = sorted(self.session_dir.glob(f"*{Path(raw).stem}*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                if matches:
                    cand = matches[0].resolve()
            if cand.is_file() and cand.suffix.lower() == ".jsonl":
                target_sid = cand.stem
                try:
                    with cand.open("r", encoding="utf-8", errors="replace") as fh:
                        for idx, line in enumerate(fh):
                            if idx > 10:
                                break
                            obj = json.loads(line.strip())
                            if isinstance(obj, dict):
                                if obj.get("type") == "session" and obj.get("id"):
                                    target_sid = str(obj["id"])
                                    break
                                if obj.get("sessionId"):
                                    target_sid = str(obj["sessionId"])
                                    break
                except Exception:
                    pass
                loaded_msgs = self._load_messages_from_jsonl(cand)
                mirror_cand = (self.session_dir / f"{target_sid}.jsonl").resolve()
                if mirror_cand.is_file() and mirror_cand != cand:
                    mirror_msgs = self._load_messages_from_jsonl(mirror_cand)
                    if len(mirror_msgs) > len(loaded_msgs):
                        loaded_msgs = mirror_msgs
                with self.lock:
                    self._session_messages = loaded_msgs
                    self._switched_session_override = {
                        "sessionId": target_sid,
                        "sessionFile": str(cand),
                    }
                    self.last_state["sessionId"] = target_sid
                    self.last_state["sessionFile"] = str(cand)
                    self._persist_state({
                        "sessionId": target_sid,
                        "sessionFile": str(cand),
                        "model": self.last_state.get("model") or {},
                    })
                switched = False
                try:
                    res = self.request({"type": "switch_session", "sessionFile": str(cand)}, timeout=3.0)
                    switched = bool(res.get("success", True))
                except Exception:
                    switched = False
                if not switched and self.proc is not None and not self.streaming:
                    self._restart_process()
        state = self.bootstrap_state(scope)
        if self._switched_session_override:
            state["sessionId"] = self._switched_session_override["sessionId"]
            state["sessionFile"] = self._switched_session_override["sessionFile"]
        self.emit({"type": "chat_session_changed", "state": state})
        return state

    def compact_session(self, instructions: str = "") -> dict[str, Any]:
        """Compact the current session context to save tokens."""
        try:
            payload: dict[str, Any] = {"type": "compact"}
            if instructions.strip():
                payload["instructions"] = instructions.strip()
            return self.request(payload, timeout=30.0)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_session_html(self) -> str:
        """Export the complete current session transcript as a rich, unabbreviated HTML document (Issue 23)."""
        try:
            state = self.get_state()
        except Exception:
            state = dict(self.last_state)
        try:
            raw_messages = self.get_messages()
        except Exception:
            raw_messages = []

        session_id = str(state.get("sessionId") or "unknown")
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        model_label = f"{model.get('provider', '')} / {model.get('id', '')}".strip(" /") or "Default"

        cards_html: list[str] = []
        for idx, raw_msg in enumerate(raw_messages, 1):
            parsed = extract_message_structured(raw_msg)
            role = parsed["role"].upper()
            raw_text = parsed["text"]
            ctx_block = ""
            user_body = raw_text
            ctx_match = re.search(r"<lantern_context>\s*([\s\S]*?)\s*</lantern_context>", raw_text)
            req_match = re.search(r"<user_request>\s*([\s\S]*?)\s*</user_request>", raw_text)
            if ctx_match:
                ctx_block = ctx_match.group(1).strip()
            if req_match:
                user_body = req_match.group(1).strip()

            sections: list[str] = []
            if ctx_block:
                sections.append(
                    f'<details class="ctx-box"><summary>📍 Lantern Context Snapshot</summary>'
                    f'<pre>{html.escape(ctx_block)}</pre></details>'
                )
            if parsed["thinking"]:
                sections.append(
                    f'<details class="thinking-box" open><summary>💭 Thinking / Reasoning Trace</summary>'
                    f'<pre>{html.escape(parsed["thinking"])}</pre></details>'
                )
            if user_body:
                sections.append(f'<div class="msg-body"><pre>{html.escape(user_body)}</pre></div>')
            for t in parsed["tools"]:
                if "result" in t:
                    sections.append(
                        f'<details class="tool-box" open><summary>🛠 Tool Result: {html.escape(t.get("name", "tool"))} '
                        f'{"(ERROR)" if t.get("isError") else "(OK)"}</summary>'
                        f'<pre>{html.escape(str(t.get("result") or ""))}</pre></details>'
                    )
                else:
                    args_str = json.dumps(t.get("arguments") or {}, ensure_ascii=False, indent=2)
                    sections.append(
                        f'<details class="tool-box" open><summary>⚡ Tool Call: {html.escape(t.get("name", "tool"))}</summary>'
                        f'<pre>{html.escape(args_str)}</pre></details>'
                    )
            for sub in parsed["subagents"]:
                sections.append(
                    f'<div class="subagent-box"><strong>🤖 Subagent [{html.escape(sub["status"])}]: '
                    f'{html.escape(sub["summary"] or sub["taskId"])}</strong>'
                    f'<pre>{html.escape(sub["result"])}</pre>'
                    f'<div class="sub-meta">Task ID: {html.escape(sub["taskId"])} · '
                    f'Tokens: {sub["usage"]["totalTokens"]} · Duration: {sub["usage"]["durationMs"]}ms · '
                    f'Output: {html.escape(sub["outputFile"])}</div></div>'
                )
            usage_info = ""
            if parsed.get("usage"):
                usage_info = f'<div class="usage-meta">Usage: {html.escape(json.dumps(parsed["usage"]))}</div>'

            cards_html.append(
                f'<section class="turn-card role-{html.escape(parsed["role"])}">'
                f'<header><span class="turn-num">#{idx}</span> <strong>{html.escape(role)}</strong></header>'
                f'{"".join(sections)}{usage_info}</section>'
            )

        body_joined = "\n".join(cards_html) or '<p class="empty">No messages in this session.</p>'
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Lantern Chatbot Full Transcript — {html.escape(session_id)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 24px; background: #080b11; color: #edf5ff; font: 14px/1.55 system-ui, -apple-system, sans-serif; }}
  .container {{ max-width: 1120px; margin: 0 auto; }}
  .head {{ padding: 16px 20px; border: 1px solid #263447; border-radius: 14px; background: #101722; margin-bottom: 20px; }}
  .head h1 {{ margin: 0 0 6px; font-size: 20px; }}
  .meta {{ color: #9fb1c5; font-size: 13px; }}
  .turn-card {{ margin-bottom: 14px; padding: 14px 16px; border: 1px solid #243244; border-radius: 12px; background: #0d131d; }}
  .turn-card.role-user {{ background: #122421; border-color: #244b43; }}
  .turn-card header {{ display: flex; gap: 8px; align-items: center; margin-bottom: 10px; font-size: 13px; color: #7eaaff; }}
  .turn-num {{ background: rgba(255,255,255,.08); padding: 2px 7px; border-radius: 6px; font-family: monospace; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; color: #eef6ff; }}
  details {{ margin: 8px 0; padding: 8px 12px; border: 1px solid rgba(255,255,255,.1); border-radius: 8px; background: rgba(0,0,0,.28); }}
  summary {{ cursor: pointer; font-weight: 700; color: #fbbf24; margin-bottom: 6px; }}
  .subagent-box {{ margin: 8px 0; padding: 10px 12px; border: 1px solid #3b82f6; border-radius: 8px; background: rgba(29,78,216,.12); }}
  .sub-meta, .usage-meta {{ margin-top: 6px; font-size: 11.5px; color: #94a3b8; font-family: monospace; }}
</style>
</head>
<body>
<div class="container">
  <div class="head">
    <h1>🏮 Lantern Chatbot — Full Session Log</h1>
    <div class="meta">Session ID: <code>{html.escape(session_id)}</code> · Model: <code>{html.escape(model_label)}</code> · Root: <code>{html.escape(str(self.root))}</code> · Total Turns: {len(raw_messages)}</div>
  </div>
  {body_joined}
</div>
</body>
</html>"""

    def normalize_context(self, context: Optional[dict[str, Any]]) -> dict[str, Any]:
        source = context if isinstance(context, dict) else {}
        result: dict[str, Any] = {}
        kind = str(source.get("kind") or "unknown").strip().lower()
        if kind == "files":
            kind = "folder"
        result["kind"] = kind if kind in {"folder", "file", "markdown"} else "unknown"

        def canonical(value: Any) -> str:
            if isinstance(value, dict):
                value = value.get("path") or value.get("rel") or value.get("name") or ""
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
        if mode == "paged":
            mode = "visual"
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
        raw_attachments = source.get("attachments")
        if not isinstance(raw_attachments, list):
            raw_attachments = source.get("attachmentPaths")
        if isinstance(raw_attachments, list):
            normalized_attachments: list[str] = []
            seen: set[str] = set()
            for item in raw_attachments[:32]:
                value = canonical(item)
                if value and value not in seen:
                    seen.add(value)
                    normalized_attachments.append(value)
            if normalized_attachments:
                result["attachments"] = normalized_attachments
        return result

    @staticmethod
    def build_prompt(message: str, context: Optional[dict[str, Any]] = None) -> str:
        text = str(message or "").strip()
        if not text:
            raise ValueError("Chat message is empty")
        if len(text) > 200_000:
            raise ValueError("Chat message is too large")
        # Issue 16: If the message is a slash command (starts with '/'), never wrap
        # <lantern_context> in front of the leading slash so Pi recognizes the command.
        if text.startswith("/"):
            return text
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
        attachments = context.get("attachments")
        if isinstance(attachments, list) and attachments:
            att_lines: list[str] = []
            for item in attachments:
                if isinstance(item, dict):
                    p = str(item.get("path") or item.get("name") or "").strip()
                    if p:
                        att_lines.append(f"- {p}")
                elif item:
                    att_lines.append(f"- {item}")
            if att_lines:
                fields.append("attachments:\n" + "\n".join(att_lines))
        custom_sys = str(context.get("customSystemPrompt") or "").strip()
        if custom_sys:
            fields.append("customSystemPrompt:\n" + custom_sys[:8000])
        skill_paths = context.get("skillPaths")
        if isinstance(skill_paths, list) and skill_paths:
            fields.append("skillPaths:\n" + "\n".join(f"- {sp}" for sp in skill_paths[:24]))
        block = "\n".join(fields) if fields else "kind: unknown"
        return f"<lantern_context>\n{block}\n</lantern_context>\n\n<user_request>\n{text}\n</user_request>"

    def execute_slash_command(
        self,
        raw_message: str,
        context: Optional[dict[str, Any]] = None,
        work_hash: Optional[str] = None,
        scope: str = "local",
    ) -> Optional[dict[str, Any]]:
        """Execute built-in Pi core slash commands or expand discovered /skill commands.
        Returns a response dict if handled directly, or a dict with {'_expanded_prompt': str}
        if a skill/template should be dispatched through Pi core prompt execution."""
        trimmed = str(raw_message or "").strip()
        if not trimmed.startswith("/"):
            return None
        parts = trimmed.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/new", "/reset"):
            state = self.new_session(scope, skip_if_empty=False)
            self.emit({
                "type": "chat_state",
                "state": state,
                "summary": self.summary(scope),
                "models": self.available_models(scope),
                "messages": [],
                "sessions": self.list_sessions(),
            })
            return {"type": "response", "command": cmd, "success": True, "state": state}

        if cmd == "/compact":
            res = self.compact_session(arg)
            try:
                state = self.get_state()
                messages = self.get_messages()
            except Exception:
                state = dict(self.last_state)
                messages = []
            self.emit({
                "type": "chat_compacted",
                "result": res,
                "state": state,
                "summary": self.summary(scope),
                "messages": messages,
            })
            return {"type": "response", "command": "/compact", "success": True, "result": res}

        if cmd == "/fork":
            state = self.fork_session(scope)
            self.emit({
                "type": "chat_state",
                "state": state,
                "summary": self.summary(scope),
                "models": self.available_models(scope),
                "messages": self.get_messages(),
                "sessions": self.list_sessions(),
            })
            return {"type": "response", "command": "/fork", "success": True, "state": state}

        if cmd in ("/thinking", "/think"):
            lvl = arg.lower() if arg else ""
            if lvl not in {"off", "minimal", "low", "medium", "high", "xhigh"}:
                levels = ["off", "low", "medium", "high"]
                cur = str(self._load_prefs().get("thinkingLevel") or self.thinking_level)
                lvl = levels[(levels.index(cur) + 1) % len(levels)] if cur in levels else "high"
            res = self.set_thinking_level(lvl)
            self.emit({
                "type": "chat_prefs_changed",
                **res,
                "summary": self.summary(scope),
            })
            self.emit({
                "type": "chat_slash_message",
                "command": cmd,
                "text": f"🧠 Thinking level updated to **{lvl.upper()}** in Pi core.",
            })
            return {"type": "response", "command": cmd, "success": True, **res}

        if cmd in ("/tools", "/tool", "/mode"):
            preset = arg.lower() if arg else ""
            if preset not in {"full", "code", "readonly", "none"}:
                modes = ["full", "code", "readonly", "none"]
                cur = str(self._load_prefs().get("toolPreset") or self.tool_preset)
                preset = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "full"
            res = self.set_tool_preset(preset)
            self.emit({
                "type": "chat_prefs_changed",
                **res,
                "summary": self.summary(scope),
            })
            self.emit({
                "type": "chat_slash_message",
                "command": cmd,
                "text": f"🛠 Agent tool policy is governed by backend YAML ({preset.upper()}).",
            })
            return {"type": "response", "command": cmd, "success": True, **res}

        if cmd in ("/model", "/models") and arg:
            models = self.available_models(scope)
            q = arg.lower()
            match = next(
                (
                    m for m in models
                    if f"{m['provider']}/{m['id']}".lower() == q
                    or m["id"].lower() == q
                    or q in f"{m['provider']}/{m['id']}".lower()
                    or q in str(m.get("name") or "").lower()
                ),
                None,
            )
            if match:
                res = self.set_model(match["provider"], match["id"], scope)
                self.emit({
                    "type": "chat_model_changed",
                    "state": self.get_state(),
                    "summary": self.summary(scope),
                })
                return res

        if cmd in ("/session", "/sessions", "/resume"):
            sessions = self.list_sessions()
            if arg:
                q = arg.lower()
                match = next(
                    (
                        s for s in sessions
                        if str(s.get("id") or "").lower().startswith(q)
                        or q in str(s.get("name") or "").lower()
                        or q in str(s.get("path") or "").lower()
                    ),
                    None,
                )
                if match and match.get("path"):
                    state = self.switch_session(match["path"], scope)
                    self.emit({
                        "type": "chat_state",
                        "state": state,
                        "summary": self.summary(scope),
                        "models": self.available_models(scope),
                        "messages": self.get_messages(),
                        "sessions": self.list_sessions(),
                    })
                    return {"type": "response", "command": cmd, "success": True, "state": state}
            self.emit({"type": "chat_sessions_list", "sessions": sessions, "openModal": True})
            return {"type": "response", "command": cmd, "success": True, "sessions": sessions}

        if cmd in ("/skills", "/skill"):
            skills = self.discover_skills()
            if arg:
                q = arg.lstrip("/").lower()
                sk = next((s for s in skills if s.get("name", "").lower() == q), None)
                if sk:
                    return self._expand_skill_prompt(sk, "", context)
            if not skills:
                msg_txt = "🧰 No skills discovered yet. Open **⚙ Settings → Skills Configuration** to enable global skills (`~/.pi/agent/skills`) or add custom skill paths."
            else:
                lines = ["🧰 **Discovered Pi Skills** (type `/<skill-name> [instructions]` to run):"]
                for s in skills:
                    lines.append(f"- `{s.get('command')}` ({s.get('scope', 'workspace')}): {s.get('description', '')}")
                msg_txt = "\n".join(lines)
            self.emit({"type": "chat_slash_message", "command": cmd, "text": msg_txt})
            return {"type": "response", "command": cmd, "success": True, "skills": skills}

        if cmd == "/mcp":
            if arg and not arg.lower().startswith(("list", "status", "info")):
                # Pass explicit MCP task instructions to Pi core
                return {"_expanded_prompt": f"Use available MCP tools to fulfill this request: {arg}"}
            mcp_files = [
                self.root / ".pi" / "mcp.json",
                self.root / ".mcp.json",
                Path.home() / ".pi" / "agent" / "mcp.json",
            ]
            found_servers: list[str] = []
            for mf in mcp_files:
                try:
                    if mf.is_file():
                        data = json.loads(mf.read_text(encoding="utf-8"))
                        servers = data.get("mcpServers") or data.get("servers") or {}
                        if isinstance(servers, dict):
                            for sname in servers.keys():
                                found_servers.append(f"`{sname}` ({mf.name})")
                except Exception:
                    pass
            scope_mcp = bool(self.bot_config.access_policy(scope).mcp)
            status_line = f"🔌 **Pi Core MCP Status ({scope})**: {'Enabled' if scope_mcp else 'Disabled by YAML policy'}"
            if found_servers:
                srv_line = "Configured MCP servers: " + ", ".join(found_servers)
            else:
                srv_line = "No external `mcp.json` servers found in workspace or `~/.pi/agent/mcp.json`."
            self.emit({
                "type": "chat_slash_message",
                "command": "/mcp",
                "text": f"{status_line}\n{srv_line}\nTip: Run `/mcp <task>` to instruct Lanbot to use MCP tools.",
            })
            return {"type": "response", "command": "/mcp", "success": True}

        if cmd in ("/help", "/?"):
            skills = self.discover_skills()
            lines = [
                "🏮 **Lanbot Slash Commands (Pi Core & Workspace)**:",
                "- `/model [name]` — Open Model Selector or switch model directly",
                "- `/new` — Start a fresh Pi session",
                "- `/compact [instructions]` — Compact conversation context via Pi core",
                "- `/fork` — Fork current conversation into a new branch",
                "- `/session [name]` — Browse or switch saved sessions",
                "- `/thinking [off|low|medium|high|xhigh]` — Set Pi core thinking effort",
                "- `/skills` — List discovered workspace & global skills",
                "- `/mcp [task]` — Check MCP status or invoke MCP tools",
                "- `/settings` — Open Lanbot Settings (System Prompt, Skills, Export HTML)",
                "- `/export` — Download full unabbreviated HTML session log",
            ]
            if skills:
                lines.append("\n**Installed Skills:**")
                for s in skills[:20]:
                    lines.append(f"- `{s.get('command')}` — {s.get('description', '')}")
            self.emit({"type": "chat_slash_message", "command": "/help", "text": "\n".join(lines)})
            return {"type": "response", "command": "/help", "success": True}

        # Check if command matches any discovered skill (/<skill-name> [args])
        skills = self.discover_skills()
        matched_skill = next(
            (s for s in skills if s.get("command", "").lower() == cmd or f"/{s.get('name', '').lower()}" == cmd),
            None,
        )
        if matched_skill:
            return self._expand_skill_prompt(matched_skill, arg, context)

        return None

    def _expand_skill_prompt(
        self,
        skill: dict[str, str],
        user_arg: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        skill_path = Path(str(skill.get("path") or ""))
        skill_body = ""
        try:
            if skill_path.is_file():
                skill_body = skill_path.read_text(encoding="utf-8", errors="replace")[:32000]
        except Exception:
            skill_body = ""
        req_text = user_arg.strip() or f"Apply the '{skill.get('name')}' skill to the current context."
        expanded = (
            f"<skill_invocation name=\"{skill.get('name', '')}\" path=\"{skill_path}\">\n"
            f"{skill_body}\n"
            f"</skill_invocation>\n\n"
            f"{req_text}"
        )
        return {"_expanded_prompt": expanded, "_include_context": True}

    def prompt(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        work_hash: Optional[str] = None,
        scope: str = "local",
    ) -> dict[str, Any]:
        raw_message = str(message or "").strip()
        if not raw_message:
            raise ValueError("Chat message is empty")
        if len(raw_message) > 200_000:
            raise ValueError("Chat message is too large")
        if not self.bot_config.enabled:
            raise PermissionError("LanternBot is disabled by configuration")
        state = self.bootstrap_state(scope)
        current = state.get("model") if isinstance(state.get("model"), dict) else {}
        provider = str(current.get("provider") or "")
        model_id = str(current.get("id") or "")
        if not provider or not model_id or not self.bot_config.allows_model(provider, model_id, scope=scope):
            raise PermissionError("LanternBot current provider/model is not allowed by configuration")
        self.usage.assert_prompt_allowed(
            max_prompts=self.bot_config.max_prompts_per_day,
            max_tokens=self.bot_config.max_tokens_per_day,
        )

        # Issue 5 & 11: Auto-recover any stale turn lock if the bot is not currently streaming
        with self.turn_lock:
            if not self.streaming and self._turn_in_progress:
                self._turn_in_progress = False
            if self.turn_rel and not self.streaming and not self._turn_in_progress:
                self._emit_work_update(final=True)
            if self._turn_in_progress or self.streaming:
                if self.turn_started_at and (time.monotonic() - self.turn_started_at) > 25.0:
                    self.streaming = False
                    self._turn_in_progress = False
                    self._emit_work_update(final=True)
                else:
                    raise RuntimeError("LanternBot is already completing a turn")

        # Issue 16 & v6 Item 4: Execute Pi core slash commands directly or expand /skill invocations
        if raw_message.startswith("/"):
            slash_res = self.execute_slash_command(raw_message, context=context, work_hash=work_hash, scope=scope)
            if isinstance(slash_res, dict) and "_expanded_prompt" not in slash_res:
                return slash_res
            if isinstance(slash_res, dict) and "_expanded_prompt" in slash_res:
                raw_message = str(slash_res["_expanded_prompt"])
                is_slash_cmd = not bool(slash_res.get("_include_context"))
            else:
                is_slash_cmd = True
        else:
            is_slash_cmd = False
        normalized = {} if is_slash_cmd else self.normalize_context(context)

        if not is_slash_cmd and normalized.get("kind") == "markdown":
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
                    self._emit_work_update(final=True)
                try:
                    turn = self.work_store.begin_turn(rel, work_hash)
                except WorkingCopyError as exc:
                    # Auto-recover with current disk hash if client's work_hash was slightly stale
                    try:
                        fresh_hash = self.work_store.peek_hash(rel)
                        turn = self.work_store.begin_turn(rel, fresh_hash)
                    except WorkingCopyError:
                        raise RuntimeError(str(exc)) from exc
                self.turn_rel = rel
                self.turn_last_hash = str(turn.get("hash") or "") or None
                self.turn_started_at = time.monotonic()
            normalized["logicalPath"] = rel
            normalized["workingPath"] = str(turn["workingPath"])
        elif self.turn_rel:
            self._emit_work_update(final=True)

        prefs = self._load_prefs()
        if not is_slash_cmd:
            if prefs.get("customSystemPrompt"):
                normalized["customSystemPrompt"] = str(prefs["customSystemPrompt"])
            if prefs.get("customSkillPaths"):
                normalized["skillPaths"] = [s["path"] for s in self.discover_skills() if s.get("scope") == "custom"]
        wrapped = self.build_prompt(raw_message, normalized)
        with self.turn_lock:
            if self._turn_in_progress:
                raise RuntimeError("LanternBot is already completing a turn")
            self._turn_in_progress = True
            self._active_turn_scope = scope
            self._turn_had_tool_call = False
            self._last_stop_reason = ""
            self._turn_stream_text.clear()
            self._turn_stream_thinking.clear()
            self._turn_stream_tools.clear()
            self._turn_assistant_saved = False
            setter = getattr(self.work_store, "set_runtime_scope", None)
            try:
                if callable(setter):
                    setter(scope, self.bot_config.access_policy(scope).tools)
            except Exception:
                self._turn_in_progress = False
                self._emit_work_update(final=True)
                raise
        try:
            self._append_message_to_session_jsonl({
                "role": "user",
                "content": wrapped,
                "timestamp": int(time.time() * 1000),
            })
            response = self.request({"type": "prompt", "message": wrapped})
            self.usage.record_prompt()
            return response
        except Exception:
            self._emit_work_update(final=True)
            self._reset_tool_scope()
            raise

    def _schedule_next_steer(self) -> None:
        with self.turn_lock:
            if not self.steer_queue or self._turn_in_progress or self.streaming:
                return
            next_item = self.steer_queue.popleft()

        def _run() -> None:
            try:
                self.emit({
                    "type": "chat_steer_executing",
                    "message": next_item.get("message", ""),
                    "remainingQueue": len(self.steer_queue),
                })
                self.prompt(
                    next_item["message"],
                    next_item.get("context"),
                    work_hash=next_item.get("work_hash"),
                    scope=next_item.get("scope", "local"),
                )
            except Exception as exc:
                self.emit({"type": "chat_error", "error": str(exc)})

        threading.Thread(target=_run, name="lanbot-steer-drain", daemon=True).start()

    def steer(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
        work_hash: Optional[str] = None,
        scope: str = "local",
    ) -> dict[str, Any]:
        raw_message = str(message or "").strip()
        if not raw_message:
            raise ValueError("Chat message is empty")
        with self.turn_lock:
            is_busy = self._turn_in_progress or self.streaming
            if is_busy:
                self.steer_queue.append({
                    "message": raw_message,
                    "context": context,
                    "work_hash": work_hash,
                    "scope": scope,
                })
                qsize = len(self.steer_queue)
                self.emit({
                    "type": "chat_steer_queued",
                    "message": raw_message,
                    "queueSize": qsize,
                })
                return {"ok": True, "steered": True, "queued": True, "queueSize": qsize}
        res = self.prompt(raw_message, context, work_hash=work_hash, scope=scope)
        return {"ok": True, "steered": False, "queued": False, "queueSize": 0, "response": res}

    def abort(self) -> dict[str, Any]:
        with self.turn_lock:
            self.steer_queue.clear()
        try:
            response = self.request({"type": "abort"}, timeout=5.0)
        finally:
            self._emit_work_update(final=True)
            self._reset_tool_scope()
        return response

    def _estimate_session_tokens(self) -> int:
        with self.lock:
            msgs = list(self._session_messages)
        if not msgs:
            return 0
        latest_reported = 0
        trailing_chars = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            usage = m.get("usage") if isinstance(m.get("usage"), dict) else {}
            raw_tok = usage.get("totalTokens", usage.get("total_tokens"))
            if isinstance(raw_tok, (int, float)) and int(raw_tok) > 0:
                latest_reported = int(raw_tok)
                trailing_chars = 0
            else:
                s = extract_message_structured(m)
                trailing_chars += len(s.get("text") or "") + len(s.get("thinking") or "")
                for t in s.get("tools") or []:
                    trailing_chars += len(str(t.get("result") or "")) + len(str(t.get("arguments") or ""))
        return latest_reported + (max(1, trailing_chars // 4) if trailing_chars > 0 else 0)

    def summary(self, scope: str = "local") -> dict[str, Any]:
        state = dict(self.last_state)
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        prefs = self._load_prefs()
        policy = self.bot_config.access_policy(scope)
        with self.lock:
            running = self.proc is not None and self.proc.poll() is None
        return {
            "running": running,
            "streaming": bool(self.streaming),
            "sessionId": str(state.get("sessionId") or ""),
            "model": self._model_public(model) if model else None,
            "favorites": list(prefs.get("favorites") or []),
            "thinkingLevel": str(prefs.get("thinkingLevel") or self.thinking_level),
            "toolPreset": "full" if policy.is_full_tools else "restricted",
            "customSystemPrompt": str(prefs.get("customSystemPrompt") or ""),
            "useGlobalSkills": bool(prefs.get("useGlobalSkills", True)),
            "customSkillPaths": list(prefs.get("customSkillPaths") or []),
            "steerQueueSize": len(self.steer_queue),
            "terminalId": "lantern_bot",
            "name": "LanternBot",
            "policy": self.bot_config.public_policy(scope),
            "usage": self.usage.snapshot(),
            "sessionTokens": self._estimate_session_tokens(),
        }

    def _restart_process(self) -> None:
        with self.lock:
            proc = self.proc
            self.proc = None
            waiting = list(self.pending.values())
            self.pending.clear()
        for item in waiting:
            item.error = RuntimeError("LanternBot process restarted")
            item.event.set()
        if proc:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except Exception:
                    pass
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
        self.ensure_started()

    def close(self) -> None:
        self._emit_work_update(final=True)
        with self.lock:
            self.closed = True
            children = list(self._child_bots.values())
            self._child_bots.clear()
            proc = self.proc
            self.proc = None
            waiting = list(self.pending.values())
            self.pending.clear()
        for child in children:
            try:
                child.close()
            except Exception:
                pass
        for item in waiting:
            item.error = RuntimeError("LanternBot manager closed")
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


PiChatManager = LanternBotManager  # compatibility for older tests/imports


BUILTIN_SLASH_COMMANDS: list[dict[str, str]] = [
    {"command": "/model", "category": "model", "description": "Open Model Selector or switch model (/model <id>)"},
    {"command": "/new", "category": "session", "description": "Start a new Pi session"},
    {"command": "/compact", "category": "session", "description": "Compact session context via Pi core to save tokens"},
    {"command": "/fork", "category": "session", "description": "Fork current conversation into a new branch"},
    {"command": "/session", "category": "session", "description": "Switch or manage saved conversations"},
    {"command": "/thinking", "category": "config", "description": "Set Pi core thinking level (off|low|medium|high|xhigh)"},
    {"command": "/skills", "category": "skill", "description": "List discovered workspace & global skills"},
    {"command": "/mcp", "category": "tools", "description": "Inspect MCP status or run an MCP task"},
    {"command": "/settings", "category": "config", "description": "Open Lanbot Settings (System Prompt, Skills, Export HTML)"},
    {"command": "/export", "category": "session", "description": "Export full unabbreviated HTML session log"},
    {"command": "/help", "category": "ui", "description": "Show all available slash commands and skills"},
    {"command": "/clear", "category": "ui", "description": "Clear local status notifications"},
]


def extract_message_text(msg: dict[str, Any]) -> str:
    return extract_message_structured(msg).get("text", "")


def build_prompt(message: str, context: Optional[dict[str, Any]] = None) -> str:
    return LanternBotManager.build_prompt(message, context)


def export_session_html(snapshot: dict[str, Any]) -> str:
    """Standalone helper to export a session snapshot dict as a full unabbreviated HTML log."""
    session_name = html.escape(str(snapshot.get("sessionName") or snapshot.get("sessionId") or "Lantern Session"))
    session_file = html.escape(str(snapshot.get("sessionFile") or ""))
    model = snapshot.get("model") or {}
    model_str = html.escape(f"{model.get('provider', 'default')} / {model.get('name') or model.get('id') or 'default'}")
    messages = snapshot.get("messages") or []
    rows: list[str] = []
    for idx, msg in enumerate(messages, 1):
        role = html.escape(str(msg.get("role") or "assistant").upper())
        text = html.escape(str(msg.get("text") or ""))
        thinking = str(msg.get("thinking") or "")
        thinking_html = (
            f'<details open><summary>💭 Full Thinking Log</summary><pre>{html.escape(thinking)}</pre></details>'
            if thinking
            else ""
        )
        rows.append(
            f'<section class="turn"><h3>#{idx} {role}</h3>{thinking_html}<pre>{text}</pre></section>'
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{session_name} — FULL UNABBREVIATED CONTEXT</title></head><body>"
        f"<h1>{session_name} — FULL UNABBREVIATED CONTEXT</h1>"
        f"<p>Session: {session_file} | Model: {model_str}</p>"
        + "\n".join(rows)
        + "</body></html>"
    )

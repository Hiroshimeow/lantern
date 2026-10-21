from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
        access_scope: str = "local",
    ) -> None:
        self.root = Path(root).resolve()
        self.access_scope = "lan" if str(access_scope or "").strip().lower() == "lan" else "local"
        if self.access_scope == "lan":
            self.bot_cwd = (self.root / ".lantern" / "lan_workspace").resolve()
            try:
                self.bot_cwd.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            self.bot_cwd = self.root
        self.runtime_id: str = f"rt-{uuid4().hex[:10]}"
        self._raw_emit = emit
        safe_cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        if safe_cid == "default":
            safe_cid = ""
        self.client_session_id: str = safe_cid
        self._parent_bot: Optional["LanternBotManager"] = parent_bot
        self._child_bots: dict[str, "LanternBotManager"] = {}
        self._shared_bots: dict[str, "LanternBotManager"] = {}
        self._running_session_bots: dict[str, "LanternBotManager"] = {}
        self._shared_bindings: dict[str, str] = {}
        self._private_clients: set[str] = set()
        self._cached_models: dict[str, list[dict[str, Any]]] = {}
        self._session_file_cache: dict[tuple[str, float, int], dict[str, Any]] = {}
        self._turn_attached_md_rels: list[str] = []
        raw_sdir = (Path(session_dir) if session_dir else
                    Path.home() / ".lantern" / "pi-sessions").resolve()
        if parent_bot is not None and hasattr(parent_bot, "base_session_dir"):
            self.base_session_dir: Path = parent_bot.base_session_dir
        elif raw_sdir.name == "lan":
            self.base_session_dir = raw_sdir.parent.resolve()
        else:
            self.base_session_dir = raw_sdir
        if self.access_scope == "lan":
            self.session_dir = (self.base_session_dir / "lan").resolve()
        else:
            self.session_dir = self.base_session_dir
        self.shared_registry_path: Path = self.base_session_dir / "lantern-shared.json"
        self.rebind_emit(emit)
        state_fname = f"lantern-active-{self.client_session_id}.json" if self.client_session_id else "lantern-active.json"
        self.state_path = self.session_dir / state_fname
        self.latest_state_path = self.session_dir / "lantern-active.json"
        self.session_names_path = self.session_dir / "lantern-session-names.json"
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
        self._turn_extra_locked_rels: dict[str, Optional[str]] = {}
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
        self._active_turn_scope: str = self.access_scope
        self._active_turn_session_id: str = ""
        self._active_turn_session_file: Optional[Path] = None
        self._turn_had_tool_call: bool = False
        self._last_stop_reason: str = ""
        self._switched_session_override: Optional[dict[str, str]] = None
        self._needs_history_hydration: bool = False
        if self.client_session_id and not self.state_path.is_file():
            self._inherit_latest_session_on_init()

    @staticmethod
    def _atomic_write_text(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".tmp", dir=str(target.parent))
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            for attempt in range(8):
                try:
                    os.replace(tmp_path, target)
                    tmp_path = None
                    break
                except (PermissionError, OSError):
                    if attempt == 7:
                        raise
                    time.sleep(0.025 * (attempt + 1))
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _scope_session_dir(self, scope: Optional[str] = None) -> Path:
        eff = str(scope or self.access_scope or "local").strip().lower()
        base = getattr(self, "base_session_dir", self.session_dir)
        if eff == "lan":
            return (base / "lan").resolve()
        return base

    def _scope_cwd(self, scope: Optional[str] = None) -> Path:
        eff = str(scope or self.access_scope or "local").strip().lower()
        if eff == "lan":
            d = (self.root / ".lantern" / "lan_workspace").resolve()
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            return d
        return self.root

    def _inherit_latest_session_on_init(self) -> None:
        """When a new browser tab opens Lanbot for the first time, inherit the active session
        from lantern-active.json if present while keeping its tab state file independent."""
        try:
            if self.latest_state_path.is_file():
                raw = json.loads(self.latest_state_path.read_text(encoding="utf-8"))
                sf = str(raw.get("sessionFile") or "").strip()
                sid = str(raw.get("sessionId") or "").strip()
                cand_path = Path(sf) if sf else (self.session_dir / f"{sid}.jsonl" if sid else None)
                if cand_path and not cand_path.is_file() and sid:
                    alt = self.session_dir / f"{sid}.jsonl"
                    if alt.is_file():
                        cand_path = alt
                if cand_path and cand_path.is_file():
                    self._atomic_write_text(self.state_path, json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
                    self._switched_session_override = {"sessionId": sid or cand_path.stem, "sessionFile": str(cand_path)}
                    self.last_state["sessionId"] = sid or cand_path.stem
                    self.last_state["sessionFile"] = str(cand_path)
                    self._session_messages = self._load_messages_from_jsonl(cand_path)
                    self._needs_history_hydration = bool(self._session_messages)
        except Exception:
            pass

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
            with self.lock:
                self._atomic_write_text(self.prefs_path, json.dumps(prefs, ensure_ascii=False, indent=2) + "\n")
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
            head = skill_md.read_text(encoding="utf-8", errors="ignore")[:3000]
            # Check YAML frontmatter block first
            fm_match = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---", head)
            search_area = fm_match.group(1) if fm_match else head
            m = re.search(r"^description:\s*(.*)$", search_area, re.MULTILINE | re.IGNORECASE)
            if m:
                inline_val = m.group(1).strip()
                if inline_val and inline_val not in ("|", ">", "|+", "|-", ">+", ">-"):
                    return inline_val.strip("\"'")[:160]
                # Multi-line YAML block scalar
                after = search_area[m.end():].splitlines()
                collected: list[str] = []
                for line in after:
                    if not line.strip():
                        if collected:
                            break
                        continue
                    if line.startswith((" ", "\t")):
                        collected.append(line.strip())
                    else:
                        break
                if collected:
                    return " ".join(collected).strip("\"'")[:160]
            # Fallback to first non-heading text line after frontmatter
            body = head[fm_match.end():] if fm_match else head
            for line in body.splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "---", "```", "<")):
                    return s[:160]
        except Exception:
            pass
        return f"Run skill {fallback_name}"

    def discover_skills(self) -> list[dict[str, str]]:
        prefs = self._load_prefs()
        use_global = bool(prefs.get("useGlobalSkills", True))
        custom_paths = prefs.get("customSkillPaths") or []
        candidate_roots: list[tuple[str, Path]] = [
            ("workspace", (self.root / ".pi" / "skills").resolve()),
            ("workspace", (self.root / ".lantern" / "skills").resolve()),
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
                    elif (
                        item.is_file()
                        and item.suffix.lower() == ".md"
                        and item.name.upper() not in ("SKILL.MD", "README.MD")
                        and item.stem not in seen_names
                    ):
                        seen_names.add(item.stem)
                        skills.append({
                            "name": item.stem,
                            "command": f"/{item.stem}",
                            "category": "skill",
                            "scope": scope_label,
                            "path": str(item),
                            "description": self._extract_skill_description(item, item.stem),
                        })
            except Exception:
                continue
        return skills

    def discover_mcp_servers(self) -> list[dict[str, str]]:
        mcp_files = [
            ("workspace", self.root / ".pi" / "mcp.json"),
            ("workspace", self.root / ".mcp.json"),
            ("global", Path.home() / ".pi" / "agent" / "mcp.json"),
            ("global", Path.home() / ".pi" / "mcp.json"),
        ]
        servers_out: list[dict[str, str]] = []
        seen: set[str] = set()
        for scope_lbl, mf in mcp_files:
            try:
                if mf.is_file():
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    servers = data.get("mcpServers") or data.get("servers") or {}
                    if isinstance(servers, dict):
                        for sname, scfg in servers.items():
                            key = f"{scope_lbl}:{sname}"
                            if key in seen:
                                continue
                            seen.add(key)
                            cmd_str = ""
                            if isinstance(scfg, dict):
                                cmd_str = str(scfg.get("command") or scfg.get("url") or "")
                            servers_out.append({
                                "name": str(sname),
                                "scope": scope_lbl,
                                "source": mf.name,
                                "command": cmd_str,
                            })
            except Exception:
                pass
        return servers_out

    def discover_extensions(self) -> list[dict[str, str]]:
        exts: list[dict[str, str]] = []
        if self.guard_extension.is_file():
            exts.append({
                "name": self.guard_extension.name,
                "scope": "builtin",
                "path": str(self.guard_extension),
            })
        ext_roots = [
            ("workspace", self.root / ".pi" / "extensions"),
            ("global", Path.home() / ".pi" / "agent" / "extensions"),
        ]
        for scope_lbl, eroot in ext_roots:
            try:
                if eroot.is_dir():
                    for item in sorted(eroot.iterdir()):
                        if item.is_file() and item.suffix.lower() in (".ts", ".mjs", ".js"):
                            exts.append({
                                "name": item.name,
                                "scope": scope_lbl,
                                "path": str(item.resolve()),
                            })
            except Exception:
                pass
        return exts

    def scaffold_harness_skills(self) -> dict[str, Any]:
        """Safely scaffold starter coding harness skills into <workspace>/.pi/skills/
        without overwriting any existing user skill files."""
        skills_root = (self.root / ".pi" / "skills").resolve()
        templates: dict[str, str] = {
            "verify-loop": (
                "---\n"
                "name: verify-loop\n"
                "description: Auto-run tests/linters after code changes, inspect tracebacks, and self-fix until 100% green.\n"
                "---\n"
                "# Verify-Loop Coding Harness\n\n"
                "When invoked, follow this strict execution loop:\n"
                "1. Detect the project stack and test/lint runner (`pytest`, `npm test`, `tsc`, `cargo test`, `go test`).\n"
                "2. Implement the requested code changes cleanly.\n"
                "3. Run the relevant unit tests or syntax/type checks via terminal tool.\n"
                "4. If any check fails (non-zero exit code):\n"
                "   - Read the exact traceback/error output.\n"
                "   - Fix the root cause in code.\n"
                "   - Re-run verification (up to 3 self-repair iterations).\n"
                "5. Conclude only when verification passes or report the exact blocker.\n"
            ),
            "checkpoint": (
                "---\n"
                "name: checkpoint\n"
                "description: Audit git status/diff before and after edits to guarantee safe, reversible changes.\n"
                "---\n"
                "# Git Checkpoint & Diff Audit Harness\n\n"
                "When invoked:\n"
                "1. Inspect `git status --short` and `git diff --stat` before modifying files.\n"
                "2. Apply minimal, targeted edits without touching unrelated files.\n"
                "3. After editing, run `git diff` to verify no unintended regressions or leftover debug code remain.\n"
                "4. Provide a concise file-by-file change summary.\n"
            ),
            "planner": (
                "---\n"
                "name: planner\n"
                "description: Decompose complex engineering tasks into verifiable step-by-step milestones.\n"
                "---\n"
                "# Structured Engineering Planner Harness\n\n"
                "When invoked:\n"
                "1. Analyze dependencies, affected files, and edge cases before writing code.\n"
                "2. Break the request into granular, verifiable milestones (`- [ ] Step ...`).\n"
                "3. Execute each milestone sequentially, verifying each step before advancing.\n"
                "4. Summarize completed milestones `[x]` and verification results at the end.\n"
            ),
        }
        created: list[str] = []
        existing: list[str] = []
        for sname, body in templates.items():
            sdir = skills_root / sname
            smd = sdir / "SKILL.md"
            if smd.is_file():
                existing.append(f"/{sname}")
            else:
                sdir.mkdir(parents=True, exist_ok=True)
                smd.write_text(body, encoding="utf-8")
                created.append(f"/{sname}")
        discovered = self.discover_skills()
        self.emit({
            "type": "chat_commands_changed",
            "skills": discovered,
        })
        return {
            "created": created,
            "existing": existing,
            "skills": discovered,
        }

    def _all_bot_instances(self) -> list["LanternBotManager"]:
        root_bot = self._parent_bot or self
        with root_bot.lock:
            seen: dict[int, "LanternBotManager"] = {id(root_bot): root_bot}
            for b in list(root_bot._child_bots.values()) + list(root_bot._shared_bots.values()) + list(root_bot._running_session_bots.values()):
                if b is not None and not b.closed:
                    seen[id(b)] = b
            return list(seen.values())

    def current_session_id(self) -> str:
        return str(
            (self._switched_session_override or {}).get("sessionId")
            or self.last_state.get("sessionId")
            or ""
        ).strip()

    @staticmethod
    def _client_bind_key(client_session_id: Optional[str], scope: str) -> str:
        eff_scope = "lan" if str(scope or "").strip().lower() == "lan" else "local"
        cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        if not cid or cid == "default":
            cid = "default"
        return f"{eff_scope}:{cid}"

    def shared_sessions(self) -> dict[str, str]:
        """Read <base_session_dir>/lantern-shared.json mapping shared localhost sessionId -> file path."""
        root_bot = self._parent_bot or self
        reg_path = root_bot.shared_registry_path
        if not reg_path.is_file():
            return {}
        try:
            raw = json.loads(reg_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            out: dict[str, str] = {}
            local_sdir = root_bot._scope_session_dir("local")
            for k, v in raw.items():
                sid = str(k or "").strip()
                spath = str(v or "").strip()
                if not sid:
                    continue
                cand = Path(spath) if spath else (local_sdir / f"{sid}.jsonl")
                if not cand.is_file():
                    alt = local_sdir / f"{sid}.jsonl"
                    if alt.is_file():
                        cand = alt
                if cand.is_file():
                    out[sid] = str(cand.resolve())
            return out
        except Exception:
            return {}

    def _save_shared_sessions(self, mapping: dict[str, str]) -> None:
        root_bot = self._parent_bot or self
        self._atomic_write_text(
            root_bot.shared_registry_path,
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        )

    @staticmethod
    def _extract_session_id_from_file(fpath: Path) -> str:
        sid = fpath.stem
        try:
            if fpath.is_file():
                with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                    for idx, line in enumerate(fh):
                        if idx > 10:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            if obj.get("type") == "session" and obj.get("id"):
                                return str(obj["id"]).strip()
                            if obj.get("sessionId"):
                                return str(obj["sessionId"]).strip()
        except Exception:
            pass
        return sid

    def _find_session_file_in_dir(self, sdir: Path, session_id: str = "", session_path: str = "") -> Optional[Path]:
        if session_path:
            try:
                cp = Path(session_path).expanduser().resolve()
                if cp.is_file() and cp.parent.resolve() == sdir.resolve():
                    return cp
            except Exception:
                pass
        clean_id = str(session_id or "").strip()
        if not clean_id and session_path:
            clean_id = Path(session_path).stem
        if not clean_id or not sdir.is_dir():
            return None
        direct = (sdir / f"{clean_id}.jsonl").resolve()
        if direct.is_file():
            return direct
        for fp in sorted(sdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True):
            if fp.stem == clean_id or fp.stem.endswith(f"_{clean_id}"):
                return fp.resolve()
            if self._extract_session_id_from_file(fp) == clean_id:
                return fp.resolve()
        return None

    def _materialize_session_file_if_needed(self, bot_inst: "LanternBotManager", sdir: Path, session_id: str) -> Path:
        existing = self._find_session_file_in_dir(sdir, session_id, bot_inst._saved_session_file() or "")
        if existing and existing.is_file() and existing.stat().st_size > 0:
            return existing
        sdir.mkdir(parents=True, exist_ok=True)
        target = (sdir / f"{session_id}.jsonl").resolve()
        lines_out = [
            json.dumps({
                "type": "session",
                "version": 3,
                "id": session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "cwd": str(bot_inst._scope_cwd(bot_inst.access_scope)),
                "lantern": True,
            }, ensure_ascii=False, separators=(",", ":"))
        ]
        prev_id = None
        for m in list(bot_inst._session_messages):
            if not isinstance(m, dict):
                continue
            eid = uuid4().hex[:8]
            lines_out.append(json.dumps({
                "type": "message",
                "id": eid,
                "parentId": prev_id,
                "sessionId": session_id,
                "timestamp": int(time.time() * 1000),
                "role": str(m.get("role") or "assistant"),
                "content": m.get("content", m.get("text", "")),
                "message": m,
            }, ensure_ascii=False, separators=(",", ":")))
            prev_id = eid
        self._atomic_write_text(target, "\n".join(lines_out) + "\n")
        return target

    def set_session_shared(
        self,
        session_id: str,
        shared: bool = True,
        *,
        session_path: str = "",
        scope: str = "local",
    ) -> dict[str, Any]:
        """Enable or disable sharing of a localhost session with LAN clients."""
        if str(scope or "local").strip().lower() != "local":
            raise PermissionError("Only localhost can share or unshare sessions")
        root_bot = self._parent_bot or self
        local_sdir = root_bot._scope_session_dir("local")
        lan_sdir = root_bot._scope_session_dir("lan")
        clean_id = str(session_id or "").strip()
        if not clean_id and session_path:
            clean_id = self._extract_session_id_from_file(Path(session_path))
        if not clean_id:
            raise ValueError("sessionId is required to share or unshare a session")

        if session_path:
            try:
                cp = Path(session_path).expanduser().resolve()
                if cp.is_relative_to(lan_sdir):
                    raise ValueError("LAN sessions are already visible to localhost and cannot be shared")
            except ValueError as exc:
                if "LAN sessions" in str(exc):
                    raise

        with root_bot.lock:
            reg = root_bot.shared_sessions()
            if shared:
                owner_bot: Optional["LanternBotManager"] = None
                for b in root_bot._all_bot_instances():
                    if b.access_scope == "local" and b.current_session_id() == clean_id:
                        owner_bot = b
                        break
                cand = root_bot._find_session_file_in_dir(local_sdir, clean_id, session_path)
                if cand is None and owner_bot is not None:
                    cand = root_bot._materialize_session_file_if_needed(owner_bot, local_sdir, clean_id)
                if cand is None:
                    if root_bot._find_session_file_in_dir(lan_sdir, clean_id, session_path) is not None:
                        raise ValueError("Only localhost sessions can be shared to LAN")
                    cand = root_bot._materialize_session_file_if_needed(self, local_sdir, clean_id)
                clean_id = self._extract_session_id_from_file(cand) or clean_id
                reg[clean_id] = str(cand.resolve())
                root_bot._save_shared_sessions(reg)
                if owner_bot is not None:
                    root_bot._shared_bots[clean_id] = owner_bot
                    owner_key = self._client_bind_key(owner_bot.client_session_id, "local")
                    if owner_key not in root_bot._private_clients:
                        root_bot._shared_bindings[owner_key] = clean_id
            else:
                reg.pop(clean_id, None)
                if session_path:
                    reg.pop(Path(session_path).stem, None)
                root_bot._save_shared_sessions(reg)
                for bkey, bound_sid in list(root_bot._shared_bindings.items()):
                    if bound_sid == clean_id and bkey.startswith("lan:"):
                        root_bot._shared_bindings.pop(bkey, None)
                        root_bot._private_clients.add(bkey)
                if not any(v == clean_id for v in root_bot._shared_bindings.values()):
                    root_bot._shared_bots.pop(clean_id, None)

        try:
            root_bot._raw_emit({
                "type": "chat_sessions_changed",
                "sessionId": clean_id,
                "shared": bool(shared),
            })
        except Exception:
            pass
        return {"ok": True, "sessionId": clean_id, "shared": bool(shared), "sharedSessions": reg}

    def select_shared_session(
        self,
        client_id: Optional[str],
        scope: str,
        session_id: str = "",
        *,
        session_path: str = "",
        session_scope: str = "",
    ) -> Optional["LanternBotManager"]:
        """Bind or unbind a viewer (client_id, scope) to a shared localhost session or LAN session.
        Returns the shared LanternBotManager runtime if bound, or None if the target is a private session."""
        root_bot = self._parent_bot or self
        eff_scope = "lan" if str(scope or "").strip().lower() == "lan" else "local"
        bind_key = self._client_bind_key(client_id, eff_scope)
        clean_id = str(session_id or "").strip()
        clean_path = str(session_path or "").strip()
        if not clean_id and clean_path:
            clean_id = self._extract_session_id_from_file(Path(clean_path))

        with root_bot.lock:
            if not clean_id and not clean_path:
                prev_sid = root_bot._shared_bindings.pop(bind_key, None)
                current_default_bot = root_bot._lookup_default_bot_locked(client_id, eff_scope)
                if prev_sid or (current_default_bot is not None and current_default_bot in root_bot._shared_bots.values()):
                    root_bot._private_clients.add(bind_key)
                return None

            local_sdir = root_bot._scope_session_dir("local")
            lan_sdir = root_bot._scope_session_dir("lan")
            shared_reg = root_bot.shared_sessions()

            local_cand = root_bot._find_session_file_in_dir(local_sdir, clean_id, clean_path)
            lan_cand = root_bot._find_session_file_in_dir(lan_sdir, clean_id, clean_path)
            if local_cand is not None and not clean_id:
                clean_id = self._extract_session_id_from_file(local_cand)
            elif lan_cand is not None and not clean_id:
                clean_id = self._extract_session_id_from_file(lan_cand)

            # Determine if this session is shared or cross-scope
            target_scope: Optional[str] = None
            target_file: Optional[Path] = None

            if eff_scope == "lan":
                if clean_id in shared_reg:
                    target_scope = "local"
                    target_file = Path(shared_reg[clean_id])
                elif local_cand is not None and str(local_cand.resolve()) in shared_reg.values():
                    for k_sid, v_path in shared_reg.items():
                        if Path(v_path).resolve() == local_cand.resolve():
                            clean_id = k_sid
                            target_scope = "local"
                            target_file = local_cand
                            break
                elif session_scope == "local" or (local_cand is not None and lan_cand is None):
                    raise PermissionError("Session is not shared with LAN")
                else:
                    # Switching to a LAN session: if it is currently shared with localhost in _shared_bots, reuse it
                    if clean_id in root_bot._shared_bots:
                        target_scope = "lan"
                        target_file = lan_cand
                    else:
                        prev_sid = root_bot._shared_bindings.pop(bind_key, None)
                        current_default_bot = root_bot._lookup_default_bot_locked(client_id, eff_scope)
                        if prev_sid or (current_default_bot is not None and current_default_bot in root_bot._shared_bots.values()):
                            root_bot._private_clients.add(bind_key)
                        return None
            else:
                # Viewer is localhost (eff_scope == "local")
                live_lan_bot = next(
                    (b for b in root_bot._all_bot_instances() if b.access_scope == "lan" and b.current_session_id() == clean_id),
                    None,
                )
                if session_scope == "lan" or live_lan_bot is not None or (lan_cand is not None and local_cand is None):
                    target_scope = "lan"
                    target_file = lan_cand
                elif clean_id in shared_reg or clean_id in root_bot._shared_bots:
                    target_scope = "local"
                    target_file = Path(shared_reg[clean_id]) if clean_id in shared_reg else local_cand
                else:
                    prev_sid = root_bot._shared_bindings.pop(bind_key, None)
                    current_default_bot = root_bot._lookup_default_bot_locked(client_id, eff_scope)
                    if prev_sid or (current_default_bot is not None and current_default_bot in root_bot._shared_bots.values()):
                        root_bot._private_clients.add(bind_key)
                    return None

            # Find or create the shared runtime manager for (clean_id, target_scope)
            owner = root_bot._shared_bots.get(clean_id)
            if owner is not None and (owner.closed or (owner.current_session_id() and owner.current_session_id() != clean_id)):
                owner = None
            if owner is None:
                for b in root_bot._all_bot_instances():
                    if not b.closed and b.access_scope == target_scope and b.current_session_id() == clean_id:
                        owner = b
                        owner_bind_key = self._client_bind_key(b.client_session_id, b.access_scope)
                        if owner_bind_key not in root_bot._private_clients:
                            root_bot._shared_bindings[owner_bind_key] = clean_id
                        break
            if owner is None:
                shared_bot_key = f"shared:{target_scope}:{clean_id}"
                owner = root_bot._child_bots.get(shared_bot_key)
                if owner is None or owner.closed:
                    owner = LanternBotManager(
                        root_bot.root,
                        root_bot._raw_emit,
                        work_store=root_bot.work_store,
                        session_dir=root_bot.base_session_dir,
                        argv_override=root_bot.argv_override,
                        request_timeout=root_bot.request_timeout,
                        bot_config=root_bot.bot_config,
                        usage_path=root_bot.usage.path,
                        client_session_id=f"shared_{clean_id[:24]}",
                        parent_bot=root_bot,
                        access_scope=target_scope,
                    )
                    root_bot._child_bots[shared_bot_key] = owner
                if target_file is not None and target_file.is_file() and owner.current_session_id() != clean_id:
                    owner.switch_session(str(target_file), scope=target_scope)

            root_bot._shared_bots[clean_id] = owner
            root_bot._shared_bindings[bind_key] = clean_id
            return owner

    def _lookup_default_bot_locked(self, client_session_id: Optional[str], eff_scope: str) -> Optional["LanternBotManager"]:
        root_bot = self._parent_bot or self
        cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        if (not cid or cid == "default") and eff_scope == root_bot.access_scope:
            return root_bot
        effective_cid = cid or f"{eff_scope}_default"
        bot_key = f"{eff_scope}:{effective_cid}" if eff_scope == "lan" else effective_cid
        return root_bot._child_bots.get(bot_key)

    def peek_session_bot(self, client_session_id: Optional[str] = None, *, scope: str = "local") -> Optional["LanternBotManager"]:
        """Non-allocating lookup of the current LanternBotManager for (client_session_id, scope)."""
        root_bot = self._parent_bot or self
        eff_scope = "lan" if str(scope or root_bot.access_scope or "local").strip().lower() == "lan" else "local"
        bind_key = self._client_bind_key(client_session_id, eff_scope)
        with root_bot.lock:
            bound_sid = root_bot._shared_bindings.get(bind_key)
            if bound_sid:
                if eff_scope == "lan":
                    shared_reg = root_bot.shared_sessions()
                    shared_mgr = root_bot._shared_bots.get(bound_sid)
                    if shared_mgr is not None and shared_mgr.access_scope == "local" and bound_sid not in shared_reg:
                        root_bot._shared_bindings.pop(bind_key, None)
                        root_bot._private_clients.add(bind_key)
                        bound_sid = None
                if bound_sid:
                    shared_mgr = root_bot._shared_bots.get(bound_sid)
                    if shared_mgr is not None and not shared_mgr.closed:
                        return shared_mgr
            if bind_key in root_bot._private_clients:
                priv = root_bot._child_bots.get(f"private:{bind_key}")
                if priv is not None and not priv.closed:
                    return priv
            cand = root_bot._lookup_default_bot_locked(client_session_id, eff_scope)
            if cand is not None and not cand.closed:
                return cand
            return None

    def get_session_bot(self, client_session_id: Optional[str] = None, *, scope: str = "local") -> "LanternBotManager":
        """Return or lazily create a LanternBotManager for a specific tab/client session ID and access scope,
        honoring shared session bindings and isolating tabs that left a shared runtime."""
        root_bot = self._parent_bot or self
        eff_scope = "lan" if str(scope or root_bot.access_scope or "local").strip().lower() == "lan" else "local"
        cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        bind_key = self._client_bind_key(cid, eff_scope)

        with root_bot.lock:
            bound_sid = root_bot._shared_bindings.get(bind_key)
            if bound_sid:
                if eff_scope == "lan":
                    shared_reg = root_bot.shared_sessions()
                    shared_mgr = root_bot._shared_bots.get(bound_sid)
                    if shared_mgr is not None and shared_mgr.access_scope == "local" and bound_sid not in shared_reg:
                        root_bot._shared_bindings.pop(bind_key, None)
                        root_bot._private_clients.add(bind_key)
                        bound_sid = None
                if bound_sid:
                    shared_mgr = root_bot._shared_bots.get(bound_sid)
                    if shared_mgr is not None and not shared_mgr.closed:
                        return shared_mgr

            default_cand = root_bot._lookup_default_bot_locked(cid, eff_scope)
            if bind_key in root_bot._private_clients or (
                default_cand is not None and default_cand in root_bot._shared_bots.values()
            ):
                priv_key = f"private:{bind_key}"
                priv = root_bot._child_bots.get(priv_key)
                if priv is None or priv.closed:
                    priv = LanternBotManager(
                        root_bot.root,
                        root_bot._raw_emit,
                        work_store=root_bot.work_store,
                        session_dir=root_bot.base_session_dir,
                        argv_override=root_bot.argv_override,
                        request_timeout=root_bot.request_timeout,
                        bot_config=root_bot.bot_config,
                        usage_path=root_bot.usage.path,
                        client_session_id=cid or f"priv_{eff_scope}",
                        parent_bot=root_bot,
                        access_scope=eff_scope,
                    )
                    root_bot._child_bots[priv_key] = priv
                return priv

            if (not cid or cid == "default") and eff_scope == root_bot.access_scope:
                return root_bot
            effective_cid = cid or f"{eff_scope}_default"
            bot_key = f"{eff_scope}:{effective_cid}" if eff_scope == "lan" else effective_cid
            child = root_bot._child_bots.get(bot_key)
            if child is None or child.closed:
                child = LanternBotManager(
                    root_bot.root,
                    root_bot._raw_emit,
                    work_store=root_bot.work_store,
                    session_dir=root_bot.base_session_dir,
                    argv_override=root_bot.argv_override,
                    request_timeout=root_bot.request_timeout,
                    bot_config=root_bot.bot_config,
                    usage_path=root_bot.usage.path,
                    client_session_id=cid,
                    parent_bot=root_bot,
                    access_scope=eff_scope,
                )
                root_bot._child_bots[bot_key] = child
            return child

    def detach_busy_bot_for_switch(
        self,
        client_session_id: Optional[str] = None,
        *,
        scope: str = "local",
        target_session_id: str = "",
        target_session_path: str = "",
    ) -> "LanternBotManager":
        """If the tab's current LanternBotManager is actively running a turn, park it in
        _running_session_bots so it finishes in the background without being aborted or
        bleeding its response into the newly selected session. If switching back to a
        background-running session, re-attach to that bot."""
        root_bot = self._parent_bot or self
        eff_scope = "lan" if str(scope or root_bot.access_scope or "local").strip().lower() == "lan" else "local"
        cid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(client_session_id or "").strip())[:64]
        bind_key = self._client_bind_key(cid, eff_scope)
        clean_target_sid = str(target_session_id or "").strip()
        if not clean_target_sid and target_session_path:
            try:
                clean_target_sid = self._extract_session_id_from_file(Path(target_session_path))
            except Exception:
                clean_target_sid = Path(target_session_path).stem

        with root_bot.lock:
            # 1. If target session is in _running_session_bots, rebind tab to it!
            if clean_target_sid and clean_target_sid in root_bot._running_session_bots:
                running_bot = root_bot._running_session_bots.get(clean_target_sid)
                if running_bot is not None and not running_bot.closed and running_bot.access_scope == eff_scope:
                    running_bot.client_session_id = cid
                    effective_cid = cid or f"{eff_scope}_default"
                    bot_key = f"{eff_scope}:{effective_cid}" if eff_scope == "lan" else effective_cid
                    root_bot._child_bots[bot_key] = running_bot
                    if bind_key in root_bot._private_clients:
                        root_bot._child_bots[f"private:{bind_key}"] = running_bot
                    if not (running_bot.streaming or running_bot._turn_in_progress):
                        root_bot._running_session_bots.pop(clean_target_sid, None)
                    return running_bot

            cur_bot = root_bot.get_session_bot(cid, scope=eff_scope)
            cur_sid = cur_bot.current_session_id()
            is_busy = bool(cur_bot.streaming or cur_bot._turn_in_progress)
            if is_busy and cur_sid and cur_sid != clean_target_sid and cur_bot not in root_bot._shared_bots.values():
                # Park cur_bot in _running_session_bots so it finishes its turn undisturbed!
                root_bot._running_session_bots[cur_sid] = cur_bot
                cur_bot.client_session_id = f"bg_{cur_sid[:24]}"
                new_bot = LanternBotManager(
                    root_bot.root,
                    root_bot._raw_emit,
                    work_store=root_bot.work_store,
                    session_dir=root_bot.base_session_dir,
                    argv_override=root_bot.argv_override,
                    request_timeout=root_bot.request_timeout,
                    bot_config=root_bot.bot_config,
                    usage_path=root_bot.usage.path,
                    client_session_id=cid or f"priv_{eff_scope}",
                    parent_bot=root_bot,
                    access_scope=eff_scope,
                )
                if root_bot.last_state.get("model"):
                    new_bot.last_state["model"] = dict(root_bot.last_state["model"])
                effective_cid = cid or f"{eff_scope}_default"
                bot_key = f"{eff_scope}:{effective_cid}" if eff_scope == "lan" else effective_cid
                root_bot._child_bots[bot_key] = new_bot
                if bind_key in root_bot._private_clients or cur_bot is root_bot:
                    root_bot._private_clients.add(bind_key)
                    root_bot._child_bots[f"private:{bind_key}"] = new_bot
                return new_bot
            return cur_bot

    def _load_session_names(self, scope: Optional[str] = None) -> dict[str, str]:
        sdir = self._scope_session_dir(scope)
        names_file = sdir / "lantern-session-names.json"
        if not names_file.is_file():
            return {}
        try:
            raw = json.loads(names_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items() if str(v).strip()}
        except Exception:
            pass
        return {}

    def rename_session(
        self,
        session_id: str,
        name: str,
        *,
        session_path: str = "",
        scope: Optional[str] = None,
        viewer_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        root_bot = self._parent_bot or self
        clean_id = str(session_id or "").strip()
        clean_name = str(name or "").strip()[:120]
        if clean_name.startswith("[Lan]-"):
            clean_name = clean_name[len("[Lan]-"):].strip()
        target_scope = str(scope or "").strip().lower()
        if target_scope not in ("local", "lan"):
            lan_sdir = root_bot._scope_session_dir("lan")
            if session_path and Path(session_path).expanduser().resolve().is_relative_to(lan_sdir):
                target_scope = "lan"
            elif root_bot._find_session_file_in_dir(lan_sdir, clean_id, session_path) is not None and root_bot._find_session_file_in_dir(root_bot._scope_session_dir("local"), clean_id, session_path) is None:
                target_scope = "lan"
            else:
                target_scope = self.access_scope or "local"
        sdir = root_bot._scope_session_dir(target_scope)
        names_file = sdir / "lantern-session-names.json"
        with root_bot.lock:
            names = root_bot._load_session_names(target_scope)
            if clean_id:
                if clean_name:
                    names[clean_id] = clean_name
                else:
                    names.pop(clean_id, None)
            if session_path:
                stem = Path(session_path).stem
                if clean_name:
                    names[stem] = clean_name
                else:
                    names.pop(stem, None)
            self._atomic_write_text(names_file, json.dumps(names, ensure_ascii=False, indent=2) + "\n")
        list_sc = str(viewer_scope or scope or self.access_scope or "local").strip().lower()
        try:
            root_bot._raw_emit({"type": "chat_sessions_changed", "sessionId": clean_id})
        except Exception:
            pass
        return {
            "ok": True,
            "sessionId": clean_id,
            "name": clean_name,
            "sessions": root_bot.list_sessions(scope=list_sc, current_bot=self),
        }

    def delete_session(
        self,
        session_id: str,
        *,
        session_path: str = "",
        scope: Optional[str] = None,
        viewer_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete a saved session JSONL file (and its custom name) from session_dir."""
        root_bot = self._parent_bot or self
        clean_id = str(session_id or "").strip()
        target_scope = str(scope or "").strip().lower()
        lan_sdir = root_bot._scope_session_dir("lan")
        local_sdir = root_bot._scope_session_dir("local")
        if target_scope not in ("local", "lan"):
            if session_path and Path(session_path).expanduser().resolve().is_relative_to(lan_sdir):
                target_scope = "lan"
            elif root_bot._find_session_file_in_dir(lan_sdir, clean_id, session_path) is not None and root_bot._find_session_file_in_dir(local_sdir, clean_id, session_path) is None:
                target_scope = "lan"
            else:
                target_scope = self.access_scope or "local"
        sdir = root_bot._scope_session_dir(target_scope)
        names_file = sdir / "lantern-session-names.json"
        cur_sid = self.current_session_id()
        was_current = bool(clean_id and cur_sid and clean_id == cur_sid)
        deleted_files: list[str] = []
        with root_bot.lock:
            candidates: set[Path] = set()
            if session_path:
                try:
                    cp = Path(session_path).expanduser().resolve()
                    cp.relative_to(sdir)
                    if cp.is_file() and cp.suffix.lower() == ".jsonl":
                        candidates.add(cp)
                except Exception:
                    pass
            if clean_id and sdir.is_dir():
                found_fp = root_bot._find_session_file_in_dir(sdir, clean_id, session_path)
                if found_fp and found_fp.is_file():
                    candidates.add(found_fp)
                for fp in sdir.glob("*.jsonl"):
                    if fp.stem == clean_id or fp.stem.endswith(f"_{clean_id}"):
                        candidates.add(fp.resolve())
            for fp in candidates:
                try:
                    if fp.is_file():
                        fp.unlink()
                        deleted_files.append(str(fp))
                except Exception:
                    pass
            names = root_bot._load_session_names(target_scope)
            changed_names = False
            for k in list(names.keys()):
                if k == clean_id or (session_path and k == Path(session_path).stem):
                    names.pop(k, None)
                    changed_names = True
            if changed_names:
                try:
                    self._atomic_write_text(names_file, json.dumps(names, ensure_ascii=False, indent=2) + "\n")
                except Exception:
                    pass
            # Also unshare if it was shared
            reg = root_bot.shared_sessions()
            if clean_id in reg:
                reg.pop(clean_id, None)
                root_bot._save_shared_sessions(reg)
            for bkey, bsid in list(root_bot._shared_bindings.items()):
                if bsid == clean_id:
                    root_bot._shared_bindings.pop(bkey, None)
            root_bot._shared_bots.pop(clean_id, None)

        new_state = None
        if was_current:
            new_state = self.new_session(self.access_scope, skip_if_empty=False)
        list_sc = str(viewer_scope or scope or self.access_scope or "local").strip().lower()
        try:
            root_bot._raw_emit({"type": "chat_sessions_changed", "sessionId": clean_id})
        except Exception:
            pass
        return {
            "ok": True,
            "deletedSessionId": clean_id,
            "deletedFiles": deleted_files,
            "wasCurrent": was_current,
            "state": new_state,
            "sessions": root_bot.list_sessions(scope=list_sc, current_bot=self),
        }

    @staticmethod
    def _clean_user_preview_text(raw_txt: str) -> str:
        req_m = re.search(r"<user_request>\s*([\s\S]*?)\s*</user_request>", raw_txt)
        body = (req_m.group(1) if req_m else raw_txt).strip()
        body = re.sub(r"<skill_invocation[\s\S]*?</skill_invocation>", "", body).strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if not lines:
            return ""
        first = lines[0]
        # Clean repetitive skill preamble like "Trước khi thực hiện, hãy đọc skill liên quan trong: C:\...\skill-name"
        skill_m = re.match(
            r"^(?:Trước khi thực hiện,?\s*hãy đọc skill[^:]*:|Before executing,?\s*read[^:]*:)\s*([^\r\n]+)$",
            first,
            re.IGNORECASE,
        )
        if skill_m:
            raw_path = skill_m.group(1).strip().strip("\"'")
            parts = [p for p in re.split(r"[\\/]+", raw_path) if p and p.lower() != "skill.md"]
            skill_tag = parts[-1] if parts else "skill"
            if len(lines) > 1:
                return f"[{skill_tag}] {lines[1]}"[:84]
            return f"[Workflow: {skill_tag}]"[:84]
        return first[:84]

    def _scan_scope_sessions(
        self,
        target_scope: str,
        *,
        current_sid: str = "",
        active_file: Optional[str] = None,
        shared_reg: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        root_bot = self._parent_bot or self
        eff = "lan" if str(target_scope or "").strip().lower() == "lan" else "local"
        sdir = root_bot._scope_session_dir(eff)
        lan_cwd_norm = os.path.normcase(str(root_bot._scope_cwd("lan")))
        custom_names = root_bot._load_session_names(eff)
        shared_map = shared_reg if shared_reg is not None else (root_bot.shared_sessions() if eff == "local" else {})

        busy_session_ids: set[str] = set()
        active_session_ids: set[str] = set()
        for bot_inst in root_bot._all_bot_instances():
            if bot_inst.access_scope != eff:
                continue
            bsid = bot_inst.current_session_id()
            if bsid:
                active_session_ids.add(bsid)
                if bot_inst.streaming or bot_inst._turn_in_progress:
                    busy_session_ids.add(bsid)

        results: list[dict[str, Any]] = []
        try:
            if not sdir.is_dir():
                return results
            files = sorted(
                sdir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
                reverse=True,
            )
            seen_ids: dict[str, dict[str, Any]] = {}
            for fpath in files[:60]:
                try:
                    if ".corrupted-" in fpath.name:
                        continue
                    stat = fpath.stat()
                    if stat.st_size == 0 and fpath.stem not in shared_map:
                        continue
                    resolved_str = str(fpath.resolve())
                    cache_key = (resolved_str, stat.st_mtime, stat.st_size)
                    cached_data = root_bot._session_file_cache.get(cache_key)
                    if cached_data is not None:
                        session_id = cached_data["session_id"]
                        preview = cached_data["preview"]
                        is_native_pi = cached_data["is_native_pi"]
                        msg_count = cached_data["msg_count"]
                        header_cwd = cached_data["header_cwd"]
                    else:
                        preview = ""
                        session_id = fpath.stem
                        is_native_pi = False
                        msg_count = 0
                        header_cwd = ""
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
                                            if obj.get("cwd"):
                                                header_cwd = os.path.normcase(str(obj["cwd"]))
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
                                            preview = self._clean_user_preview_text(txt)
                                except Exception:
                                    pass
                        root_bot._session_file_cache[cache_key] = {
                            "session_id": session_id,
                            "preview": preview,
                            "is_native_pi": is_native_pi,
                            "msg_count": msg_count,
                            "header_cwd": header_cwd,
                        }
                    # Prevent LAN workspace sessions from leaking into local directory scan
                    if eff == "local" and header_cwd and header_cwd == lan_cwd_norm:
                        continue
                    is_cur = bool(
                        (current_sid and session_id == current_sid)
                        or (active_file and Path(active_file).resolve() == fpath.resolve())
                    )
                    custom_title = custom_names.get(session_id) or custom_names.get(fpath.stem) or ""
                    display_title = custom_title or preview or fpath.stem
                    is_shared = bool(eff == "local" and session_id in shared_map)
                    entry = {
                        "id": session_id,
                        "name": display_title,
                        "label": display_title,
                        "customName": bool(custom_title),
                        "preview": preview,
                        "path": resolved_str,
                        "updatedAt": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                        "current": is_cur,
                        "busy": session_id in busy_session_ids,
                        "activeInTab": session_id in active_session_ids,
                        "messageCount": msg_count,
                        "sessionScope": eff,
                        "shared": is_shared,
                        "_isNative": is_native_pi,
                    }
                    if session_id in seen_ids:
                        existing = seen_ids[session_id]
                        if custom_title:
                            existing["name"] = custom_title
                            existing["label"] = custom_title
                            existing["customName"] = True
                        elif not existing["name"] or existing["name"] == existing["id"]:
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
                        if is_shared:
                            existing["shared"] = True
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

    def list_sessions(
        self,
        scope: Optional[str] = None,
        *,
        include_other: bool = True,
        current_bot: Optional["LanternBotManager"] = None,
    ) -> list[dict[str, Any]]:
        """List sessions visible to `scope` ('local' or 'lan'):
        - scope='local': all localhost sessions + all LAN sessions labeled '[Lan]-<name>'.
        - scope='lan': all LAN sessions + localhost sessions explicitly shared in lantern-shared.json.
        """
        root_bot = self._parent_bot or self
        eff_scope = "lan" if str(scope or self.access_scope or "local").strip().lower() == "lan" else "local"
        viewer = current_bot or self
        current_sid = viewer.current_session_id()
        active_file = viewer._saved_session_file()
        shared_map = root_bot.shared_sessions()

        own_list = root_bot._scan_scope_sessions(
            eff_scope,
            current_sid=current_sid,
            active_file=active_file,
            shared_reg=shared_map,
        )
        if not include_other:
            return own_list

        if eff_scope == "local":
            lan_list = root_bot._scan_scope_sessions(
                "lan",
                current_sid=current_sid,
                active_file=active_file,
                shared_reg={},
            )
            for item in lan_list:
                raw_lbl = str(item.get("label") or item.get("name") or item.get("id") or "")
                item["label"] = raw_lbl if raw_lbl.startswith("[Lan]-") else f"[Lan]-{raw_lbl}"
                item["sessionScope"] = "lan"
                item["shared"] = False
            return own_list + lan_list

        # eff_scope == "lan": include shared localhost sessions
        if not shared_map:
            return own_list
        local_all = root_bot._scan_scope_sessions(
            "local",
            current_sid=current_sid,
            active_file=active_file,
            shared_reg=shared_map,
        )
        shared_local = [item for item in local_all if item.get("id") in shared_map or item.get("shared")]
        for item in shared_local:
            item["sessionScope"] = "local"
            item["shared"] = True
        return shared_local + own_list

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
        def _scoped_emit(payload: dict[str, Any]) -> None:
            enriched = dict(payload)
            enriched.setdefault("runtimeId", self.runtime_id)
            root_bot = self._parent_bot or self
            cur_sid = self._active_turn_session_id or self.current_session_id()
            if cur_sid:
                enriched.setdefault("sessionId", cur_sid)
            is_shared_rt = bool(
                cur_sid
                and (
                    self in root_bot._shared_bots.values()
                    or cur_sid in root_bot._shared_bindings.values()
                    or (self.access_scope == "local" and cur_sid in root_bot.shared_sessions())
                )
            )
            if is_shared_rt:
                enriched.setdefault("sharedSessionId", cur_sid)
            if self.client_session_id and not self.client_session_id.startswith("shared_"):
                enriched.setdefault("clientSessionId", self.client_session_id)
            emit(enriched)
        self.emit = _scoped_emit
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
                LanternBotManager._atomic_write_text(path, "\n".join(valid_lines) + "\n")
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
                    self._atomic_write_text(self.state_path, json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
            except Exception:
                pass

    def _saved_session_file(self) -> str:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            value = str(raw.get("sessionFile") or "").strip()
            sid = str(raw.get("sessionId") or "").strip()
            if not value:
                return ""
            path = Path(value).expanduser().resolve()
            path.relative_to(self.session_dir)
            if path.suffix.lower() != ".jsonl" or not path.is_file():
                return ""
            # Check if this is a Lantern-managed JSONL file or a child tab bot
            is_lantern_jsonl = False
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    first_line = fh.readline().strip()
                if first_line:
                    hdr = json.loads(first_line)
                    if isinstance(hdr, dict) and hdr.get("lantern"):
                        is_lantern_jsonl = True
            except Exception:
                pass
            if self.client_session_id or is_lantern_jsonl:
                if not self._session_messages:
                    loaded = self._load_messages_from_jsonl(path)
                    if loaded:
                        self._session_messages = loaded
                        self._needs_history_hydration = True
                        self._switched_session_override = {
                            "sessionId": sid or path.stem,
                            "sessionFile": str(path),
                        }
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

    def _append_message_to_session_jsonl(
        self,
        msg: dict[str, Any],
        *,
        target_sid: str = "",
        target_file: Optional[Path] = None,
    ) -> None:
        if not isinstance(msg, dict):
            return
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            return
        with self.lock:
            msg_struct = extract_message_structured(msg)
            if role == "assistant" and not msg_struct["text"] and not msg_struct["thinking"] and not msg_struct["tools"] and not msg.get("errorMessage"):
                return
            cur_sid = self.current_session_id()
            pinned_sid = str(target_sid or self._active_turn_session_id or cur_sid or "").strip()
            same_session_in_memory = bool(not pinned_sid or not cur_sid or pinned_sid == cur_sid)
            if same_session_in_memory and self._session_messages:
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
            elif same_session_in_memory:
                self._session_messages.append(dict(msg))

            sid = pinned_sid or str((self._switched_session_override or {}).get("sessionId") or self.last_state.get("sessionId") or "").strip()
            safe_sid = re.sub(r"[^A-Za-z0-9._-]+", "-", sid).strip("-") if sid else ""
            sdir = self._scope_session_dir(self._active_turn_scope)
            jsonl_path = target_file or self._active_turn_session_file or ((sdir / f"{safe_sid}.jsonl").resolve() if safe_sid else self._resolve_session_jsonl_path())
            if not jsonl_path:
                return
            if jsonl_path.is_file():
                try:
                    with jsonl_path.open("r", encoding="utf-8", errors="ignore") as rfh:
                        first_line = rfh.readline().strip()
                    if "\"type\":\"session\"" in first_line.replace(" ", "") and "version" in first_line and not first_line.endswith("\"lantern\":true}"):
                        # Native Pi CLI session file with timestamp_uuid stem: write to <safe_sid>.jsonl mirror instead
                        if "_" in jsonl_path.stem and safe_sid:
                            jsonl_path = (sdir / f"{safe_sid}.jsonl").resolve()
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
                sid = str(pinned_sid or self.last_state.get("sessionId") or jsonl_path.stem)
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
                            "cwd": str(self._scope_cwd(self._active_turn_scope)),
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
        with self.lock:
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
            serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            try:
                self._atomic_write_text(self.state_path, serialized)
                if session_file and self.latest_state_path != self.state_path:
                    self._atomic_write_text(self.latest_state_path, serialized)
            except Exception:
                pass

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
        if Path(pi).suffix.lower() == ".py":
            prefix = [sys.executable, "-u", pi]
        elif os.name == "nt" and Path(pi).suffix.lower() in {".cmd", ".bat"}:
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
            if Path(pi).suffix.lower() == ".py":
                prefix = [sys.executable, "-u", pi]
            elif os.name == "nt":
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
            child_env["LANTERN_PI_PROCESS_SCOPE"] = self.access_scope
            child_env["LANTERN_PI_PROCESS_TOOLS"] = json.dumps(list(self.bot_config.access_policy(self.access_scope).tools))

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
                    t_name = str(event.get("toolName") or event.get("name") or "tool")
                    t_args = event.get("args") or event.get("arguments") or {}
                    if isinstance(t_args, dict) and t_name in ("read", "edit", "write"):
                        raw_p = str(t_args.get("path") or t_args.get("file_path") or t_args.get("target") or "").strip()
                        if raw_p:
                            self._on_markdown_tool_target(raw_p, is_write=t_name in ("edit", "write"))
                    existing_call_ids = {t.get("id") for t in self._turn_stream_tools if "result" not in t and t.get("id")}
                    if not tc_id or tc_id not in existing_call_ids:
                        self._turn_stream_tools.append({
                            "id": tc_id,
                            "name": t_name,
                            "arguments": t_args,
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
                turn_sid_for_event = self._active_turn_session_id or self.current_session_id()
                self.emit({"type": "chat_bot_event", "event": event, "sessionId": turn_sid_for_event})
                if typ in ("agent_settled", "agent_end") or (typ == "turn_end" and not self.streaming):
                    self._active_turn_session_id = ""
                    self._active_turn_session_file = None
        except (ValueError, OSError):
            pass
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

    def _lock_extra_markdown_rel(self, rel: str) -> None:
        """Ensure baseline and lock an additional Markdown file (attached or tool-targeted)
        so open browser tabs lock the page and receive live diff updates."""
        if not rel:
            return
        ensure_fn = getattr(self.work_store, "ensure_baseline", None)
        if callable(ensure_fn):
            try:
                ensure_fn(rel)
            except Exception:
                pass
        with self.turn_lock:
            if rel == self.turn_rel or rel in self._turn_extra_locked_rels:
                return
            try:
                cur_hash = self.work_store.peek_hash(rel)
                turn = self.work_store.begin_turn(rel, cur_hash)
                self._turn_extra_locked_rels[rel] = str((turn or {}).get("hash") or "") or None
                self.emit({
                    "type": "chat_work_locked",
                    "path": rel,
                    "locked": True,
                })
            except Exception:
                pass

    def _on_markdown_tool_target(self, raw_path: str, *, is_write: bool = False) -> None:
        """Called when Pi starts a read/edit/write tool call on a path.
        Guarantees md_temp baseline exists BEFORE Pi edits even an unopened, unattached .md file."""
        md_suffixes = getattr(self.work_store, "suffixes", {".md", ".markdown"})
        try:
            cand = Path(raw_path)
            if not cand.is_absolute():
                cand = (self.root / cand).resolve()
            else:
                cand = cand.resolve()
            if cand.suffix.lower() not in md_suffixes:
                return
            rel = cand.relative_to(self.root).as_posix()
            if rel == ".lantern_uploads" or rel.startswith(".lantern_uploads/"):
                return
            if not cand.is_file():
                return
            ensure_fn = getattr(self.work_store, "ensure_baseline", None)
            if callable(ensure_fn):
                ensure_fn(rel)
            if is_write:
                self._lock_extra_markdown_rel(rel)
        except Exception:
            pass

    def _pre_ensure_prompt_markdown_baselines(self, raw_message: str) -> None:
        """Scan user prompt text for any existing project .md/.markdown paths and ensure
        their md_temp baseline is snapshotted before Pi begins its turn."""
        if not raw_message:
            return
        ensure_fn = getattr(self.work_store, "ensure_baseline", None)
        if not callable(ensure_fn):
            return
        md_suffixes = getattr(self.work_store, "suffixes", {".md", ".markdown"})
        for m in re.finditer(r"([A-Za-z0-9_./\\-]+?\.(?:md|markdown))\b", raw_message, re.IGNORECASE):
            token = m.group(1).strip().strip("\"'`()")
            if not token:
                continue
            try:
                cand = (self.root / token.replace("\\", "/").lstrip("/")).resolve()
                if cand.suffix.lower() not in md_suffixes or not cand.is_file():
                    continue
                rel = cand.relative_to(self.root).as_posix()
                if rel == ".lantern_uploads" or rel.startswith(".lantern_uploads/"):
                    continue
                ensure_fn(rel)
            except Exception:
                continue

    def _emit_work_update(self, *, final: bool) -> None:
        with self.turn_lock:
            rel = self.turn_rel
            extra_rels = list(self._turn_extra_locked_rels.keys())
            if not rel and not extra_rels:
                return
            if not final:
                if rel:
                    try:
                        current_hash = self.work_store.peek_hash(rel)
                        if current_hash != self.turn_last_hash:
                            self.turn_last_hash = current_hash
                            self.emit({
                                "type": "chat_work_changed",
                                "path": rel,
                                "hash": current_hash,
                                "workHash": current_hash,
                                "final": False,
                            })
                    except Exception as exc:
                        self.emit({"type": "chat_work_error", "path": rel, "error": str(exc), "final": False})
                for erel in extra_rels:
                    try:
                        ehash = self.work_store.peek_hash(erel)
                        if ehash != self._turn_extra_locked_rels.get(erel):
                            self._turn_extra_locked_rels[erel] = ehash
                            self.emit({
                                "type": "chat_work_changed",
                                "path": erel,
                                "hash": ehash,
                                "workHash": ehash,
                                "final": False,
                            })
                    except Exception:
                        pass
                return

            # final == True: unlock and broadcast final update for primary + extra locked .md files
            for erel in extra_rels:
                self._turn_extra_locked_rels.pop(erel, None)
                try:
                    eres = self.work_store.end_turn(erel)
                    efinal_hash = eres.get("hash")
                    self.emit({
                        "type": "chat_work_locked",
                        "path": erel,
                        "locked": False,
                    })
                    self.emit({
                        "type": "chat_work_changed",
                        "path": erel,
                        "hash": efinal_hash,
                        "workHash": efinal_hash,
                        "final": True,
                    })
                except Exception:
                    self.emit({"type": "chat_work_locked", "path": erel, "locked": False})

            if not rel:
                return

            try:
                result = self.work_store.end_turn(rel)
            except Exception as exc:
                self.emit({"type": "chat_work_locked", "path": rel, "locked": False})
                self.emit({"type": "chat_work_error", "path": rel, "error": str(exc), "final": True})
                self.turn_rel = None
                self.turn_last_hash = None
                return

            self.turn_rel = None
            self.turn_last_hash = None
            final_hash = result.get("hash")
            self.emit({
                "type": "chat_work_locked",
                "path": rel,
                "locked": False,
            })
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
        response = self.request({"type": "get_state"}, timeout=8.0)
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
        with self.lock:
            if self._switched_session_override and self._session_messages and not self.streaming:
                return self._coalesce_transcript_list(self._session_messages)
        rpc_msgs: list[dict[str, Any]] = []
        try:
            with self.lock:
                proc_running = self.proc is not None and self.proc.poll() is None
            if proc_running or not self._session_messages:
                response = self.request({"type": "get_messages"}, timeout=6.0)
            else:
                response = {}
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

    def get_messages_page(
        self,
        *,
        before_index: Optional[int] = None,
        limit_messages: int = 24,
        max_bytes: int = 512_000,
        tool_preview_chars: int = 1200,
    ) -> dict[str, Any]:
        """Return a bounded slice of conversation history (by both message count and byte budget)
        with oversized tool outputs replaced by lightweight previews in the transport copy only.
        Never mutates self._session_messages or disk JSONL."""
        all_msgs = self.get_messages()
        total = len(all_msgs)
        end_idx = total if before_index is None else max(0, min(total, int(before_index)))
        limit_messages = max(1, min(100, int(limit_messages or 24)))
        max_bytes = max(32_000, min(4_000_000, int(max_bytes or 512_000)))
        tool_preview_chars = max(200, int(tool_preview_chars or 1200))

        collected: list[dict[str, Any]] = []
        used_bytes = 0
        start_idx = end_idx

        for idx in range(end_idx - 1, -1, -1):
            raw_m = all_msgs[idx]
            if not isinstance(raw_m, dict):
                continue
            parsed = extract_message_structured(raw_m)
            role = str(parsed.get("role") or raw_m.get("role") or "assistant")
            text_val = str(parsed.get("text") or "")
            thinking_val = str(parsed.get("thinking") or "")
            text_truncated = False
            full_text_len = len(text_val)
            if full_text_len > 80_000:
                text_val = text_val[:80_000] + f"\n\n… [Preview truncated at 80,000 / {full_text_len:,} chars]"
                text_truncated = True
            if len(thinking_val) > 40_000:
                thinking_val = thinking_val[:40_000] + "\n… [Thinking preview truncated]"

            tools_out: list[dict[str, Any]] = []
            for t_idx, t in enumerate(parsed.get("tools") or []):
                t_copy = dict(t)
                if "result" in t_copy:
                    res_str = str(t_copy.get("result") or "")
                    full_len = len(res_str)
                    if full_len > tool_preview_chars:
                        t_copy["result"] = res_str[:tool_preview_chars]
                        t_copy["truncated"] = True
                        t_copy["fullLength"] = full_len
                        t_copy["msgIndex"] = idx
                        t_copy["toolIndex"] = t_idx
                else:
                    args_str = json.dumps(t_copy.get("arguments") or {}, ensure_ascii=False)
                    if len(args_str) > tool_preview_chars:
                        t_copy["arguments"] = args_str[:tool_preview_chars] + "… [truncated]"
                tools_out.append(t_copy)

            view_msg: dict[str, Any] = {
                "role": role,
                "text": text_val,
                "thinking": thinking_val,
                "toolCalls": tools_out,
                "subagents": parsed.get("subagents") or [],
                "_msgIndex": idx,
            }
            if text_truncated:
                view_msg["textTruncated"] = True
                view_msg["fullTextLength"] = full_text_len
            if isinstance(raw_m.get("usage"), dict):
                view_msg["usage"] = raw_m["usage"]
            if isinstance(raw_m.get("context"), dict):
                view_msg["context"] = raw_m["context"]
            elif role == "user":
                raw_content = str(raw_m.get("content") or raw_m.get("text") or "")
                if "<lantern_context>" in raw_content:
                    view_msg["content"] = raw_content[:80_000]

            item_bytes = len(json.dumps(view_msg, ensure_ascii=False).encode("utf-8"))
            if collected and (len(collected) >= limit_messages or (used_bytes + item_bytes) > max_bytes):
                break
            collected.append(view_msg)
            used_bytes += item_bytes
            start_idx = idx

        collected.reverse()
        return {
            "messages": collected,
            "totalMessages": total,
            "startIndex": start_idx,
            "oldestIndex": start_idx,
            "endIndex": end_idx,
            "hasMoreOlder": start_idx > 0,
            "olderCount": start_idx,
            "pageBytes": used_bytes,
        }

    def get_tool_output_full(self, msg_index: int, tool_index: int = 0) -> dict[str, Any]:
        """Fetch the full unabbreviated tool output or message text for a specific message/tool index on demand."""
        all_msgs = self.get_messages()
        if msg_index < 0 or msg_index >= len(all_msgs):
            raise IndexError("Message index out of range")
        raw_m = all_msgs[msg_index]
        parsed = extract_message_structured(raw_m)
        tools = parsed.get("tools") or []
        if 0 <= tool_index < len(tools):
            target_tool = tools[tool_index]
            res_val = str(target_tool.get("result") or "")
            return {
                "ok": True,
                "msgIndex": msg_index,
                "toolIndex": tool_index,
                "name": target_tool.get("name", "tool"),
                "result": res_val,
                "content": res_val,
                "isError": bool(target_tool.get("isError")),
            }
        return {
            "ok": True,
            "msgIndex": msg_index,
            "toolIndex": tool_index,
            "text": str(parsed.get("text") or ""),
        }

    def rerun_from_turn(
        self,
        turn_index: int,
        message: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        work_hash: Optional[str] = None,
        scope: str = "local",
    ) -> dict[str, Any]:
        """Re-run the user prompt corresponding to turn_index (an assistant or user turn).
        Truncates session history to right before that user turn, resets Pi in-memory session
        with history hydration, and dispatches the prompt fresh."""
        all_msgs = self.get_messages()
        idx = max(0, min(len(all_msgs) - 1, int(turn_index))) if all_msgs else -1
        user_idx = idx
        while user_idx >= 0 and str(all_msgs[user_idx].get("role") or "") != "user":
            user_idx -= 1
        prompt_text = str(message or "").strip()
        extracted_ctx = context if isinstance(context, dict) else {}
        if user_idx >= 0:
            raw_u = all_msgs[user_idx]
            parsed_u = extract_message_structured(raw_u)
            raw_body = str(parsed_u.get("text") or raw_u.get("content") or "")
            req_m = re.search(r"<user_request>\s*([\s\S]*?)\s*</user_request>", raw_body)
            if not prompt_text:
                prompt_text = (req_m.group(1).strip() if req_m else raw_body).strip()
            if not extracted_ctx:
                ctx_m = re.search(r"<lantern_context>\s*([\s\S]*?)\s*</lantern_context>", raw_body)
                if ctx_m:
                    cblock = ctx_m.group(1)
                    km = re.search(r"kind:\s*([^\r\n]+)", cblock)
                    pm = re.search(r"(?:logicalPath|path):\s*([^\r\n]+)", cblock)
                    if km:
                        extracted_ctx["kind"] = km.group(1).strip()
                    if pm:
                        extracted_ctx["path"] = pm.group(1).strip()
        if not prompt_text:
            raise ValueError("Cannot determine user prompt text to re-run")

        keep_msgs = list(all_msgs[:user_idx]) if user_idx > 0 else []
        sdir = self._scope_session_dir(scope)
        cur_sid = str((self._switched_session_override or {}).get("sessionId") or self.last_state.get("sessionId") or f"session-{int(time.time())}").strip()
        safe_sid = re.sub(r"[^A-Za-z0-9._-]+", "-", cur_sid).strip("-") or "default-session"
        jsonl_path = (sdir / f"{safe_sid}.jsonl").resolve()

        with self.lock:
            self._session_messages = list(keep_msgs)
            self._needs_history_hydration = bool(keep_msgs)
            self._switched_session_override = {
                "sessionId": cur_sid,
                "sessionFile": str(jsonl_path),
            }
            try:
                sdir.mkdir(parents=True, exist_ok=True)
                lines_out: list[str] = [
                    json.dumps({
                        "type": "session",
                        "version": 3,
                        "id": cur_sid,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "cwd": str(self._scope_cwd(scope)),
                        "lantern": True,
                    }, ensure_ascii=False, separators=(",", ":"))
                ]
                prev_id = None
                for m in keep_msgs:
                    eid = uuid4().hex[:8]
                    lines_out.append(json.dumps({
                        "type": "message",
                        "id": eid,
                        "parentId": prev_id,
                        "sessionId": cur_sid,
                        "timestamp": int(time.time() * 1000),
                        "role": str(m.get("role") or "assistant"),
                        "content": m.get("content", m.get("text", "")),
                        "message": m,
                    }, ensure_ascii=False, separators=(",", ":")))
                    prev_id = eid
                self._atomic_write_text(jsonl_path, "\n".join(lines_out) + "\n")
            except Exception:
                pass
        try:
            if not self.argv_override:
                self.request({"type": "new_session"}, timeout=4.0)
        except Exception:
            pass
        return self.prompt(prompt_text, extracted_ctx, work_hash=work_hash, scope=scope)

    def available_models(self, scope: str = "local") -> list[dict[str, Any]]:
        root_bot = self._parent_bot or self
        with self.lock:
            proc_running = self.proc is not None and self.proc.poll() is None
        if not proc_running and scope in root_bot._cached_models and root_bot._cached_models[scope]:
            prefs = self._load_prefs()
            fav_set = set(str(x) for x in (prefs.get("favorites") or []))
            cached_out = []
            for item in root_bot._cached_models[scope]:
                c_item = dict(item)
                c_item["favorite"] = f"{c_item.get('provider', '')}/{c_item.get('id', '')}" in fav_set
                cached_out.append(c_item)
            return cached_out
        response = self.request({"type": "get_available_models"}, timeout=8.0)
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
        root_bot._cached_models[scope] = [dict(x) for x in selected]
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
            self._needs_history_hydration = False
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

    def fork_session(
        self,
        scope: str = "local",
        *,
        upto_index: Optional[int] = None,
        source_session_path: Optional[str] = None,
        custom_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fork the current (or specified) session into a new branch, optionally at a specific checkpoint turn."""
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
        sdir = self._scope_session_dir(scope)
        if source_session_path:
            cand = Path(source_session_path).expanduser().resolve()
            if not cand.is_file():
                cand = (sdir / Path(source_session_path).name).resolve()
            raw_msgs = self._load_messages_from_jsonl(cand) if cand.is_file() else []
            prior_messages = self._coalesce_transcript_list(raw_msgs)
        else:
            prior_messages = self.get_messages() or list(self._session_messages)

        if upto_index is not None:
            try:
                cut = int(upto_index)
                if cut >= 0:
                    prior_messages = list(prior_messages[: cut + 1])
            except (TypeError, ValueError):
                pass

        fork_sid = f"fork-{int(time.time())}-{uuid4().hex[:6]}"
        fork_path = sdir / f"{fork_sid}.jsonl"
        used_custom_fork = True
        if upto_index is None and not source_session_path and self.argv_override:
            try:
                self.request({"type": "fork_session"}, timeout=3.0)
                self._switched_session_override = None
                self._needs_history_hydration = False
                used_custom_fork = False
            except Exception:
                used_custom_fork = True

        if used_custom_fork:
            sdir.mkdir(parents=True, exist_ok=True)
            lines_out: list[str] = []
            header = {
                "type": "session",
                "version": 3,
                "id": fork_sid,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "cwd": str(self._scope_cwd(scope)),
                "lantern": True,
            }
            lines_out.append(json.dumps(header, ensure_ascii=False, separators=(",", ":")))
            prev_id = None
            for m in prior_messages:
                eid = uuid4().hex[:8]
                rec = {
                    "type": "message",
                    "id": eid,
                    "parentId": prev_id,
                    "sessionId": fork_sid,
                    "timestamp": int(time.time() * 1000),
                    "role": str(m.get("role") or "assistant"),
                    "content": m.get("content", m.get("text", "")),
                    "message": m,
                }
                prev_id = eid
                lines_out.append(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
            self._atomic_write_text(fork_path, "\n".join(lines_out) + "\n")
            with self.lock:
                self._session_messages = list(prior_messages)
                self._needs_history_hydration = bool(prior_messages)
                self._switched_session_override = {
                    "sessionId": fork_sid,
                    "sessionFile": str(fork_path),
                }
                self.last_state["sessionId"] = fork_sid
                self.last_state["sessionFile"] = str(fork_path)
                self._persist_state({
                    "sessionId": fork_sid,
                    "sessionFile": str(fork_path),
                    "model": self.last_state.get("model") or {},
                })
            try:
                if self.argv_override:
                    self.request({"type": "switch_session", "sessionFile": str(fork_path)}, timeout=2.5)
                else:
                    self.request({"type": "new_session"}, timeout=4.0)
            except Exception:
                pass
        if custom_name and custom_name.strip():
            self.rename_session(fork_sid, custom_name.strip(), session_path=str(fork_path), scope=scope)
        try:
            state = self.bootstrap_state(scope)
        except Exception:
            state = dict(self.last_state)
        if self._switched_session_override:
            state["sessionId"] = self._switched_session_override["sessionId"]
            state["sessionFile"] = self._switched_session_override["sessionFile"]
        self.emit({"type": "chat_session_changed", "state": state})
        return state

    def switch_session(self, session_path: str, scope: str = "local") -> dict[str, Any]:
        """Switch to another saved session JSONL file inside session_dir."""
        root_bot = self._parent_bot or self
        if not (self.streaming or self._turn_in_progress):
            self._emit_work_update(final=True)
            self._reset_tool_scope()
        sdir = self._scope_session_dir(scope)
        raw = str(session_path or "").strip()
        if raw:
            cand = (sdir / Path(raw).name).resolve()
            if not cand.is_file() and not raw.endswith(".jsonl"):
                cand = (sdir / f"{Path(raw).name}.jsonl").resolve()
            if not cand.is_file():
                cand = Path(raw).expanduser().resolve()
            if not cand.is_file() and sdir.is_dir():
                matches = sorted(sdir.glob(f"*{Path(raw).stem}*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
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
                mirror_cand = (sdir / f"{target_sid}.jsonl").resolve()
                if mirror_cand.is_file() and mirror_cand != cand:
                    mirror_msgs = self._load_messages_from_jsonl(mirror_cand)
                    if len(mirror_msgs) > len(loaded_msgs):
                        loaded_msgs = mirror_msgs
                with self.lock:
                    self._session_messages = loaded_msgs
                    self._needs_history_hydration = bool(loaded_msgs)
                    self._turn_stream_text.clear()
                    self._turn_stream_thinking.clear()
                    self._turn_stream_tools.clear()
                    self._turn_assistant_saved = False
                    self._switched_session_override = {
                        "sessionId": target_sid,
                        "sessionFile": str(cand),
                    }
                    if not self.last_state.get("model") and root_bot.last_state.get("model"):
                        self.last_state["model"] = dict(root_bot.last_state["model"])
                    self.last_state["sessionId"] = target_sid
                    self.last_state["sessionFile"] = str(cand)
                    self._persist_state({
                        "sessionId": target_sid,
                        "sessionFile": str(cand),
                        "model": self.last_state.get("model") or {},
                    })
                    proc_running = self.proc is not None and self.proc.poll() is None
                try:
                    if proc_running and not (self.streaming or self._turn_in_progress):
                        if self.argv_override:
                            self.request({"type": "switch_session", "sessionFile": str(cand)}, timeout=2.0)
                        else:
                            self.send_fire_and_forget({"type": "new_session"})
                except Exception:
                    pass
        with self.lock:
            has_model = bool(self.last_state.get("model"))
        if has_model:
            state = dict(self.last_state)
        else:
            try:
                state = self.bootstrap_state(scope)
            except Exception:
                state = dict(self.last_state)
        if self._switched_session_override:
            state["sessionId"] = self._switched_session_override["sessionId"]
            state["sessionFile"] = self._switched_session_override["sessionFile"]
        return state

    def reset_runtime(self, scope: str = "local") -> dict[str, Any]:
        """Force-reset the Lanbot runtime process and clear all stuck turn locks across tabs without restarting the server."""
        try:
            with self.work_store.lock:
                if hasattr(self.work_store, "turns") and isinstance(self.work_store.turns, dict):
                    self.work_store.turns.clear()
                if hasattr(self.work_store, "_write_guard"):
                    self.work_store._write_guard()
        except Exception:
            pass
        for b in self._all_bot_instances():
            try:
                if b.streaming or b._turn_in_progress:
                    b.send_fire_and_forget({"type": "abort"})
            except Exception:
                pass
            b.streaming = False
            with b.turn_lock:
                b._turn_in_progress = False
                b.turn_rel = None
                b.turn_last_hash = None
                b.steer_queue.clear()
            with b.lock:
                b._turn_stream_text.clear()
                b._turn_stream_thinking.clear()
                b._turn_stream_tools.clear()
                b._turn_assistant_saved = False
                if b._session_messages:
                    b._needs_history_hydration = True
        self._reset_tool_scope()
        self._restart_process()
        try:
            state = self.bootstrap_state(scope)
        except Exception:
            state = dict(self.last_state)
        if self._switched_session_override:
            state["sessionId"] = self._switched_session_override["sessionId"]
            state["sessionFile"] = self._switched_session_override["sessionFile"]
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
            md_suffixes = getattr(self.work_store, "suffixes", {".md", ".markdown"})
            for item in raw_attachments[:32]:
                raw_path_val = item.get("path") or item.get("rel") or item.get("name") or "" if isinstance(item, dict) else item
                item_source = str(item.get("source") or "").strip().lower() if isinstance(item, dict) else ""
                raw_str = str(raw_path_val or "").strip()
                if not raw_str:
                    continue
                if Path(raw_str).suffix.lower() in md_suffixes:
                    clean_rel = raw_str.replace("\\", "/").lstrip("/")
                    if clean_rel == ".lantern_uploads" or clean_rel.startswith(".lantern_uploads/") or item_source in {"upload", "paste", "drop", "picker"}:
                        raise ValueError(
                            f"Không xác định được file Markdown gốc cho bản upload/copy '{Path(raw_str).name}'. "
                            "Hãy đính kèm hoặc kéo thả file trực tiếp từ thư mục dự án trong Lantern."
                        )
                value = canonical(item)
                if value and value not in seen:
                    seen.add(value)
                    normalized_attachments.append(value)
            if normalized_attachments:
                result["attachments"] = normalized_attachments
        return result

    def _ensure_markdown_attachment_baselines(self, normalized: Optional[dict[str, Any]]) -> list[str]:
        """Ensure md_temp baseline exists for every Markdown (.md, .markdown) attachment
        explicitly sent in this turn, before Lanbot starts processing.
        - Preserves any existing baseline without overwriting.
        - Rejects uploaded copies (.lantern_uploads) or missing files rather than guessing.
        """
        if not isinstance(normalized, dict):
            return []
        attachments = normalized.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            return []
        md_suffixes = getattr(self.work_store, "suffixes", {".md", ".markdown"})
        ensure_fn = getattr(self.work_store, "ensure_baseline", None)
        ensured_rels: list[str] = []
        for att in attachments:
            cand = Path(str(att)).resolve()
            if cand.suffix.lower() not in md_suffixes:
                continue
            try:
                rel = cand.relative_to(self.root).as_posix()
            except ValueError as exc:
                raise ValueError(f"Markdown attachment escapes project root: {att}") from exc
            if rel == ".lantern_uploads" or rel.startswith(".lantern_uploads/"):
                raise ValueError(
                    f"Không xác định được file Markdown gốc cho bản upload/copy '{cand.name}'. "
                    "Hãy đính kèm hoặc kéo thả file trực tiếp từ thư mục dự án trong Lantern."
                )
            if not cand.exists() or not cand.is_file():
                raise ValueError(f"Không tìm thấy file Markdown gốc trong dự án: {rel}")
            if callable(ensure_fn):
                ensure_fn(rel)
                ensured_rels.append(rel)
        return ensured_rels

    @staticmethod
    def _build_history_hydration_block(messages: list[dict[str, Any]]) -> str:
        """Build a compact <conversation_history> block from prior session turns so switched
        or forked sessions retain full conversational continuity on a fresh Pi RPC session."""
        if not messages:
            return ""
        lines: list[str] = []
        recent = messages[-16:]
        for idx, m in enumerate(recent, 1):
            if not isinstance(m, dict):
                continue
            parsed = extract_message_structured(m)
            role = "User" if parsed.get("role") == "user" else "Assistant"
            raw_txt = str(parsed.get("text") or "").strip()
            ctx_m = re.search(r"<lantern_context>\s*([\s\S]*?)\s*</lantern_context>", raw_txt)
            ctx_file = ""
            if ctx_m:
                pm = re.search(r"(?:logicalPath|path):\s*([^\r\n]+)", ctx_m.group(1))
                if pm:
                    ctx_file = pm.group(1).strip()
            req_m = re.search(r"<user_request>\s*([\s\S]*?)\s*</user_request>", raw_txt)
            clean_txt = (req_m.group(1).strip() if req_m else raw_txt)[:2500]
            if clean_txt:
                ctx_tag = f" (file open during this turn: {ctx_file})" if (role == "User" and ctx_file) else ""
                lines.append(f"[Turn {idx} - {role}{ctx_tag}]:\n{clean_txt}")
        if not lines:
            return ""
        return "<conversation_history>\n" + "\n\n".join(lines) + "\n</conversation_history>"

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

        if cmd == "/reset-bot":
            state = self.reset_runtime(scope)
            self.emit({
                "type": "chat_bot_reset",
                "state": state,
                "summary": self.summary(scope),
                "models": self.available_models(scope),
                "messages": self.get_messages(),
                "sessions": self.list_sessions(scope),
            })
            return {"type": "response", "command": cmd, "success": True, "state": state}

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
            self.emit({"type": "chat_commands_changed", "skills": skills})
            if arg:
                parts_arg = arg.split(None, 1)
                q = parts_arg[0].lstrip("/").lower()
                rem_arg = parts_arg[1].strip() if len(parts_arg) > 1 else ""
                sk = next((s for s in skills if s.get("name", "").lower() == q), None)
                if sk:
                    return self._expand_skill_prompt(sk, rem_arg, context)
            if not skills:
                msg_txt = (
                    "🧰 No skills discovered yet.\n"
                    "- Run `/harness init` to scaffold starter coding skills (`/verify-loop`, `/checkpoint`, `/planner`) into `.pi/skills/`\n"
                    "- Or open **⚙ Settings → Skills Configuration** to enable global skills (`~/.pi/agent/skills`) or add custom skill paths."
                )
            else:
                lines = ["🧰 **Discovered Pi Skills** (type `/<skill-name> [instructions]` to run):"]
                for s in skills:
                    lines.append(f"- `{s.get('command')}` ({s.get('scope', 'workspace')}): {s.get('description', '')}")
                msg_txt = "\n".join(lines)
            self.emit({"type": "chat_slash_message", "command": cmd, "text": msg_txt})
            return {"type": "response", "command": cmd, "success": True, "skills": skills}

        if cmd == "/harness":
            sub = arg.strip().lower()
            if sub in ("init", "setup", "install", "scaffold"):
                res = self.scaffold_harness_skills()
                created_str = ", ".join(f"`{c}`" for c in res["created"]) if res["created"] else "none (all already present)"
                existing_str = ", ".join(f"`{e}`" for e in res["existing"]) if res["existing"] else "none"
                msg_txt = (
                    "🛠️ **Lantern Pi-Core Harness Initialized (.pi/skills/)**:\n"
                    f"- **Created**: {created_str}\n"
                    f"- **Preserved existing**: {existing_str}\n\n"
                    "You can now type `/verify-loop`, `/checkpoint`, or `/planner` directly in chat!"
                )
                self.emit({"type": "chat_slash_message", "command": "/harness", "text": msg_txt})
                return {"type": "response", "command": "/harness", "success": True, **res}

            policy = self.bot_config.access_policy(scope)
            skills = self.discover_skills()
            mcp_servers = self.discover_mcp_servers()
            exts = self.discover_extensions()
            self.emit({"type": "chat_commands_changed", "skills": skills})
            tools_desc = "FULL (`*`)" if policy.is_full_tools else ", ".join(f"`{t}`" for t in policy.tools)
            skill_str = ", ".join(f"`{s['command']}` ({s['scope']})" for s in skills) if skills else "None (run `/harness init` to create starter skills)"
            mcp_str = ", ".join(f"`{m['name']}` ({m['source']})" for m in mcp_servers) if mcp_servers else "None configured in `.mcp.json` / `.pi/mcp.json`"
            ext_str = ", ".join(f"`{e['name']}` ({e['scope']})" for e in exts) if exts else "None"
            msg_txt = (
                f"🏮 **Lantern Pi-Core Harness Status ({scope})**:\n"
                f"- **Pi Core Runtime**: Active (`--mode rpc`)\n"
                f"- **Tool Policy**: {tools_desc}\n"
                f"- **Markdown Guard & Auto-Baseline**: Enabled (`pi_working_copy_guard.ts` + `LiveMarkdownStore`)\n"
                f"- **Discovered Skills ({len(skills)})**: {skill_str}\n"
                f"- **MCP Servers ({len(mcp_servers)})**: {mcp_str} (Policy: {'Enabled' if policy.mcp else 'Disabled'})\n"
                f"- **Pi Extensions ({len(exts)})**: {ext_str} (Policy: {'Enabled' if policy.extensions else 'Guard-only'})\n\n"
                "💡 *Tip*: Run `/harness init` to scaffold `.pi/skills/verify-loop`, `checkpoint`, and `planner`."
            )
            self.emit({"type": "chat_slash_message", "command": "/harness", "text": msg_txt})
            return {
                "type": "response",
                "command": "/harness",
                "success": True,
                "skills": skills,
                "mcpServers": mcp_servers,
                "extensions": exts,
            }

        if cmd == "/mcp":
            if arg and not arg.lower().startswith(("list", "status", "info")):
                # Pass explicit MCP task instructions to Pi core with active workspace context
                return {"_expanded_prompt": f"Use available MCP tools to fulfill this request: {arg}", "_include_context": True}
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
                "- `/harness [init|status]` — Inspect Pi Core Harness or scaffold starter skills",
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

        # Issue 16 & v7.91: Execute synchronous slash commands (/harness, /skills, /help, /mcp, etc.)
        # immediately without entering LLM streaming/busy state or requiring model bootstrap!
        if raw_message.startswith("/"):
            slash_res = self.execute_slash_command(raw_message, context=context, work_hash=work_hash, scope=scope)
            if isinstance(slash_res, dict) and "_expanded_prompt" not in slash_res:
                out_slash = dict(slash_res)
                out_slash["slashHandled"] = True
                return out_slash
            if isinstance(slash_res, dict) and "_expanded_prompt" in slash_res:
                raw_message = str(slash_res["_expanded_prompt"])
                is_slash_cmd = not bool(slash_res.get("_include_context"))
            else:
                is_slash_cmd = True
        else:
            is_slash_cmd = False

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
        normalized = {} if is_slash_cmd else self.normalize_context(context)
        if not is_slash_cmd:
            self._turn_attached_md_rels = self._ensure_markdown_attachment_baselines(normalized)
            self._pre_ensure_prompt_markdown_baselines(raw_message)
        else:
            self._turn_attached_md_rels = []

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
                if self.turn_rel or self._turn_extra_locked_rels:
                    self._emit_work_update(final=True)
                turn = None
                try:
                    turn = self.work_store.begin_turn(rel, work_hash)
                except WorkingCopyError as exc:
                    # Auto-recover if a prior turn left a stale pi_turn lock or stale work_hash
                    if getattr(exc, "details", {}).get("reason") == "pi_turn":
                        other_active = any(
                            b is not self and (b.streaming or b._turn_in_progress) and b.turn_rel == rel
                            for b in self._all_bot_instances()
                        )
                        if not other_active:
                            try:
                                self.work_store.end_turn(rel)
                            except Exception:
                                pass
                    try:
                        fresh_hash = self.work_store.peek_hash(rel)
                        turn = self.work_store.begin_turn(rel, fresh_hash)
                    except WorkingCopyError as exc2:
                        if getattr(exc2, "details", {}).get("reason") == "pi_turn":
                            # Another tab is actively editing this file; allow chat turn without locking turn_rel
                            turn = {"workingPath": str(real), "hash": None}
                        else:
                            raise RuntimeError(str(exc2)) from exc2
                if turn and turn.get("hash") is not None or not any(
                    b is not self and b.turn_rel == rel for b in self._all_bot_instances()
                ):
                    self.turn_rel = rel
                    self.turn_last_hash = str((turn or {}).get("hash") or "") or None
                    self.emit({
                        "type": "chat_work_locked",
                        "path": rel,
                        "locked": True,
                    })
                self.turn_started_at = time.monotonic()
            normalized["logicalPath"] = rel
            normalized["workingPath"] = str((turn or {}).get("workingPath") or real)
        elif not is_slash_cmd and normalized.get("path"):
            # Support Context: ON for all non-.md files (.py, .txt, .json, .csv, .html, etc.)
            if self.turn_rel or self._turn_extra_locked_rels:
                self._emit_work_update(final=True)
            real = Path(str(normalized["path"])).resolve()
            try:
                rel = real.relative_to(self.root).as_posix()
                normalized["logicalPath"] = rel
                normalized["workingPath"] = str(real)
                if normalized.get("kind") in ("unknown", "folder"):
                    normalized["kind"] = "file"
            except ValueError:
                pass
        elif self.turn_rel or self._turn_extra_locked_rels:
            self._emit_work_update(final=True)

        for att_rel in self._turn_attached_md_rels:
            self._lock_extra_markdown_rel(att_rel)

        prefs = self._load_prefs()
        if not is_slash_cmd:
            if prefs.get("customSystemPrompt"):
                normalized["customSystemPrompt"] = str(prefs["customSystemPrompt"])
            if prefs.get("customSkillPaths"):
                normalized["skillPaths"] = [s["path"] for s in self.discover_skills() if s.get("scope") == "custom"]
        wrapped = self.build_prompt(raw_message, normalized)
        rpc_message = wrapped
        with self.lock:
            if not is_slash_cmd and self._needs_history_hydration and self._session_messages:
                hist_block = self._build_history_hydration_block(self._session_messages)
                if hist_block:
                    rpc_message = f"{hist_block}\n\n{wrapped}"
                self._needs_history_hydration = False
        with self.turn_lock:
            if self._turn_in_progress:
                raise RuntimeError("LanternBot is already completing a turn")
            self._turn_in_progress = True
            self._active_turn_scope = scope
            self._active_turn_session_id = self.current_session_id()
            self._active_turn_session_file = self._resolve_session_jsonl_path(session_id=self._active_turn_session_id)
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
            try:
                response = self.request({"type": "prompt", "message": rpc_message})
            except Exception:
                if not self.argv_override:
                    # Auto-recover if Pi CLI had a corrupt in-memory session state
                    try:
                        self.request({"type": "new_session"}, timeout=4.0)
                    except Exception:
                        self._restart_process()
                    prior_without_current = list(self._session_messages[:-1]) if len(self._session_messages) > 1 else []
                    retry_msg = wrapped
                    if prior_without_current:
                        hb = self._build_history_hydration_block(prior_without_current)
                        if hb:
                            retry_msg = f"{hb}\n\n{wrapped}"
                    response = self.request({"type": "prompt", "message": retry_msg})
                else:
                    raise
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
        if not raw_message.startswith("/"):
            self._ensure_markdown_attachment_baselines(self.normalize_context(context))
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
        cur_sid = str((self._switched_session_override or {}).get("sessionId") or state.get("sessionId") or "")
        custom_names = self._load_session_names(scope)
        return {
            "running": running,
            "streaming": bool(self.streaming),
            "sessionId": cur_sid,
            "sessionName": custom_names.get(cur_sid, ""),
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
            if os.name == "nt" and proc.pid:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        timeout=2.5,
                    )
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
    {"command": "/reset-bot", "category": "config", "description": "Force-reset Lanbot runtime process and clear stuck locks"},
    {"command": "/compact", "category": "session", "description": "Compact session context via Pi core to save tokens"},
    {"command": "/fork", "category": "session", "description": "Fork current conversation into a new branch"},
    {"command": "/session", "category": "session", "description": "Switch or manage saved conversations"},
    {"command": "/thinking", "category": "config", "description": "Set Pi core thinking level (off|low|medium|high|xhigh)"},
    {"command": "/skills", "category": "skill", "description": "List discovered workspace & global skills"},
    {"command": "/harness", "category": "harness", "description": "Inspect Pi Core Harness status or scaffold starter skills (/harness init)"},
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

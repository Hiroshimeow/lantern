"""HTTP API routes for Lanbot (Lantern Chatbot) advanced features (v5).

Provides:
- GET  /api/chatbot/export              : Full unabbreviated HTML session transcript export
- GET  /api/chatbot/subagent-transcript : Reads subagent .output transcript files safely
- GET  /api/chatbot/file-index          : Fast workspace file autocomplete index for @-mentions
- GET  /api/chatbot/commands            : Lists available slash commands (built-in + workspace/global/custom skills)
- GET  /api/chatbot/prefs               : Returns current model/favorite/thinking/customSystemPrompt/skill preferences
- POST /api/chatbot/prefs               : Updates favorite models, thinking level, tool preset, customSystemPrompt, and skill paths
- POST /api/chatbot/upload              : Uploads pasted (Ctrl+V) or dragged-and-dropped images/files into <root>/.lantern_uploads/
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from lantern.pi_chat import BUILTIN_SLASH_COMMANDS

_MAX_CHATBOT_UPLOAD_BYTES = 36 * 1024 * 1024  # 36 MB JSON envelope (~25 MB binary)
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"}


def _sanitize_upload_name(raw_name: str, mime: str = "") -> str:
    base = Path(str(raw_name or "attachment")).name
    stem = _SAFE_FILENAME_RE.sub("_", Path(base).stem).strip("._-") or "attachment"
    ext = Path(base).suffix.lower()
    if not ext and mime:
        guessed = mimetypes.guess_extension(mime.split(";")[0].strip().lower())
        if guessed:
            ext = guessed.lower()
    if not ext:
        ext = ".bin"
    ext = _SAFE_FILENAME_RE.sub("", ext)
    if not ext.startswith("."):
        ext = "." + ext
    return f"{stem[:64]}{ext[:12]}"


class ChatbotRoutes:
    def _client_ip(self) -> str:
        addr = getattr(self, "client_address", None)
        if isinstance(addr, (tuple, list)) and addr:
            return str(addr[0])
        return "127.0.0.1"

    def _terminal_access(self, client_ip: str = "") -> tuple[bool, str]:
        ip = client_ip or self._client_ip()
        access = getattr(getattr(self, "app", None), "terminal_access", None)
        if access is None:
            return True, "ok"
        cookie = self.headers.get("Cookie", "") if getattr(self, "headers", None) else ""
        permitted = bool(access.permitted(ip, cookie))
        return permitted, ("ok" if permitted else "locked")

    def _chatbot_permitted(self) -> bool:
        return self._terminal_access(self._client_ip())[0]

    def _build_commands_list(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        commands: list[dict[str, Any]] = [dict(c) for c in BUILTIN_SLASH_COMMANDS]
        skills: list[dict[str, str]] = []
        bot = getattr(self.app, "bot", None)
        if bot is not None and hasattr(bot, "discover_skills"):
            try:
                skills = bot.discover_skills()
            except Exception:
                skills = []
        else:
            root = self.app.config.root.resolve()
            for skill_root in (root / ".pi" / "skills", Path.home() / ".pi" / "agent" / "skills"):
                if skill_root.is_dir():
                    try:
                        for item in sorted(skill_root.iterdir()):
                            if item.is_dir() and (item / "SKILL.md").is_file():
                                skills.append({
                                    "name": item.name,
                                    "command": f"/{item.name}",
                                    "category": "skill",
                                    "scope": "workspace",
                                    "path": str((item / "SKILL.md").resolve()),
                                    "description": f"Run skill {item.name}",
                                })
                    except Exception:
                        pass
        for sk in skills:
            cmd_name = sk.get("command") or f"/{sk.get('name', '')}"
            if cmd_name and not any(c.get("command") == cmd_name for c in commands):
                commands.append({
                    "command": cmd_name,
                    "category": "skill",
                    "scope": sk.get("scope", "workspace"),
                    "description": sk.get("description") or f"Run skill {sk.get('name', '')}",
                })
        return commands, skills

    def serve_standalone_chat(self, query: str = "") -> None:
        qs = urllib.parse.parse_qs(query or "")
        rel_path = (qs.get("path") or qs.get("p") or [""])[0].strip()
        kind = (qs.get("kind") or ["markdown" if rel_path.lower().endswith((".md", ".markdown")) else "folder"])[0].strip()
        client_sid = (qs.get("client_session") or qs.get("session") or [""])[0].strip()
        esc = self.app.files.html_escape
        title = f"Lanbot — {rel_path or self.app.config.title}"
        html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>{esc(title)}</title>
<link rel="stylesheet" href="/static/chatbot.css">
<style>
  html, body {{
    margin: 0;
    padding: 0 !important;
    width: 100%;
    height: 100dvh;
    overflow: hidden;
    background: #0b1018;
    color: #edf5ff;
  }}
  body.lantern-chat-standalone .lantern-chat-fab {{
    display: none !important;
  }}
  body.lantern-chat-standalone .lantern-chat-drawer {{
    display: flex !important;
    width: 100vw !important;
    max-width: 100vw !important;
    left: 0 !important;
    right: 0 !important;
    top: 0 !important;
    bottom: 0 !important;
    border: none !important;
    box-shadow: none !important;
  }}
  body.lantern-chat-standalone .lantern-chat-resizer,
  body.lantern-chat-standalone #lcDockBtn,
  body.lantern-chat-standalone #lcExpandBtn,
  body.lantern-chat-standalone #lcCloseBtn,
  body.lantern-chat-standalone #lcPopoutBtn {{
    display: none !important;
  }}
</style>
</head>
<body class="lantern-chat-standalone lantern-chat-open"
      data-lantern-chat-kind="{esc(kind)}"
      data-lantern-chat-path="{esc(rel_path)}"
      data-lantern-client-session="{esc(client_sid)}">
<script>
  window.APP = {{
    currentPath: {self.app.files.json_dumps(rel_path)},
    title: {self.app.files.json_dumps(self.app.config.title)},
    standaloneChat: true,
    clientSessionId: {self.app.files.json_dumps(client_sid)}
  }};
</script>
<script src="/static/chatbot.js"></script>
</body>
</html>"""
        self.send_bytes(200, html_doc.encode("utf-8"), "text/html; charset=utf-8", {"Cache-Control": "no-store"})

    def api_chatbot_export(self, query: Any = "") -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Lanbot access requires terminal unlock."})
            return
        qs = urllib.parse.parse_qs(query) if isinstance(query, str) else {}
        cid = (qs.get("clientSessionId") or qs.get("session") or [""])[0].strip()
        target_bot = self.app.bot.get_session_bot(cid) if (cid and hasattr(self.app.bot, "get_session_bot")) else self.app.bot
        html_doc = target_bot.export_session_html()
        raw = html_doc.encode("utf-8")
        filename = "lanbot-full-session-log.html"
        self.send_bytes(
            200,
            raw,
            "text/html; charset=utf-8",
            {
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    def api_chatbot_subagent_transcript(self, query: Any = "", extra_qs: Any = None) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        raw_qs = extra_qs if isinstance(extra_qs, dict) else query
        qs = urllib.parse.parse_qs(raw_qs) if isinstance(raw_qs, str) else (raw_qs if isinstance(raw_qs, dict) else {})
        raw_path = (qs.get("path") or [""])[0].strip()
        if not raw_path:
            self.send_json(400, {"error": "Missing transcript path."})
            return
        try:
            candidate = Path(raw_path).resolve()
            temp_root = Path(tempfile.gettempdir()).resolve()
            workspace_root = self.app.config.root.resolve()
            home_pi = (Path.home() / ".pi").resolve()
            allowed = (
                candidate.is_relative_to(temp_root)
                or candidate.is_relative_to(workspace_root)
                or candidate.is_relative_to(home_pi)
                or "pi-subagents" in str(candidate).replace("\\", "/")
            )
            if not allowed or not candidate.is_file():
                self.send_json(404, {"error": "Subagent transcript file not found or outside allowed roots."})
                return
            content = candidate.read_text(encoding="utf-8", errors="replace")
            self.send_json(
                200,
                {
                    "path": str(candidate),
                    "name": candidate.name,
                    "size": len(content),
                    "content": content,
                },
            )
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def api_chatbot_file_index(self, query: Any = "", extra_qs: Any = None) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        raw_qs = extra_qs if isinstance(extra_qs, dict) else query
        qs = urllib.parse.parse_qs(raw_qs) if isinstance(raw_qs, str) else (raw_qs if isinstance(raw_qs, dict) else {})
        q = (qs.get("q") or [""])[0].strip().lower()
        root = self.app.config.root.resolve()
        results: list[dict[str, Any]] = []
        skip_dirs = {".git", "node_modules", "__pycache__", ".lantern", ".lantern_uploads", ".venv", "venv", ".next", "dist"}
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".lantern")]
                rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
                if rel_dir == ".":
                    rel_dir = ""
                for fname in filenames:
                    rel_path = f"{rel_dir}/{fname}" if rel_dir else fname
                    if not q or q in rel_path.lower():
                        ext = Path(fname).suffix.lower()
                        results.append({
                            "path": rel_path,
                            "name": fname,
                            "isImage": ext in _IMAGE_EXTS,
                        })
                        if len(results) >= 80:
                            break
                if len(results) >= 80:
                    break
        except Exception:
            pass
        self.send_json(200, {"files": results})

    def api_chatbot_commands(self, _unused: Any = None) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        commands, skills = self._build_commands_list()
        self.send_json(200, {"commands": commands, "skills": skills})

    def api_chatbot_prefs_get(self) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        prefs = self.app.bot._load_prefs() if hasattr(self.app.bot, "_load_prefs") else {}
        commands, skills = self._build_commands_list()
        self.send_json(200, {"ok": True, "prefs": prefs, "skills": skills, "commands": commands})

    def api_chatbot_prefs_post(self) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        body = self.read_json()
        action = str(body.get("action") or "").strip()
        if action == "toggle_favorite_model":
            model_key = str(body.get("modelKey") or "").strip()
            parts = model_key.split("/", 1) if "/" in model_key else ["", model_key]
            self.send_json(200, self.app.bot.toggle_favorite_model(parts[0], parts[1]))
            return
        if action == "set_thinking_level":
            self.send_json(200, self.app.bot.set_thinking_level(str(body.get("level") or "medium")))
            return
        if action == "set_tool_preset":
            self.send_json(200, self.app.bot.set_tool_preset(str(body.get("preset") or "full")))
            return
        if (
            action in ("update_custom_settings", "save_settings")
            or "customSystemPrompt" in body
            or "useGlobalSkills" in body
            or "customSkillPaths" in body
        ):
            res = self.app.bot.update_custom_settings(
                custom_system_prompt=body.get("customSystemPrompt"),
                use_global_skills=body.get("useGlobalSkills"),
                custom_skill_paths=body.get("customSkillPaths"),
            )
            commands, skills = self._build_commands_list()
            res["commands"] = commands
            res["skills"] = skills
            self.send_json(200, res)
            return
        self.send_json(400, {"error": "Unsupported preference action."})

    # Legacy alias if any test calls api_chatbot_prefs directly
    def api_chatbot_prefs(self, _unused: Any = None) -> None:
        return self.api_chatbot_prefs_post()

    def api_chatbot_upload(self) -> None:
        if not self._chatbot_permitted():
            self.send_json(403, {"error": "Access denied."})
            return
        body = self.read_json(max_bytes=_MAX_CHATBOT_UPLOAD_BYTES)
        raw_items = body.get("files")
        if not isinstance(raw_items, list):
            if body.get("dataBase64") or body.get("contentBase64"):
                raw_items = [body]
            else:
                self.send_json(400, {"error": "No files provided for upload."})
                return

        root = self.app.config.root.resolve()
        day_folder = time.strftime("%Y%m%d")
        upload_dir = (root / ".lantern_uploads" / day_folder).resolve()
        try:
            upload_dir.relative_to(root)
        except ValueError:
            self.send_json(400, {"error": "Invalid upload directory."})
            return
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved_attachments: list[dict[str, Any]] = []
        ts_ms = int(time.time() * 1000)

        for idx, item in enumerate(raw_items[:16]):
            if not isinstance(item, dict):
                continue
            raw_b64 = str(item.get("dataBase64") or item.get("contentBase64") or "").strip()
            if not raw_b64:
                continue
            mime = str(item.get("type") or item.get("mime") or "").strip()
            if raw_b64.startswith("data:") and "," in raw_b64:
                header, raw_b64 = raw_b64.split(",", 1)
                if not mime and ":" in header and ";" in header:
                    mime = header.split(":", 1)[1].split(";", 1)[0].strip()
            try:
                binary = base64.b64decode(raw_b64, validate=False)
            except Exception as exc:
                self.send_json(400, {"error": f"Invalid base64 payload: {exc}"})
                return

            safe_name = _sanitize_upload_name(str(item.get("name") or f"paste-{idx + 1}"), mime)
            dest_name = f"{ts_ms}_{idx + 1}_{safe_name}"
            dest_path = (upload_dir / dest_name).resolve()
            try:
                dest_path.relative_to(root)
            except ValueError:
                self.send_json(400, {"error": "Upload path escaped workspace root."})
                return

            dest_path.write_bytes(binary)
            rel_posix = dest_path.relative_to(root).as_posix()
            ext = dest_path.suffix.lower()
            if not mime:
                mime = mimetypes.guess_type(dest_path.name)[0] or "application/octet-stream"
            is_image = ext in _IMAGE_EXTS or mime.lower().startswith("image/")
            saved_attachments.append({
                "path": rel_posix,
                "name": str(item.get("name") or safe_name),
                "size": len(binary),
                "mime": mime,
                "isImage": is_image,
                "isDir": False,
                "source": str(item.get("source") or "upload"),
                "previewUrl": "/" + urllib.parse.quote(rel_posix, safe="/"),
            })

        if not saved_attachments:
            self.send_json(400, {"error": "No valid file payloads found."})
            return

        self.send_json(200, {"ok": True, "attachments": saved_attachments})

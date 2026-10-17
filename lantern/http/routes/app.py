
import os
import platform
from typing import Any, Dict

from lantern.config import (APP_NAME, config_to_dict, normalize_animation, normalize_conflict, normalize_fit, normalize_page_limit, normalize_sort, normalize_view, write_config_file)
from lantern.media import HAS_PIL, FFMPEG, FFPROBE

class AppRoutes:
    def api_terminal_auth(self) -> None:
        access = self.app.terminal_access
        if access is None:
            self.send_json(503, {"error": "Terminal auth is not ready"})
            return
        ip = self.client_address[0]
        self.send_bytes(200, self.app.files.json_dumps({
            "required": access.required(ip),
            "authenticated": access.permitted(ip, self.headers.get("Cookie", "")),
            "configured": access.configured,
        }).encode("utf-8"), "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def api_terminal_login(self) -> None:
        access = self.app.terminal_access
        if access is None:
            self.send_json(503, {"error": "Terminal auth is not ready"}); return
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self.send_json(415, {"error": "JSON required"}); return
        data = self.read_json(max_bytes=4096)
        code, token = access.login(self.client_address[0], data.get("password"))
        if code != 200:
            message = ("Set a Terminal password on the Lantern host first" if code == 503 else
                       "Too many attempts. Try again in five minutes." if code == 429 else "Incorrect password")
            self.send_json(code, {"error": message}); return
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        self.send_bytes(200, b'{"ok":true}', "application/json; charset=utf-8", {
            "Set-Cookie": access.cookie_header(token, secure=secure),
            "Cache-Control": "no-store",
        })

    def api_terminal_logout(self) -> None:
        access = self.app.terminal_access
        if access is None:
            self.send_json(503, {"error": "Terminal auth is not ready"}); return
        token = access.cookie_token(self.headers.get("Cookie", ""))
        access.logout(token)
        self.app.ws.close_token(token)
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        self.send_bytes(200, b'{"ok":true}', "application/json; charset=utf-8", {
            "Set-Cookie": access.clear_cookie(secure=secure),
            "Cache-Control": "no-store",
        })

    def api_info(self) -> None:
        data = {
            "app": APP_NAME,
            "root": str(self.app.config.root),
            "platform": platform.platform(),
            "pillow": HAS_PIL,
            "ffmpeg": bool(FFMPEG),
            "ffprobe": bool(FFPROBE),
            "config": str(self.app.config.config_path),
            "defaults": {
                "default_sort": self.app.config.default_sort,
                "default_view": self.app.config.default_view,
                "page_limit": self.app.config.page_limit,
                "folders_first": self.app.config.folders_first,
                "search_debounce_ms": self.app.config.search_debounce_ms,
                "terminal_enabled": self.app.config.terminal_enabled,
                "terminal_max_buffer_chars": self.app.config.terminal_max_buffer_chars,
                "terminal_start_height_px": self.app.config.terminal_start_height_px,
                "terminal_mobile_extra_keys": self.app.config.terminal_mobile_extra_keys,
                "thumb_fit": self.app.config.thumb_fit,
                "folder_preview_enabled": self.app.config.folder_preview_enabled,
                "folder_preview_animation": self.app.config.folder_preview_animation,
                "upload_parallel": self.app.config.upload_parallel,
                "upload_conflict": self.app.config.upload_conflict,
            },
            "terminal": {
                "enabled": self.app.config.terminal_enabled,
                "transport": "websocket",
                "renderer": "xterm.js",
                "pty": "conpty" if os.name == "nt" else "pty",
            },
            "plugin": {
                "enabled": self.app.files.plugin_enabled(),
                "config": str(self.app.files.plugin_config_path()),
            },
        }
        self.send_json(200, data)

    def api_config_get(self) -> None:
        self.send_json(200, config_to_dict(self.app.config))

    def api_config_post(self) -> None:
        data = self.read_json()
        changed: Dict[str, Any] = {}
        if "default_sort" in data:
            self.app.config.default_sort = normalize_sort(data.get("default_sort"))
            changed["default_sort"] = self.app.config.default_sort
        if "default_view" in data:
            self.app.config.default_view = normalize_view(data.get("default_view"))
            changed["default_view"] = self.app.config.default_view
        if "page_limit" in data:
            self.app.config.page_limit = normalize_page_limit(data.get("page_limit"))
            changed["page_limit"] = self.app.config.page_limit
        if "folders_first" in data:
            self.app.config.folders_first = bool(data.get("folders_first"))
            changed["folders_first"] = self.app.config.folders_first
        if "search_debounce_ms" in data:
            try:
                self.app.config.search_debounce_ms = max(100, min(int(data.get("search_debounce_ms")), 1500))
            except Exception:
                pass
            changed["search_debounce_ms"] = self.app.config.search_debounce_ms
        if "thumb_fit" in data:
            self.app.config.thumb_fit = normalize_fit(data.get("thumb_fit"))
            changed["thumb_fit"] = self.app.config.thumb_fit
        if "folder_preview_fit" in data:
            self.app.config.folder_preview_fit = normalize_fit(data.get("folder_preview_fit"))
            changed["folder_preview_fit"] = self.app.config.folder_preview_fit
        if "folder_preview_enabled" in data:
            self.app.config.folder_preview_enabled = bool(data.get("folder_preview_enabled"))
            changed["folder_preview_enabled"] = self.app.config.folder_preview_enabled
        if "folder_preview_animation" in data:
            self.app.config.folder_preview_animation = normalize_animation(data.get("folder_preview_animation"))
            changed["folder_preview_animation"] = self.app.config.folder_preview_animation
        if "upload_conflict" in data:
            self.app.config.upload_conflict = normalize_conflict(data.get("upload_conflict"))
            changed["upload_conflict"] = self.app.config.upload_conflict
        if "upload_parallel" in data:
            try:
                self.app.config.upload_parallel = max(1, min(int(data.get("upload_parallel") or 3), 8))
            except Exception:
                pass
            changed["upload_parallel"] = self.app.config.upload_parallel
        if changed:
            write_config_file(self.app.config)
        self.send_json(200, {"ok": True, "changed": changed})

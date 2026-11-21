import os
import platform
from typing import Any, Dict

from lantern.config import (APP_NAME, config_to_dict, normalize_animation, normalize_conflict, normalize_fit, normalize_page_limit, normalize_sort, normalize_view, write_config_file)
from lantern.media import HAS_PIL, FFMPEG, FFPROBE
from lantern.system_telemetry import get_system_telemetry


class AppRoutes:
    def api_terminal_auth(self) -> None:
        access = self.app.terminal_access
        if access is None:
            self.send_json(503, {"error": "Terminal auth is not ready"})
            return
        ip = self.client_address[0]
        is_local = access.is_local(ip) if hasattr(access, "is_local") else False
        lan_sessions = access.active_lan_sessions() if hasattr(access, "active_lan_sessions") else 0
        lan_locked = bool(getattr(access, "lan_locked", False))
        self.send_bytes(200, self.app.files.json_dumps({
            "required": access.required(ip),
            "authenticated": access.permitted(ip, self.headers.get("Cookie", "")),
            "configured": access.configured,
            "isLocal": is_local,
            "lanSessions": lan_sessions if is_local else 0,
            "lanLocked": lan_locked,
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
            message = (
                "LAN access is locked by the localhost host" if code == 403 else
                "Set a Terminal password on the Lantern host first" if code == 503 else
                "Too many attempts. Try again in five minutes." if code == 429 else
                "Incorrect password"
            )
            self.send_json(code, {"error": message}); return
        if hasattr(self.app.ws, "notify_local_auth_state"):
            self.app.ws.notify_local_auth_state(access)
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        self.send_bytes(200, b'{"ok":true}', "application/json; charset=utf-8", {
            "Set-Cookie": access.cookie_header(token, secure=secure),
            "Cache-Control": "no-store",
        })

    def api_terminal_logout(self) -> None:
        access = self.app.terminal_access
        if access is None:
            self.send_json(503, {"error": "Terminal auth is not ready"}); return
        ip = self.client_address[0]
        is_local = access.is_local(ip) if hasattr(access, "is_local") else False
        try:
            data = self.read_json(max_bytes=4096) if int(self.headers.get("Content-Length") or 0) > 0 else {}
        except Exception:
            data = {}
        if is_local and hasattr(access, "revoke_all_lan"):
            hard_lock = data.get("hardLock") if isinstance(data, dict) and "hardLock" in data else None
            if hard_lock is True and not getattr(access, "configured", False):
                revoked = access.revoke_all_lan(hard_lock=True)
                if hasattr(self.app.ws, "close_lan_peers"):
                    self.app.ws.close_lan_peers(access)
                if hasattr(self.app.ws, "notify_local_auth_state"):
                    self.app.ws.notify_local_auth_state(access)
                self.send_json(409, {
                    "ok": False,
                    "error": "Chưa cấu hình mật khẩu Terminal (chạy python main.py --set-terminal-password). LAN đã bị khóa và không thể đăng nhập cho tới khi đặt mật khẩu hoặc Unlock.",
                    "isLocal": True,
                    "configured": False,
                    "revokedLanSessions": revoked,
                    "lanSessions": access.active_lan_sessions(),
                    "lanLocked": True,
                })
                return
            revoked = access.revoke_all_lan(hard_lock=hard_lock)
            if hasattr(self.app.ws, "close_lan_peers"):
                self.app.ws.close_lan_peers(access)
            if hasattr(self.app.ws, "notify_local_auth_state"):
                self.app.ws.notify_local_auth_state(access)
            payload = self.app.files.json_dumps({
                "ok": True,
                "isLocal": True,
                "configured": bool(getattr(access, "configured", True)),
                "revokedLanSessions": revoked,
                "lanSessions": access.active_lan_sessions(),
                "lanLocked": bool(getattr(access, "lan_locked", False)),
            }).encode("utf-8")
            self.send_bytes(200, payload, "application/json; charset=utf-8", {
                "Cache-Control": "no-store",
            })
            return

        token = access.cookie_token(self.headers.get("Cookie", ""))
        access.logout(token)
        self.app.ws.close_token(token)
        if hasattr(self.app.ws, "notify_local_auth_state"):
            self.app.ws.notify_local_auth_state(access)
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        self.send_bytes(200, b'{"ok":true}', "application/json; charset=utf-8", {
            "Set-Cookie": access.clear_cookie(secure=secure),
            "Cache-Control": "no-store",
        })

    def api_sysstats(self) -> None:
        self.send_bytes(
            200,
            self.app.files.json_dumps(get_system_telemetry()).encode("utf-8"),
            "application/json; charset=utf-8",
            {"Cache-Control": "no-store"},
        )

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
        if "show_hidden" in data:
            self.app.config.show_hidden = bool(data.get("show_hidden"))
            changed["show_hidden"] = self.app.config.show_hidden
        if "show_system" in data:
            self.app.config.show_system = bool(data.get("show_system"))
            changed["show_system"] = self.app.config.show_system
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


    def api_lan_settings_get(self) -> None:
        access = self.app.terminal_access
        ip = self.client_address[0]
        is_local = bool(access and hasattr(access, "is_local") and access.is_local(ip))
        cfg = self.app.config
        bot_cfg = cfg.lantern_bot
        loc = bot_cfg.local_access
        lan = bot_cfg.lan_access
        lan_tools_mode = "full" if lan.is_full_tools else ("none" if lan.tools == ("none",) else ("code" if "edit" in lan.tools else "readonly"))
        self.send_json(200, {
            "ok": True,
            "isLocal": is_local,
            "lanLocked": bool(getattr(access, "lan_locked", False)),
            "passwordConfigured": bool(getattr(access, "configured", False)),
            "lanSessions": access.active_lan_sessions() if (access and is_local) else 0,
            "terminalEnabled": bool(cfg.terminal_enabled),
            "lanbotEnabled": bool(bot_cfg.enabled),
            "localSelection": {
                "provider": loc.provider or "",
                "model": loc.model or "",
                "lockProvider": bool(loc.lock_provider),
                "lockModel": bool(loc.lock_model),
            },
            "lanSelection": {
                "provider": lan.provider or "",
                "model": lan.model or "",
                "lockProvider": bool(lan.lock_provider),
                "lockModel": bool(lan.lock_model),
            },
            "lanToolsMode": lan_tools_mode,
        })

    def api_lan_settings_post(self) -> None:
        import dataclasses
        from lantern.bot_config import _TOOL_MODE_PRESETS
        access = self.app.terminal_access
        ip = self.client_address[0]
        is_local = bool(access and hasattr(access, "is_local") and access.is_local(ip))
        if not is_local:
            self.send_json(403, {"error": "Only localhost can modify LAN & Workspace Settings"})
            return
        data = self.read_json()
        cfg = self.app.config

        # 1. Password update (4-12 chars) or clear
        if "password" in data or data.get("clearPassword"):
            raw_pwd = "" if data.get("clearPassword") else str(data.get("password") or "").strip()
            if raw_pwd and (len(raw_pwd) < 4 or len(raw_pwd) > 12):
                self.send_json(400, {"error": "Mật khẩu LAN phải từ 4 đến 12 ký tự (Password must be 4-12 characters)."})
                return
            if access and hasattr(access, "set_password"):
                encoded = access.set_password(raw_pwd, cfg.config_path)
                cfg.terminal_password_hash = encoded

        # 2. LAN lock state
        if "lanLocked" in data and access and hasattr(access, "revoke_all_lan"):
            want_lock = bool(data.get("lanLocked"))
            access.revoke_all_lan(hard_lock=want_lock)
            if want_lock and hasattr(self.app.ws, "close_lan_peers"):
                self.app.ws.close_lan_peers(access)

        # 3. Terminal & Lanbot enable/disable switches
        if "terminalEnabled" in data:
            cfg.terminal_enabled = bool(data.get("terminalEnabled"))
        bot_cfg = cfg.lantern_bot
        next_enabled = bool(data["lanbotEnabled"]) if "lanbotEnabled" in data else bot_cfg.enabled

        # 4. Pinned Provider / Model for LAN (Localhost Keyholder is NEVER locked by LAN settings)
        loc = dataclasses.replace(bot_cfg.local_access, lock_provider=False, lock_model=False)
        if isinstance(data.get("localSelection"), dict):
            lsel = data["localSelection"]
            l_prov = str(lsel.get("provider") or "").strip()
            l_mod = str(lsel.get("model") or "").strip()
            if "/" in l_mod and not l_prov:
                l_prov, l_mod = l_mod.split("/", 1)
            loc = dataclasses.replace(loc, provider=l_prov, model=l_mod, lock_provider=False, lock_model=False)

        lan = bot_cfg.lan_access
        if isinstance(data.get("lanSelection"), dict):
            nsel = data["lanSelection"]
            n_prov = str(nsel.get("provider") or "").strip()
            n_mod = str(nsel.get("model") or "").strip()
            if "/" in n_mod and not n_prov:
                n_prov, n_mod = n_mod.split("/", 1)
            n_lock_m = bool(nsel.get("lockModel")) and bool(n_prov and n_mod)
            n_lock_p = (bool(nsel.get("lockProvider")) or n_lock_m) and bool(n_prov)
            lan = dataclasses.replace(lan, provider=n_prov, model=n_mod, lock_provider=n_lock_p, lock_model=n_lock_m)

        if "lanToolsMode" in data:
            tmode = str(data.get("lanToolsMode") or "readonly").strip().lower()
            preset = _TOOL_MODE_PRESETS.get(tmode, ("read", "grep", "find", "ls"))
            lan = dataclasses.replace(lan, tools=preset)

        cfg.lantern_bot = dataclasses.replace(bot_cfg, enabled=next_enabled, local_access=loc, lan_access=lan)
        if self.app.bot is not None and hasattr(self.app.bot, "update_bot_config"):
            self.app.bot.update_bot_config(cfg.lantern_bot)
        elif self.app.bot is not None:
            self.app.bot.bot_config = cfg.lantern_bot
            for b_inst in getattr(self.app.bot, "_all_bot_instances", lambda: [])():
                b_inst.bot_config = cfg.lantern_bot

        write_config_file(cfg)
        if access and hasattr(self.app.ws, "notify_local_auth_state"):
            self.app.ws.notify_local_auth_state(access)
        return self.api_lan_settings_get()

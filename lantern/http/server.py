
import json
import socketserver
import sys
import time
import urllib.parse
from typing import Any, Dict, Optional
from http.server import SimpleHTTPRequestHandler

from lantern.config import (MAX_JSON_BODY)
from lantern.filesystem import BadRequest
from lantern.ws import same_origin, upgrade as upgrade_websocket

from lantern.http.routes.app import AppRoutes
from lantern.http.routes.plugin import PluginRoutes
from lantern.http.routes.media import MediaRoutes
from lantern.http.routes.crop import CropRoutes
from lantern.http.routes.markdown import MarkdownRoutes
from lantern.http.routes.files import FilesRoutes

class LanternHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler, app):
        self.app = app
        super().__init__(server_address, handler)

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

class Handler(AppRoutes,PluginRoutes,MediaRoutes,CropRoutes,MarkdownRoutes,FilesRoutes,SimpleHTTPRequestHandler):
    @property
    def app(self):
        return self.server.app

    server_version = "LANDriveOneFile/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s - %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_bytes(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8", extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, data: Dict[str, Any]) -> None:
        self.send_bytes(status, self.app.files.json_dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def content_length(self, *, max_bytes: Optional[int] = None) -> int:
        raw = self.headers.get("Content-Length") or "0"
        try:
            n = int(raw)
        except Exception:
            raise BadRequest("invalid Content-Length")
        if n < 0:
            raise BadRequest("invalid Content-Length")
        if max_bytes is not None and n > max_bytes:
            raise BadRequest(f"request body too large; max {self.app.files.size_fmt(max_bytes)}")
        return n

    def read_body_exact(self, n: int) -> bytes:
        data = self.rfile.read(n) if n else b""
        if len(data) != n:
            raise BadRequest("incomplete request body")
        return data

    def read_json(self, *, max_bytes: int = MAX_JSON_BODY) -> Dict[str, Any]:
        n = self.content_length(max_bytes=max_bytes)
        if n <= 0:
            return {}
        raw = self.read_body_exact(n)
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as e:
            raise BadRequest(f"invalid JSON: {e.msg}")
        if not isinstance(data, dict):
            raise BadRequest("JSON body must be an object")
        return data

    def serve_app_asset(self, url_path: str) -> None:
        root = self.app.static_dir
        rel = url_path[len("/static/"):].replace("\\", "/")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self.send_error(403, "invalid asset path"); return
        if not target.is_file():
            self.send_error(404, "asset not found"); return
        return self.serve_static_file(target, cache_control="no-cache")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/favicon.ico":
                self.send_response(204); self.end_headers(); return
            if parsed.path == "/ws":
                if self.app.terminal is None or self.app.scm is None or self.app.terminal_access is None:
                    self.send_error(503, "runtime not initialized"); return
                return upgrade_websocket(self, self.app.ws, self.app.terminal, self.app.scm, self.app.terminal_access, self.app.bot)
            if parsed.path.startswith("/static/"):
                return self.serve_app_asset(parsed.path)
            if parsed.path == "/api/terminal/auth":
                return self.api_terminal_auth()
            if parsed.path == "/api/info":
                return self.api_info()
            if parsed.path == "/api/config":
                return self.api_config_get()
            if parsed.path == "/api/list":
                return self.api_list(parsed.query)
            if parsed.path == "/api/upload/check":
                return self.api_upload_check(parsed.query)
            if parsed.path == "/api/image/version":
                return self.api_image_version(parsed.query)
            if parsed.path == "/api/thumb":
                return self.api_thumb(parsed.query)
            if parsed.path == "/api/folder_preview":
                return self.api_folder_preview(parsed.query)
            if parsed.path == "/api/video_info":
                return self.api_video_info(parsed.query)
            if parsed.path == "/api/subtitle":
                return self.api_subtitle(parsed.query)
            if parsed.path == "/api/work":
                return self.api_work_get(parsed.query)
            if parsed.path == "/api/md/document":
                return self.api_md_document(parsed.query)
            if parsed.path == "/api/plugin/info":
                return self.api_plugin_info()
            if parsed.path in ("/api/plugin/preview", "/api/preview"):
                return self.api_plugin_preview(parsed.query)

            target = self.app.files.safe_join(parsed.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "edit" in qs:
                return self.serve_editor(target)
            if target.is_dir():
                return self.serve_directory(target)
            if target.is_file():
                if "download" in qs:
                    return self.serve_static_file(target, download=True)
                return self.serve_file(target)
            self.send_error(404, "Not found")
        except BadRequest as e:
            self.send_json(400, {"error": str(e)})
        except PermissionError as e:
            self.send_error(403, str(e))
        except BrokenPipeError:
            return
        except Exception as e:
            self.send_error(500, f"Server error: {e}")

    def do_POST(self) -> None:
        try:
            # Browser-originated mutations must stay same-origin. Requests without
            # Origin remain allowed for CLI/API clients on trusted networks.
            if self.headers.get("Origin") and not same_origin(self):
                self.send_error(403, "POST Origin must match Host")
                return
            parsed = urllib.parse.urlsplit(self.path)
            route = parsed.path
            if route == "/api/terminal/login": return self.api_terminal_login()
            if route == "/api/terminal/logout": return self.api_terminal_logout()
            if route == "/api/upload": return self.api_upload(parsed.query)
            if route == "/api/image/overwrite": return self.api_image_overwrite(parsed.query)
            if route == "/api/save": return self.api_save()
            if route == "/api/work/write": return self.api_work_write()
            if route == "/api/work/patch": return self.api_work_patch()
            if route == "/api/work/save": return self.api_work_save()
            if route == "/api/work/accept-hunk": return self.api_work_accept_hunk()
            if route == "/api/work/discard": return self.api_work_discard()
            if route == "/api/md/render": return self.api_md_render()
            if route == "/api/md/save": return self.api_md_save()
            if route == "/api/mkdir": return self.api_mkdir()
            if route == "/api/newfile": return self.api_newfile()
            if route == "/api/rename": return self.api_rename()
            if route == "/api/copy": return self.api_copy()
            if route == "/api/move": return self.api_move()
            if route == "/api/duplicate": return self.api_duplicate()
            if route == "/api/batch_rename": return self.api_batch_rename()
            if route == "/api/extract": return self.api_extract()
            if route == "/api/delete": return self.api_delete()
            if route == "/api/archive": return self.api_archive()
            if route == "/api/zip": return self.api_zip()
            if route == "/api/config": return self.api_config_post()
            if route == "/api/plugin/extensions": return self.api_plugin_extensions()
            self.send_error(404, "API not found")
        except BadRequest as e:
            self.send_json(400, {"error": str(e)})
        except PermissionError as e:
            self.send_json(403, {"error": str(e)})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LAN Drive OneFile Lazy Config
=============================
Một file Python duy nhất để duyệt / xem / upload / sửa / tải / chia sẻ file trong LAN hoặc Tailscale.

Chạy nhanh:
  python3 lan_drive.py --port 9999
  python3 lan_drive.py --root / --port 9999

Tuỳ chọn:
  --root PATH        Thư mục gốc để duyệt. Linux mặc định là /. Windows mặc định là ổ hiện tại, ví dụ C:\\
  --port PORT        Cổng web, mặc định 9999
  --host HOST        Mặc định 0.0.0.0 để máy khác trong LAN truy cập được
  --title TITLE      Tên hiển thị ở giao diện
  --cache-dir PATH   Nơi lưu thumbnail. Mặc định dùng temp/cache của hệ thống
  --show-hidden      Hiện file/thư mục bắt đầu bằng dấu chấm
  --show-system      Khi root là / trên Linux, hiện cả /proc /sys /run /dev. Mặc định ẩn để UI mượt hơn

Tính năng chính:
  - Gõ ip:port là vào xem luôn
  - Duyệt thư mục dạng grid/list, tìm nhanh, tìm đệ quy theo độ sâu, sort, breadcrumb
  - Xem ảnh dạng gallery có next/prev, vuốt trái/phải trên điện thoại, phím mũi tên trên laptop
  - Xem video/audio trong media player modal; video hỗ trợ tua nhờ HTTP Range và tự chuyển video kế tiếp
  - Upload nhiều file bằng stream từng file, có progress; hỗ trợ upload folder trên Chrome/Edge
  - Tạo thư mục, tạo file text, sửa file text/code/config/log
  - Rename, delete, download file, download nhiều file/folder dạng zip stream
  - Share link đơn giản: copy URL trực tiếp tới file/thư mục trong LAN/Tailscale
  - Không cần tài khoản, không DB, không Docker, không framework ngoài stdlib
  - Terminal drawer: Linux ưu tiên tmux + PTY thật, fallback PTY; Windows command mode cơ bản
  - Nếu có Pillow thì thumbnail ảnh đẹp hơn; nếu có ffmpeg thì thumbnail video tốt hơn

Lưu ý: File này được thiết kế cho LAN/Tailscale tin cậy. Không phơi thẳng ra Internet.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import io
import json
import mimetypes
import os
import platform
import posixpath
import re
import shlex
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import tarfile
import threading
import time
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from http import HTTPStatus

try:
    import plugin as LAN_PLUGIN  # optional document preview plugin
except Exception:
    LAN_PLUGIN = None  # lan_drive.py must remain standalone
from http.server import SimpleHTTPRequestHandler

try:
    from PIL import Image, ImageOps  # type: ignore
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    FFMPEG = shutil.which("ffmpeg")
except Exception:
    FFMPEG = None
try:
    FFPROBE = shutil.which("ffprobe")
except Exception:
    FFPROBE = None

try:
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios
    HAS_UNIX_PTY = os.name != "nt"
except Exception:
    fcntl = pty = select = signal = struct = termios = None  # type: ignore
    HAS_UNIX_PTY = False

APP_NAME = "LAN Drive OneFile"
DEFAULT_PORT = int(os.environ.get("LAN_DRIVE_PORT", "9999"))
DEFAULT_HOST = os.environ.get("LAN_DRIVE_HOST", "0.0.0.0")

if os.name == "nt":
    DEFAULT_ROOT = os.environ.get("LAN_DRIVE_ROOT") or Path.cwd().anchor or "C:/"
else:
    DEFAULT_ROOT = os.environ.get("LAN_DRIVE_ROOT", "/")

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".py", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".htm",
    ".xml", ".svg", ".sql", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".java",
    ".kt", ".swift", ".php", ".rb", ".lua", ".r", ".dockerfile", ".env",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".heic", ".heif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi", ".ts", ".mpeg", ".mpg", ".3gp"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".weba"}
SUBTITLE_EXTS = {".vtt", ".srt", ".ass", ".ssa"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".bz2"}
OFFICE_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}

SYSTEM_SKIP_NAMES = {"proc", "sys", "run", "dev"}
CHUNK_SIZE = 1024 * 1024
MAX_TEXT_PREVIEW = 20 * 1024 * 1024  # 20MB
MAX_JSON_BODY = 32 * 1024 * 1024
MAX_ZIP_PAYLOAD = 4 * 1024 * 1024

mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("image/heic", ".heic")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("audio/flac", ".flac")

@dataclass
class AppConfig:
    root: Path
    port: int
    host: str
    title: str
    cache_dir: Path
    config_path: Path
    show_hidden: bool = False
    show_system: bool = False
    default_sort: str = "name-asc"
    default_view: str = "grid"
    page_limit: int = 220
    folders_first: bool = True
    search_debounce_ms: int = 240
    terminal_enabled: bool = True
    terminal_backend_linux: str = "pty"
    terminal_backend_linux_fallback: str = "pty"
    terminal_shell_linux: str = "/bin/bash"
    terminal_tmux_bin: str = "tmux"
    terminal_tmux_session_prefix: str = "landrive"
    terminal_tmux_status_bar: bool = False
    terminal_session_mode: str = "per_folder"
    terminal_backend_windows: str = "command"
    terminal_shell_windows: str = "powershell"
    terminal_command_timeout: int = 0
    terminal_max_sessions: int = 8
    terminal_idle_detach_minutes: int = 120
    terminal_max_buffer_chars: int = 500000
    terminal_poll_ms: int = 150
    terminal_start_height_px: int = 380
    terminal_mobile_extra_keys: bool = True
    thumb_fit: str = "contain"
    folder_preview_enabled: bool = True
    folder_preview_mode: str = "mosaic4"
    folder_preview_fit: str = "contain"
    folder_preview_rotate: bool = True
    folder_preview_animation: str = "fade"
    folder_preview_interval_ms: int = 3500
    folder_preview_scan_limit: int = 40
    folder_preview_max_items: int = 12
    folder_preview_include_video: bool = True
    upload_auto_start: bool = False
    upload_parallel: int = 3
    upload_conflict: str = "ask"

CONFIG: AppConfig


def plugin_config_path() -> Path:
    try:
        return CONFIG.cache_dir / "plugin_config.json"
    except Exception:
        return Path(tempfile.gettempdir()) / "lan-drive-plugin-config.json"


def plugin_enabled() -> bool:
    return LAN_PLUGIN is not None


def plugin_can_preview(path: Path) -> bool:
    if LAN_PLUGIN is None:
        return False
    try:
        return bool(LAN_PLUGIN.can_preview(path, plugin_config_path()))
    except Exception:
        return False


VALID_SORTS = {
    "name-asc", "name-desc",
    "mtime-desc", "mtime-asc",
    "size-desc", "size-asc",
    "type-asc", "type-desc",
    "ext-asc", "ext-desc",
}
VALID_VIEWS = {"grid", "list"}

DEFAULT_CONFIG_DATA: Dict[str, Any] = {
    "root": DEFAULT_ROOT,
    "port": DEFAULT_PORT,
    "host": DEFAULT_HOST,
    "title": "LAN Drive",
    "cache_dir": os.environ.get("LAN_DRIVE_CACHE", os.path.join(tempfile.gettempdir(), "lan-drive-onefile-cache")),
    "show_hidden": False,
    "show_system": False,
    "default_sort": "name-asc",
    "default_view": "grid",
    "page_limit": 220,
    "folders_first": True,
    "search_debounce_ms": 240,
    "terminal_enabled": True,
    "terminal_backend_linux": "pty",
    "terminal_backend_linux_fallback": "pty",
    "terminal_shell_linux": "/bin/bash",
    "terminal_tmux_bin": "tmux",
    "terminal_tmux_session_prefix": "landrive",
    "terminal_tmux_status_bar": False,
    "terminal_session_mode": "per_folder",
    "terminal_backend_windows": "command",
    "terminal_shell_windows": "powershell",
    "terminal_command_timeout": 0,
    "terminal_max_sessions": 8,
    "terminal_idle_detach_minutes": 120,
    "terminal_max_buffer_chars": 500000,
    "terminal_poll_ms": 150,
    "terminal_start_height_px": 380,
    "terminal_mobile_extra_keys": True,
    "thumb_fit": "contain",
    "folder_preview_enabled": True,
    "folder_preview_mode": "mosaic4",
    "folder_preview_fit": "contain",
    "folder_preview_rotate": True,
    "folder_preview_animation": "fade",
    "folder_preview_interval_ms": 3500,
    "folder_preview_scan_limit": 40,
    "folder_preview_max_items": 12,
    "folder_preview_include_video": True,
    "upload_auto_start": False,
    "upload_parallel": 3,
    "upload_conflict": "ask",
}


def config_file_default_path() -> Path:
    try:
        return Path(__file__).resolve().with_name("lan_drive_config.yaml")
    except Exception:
        return Path("lan_drive_config.yaml").resolve()


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {'"', "'"} and value[-1:] == value[0]:
        return value[1:-1]
    low = value.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if low in {"null", "none"}:
        return None
    try:
        return int(value)
    except Exception:
        return value


def load_simple_yaml(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        if key:
            data[key] = parse_scalar(val)
    return data


def yaml_quote(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\"')
    return f'"{text}"'


def config_to_dict(cfg: "AppConfig") -> Dict[str, Any]:
    return {
        "root": str(cfg.root),
        "port": cfg.port,
        "host": cfg.host,
        "title": cfg.title,
        "cache_dir": str(cfg.cache_dir),
        "show_hidden": cfg.show_hidden,
        "show_system": cfg.show_system,
        "default_sort": cfg.default_sort,
        "default_view": cfg.default_view,
        "page_limit": cfg.page_limit,
        "folders_first": cfg.folders_first,
        "search_debounce_ms": cfg.search_debounce_ms,
        "terminal_enabled": cfg.terminal_enabled,
        "terminal_backend_linux": cfg.terminal_backend_linux,
        "terminal_backend_linux_fallback": cfg.terminal_backend_linux_fallback,
        "terminal_shell_linux": cfg.terminal_shell_linux,
        "terminal_tmux_bin": cfg.terminal_tmux_bin,
        "terminal_tmux_session_prefix": cfg.terminal_tmux_session_prefix,
        "terminal_tmux_status_bar": cfg.terminal_tmux_status_bar,
        "terminal_session_mode": cfg.terminal_session_mode,
        "terminal_backend_windows": cfg.terminal_backend_windows,
        "terminal_shell_windows": cfg.terminal_shell_windows,
        "terminal_command_timeout": cfg.terminal_command_timeout,
        "terminal_max_sessions": cfg.terminal_max_sessions,
        "terminal_idle_detach_minutes": cfg.terminal_idle_detach_minutes,
        "terminal_max_buffer_chars": cfg.terminal_max_buffer_chars,
        "terminal_poll_ms": cfg.terminal_poll_ms,
        "terminal_start_height_px": cfg.terminal_start_height_px,
        "terminal_mobile_extra_keys": cfg.terminal_mobile_extra_keys,
        "thumb_fit": cfg.thumb_fit,
        "folder_preview_enabled": cfg.folder_preview_enabled,
        "folder_preview_mode": cfg.folder_preview_mode,
        "folder_preview_fit": cfg.folder_preview_fit,
        "folder_preview_rotate": cfg.folder_preview_rotate,
        "folder_preview_animation": cfg.folder_preview_animation,
        "folder_preview_interval_ms": cfg.folder_preview_interval_ms,
        "folder_preview_scan_limit": cfg.folder_preview_scan_limit,
        "folder_preview_max_items": cfg.folder_preview_max_items,
        "folder_preview_include_video": cfg.folder_preview_include_video,
        "upload_auto_start": cfg.upload_auto_start,
        "upload_parallel": cfg.upload_parallel,
        "upload_conflict": cfg.upload_conflict,
    }


def write_config_file(cfg: "AppConfig") -> None:
    cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config_to_dict(cfg)
    lines = [
        "# LAN Drive config - file này có thể sửa tay hoặc đổi trong UI.",
        "# Chạy: python3 lan_drive.py --config lan_drive_config.yaml",
    ]
    for key in [
        "root", "port", "host", "title", "cache_dir",
        "show_hidden", "show_system", "default_sort", "default_view",
        "page_limit", "folders_first", "search_debounce_ms",
        "terminal_enabled", "terminal_backend_linux", "terminal_backend_linux_fallback",
        "terminal_shell_linux", "terminal_tmux_bin", "terminal_tmux_session_prefix",
        "terminal_tmux_status_bar", "terminal_session_mode", "terminal_backend_windows", "terminal_shell_windows",
        "terminal_command_timeout", "terminal_max_sessions", "terminal_idle_detach_minutes", "terminal_max_buffer_chars",
        "terminal_poll_ms", "terminal_start_height_px", "terminal_mobile_extra_keys",
        "thumb_fit", "folder_preview_enabled", "folder_preview_mode", "folder_preview_fit",
        "folder_preview_rotate", "folder_preview_animation", "folder_preview_interval_ms",
        "folder_preview_scan_limit", "folder_preview_max_items", "folder_preview_include_video",
        "upload_auto_start", "upload_parallel", "upload_conflict",
    ]:
        lines.append(f"{key}: {yaml_quote(data[key])}")
    cfg.config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_sort(value: Any) -> str:
    v = str(value or "name-asc").strip()
    return v if v in VALID_SORTS else "name-asc"


def normalize_view(value: Any) -> str:
    v = str(value or "grid").strip()
    return v if v in VALID_VIEWS else "grid"


def normalize_page_limit(value: Any) -> int:
    try:
        return max(50, min(int(value), 1000))
    except Exception:
        return 220


def normalize_fit(value: Any) -> str:
    v = str(value or "contain").strip().lower()
    return v if v in {"contain", "cover"} else "contain"


def normalize_animation(value: Any) -> str:
    v = str(value or "fade").strip().lower()
    return v if v in {"none", "fade", "flip", "slide"} else "fade"


def normalize_conflict(value: Any) -> str:
    v = str(value or "ask").strip().lower()
    return v if v in {"ask", "overwrite", "skip", "rename"} else "ask"


def normalize_recursive_depth(value: Any) -> Optional[int]:
    v = str(value or "0").strip().lower()
    if v in {"all", "*", "∞", "unlimited"}:
        return None
    try:
        return max(0, min(int(v), 6))
    except (TypeError, ValueError):
        return 0


def norm_root(p: str) -> Path:
    if os.name == "nt":
        return Path(p).resolve()
    return Path(p).resolve()


def is_windows_drive_listing_request(rel: str) -> bool:
    return os.name == "nt" and rel in ("", "/") and str(CONFIG.root) in ("/", "\\")


def safe_join(rel_url_path: str) -> Path:
    """Map URL path to filesystem path inside CONFIG.root."""
    raw = urllib.parse.unquote(rel_url_path.split("?", 1)[0].split("#", 1)[0])
    raw = raw.replace("\\", "/")
    parts = []
    for part in raw.split("/"):
        if not part or part in (".", ".."):
            continue
        parts.append(part)
    candidate = CONFIG.root.joinpath(*parts).resolve()
    root = CONFIG.root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError("Path is outside root")
    return candidate


def rel_url_for_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(CONFIG.root.resolve()).as_posix()
    except Exception:
        rel = path.name
    if not rel or rel == ".":
        return "/"
    return "/" + quote_path(rel)


def quote_path(path: str) -> str:
    path = path.replace("\\", "/")
    return "/".join(urllib.parse.quote(p) for p in path.split("/"))


class BadRequest(ValueError):
    pass


def clean_name(name: str) -> str:
    name = name.replace("\x00", "").strip()
    name = name.replace("/", "_").replace("\\", "_")
    return name or f"unnamed-{int(time.time())}"


def clean_component(name: str, *, fallback: Optional[str] = None) -> str:
    raw = str(name).replace("\x00", "").replace("/", "_").replace("\\", "_").strip()
    raw = "".join(ch for ch in raw if ch == "\t" or ord(ch) >= 32).strip()
    if not raw and fallback is not None:
        raw = fallback
    if not raw or raw in {".", ".."}:
        raise BadRequest("bad filename component")
    return raw


def drain_stream(stream: Any, remaining: int) -> None:
    while remaining > 0:
        chunk = stream.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            break
        remaining -= len(chunk)


def ensure_under_root(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(CONFIG.root.resolve())
    except ValueError:
        raise PermissionError("Path is outside root")
    return resolved


def payload_paths(data: Dict[str, Any], key: str = "paths") -> List[str]:
    raw = data.get(key)
    if raw is None and "path" in data:
        raw = [data.get("path")]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise BadRequest(f"{key} must be a list")
    out: List[str] = []
    for item in raw:
        rel = str(item or "").strip()
        if rel:
            out.append(rel)
    if not out:
        raise BadRequest("no paths supplied")
    return out


def resolve_existing(rel: str) -> Path:
    p = safe_join("/" + str(rel))
    if not p.exists():
        raise BadRequest(f"not found: {rel}")
    return p


def resolve_destination_dir(data: Dict[str, Any], default: str = "") -> Path:
    rel = str(data.get("dest") if data.get("dest") is not None else data.get("dest_dir", default))
    dest = safe_join("/" + rel)
    if dest.exists() and not dest.is_dir():
        raise BadRequest("destination is not a folder")
    dest.mkdir(parents=True, exist_ok=True)
    return ensure_under_root(dest)


def split_stem_suffix(name: str) -> Tuple[str, str]:
    p = Path(name)
    return p.stem, p.suffix


def unique_path(candidate: Path) -> Path:
    candidate = ensure_under_root(candidate)
    if not candidate.exists():
        return candidate
    stem, suffix = split_stem_suffix(candidate.name)
    for i in range(1, 10000):
        alt = candidate.with_name(f"{stem} ({i}){suffix}")
        if not alt.exists():
            return ensure_under_root(alt)
    raise BadRequest("cannot find free target name")


def conflict_target(candidate: Path, conflict: str) -> Optional[Path]:
    conflict = normalize_conflict(conflict)
    candidate = ensure_under_root(candidate)
    if not candidate.exists():
        return candidate
    if conflict == "skip":
        return None
    if conflict == "rename":
        return unique_path(candidate)
    if conflict == "overwrite":
        return candidate
    raise BadRequest(f"target exists: {candidate.name}")


def reject_self_nesting(src: Path, dest: Path) -> None:
    src_r, dest_r = src.resolve(), dest.resolve()
    if src_r == dest_r:
        raise BadRequest("source and destination are the same")
    if src.is_dir():
        try:
            dest_r.relative_to(src_r)
            raise BadRequest("cannot place a folder inside itself")
        except ValueError:
            pass


def remove_existing_target(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def copy_item(src: Path, dest_dir: Path, *, name: Optional[str] = None, conflict: str = "rename") -> Optional[Path]:
    final_name = clean_component(name if name is not None else src.name)
    dest = conflict_target(dest_dir / final_name, conflict)
    if dest is None:
        return None
    reject_self_nesting(src, dest)
    if dest.exists() and normalize_conflict(conflict) == "overwrite":
        remove_existing_target(dest)
    if src.is_dir() and not src.is_symlink():
        shutil.copytree(src, dest, symlinks=True, copy_function=shutil.copy2)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest, follow_symlinks=False)
    return dest


def move_item(src: Path, dest_dir: Path, *, name: Optional[str] = None, conflict: str = "rename") -> Optional[Path]:
    final_name = clean_component(name if name is not None else src.name)
    dest = conflict_target(dest_dir / final_name, conflict)
    if dest is None:
        return None
    reject_self_nesting(src, dest)
    if dest.exists() and normalize_conflict(conflict) == "overwrite":
        remove_existing_target(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return dest


def duplicate_name(src: Path) -> str:
    stem, suffix = split_stem_suffix(src.name)
    return f"{stem} copy{suffix}" if suffix else f"{src.name} copy"


def unique_arcname(name: str, used: set[str]) -> str:
    clean = name.strip("/") or "item"
    if clean not in used:
        used.add(clean)
        return clean
    p = Path(clean)
    stem, suffix = p.stem, p.suffix
    parent = p.parent.as_posix()
    for i in range(1, 10000):
        cand = f"{stem} ({i}){suffix}"
        if parent not in ("", "."):
            cand = parent.rstrip("/") + "/" + cand
        if cand not in used:
            used.add(cand)
            return cand
    raise BadRequest("cannot allocate archive name")


def iter_archive_entries(paths: List[Path]) -> Iterable[Tuple[Path, str]]:
    used: set[str] = set()
    for target in paths:
        top = unique_arcname(target.name, used)
        if target.is_dir() and not target.is_symlink():
            yielded = False
            for root, dirs, files in os.walk(target):
                rootp = Path(root)
                dirs[:] = [d for d in dirs if not should_hide_entry(rootp, d)]
                for fn in files:
                    if should_hide_entry(rootp, fn):
                        continue
                    p = rootp / fn
                    try:
                        rel = p.relative_to(target).as_posix()
                    except Exception:
                        continue
                    yielded = True
                    yield p, top + "/" + rel
            if not yielded:
                yield target, top + "/"
        else:
            yield target, top


def parse_archive_payload(handler: Any) -> Dict[str, Any]:
    n = handler.content_length(max_bytes=MAX_ZIP_PAYLOAD)
    raw = handler.read_body_exact(n) if n else b""
    if not raw:
        return {}
    ctype = handler.headers.get("Content-Type", "")
    if "application/json" in ctype:
        return json.loads(raw.decode("utf-8", "replace"))
    form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
    return json.loads(form.get("payload", ["{}"])[0])


def archive_response_meta(fmt: str, compression: str) -> Tuple[str, str, str]:
    fmt = str(fmt or "zip").lower()
    compression = str(compression or "compress").lower()
    stamp = int(time.time())
    if fmt == "tar":
        if compression == "compress":
            return f"lan-drive-{stamp}.tar.gz", "application/gzip", "w|gz"
        return f"lan-drive-{stamp}.tar", "application/x-tar", "w|"
    if fmt != "zip":
        raise BadRequest("archive format must be zip or tar")
    return f"lan-drive-{stamp}.zip", "application/zip", "zip"


def safe_extract_member_path(dest: Path, member_name: str) -> Path:
    name = str(member_name or "").replace("\\", "/")
    if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise BadRequest(f"unsafe archive member: {member_name}")
    parts = []
    for part in name.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise BadRequest(f"unsafe archive member: {member_name}")
        parts.append(clean_component(part))
    if not parts:
        raise BadRequest(f"unsafe archive member: {member_name}")
    return ensure_under_root(dest.joinpath(*parts))


def write_extracted_file(src_file: Any, out_path: Path, conflict: str) -> Optional[Path]:
    target = conflict_target(out_path, conflict)
    if target is None:
        return None
    if target.exists() and normalize_conflict(conflict) == "overwrite":
        remove_existing_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp: Optional[Path] = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".extract-", dir=str(target.parent))
        tmp = Path(tmp_name)
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(src_file, out, CHUNK_SIZE)
        os.replace(tmp, target)
        tmp = None
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
    return target


def extract_archive(archive_path: Path, dest: Path, conflict: str = "rename") -> Dict[str, Any]:
    written = 0
    skipped = 0
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                out_path = safe_extract_member_path(dest, info.filename)
                if info.is_dir():
                    out_path.mkdir(parents=True, exist_ok=True)
                    continue
                with zf.open(info) as src:
                    result = write_extracted_file(src, out_path, conflict)
                if result is None:
                    skipped += 1
                else:
                    written += 1
        return {"ok": True, "format": "zip", "written": written, "skipped": skipped}
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                out_path = safe_extract_member_path(dest, member.name)
                if member.isdir():
                    out_path.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    skipped += 1
                    continue
                src = tf.extractfile(member)
                if src is None:
                    skipped += 1
                    continue
                with src:
                    result = write_extracted_file(src, out_path, conflict)
                if result is None:
                    skipped += 1
                else:
                    written += 1
        return {"ok": True, "format": "tar", "written": written, "skipped": skipped}
    raise BadRequest("unsupported archive; use zip/tar/tar.gz/tgz/tbz2/txz")


def html_escape(s: Any) -> str:
    return html.escape(str(s), quote=True)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def size_fmt(num: int) -> str:
    try:
        n = float(num)
    except Exception:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if n < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def mtime_fmt(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return ""


def classify(path: Path, is_dir: bool = False) -> str:
    if is_dir:
        return "folder"

    name = path.name.lower()
    ext = path.suffix.lower()

    TEXT_NAMES = {
        "dockerfile",
        "makefile",
        "readme",
        "license",

        # dot/config files không có suffix thật
        ".env",
        ".gitignore",
        ".dockerignore",
        ".npmrc",
        ".yarnrc",
        ".pnpmrc",
        ".bashrc",
        ".zshrc",
        ".profile",
        ".bash_profile",
        ".bash_aliases",
        ".vimrc",
        ".editorconfig",
        ".prettierrc",
        ".eslintrc",

        # config/text files thường không có extension
        "authorized_keys",
        "known_hosts",
        "config",
        "hosts",
    }

    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"

    if (
        ext in TEXT_EXTS
        or name in TEXT_NAMES
        or name.startswith(".env.")      # .env.local, .env.production
        or name.startswith(".env-")      # .env-prod
    ):
        return "text"

    if ext == ".pdf":
        return "pdf"
    if ext in OFFICE_EXTS:
        return "office"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "file"


def icon_for(kind: str) -> str:
    return {
        "folder": "📁", "image": "🖼️", "video": "🎬", "audio": "🎵", "text": "📝",
        "pdf": "📕", "office": "📄", "archive": "🗜️", "file": "📦",
    }.get(kind, "📦")


def should_hide_entry(parent: Path, name: str) -> bool:
    if not CONFIG.show_hidden and name.startswith("."):
        return True
    if os.name != "nt" and CONFIG.root == Path("/").resolve() and parent.resolve() == Path("/") and not CONFIG.show_system:
        if name in SYSTEM_SKIP_NAMES:
            return True
    return False


def get_local_ip_guess() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def file_etag(path: Path, st: os.stat_result) -> str:
    raw = f"{path}:{st.st_size}:{st.st_mtime_ns}".encode("utf-8", "surrogateescape")
    return hashlib.sha1(raw).hexdigest()[:16]


def thumb_cache_path(path: Path, kind: str) -> Path:
    try:
        st = path.stat()
        raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{kind}".encode("utf-8", "surrogateescape")
    except Exception:
        raw = f"{path}|{time.time()}|{kind}".encode("utf-8", "surrogateescape")
    name = hashlib.sha1(raw).hexdigest() + ".jpg"
    return CONFIG.cache_dir / "thumbs" / name[:2] / name

def folder_preview_cache_path(folder: Path) -> Path:
    try:
        st = folder.stat()
        raw = f"{folder.resolve()}|{st.st_mtime_ns}|{CONFIG.folder_preview_scan_limit}|{CONFIG.folder_preview_max_items}|{CONFIG.folder_preview_include_video}".encode("utf-8", "surrogateescape")
    except Exception:
        raw = f"{folder}|{time.time()}".encode("utf-8", "surrogateescape")
    name = hashlib.sha1(raw).hexdigest() + ".json"
    return CONFIG.cache_dir / "folder_previews" / name[:2] / name


def folder_preview_items(folder: Path) -> List[Dict[str, Any]]:
    """Return lightweight preview metadata for a folder.

    Important for performance: scan only one level, prefer images, and only fall
    back to videos when there are not enough images. This avoids spawning ffmpeg
    thumbnails for every video-heavy folder while browsing.
    """
    if not CONFIG.folder_preview_enabled or not folder.is_dir():
        return []
    cache = folder_preview_cache_path(folder)
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    images: List[Dict[str, Any]] = []
    videos: List[Dict[str, Any]] = []
    scanned = 0

    def add_item(p: Path, name: str, kind: str) -> Dict[str, Any]:
        rel = p.resolve().relative_to(CONFIG.root.resolve()).as_posix()
        return {
            "name": name,
            "kind": kind,
            "url": "/" + quote_path(rel),
            "thumb": f"/api/thumb?p={urllib.parse.quote(rel)}",
        }

    try:
        with os.scandir(folder) as it:
            for de in it:
                if scanned >= int(CONFIG.folder_preview_scan_limit):
                    break
                scanned += 1
                name = de.name
                if should_hide_entry(folder, name):
                    continue
                try:
                    if not de.is_file(follow_symlinks=False):
                        continue
                    p = folder / name
                    kind = classify(p, False)
                    if kind == "image":
                        images.append(add_item(p, name, kind))
                        if len(images) >= int(CONFIG.folder_preview_max_items):
                            break
                    elif CONFIG.folder_preview_include_video and kind == "video" and len(videos) < int(CONFIG.folder_preview_max_items):
                        videos.append(add_item(p, name, kind))
                except Exception:
                    continue
    except Exception:
        images, videos = [], []

    # Prefer images. Only add video thumbs if image count is too low.
    items = (images + videos)[: int(CONFIG.folder_preview_max_items)]
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json_dumps(items), encoding="utf-8")
    except Exception:
        pass
    return items

def make_image_thumb(src: Path, dst: Path) -> bool:
    if not HAS_PIL:
        return False
    if src.suffix.lower() in {".svg", ".avif", ".heic", ".heif"}:
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((420, 420))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.save(dst, "JPEG", quality=82, optimize=True)
        return True
    except Exception:
        return False


def make_video_thumb(src: Path, dst: Path) -> bool:
    if not FFMPEG:
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "00:00:01.000", "-i", str(src),
            "-frames:v", "1", "-vf", "scale='min(420,iw)':-2", "-q:v", "3", str(dst)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "N/A"):
            return None
        return float(value)
    except Exception:
        return None

def _fps(value: str) -> str:
    try:
        if not value or value == "0/0":
            return ""
        a, b = value.split("/", 1)
        fps = float(a) / float(b)
        return f"{fps:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return ""

def bitrate_fmt(value: Any) -> str:
    try:
        n = int(float(value))
    except Exception:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} Mbps"
    if n >= 1_000:
        return f"{n / 1_000:.0f} kbps"
    return f"{n} bps"

def video_subtitle_sidecars(video: Path) -> List[Path]:
    found: List[Path] = []
    try:
        parent = video.parent
        stem = video.stem
        for ext in sorted(SUBTITLE_EXTS):
            p = parent / f"{stem}{ext}"
            if p.is_file():
                found.append(p)
        for p in parent.glob(stem + ".*"):
            try:
                if p.is_file() and p.suffix.lower() in SUBTITLE_EXTS and p not in found:
                    found.append(p)
            except Exception:
                continue
    except Exception:
        pass
    return found[:12]

def srt_to_vtt(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    if text.lstrip().startswith("WEBVTT"):
        return text
    text = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    return "WEBVTT\n\n" + text.strip() + "\n"

def _ass_time_to_vtt(t: str) -> str:
    try:
        h, m, rest = t.strip().split(":", 2)
        s, cs = rest.split(".", 1)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int(cs[:2]) * 10:03d}"
    except Exception:
        return "00:00:00.000"

def ass_to_vtt(text: str) -> str:
    out = ["WEBVTT", ""]
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start, end, body = parts[1], parts[2], parts[9]
        body = re.sub(r"\{.*?\}", "", body).replace("\\N", "\n").replace("\\n", "\n")
        if body.strip():
            out.append(f"{_ass_time_to_vtt(start)} --> {_ass_time_to_vtt(end)}")
            out.append(body.strip())
            out.append("")
    return "\n".join(out).strip() + "\n"

def subtitle_to_vtt(path: Path) -> str:
    data = path.read_bytes()[: 4 * 1024 * 1024]
    text = data.decode("utf-8-sig", "replace")
    ext = path.suffix.lower()
    if ext == ".vtt":
        return text if text.lstrip().startswith("WEBVTT") else "WEBVTT\n\n" + text
    if ext == ".srt":
        return srt_to_vtt(text)
    if ext in {".ass", ".ssa"}:
        return ass_to_vtt(text)
    return "WEBVTT\n\n" + text

def ffprobe_video_info(path: Path) -> Dict[str, Any]:
    if not FFPROBE:
        return {}
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, timeout=12, errors="replace")
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout or "{}")
    except Exception:
        return {}
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    astream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = _float_or_none(vstream.get("duration")) or _float_or_none(fmt.get("duration"))
    bitrate = vstream.get("bit_rate") or fmt.get("bit_rate")
    return {
        "duration": duration, "width": vstream.get("width"), "height": vstream.get("height"),
        "video_codec": vstream.get("codec_name") or "", "audio_codec": astream.get("codec_name") or "",
        "fps": _fps(vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or ""),
        "bitrate": int(float(bitrate)) if bitrate not in (None, "", "N/A") else None,
        "bitrateText": bitrate_fmt(bitrate), "container": fmt.get("format_name") or "",
    }

def video_info(path: Path) -> Dict[str, Any]:
    st = path.stat()
    rel = path.resolve().relative_to(CONFIG.root.resolve()).as_posix()
    info: Dict[str, Any] = {"ok": True, "name": path.name, "rel": rel, "size": st.st_size, "sizeText": size_fmt(st.st_size), "mtime": st.st_mtime, "mtimeText": mtime_fmt(st.st_mtime), "mime": mimetypes.guess_type(str(path))[0] or "application/octet-stream", "ffprobe": bool(FFPROBE)}
    info.update(ffprobe_video_info(path))
    subtitles = []
    for idx, sub in enumerate(video_subtitle_sidecars(path)):
        try:
            srel = sub.resolve().relative_to(CONFIG.root.resolve()).as_posix()
            lang = sub.stem[len(path.stem):].strip("._-") or f"s{idx}"
            subtitles.append({"name": sub.name, "rel": srel, "label": lang or sub.name, "lang": re.sub(r"[^A-Za-z0-9_-]+", "", lang)[:16] or f"s{idx}", "ext": sub.suffix.lower(), "url": f"/api/subtitle?p={urllib.parse.quote(rel)}&i={idx}"})
        except Exception:
            continue
    info["subtitles"] = subtitles
    return info


def breadcrumb(rel_path: str) -> str:
    rel_path = rel_path.strip("/")
    parts = [] if not rel_path else rel_path.split("/")
    out = [f'<a href="/">Root</a>']
    acc = []
    for p in parts:
        acc.append(p)
        out.append(f'<span>/</span><a href="/{quote_path("/".join(acc))}/">{html_escape(p)}</a>')
    return "".join(out)


CSS = r"""
:root{color-scheme:dark;--bg:#090b10;--panel:#11141b;--panel2:#111827;--line:#374151;--text:#f8fafc;--muted:#cbd5e1;--accent:#68e37a;--accent2:#8db4ff;--danger:#ff5d5d;--warn:#ffbf63;--shadow:0 18px 48px rgba(0,0,0,.32)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#142017 0,#090b10 36%,#06070a 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;overflow-x:hidden}a{color:inherit;text-decoration:none}button,input,textarea{font:inherit}.app{min-height:100vh;display:flex;flex-direction:column}.top{position:sticky;top:0;z-index:30;background:rgba(9,11,16,.82);backdrop-filter:blur(18px);border-bottom:1px solid rgba(255,255,255,.08)}.top-inner{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:12px 14px}.brand{display:flex;align-items:center;gap:10px;min-width:0}.logo{width:36px;height:36px;border-radius:14px;background:linear-gradient(135deg,#61ff75,#8bb6ff);display:grid;place-items:center;color:#061007;font-weight:900;box-shadow:0 10px 30px rgba(104,227,122,.2)}.brand-title{font-weight:850;white-space:nowrap}.brand-sub{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:36vw}.search{min-width:140px}.search input{width:100%;height:40px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.05);color:var(--text);padding:0 14px;outline:none}.search input:focus{border-color:rgba(104,227,122,.75);box-shadow:0 0 0 4px rgba(104,227,122,.1)}.actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.btn{height:38px;padding:0 13px;border:1px solid rgba(255,255,255,.1);border-radius:13px;background:var(--panel2);color:var(--text);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;font-weight:750;transition:.12s}.btn:hover{transform:translateY(-1px);border-color:rgba(255,255,255,.2);background:#1b2230}.btn:active{transform:translateY(0)}.btn.primary{background:linear-gradient(135deg,#54ee69,#7eaaff);color:#061007;border:0}.btn.danger{background:#28171a;color:#ffd6d6;border-color:#653238}.btn.warn{background:#2a2111;color:#ffe2b3;border-color:#604819}.btn.ghost{background:transparent}.btn.small{height:31px;padding:0 10px;border-radius:10px;font-size:12px}.select{height:31px;border:1px solid rgba(255,255,255,.18);border-radius:10px;background:#111827;color:#f8fafc;padding:0 10px;font-weight:700;outline:none;color-scheme:dark}.select.compact{max-width:105px}.checkline{height:31px;display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(255,255,255,.1);border-radius:10px;background:var(--panel2);padding:0 10px;font-weight:700;font-size:12px;color:var(--text);user-select:none}.checkline input{accent-color:var(--accent)}.crumbs{display:flex;gap:7px;align-items:center;overflow:auto;padding:0 14px 12px;color:var(--muted);white-space:nowrap}.crumbs a{color:var(--text);background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);padding:5px 9px;border-radius:10px}.crumbs span{color:#596272}.notice{margin:14px 14px 0;padding:10px 12px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:rgba(255,255,255,.04);color:var(--muted);display:flex;justify-content:space-between;gap:10px;align-items:center}.notice b{color:var(--text)}.main{padding:14px;display:flex;flex-direction:column;gap:12px}.toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.toolbar .grow{flex:1}.view-toggle{display:flex;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:3px}.view-toggle button{border:0;background:transparent;color:var(--muted);height:30px;padding:0 10px;border-radius:10px;cursor:pointer}.view-toggle button.active{background:#242b38;color:#fff}.dropzone{border:1px dashed rgba(255,255,255,.14);border-radius:20px;background:rgba(255,255,255,.035);min-height:55vh;padding:12px;transition:.12s}.dropzone.drag{border-color:var(--accent);background:rgba(104,227,122,.08)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}.grid.list{display:flex;flex-direction:column}.card{position:relative;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(17,20,27,.9);overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.14);transition:.1s;min-width:0}.card:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.18)}.card.selected{outline:2px solid var(--accent);outline-offset:0}.card-main{display:block;cursor:pointer}.grid:not(.list) .thumbwrap{height:128px;display:grid;place-items:center;background:#080a0e;position:relative}.thumb{width:100%;height:100%;object-fit:cover;display:block}.fileicon{font-size:42px;filter:drop-shadow(0 12px 24px rgba(0,0,0,.25))}.meta{padding:10px;min-width:0}.name{font-weight:760;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sub{margin-top:4px;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.badge{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.12);color:#fff;border-radius:999px;font-size:11px;padding:3px 7px;font-weight:800}.check{position:absolute;top:8px;left:8px;width:28px;height:28px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:rgba(0,0,0,.45);z-index:4;display:grid;place-items:center;cursor:pointer}.selected .check{background:var(--accent);color:#061007;border-color:var(--accent)}.selected .check:after{content:'✓';font-weight:900}.grid.list .card{display:grid;grid-template-columns:44px 1fr auto;align-items:center;border-radius:14px}.grid.list .thumbwrap{height:44px;display:grid;place-items:center;background:#10141c}.grid.list .thumb{width:44px;height:44px}.grid.list .fileicon{font-size:24px}.grid.list .meta{padding:8px 10px}.grid.list .badge{position:static;margin-right:10px}.grid.list .check{top:8px;left:8px;width:24px;height:24px}.empty{height:45vh;display:grid;place-items:center;color:var(--muted);text-align:center}.loader{grid-column:1/-1;padding:18px;text-align:center;color:var(--muted)}.skeleton{height:190px;border-radius:18px;background:linear-gradient(90deg,rgba(255,255,255,.04),rgba(255,255,255,.08),rgba(255,255,255,.04));background-size:200% 100%;animation:shimmer 1.2s infinite}@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}.modal{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:100;display:none;align-items:center;justify-content:center;padding:12px}.modal.show{display:flex}.modal-box{width:min(1200px,98vw);max-height:96vh;background:#0c0f15;border:1px solid rgba(255,255,255,.12);border-radius:22px;box-shadow:var(--shadow);overflow:hidden;display:flex;flex-direction:column}.modal-head{height:54px;display:flex;align-items:center;gap:10px;justify-content:space-between;padding:0 12px;border-bottom:1px solid rgba(255,255,255,.08)}.modal-title{font-weight:800;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.modal-body{display:grid;place-items:center;min-height:40vh;overflow:auto;background:#050608}.modal-body img,.modal-body video{max-width:100%;max-height:calc(96vh - 56px);background:#000}.modal-body audio{width:min(760px,92vw)}.editor{min-height:calc(100vh - 1px);display:flex;flex-direction:column}.editorbar{position:sticky;top:0;z-index:10;display:flex;gap:8px;align-items:center;padding:10px;background:#0c0f15;border-bottom:1px solid rgba(255,255,255,.08)}.editorbar .title{font-weight:800;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.editorbar .grow{flex:1}.editarea{flex:1;width:100%;min-height:70vh;background:#07090d;color:#f5f7fb;border:0;outline:0;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:14px;line-height:1.55;resize:none}.toast{position:fixed;right:14px;bottom:14px;z-index:200;display:flex;flex-direction:column;gap:8px}.toast div{background:#111823;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:10px 12px;box-shadow:var(--shadow);color:#fff}.progress{height:8px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;min-width:160px}.progress span{display:block;height:100%;width:0;background:linear-gradient(90deg,#61ff75,#8bb6ff)}.hidden{display:none!important}@media(max-width:760px){.top-inner{grid-template-columns:1fr}.brand-sub{max-width:80vw}.actions{justify-content:flex-start}.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}.grid:not(.list) .thumbwrap{height:108px}.btn .label{display:none}}



/* --- recursive search selector --- */
.search{display:flex;align-items:center;min-width:220px}
.search-depth{height:40px;max-width:86px;border:1px solid var(--line);border-right:0;border-radius:14px 0 0 14px;background:#111827;color:#f8fafc;padding:0 8px;outline:none;font-weight:800;cursor:pointer;color-scheme:dark}
.search input{border-radius:0 14px 14px 0!important}
.search-depth option,.select option{background:#111827;color:#f8fafc}
.search-depth:focus,.search input:focus{border-color:rgba(104,227,122,.75);box-shadow:0 0 0 4px rgba(104,227,122,.1)}
@media(max-width:760px){.search{min-width:0}.search-depth{max-width:78px;padding:0 6px}}
/* --- media viewer / video player mode --- */
.modal.media-video .modal-box{width:min(1320px,98vw)}
.modal.media-video .modal-body{background:#000}
.modal-stage{position:relative;min-height:40vh;background:#050608}.modal-body{position:relative;touch-action:pan-y;overscroll-behavior:contain}
.modal-title-wrap{min-width:0;display:flex;flex-direction:column;gap:2px}.modal-meta{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.modal-head .actions{flex-wrap:nowrap}.modal-head .btn:disabled,.modal-nav:disabled{opacity:.35;cursor:default;transform:none}.modal-nav{position:absolute;top:50%;transform:translateY(-50%);z-index:3;width:46px;height:70px;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(0,0,0,.45);color:#fff;font-size:34px;font-weight:900;display:grid;place-items:center;cursor:pointer;backdrop-filter:blur(8px)}.modal-nav:hover:not(:disabled){background:rgba(255,255,255,.12)}.modal-prev{left:12px}.modal-next{right:12px}.modal-body img{user-select:none;-webkit-user-drag:none}.modal-body video{width:min(1280px,100%);height:auto}.media-hint{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);background:rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:5px 10px;color:var(--muted);font-size:12px;pointer-events:none}.modal.media-video .media-hint{display:none}@media(max-width:760px){.modal{padding:0}.modal-box{width:100vw;height:100dvh;max-height:none;border-radius:0;border-left:0;border-right:0}.modal-head{height:auto;min-height:54px}.modal-body{min-height:calc(100dvh - 54px)}.modal-body img,.modal-body video{max-height:calc(100dvh - 56px)}.modal-nav{display:none}.modal-meta{font-size:11px}.modal-head .btn.small{height:30px;padding:0 9px}}

.video-wrap{width:100%;display:flex;flex-direction:column;align-items:center;background:#000}.video-wrap video{width:100%;max-height:calc(96vh - 150px);background:#000}.video-panel{width:100%;padding:10px 12px;background:#080b10;border-top:1px solid rgba(255,255,255,.08);color:var(--muted);font-size:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:7px}.video-panel b{color:var(--text)}.video-panel .wide{grid-column:1/-1}.video-panel .video-actions{display:flex;gap:7px;flex-wrap:wrap}.video-panel .chip{display:inline-flex;align-items:center;min-height:26px;padding:4px 8px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:#111827;color:#f8fafc;text-decoration:none;font-weight:750}

/* --- vNext stability patch: thumbnail/folder/upload styles --- */
body.thumb-contain .thumb,
body.thumb-contain .folder-mosaic img{object-fit:contain;background:#000}
body.thumb-cover .thumb,
body.thumb-cover .folder-mosaic img{object-fit:cover;background:#000}
.thumbwrap{overflow:hidden}
.grid:not(.list) .card{min-height:190px}
.grid:not(.list) .card-main{height:100%;display:flex;flex-direction:column}
.grid:not(.list) .thumbwrap{flex:0 0 128px}
.grid:not(.list) .meta{background:rgba(17,20,27,.92);border-top:1px solid rgba(255,255,255,.04)}
.folder-mosaic{width:100%;height:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:1px;background:#050608;overflow:hidden}
.folder-mosaic.empty{display:grid;grid-template-columns:1fr;grid-template-rows:1fr;place-items:center;background:#080a0e}
.folder-mosaic.empty .fileicon{font-size:46px;opacity:.95}
.folder-mosaic .cell{min-width:0;min-height:0;display:grid;place-items:center;background:#000;overflow:hidden;transform:translateZ(0)}
.folder-mosaic .cell img{width:100%;height:100%;display:block;object-fit:contain;background:#000;will-change:opacity,transform}
.folder-mosaic.none .cell img{animation:none}
.folder-mosaic.fade .cell img{animation:fpFade .22s ease-out both}
.folder-mosaic.slide .cell img{animation:fpSlide .24s ease-out both}
.folder-mosaic.flip .cell img{animation:fpFlip .26s ease-out both;backface-visibility:hidden}
@keyframes fpFade{from{opacity:.35}to{opacity:1}}
@keyframes fpSlide{from{opacity:.55;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes fpFlip{from{opacity:.4;transform:rotateY(80deg)}to{opacity:1;transform:rotateY(0)}}
@media (prefers-reduced-motion:reduce){.folder-mosaic .cell img,.btn,.card,.skeleton{animation:none!important;transition:none!important}}
.upload-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:110;display:none;align-items:center;justify-content:center;padding:14px;backdrop-filter:blur(8px)}
.upload-backdrop.show{display:flex}
.upload-box{width:min(900px,96vw);max-height:92vh;background:#0d1118;border:1px solid rgba(255,255,255,.12);border-radius:22px;box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden}
.upload-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:14px;border-bottom:1px solid rgba(255,255,255,.08)}
.upload-title{font-weight:850;font-size:16px}.upload-body{padding:14px;overflow:auto;display:flex;flex-direction:column;gap:12px}.upload-drop{min-height:190px;border:2px dashed rgba(255,255,255,.16);border-radius:20px;background:rgba(255,255,255,.035);display:grid;place-items:center;text-align:center;color:var(--muted);cursor:pointer;transition:.12s}.upload-drop:hover,.upload-drop.drag{border-color:var(--accent);background:rgba(104,227,122,.08);color:var(--text)}.upload-plus{font-size:52px;line-height:1;color:var(--accent);font-weight:900}.upload-options{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.upload-queue{border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:auto;max-height:260px;background:#080b10}.upload-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.055);font-size:12px}.upload-row:last-child{border-bottom:0}.upload-path{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.upload-state{color:var(--muted);white-space:nowrap}.upload-state.ok{color:var(--accent)}.upload-state.err{color:var(--danger)}.upload-foot{display:flex;gap:10px;align-items:center;padding:12px 14px;border-top:1px solid rgba(255,255,255,.08);flex-wrap:wrap}.upload-summary{color:var(--muted);font-size:12px;min-width:160px}.upload-progress{height:8px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;flex:1;min-width:180px}.upload-progress span{display:block;height:100%;width:0;background:linear-gradient(90deg,#61ff75,#8bb6ff)}
.grid.list .folder-mosaic{width:44px;height:44px}.grid.list .folder-mosaic.empty .fileicon{font-size:24px}.grid.list .card-main{display:contents}.grid.list .meta{border-top:0;background:transparent}
.ctx-menu{position:fixed;z-index:230;min-width:190px;padding:6px;border:1px solid rgba(255,255,255,.14);border-radius:14px;background:#0d121b;box-shadow:0 18px 54px rgba(0,0,0,.5);display:flex;flex-direction:column;gap:2px}.ctx-menu.hidden{display:none}.ctx-menu button{height:32px;border:0;border-radius:9px;background:transparent;color:var(--text);display:flex;align-items:center;gap:8px;padding:0 10px;text-align:left;cursor:pointer;font-weight:720}.ctx-menu button:hover{background:#1a2230}.ctx-menu button.danger{color:#ffd2d2}.ctx-menu button.hidden{display:none}

/* compact grid + cleaner list mode */
.grid{grid-template-columns:repeat(auto-fill,minmax(126px,1fr));gap:10px}.dropzone{padding:10px;border-radius:18px}.grid:not(.list) .card{border-radius:15px;min-height:162px}.grid:not(.list) .thumbwrap{height:104px;flex:0 0 104px}.grid:not(.list) .meta{padding:8px 9px}.grid:not(.list) .fileicon{font-size:34px}.grid:not(.list) .name{font-size:13px}.grid:not(.list) .sub{font-size:11px}.grid:not(.list) .check{width:25px;height:25px;border-radius:9px;top:7px;left:7px}.grid:not(.list) .badge{top:7px;right:7px;font-size:10px;padding:2px 6px}
.grid.list{gap:6px}.grid.list .card{display:grid;grid-template-columns:30px 44px minmax(0,1fr) auto;gap:9px;align-items:center;min-height:58px;padding:6px 10px;border-radius:13px;background:rgba(17,20,27,.78);box-shadow:none;overflow:visible}.grid.list .card:hover{transform:none;background:rgba(24,31,43,.9);border-color:rgba(255,255,255,.16)}.grid.list .card.selected{outline:1px solid var(--accent);box-shadow:inset 3px 0 0 var(--accent)}.grid.list .check{position:static;grid-column:1;grid-row:1;width:24px;height:24px;border-radius:8px;background:rgba(255,255,255,.055);justify-self:center}.grid.list .card-main{display:contents}.grid.list .thumbwrap{grid-column:2;grid-row:1;width:44px;height:44px;border-radius:11px;display:grid;place-items:center;background:#0b1018}.grid.list .thumb{width:44px;height:44px;border-radius:11px}.grid.list .folder-mosaic{grid-column:2;grid-row:1;width:44px;height:44px;border-radius:11px}.grid.list .folder-mosaic.empty .fileicon,.grid.list .fileicon{font-size:23px}.grid.list .meta{grid-column:3;grid-row:1;min-width:0;padding:0;background:transparent;border-top:0}.grid.list .name{font-size:14px;font-weight:760}.grid.list .sub{font-size:12px;margin-top:2px}.grid.list .badge{grid-column:4;grid-row:1;position:static;margin:0;justify-self:end;align-self:center;background:rgba(255,255,255,.075);color:var(--muted);max-width:96px;overflow:hidden;text-overflow:ellipsis}.grid.list .skeleton{height:58px;border-radius:13px}
@media(max-width:760px){.grid{grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px}.grid:not(.list) .thumbwrap{height:92px;flex-basis:92px}.grid:not(.list) .card{min-height:146px}.grid.list .card{grid-template-columns:28px 40px minmax(0,1fr);padding:6px 8px}.grid.list .thumbwrap,.grid.list .thumb,.grid.list .folder-mosaic{width:40px;height:40px}.grid.list .badge{display:none}}

.term-drawer{position:fixed;left:14px;right:14px;bottom:14px;z-index:80;display:none;flex-direction:column;min-height:240px;max-height:88vh;background:linear-gradient(180deg,rgba(8,13,10,.98),rgba(3,5,8,.98));border:1px solid rgba(104,227,122,.34);border-radius:18px;box-shadow:0 22px 80px rgba(0,0,0,.62);overflow:hidden;resize:vertical}
.term-drawer.show{display:flex}.term-drawer.full{inset:10px;height:auto!important;max-height:none}.term-head{min-height:45px;display:flex;align-items:center;gap:10px;justify-content:space-between;padding:7px 9px 7px 13px;background:linear-gradient(180deg,rgba(104,227,122,.13),rgba(255,255,255,.025));border-bottom:1px solid rgba(104,227,122,.22)}.term-title{font-weight:850;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.term-mode{margin-left:8px;color:#7dff93;font-size:12px}.term-cwd{margin-left:10px;color:#b6c6b8;font-size:12px;font-weight:650}.term-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.term-screen{flex:1;margin:0;padding:14px 16px;background:linear-gradient(180deg,#000503,#02060a);color:#dfffe6;font:14px/1.55 "Cascadia Mono","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;overflow:auto;white-space:pre;word-break:normal;outline:none;tab-size:4;letter-spacing:0;text-rendering:geometricPrecision;scrollbar-color:rgba(104,227,122,.42) rgba(255,255,255,.05)}.term-screen:empty::before{content:"Terminal chưa có output. Bấm New hoặc gõ lệnh khi cursor đang ở khung này.";color:#6f7f78}.term-screen:focus{box-shadow:inset 0 0 0 1px rgba(104,227,122,.42)}.term-command{display:flex;align-items:center;gap:8px;padding:9px 11px;border-top:1px solid rgba(104,227,122,.18);background:#05090c}.term-command.hidden{display:none}.term-command span{font:13px ui-monospace,monospace;color:#7dff93;white-space:nowrap}.term-command input{flex:1;background:transparent;color:#f6fff7;border:0;outline:0;font:13px ui-monospace,monospace}.term-keys{display:none;gap:5px;align-items:center;overflow:auto;padding:7px;border-top:1px solid rgba(255,255,255,.07);background:#070a0f}.term-keys button{border:1px solid rgba(255,255,255,.14);background:#121821;color:#f6fff7;border-radius:9px;padding:6px 10px;font-weight:800}@media(max-width:720px){
.term-drawer{left:6px;right:6px;bottom:6px;height:54vh!important}.term-actions .btn{height:28px;padding:0 8px}.term-cwd{display:none}.term-keys{display:flex}.terminal-btn .label{display:none}}

"""

JS = r"""
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
const defaults = window.APP?.defaults || {};
const prefKey = k => 'lanDrive:' + k;
function pref(k, fallback){ const v = localStorage.getItem(prefKey(k)); return v === null ? fallback : v; }
const state = {
  selected:new Set(),
  view:pref('view', defaults.default_view || 'grid'),
  sort:pref('sort', defaults.default_sort || 'name-asc'),
  items:[], offset:0,
  limit:Number(pref('page_limit', defaults.page_limit || 220)),
  foldersFirst:String(pref('folders_first', defaults.folders_first === false ? 'false' : 'true')) !== 'false',
  recursiveDepth:pref('recursive_depth', '0'),
  thumbFit:pref('thumb_fit', defaults.thumb_fit || 'contain'),
  folderPreview:String(pref('folder_preview_enabled', defaults.folder_preview_enabled === false ? 'false' : 'true')) !== 'false',
  previewAnimation:pref('folder_preview_animation', defaults.folder_preview_animation || 'fade'),
  uploadConflict:pref('upload_conflict', defaults.upload_conflict || 'ask'),
  uploadParallel:Number(pref('upload_parallel', defaults.upload_parallel || 3)),
  uploadAutoStart:String(pref('upload_auto_start', defaults.upload_auto_start ? 'true' : 'false')) === 'true',
  pluginEnabled:!!(window.APP?.plugin?.enabled),
  hasMore:true, loading:false, searchTimer:null
};
document.body.classList.add('thumb-'+(state.thumbFit==='cover'?'cover':'contain'));
const grid=$('#grid'), q=$('#q'), toastBox=$('#toast');
const emptyHTML='<div class="empty"><div><div style="font-size:42px">🫙</div><p>Không có mục phù hợp.</p><p>Kéo file/folder vào đây hoặc bấm Upload.</p></div></div>';
function toast(msg){ if(!toastBox){console.log(msg);return} const el=document.createElement('div');el.textContent=msg;toastBox.appendChild(el);setTimeout(()=>el.remove(),3200) }
function enc(s){return encodeURIComponent(s).replace(/%2F/g,'/')}
function currentPath(){return window.APP?.currentPath||''}
function selectedArray(){return Array.from(state.selected)}
function cachePrefix(){return 'lanDrive:list:'+location.pathname+':'}
function cacheKey(){return cachePrefix()+state.sort+':'+state.limit+':'+state.recursiveDepth+':'+(q?.value||'')}
function scrollKey(){return 'lanDrive:scroll:'+location.pathname}
function clearFolderCache(){try{const p=cachePrefix(); Object.keys(sessionStorage).forEach(k=>{if(k.startsWith(p))sessionStorage.removeItem(k)})}catch(e){}}
let prefSaveTimer=null;
function savePrefs(patch){
  Object.entries(patch||{}).forEach(([k,v])=>localStorage.setItem(prefKey(k), String(v)));
  clearTimeout(prefSaveTimer);
  prefSaveTimer=setTimeout(()=>fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)}).catch(()=>{}),180);
}
function applyView(){ if(!grid)return; grid.classList.toggle('list',state.view==='list');$$('.view-toggle button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));localStorage.setItem(prefKey('view'),state.view)}
function setView(v){state.view=v;applyView();savePrefs({default_view:v})}
function syncControls(){
  const s=$('#sortSelect'), l=$('#limitSelect'), f=$('#foldersFirst'), rd=$('#recursiveDepth'), tf=$('#thumbFit'), fp=$('#folderPreviewToggle'), anim=$('#previewAnim'), uc=$('#uploadConflict');
  if(s)s.value=state.sort; if(l)l.value=String(state.limit); if(f)f.checked=!!state.foldersFirst; if(rd)rd.value=state.recursiveDepth;
  if(tf)tf.value=state.thumbFit; if(fp)fp.checked=!!state.folderPreview; if(anim)anim.value=state.previewAnimation; if(uc)uc.value=state.uploadConflict;
}
function changeThumbFit(sel){state.thumbFit=sel.value==='cover'?'cover':'contain';document.body.classList.toggle('thumb-cover',state.thumbFit==='cover');document.body.classList.toggle('thumb-contain',state.thumbFit!=='cover');savePrefs({thumb_fit:state.thumbFit,folder_preview_fit:state.thumbFit});refreshFolder()}
function toggleFolderPreview(el){state.folderPreview=!!el.checked;savePrefs({folder_preview_enabled:state.folderPreview});refreshFolder()}
function changePreviewAnimation(sel){state.previewAnimation=sel.value||'fade';savePrefs({folder_preview_animation:state.previewAnimation});setupFolderPreviews()}
function changeUploadConflict(sel){state.uploadConflict=sel.value||'ask';savePrefs({upload_conflict:state.uploadConflict})}
function updateSelectionUI(){ if(!grid)return; $$('.card').forEach(c=>c.classList.toggle('selected',state.selected.has(c.dataset.rel))); const n=state.selected.size; const count=$('#selCount'); if(count)count.textContent=n?`${n} selected`:(state.loading?'Đang tải...':`${Math.max(0,state.items.filter(x=>!x.special).length)}${state.hasMore?'+':''} mục`); const one=n===1?document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0]||'')}"]`):null; const oneFile=!!(one&&one.dataset.isdir==='0'); const canPreview=!!(oneFile&&one.dataset.preview==='1'); $('#deleteBtn')?.classList.toggle('hidden',!n); $('#downloadBtn')?.classList.toggle('hidden',!n); $('#archiveBtn')?.classList.toggle('hidden',!n); $('#copyBtn')?.classList.toggle('hidden',!n); $('#moveBtn')?.classList.toggle('hidden',!n); $('#duplicateBtn')?.classList.toggle('hidden',!n); $('#batchRenameBtn')?.classList.toggle('hidden',!n); $('#extractBtn')?.classList.toggle('hidden',n!==1); $('#renameBtn')?.classList.toggle('hidden',n!==1); $('#shareBtn')?.classList.toggle('hidden',n!==1); $('#previewBtn')?.classList.toggle('hidden',!canPreview); }
function toggleSelect(rel,ev){if(ev){ev.preventDefault();ev.stopPropagation()} closeContextMenu(); if(!rel)return; if(state.selected.has(rel))state.selected.delete(rel);else state.selected.add(rel);updateSelectionUI()}
function clearSel(){state.selected.clear();updateSelectionUI()}
function selectVisible(){$$('.card:not(.hidden)').forEach(c=>{if(c.dataset.rel)state.selected.add(c.dataset.rel)});updateSelectionUI()}
function closeContextMenu(){const m=$('#ctxMenu'); if(m)m.classList.add('hidden')}
function ensureContextSelection(card){const rel=card?.dataset?.rel||''; if(!rel)return ''; if(!state.selected.has(rel)){state.selected.clear();state.selected.add(rel);updateSelectionUI()} return rel}
function openContextMenu(ev,card){
  ev.preventDefault();ev.stopPropagation();const rel=ensureContextSelection(card);if(!rel)return;
  const m=$('#ctxMenu'); if(!m)return; m.dataset.rel=rel;
  const arr=selectedArray(); const one=arr.length===1; const c=one?document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`):null;
  const oneFile=!!(c&&c.dataset.isdir==='0'), oneText=!!(oneFile&&c.dataset.kind==='text'), canPreview=!!(oneFile&&c.dataset.preview==='1');
  m.querySelector('[data-act="open"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="preview"]')?.classList.toggle('hidden',!canPreview);
  m.querySelector('[data-act="edit"]')?.classList.toggle('hidden',!oneText);
  m.querySelector('[data-act="rename"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="share"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="extract"]')?.classList.toggle('hidden',!one);
  const w=210,h=390; m.style.left=Math.max(8,Math.min(ev.clientX,innerWidth-w-8))+'px'; m.style.top=Math.max(8,Math.min(ev.clientY,innerHeight-h-8))+'px'; m.classList.remove('hidden');
}
function contextAction(action){
  closeContextMenu();
  if(action==='open'){const rel=selectedArray()[0];const c=rel&&document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`);if(c)openItem(c);return}
  if(action==='preview')return previewSelected();
  if(action==='edit'){const rel=selectedArray()[0];if(rel)location.href=fileUrl(rel)+'?edit=1';return}
  if(action==='rename')return renameOne();
  if(action==='share')return shareOne();
  if(action==='download')return downloadSelected();
  if(action==='archive')return archiveSelected();
  if(action==='extract')return extractSelected();
  if(action==='copy')return copySel();
  if(action==='move')return moveSel();
  if(action==='duplicate')return duplicateSel();
  if(action==='batch')return batchRenameSel();
  if(action==='delete')return deleteSel();
}
function cardHTML(it){
  if(it.special==='back')return `<div class="card" data-rel="" data-name=".." data-size="0" data-mtime="0" data-isdir="1" data-kind="folder" data-rawname=".."><a class="card-main" href="${it.href}"><div class="thumbwrap"><div class="fileicon">↩️</div></div><div class="meta"><div class="name">Back</div><div class="sub">Parent folder</div></div></a></div>`;
  const badge=['video','audio','text','pdf'].includes(it.kind)?`<div class="badge">${it.kind.toUpperCase()}</div>`:'';
  let thumb='';
  if(it.kind==='folder' && state.folderPreview){
    thumb=`<div class="folder-mosaic empty ${state.previewAnimation}" data-folder-preview="${it.relEsc}" title="Folder preview"><div class="fileicon">📁</div></div>`;
  }else if(it.thumb){
    thumb=`<img class="thumb" loading="lazy" decoding="async" src="${it.thumb}" onerror="this.style.display='none';this.nextElementSibling.classList.remove('hidden')"><div class="fileicon hidden">${it.icon}</div>`;
  }else{ thumb=`<div class="fileicon">${it.icon}</div>`; }
  return `<div class="card" data-rel="${it.relEsc}" data-name="${it.nameLowerEsc}" data-size="${it.size}" data-mtime="${it.mtime}" data-isdir="${it.is_dir?'1':'0'}" data-kind="${it.kind}" data-preview="${it.preview?'1':'0'}" data-rawname="${it.nameEsc}" oncontextmenu="openContextMenu(event,this)"><button class="check" onclick="toggleSelect('${it.relJs}', event)" title="Select"></button>${badge}<div class="card-main" onclick="openItem(this.closest('.card'),event)"><div class="thumbwrap">${thumb}</div><div class="meta"><div class="name" title="${it.nameEsc}">${it.nameEsc}</div><div class="sub">${it.searchPathTextEsc?it.searchPathTextEsc+' · ':''}${it.sizeTextEsc} · ${it.mtimeTextEsc}</div></div></div></div>`
}
function ensureLoader(){ const old=$('#loader'); if(old)old.remove(); if(state.hasMore)grid.insertAdjacentHTML('beforeend','<div id="loader" class="loader">Cuộn xuống để tải thêm...</div>'); observeLoader(); }
function render(){ if(!grid)return; const old=$('#loader'); if(old)old.remove(); if(!state.items.length&&!state.loading){grid.innerHTML=emptyHTML;return} if(grid.querySelector('.empty')||grid.querySelector('.skeleton'))grid.innerHTML=''; grid.innerHTML=state.items.map(cardHTML).join(''); ensureLoader(); applyView(); updateSelectionUI(); setupFolderPreviews() }
function appendRender(newItems){ if(!grid)return; const old=$('#loader'); if(old)old.remove(); if(grid.querySelector('.empty')||grid.querySelector('.skeleton'))grid.innerHTML=''; if(newItems&&newItems.length)grid.insertAdjacentHTML('beforeend',newItems.map(cardHTML).join('')); ensureLoader(); applyView(); updateSelectionUI(); setupFolderPreviews() }
function saveListCache(){try{sessionStorage.setItem(cacheKey(),JSON.stringify({items:state.items,offset:state.offset,hasMore:state.hasMore,scrollY:window.scrollY,ts:Date.now()}))}catch(e){}}
function hydrateCache(){try{const raw=sessionStorage.getItem(cacheKey()); if(!raw)return false; const c=JSON.parse(raw); if(!Array.isArray(c.items))return false; state.items=c.items; state.offset=c.offset||c.items.length; state.hasMore=!!c.hasMore; render(); requestAnimationFrame(()=>window.scrollTo(0,c.scrollY||Number(sessionStorage.getItem(scrollKey())||0))); return true}catch(e){return false}}
window.addEventListener('pagehide',()=>{if(grid){sessionStorage.setItem(scrollKey(),String(window.scrollY));saveListCache()}});
async function loadMore(reset=false){ if(!grid||state.loading)return; if(reset){state.items=[];state.offset=0;state.hasMore=true;state.selected.clear();grid.innerHTML='<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>'} if(!state.hasMore)return; state.loading=true; updateSelectionUI(); const params=new URLSearchParams({path:currentPath(),offset:String(state.offset),limit:String(state.limit),sort:state.sort,q:q?.value||'',recursive_depth:(q?.value||'').trim()?state.recursiveDepth:'0',folders_first:String(state.foldersFirst)}); try{const r=await fetch('/api/list?'+params.toString(),{cache:'no-store'}); const j=await r.json(); if(!r.ok||j.error)throw new Error(j.error||r.statusText); const newItems=j.items||[]; if(reset)state.items=[]; state.items.push(...newItems); state.offset=j.nextOffset; state.hasMore=!!j.hasMore; if(reset)render(); else appendRender(newItems); saveListCache()}catch(e){grid.innerHTML=`<div class="empty"><div><div style="font-size:42px">⚠️</div><p>Lỗi tải thư mục</p><p>${String(e.message||e)}</p></div></div>`}finally{state.loading=false;updateSelectionUI()} }
let io=null; function observeLoader(){ if(!grid)return; if(io)io.disconnect(); const loader=$('#loader'); if(!loader)return; io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting))loadMore(false)},{rootMargin:'900px'}); io.observe(loader)}
function filterCards(){clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>{clearFolderCache();loadMore(true)}, Number(defaults.search_debounce_ms||240))} q?.addEventListener('input',filterCards);
function sortCards(mode){if(mode)state.sort=mode; syncControls(); savePrefs({default_sort:state.sort}); clearFolderCache(); loadMore(true)}
function changeSort(sel){sortCards(sel.value)}
function changeLimit(sel){state.limit=Number(sel.value||220); savePrefs({page_limit:state.limit}); clearFolderCache(); loadMore(true)}
function changeFoldersFirst(el){state.foldersFirst=!!el.checked; savePrefs({folders_first:state.foldersFirst}); clearFolderCache(); loadMore(true)}
function changeRecursiveDepth(sel){state.recursiveDepth=String(sel.value||'0');localStorage.setItem(prefKey('recursive_depth'),state.recursiveDepth);clearFolderCache();loadMore(true)}
function refreshFolder(){clearFolderCache();loadMore(true)}
const MEDIA_KINDS = new Set(['image','video','audio']);
const mediaState = {kind:null,current:null,items:[],index:-1,busy:false,touchX:0,touchY:0};
function isTypingTarget(el){return el&&['INPUT','TEXTAREA','SELECT'].includes(el.tagName)}
function isMediaKind(kind){return MEDIA_KINDS.has(kind)}
function findLoadedItem(rel){return state.items.find(it=>!it.special&&it.rel===rel)||null}
function normalizeMediaItem(src,kind,url,name,rel){
  const item=src||{};
  return {kind:item.kind||kind,rel:item.rel||rel||'',url:item.url||url||fileUrl(item.rel||rel||''),name:item.name||name||item.nameEsc||''};
}
function collectMediaItems(kind,fallback){
  const items=state.items.filter(it=>!it.special&&it.kind===kind).map(it=>normalizeMediaItem(it));
  if(fallback){
    const exists=items.some(it=>(fallback.rel&&it.rel===fallback.rel)||(fallback.url&&it.url===fallback.url));
    if(!exists)items.push(fallback);
  }
  return items;
}
function mediaLabel(kind){return kind==='image'?'Ảnh':kind==='video'?'Video':kind==='audio'?'Audio':'Media'}
function mediaUrl(it){return it?.url||fileUrl(it?.rel||'')}
function setModalNavState(){
  const len=mediaState.items.length, idx=mediaState.index;
  const canStep=len>1||(mediaState.kind&&state.hasMore);
  ['#modalPrevBtn','#modalNextBtn','#modalPrevFloat','#modalNextFloat'].forEach(sel=>{const b=$(sel);if(b)b.disabled=!canStep||mediaState.busy});
  const meta=$('#modalMeta');
  if(meta){
    const pos=len?`${Math.max(0,idx)+1}/${len}${state.hasMore?'+':''}`:'0/0';
    const tip=mediaState.kind==='image'?'Vuốt trái/phải hoặc dùng ←/→':'Nút Trước/Tiếp; Shift+←/→ để chuyển; video tự next khi hết';
    meta.textContent=`${mediaLabel(mediaState.kind)} · ${pos} · ${tip}`;
  }
}
function prefetchMediaAround(){
  const len=mediaState.items.length;
  if(len<2)return;
  [1,-1].forEach(delta=>{
    const it=mediaState.items[(mediaState.index+delta+len)%len];
    if(!it)return;
    const url=mediaUrl(it);
    if(it.kind==='image'){const img=new Image();img.decoding='async';img.src=url;}
    else if(it.kind==='video'){const v=document.createElement('video');v.preload='metadata';v.src=url;}
  });
}
function fmtTime(seconds){seconds=Number(seconds||0);if(!seconds)return'';const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60),s=Math.floor(seconds%60);return(h?String(h).padStart(2,'0')+':':'')+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')}
function addVideoPanelItem(panel,label,value){if(value===undefined||value===null||value==='')return;const div=document.createElement('div');div.innerHTML='<b>'+label+':</b> ';div.append(document.createTextNode(String(value)));panel.appendChild(div)}
async function loadVideoInfo(it,video,panel){
  if(!it?.rel||!panel)return;
  panel.innerHTML='<div class="wide">Đang đọc metadata video...</div>';
  try{
    const r=await fetch('/api/video_info?p='+encodeURIComponent(it.rel));
    const j=await r.json();
    if(!r.ok||j.error)throw new Error(j.error||r.statusText);
    panel.innerHTML='';
    addVideoPanelItem(panel,'File',j.name);
    addVideoPanelItem(panel,'Dung lượng',j.sizeText);
    addVideoPanelItem(panel,'Duration',fmtTime(j.duration));
    addVideoPanelItem(panel,'Resolution',j.width&&j.height?`${j.width}×${j.height}`:'');
    addVideoPanelItem(panel,'Video',j.video_codec);
    addVideoPanelItem(panel,'Audio',j.audio_codec);
    addVideoPanelItem(panel,'FPS',j.fps);
    addVideoPanelItem(panel,'Bitrate',j.bitrateText);
    if(Array.isArray(j.subtitles)&&j.subtitles.length){
      const wrap=document.createElement('div');wrap.className='wide video-actions';
      const label=document.createElement('span');label.className='chip';label.textContent='Subtitles';wrap.appendChild(label);
      j.subtitles.forEach((s,idx)=>{
        const track=document.createElement('track');track.kind='subtitles';track.label=s.label||s.name||('Sub '+(idx+1));track.srclang=s.lang||('s'+idx);track.src=s.url;if(idx===0)track.default=true;video.appendChild(track);
        const a=document.createElement('a');a.className='chip';a.href=s.url;a.target='_blank';a.textContent=s.name||('Sub '+(idx+1));wrap.appendChild(a);
      });
      panel.appendChild(wrap);
    }
    if(!j.ffprobe){const note=document.createElement('div');note.className='wide';note.textContent='ffprobe không có, chỉ hiển thị stat cơ bản.';panel.appendChild(note)}
  }catch(e){panel.innerHTML='<div class="wide">Không đọc được metadata video: '+e.message+'</div>'}
}
function renderMediaItem(it,index,opts={}){
  const modal=$('#modal'),body=$('#modalBody'),title=$('#modalTitle');
  if(!modal||!body||!it)return;
  mediaState.current=it;mediaState.kind=it.kind;mediaState.index=index;
  title.textContent=it.name||'';
  body.innerHTML='';
  modal.classList.toggle('media-image',it.kind==='image');
  modal.classList.toggle('media-video',it.kind==='video');
  modal.classList.toggle('media-audio',it.kind==='audio');
  if(it.kind==='image'){
    const img=document.createElement('img');img.src=mediaUrl(it);img.alt=it.name||'';img.draggable=false;body.appendChild(img);
    const hint=document.createElement('div');hint.className='media-hint';hint.textContent='Vuốt trái/phải hoặc dùng ←/→ để xem ảnh khác';body.appendChild(hint);
  }else if(it.kind==='video'){
    const wrap=document.createElement('div');wrap.className='video-wrap';
    const v=document.createElement('video');v.src=mediaUrl(it);v.controls=true;v.autoplay=opts.autoplay!==false;v.playsInline=true;v.preload='metadata';
    v.addEventListener('ended',()=>{if(mediaState.items.length>1)stepMedia(1)});
    const panel=document.createElement('div');panel.className='video-panel';
    wrap.appendChild(v);wrap.appendChild(panel);body.appendChild(wrap);
    loadVideoInfo(it,v,panel);
  }else if(it.kind==='audio'){
    const a=document.createElement('audio');a.src=mediaUrl(it);a.controls=true;a.autoplay=opts.autoplay!==false;a.preload='metadata';body.appendChild(a);
  }
  setModalNavState();prefetchMediaAround();
}
function openPreview(kind,url,name,rel=''){
  if(!isMediaKind(kind))return;
  const modal=$('#modal'); if(!modal)return;
  const loaded=findLoadedItem(rel);
  const fallback=normalizeMediaItem(loaded,kind,url,name,rel);
  mediaState.items=collectMediaItems(kind,fallback);
  const foundIndex=mediaState.items.findIndex(it=>(rel&&it.rel===rel)||it.url===url);
  mediaState.index=foundIndex>=0?foundIndex:mediaState.items.length-1;
  renderMediaItem(mediaState.items[mediaState.index]||fallback,mediaState.index,{autoplay:true});
  modal.classList.add('show');
}
async function stepMedia(delta,ev){
  if(ev&&ev.preventDefault){ev.preventDefault();ev.stopPropagation();}
  const modal=$('#modal');
  if(!modal?.classList.contains('show')||!mediaState.kind||mediaState.busy)return;
  let items=mediaState.items;
  if(!items.length)return;
  let currentIndex=items.findIndex(it=>(mediaState.current?.rel&&it.rel===mediaState.current.rel)||it.url===mediaState.current?.url);
  if(currentIndex>=0)mediaState.index=currentIndex;
  let next=mediaState.index+delta;
  if(delta>0&&next>=items.length&&state.hasMore&&!state.loading){
    mediaState.busy=true;setModalNavState();
    await loadMore(false);
    mediaState.items=collectMediaItems(mediaState.kind,mediaState.current);
    items=mediaState.items;
    currentIndex=items.findIndex(it=>(mediaState.current?.rel&&it.rel===mediaState.current.rel)||it.url===mediaState.current?.url);
    mediaState.index=currentIndex>=0?currentIndex:mediaState.index;
    next=mediaState.index+delta;
    mediaState.busy=false;setModalNavState();
  }
  if(!items.length)return;
  if(next<0)next=items.length-1;
  if(next>=items.length)next=0;
  if(next===mediaState.index&&items.length===1)return;
  renderMediaItem(items[next],next,{autoplay:true});
}
function closeModal(){const m=$('#modal'); if(!m)return; $('#modalBody').innerHTML='';m.classList.remove('show','media-image','media-video','media-audio');mediaState.kind=null;mediaState.current=null;mediaState.items=[];mediaState.index=-1;mediaState.busy=false}
function setupModalGestures(){
  const body=$('#modalBody'); if(!body||body.dataset.swipeReady)return; body.dataset.swipeReady='1';
  body.addEventListener('touchstart',e=>{const t=e.changedTouches[0];mediaState.touchX=t.clientX;mediaState.touchY=t.clientY},{passive:true});
  body.addEventListener('touchend',e=>{const t=e.changedTouches[0];const dx=t.clientX-mediaState.touchX,dy=t.clientY-mediaState.touchY;if(Math.abs(dx)>52&&Math.abs(dx)>Math.abs(dy)*1.35){e.preventDefault();stepMedia(dx<0?1:-1)}},{passive:false});
}
setupModalGestures();
document.addEventListener('keydown',e=>{
  const modalOpen=$('#modal')?.classList.contains('show');
  if(modalOpen){
    if(e.key==='Escape'){e.preventDefault();closeModal();return}
    if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!isTypingTarget(document.activeElement)){
      if(mediaState.kind==='image'||e.shiftKey){e.preventDefault();stepMedia(e.key==='ArrowRight'?1:-1);return}
    }
  }else if(e.key==='Escape'&&$('#uploadModal')?.classList.contains('show')){closeUploadDialog();return}
  if(grid&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'&&!isTypingTarget(document.activeElement)){e.preventDefault();selectVisible()}
});
document.addEventListener('click',e=>{if(!e.target.closest?.('#ctxMenu'))closeContextMenu()});
window.addEventListener('scroll',closeContextMenu,true);
async function api(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})});const j=await r.json().catch(()=>({}));if(!r.ok||j.error)throw new Error(j.error||`HTTP ${r.status}`);return j}
async function mkdir(){const name=prompt('Tên thư mục mới:');if(!name)return;try{await api('/api/mkdir',{path:currentPath(),name});clearFolderCache();loadMore(true)}catch(e){toast('Lỗi tạo thư mục: '+e.message)}}
async function newFile(){const name=prompt('Tên file mới, ví dụ notes.txt:');if(!name)return;try{const r=await api('/api/newfile',{path:currentPath(),name});location.href=r.edit_url}catch(e){toast('Lỗi tạo file: '+e.message)}}
async function renameOne(){const rel=selectedArray()[0];if(!rel)return;const old=rel.split('/').pop();const name=prompt('Đổi tên thành:',old);if(!name||name===old)return;try{await api('/api/rename',{path:rel,name});clearFolderCache();loadMore(true)}catch(e){toast('Lỗi rename: '+e.message)}}
async function copySel(){const arr=selectedArray();if(!arr.length)return;const dest=prompt(`Copy ${arr.length} mục đến thư mục:`,currentPath());if(dest===null)return;try{const r=await api('/api/copy',{paths:arr,dest,conflict:'rename'});toast(`Đã copy ${r.copied?.length||0} mục`);clearFolderCache();loadMore(true)}catch(e){toast('Lỗi copy: '+e.message)}}
async function moveSel(){const arr=selectedArray();if(!arr.length)return;const dest=prompt(`Move ${arr.length} mục đến thư mục:`,currentPath());if(dest===null)return;if(!confirm(`Move ${arr.length} mục đến /${dest}?`))return;try{const r=await api('/api/move',{paths:arr,dest,conflict:'rename'});toast(`Đã move ${r.moved?.length||0} mục`);clearFolderCache();loadMore(true)}catch(e){toast('Lỗi move: '+e.message)}}
async function duplicateSel(){const arr=selectedArray();if(!arr.length)return;try{const r=await api('/api/duplicate',{paths:arr,conflict:'rename'});toast(`Đã duplicate ${r.duplicated?.length||0} mục`);clearFolderCache();loadMore(true)}catch(e){toast('Lỗi duplicate: '+e.message)}}
async function batchRenameSel(){const arr=selectedArray();if(!arr.length)return;const find=prompt('Batch rename: tìm chuỗi trong tên file:','');if(find===null)return;const repl=prompt('Thay bằng:','');if(repl===null)return;const items=arr.map(path=>{const old=path.split('/').pop();return{path,name:old.split(find).join(repl)}}).filter(x=>x.name&&x.name!==x.path.split('/').pop());if(!items.length){toast('Không có tên nào thay đổi');return}try{const r=await api('/api/batch_rename',{items});toast(`Đã rename ${r.renamed?.length||0} mục`);clearFolderCache();loadMore(true)}catch(e){toast('Lỗi batch rename: '+e.message)}}
async function extractSelected(){const arr=selectedArray();if(arr.length!==1){toast('Chọn đúng 1 archive để extract');return}const dest=prompt('Extract đến thư mục:',currentPath());if(dest===null)return;try{const r=await api('/api/extract',{path:arr[0],dest,conflict:'rename'});toast(`Extract xong: ${r.written||0} file`);clearFolderCache();loadMore(true)}catch(e){toast('Lỗi extract: '+e.message)}}
function submitArchive(paths,format='zip',compression='compress'){const arr=paths||selectedArray();if(!arr.length)return;const form=document.createElement('form');form.method='POST';form.action='/api/archive';const input=document.createElement('input');input.name='payload';input.value=JSON.stringify({paths:arr,format,compression});form.appendChild(input);document.body.appendChild(form);form.submit();form.remove()}
function downloadZip(paths){submitArchive(paths||selectedArray(),'zip','compress')}
function archiveSelected(){const arr=selectedArray();if(!arr.length)return;let format=(prompt('Archive format: zip hoặc tar','zip')||'zip').trim().toLowerCase();if(!['zip','tar'].includes(format)){toast('Format phải là zip hoặc tar');return}let compression=(prompt('Compression: compress hoặc store','compress')||'compress').trim().toLowerCase();if(!['compress','store'].includes(compression)){toast('Compression phải là compress hoặc store');return}submitArchive(arr,format,compression)}
function downloadSelected(){const arr=selectedArray();if(!arr.length)return; if(arr.length===1){const card=document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`); if(card&&card.dataset.isdir==='0'){location.href='/'+enc(arr[0])+'?download=1'; return}} submitArchive(arr,'zip','compress')}
async function deleteSel(){const arr=selectedArray();if(!arr.length)return;if(!confirm(`Xoá vĩnh viễn ${arr.length} mục?`))return;try{await api('/api/delete',{paths:arr});clearFolderCache();loadMore(true)}catch(e){toast('Lỗi xoá: '+e.message)}}
async function shareOne(){const rel=selectedArray()[0];if(!rel)return;const url=new URL('/'+enc(rel),location.href).href;try{await navigator.clipboard.writeText(url);toast('Đã copy link share')}catch(e){prompt('Copy link:',url)}}
function previewUrl(rel){return '/api/plugin/preview?p='+encodeURIComponent(rel)}
function previewSelected(){const rel=selectedArray()[0];if(!rel)return;window.open(previewUrl(rel),'_blank')}
async function addPreviewExtension(){const raw=prompt('Thêm đuôi/pattern đọc nhanh, ví dụ .env.local hoặc *.secret hoặc .foo:');if(!raw)return;try{const j=await api('/api/plugin/extensions',{add:raw});state.pluginEnabled=true;toast('Đã thêm: '+(j.custom_patterns||[]).join(', '));clearFolderCache();loadMore(true)}catch(e){toast('Lỗi plugin: '+e.message)}}
function fileUrl(rel){return '/'+enc(rel)}
function openItem(card,ev){const rel=card.dataset.rel;if(ev&&(ev.ctrlKey||ev.metaKey)){toggleSelect(rel,ev);return}closeContextMenu();const kind=card.dataset.kind,item=findLoadedItem(rel),name=item?.name||card.dataset.rawname,url=fileUrl(rel);saveListCache();if(kind==='folder')location.href=url+'/';else if(isMediaKind(kind))openPreview(kind,url,name,rel);else if(card.dataset.preview==='1')location.href=previewUrl(rel);else if(kind==='text')location.href=url+'?edit=1';else location.href=url}

// ---------------- Folder preview mosaic ----------------
let folderPreviewIO=null, folderPreviewTimers=[];
const folderPreviewQueue=[];
let folderPreviewActive=0;
function clearFolderPreviewTimers(){folderPreviewTimers.forEach(t=>clearInterval(t));folderPreviewTimers=[]}
function renderFolderMosaic(el, items, start=0){
  if(!el||!Array.isArray(items)||!items.length)return;
  const anim=(state.previewAnimation||'fade');
  el.className='folder-mosaic '+anim;
  el.innerHTML='';
  for(let i=0;i<4;i++){
    const it=items[(start+i)%items.length];
    const cell=document.createElement('div');cell.className='cell';
    if(it){
      const img=document.createElement('img');img.loading='lazy';img.decoding='async';img.src=it.thumb||it.url;img.alt=it.name||'';
      img.onerror=()=>{ if(it.url && img.src.indexOf(it.url)===-1){ img.src=it.url; } else { cell.innerHTML='<span class="fileicon">📁</span>'; } };
      cell.appendChild(img);
    } else cell.innerHTML='<span class="fileicon">📁</span>';
    el.appendChild(cell);
  }
}
function startFolderRotate(el, items){
  if(!defaults.folder_preview_rotate || !state.folderPreview || !items || items.length<=4)return;
  let idx=0; const ms=Math.max(1800,Number(defaults.folder_preview_interval_ms||3500));
  const timer=setInterval(()=>{if(document.hidden||!document.body.contains(el))return; const r=el.getBoundingClientRect(); if(r.bottom<0||r.top>innerHeight)return; idx=(idx+4)%items.length; renderFolderMosaic(el,items,idx)},ms);
  folderPreviewTimers.push(timer);
}
function queueFolderPreview(el){
  if(!el||el.dataset.loaded||el.dataset.queued)return;
  el.dataset.queued='1'; folderPreviewQueue.push(el); pumpFolderPreviewQueue();
}
async function pumpFolderPreviewQueue(){
  const maxActive=2;
  while(folderPreviewActive<maxActive && folderPreviewQueue.length){
    const el=folderPreviewQueue.shift();
    if(!el||!document.body.contains(el)||el.dataset.loaded)continue;
    folderPreviewActive++;
    loadFolderPreview(el).finally(()=>{folderPreviewActive--; setTimeout(pumpFolderPreviewQueue,40);});
  }
}
async function loadFolderPreview(el){
  const rel=el.dataset.folderPreview;if(!rel||el.dataset.loaded)return;el.dataset.loaded='1';
  try{const r=await fetch('/api/folder_preview?p='+encodeURIComponent(rel),{cache:'force-cache'});const j=await r.json(); if(!r.ok||j.error||!j.items||!j.items.length)return; renderFolderMosaic(el,j.items,0); startFolderRotate(el,j.items)}catch(e){}
}
function setupFolderPreviews(){
  clearFolderPreviewTimers(); if(folderPreviewIO)folderPreviewIO.disconnect(); folderPreviewQueue.length=0; folderPreviewActive=0;
  const els=$$('.folder-mosaic[data-folder-preview]'); if(!els.length||!state.folderPreview)return;
  folderPreviewIO=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){queueFolderPreview(e.target);folderPreviewIO.unobserve(e.target)}})},{rootMargin:'350px'});
  els.forEach(el=>folderPreviewIO.observe(el));
}

async function uploadFile(item,relDir,progressCb,conflictMode){
  const file=item.file||item; const relName=(item.relPath||file.webkitRelativePath||file.name).replace(/^\/+/, '');
  const target=relDir.replace(/^\/+|\/+$/g,'');
  const url=`/api/upload?path=${encodeURIComponent(target)}&name=${encodeURIComponent(relName)}&conflict=${encodeURIComponent(conflictMode||state.uploadConflict||'ask')}`;
  return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST',url);xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.upload.onprogress=e=>{if(e.lengthComputable&&progressCb)progressCb(e.loaded,e.total,relName)};xhr.onload=()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch(e){};if(xhr.status>=200&&xhr.status<300)resolve(data);else{const err=new Error(data.error||xhr.responseText||xhr.statusText);err.status=xhr.status;reject(err)}};xhr.onerror=()=>reject(new Error('network error'));xhr.send(file)})
}
const uploadState={queue:[],running:false,done:0,failed:0,totalBytes:0,loadedBytes:0,active:new Map()};
function humanBytes(n){n=Number(n||0);for(const u of ['B','KB','MB','GB','TB']){if(n<1024||u==='TB')return (u==='B'?Math.round(n):n.toFixed(1))+' '+u;n/=1024}}
function openUploadDialog(){const m=$('#uploadModal'); if(!m)return; m.classList.add('show'); renderUploadQueue();}
function closeUploadDialog(){ if(uploadState.running&&!confirm('Upload đang chạy, vẫn đóng popup?'))return; $('#uploadModal')?.classList.remove('show') }
function chooseFiles(){openUploadDialog()} function chooseFolder(){openUploadDialog()}
function pickUploadFiles(){$('#fileInput')?.click()} function pickUploadFolder(){$('#folderInput')?.click()}
function normalizeUploadItem(it,targetPath){it.targetPath=targetPath==null?currentPath():targetPath;return it}
function enqueueUploadItems(items,targetPath,autoStart=state.uploadAutoStart){
  const arr=Array.from(items||[]).map(it=>normalizeUploadItem(it,targetPath));
  if(!arr.length)return 0;
  uploadState.queue.push(...arr); uploadState.totalBytes=uploadState.queue.reduce((a,x)=>a+(x.size||0),0); renderUploadQueue();
  if(autoStart)startUploadQueue();
  return arr.length;
}
function addUploadFiles(files,targetPath=currentPath()){const arr=Array.from(files||[]).map(f=>({file:f,relPath:f.webkitRelativePath||f.name,state:'ready',loaded:0,size:f.size||0,targetPath})); return enqueueUploadItems(arr,targetPath);}
async function traverseEntry(entry,path,out,targetPath=currentPath()){
  if(entry.isFile){await new Promise(res=>entry.file(f=>{out.push({file:f,relPath:(path+f.name).replace(/^\/+/,''),state:'ready',loaded:0,size:f.size||0,targetPath});res()},()=>res()))}
  else if(entry.isDirectory){const reader=entry.createReader();let batch=[];do{batch=await new Promise(res=>reader.readEntries(res,()=>res([])));for(const e of batch)await traverseEntry(e,path+entry.name+'/',out,targetPath)}while(batch.length)}
}
async function itemsFromDrop(e,targetPath=currentPath()){
  const out=[]; const dt=e.dataTransfer; const items=Array.from(dt?.items||[]);
  if(items.length&&items[0].webkitGetAsEntry){for(const it of items){const entry=it.webkitGetAsEntry();if(entry)await traverseEntry(entry,'',out,targetPath)}}
  if(out.length)return out;
  return Array.from(dt?.files||[]).map(f=>({file:f,relPath:f.webkitRelativePath||f.name,state:'ready',loaded:0,size:f.size||0,targetPath}));
}
async function handleUploadDrop(e){e.preventDefault();e.stopPropagation();const dz=$('#uploadDrop');dz?.classList.remove('drag');const targetPath=currentPath();const out=await itemsFromDrop(e,targetPath);enqueueUploadItems(out,targetPath);}
async function handleGridUploadDrop(e){
  e.preventDefault(); e.stopPropagation(); grid?.classList.remove('drag');
  if(uploadState.running){toast('Upload đang chạy, chưa thêm queue mới');return}
  const targetPath=currentPath(); openUploadDialog();
  const added=enqueueUploadItems(await itemsFromDrop(e,targetPath),targetPath,false);
  if(added)toast(`Đã thêm ${added} file vào queue upload`);
}
function renderUploadQueue(){
  const q=$('#uploadQueue'), sum=$('#uploadSummary'), bar=$('#uploadModalBar'); if(!q)return;
  const total=uploadState.queue.length; const bytes=uploadState.queue.reduce((a,x)=>a+(x.size||0),0);
  q.innerHTML=uploadState.queue.slice(0,500).map((it,i)=>`<div class="upload-row"><div class="upload-path" title="${it.relPath}">${it.relPath}</div><div class="upload-state ${it.state==='done'?'ok':it.state==='error'?'err':''}">${it.state||'ready'} ${it.size?humanBytes(it.size):''}</div></div>`).join('') || '<div class="upload-row"><div class="upload-path">Chưa có file nào trong queue.</div><div class="upload-state">ready</div></div>';
  if(total>500)q.insertAdjacentHTML('beforeend',`<div class="upload-row"><div class="upload-path">... còn ${total-500} file nữa</div><div></div></div>`);
  if(sum)sum.textContent=`${total} file · ${humanBytes(bytes)} · done ${uploadState.done} · lỗi ${uploadState.failed}`;
  const loaded=uploadState.queue.reduce((a,x)=>a+(x.loaded||0),0); if(bar)bar.style.width=bytes?Math.min(100,Math.round(loaded/bytes*100))+'%':'0%';
}
async function uploadOneQueued(it){
  it.state='uploading';it.loaded=0;renderUploadQueue();
  try{let mode=state.uploadConflict;let res;const targetPath=it.targetPath==null?currentPath():it.targetPath;try{res=await uploadFile(it,targetPath,(loaded,total)=>{it.loaded=loaded;renderUploadQueue()},mode)}catch(e){if(e.status===409&&mode==='ask'){if(confirm(`File đã tồn tại:\n${it.relPath}\n\nGhi đè file này?`)){res=await uploadFile(it,targetPath,(loaded,total)=>{it.loaded=loaded;renderUploadQueue()},'overwrite')}else{it.state='skipped';it.loaded=it.size;return}}else throw e} it.state=res?.skipped?'skipped':'done';it.loaded=it.size;uploadState.done++}
  catch(e){it.state='error';it.error=e.message;uploadState.failed++} finally{renderUploadQueue()}
}
async function startUploadQueue(){
  if(uploadState.running)return; if(!uploadState.queue.length){toast('Queue trống');return} uploadState.running=true;uploadState.done=0;uploadState.failed=0;
  const workers=Array.from({length:Math.max(1,Math.min(Number(state.uploadParallel||3),8))},async()=>{while(true){const it=uploadState.queue.find(x=>x.state==='ready'); if(!it)break; await uploadOneQueued(it)}});
  await Promise.all(workers); uploadState.running=false; toast(uploadState.failed?`Upload xong, lỗi ${uploadState.failed}`:'Upload xong'); clearFolderCache(); loadMore(true);
}
function clearUploadQueue(){if(uploadState.running){toast('Đang upload, chưa xoá queue được');return} uploadState.queue=[];uploadState.done=0;uploadState.failed=0;renderUploadQueue()}
$('#fileInput')?.addEventListener('change',e=>{addUploadFiles(e.target.files);e.target.value=''});$('#folderInput')?.addEventListener('change',e=>{addUploadFiles(e.target.files);e.target.value=''});
const upDrop=$('#uploadDrop'); if(upDrop){['dragenter','dragover'].forEach(ev=>upDrop.addEventListener(ev,e=>{e.preventDefault();upDrop.classList.add('drag')}));['dragleave','drop'].forEach(ev=>upDrop.addEventListener(ev,e=>{e.preventDefault();upDrop.classList.remove('drag')}));upDrop.addEventListener('drop',handleUploadDrop);upDrop.addEventListener('click',pickUploadFiles)}
if(grid){
  ['dragenter','dragover'].forEach(ev=>grid.addEventListener(ev,e=>{if(uploadState.running)return;e.preventDefault();e.stopPropagation();grid.classList.add('drag')}));
  ['dragleave','dragend'].forEach(ev=>grid.addEventListener(ev,e=>{e.preventDefault();grid.classList.remove('drag')}));
  grid.addEventListener('drop',handleGridUploadDrop);
}
$('#uploadConflict')?.addEventListener('change',e=>changeUploadConflict(e.target));
if(grid){
  syncControls(); applyView(); if(!hydrateCache())loadMore(true); updateSelectionUI();
}

// ---------------- Terminal drawer ----------------
const term = {
  id:null, mode:null, poll:null, shown:false, started:false,
  cmdHistory:[], cmdIndex:0, commandCwd:'',
  screen:null
};
function termEl(){return $('#termDrawer')}
function termScreen(){return $('#termScreen')}
function termRowsColsEstimate(){
  const scr=termScreen(); if(!scr)return {cols:100,rows:30};
  const cs=getComputedStyle(scr);
  let cw=8;
  try{
    const span=document.createElement('span');
    span.textContent='MMMMMMMMMM'; span.style.visibility='hidden'; span.style.position='absolute'; span.style.font=cs.font;
    document.body.appendChild(span); cw=Math.max(5,span.getBoundingClientRect().width/10); span.remove();
  }catch(e){}
  const lh=parseFloat(cs.lineHeight)||18;
  const padX=(parseFloat(cs.paddingLeft)||0)+(parseFloat(cs.paddingRight)||0);
  const padY=(parseFloat(cs.paddingTop)||0)+(parseFloat(cs.paddingBottom)||0);
  const usableW=Math.max(40,scr.clientWidth-padX);
  const usableH=Math.max(40,scr.clientHeight-padY);
  return {cols:Math.max(40,Math.floor(usableW/cw)), rows:Math.max(8,Math.floor(usableH/lh))};
}
function termInitScreen(){ const rc=termRowsColsEstimate(); term.screen={cols:rc.cols, rows:rc.rows, r:0, c:0, lines:[''], saved:null}; }
function termResetScreen(){termInitScreen(); termRender(true)}
function termEnsureScreen(){if(!term.screen)termInitScreen(); return term.screen}
function termEnsureLine(st,r){while(st.lines.length<=r)st.lines.push(''); return st.lines[r]}
function termSetLine(st,r,line){while(st.lines.length<=r)st.lines.push(''); st.lines[r]=line}
function termPutChar(ch){
  const st=termEnsureScreen();
  if(ch==='\t'){ const n=8-(st.c%8); for(let i=0;i<n;i++)termPutChar(' '); return; }
  if(st.c>=st.cols){ st.c=0; st.r++; }
  if(st.r>=st.lines.length)st.lines.push('');
  let line=termEnsureLine(st,st.r);
  if(line.length<st.c)line=line+' '.repeat(st.c-line.length);
  line=line.slice(0,st.c)+ch+line.slice(st.c+1);
  termSetLine(st,st.r,line); st.c++;
  const maxLines=Math.max(st.rows*6, Math.ceil(Number(defaults.terminal_max_buffer_chars||500000)/80));
  if(st.lines.length>maxLines){ const drop=st.lines.length-maxLines; st.lines.splice(0,drop); st.r=Math.max(0,st.r-drop); }
}
function termCSI(params, final){
  const st=termEnsureScreen();
  if(params.startsWith('?'))params=params.slice(1);
  const nums=params.split(';').filter(x=>x!=='').map(x=>parseInt(x,10));
  const n=(i,def)=>Number.isFinite(nums[i])?nums[i]:def;
  if(final==='A')st.r=Math.max(0,st.r-n(0,1));
  else if(final==='B')st.r+=n(0,1);
  else if(final==='C')st.c=Math.min(st.cols-1,st.c+n(0,1));
  else if(final==='D')st.c=Math.max(0,st.c-n(0,1));
  else if(final==='E'){st.r+=n(0,1);st.c=0;}
  else if(final==='F'){st.r=Math.max(0,st.r-n(0,1));st.c=0;}
  else if(final==='G')st.c=Math.max(0,Math.min(st.cols-1,n(0,1)-1));
  else if(final==='H'||final==='f'){st.r=Math.max(0,n(0,1)-1);st.c=Math.max(0,Math.min(st.cols-1,n(1,1)-1));}
  else if(final==='d')st.r=Math.max(0,n(0,1)-1);
  else if(final==='J'){
    const mode=n(0,0);
    if(mode===2||mode===3){st.lines=[''];st.r=0;st.c=0;}
    else if(mode===0){let line=termEnsureLine(st,st.r); termSetLine(st,st.r,line.slice(0,st.c)); st.lines=st.lines.slice(0,st.r+1);}
    else if(mode===1){for(let i=0;i<st.r;i++)st.lines[i]=''; let line=termEnsureLine(st,st.r); termSetLine(st,st.r,' '.repeat(st.c)+line.slice(st.c));}
  }
  else if(final==='K'){
    const mode=n(0,0); let line=termEnsureLine(st,st.r);
    if(mode===0)termSetLine(st,st.r,line.slice(0,st.c));
    else if(mode===1)termSetLine(st,st.r,' '.repeat(Math.min(st.c,line.length))+line.slice(st.c));
    else if(mode===2)termSetLine(st,st.r,'');
  }
  else if(final==='P'){ const count=n(0,1); let line=termEnsureLine(st,st.r); termSetLine(st,st.r,line.slice(0,st.c)+line.slice(st.c+count)); }
  else if(final==='X'){ const count=n(0,1); let line=termEnsureLine(st,st.r); if(line.length<st.c)line+=' '.repeat(st.c-line.length); termSetLine(st,st.r,line.slice(0,st.c)+' '.repeat(count)+line.slice(st.c+count)); }
  else if(final==='@'){ const count=n(0,1); let line=termEnsureLine(st,st.r); if(line.length<st.c)line+=' '.repeat(st.c-line.length); termSetLine(st,st.r,line.slice(0,st.c)+' '.repeat(count)+line.slice(st.c)); }
  else if(final==='s'){st.saved={r:st.r,c:st.c};}
  else if(final==='u'&&st.saved){st.r=st.saved.r;st.c=st.saved.c;}
}
function termRender(forceStick=false){
  const scr=termScreen(); if(!scr)return;
  const st=termEnsureScreen();
  const stick=forceStick || (scr.scrollTop + scr.clientHeight >= scr.scrollHeight - 24);
  const maxChars=Number(defaults.terminal_max_buffer_chars||500000);
  let text=st.lines.join('\n'); if(text.length>maxChars)text=text.slice(-maxChars);
  scr.textContent=text; if(stick)scr.scrollTop=scr.scrollHeight;
}
function termAppend(s){
  const scr=termScreen(); if(!scr||!s)return;
  const st=termEnsureScreen(); s=String(s);
  for(let i=0;i<s.length;i++){
    const ch=s[i];
    if(ch==='\x1b'){
      const next=s[i+1];
      if(next===']'){
        let end=s.indexOf('\x07',i+2); let end2=s.indexOf('\x1b\\',i+2);
        if(end<0 || (end2>=0 && end2<end)) end=end2>=0?end2+1:end;
        i=end>=0?end:s.length-1; continue;
      }
      if(next==='['){ let j=i+2; while(j<s.length && !(/[A-Za-z@`~]/.test(s[j])))j++; if(j<s.length){termCSI(s.slice(i+2,j),s[j]); i=j; continue;} }
      if(next==='7'){st.saved={r:st.r,c:st.c}; i++; continue;}
      if(next==='8'&&st.saved){st.r=st.saved.r;st.c=st.saved.c;i++;continue;}
      if(next && '=>()#'.includes(next)){i+=2; continue;}
      continue;
    }
    if(ch==='\x07')continue;
    if(ch==='\x0c'){st.lines=[''];st.r=0;st.c=0;continue;}
    if(ch==='\r'){st.c=0;continue;}
    if(ch==='\n'){
      st.r++;
      st.c=0;
      if(st.r>=st.lines.length)st.lines.push('');
      if(st.r>Math.max(st.rows*6,200)){const drop=st.r-Math.max(st.rows*6,200); st.lines.splice(0,drop); st.r-=drop;}
      continue;
    }
    if(ch==='\b'||ch==='\x7f'){st.c=Math.max(0,st.c-1);continue;}
    if(ch<' ' && ch!=='\t')continue;
    termPutChar(ch);
  }
  termRender(false);
}
function termSetStatus(j){
  $('#termMode') && ($('#termMode').textContent = j?.mode ? `[${j.mode}${j.tmux_name?' '+j.tmux_name:''}]` : '');
  $('#termCwd') && ($('#termCwd').textContent = j?.cwd ? j.cwd : '');
}
async function termApi(path,data){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||j.error) throw new Error(j.error||`HTTP ${r.status}`);
  return j;
}
function termRowsCols(){return termRowsColsEstimate()}
async function openTerminal(forceNew=false){
  const drawer=termEl(); if(!drawer){toast('Terminal UI không có trên trang này');return}
  if(!defaults.terminal_enabled){toast('Terminal đang tắt trong config');return}
  drawer.classList.add('show'); term.shown=true;
  if(term.id && !forceNew){termScreen()?.focus();return}
  try{
    termAppend('\n[opening terminal...]\n');
    const j=await termApi('/api/term/new',{path:currentPath()});
    term.id=j.id; term.mode=j.mode; term.started=true; term.commandCwd=j.cwd||''; termSetStatus(j);
    drawer.classList.toggle('command-mode', term.mode==='command');
    $('#termCommand')?.classList.toggle('hidden', term.mode!=='command');
    if(term.mode==='command'){ $('#termPrompt').textContent=(term.commandCwd||'>')+'>'; $('#termLine')?.focus(); }
    else { termScreen()?.focus(); await termResize(); termPoll(); }
  }catch(e){termAppend('\n[terminal error: '+e.message+']\n');}
}
function toggleTerminal(){ const d=termEl(); if(!d)return; if(d.classList.contains('show')){termHide()}else openTerminal(false); }
function termHide(){termEl()?.classList.remove('show'); term.shown=false;}
async function newTerminalSession(){ if(term.id){try{await termApi('/api/term/detach',{id:term.id})}catch(e){}} term.id=null; term.mode=null; termResetScreen(); await openTerminal(true); }
function termPoll(){
  clearInterval(term.poll);
  const ms=Number(defaults.terminal_poll_ms||150);
  async function once(){
    if(!term.id || term.mode==='command')return;
    try{
      const r=await fetch('/api/term/read?id='+encodeURIComponent(term.id));
      const j=await r.json();
      if(j.error){clearInterval(term.poll);term.poll=null;term.id=null;termAppend('\n[terminal session lost: '+j.error+']\n[Ấn New để mở session mới.]\n'); return}
      termSetStatus(j);
      if(j.data)termAppend(j.data);
      if(j.alive===false){termAppend('\n[terminal detached]\n');clearInterval(term.poll)}
    }catch(e){}
  }
  once(); term.poll=setInterval(once, ms);
}
async function termSend(data){ if(!term.id){await openTerminal(false)} if(term.mode==='command')return; try{await termApi('/api/term/input',{id:term.id,data})}catch(e){termAppend('\n[input error: '+e.message+']\n')}}
function termSendCtrl(ch){ const code=ch.toLowerCase().charCodeAt(0)-96; if(code>0&&code<27)termSend(String.fromCharCode(code));}
async function termResize(){ const rc=termRowsCols(); if(term.screen){term.screen.cols=rc.cols; term.screen.rows=rc.rows; termRender(true);} if(!term.id||term.mode==='command')return; try{await termApi('/api/term/resize',{id:term.id,...rc})}catch(e){}}
async function termDetach(){ if(!term.id)return; try{await termApi('/api/term/detach',{id:term.id})}catch(e){} clearInterval(term.poll); term.id=null; termAppend('\n[detached]\n'); }
async function termKill(){ if(!term.id)return; if(!confirm('Kill terminal/session này? Với tmux, lệnh này kill cả tmux session.'))return; try{await termApi('/api/term/kill',{id:term.id})}catch(e){} clearInterval(term.poll); term.id=null; termAppend('\n[killed]\n'); }
function termClear(){ termResetScreen(); if(term.id&&term.mode!=='command')termSend('\x0c');}
async function termCopy(){try{await navigator.clipboard.writeText(termScreen()?.textContent||'');toast('Đã copy terminal output')}catch(e){toast('Không copy được')}}
function termStartTmux(){ const cmd='tmux new-session -A -s landrive'; if(term.mode==='command'){termRunCommand(cmd);return;} termSend(cmd+'\r'); }
function termFullscreen(){termEl()?.classList.toggle('full'); setTimeout(termResize,120)}
async function termRunCommand(cmd){
  if(!cmd.trim())return;
  term.cmdHistory.push(cmd); term.cmdIndex=term.cmdHistory.length;
  termAppend(($('#termPrompt')?.textContent||'>')+' '+cmd+'\n');
  try{
    const j=await termApi('/api/term/run',{id:term.id,cmd});
    if(j.output)termAppend(j.output);
    term.commandCwd=j.cwd||term.commandCwd; $('#termPrompt').textContent=term.commandCwd+'>';
  }catch(e){termAppend('[command error: '+e.message+']\n')}
}
document.addEventListener('keydown', async e=>{
  const active=document.activeElement;
  const inEditor=active && ['INPUT','TEXTAREA'].includes(active.tagName) && active.id!=='termLine';
  if((e.ctrlKey||e.metaKey) && e.key==='`'){e.preventDefault();toggleTerminal();return}
  if(!termEl()?.classList.contains('show'))return;
  if(e.key==='Escape' && termEl()?.classList.contains('full')){e.preventDefault();termEl().classList.remove('full');setTimeout(termResize,80);return}
  if(inEditor || term.mode==='command' || active!==termScreen())return;
  if(e.ctrlKey){
    const k=e.key.toLowerCase();
    if(k==='c'){e.preventDefault();termSendCtrl('c');return}
    if(k==='d'){e.preventDefault();termSendCtrl('d');return}
    if(k==='l'){e.preventDefault();termClear();return}
  }
  if(e.altKey && e.key==='Enter'){e.preventDefault();termFullscreen();return}
  if(e.key==='Backspace' || e.code==='Backspace'){e.preventDefault();termSend('\x7f');return}
  if(e.key==='Delete' || e.code==='Delete'){e.preventDefault();termSend('\x1b[3~');return}
  const map={Enter:'\r',Tab:'\t',Escape:'\x1b',ArrowUp:'\x1b[A',ArrowDown:'\x1b[B',ArrowRight:'\x1b[C',ArrowLeft:'\x1b[D',Home:'\x1b[H',End:'\x1b[F',PageUp:'\x1b[5~',PageDown:'\x1b[6~'};
  if(map[e.key]){e.preventDefault();termSend(map[e.key]);return}
  if(e.key.length===1 && !e.metaKey && !e.altKey){e.preventDefault();termSend(e.key)}
});
termScreen()?.addEventListener('paste',e=>{if(term.mode==='command')return;e.preventDefault();const t=(e.clipboardData||window.clipboardData).getData('text');termSend(t)});
$('#termLine')?.addEventListener('keydown',e=>{
  if(e.key==='Enter'){const v=e.target.value;e.target.value='';termRunCommand(v)}
  else if(e.key==='ArrowUp'){e.preventDefault(); if(term.cmdHistory.length){term.cmdIndex=Math.max(0,term.cmdIndex-1); e.target.value=term.cmdHistory[term.cmdIndex]||''}}
  else if(e.key==='ArrowDown'){e.preventDefault(); term.cmdIndex=Math.min(term.cmdHistory.length,term.cmdIndex+1); e.target.value=term.cmdHistory[term.cmdIndex]||''}
});
window.addEventListener('resize',()=>{clearTimeout(window.__termResizeTimer);window.__termResizeTimer=setTimeout(termResize,250)});

"""


def page_shell(title: str, body: str, current_path: str = "/") -> bytes:
    app = {
        "currentPath": current_path.strip("/"),
        "title": CONFIG.title,
        "plugin": {"enabled": plugin_enabled()},
        "defaults": {
            "default_sort": CONFIG.default_sort,
            "default_view": CONFIG.default_view,
            "page_limit": CONFIG.page_limit,
            "folders_first": CONFIG.folders_first,
            "search_debounce_ms": CONFIG.search_debounce_ms,
            "terminal_enabled": CONFIG.terminal_enabled,
            "terminal_poll_ms": CONFIG.terminal_poll_ms,
            "terminal_max_buffer_chars": CONFIG.terminal_max_buffer_chars,
            "terminal_start_height_px": CONFIG.terminal_start_height_px,
            "terminal_mobile_extra_keys": CONFIG.terminal_mobile_extra_keys,
            "thumb_fit": CONFIG.thumb_fit,
            "folder_preview_enabled": CONFIG.folder_preview_enabled,
            "folder_preview_mode": CONFIG.folder_preview_mode,
            "folder_preview_fit": CONFIG.folder_preview_fit,
            "folder_preview_rotate": CONFIG.folder_preview_rotate,
            "folder_preview_animation": CONFIG.folder_preview_animation,
            "folder_preview_interval_ms": CONFIG.folder_preview_interval_ms,
            "folder_preview_scan_limit": CONFIG.folder_preview_scan_limit,
            "folder_preview_max_items": CONFIG.folder_preview_max_items,
            "folder_preview_include_video": CONFIG.folder_preview_include_video,
            "upload_auto_start": CONFIG.upload_auto_start,
            "upload_parallel": CONFIG.upload_parallel,
            "upload_conflict": CONFIG.upload_conflict,
        },
    }
    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>{html_escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<script>window.APP={json_dumps(app)};</script>
<script>{JS}</script>
</body>
</html>"""
    return html_doc.encode("utf-8", "surrogateescape")




def entry_to_json(path: Path, dirent_name: str, st: os.stat_result, is_dir: bool, base_path: Optional[Path] = None) -> Dict[str, Any]:
    kind = classify(path, is_dir)
    rel_item = path.resolve().relative_to(CONFIG.root.resolve()).as_posix()
    thumb = f"/api/thumb?p={urllib.parse.quote(rel_item)}" if kind in ("image", "video") else ""
    search_path_text = ""
    if base_path is not None:
        try:
            parent_rel = path.resolve().parent.relative_to(base_path.resolve()).as_posix()
            if parent_rel != ".":
                search_path_text = parent_rel
        except ValueError:
            search_path_text = ""
    return {
        "name": dirent_name,
        "nameEsc": html_escape(dirent_name),
        "nameLowerEsc": html_escape(dirent_name.lower()),
        "rel": rel_item,
        "relEsc": html_escape(rel_item),
        "relJs": html_escape(rel_item).replace("'", "&#39;"),
        "is_dir": is_dir,
        "kind": kind,
        "icon": icon_for(kind),
        "size": 0 if is_dir else st.st_size,
        "sizeText": "Folder" if is_dir else size_fmt(st.st_size),
        "sizeTextEsc": html_escape("Folder" if is_dir else size_fmt(st.st_size)),
        "mtime": st.st_mtime,
        "mtimeText": mtime_fmt(st.st_mtime),
        "mtimeTextEsc": html_escape(mtime_fmt(st.st_mtime)),
        "searchPathText": search_path_text,
        "searchPathTextEsc": html_escape(search_path_text),
        "thumb": thumb,
        "preview": (not is_dir) and plugin_can_preview(path),
    }


def sort_key_for(name: str, is_dir: bool, st: Optional[os.stat_result], sort_mode: str, path: Optional[Path] = None) -> Any:
    lname = name.lower()
    ext = Path(name).suffix.lower().lstrip(".")
    if sort_mode.startswith("mtime"):
        return getattr(st, "st_mtime", 0.0)
    if sort_mode.startswith("size"):
        if is_dir:
            return -1
        return getattr(st, "st_size", 0)
    if sort_mode.startswith("type"):
        fake = path if path is not None else Path(name)
        return (classify(fake, is_dir), ext, lname)
    if sort_mode.startswith("ext"):
        return (ext, lname)
    return lname


def list_entries_page(path: Path, offset: int, limit: int, sort_mode: str, query: str, folders_first: Optional[bool] = None, recursive_depth: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], int, bool, int, int]:
    offset = max(0, int(offset or 0))
    limit = max(20, min(int(limit or 220), 1000))
    query_l = (query or "").strip().lower()
    sort_mode = normalize_sort(sort_mode)
    reverse = sort_mode.endswith("desc")
    folders_first = CONFIG.folders_first if folders_first is None else bool(folders_first)
    # Recursive mode is only meaningful with a keyword. Without this guard, choosing
    # "all" at / would accidentally enumerate the whole root just to show a folder.
    recursive_enabled = bool(query_l) and recursive_depth != 0
    needs_stat = sort_mode.startswith("mtime") or sort_mode.startswith("size")
    rows: List[Any] = []
    errors = 0

    def maybe_add_row(p: Path, name: str, is_dir: bool, st: Optional[os.stat_result], match_text: str) -> None:
        if query_l and query_l not in match_text.lower():
            return
        key = sort_key_for(name, is_dir, st, sort_mode, p)
        rows.append((is_dir, key, name.lower(), name, st, p))

    if recursive_enabled:
        stack: List[Tuple[Path, int]] = [(path, 0)]
        while stack:
            folder, depth = stack.pop()
            try:
                with os.scandir(folder) as it:
                    entries = list(it)
            except OSError:
                errors += 1
                continue
            for de in entries:
                name = de.name
                if should_hide_entry(folder, name):
                    continue
                p = folder / name
                try:
                    is_dir = de.is_dir(follow_symlinks=False)
                    st = de.stat(follow_symlinks=False) if needs_stat else None
                    rel_under_search = p.relative_to(path).as_posix()
                    maybe_add_row(p, name, is_dir, st, f"{name}\n{rel_under_search}")
                    if is_dir and (recursive_depth is None or depth < recursive_depth):
                        stack.append((p, depth + 1))
                except OSError:
                    errors += 1
    else:
        try:
            with os.scandir(path) as it:
                for de in it:
                    name = de.name
                    if should_hide_entry(path, name):
                        continue
                    if query_l and query_l not in name.lower():
                        continue
                    try:
                        is_dir = de.is_dir(follow_symlinks=False)
                        st = de.stat(follow_symlinks=False) if needs_stat else None
                        key = sort_key_for(name, is_dir, st, sort_mode, path / name)
                        rows.append((is_dir, key, name.lower(), name, st, path / name))
                    except OSError:
                        errors += 1
        except OSError:
            raise

    def row_sort(row: Any) -> Any:
        is_dir, key, lname, _name, _st, _path = row
        if folders_first:
            # Keep folders at top, but sort folders by name for size sort so folders do not look random.
            group = 0 if is_dir else 1
            if is_dir and sort_mode.startswith("size"):
                key = lname
            return (group, key, lname)
        return (key, lname)

    rows.sort(key=row_sort, reverse=reverse if not folders_first else False)
    if folders_first and reverse:
        # Reverse inside each group, not the folder/file grouping itself.
        dirs = [r for r in rows if r[0]]
        files = [r for r in rows if not r[0]]
        dirs.sort(key=lambda r: row_sort(r)[1:], reverse=True)
        files.sort(key=lambda r: row_sort(r)[1:], reverse=True)
        rows = dirs + files

    total = len(rows)
    page = rows[offset:offset + limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    out: List[Dict[str, Any]] = []
    for row in page:
        try:
            is_dir, _key, _lname, name, st, p = row
            if st is None:
                st = p.stat()
            out.append(entry_to_json(p, name, st, is_dir, path if recursive_enabled else None))
        except OSError:
            errors += 1
    return out, offset + len(out), has_more, errors, total



# ---------------------------------------------------------------------------
# Terminal backend
# ---------------------------------------------------------------------------

class TerminalSession:
    """One browser-attached terminal client.

    Linux tmux mode:
      this object owns only the tmux attach client. The real tmux session can
      continue after detach/reload.
    Linux pty mode:
      this object owns the real shell process.
    Windows command mode:
      this object owns only a cwd and runs one command per Enter.
    """
    def __init__(self, sid: str, mode: str, cwd: Path, tmux_name: str = "") -> None:
        self.id = sid
        self.mode = mode
        self.cwd = cwd
        self.tmux_name = tmux_name
        self.proc: Optional[subprocess.Popen[Any]] = None
        self.fd: Optional[int] = None
        self.buffer = ""
        self.lock = threading.Lock()
        self.alive = True
        self.created = time.time()
        self.last_seen = time.time()
        self.reader: Optional[threading.Thread] = None

    def append(self, text: str) -> None:
        if not text:
            return
        with self.lock:
            self.buffer += text
            max_chars = int(getattr(CONFIG, "terminal_max_buffer_chars", 500000))
            if len(self.buffer) > max_chars:
                self.buffer = self.buffer[-max_chars:]

    def drain(self) -> str:
        self.last_seen = time.time()
        with self.lock:
            out = self.buffer
            self.buffer = ""
            return out

    def start_pty(self, argv: List[str], env: Optional[Dict[str, str]] = None) -> None:
        if not HAS_UNIX_PTY or pty is None:
            raise RuntimeError("PTY is not available on this platform")
        master, slave = pty.openpty()
        self.fd = master
        child_env = os.environ.copy()
        child_env.update(env or {})
        child_env.setdefault("TERM", "xterm-256color")
        child_env.setdefault("COLORTERM", "truecolor")
        self.proc = subprocess.Popen(
            argv,
            cwd=str(self.cwd),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=child_env,
            close_fds=True,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
        try:
            os.close(slave)
        except Exception:
            pass
        self.reader = threading.Thread(target=self._reader_loop, name=f"term-reader-{self.id}", daemon=True)
        self.reader.start()

    def _reader_loop(self) -> None:
        fd = self.fd
        if fd is None:
            return
        while self.alive:
            try:
                if select is not None:
                    r, _, _ = select.select([fd], [], [], 0.25)
                    if not r:
                        if self.proc and self.proc.poll() is not None:
                            break
                        continue
                raw = os.read(fd, 65536)
                if not raw:
                    break
                self.append(raw.decode("utf-8", "replace"))
            except OSError:
                break
            except Exception as e:
                self.append(f"\n[terminal read error: {e}]\n")
                break
        self.alive = False

    def write(self, data: str) -> None:
        self.last_seen = time.time()
        if not self.alive:
            return
        if self.fd is None:
            return
        try:
            os.write(self.fd, data.encode("utf-8", "surrogatepass"))
        except Exception as e:
            self.append(f"\n[terminal write error: {e}]\n")

    def resize(self, cols: int, rows: int) -> None:
        if not self.fd or not HAS_UNIX_PTY or fcntl is None or termios is None or struct is None:
            return
        try:
            cols = max(20, min(int(cols or 100), 300))
            rows = max(8, min(int(rows or 30), 100))
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:
            pass

    def detach(self) -> None:
        self.alive = False
        if self.proc and self.proc.poll() is None:
            try:
                if os.name != "nt" and signal is not None:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGHUP)
                else:
                    self.proc.terminate()
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None

    def kill(self) -> None:
        if self.mode == "tmux" and self.tmux_name:
            tmux_bin = shutil.which(CONFIG.terminal_tmux_bin) or CONFIG.terminal_tmux_bin
            try:
                subprocess.run([tmux_bin, "kill-session", "-t", self.tmux_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception as e:
                self.append(f"\n[tmux kill error: {e}]\n")
        self.detach()


class TerminalManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, TerminalSession] = {}
        self.lock = threading.Lock()
        self._cleaner_started = False

    def _ensure_cleaner(self) -> None:
        if self._cleaner_started:
            return
        self._cleaner_started = True
        threading.Thread(target=self._cleaner_loop, name="term-cleaner", daemon=True).start()

    def _cleaner_loop(self) -> None:
        while True:
            time.sleep(30)
            try:
                idle = max(5, int(getattr(CONFIG, "terminal_idle_detach_minutes", 120))) * 60
            except Exception:
                idle = 7200
            now = time.time()
            stale: List[str] = []
            with self.lock:
                for sid, sess in list(self.sessions.items()):
                    if now - sess.last_seen > idle or (sess.mode != "command" and not sess.alive):
                        stale.append(sid)
                for sid in stale:
                    sess = self.sessions.pop(sid, None)
                    if sess:
                        sess.detach()

    def _new_sid(self) -> str:
        raw = f"{time.time()}:{threading.get_ident()}:{os.urandom(8).hex()}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def _tmux_name_for(self, cwd: Path) -> str:
        prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", str(CONFIG.terminal_tmux_session_prefix or "landrive")).strip("_") or "landrive"
        if CONFIG.terminal_session_mode == "global":
            return prefix + "_main"
        try:
            rel = cwd.resolve().relative_to(CONFIG.root.resolve()).as_posix()
        except Exception:
            rel = str(cwd)
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(rel).name or "root").strip("_")[:24] or "root"
        h = hashlib.sha1(str(cwd.resolve()).encode("utf-8", "surrogateescape")).hexdigest()[:10]
        return f"{prefix}_{base}_{h}"

    def new(self, cwd: Path) -> TerminalSession:
        if not CONFIG.terminal_enabled:
            raise RuntimeError("Terminal is disabled in config")
        self._ensure_cleaner()
        cwd = cwd.resolve()
        try:
            cwd.relative_to(CONFIG.root.resolve())
        except ValueError:
            cwd = CONFIG.root.resolve()
        if not cwd.is_dir():
            cwd = cwd.parent

        with self.lock:
            if len(self.sessions) >= int(CONFIG.terminal_max_sessions):
                # Detach oldest browser client. For tmux this does not kill tmux session itself.
                oldest_sid = min(self.sessions, key=lambda k: self.sessions[k].last_seen)
                old = self.sessions.pop(oldest_sid)
                old.detach()

        if os.name == "nt":
            sess = TerminalSession(self._new_sid(), "command", cwd)
            sess.append(f"Windows command mode. cwd: {cwd}\n")
            with self.lock:
                self.sessions[sess.id] = sess
            return sess

        backend = str(CONFIG.terminal_backend_linux or "pty").lower()
        tmux_bin = shutil.which(CONFIG.terminal_tmux_bin) if CONFIG.terminal_tmux_bin else None
        use_tmux = backend == "tmux" and bool(tmux_bin)
        if backend == "tmux" and not tmux_bin and str(CONFIG.terminal_backend_linux_fallback).lower() != "pty":
            raise RuntimeError("tmux not found and fallback is disabled")

        sid = self._new_sid()
        if use_tmux:
            tmux_name = self._tmux_name_for(cwd)
            sess = TerminalSession(sid, "tmux", cwd, tmux_name)
            shell = str(CONFIG.terminal_shell_linux or "/bin/bash")
            if not Path(shell).exists():
                shell = os.environ.get("SHELL", "/bin/sh")
            shell_cmd = f"exec {shlex.quote(shell)} -l" if shell.endswith(("bash", "zsh")) else f"exec {shlex.quote(shell)}"
            tmux_env = os.environ.copy()
            tmux_env.update({"LAN_DRIVE_TERM": "1", "TERM": "xterm-256color", "COLORTERM": "truecolor"})
            has = subprocess.run([tmux_bin, "has-session", "-t", tmux_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=tmux_env)
            if has.returncode != 0:
                subprocess.run([tmux_bin, "new-session", "-d", "-s", tmux_name, "-c", str(cwd), shell_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=tmux_env, check=True)
            # The browser UI is a lightweight renderer, so hide tmux status/bell noise by default.
            status_value = "on" if bool(getattr(CONFIG, "terminal_tmux_status_bar", False)) else "off"
            for opt, val in [
                ("status", status_value), ("visual-bell", "off"), ("bell-action", "none"),
                ("monitor-bell", "off"), ("set-clipboard", "off"), ("mouse", "off"),
            ]:
                subprocess.run([tmux_bin, "set-option", "-t", tmux_name, opt, val], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=tmux_env)
            argv = [tmux_bin, "attach-session", "-t", tmux_name]
            sess.start_pty(argv, env={"LAN_DRIVE_TERM": "1", "TERM": "xterm-256color", "COLORTERM": "truecolor"})
            sess.append(f"\n[tmux attached: {tmux_name} | cwd: {cwd}]\n[Tip: bạn đang ở trong tmux rồi; dùng 'tmux ls' để xem session, hoặc SSH rồi chạy: tmux attach -t {tmux_name}]\n")
        else:
            shell = str(CONFIG.terminal_shell_linux or "/bin/bash")
            if not Path(shell).exists():
                shell = os.environ.get("SHELL", "/bin/sh")
            sess = TerminalSession(sid, "pty", cwd)
            sess.start_pty([shell, "-l"] if shell.endswith(("bash", "zsh", "fish")) else [shell], env={"LAN_DRIVE_TERM": "1"})
            sess.append(f"\n[pty shell | cwd: {cwd}]\n[Tip: gõ 'tmux new-session -A -s landrive' hoặc bấm nút tmux để vào tmux Linux.]\n")

        with self.lock:
            self.sessions[sid] = sess
        return sess

    def get(self, sid: str) -> TerminalSession:
        with self.lock:
            sess = self.sessions.get(sid)
        if not sess:
            raise KeyError("Terminal session not found")
        sess.last_seen = time.time()
        return sess

    def detach(self, sid: str) -> None:
        with self.lock:
            sess = self.sessions.pop(sid, None)
        if sess:
            sess.detach()

    def kill(self, sid: str) -> None:
        with self.lock:
            sess = self.sessions.pop(sid, None)
        if sess:
            sess.kill()

    def list_tmux_sessions(self) -> List[Dict[str, str]]:
        if os.name == "nt":
            return []
        tmux_bin = shutil.which(CONFIG.terminal_tmux_bin) if CONFIG.terminal_tmux_bin else None
        if not tmux_bin:
            return []
        prefix = str(CONFIG.terminal_tmux_session_prefix or "landrive")
        try:
            r = subprocess.run([tmux_bin, "list-sessions", "-F", "#{session_name}\t#{session_created}\t#{session_windows}"], capture_output=True, text=True, timeout=3)
            out = []
            for line in (r.stdout or "").splitlines():
                parts = line.split("\t")
                if parts and parts[0].startswith(prefix):
                    out.append({"name": parts[0], "created": parts[1] if len(parts) > 1 else "", "windows": parts[2] if len(parts) > 2 else ""})
            return out
        except Exception:
            return []


TERM_MANAGER = TerminalManager()


def terminal_run_command(sess: TerminalSession, cmd: str) -> Dict[str, Any]:
    """Windows/simple command fallback."""
    cmd = (cmd or "").strip()
    if not cmd:
        return {"ok": True, "cwd": str(sess.cwd), "output": ""}
    if cmd.lower() in {"clear", "cls"}:
        return {"ok": True, "cwd": str(sess.cwd), "output": "\x0c"}
    if cmd.lower().startswith("cd"):
        rest = cmd[2:].strip().strip('"')
        if not rest:
            return {"ok": True, "cwd": str(sess.cwd), "output": str(sess.cwd) + "\n"}
        target = Path(rest)
        if not target.is_absolute():
            target = (sess.cwd / rest)
        try:
            target = target.resolve()
            if target.is_dir():
                sess.cwd = target
                return {"ok": True, "cwd": str(sess.cwd), "output": ""}
            return {"ok": False, "cwd": str(sess.cwd), "output": f"cd: not a directory: {rest}\n"}
        except Exception as e:
            return {"ok": False, "cwd": str(sess.cwd), "output": f"cd: {e}\n"}

    timeout = 0
    try:
        timeout = int(getattr(CONFIG, "terminal_command_timeout", 0) or 0)
    except Exception:
        timeout = 0
    try:
        shell_windows = str(CONFIG.terminal_shell_windows or "powershell").lower()
        if os.name == "nt" and "cmd" not in shell_windows:
            argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
            if not shutil.which("powershell") and shutil.which("pwsh"):
                argv[0] = "pwsh"
        elif os.name == "nt":
            argv = ["cmd", "/C", cmd]
        else:
            argv = [str(CONFIG.terminal_shell_linux or "/bin/sh"), "-lc", cmd]
        r = subprocess.run(argv, cwd=str(sess.cwd), capture_output=True, text=True, timeout=timeout if timeout > 0 else None, errors="replace")
        output = (r.stdout or "") + (r.stderr or "")
        if len(output) > int(CONFIG.terminal_max_buffer_chars):
            output = output[-int(CONFIG.terminal_max_buffer_chars):]
        return {"ok": r.returncode == 0, "cwd": str(sess.cwd), "code": r.returncode, "output": output}
    except subprocess.TimeoutExpired:
        return {"ok": False, "cwd": str(sess.cwd), "output": "\n[command timeout]\n"}
    except Exception as e:
        return {"ok": False, "cwd": str(sess.cwd), "output": f"\n[command error: {e}]\n"}


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


class Handler(SimpleHTTPRequestHandler):
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
        self.send_bytes(status, json_dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def content_length(self, *, max_bytes: Optional[int] = None) -> int:
        raw = self.headers.get("Content-Length") or "0"
        try:
            n = int(raw)
        except Exception:
            raise BadRequest("invalid Content-Length")
        if n < 0:
            raise BadRequest("invalid Content-Length")
        if max_bytes is not None and n > max_bytes:
            raise BadRequest(f"request body too large; max {size_fmt(max_bytes)}")
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

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/favicon.ico":
                self.send_response(204); self.end_headers(); return
            if parsed.path == "/api/info":
                return self.api_info()
            if parsed.path == "/api/config":
                return self.api_config_get()
            if parsed.path == "/api/list":
                return self.api_list(parsed.query)
            if parsed.path == "/api/thumb":
                return self.api_thumb(parsed.query)
            if parsed.path == "/api/folder_preview":
                return self.api_folder_preview(parsed.query)
            if parsed.path == "/api/video_info":
                return self.api_video_info(parsed.query)
            if parsed.path == "/api/subtitle":
                return self.api_subtitle(parsed.query)
            if parsed.path == "/api/plugin/info":
                return self.api_plugin_info()
            if parsed.path in ("/api/plugin/preview", "/api/preview"):
                return self.api_plugin_preview(parsed.query)
            if parsed.path == "/api/term/read":
                return self.api_term_read(parsed.query)
            if parsed.path == "/api/term/sessions":
                return self.api_term_sessions()

            target = safe_join(parsed.path)
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
        except PermissionError as e:
            self.send_error(403, str(e))
        except BrokenPipeError:
            return
        except Exception as e:
            self.send_error(500, f"Server error: {e}")

    def do_POST(self) -> None:
        try:
            parsed = urllib.parse.urlsplit(self.path)
            route = parsed.path
            if route == "/api/upload": return self.api_upload(parsed.query)
            if route == "/api/save": return self.api_save()
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
            if route == "/api/term/new": return self.api_term_new()
            if route == "/api/term/input": return self.api_term_input()
            if route == "/api/term/resize": return self.api_term_resize()
            if route == "/api/term/detach": return self.api_term_detach()
            if route == "/api/term/kill": return self.api_term_kill()
            if route == "/api/term/run": return self.api_term_run()
            self.send_error(404, "API not found")
        except BadRequest as e:
            self.send_json(400, {"error": str(e)})
        except PermissionError as e:
            self.send_json(403, {"error": str(e)})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def api_term_sessions(self) -> None:
        self.send_json(200, {"ok": True, "sessions": TERM_MANAGER.list_tmux_sessions()})

    def api_term_new(self) -> None:
        data = self.read_json()
        rel = str(data.get("path", ""))
        cwd = safe_join("/" + rel)
        if not cwd.is_dir():
            cwd = cwd.parent
        sess = TERM_MANAGER.new(cwd)
        self.send_json(200, {
            "ok": True,
            "id": sess.id,
            "mode": sess.mode,
            "cwd": str(sess.cwd),
            "tmux_name": sess.tmux_name,
            "poll_ms": CONFIG.terminal_poll_ms,
            "height_px": CONFIG.terminal_start_height_px,
        })

    def api_term_read(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        sid = qs.get("id", [""])[0]
        try:
            sess = TERM_MANAGER.get(sid)
            self.send_json(200, {"ok": True, "id": sid, "alive": sess.alive, "mode": sess.mode, "data": sess.drain(), "cwd": str(sess.cwd), "tmux_name": sess.tmux_name})
        except KeyError:
            self.send_json(404, {"error": "terminal session not found"})

    def api_term_input(self) -> None:
        data = self.read_json()
        sid = str(data.get("id", ""))
        payload = str(data.get("data", "")).replace("\x08", "\x7f")
        try:
            sess = TERM_MANAGER.get(sid)
            if sess.mode == "command":
                self.send_json(400, {"error": "command-mode terminal uses /api/term/run"}); return
            sess.write(payload)
            self.send_json(200, {"ok": True})
        except KeyError:
            self.send_json(404, {"error": "terminal session not found"})

    def api_term_resize(self) -> None:
        data = self.read_json()
        sid = str(data.get("id", ""))
        try:
            sess = TERM_MANAGER.get(sid)
            sess.resize(int(data.get("cols") or 100), int(data.get("rows") or 30))
            self.send_json(200, {"ok": True})
        except KeyError:
            self.send_json(404, {"error": "terminal session not found"})

    def api_term_detach(self) -> None:
        data = self.read_json()
        sid = str(data.get("id", ""))
        TERM_MANAGER.detach(sid)
        self.send_json(200, {"ok": True})

    def api_term_kill(self) -> None:
        data = self.read_json()
        sid = str(data.get("id", ""))
        TERM_MANAGER.kill(sid)
        self.send_json(200, {"ok": True})

    def api_term_run(self) -> None:
        data = self.read_json()
        sid = str(data.get("id", ""))
        cmd = str(data.get("cmd", ""))
        try:
            sess = TERM_MANAGER.get(sid)
            result = terminal_run_command(sess, cmd)
            self.send_json(200, result)
        except KeyError:
            self.send_json(404, {"error": "terminal session not found"})

    def api_info(self) -> None:
        data = {
            "app": APP_NAME,
            "root": str(CONFIG.root),
            "platform": platform.platform(),
            "pillow": HAS_PIL,
            "ffmpeg": bool(FFMPEG),
            "ffprobe": bool(FFPROBE),
            "config": str(CONFIG.config_path),
            "defaults": {
                "default_sort": CONFIG.default_sort,
                "default_view": CONFIG.default_view,
                "page_limit": CONFIG.page_limit,
                "folders_first": CONFIG.folders_first,
                "search_debounce_ms": CONFIG.search_debounce_ms,
                "terminal_enabled": CONFIG.terminal_enabled,
                "terminal_backend_linux": CONFIG.terminal_backend_linux,
                "terminal_backend_windows": CONFIG.terminal_backend_windows,
                "terminal_poll_ms": CONFIG.terminal_poll_ms,
                "terminal_max_buffer_chars": CONFIG.terminal_max_buffer_chars,
                "terminal_start_height_px": CONFIG.terminal_start_height_px,
                "terminal_mobile_extra_keys": CONFIG.terminal_mobile_extra_keys,
                "thumb_fit": CONFIG.thumb_fit,
                "folder_preview_enabled": CONFIG.folder_preview_enabled,
                "folder_preview_animation": CONFIG.folder_preview_animation,
                "upload_parallel": CONFIG.upload_parallel,
                "upload_conflict": CONFIG.upload_conflict,
            },
            "terminal": {
                "enabled": CONFIG.terminal_enabled,
                "pty_available": HAS_UNIX_PTY,
                "tmux": bool(shutil.which(CONFIG.terminal_tmux_bin)) if os.name != "nt" else False,
                "mode": "command" if os.name == "nt" else CONFIG.terminal_backend_linux,
            },
            "plugin": {
                "enabled": plugin_enabled(),
                "config": str(plugin_config_path()),
            },
        }
        self.send_json(200, data)

    def api_plugin_info(self) -> None:
        if LAN_PLUGIN is None:
            self.send_json(200, {"ok": True, "enabled": False, "error": "plugin.py not loaded"})
            return
        try:
            info = LAN_PLUGIN.info(plugin_config_path())
            info["enabled"] = True
            self.send_json(200, info)
        except Exception as e:
            self.send_json(500, {"error": str(e), "enabled": False})

    def api_plugin_preview(self, query: str) -> None:
        if LAN_PLUGIN is None:
            self.send_error(404, "plugin.py not loaded")
            return
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        target = safe_join("/" + rel)
        if not target.is_file():
            self.send_error(404, "preview target not found")
            return
        try:
            body = LAN_PLUGIN.render_preview_page(target, CONFIG.root, plugin_config_path(), CONFIG.title)
            self.send_bytes(200, body, "text/html; charset=utf-8")
        except Exception as e:
            self.send_error(500, f"preview error: {e}")

    def api_plugin_extensions(self) -> None:
        if LAN_PLUGIN is None:
            self.send_json(404, {"error": "plugin.py not loaded"})
            return
        data = self.read_json()
        try:
            if "add" in data:
                info = LAN_PLUGIN.add_extension(plugin_config_path(), str(data.get("add") or ""))
            elif "remove" in data:
                info = LAN_PLUGIN.remove_extension(plugin_config_path(), str(data.get("remove") or ""))
            else:
                info = LAN_PLUGIN.info(plugin_config_path())
            info["enabled"] = True
            self.send_json(200, info)
        except Exception as e:
            self.send_json(400, {"error": str(e)})

    def api_config_get(self) -> None:
        self.send_json(200, config_to_dict(CONFIG))

    def api_config_post(self) -> None:
        data = self.read_json()
        changed: Dict[str, Any] = {}
        if "default_sort" in data:
            CONFIG.default_sort = normalize_sort(data.get("default_sort"))
            changed["default_sort"] = CONFIG.default_sort
        if "default_view" in data:
            CONFIG.default_view = normalize_view(data.get("default_view"))
            changed["default_view"] = CONFIG.default_view
        if "page_limit" in data:
            CONFIG.page_limit = normalize_page_limit(data.get("page_limit"))
            changed["page_limit"] = CONFIG.page_limit
        if "folders_first" in data:
            CONFIG.folders_first = bool(data.get("folders_first"))
            changed["folders_first"] = CONFIG.folders_first
        if "search_debounce_ms" in data:
            try:
                CONFIG.search_debounce_ms = max(100, min(int(data.get("search_debounce_ms")), 1500))
            except Exception:
                pass
            changed["search_debounce_ms"] = CONFIG.search_debounce_ms
        if "thumb_fit" in data:
            CONFIG.thumb_fit = normalize_fit(data.get("thumb_fit"))
            changed["thumb_fit"] = CONFIG.thumb_fit
        if "folder_preview_fit" in data:
            CONFIG.folder_preview_fit = normalize_fit(data.get("folder_preview_fit"))
            changed["folder_preview_fit"] = CONFIG.folder_preview_fit
        if "folder_preview_enabled" in data:
            CONFIG.folder_preview_enabled = bool(data.get("folder_preview_enabled"))
            changed["folder_preview_enabled"] = CONFIG.folder_preview_enabled
        if "folder_preview_animation" in data:
            CONFIG.folder_preview_animation = normalize_animation(data.get("folder_preview_animation"))
            changed["folder_preview_animation"] = CONFIG.folder_preview_animation
        if "upload_conflict" in data:
            CONFIG.upload_conflict = normalize_conflict(data.get("upload_conflict"))
            changed["upload_conflict"] = CONFIG.upload_conflict
        if "upload_parallel" in data:
            try:
                CONFIG.upload_parallel = max(1, min(int(data.get("upload_parallel") or 3), 8))
            except Exception:
                pass
            changed["upload_parallel"] = CONFIG.upload_parallel
        if changed:
            write_config_file(CONFIG)
        self.send_json(200, {"ok": True, "changed": changed})

    def api_list(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("path", [""])[0]
        offset = int(qs.get("offset", ["0"])[0] or 0)
        limit = int(qs.get("limit", [str(CONFIG.page_limit)])[0] or CONFIG.page_limit)
        sort_mode = normalize_sort(qs.get("sort", [CONFIG.default_sort])[0])
        q = qs.get("q", [""])[0]
        recursive_depth_raw = qs.get("recursive_depth", ["0"])[0]
        recursive_depth = normalize_recursive_depth(recursive_depth_raw)
        folders_first_raw = qs.get("folders_first", ["true" if CONFIG.folders_first else "false"])[0]
        folders_first = str(folders_first_raw).lower() not in {"0", "false", "no", "off"}
        target = safe_join("/" + rel)
        if not target.is_dir():
            self.send_json(404, {"error": "not a folder"}); return
        items, next_offset, has_more, errors, total = list_entries_page(target, offset, limit, sort_mode, q, folders_first, recursive_depth)
        if offset == 0:
            rel_norm = target.resolve().relative_to(CONFIG.root.resolve()).as_posix()
            if rel_norm != ".":
                parent = Path(rel_norm).parent.as_posix()
                href = "/" if parent == "." else "/" + quote_path(parent) + "/"
                items.insert(0, {"special": "back", "href": href})
        self.send_json(200, {"items": items, "nextOffset": next_offset, "hasMore": has_more, "errors": errors, "total": total, "sort": sort_mode, "folders_first": folders_first, "recursive_depth": recursive_depth_raw if q.strip() else "0"})

    def api_folder_preview(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        target = safe_join("/" + rel)
        if not target.is_dir():
            self.send_json(404, {"error": "folder not found"}); return
        self.send_json(200, {"ok": True, "items": folder_preview_items(target)})

    def api_video_info(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        target = safe_join("/" + rel)
        if not target.is_file() or classify(target) != "video":
            self.send_json(404, {"error": "video not found"}); return
        self.send_json(200, video_info(target))

    def api_subtitle(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        try:
            idx = max(0, min(int(qs.get("i", ["0"])[0] or 0), 50))
        except Exception:
            idx = 0
        video = safe_join("/" + rel)
        if not video.is_file() or classify(video) != "video":
            self.send_error(404, "video not found"); return
        subs = video_subtitle_sidecars(video)
        if idx >= len(subs):
            self.send_error(404, "subtitle not found"); return
        try:
            body = subtitle_to_vtt(subs[idx]).encode("utf-8", "replace")
        except Exception as e:
            self.send_error(500, f"subtitle error: {e}"); return
        self.send_bytes(200, body, "text/vtt; charset=utf-8")

    def api_thumb(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        target = safe_join("/" + rel)
        if not target.is_file():
            self.send_error(404, "thumb target not found"); return
        kind = classify(target)
        dst = thumb_cache_path(target, kind)
        if not dst.exists():
            ok = False
            if kind == "image": ok = make_image_thumb(target, dst)
            elif kind == "video": ok = make_video_thumb(target, dst)
            if not ok:
                self.send_error(404, "thumbnail unavailable"); return
        self.serve_static_file(dst, download=False, ctype="image/jpeg")

    def api_upload(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        base_rel = qs.get("path", [""])[0]
        name = qs.get("name", [""])[0]
        conflict = normalize_conflict(qs.get("conflict", [CONFIG.upload_conflict])[0])
        if not name:
            raise BadRequest("missing name")
        total = self.content_length()
        base = safe_join("/" + base_rel)
        if base.exists() and not base.is_dir():
            drain_stream(self.rfile, total)
            raise BadRequest("upload path is not a folder")
        base.mkdir(parents=True, exist_ok=True)

        parts: List[str] = []
        for p in name.replace("\\", "/").split("/"):
            if not p or p in {".", ".."}:
                continue
            parts.append(clean_component(p))
        if not parts:
            drain_stream(self.rfile, total)
            raise BadRequest("bad filename")
        dest = base.joinpath(*parts).resolve()
        try:
            dest.relative_to(CONFIG.root.resolve())
        except ValueError:
            drain_stream(self.rfile, total)
            self.send_json(403, {"error": "outside root"}); return
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if conflict == "skip":
                drain_stream(self.rfile, total)
                self.send_json(200, {"ok": True, "skipped": True, "file": rel_url_for_path(dest), "reason": "exists"}); return
            if conflict == "ask":
                drain_stream(self.rfile, total)
                self.send_json(409, {"error": "exists", "file": rel_url_for_path(dest)}); return
            if conflict == "rename":
                stem, suffix = dest.stem, dest.suffix
                parent = dest.parent
                for i in range(1, 10000):
                    cand = parent / f"{stem} ({i}){suffix}"
                    if not cand.exists():
                        dest = cand.resolve()
                        break

        tmp: Optional[Path] = None
        written = 0
        remaining = total
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".uploading-", dir=str(dest.parent))
            tmp = Path(tmp_name)
            with os.fdopen(fd, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            if written != total or remaining != 0:
                raise BadRequest(f"incomplete upload: got {written} of {total} bytes")
            os.replace(tmp, dest)
            tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        self.send_json(200, {"ok": True, "file": rel_url_for_path(dest), "bytes": written})

    def api_save(self) -> None:
        data = self.read_json()
        rel = str(data.get("path", ""))
        content = str(data.get("content", ""))
        target = safe_join("/" + rel)
        if not target.is_file():
            self.send_json(404, {"error": "file not found"}); return
        if classify(target) != "text":
            self.send_json(400, {"error": "not a text file"}); return
        tmp = target.with_name(target.name + f".save-{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, target)
        self.send_json(200, {"ok": True})

    def api_mkdir(self) -> None:
        data = self.read_json()
        base = safe_join("/" + str(data.get("path", "")))
        name = clean_component(str(data.get("name", "")))
        dest = (base / name).resolve()
        dest.relative_to(CONFIG.root.resolve())
        dest.mkdir(parents=True, exist_ok=False)
        self.send_json(200, {"ok": True, "path": rel_url_for_path(dest)})

    def api_newfile(self) -> None:
        data = self.read_json()
        base = safe_join("/" + str(data.get("path", "")))
        name = clean_component(str(data.get("name", "")))
        dest = (base / name).resolve()
        dest.relative_to(CONFIG.root.resolve())
        if dest.exists():
            self.send_json(409, {"error": "file already exists"}); return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("", encoding="utf-8")
        self.send_json(200, {"ok": True, "edit_url": rel_url_for_path(dest) + "?edit=1"})

    def api_rename(self) -> None:
        data = self.read_json()
        target = safe_join("/" + str(data.get("path", "")))
        name = clean_component(str(data.get("name", "")))
        if not target.exists():
            self.send_json(404, {"error": "not found"}); return
        dest = (target.parent / name).resolve()
        dest.relative_to(CONFIG.root.resolve())
        if dest.exists():
            self.send_json(409, {"error": "target exists"}); return
        target.rename(dest)
        self.send_json(200, {"ok": True, "path": rel_url_for_path(dest)})

    def api_copy(self) -> None:
        data = self.read_json()
        dest_dir = resolve_destination_dir(data, current_path if (current_path := str(data.get("dest", data.get("dest_dir", "")))) is not None else "")
        conflict = normalize_conflict(data.get("conflict", "rename"))
        copied = []
        skipped = 0
        for rel in payload_paths(data):
            src = resolve_existing(rel)
            result = copy_item(src, dest_dir, conflict=conflict)
            if result is None:
                skipped += 1
            else:
                copied.append(rel_url_for_path(result).lstrip("/"))
        self.send_json(200, {"ok": True, "copied": copied, "skipped": skipped})

    def api_move(self) -> None:
        data = self.read_json()
        dest_dir = resolve_destination_dir(data)
        conflict = normalize_conflict(data.get("conflict", "rename"))
        moved = []
        skipped = 0
        for rel in payload_paths(data):
            src = resolve_existing(rel)
            if src.resolve() == CONFIG.root.resolve():
                raise BadRequest("cannot move root")
            result = move_item(src, dest_dir, conflict=conflict)
            if result is None:
                skipped += 1
            else:
                moved.append(rel_url_for_path(result).lstrip("/"))
        self.send_json(200, {"ok": True, "moved": moved, "skipped": skipped})

    def api_duplicate(self) -> None:
        data = self.read_json()
        conflict = normalize_conflict(data.get("conflict", "rename"))
        duplicated = []
        skipped = 0
        for rel in payload_paths(data):
            src = resolve_existing(rel)
            if src.resolve() == CONFIG.root.resolve():
                raise BadRequest("cannot duplicate root")
            result = copy_item(src, src.parent, name=duplicate_name(src), conflict=conflict)
            if result is None:
                skipped += 1
            else:
                duplicated.append(rel_url_for_path(result).lstrip("/"))
        self.send_json(200, {"ok": True, "duplicated": duplicated, "skipped": skipped})

    def api_batch_rename(self) -> None:
        data = self.read_json()
        items = data.get("items")
        if not isinstance(items, list) or not items:
            raise BadRequest("items must be a non-empty list")
        planned: List[Tuple[Path, Path]] = []
        seen: set[Path] = set()
        for item in items:
            if not isinstance(item, dict):
                raise BadRequest("each batch rename item must be an object")
            src = resolve_existing(str(item.get("path", "")))
            if src.resolve() == CONFIG.root.resolve():
                raise BadRequest("cannot rename root")
            name = clean_component(str(item.get("name", "")))
            dest = ensure_under_root(src.parent / name)
            if src.resolve() == dest.resolve():
                continue
            if dest in seen:
                raise BadRequest(f"duplicate target in batch: {name}")
            if dest.exists():
                raise BadRequest(f"target exists: {name}")
            planned.append((src, dest))
            seen.add(dest)
        renamed = []
        for src, dest in planned:
            src.rename(dest)
            renamed.append({"from": rel_url_for_path(src).lstrip("/"), "to": rel_url_for_path(dest).lstrip("/")})
        self.send_json(200, {"ok": True, "renamed": renamed})

    def api_extract(self) -> None:
        data = self.read_json()
        archive = resolve_existing(str(data.get("path", "")))
        if not archive.is_file():
            raise BadRequest("archive path must be a file")
        dest = resolve_destination_dir(data, archive.parent.resolve().relative_to(CONFIG.root.resolve()).as_posix())
        conflict = normalize_conflict(data.get("conflict", "rename"))
        result = extract_archive(archive, dest, conflict)
        result["dest"] = rel_url_for_path(dest).lstrip("/")
        self.send_json(200, result)

    def api_archive(self) -> None:
        payload = parse_archive_payload(self)
        rels = payload_paths(payload)
        paths = [resolve_existing(rel) for rel in rels]
        fmt = str(payload.get("format", "zip")).lower()
        compression = str(payload.get("compression", "compress")).lower()
        if compression not in {"store", "compress"}:
            raise BadRequest("compression must be store or compress")
        filename, ctype, mode = archive_response_meta(fmt, compression)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if mode == "zip":
            zip_compression = zipfile.ZIP_STORED if compression == "store" else zipfile.ZIP_DEFLATED
            with zipfile.ZipFile(self.wfile, "w", compression=zip_compression, compresslevel=(0 if compression == "store" else 3)) as zf:
                for path, arc in iter_archive_entries(paths):
                    try:
                        if path.is_dir():
                            zf.writestr(arc.rstrip("/") + "/", b"")
                        else:
                            zf.write(path, arc)
                    except Exception:
                        pass
        else:
            with tarfile.open(fileobj=self.wfile, mode=mode) as tf:
                for path, arc in iter_archive_entries(paths):
                    try:
                        tf.add(path, arcname=arc, recursive=False)
                    except Exception:
                        pass

    def api_delete(self) -> None:
        data = self.read_json()
        paths = data.get("paths") or []
        deleted = 0
        for rel in paths:
            target = safe_join("/" + str(rel))
            if target.resolve() == CONFIG.root.resolve():
                continue
            if target.is_dir():
                shutil.rmtree(target)
                deleted += 1
            elif target.exists():
                target.unlink()
                deleted += 1
        self.send_json(200, {"ok": True, "deleted": deleted})

    def api_zip(self) -> None:
        # Accept form because browser download from fetch is more awkward; JSON fallback too.
        n = self.content_length(max_bytes=MAX_ZIP_PAYLOAD)
        raw = self.read_body_exact(n) if n else b""
        payload = {}
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            payload = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        else:
            form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
            payload = json.loads(form.get("payload", ["{}"])[0])
        paths = payload.get("paths") or []
        filename = f"lan-drive-{int(time.time())}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        # ZipFile needs seekable output for central directory? It can write to unseekable in py3.5+ via data descriptors.
        with zipfile.ZipFile(self.wfile, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
            for rel in paths:
                target = safe_join("/" + str(rel))
                if not target.exists():
                    continue
                if target.is_dir():
                    base = target.parent
                    for root, dirs, files in os.walk(target):
                        dirs[:] = [d for d in dirs if not should_hide_entry(Path(root), d)]
                        for fn in files:
                            if should_hide_entry(Path(root), fn):
                                continue
                            p = Path(root) / fn
                            try:
                                arc = p.relative_to(base).as_posix()
                                zf.write(p, arc)
                            except Exception:
                                pass
                else:
                    zf.write(target, target.name)

    def serve_directory(self, path: Path) -> None:
        rel = path.resolve().relative_to(CONFIG.root.resolve()).as_posix()
        if rel == ".": rel = ""
        body = f"""
<div class="app">
  <header class="top">
    <div class="top-inner">
      <div class="brand"><div class="logo">LD</div><div><div class="brand-title">{html_escape(CONFIG.title)}</div><div class="brand-sub">Root: {html_escape(str(CONFIG.root))}</div></div></div>
      <div class="search">
        <select id="recursiveDepth" class="search-depth" onchange="changeRecursiveDepth(this)" title="Độ sâu tìm đệ quy; 0 chỉ tìm thư mục hiện tại">
          <option value="0">Hiện tại</option>
          <option value="all">All</option>
          <option value="1">1 cấp</option>
          <option value="2">2 cấp</option>
          <option value="3">3 cấp</option>
          <option value="4">4 cấp</option>
          <option value="5">5 cấp</option>
          <option value="6">6 cấp</option>
        </select>
        <input id="q" type="search" placeholder="Tìm tên, đường dẫn, đuôi file...">
      </div>
      <div class="actions">
        <button class="btn primary" onclick="openUploadDialog()">⬆️ <span class="label">Upload</span></button>
        <button class="btn" onclick="mkdir()">➕ <span class="label">Thư mục</span></button>
        <button class="btn" onclick="newFile()">📝 <span class="label">File</span></button>
        <button class="btn terminal-btn" onclick="toggleTerminal()">⌨️ <span class="label">Terminal</span></button>
      </div>
    </div>
    <div class="crumbs">{breadcrumb(rel)}</div>
  </header>
  <main class="main">
    <div class="toolbar">
      <div class="view-toggle"><button data-view="grid" onclick="setView('grid')">Grid</button><button data-view="list" onclick="setView('list')">List</button></div>
      <select id="sortSelect" class="select" onchange="changeSort(this)" title="Sắp xếp">
        <option value="name-asc">Tên A→Z</option>
        <option value="name-desc">Tên Z→A</option>
        <option value="mtime-desc">Ngày mới nhất</option>
        <option value="mtime-asc">Ngày cũ nhất</option>
        <option value="size-desc">Dung lượng lớn nhất</option>
        <option value="size-asc">Dung lượng nhỏ nhất</option>
        <option value="type-asc">Loại file A→Z</option>
        <option value="type-desc">Loại file Z→A</option>
        <option value="ext-asc">Đuôi file A→Z</option>
        <option value="ext-desc">Đuôi file Z→A</option>
      </select>
      <select id="limitSelect" class="select compact" onchange="changeLimit(this)" title="Số item mỗi lần tải">
        <option value="100">100/lần</option>
        <option value="220">220/lần</option>
        <option value="500">500/lần</option>
        <option value="1000">1000/lần</option>
      </select>
      <label class="checkline" title="Giữ thư mục nằm trước file khi sắp xếp"><input id="foldersFirst" type="checkbox" onchange="changeFoldersFirst(this)"> 📁 trước</label>
      <select id="thumbFit" class="select compact" onchange="changeThumbFit(this)" title="Cách fit thumbnail"><option value="contain">Fit</option><option value="cover">Crop</option></select>
      <label class="checkline" title="Bật/tắt preview 2x2 cho folder"><input id="folderPreviewToggle" type="checkbox" onchange="toggleFolderPreview(this)"> Preview</label>
      <select id="previewAnim" class="select compact" onchange="changePreviewAnimation(this)" title="Animation folder preview"><option value="none">No anim</option><option value="fade">Fade</option><option value="flip">Flip</option><option value="slide">Slide</option></select>
      <button class="btn small" onclick="refreshFolder()">↻ Refresh</button>
      <button class="btn small" onclick="selectVisible()">Chọn hiện</button>
      <button class="btn small ghost" onclick="clearSel()">Bỏ chọn</button>
      <span id="selCount" class="sub"></span>
      <div class="grow"></div>
      <button id="shareBtn" class="btn small hidden" onclick="shareOne()">🔗 Share</button>
      <button id="previewBtn" class="btn small hidden" onclick="previewSelected()">👁 Preview</button>
      <button class="btn small" onclick="addPreviewExtension()" title="Thêm đuôi/pattern để plugin đọc nhanh, ví dụ .foo hoặc *.env.*">＋ Đuôi đọc</button>
      <button id="copyBtn" class="btn small hidden" onclick="copySel()">📋 Copy</button>
      <button id="moveBtn" class="btn small hidden" onclick="moveSel()">➡️ Move</button>
      <button id="duplicateBtn" class="btn small hidden" onclick="duplicateSel()">⧉ Duplicate</button>
      <button id="batchRenameBtn" class="btn small hidden" onclick="batchRenameSel()">🔤 Batch rename</button>
      <button id="extractBtn" class="btn small hidden" onclick="extractSelected()">📦 Extract</button>
      <button id="archiveBtn" class="btn small hidden" onclick="archiveSelected()">🗜 Archive</button>
      <button id="renameBtn" class="btn small warn hidden" onclick="renameOne()">✏️ Rename</button>
      <button id="downloadBtn" class="btn small hidden" onclick="downloadSelected()">⬇️ Tải</button>
      <button id="deleteBtn" class="btn small danger hidden" onclick="deleteSel()">🗑️ Xoá</button>
    </div>
    <section id="grid" class="dropzone grid"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></section>
  </main>
</div>
<input id="fileInput" class="hidden" type="file" multiple>
<input id="folderInput" class="hidden" type="file" webkitdirectory directory multiple>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()"><div class="modal-box"><div class="modal-head"><div class="modal-title-wrap"><div id="modalTitle" class="modal-title"></div><div id="modalMeta" class="modal-meta"></div></div><div class="actions"><button id="modalPrevBtn" class="btn small" onclick="stepMedia(-1,event)" title="Trước">←</button><button id="modalNextBtn" class="btn small" onclick="stepMedia(1,event)" title="Tiếp">→</button><button class="btn small" onclick="closeModal()">✕</button></div></div><div class="modal-stage"><button id="modalPrevFloat" class="modal-nav modal-prev" onclick="stepMedia(-1,event)" title="Trước">‹</button><div id="modalBody" class="modal-body"></div><button id="modalNextFloat" class="modal-nav modal-next" onclick="stepMedia(1,event)" title="Tiếp">›</button></div></div></div>
<div id="uploadModal" class="upload-backdrop" onclick="if(event.target===this)closeUploadDialog()">
  <div class="upload-box">
    <div class="upload-head"><div><div class="upload-title">⬆️ Upload vào: /{html_escape(rel)}</div><div class="sub">Kéo file/folder vào vùng dấu +, hoặc bấm chọn file/folder. Folder drag/drop tốt nhất trên Chrome/Edge.</div></div><button class="btn small" onclick="closeUploadDialog()">✕</button></div>
    <div class="upload-body">
      <div id="uploadDrop" class="upload-drop"><div><div class="upload-plus">＋</div><b>Kéo file/folder vào đây</b><div>hoặc bấm để chọn file</div></div></div>
      <div class="upload-options">
        <button class="btn" onclick="pickUploadFiles()">Chọn file</button>
        <button class="btn" onclick="pickUploadFolder()">Chọn folder</button>
        <label class="checkline">Trùng tên: <select id="uploadConflict" class="select compact"><option value="ask">Hỏi</option><option value="overwrite">Ghi đè</option><option value="skip">Bỏ qua</option><option value="rename">Tự đổi tên</option></select></label>
      </div>
      <div id="uploadQueue" class="upload-queue"></div>
    </div>
    <div class="upload-foot"><div id="uploadSummary" class="upload-summary">0 file</div><div class="upload-progress"><span id="uploadModalBar"></span></div><button class="btn ghost" onclick="clearUploadQueue()">Clear</button><button class="btn primary" onclick="startUploadQueue()">Start Upload</button></div>
  </div>
</div>
<div id="termDrawer" class="term-drawer" style="height:{int(CONFIG.terminal_start_height_px)}px">
  <div class="term-head">
    <div class="term-title">⌨️ Terminal <span id="termMode" class="term-mode"></span><span id="termCwd" class="term-cwd"></span></div>
    <div class="term-actions">
      <button class="btn small" onclick="newTerminalSession()">New</button>
      <button class="btn small" onclick="termStartTmux()">tmux</button>
      <button class="btn small" onclick="termClear()">Clear</button>
      <button class="btn small" onclick="termCopy()">Copy</button>
      <button class="btn small" onclick="refreshFolder()">Refresh</button>
      <button class="btn small" onclick="termFullscreen()">⛶</button>
      <button class="btn small warn" onclick="termDetach()">Detach</button>
      <button class="btn small danger" onclick="termKill()">Kill</button>
      <button class="btn small" onclick="termHide()">✕</button>
    </div>
  </div>
  <pre id="termScreen" class="term-screen" tabindex="0"></pre>
  <div id="termCommand" class="term-command hidden"><span id="termPrompt"></span><input id="termLine" autocomplete="off" spellcheck="false" placeholder="gõ lệnh rồi Enter"></div>
  <div id="termKeys" class="term-keys">
    <button onclick="termSendCtrl('c')">Ctrl-C</button><button onclick="termSend('\x7f')">⌫</button><button onclick="termSend('\t')">Tab</button><button onclick="termSend('\x1b[A')">↑</button><button onclick="termSend('\x1b[B')">↓</button><button onclick="termSend('\x1b')">Esc</button><button onclick="termSend('/')">/</button><button onclick="termSend('..')">..</button>
  </div>
</div>
<div id="ctxMenu" class="ctx-menu hidden" onclick="event.stopPropagation()">
  <button data-act="open" onclick="contextAction('open')">↗ Open</button>
  <button data-act="preview" onclick="contextAction('preview')">👁 Preview</button>
  <button data-act="edit" onclick="contextAction('edit')">📝 Edit</button>
  <button data-act="rename" onclick="contextAction('rename')">✏️ Rename</button>
  <button data-act="download" onclick="contextAction('download')">⬇️ Download</button>
  <button data-act="archive" onclick="contextAction('archive')">🗜 Archive</button>
  <button data-act="extract" onclick="contextAction('extract')">📦 Extract</button>
  <button data-act="copy" onclick="contextAction('copy')">📋 Copy</button>
  <button data-act="move" onclick="contextAction('move')">➡️ Move</button>
  <button data-act="duplicate" onclick="contextAction('duplicate')">⧉ Duplicate</button>
  <button data-act="batch" onclick="contextAction('batch')">🔤 Batch rename</button>
  <button data-act="share" onclick="contextAction('share')">🔗 Copy link</button>
  <button data-act="delete" class="danger" onclick="contextAction('delete')">🗑 Delete</button>
</div>
<div id="toast" class="toast"></div>
"""
        self.send_bytes(200, page_shell(CONFIG.title, body, "/" + rel), "text/html; charset=utf-8")

    def serve_editor(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "file not found"); return
        if classify(path) != "text":
            self.send_error(400, "not editable text"); return
        st = path.stat()
        if st.st_size > MAX_TEXT_PREVIEW:
            self.send_error(413, "text file too large to edit safely"); return
        rel = path.resolve().relative_to(CONFIG.root.resolve()).as_posix()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.send_error(500, f"cannot read file: {e}"); return
        parent = Path(rel).parent.as_posix()
        back = "/" if parent == "." else "/" + quote_path(parent) + "/"
        body = f"""
<div class="editor">
  <div class="editorbar">
    <a class="btn" href="{back}">↩ Back</a>
    <div class="title">📝 {html_escape(rel)}</div>
    <div class="grow"></div>
    <span id="saveStatus" class="sub"></span>
    <button class="btn primary" onclick="saveEdit()">💾 Save</button>
  </div>
  <textarea id="editarea" class="editarea" spellcheck="false">{html_escape(content)}</textarea>
</div>
<div id="toast" class="toast"></div>
<script>
async function saveEdit(){{
  const st=document.getElementById('saveStatus'); st.textContent='Saving...';
  try{{
    const r=await fetch('/api/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{path:{json_dumps(rel)},content:document.getElementById('editarea').value}})}});
    const j=await r.json(); if(!r.ok||j.error) throw new Error(j.error||r.statusText);
    st.textContent='Saved'; setTimeout(()=>st.textContent='',2000);
  }}catch(e){{ st.textContent='Error: '+e.message; }}
}}
document.addEventListener('keydown',e=>{{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){{e.preventDefault();saveEdit();}}}});
</script>
"""
        self.send_bytes(200, page_shell(f"Edit {path.name}", body, "/" + rel), "text/html; charset=utf-8")

    def serve_file(self, path: Path) -> None:
        self.serve_static_file(path, download=False)

    def serve_static_file(self, path: Path, download: bool = False, ctype: Optional[str] = None) -> None:
        st = path.stat()
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        etag = file_etag(path, st)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304); self.end_headers(); return

        range_header = self.headers.get("Range")
        start, end = 0, st.st_size - 1
        status = 200
        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if m:
                a, b = m.group(1), m.group(2)
                if a == "" and b:
                    length = int(b)
                    start = max(0, st.st_size - length)
                else:
                    start = int(a or 0)
                    end = int(b) if b else st.st_size - 1
                if start >= st.st_size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{st.st_size}")
                    self.end_headers(); return
                end = min(end, st.st_size - 1)
                status = 206

        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{st.st_size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)


def ensure_cache_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "thumbs").mkdir(parents=True, exist_ok=True)
    (path / "folder_previews").mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="One-file LAN/Tailscale web file manager")
    p.add_argument("--config", default=str(config_file_default_path()), help="YAML config path, default: lan_drive_config.yaml next to script")
    p.add_argument("--root", default=None, help="Root folder. Linux default: /. Windows default: current drive root")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--show-hidden", action="store_true", default=None)
    p.add_argument("--show-system", action="store_true", default=None, help="Show /proc /sys /run /dev when browsing Linux root")
    p.add_argument("--sort", choices=sorted(VALID_SORTS), default=None, help="Default sort mode")
    p.add_argument("--view", choices=sorted(VALID_VIEWS), default=None, help="Default view mode")
    p.add_argument("--page-limit", type=int, default=None, help="Items per lazy-load page")
    p.add_argument("--save-config", action="store_true", help="Persist CLI overrides to the config file. Without this, CLI overrides are runtime-only.")
    return p.parse_args()


def build_config(args: argparse.Namespace) -> AppConfig:
    config_path = Path(args.config).expanduser().resolve()
    data = dict(DEFAULT_CONFIG_DATA)
    loaded = load_simple_yaml(config_path)
    data.update({k: v for k, v in loaded.items() if v is not None})

    if args.root is not None: data["root"] = args.root
    if args.port is not None: data["port"] = args.port
    if args.host is not None: data["host"] = args.host
    if args.title is not None: data["title"] = args.title
    if args.cache_dir is not None: data["cache_dir"] = args.cache_dir
    if args.show_hidden is True: data["show_hidden"] = True
    if args.show_system is True: data["show_system"] = True
    if args.sort is not None: data["default_sort"] = args.sort
    if args.view is not None: data["default_view"] = args.view
    if args.page_limit is not None: data["page_limit"] = args.page_limit

    root = norm_root(str(data.get("root") or DEFAULT_ROOT))
    return AppConfig(
        root=root,
        port=int(data.get("port") or DEFAULT_PORT),
        host=str(data.get("host") or DEFAULT_HOST),
        title=str(data.get("title") or "LAN Drive"),
        cache_dir=Path(str(data.get("cache_dir") or DEFAULT_CONFIG_DATA["cache_dir"])).expanduser().resolve(),
        config_path=config_path,
        show_hidden=bool(data.get("show_hidden", False)),
        show_system=bool(data.get("show_system", False)),
        default_sort=normalize_sort(data.get("default_sort")),
        default_view=normalize_view(data.get("default_view")),
        page_limit=normalize_page_limit(data.get("page_limit")),
        folders_first=bool(data.get("folders_first", True)),
        search_debounce_ms=max(100, min(int(data.get("search_debounce_ms") or 240), 1500)),
        terminal_enabled=bool(data.get("terminal_enabled", True)),
        terminal_backend_linux=str(data.get("terminal_backend_linux") or "pty"),
        terminal_backend_linux_fallback=str(data.get("terminal_backend_linux_fallback") or "pty"),
        terminal_shell_linux=str(data.get("terminal_shell_linux") or "/bin/bash"),
        terminal_tmux_bin=str(data.get("terminal_tmux_bin") or "tmux"),
        terminal_tmux_session_prefix=str(data.get("terminal_tmux_session_prefix") or "landrive"),
        terminal_tmux_status_bar=bool(data.get("terminal_tmux_status_bar", False)),
        terminal_session_mode=str(data.get("terminal_session_mode") or "per_folder"),
        terminal_backend_windows=str(data.get("terminal_backend_windows") or "command"),
        terminal_shell_windows=str(data.get("terminal_shell_windows") or "powershell"),
        terminal_command_timeout=max(0, min(int(data.get("terminal_command_timeout") or 0), 86400)),
        terminal_max_sessions=max(1, min(int(data.get("terminal_max_sessions") or 8), 32)),
        terminal_idle_detach_minutes=max(5, min(int(data.get("terminal_idle_detach_minutes") or 120), 1440)),
        terminal_max_buffer_chars=max(10000, min(int(data.get("terminal_max_buffer_chars") or 500000), 5000000)),
        terminal_poll_ms=max(80, min(int(data.get("terminal_poll_ms") or 150), 2000)),
        terminal_start_height_px=max(220, min(int(data.get("terminal_start_height_px") or 380), 900)),
        terminal_mobile_extra_keys=bool(data.get("terminal_mobile_extra_keys", True)),
        thumb_fit=normalize_fit(data.get("thumb_fit")),
        folder_preview_enabled=bool(data.get("folder_preview_enabled", True)),
        folder_preview_mode=str(data.get("folder_preview_mode") or "mosaic4"),
        folder_preview_fit=normalize_fit(data.get("folder_preview_fit") or data.get("thumb_fit")),
        folder_preview_rotate=bool(data.get("folder_preview_rotate", True)),
        folder_preview_animation=normalize_animation(data.get("folder_preview_animation")),
        folder_preview_interval_ms=max(1200, min(int(data.get("folder_preview_interval_ms") or 3500), 15000)),
        folder_preview_scan_limit=max(8, min(int(data.get("folder_preview_scan_limit") or 80), 1000)),
        folder_preview_max_items=max(4, min(int(data.get("folder_preview_max_items") or 24), 80)),
        folder_preview_include_video=bool(data.get("folder_preview_include_video", True)),
        upload_auto_start=bool(data.get("upload_auto_start", False)),
        upload_parallel=max(1, min(int(data.get("upload_parallel") or 3), 8)),
        upload_conflict=normalize_conflict(data.get("upload_conflict")),
    )


def main() -> None:
    global CONFIG
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config_existed = config_path.exists()
    CONFIG = build_config(args)
    if not CONFIG.root.exists():
        print(f"Root does not exist: {CONFIG.root}", file=sys.stderr)
        sys.exit(2)
    ensure_cache_dir(CONFIG.cache_dir)
    if args.save_config or not config_existed:
        try:
            write_config_file(CONFIG)
        except Exception as e:
            print(f"Warning: cannot write config {CONFIG.config_path}: {e}", file=sys.stderr)
    os.chdir(str(CONFIG.root))
    ip = get_local_ip_guess()
    print(f"\n{APP_NAME}")
    print(f"Root      : {CONFIG.root}")
    print(f"Config    : {CONFIG.config_path}")
    print(f"Sort/View : {CONFIG.default_sort} / {CONFIG.default_view} / {CONFIG.page_limit} per page")
    print(f"Cache     : {CONFIG.cache_dir}")
    print(f"Pillow    : {'yes' if HAS_PIL else 'no'}")
    print(f"ffmpeg    : {'yes' if FFMPEG else 'no'}")
    print(f"Local     : http://127.0.0.1:{CONFIG.port}")
    print(f"LAN       : http://{ip}:{CONFIG.port}")
    print("Stop      : Ctrl+C\n")
    with ThreadingHTTPServer((CONFIG.host, CONFIG.port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping...")
            httpd.shutdown()

if __name__ == "__main__":
    main()

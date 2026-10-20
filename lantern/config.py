
import argparse
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from .bot_config import LanternBotConfig

APP_NAME = "LAN Drive OneFile"
DEFAULT_PORT = int(os.environ.get("LAN_DRIVE_PORT", "9999"))
DEFAULT_HOST = os.environ.get("LAN_DRIVE_HOST", "127.0.0.1")
# Per-server budget shared by all LAN clients; other Lantern processes have separate limits.
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
    "terminal_local_bypass": True,
    "terminal_max_sessions": 16,
    "terminal_max_buffer_chars": 204800,
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
    terminal_password_hash: str = ""
    terminal_local_bypass: bool = True
    terminal_max_sessions: int = 16
    terminal_max_buffer_chars: int = 204800
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
    lantern_bot: LanternBotConfig = LanternBotConfig()

def config_file_default_path() -> Path:
    try:
        return Path(__file__).resolve().parents[1] / "lan_drive_config.yaml"
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
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8", errors="strict"))
    except Exception as exc:
        raise ValueError(f"Invalid YAML config {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("Lantern config root must be a YAML mapping")
    return dict(loaded)

def yaml_quote(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\"')
    return f'"{text}"'

def config_to_dict(cfg: "AppConfig", *, include_secrets: bool = False) -> Dict[str, Any]:
    data = {
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
        "terminal_local_bypass": cfg.terminal_local_bypass,
        "terminal_max_sessions": cfg.terminal_max_sessions,
        "terminal_max_buffer_chars": cfg.terminal_max_buffer_chars,
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
        "lantern_bot": cfg.lantern_bot.public_policy(),
    }
    if include_secrets:
        data["terminal_password_hash"] = cfg.terminal_password_hash
    return data

def write_config_file(cfg: "AppConfig") -> None:
    cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config_to_dict(cfg, include_secrets=True)
    current = load_simple_yaml(cfg.config_path)
    password_hash = current.get("terminal_password_hash")
    if isinstance(password_hash, str):
        data["terminal_password_hash"] = password_hash
    else:
        data["terminal_password_hash"] = cfg.terminal_password_hash

    bot = cfg.lantern_bot

    def access_yaml(access):
        return {
            "tools": list(access.tools),
            "extensions": bool(access.extensions),
            "mcp": bool(access.mcp),
            "provider_mode": access.provider_mode,
            "providers": list(access.providers),
            "model_mode": access.model_mode,
            "models": list(access.models),
            "bypass_models": list(access.bypass_models),
            "selection": {
                "provider": access.provider or None,
                "model": access.model or None,
                "lock_provider": access.lock_provider,
                "lock_model": access.lock_model,
            },
        }

    data["lantern_bot"] = {
        "enabled": bot.enabled,
        "access": {
            "localhost": access_yaml(bot.local_access),
            "lan": access_yaml(bot.lan_access),
        },
        "policy": {
            "max_prompts_per_day": bot.max_prompts_per_day,
            "max_tokens_per_day": bot.max_tokens_per_day,
        },
        "greeting": bot.greeting,
        "lantern_context": bot.system_prompt,
    }

    rendered = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )
    fd, tmp = tempfile.mkstemp(prefix=".lantern-config-", dir=str(cfg.config_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, cfg.config_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

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
    terminal_password_cli = p.add_mutually_exclusive_group()
    terminal_password_cli.add_argument("--set-terminal-password", action="store_true", help="Set a local Terminal password in YAML without starting the server")
    terminal_password_cli.add_argument("--no-password", action="store_true", help="Disable Terminal password for this server process only; do not change the YAML")
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
        terminal_password_hash=str(data.get("terminal_password_hash") or ""),
        terminal_local_bypass=bool(data.get("terminal_local_bypass", True)),
        terminal_max_sessions=max(1, min(int(data.get("terminal_max_sessions") or 16), 32)),
        terminal_max_buffer_chars=max(10000, min(int(data.get("terminal_max_buffer_chars") or 204800), 5000000)),
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
        lantern_bot=LanternBotConfig.from_mapping(data.get("lantern_bot")),
    )

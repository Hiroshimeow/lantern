import getpass
import hashlib
import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig, APP_NAME, parse_args, build_config, write_config_file
from .filesystem import FileService
from .media import MediaService, HAS_PIL, FFMPEG
from .views import ViewService
from .crop import CropService
from .http.server import LanternHTTPServer, Handler
from .terminal import TerminalManager
from .pi_chat import LanternBotManager
from .pi_sessions import PiSessionRegistry, resolve_native_pi_argv
from .scm import ScmService
from .terminal_auth import TerminalAccess, hash_password, update_password_yaml
from .ws import WebSocketHub
from .live_markdown import LiveMarkdownStore

try:
    import plugin as LAN_PLUGIN
except ImportError:
    LAN_PLUGIN = None


def ensure_cache_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "thumbs").mkdir(parents=True, exist_ok=True)
    (path / "folder_previews").mkdir(parents=True, exist_ok=True)


def _native_pi_context_prompt(config: AppConfig, context: dict[str, Any]) -> str:
    snapshot = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return (
        config.lantern_bot.system_prompt.rstrip()
        + "\n\n"
        + "This native Pi session was created from an immutable Lantern context. "
          "Use the context below as the user's initial workspace reference. "
          "Do not infer a different active Lantern file merely because the browser navigates later. "
          "Edit real project files with Pi's native tools; Lantern's Markdown layer observes file changes independently.\n"
        + "<lantern_native_context>"
        + snapshot
        + "</lantern_native_context>"
    )


@dataclass
class Application:
    config: AppConfig
    ws: WebSocketHub
    terminal_access: TerminalAccess
    terminal: TerminalManager
    bot: LanternBotManager
    pi: PiSessionRegistry
    scm: ScmService
    work: LiveMarkdownStore
    files: FileService
    media: MediaService
    views: ViewService
    crop: CropService
    plugin: Any
    heavy_preview_slots: threading.BoundedSemaphore
    static_dir: Path
    _closed: bool = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.scm.close()
        finally:
            try:
                self.pi.close()
            finally:
                try:
                    self.bot.close()
                finally:
                    self.terminal.kill_all()


def make_application(config: AppConfig, *, no_password: bool = False,
                     plugin = LAN_PLUGIN) -> Application:
    if not config.root.exists():
        raise ValueError(f"Root does not exist: {config.root}")
    ws = WebSocketHub()
    access = TerminalAccess("" if no_password else config.terminal_password_hash,
                            local_bypass=config.terminal_local_bypass)
    terminal = TerminalManager(config.root, ws.broadcast,
                               enabled=config.terminal_enabled,
                               max_live=config.terminal_max_sessions,
                               max_output=config.terminal_max_buffer_chars)
    work_dir = Path(os.environ.get("LANTERN_WORK_DIR") or (Path.home() / ".lantern" / "work"))
    work = LiveMarkdownStore(config.root, work_dir, {".md", ".markdown"})
    bot = LanternBotManager(config.root, ws.broadcast, work_store=work,
                            bot_config=config.lantern_bot)
    configured_pi_state = os.environ.get("LANTERN_PI_SESSION_DIR", "").strip()
    if configured_pi_state:
        pi_state_dir = Path(configured_pi_state).expanduser().resolve()
    else:
        root_identity = os.path.normcase(str(config.root.resolve())).encode("utf-8")
        root_key = hashlib.sha256(root_identity).hexdigest()[:16]
        pi_state_dir = (Path.home() / ".lantern" / "pi-native" / root_key).resolve()
    pi = PiSessionRegistry(
        config.root,
        pi_state_dir,
        terminal,
        resolve_native_pi_argv(),
        env={"LANTERN_PI_NATIVE_HARNESS": "1"},
        context_prompt_factory=lambda context: _native_pi_context_prompt(config, dict(context)),
    )
    scm = ScmService(config.root, ws.broadcast)
    files = FileService(config, plugin)
    media = MediaService(config, files)
    views = ViewService(config, files, media)
    crop = CropService(files)
    return Application(config, ws, access, terminal, bot, pi, scm, work,
                       files, media, views, crop, plugin,
                       threading.BoundedSemaphore(value=2),
                       (Path(__file__).resolve().parents[1] / "static").resolve())


def main():
    args = parse_args()
    if args.set_terminal_password:
        password = getpass.getpass("New remote Terminal password (blank = no password): ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")
        update_password_yaml(Path(args.config), hash_password(password) if password else "")
        print(("Terminal password updated" if password else "Terminal password disabled")
              + " in YAML. Restart Lantern to apply.")
        return
    config_path = Path(args.config).expanduser().resolve()
    config_existed = config_path.exists()
    config = build_config(args)
    if not config.root.exists():
        print(f"Root does not exist: {config.root}", file=sys.stderr)
        raise SystemExit(2)
    ensure_cache_dir(config.cache_dir)
    cli_overrides = any(getattr(args, name) is not None for name in
        ("root", "port", "host", "title", "cache_dir", "show_hidden", "show_system",
         "sort", "view", "page_limit"))
    if args.save_config or (not config_existed and not cli_overrides):
        try:
            write_config_file(config)
        except Exception as exc:
            print(f"Warning: cannot write config {config.config_path}: {exc}", file=sys.stderr)
    app = make_application(config, no_password=args.no_password)
    print(f"\n{APP_NAME}")
    print(f"Root      : {config.root}")
    print(f"Config    : {config.config_path}")
    print(f"Sort/View : {config.default_sort} / {config.default_view} / {config.page_limit} per page")
    print(f"Cache     : {config.cache_dir}")
    print(f"Pillow    : {'yes' if HAS_PIL else 'no'}")
    print(f"ffmpeg    : {'yes' if FFMPEG else 'no'}")
    print(f"Local     : http://127.0.0.1:{config.port}")
    print(f"LAN       : http://{app.files.get_local_ip_guess()}:{config.port}")
    print("Stop      : Ctrl+C\n")
    try:
        with LanternHTTPServer((config.host,config.port), Handler, app) as server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\nStopping...")
                server.shutdown()
    finally:
        app.close()

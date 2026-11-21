"""Lantern HTML shell and breadcrumb helpers (v9.25 modular static assets)."""
from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .filesystem import FileService
from .media import MediaService


def breadcrumb(rel_path: str, files: FileService) -> str:
    rel_path = rel_path.strip("/")
    parts = [] if not rel_path else rel_path.split("/")
    out = []
    if parts:
        parent_rel = "/".join(parts[:-1])
        parent_href = "/" if not parent_rel else f"/{files.quote_path(parent_rel)}/"
        out.append(
            f'<a class="crumb-back" data-action="back" data-rel="{files.html_escape(parent_rel)}" '
            f'href="{parent_href}" onclick="return goParentFolder(event, \'{parent_href}\')">↩ Back</a>'
        )
    out.append('<a data-rel="" href="/" onclick="return navigateCrumb(event, \'\')">Root</a>')
    acc = []
    for p in parts:
        acc.append(p)
        cur = "/".join(acc)
        href = f"/{files.quote_path(cur)}/"
        out.append(
            f'<span class="crumb-sep">/</span>'
            f'<a data-rel="{files.html_escape(cur)}" href="{href}" '
            f'onclick="return navigateCrumb(event, {files.json_dumps(cur)})">{files.html_escape(p)}</a>'
        )
    return "".join(out)


def page_shell(title: str, body: str, current_path: str, *, config: AppConfig, files: FileService) -> bytes:
    static_root = (Path(__file__).resolve().parents[1] / "static").resolve()

    def asset_url(rel: str) -> str:
        path = (static_root / rel).resolve()
        try:
            path.relative_to(static_root)
            version = files.file_etag(path, path.stat())
        except (OSError, ValueError):
            return f"/static/{rel}"
        return f"/static/{rel}?v={version}"

    gallery_css = asset_url("gallery.css")
    xterm_css = asset_url("vendor/xterm.css")
    terminal_css = asset_url("terminal_scm.css")
    chat_css = asset_url("chatbot.css")

    gallery_tree_js = asset_url("gallery_tree.js")
    gallery_upload_js = asset_url("gallery_upload.js")
    gallery_media_js = asset_url("gallery_media.js")
    gallery_app_js = asset_url("gallery_app.js")
    xterm_js = asset_url("vendor/xterm.js")
    fit_js = asset_url("vendor/addon-fit.js")
    terminal_js = asset_url("terminal_scm.js")
    chat_js = asset_url("chatbot.js")

    app = {
        "currentPath": current_path.strip("/"),
        "title": config.title,
        "rootName": config.root.name or str(config.root),
        "plugin": {"enabled": files.plugin_enabled()},
        "defaults": {
            "default_sort": config.default_sort,
            "default_view": config.default_view,
            "page_limit": config.page_limit,
            "folders_first": config.folders_first,
            "search_debounce_ms": config.search_debounce_ms,
            "terminal_enabled": config.terminal_enabled,
            "terminal_max_buffer_chars": config.terminal_max_buffer_chars,
            "terminal_start_height_px": config.terminal_start_height_px,
            "terminal_mobile_extra_keys": config.terminal_mobile_extra_keys,
            "thumb_fit": config.thumb_fit,
            "folder_preview_enabled": config.folder_preview_enabled,
            "folder_preview_mode": config.folder_preview_mode,
            "folder_preview_fit": config.folder_preview_fit,
            "folder_preview_rotate": config.folder_preview_rotate,
            "folder_preview_animation": config.folder_preview_animation,
            "folder_preview_interval_ms": config.folder_preview_interval_ms,
            "folder_preview_scan_limit": config.folder_preview_scan_limit,
            "folder_preview_max_items": config.folder_preview_max_items,
            "folder_preview_include_video": config.folder_preview_include_video,
            "upload_auto_start": config.upload_auto_start,
            "upload_parallel": config.upload_parallel,
            "upload_conflict": config.upload_conflict,
        },
    }
    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>{files.html_escape(title)}</title>
<link rel="stylesheet" href="{gallery_css}">
<link rel="stylesheet" href="{xterm_css}">
<link rel="stylesheet" href="{terminal_css}">
<link rel="stylesheet" href="{chat_css}">
</head>
<body>
{body}
<script>window.APP={files.json_dumps(app)};</script>
<script src="{gallery_tree_js}"></script>
<script src="{gallery_upload_js}"></script>
<script src="{gallery_media_js}"></script>
<script src="{gallery_app_js}"></script>
<script src="{xterm_js}"></script>
<script src="{fit_js}"></script>
<script src="{terminal_js}"></script>
<script src="{chat_js}"></script>
</body>
</html>"""
    return html_doc.encode("utf-8", "surrogateescape")


class ViewService:
    def __init__(self, config: AppConfig, files: FileService, media: MediaService):
        self.cfg = config
        self.files = files
        self.media = media

    def breadcrumb(self, rel_path: str) -> str:
        return breadcrumb(rel_path, self.files)

    def page_shell(self, title: str, body: str, current_path: str = "/") -> bytes:
        return page_shell(title, body, current_path, config=self.cfg, files=self.files)

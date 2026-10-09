"""Bounded, optimistic-concurrency Markdown document persistence for Lantern.

The public HTTP handlers authorize paths inside the configured root; this module
performs the byte-preserving read / compare / atomic replacement. No collaboration
protocol, server-side HTML interpretation, or network fetches are involved.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any

MAX_MARKDOWN_EDITOR_BYTES = 5 * 1024 * 1024
_MARKDOWN_SUFFIXES = frozenset((".md", ".markdown"))
_SAVE_LOCK = threading.RLock()


class MarkdownEditorError(Exception):
    def __init__(self, status: int, message: str, **details: Any):
        super().__init__(message)
        self.status = status
        self.details = details


def require_markdown(path: Path) -> None:
    if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
        raise MarkdownEditorError(400, "Only .md and .markdown files are supported")
    if not path.is_file():
        raise MarkdownEditorError(404, "Markdown file not found")


def _read_bytes(path: Path) -> bytes:
    require_markdown(path)
    with path.open("rb") as stream:
        content = stream.read(MAX_MARKDOWN_EDITOR_BYTES + 1)
    if len(content) > MAX_MARKDOWN_EDITOR_BYTES:
        raise MarkdownEditorError(413, "Markdown exceeds the 5 MiB visual editor limit; original file is untouched")
    return content


def _newline_mode(raw: bytes) -> str:
    if b"\r\n" in raw:
        remaining = raw.replace(b"\r\n", b"")
        return "mixed" if b"\n" in remaining or b"\r" in remaining else "crlf"
    return "lf" if b"\n" in raw else "none"


def _snapshot_from_bytes(raw: bytes) -> dict[str, Any]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        content = raw.decode("utf-8-sig" if bom else "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MarkdownEditorError(415, "Only lossless UTF-8 Markdown can be edited visually") from exc
    if "\x00" in content:
        raise MarkdownEditorError(415, "Binary/NUL Markdown is not editable")
    return {
        "content": content,
        "version": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "bom": bom,
        "newline": _newline_mode(raw),
    }


def read_document(path: Path) -> dict[str, Any]:
    return _snapshot_from_bytes(_read_bytes(path))


def save_document(path: Path, content: str, expected_version: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise MarkdownEditorError(400, "Markdown content must be a string")
    if not isinstance(expected_version, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_version):
        raise MarkdownEditorError(428, "The exact document version is required to save")
    if "\x00" in content:
        raise MarkdownEditorError(400, "NUL characters are not valid Markdown content")
    try:
        new_utf8 = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise MarkdownEditorError(400, "Markdown contains invalid Unicode") from exc
    if len(new_utf8) > MAX_MARKDOWN_EDITOR_BYTES:
        raise MarkdownEditorError(413, "Markdown exceeds the 5 MiB save limit")

    with _SAVE_LOCK:
        original = _read_bytes(path)
        before = _snapshot_from_bytes(original)
        if before["version"] != expected_version:
            raise MarkdownEditorError(409, "File changed on disk or another LAN client", current_version=before["version"])

        # ProseMirror produces LF. Keep existing CRLF and UTF-8 BOM where possible.
        if before["newline"] == "crlf":
            new_utf8 = new_utf8.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if before["bom"]:
            new_utf8 = b"\xef\xbb\xbf" + new_utf8
        if len(new_utf8) > MAX_MARKDOWN_EDITOR_BYTES:
            raise MarkdownEditorError(413, "Encoded Markdown exceeds the 5 MiB save limit")
        if new_utf8 == original:
            return {k: v for k, v in before.items() if k != "content"}

        # Never truncate the target. A crash before replacement retains the
        # previous complete file; on successful replacement readers see complete bytes.
        mode = stat.S_IMODE(path.stat().st_mode)
        fd, tmpname = tempfile.mkstemp(prefix=".lantern-md-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(new_utf8)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(tmpname, mode)
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
        return {k: v for k, v in _snapshot_from_bytes(new_utf8).items() if k != "content"}

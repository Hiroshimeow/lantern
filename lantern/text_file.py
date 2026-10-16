"""Generic bounded UTF-8 text snapshot and atomic CAS persistence for Lantern."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any

MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
_SAVE_LOCK = threading.RLock()


class TextFileError(Exception):
    def __init__(self, status: int, message: str, **details: Any):
        super().__init__(message)
        self.status = status
        self.details = details


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise TextFileError(404, "Text file not found")


def _read_bytes(path: Path, max_bytes: int) -> bytes:
    _require_file(path)
    with path.open("rb") as stream:
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise TextFileError(413, f"Text file exceeds the {max_bytes} byte edit limit")
    return content


def _newline_mode(raw: bytes) -> str:
    if b"\r\n" in raw:
        remaining = raw.replace(b"\r\n", b"")
        return "mixed" if b"\n" in remaining or b"\r" in remaining else "crlf"
    return "lf" if b"\n" in raw else "none"


def snapshot_from_bytes(raw: bytes) -> dict[str, Any]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        content = raw.decode("utf-8-sig" if bom else "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TextFileError(415, "Only lossless UTF-8 text files can be edited") from exc
    if "\x00" in content:
        raise TextFileError(415, "Binary/NUL files are not editable as text")
    return {
        "content": content,
        "version": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "bom": bom,
        "newline": _newline_mode(raw),
    }


def read_text_snapshot(path: Path, max_bytes: int = MAX_TEXT_FILE_BYTES) -> dict[str, Any]:
    return snapshot_from_bytes(_read_bytes(path, max_bytes))


def _encode_for_existing_file(content: str, before: dict[str, Any], max_bytes: int) -> bytes:
    if not isinstance(content, str):
        raise TextFileError(400, "Text content must be a string")
    if "\x00" in content:
        raise TextFileError(400, "NUL characters are not valid text content")
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise TextFileError(400, "Text contains invalid Unicode") from exc
    if len(encoded) > max_bytes:
        raise TextFileError(413, f"Text content exceeds the {max_bytes} byte save limit")

    if before["newline"] == "crlf":
        encoded = encoded.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if before["bom"]:
        encoded = b"\xef\xbb\xbf" + encoded
    if len(encoded) > max_bytes:
        raise TextFileError(413, f"Encoded text exceeds the {max_bytes} byte save limit")
    return encoded


def save_text_cas(
    path: Path,
    content: str,
    expected_version: str,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> dict[str, Any]:
    if not isinstance(expected_version, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_version):
        raise TextFileError(428, "The exact document version is required to save")

    with _SAVE_LOCK:
        original = _read_bytes(path, max_bytes)
        before = snapshot_from_bytes(original)
        if before["version"] != expected_version:
            raise TextFileError(
                409,
                "File changed on disk or another LAN client",
                current_version=before["version"],
            )

        encoded = _encode_for_existing_file(content, before, max_bytes)
        if encoded == original:
            return {k: v for k, v in before.items() if k != "content"}

        mode = stat.S_IMODE(path.stat().st_mode)
        fd, tmpname = tempfile.mkstemp(prefix=".lantern-text-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(tmpname, mode)
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)

        return {k: v for k, v in snapshot_from_bytes(encoded).items() if k != "content"}

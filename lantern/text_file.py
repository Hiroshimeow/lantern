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


def _line_records(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    start = 0
    for match in re.finditer(r"\r\n|\r|\n", content):
        records.append({
            "start": start,
            "end": match.start(),
            "separator": match.group(0),
        })
        start = match.end()
    records.append({"start": start, "end": len(content), "separator": ""})
    return records


def _utf16_column_to_py_index(text: str, column: int) -> int:
    if not isinstance(column, int) or isinstance(column, bool) or column < 0:
        raise TextFileError(400, "Patch UTF-16 column must be a non-negative integer")
    units = 0
    for index, char in enumerate(text):
        if column == units:
            return index
        width = 2 if ord(char) > 0xFFFF else 1
        if column < units + width:
            raise TextFileError(400, "Patch range splits a UTF-16 surrogate pair")
        units += width
    if column == units:
        return len(text)
    raise TextFileError(400, "Patch UTF-16 column exceeds source line")


def _patch_point(
    content: str,
    lines: list[dict[str, Any]],
    point: Any,
) -> tuple[int, int]:
    if not isinstance(point, dict):
        raise TextFileError(400, "Patch point must contain line and column")
    line = point.get("line")
    column = point.get("column")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1 or line > len(lines):
        raise TextFileError(400, "Patch line is outside the source document")
    record = lines[line - 1]
    line_text = content[record["start"]:record["end"]]
    local = _utf16_column_to_py_index(line_text, column)
    return record["start"] + local, line - 1


def _local_newline(before: dict[str, Any], lines: list[dict[str, Any]], line_index: int) -> str:
    if before["newline"] == "crlf":
        return "\r\n"
    if before["newline"] == "lf":
        return "\n"
    separator = lines[line_index]["separator"] if 0 <= line_index < len(lines) else ""
    if separator:
        return separator
    for index in range(min(line_index - 1, len(lines) - 1), -1, -1):
        if lines[index]["separator"]:
            return lines[index]["separator"]
    for index in range(max(0, line_index + 1), len(lines)):
        if lines[index]["separator"]:
            return lines[index]["separator"]
    return "\n"


def patch_text_cas(
    path: Path,
    patches: list[dict[str, Any]],
    expected_version: str,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> dict[str, Any]:
    if not isinstance(expected_version, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_version):
        raise TextFileError(428, "The exact document version is required to patch")
    if not isinstance(patches, list) or not patches:
        raise TextFileError(400, "At least one Source patch is required")
    if len(patches) > 512:
        raise TextFileError(400, "Too many Source patches in one batch")

    with _SAVE_LOCK:
        original = _read_bytes(path, max_bytes)
        before = snapshot_from_bytes(original)
        if before["version"] != expected_version:
            raise TextFileError(
                409,
                "File changed on disk or another LAN client",
                current_version=before["version"],
            )

        content = before["content"]
        lines = _line_records(content)
        bom_bytes = 3 if before["bom"] else 0
        prepared: list[dict[str, Any]] = []

        for patch in patches:
            if not isinstance(patch, dict):
                raise TextFileError(400, "Source patch must be an object")
            insert = patch.get("insert")
            expected = patch.get("expected")
            if not isinstance(insert, str) or not isinstance(expected, str):
                raise TextFileError(400, "Source patch insert/expected must be strings")
            if "\r" in insert:
                raise TextFileError(400, "Source patch insert text must use normalized LF")

            start_py, start_line = _patch_point(content, lines, patch.get("from"))
            end_py, _end_line = _patch_point(content, lines, patch.get("to"))
            if end_py < start_py:
                raise TextFileError(400, "Source patch range is reversed")

            selected = content[start_py:end_py].replace("\r\n", "\n").replace("\r", "\n")
            if selected != expected:
                raise TextFileError(409, "Source patch no longer matches current text",
                                    current_version=before["version"])

            raw_start = bom_bytes + len(content[:start_py].encode("utf-8"))
            raw_end = bom_bytes + len(content[:end_py].encode("utf-8"))
            separator = _local_newline(before, lines, start_line)
            inserted_raw = insert.replace("\n", separator).encode("utf-8")
            prepared.append({
                "start": raw_start,
                "end": raw_end,
                "insert": inserted_raw,
            })

        ordered = sorted(prepared, key=lambda item: (item["start"], item["end"]))
        previous_end = -1
        previous_start = -1
        for item in ordered:
            if item["start"] < previous_end or (
                item["start"] == previous_start
                and item["start"] == item["end"] == previous_end
            ):
                raise TextFileError(400, "Source patch ranges overlap")
            previous_start = item["start"]
            previous_end = item["end"]

        encoded = original
        for item in reversed(ordered):
            encoded = encoded[:item["start"]] + item["insert"] + encoded[item["end"]:]

        if len(encoded) > max_bytes:
            raise TextFileError(413, f"Patched text exceeds the {max_bytes} byte save limit")
        snapshot_from_bytes(encoded)
        if encoded == original:
            return {k: v for k, v in before.items() if k != "content"}

        mode = stat.S_IMODE(path.stat().st_mode)
        fd, tmpname = tempfile.mkstemp(prefix=".lantern-text-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(encoded)
                output.flush()
                try:
                    os.fsync(output.fileno())
                except OSError:
                    pass
            os.chmod(tmpname, mode)
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)

        return {k: v for k, v in snapshot_from_bytes(encoded).items() if k != "content"}


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
                try:
                    os.fsync(output.fileno())
                except OSError:
                    pass
            os.chmod(tmpname, mode)
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)

        return {k: v for k, v in snapshot_from_bytes(encoded).items() if k != "content"}

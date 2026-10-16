"""Live Markdown editing: project .md is authoritative, md_temp is an accepted snapshot.

A write from the browser updates the real .md with compare-and-swap. Pi edits
that same real path through its native edit tool; VS Code changes are observed
by reading the real file. Ctrl+S accepts the current bytes into md_temp only.

Legacy unsaved staged edits are never silently discarded or promoted.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .text_file import (
    MAX_TEXT_FILE_BYTES, TextFileError, read_text_snapshot,
    save_text_cas, snapshot_from_bytes,
)
from .working_copy import WorkingCopyError


class LiveMarkdownStore:
    live = True

    def __init__(self, root: Path, work_dir: Path, suffixes: Iterable[str],
                 *, max_bytes: int = MAX_TEXT_FILE_BYTES):
        self.root = Path(root).resolve()
        self.legacy_dir = Path(work_dir).expanduser().resolve()
        self.temp_dir = self.legacy_dir / "md_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self.suffixes = frozenset(s.lower() for s in suffixes)
        self.lock = threading.RLock()
        self.turns: dict[str, str] = {}
        # Fail closed before a trusted prompt provides its origin-derived scope.
        self.active_scope = "lan"
        self.active_tools: tuple[str, ...] = ("read", "grep", "find", "ls")
        self.guard_path = self.temp_dir / ("live-guard-" +
            hashlib.sha256(os.path.normcase(str(self.root)).encode()).hexdigest()[:12] + ".json")
        self._write_guard()

    def _resolve(self, rel: str) -> tuple[str, Path, str, Path]:
        if not isinstance(rel, str) or not rel.strip():
            raise WorkingCopyError(400, "Markdown path is required")
        candidate = (self.root / rel.strip().replace("\\", "/").lstrip("/")).resolve()
        try:
            logical = candidate.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise WorkingCopyError(403, "Markdown path escapes project root") from exc
        if candidate.suffix.lower() not in self.suffixes:
            raise WorkingCopyError(415, "Only Markdown files can use live diff")
        key = os.path.normcase(str(self.root)) + "\0" + os.path.normcase(logical)
        identifier = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return logical, candidate, identifier, self.temp_dir / identifier / candidate.name

    def _read_real(self, real: Path) -> dict[str, Any]:
        try:
            return read_text_snapshot(real, self.max_bytes)
        except TextFileError as exc:
            raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc

    @staticmethod
    def _atomic_copy_bytes(dst: Path, data: bytes) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".lantern-md-temp-", suffix=".tmp", dir=dst.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _baseline(self, real: Path, identifier: str, temp: Path) -> dict[str, Any]:
        if not temp.is_file():
            # A legacy draft may contain text the user never accepted. Fail
            # closed, and leave that old private file available for recovery.
            legacy = self.legacy_dir / identifier / real.name
            if legacy.is_file() and (legacy.parent / "meta.json").is_file():
                try:
                    if legacy.read_bytes() != real.read_bytes():
                        raise WorkingCopyError(
                            409, "Older Lantern draft exists. Export or accept it in "
                            "the previous version before switching to live editing.",
                            reason="legacy_pending", legacyPath=str(legacy))
                except OSError as exc:
                    raise WorkingCopyError(409, "Cannot inspect legacy draft",
                                           reason="legacy_pending") from exc
            raw = real.read_bytes()
            if len(raw) > self.max_bytes:
                raise WorkingCopyError(413, "Markdown exceeds live edit size limit")
            snapshot_from_bytes(raw)  # lossless UTF-8 validation
            self._atomic_copy_bytes(temp, raw)
        return self._read_real(temp)

    def get(self, rel: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            current = self._read_real(real)
            baseline = self._baseline(real, identifier, temp)
            changed = current["version"] != baseline["version"]
            return {
                "path": logical, "live": True,
                "realPath": str(real), "tempPath": str(temp),
                "currentVersion": current["version"],
                "turnActive": identifier in self.turns,
                "state": "pending" if changed else "clean",
                "saved": baseline,
                "work": ({
                    "content": current["content"], "hash": current["version"],
                    "baseVersion": baseline["version"],
                    "updatedAt": real.stat().st_mtime,
                } if changed else None),
            }

    def write(self, rel: str, content: str, *, expect_hash: str | None,
              base_version: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp)
            if baseline["version"] != base_version:
                raise WorkingCopyError(409, "Accepted Markdown baseline changed",
                                       reason="baseline_changed",
                                       currentVersion=baseline["version"])
            before = self._read_real(real)
            expected = expect_hash or base_version
            if before["version"] != expected:
                raise WorkingCopyError(409, "Project file changed in another editor",
                                       reason="stale",
                                       currentHash=(before["version"] if
                                                    before["version"] != base_version else None),
                                       currentVersion=before["version"])
            try:
                result = save_text_cas(real, content, expected, self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), reason="stale",
                                       **exc.details) from exc
            changed = result["version"] != baseline["version"]
            return {"state": "pending" if changed else "clean",
                    "hash": result["version"] if changed else None,
                    "currentVersion": result["version"], "updatedAt": time.time()}

    def save(self, rel: str, *, expect_hash: str | None,
             expect_saved_version: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp)
            if baseline["version"] != expect_saved_version:
                raise WorkingCopyError(409, "Baseline changed in another browser",
                                       reason="baseline_changed",
                                       currentVersion=baseline["version"])
            current = self._read_real(real)
            expected = expect_hash or baseline["version"]
            if current["version"] != expected:
                raise WorkingCopyError(409, "Project file changed before Accept",
                                       reason="stale", currentVersion=current["version"])
            # Preserve real bytes (BOM/newline/mixed line endings). This must
            # never write to the project .md, even if it was edited by VS Code.
            raw = real.read_bytes()
            if hashlib.sha256(raw).hexdigest() != current["version"]:
                raise WorkingCopyError(409, "Project file changed during snapshot",
                                       reason="stale")
            self._atomic_copy_bytes(temp, raw)
            return {"state": "clean", "version": current["version"],
                    "bytes": len(raw), "tempPath": str(temp)}

    def accept_partial(self, rel: str, content: str, *,
                       expect_saved_version: str,
                       expect_current_version: str) -> dict[str, Any]:
        """Accept only selected diff hunks into md_temp; never write real .md."""
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp)
            current = self._read_real(real)
            if baseline["version"] != expect_saved_version or (
                current["version"] != expect_current_version
            ):
                raise WorkingCopyError(409, "Project file/baseline changed before accepting hunk",
                                       reason="stale")
            try:
                result = save_text_cas(temp, content, expect_saved_version, self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
            return {"state": "clean" if current["version"] == result["version"]
                    else "pending", "version": result["version"],
                    "currentVersion": current["version"]}

    def discard(self, rel: str, *, expect_hash: str | None) -> dict[str, Any]:
        """Explicit Restore All: revert real .md to the accepted snapshot via CAS."""
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp)
            current = self._read_real(real)
            if current["version"] != (expect_hash or baseline["version"]):
                raise WorkingCopyError(409, "Cannot undo newer external file changes",
                                       reason="stale", currentVersion=current["version"])
            try:
                result = save_text_cas(real, baseline["content"],
                                       current["version"], self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
            return {"ok": True, "path": logical, "state": "clean",
                    "version": result["version"]}

    def begin_turn(self, rel: str, expect_hash: str | None) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            if identifier in self.turns:
                raise WorkingCopyError(409, "LanternBot is already editing this file",
                                       reason="pi_turn")
            baseline = self._baseline(real, identifier, temp)
            current = self._read_real(real)
            if current["version"] != (expect_hash or baseline["version"]):
                raise WorkingCopyError(409, "Project file changed before bot turn",
                                       reason="stale", currentVersion=current["version"])
            self.turns[identifier] = current["version"]
            self._write_guard()
            return {"path": logical, "workingPath": str(real),
                    "hash": current["version"] if
                            current["version"] != baseline["version"] else None,
                    "startRealHash": current["version"]}

    def peek_hash(self, rel: str) -> str | None:
        _logical, real, _id, _temp = self._resolve(rel)
        return self._read_real(real)["version"]

    def end_turn(self, rel: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            before = self.turns.pop(identifier, "")
            after = self._read_real(real)["version"]
            self._write_guard()
            return {"path": logical, "hash": after,
                    "realTouched": bool(before and after != before)}

    def working_path(self, rel: str) -> Path | None:
        _logical, real, _id, _temp = self._resolve(rel)
        return real

    def set_runtime_scope(self, scope: str, tools: Iterable[str]) -> None:
        with self.lock:
            if scope not in ("local", "lan"):
                raise WorkingCopyError(403, "Invalid LanternBot access scope")
            accepted = tuple(str(t).strip() for t in tools if str(t).strip())
            if not accepted:
                raise WorkingCopyError(403, "Empty LanternBot tool allowlist")
            self.active_scope = scope
            self.active_tools = accepted
            self._write_guard()

    def _write_guard(self) -> None:
        # Ordinary project files stay writable via native Pi tools.
        # Lantern's private snapshot/metadata always remain protected.
        payload = {
            "staged": [], "turnWritable": [],
            "protectedDir": os.path.normcase(str(self.legacy_dir)),
            "liveWritable": [],
            "activeScope": self.active_scope,
            "allowedTools": list(self.active_tools),
        }
        self._atomic_copy_bytes(
            self.guard_path,
            (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"),
        )

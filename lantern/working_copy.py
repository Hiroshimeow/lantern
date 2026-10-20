"""Persistent unsaved working copies for Lantern text files.

The real project file remains the saved baseline. Browser/Pi edits live in a
private working file until an explicit Save performs a content-version CAS.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .text_file import MAX_TEXT_FILE_BYTES, TextFileError, read_text_snapshot, save_text_cas


class WorkingCopyError(Exception):
    def __init__(self, status: int, message: str, *, reason: str | None = None, **details: Any):
        super().__init__(message)
        self.status = status
        self.details = dict(details)
        if reason:
            self.details["reason"] = reason


@dataclass
class _TurnState:
    active: bool = False
    start_real_hash: str = ""


class WorkingCopyStore:
    def __init__(
        self,
        root: Path,
        work_dir: Path,
        allowed_suffixes: Iterable[str],
        *,
        max_bytes: int = MAX_TEXT_FILE_BYTES,
    ) -> None:
        self.root = Path(root).resolve()
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.allowed_suffixes = frozenset(str(x).lower() for x in allowed_suffixes)
        self.max_bytes = int(max_bytes)
        root_guard_id = hashlib.sha256(os.path.normcase(str(self.root)).encode("utf-8")).hexdigest()[:12]
        self.guard_path = self.work_dir / f"guard-{root_guard_id}.json"
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        self._turns: dict[str, _TurnState] = {}
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._write_guard_state()

    def _lock_for(self, doc_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(doc_id, threading.RLock())

    def _resolve(self, rel: str) -> tuple[str, Path, str]:
        if not isinstance(rel, str) or not rel.strip():
            raise WorkingCopyError(400, "Working-copy path is required")
        cleaned = rel.strip().replace("\\", "/").lstrip("/")
        candidate = (self.root / Path(cleaned.replace("/", os.sep))).resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkingCopyError(403, "Working-copy path escapes the configured root") from exc
        if candidate.suffix.lower() not in self.allowed_suffixes:
            raise WorkingCopyError(415, "This file type is not enabled for working copies")
        logical = relative.as_posix()
        key = os.path.normcase(str(self.root)) + "\0" + os.path.normcase(logical)
        doc_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return logical, candidate, doc_id

    def _paths(self, rel: str) -> tuple[str, Path, str, Path, Path]:
        logical, real, doc_id = self._resolve(rel)
        directory = self.work_dir / doc_id
        working = directory / real.name
        meta = directory / "meta.json"
        return logical, real, doc_id, working, meta

    @staticmethod
    def _normalized_text(text: str) -> str:
        return str(text).replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _hash_bytes(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _working_snapshot(self, working: Path) -> dict[str, Any]:
        try:
            raw = working.read_bytes()
        except FileNotFoundError as exc:
            raise WorkingCopyError(409, "Working copy is missing", reason="missing_work") from exc
        if len(raw) > self.max_bytes:
            raise WorkingCopyError(413, "Working copy exceeds the text edit limit")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkingCopyError(415, "Working copy is not lossless UTF-8 text") from exc
        if "\x00" in text:
            raise WorkingCopyError(415, "Working copy contains NUL data")
        return {"content": text, "hash": self._hash_bytes(raw), "bytes": len(raw)}

    def _read_meta(self, meta: Path) -> dict[str, Any]:
        try:
            value = json.loads(meta.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            raise WorkingCopyError(409, "Working-copy metadata is missing or corrupt", reason="meta") from exc
        if not isinstance(value, dict) or value.get("v") != 1:
            raise WorkingCopyError(409, "Unsupported working-copy metadata", reason="meta")
        return value

    @staticmethod
    def _atomic_replace_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(prefix=".lantern-work-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                try:
                    os.fsync(output.fileno())
                except OSError:
                    pass
            last: OSError | None = None
            for attempt in range(4):
                try:
                    os.replace(tmpname, path)
                    tmpname = ""
                    return
                except PermissionError as exc:
                    last = exc
                    if attempt == 3:
                        break
                    time.sleep(0.05)
            raise WorkingCopyError(503, "Working copy is busy; retry", reason="busy") from last
        finally:
            if tmpname and os.path.exists(tmpname):
                os.unlink(tmpname)

    def _write_meta(self, meta: Path, value: dict[str, Any]) -> None:
        payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._atomic_replace_bytes(meta, payload)

    def _delete_dir(self, directory: Path) -> None:
        if directory.exists():
            shutil.rmtree(directory)

    def _turn_state(self, doc_id: str) -> _TurnState:
        return self._turns.setdefault(doc_id, _TurnState())

    def _ensure_not_turn(self, doc_id: str) -> None:
        if self._turn_state(doc_id).active:
            raise WorkingCopyError(409, "Pi is editing this working copy", reason="pi_turn")

    def _meta_payload(
        self,
        *,
        doc_id: str,
        logical: str,
        real: Path,
        working: Path,
        base: dict[str, Any],
        work_hash: str,
    ) -> dict[str, Any]:
        return {
            "v": 1,
            "id": doc_id,
            "root": str(self.root),
            "logicalPath": logical,
            "realPath": str(real),
            "workingPath": str(working),
            "baseVersion": base["version"],
            "workHash": work_hash,
            "encoding": {"bom": bool(base["bom"]), "newline": str(base["newline"])},
            "kind": "markdown" if real.suffix.lower() in {".md", ".markdown"} else "text",
            "updatedAt": time.time(),
        }

    def _create_from_text(
        self,
        rel: str,
        text: str,
        *,
        base_version: str,
    ) -> dict[str, Any]:
        logical, real, doc_id, working, meta_path = self._paths(rel)
        base = read_text_snapshot(real, self.max_bytes)
        if base["version"] != base_version:
            raise WorkingCopyError(
                409,
                "Saved file changed before working copy creation",
                reason="base_changed",
                currentVersion=base["version"],
            )
        normalized = self._normalized_text(text)
        if normalized == self._normalized_text(base["content"]):
            self._delete_dir(working.parent)
            self._write_guard_state()
            return {"hash": None, "updatedAt": time.time(), "state": "clean"}

        raw = normalized.encode("utf-8")
        if len(raw) > self.max_bytes:
            raise WorkingCopyError(413, "Working copy exceeds the text edit limit")
        self._atomic_replace_bytes(working, raw)
        work_hash = self._hash_bytes(raw)
        meta = self._meta_payload(
            doc_id=doc_id,
            logical=logical,
            real=real,
            working=working,
            base=base,
            work_hash=work_hash,
        )
        self._write_meta(meta_path, meta)
        self._write_guard_state()
        return {"hash": work_hash, "updatedAt": meta["updatedAt"], "state": "pending"}

    def get(self, rel: str) -> dict[str, Any]:
        logical, real, doc_id, working, meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            try:
                saved = read_text_snapshot(real, self.max_bytes)
            except TextFileError as exc:
                if exc.status != 404 or not working.exists():
                    raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
                meta = self._read_meta(meta_path)
                work = self._working_snapshot(working)
                return {
                    "path": logical,
                    "state": "missing",
                    "turnActive": self._turn_state(doc_id).active,
                    "saved": None,
                    "work": {
                        "content": work["content"],
                        "hash": work["hash"],
                        "baseVersion": meta["baseVersion"],
                        "updatedAt": meta.get("updatedAt"),
                    },
                }

            saved_public = {
                "content": saved["content"],
                "version": saved["version"],
                "bytes": saved["bytes"],
                "bom": saved["bom"],
                "newline": saved["newline"],
            }
            if not working.exists():
                return {
                    "path": logical,
                    "state": "clean",
                    "turnActive": self._turn_state(doc_id).active,
                    "saved": saved_public,
                    "work": None,
                }

            meta = self._read_meta(meta_path)
            work = self._working_snapshot(working)
            turn_active = self._turn_state(doc_id).active
            if (not turn_active
                    and self._normalized_text(work["content"]) == self._normalized_text(saved["content"])):
                self._delete_dir(working.parent)
                self._write_guard_state()
                return {
                    "path": logical,
                    "state": "clean",
                    "turnActive": False,
                    "saved": saved_public,
                    "work": None,
                }

            state = "pending" if meta.get("baseVersion") == saved["version"] else "external"
            return {
                "path": logical,
                "state": state,
                "turnActive": self._turn_state(doc_id).active,
                "saved": saved_public,
                "work": {
                    "content": work["content"],
                    "hash": work["hash"],
                    "baseVersion": meta.get("baseVersion"),
                    "updatedAt": meta.get("updatedAt"),
                },
            }

    def write(
        self,
        rel: str,
        content: str,
        *,
        expect_hash: str | None,
        base_version: str,
    ) -> dict[str, Any]:
        if not isinstance(content, str):
            raise WorkingCopyError(400, "Working-copy content must be text")
        if not isinstance(base_version, str) or len(base_version) != 64:
            raise WorkingCopyError(428, "The saved base version is required")
        logical, real, doc_id, working, meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            self._ensure_not_turn(doc_id)
            if not working.exists():
                if expect_hash not in (None, ""):
                    raise WorkingCopyError(409, "Working copy does not exist", reason="stale", currentHash=None)
                return self._create_from_text(logical, content, base_version=base_version)

            current = self._working_snapshot(working)
            if not isinstance(expect_hash, str) or expect_hash != current["hash"]:
                raise WorkingCopyError(
                    409,
                    "Working copy changed since the browser last acknowledged it",
                    reason="stale",
                    currentHash=current["hash"],
                )
            meta = self._read_meta(meta_path)
            try:
                saved = read_text_snapshot(real, self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc

            normalized = self._normalized_text(content)
            if normalized == self._normalized_text(saved["content"]):
                self._delete_dir(working.parent)
                self._write_guard_state()
                return {"hash": None, "updatedAt": time.time(), "state": "clean"}

            raw = normalized.encode("utf-8")
            if len(raw) > self.max_bytes:
                raise WorkingCopyError(413, "Working copy exceeds the text edit limit")
            self._atomic_replace_bytes(working, raw)
            work_hash = self._hash_bytes(raw)
            meta["workHash"] = work_hash
            meta["updatedAt"] = time.time()
            self._write_meta(meta_path, meta)
            return {"hash": work_hash, "updatedAt": meta["updatedAt"], "state": "pending"}

    def save(
        self,
        rel: str,
        *,
        expect_hash: str,
        expect_saved_version: str,
    ) -> dict[str, Any]:
        logical, real, doc_id, working, meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            self._ensure_not_turn(doc_id)
            if not working.exists():
                try:
                    saved = read_text_snapshot(real, self.max_bytes)
                except TextFileError as exc:
                    raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
                return {"state": "clean", **{k: v for k, v in saved.items() if k != "content"}}

            current = self._working_snapshot(working)
            if not isinstance(expect_hash, str) or expect_hash != current["hash"]:
                raise WorkingCopyError(
                    409,
                    "Working copy changed since the browser last acknowledged it",
                    reason="stale",
                    currentHash=current["hash"],
                )
            meta = self._read_meta(meta_path)
            try:
                result = save_text_cas(real, current["content"], expect_saved_version, self.max_bytes)
            except TextFileError as exc:
                details = dict(exc.details)
                if exc.status == 409:
                    details.setdefault("reason", "external")
                raise WorkingCopyError(exc.status, str(exc), **details) from exc

            after = self._working_snapshot(working)
            if after["hash"] != current["hash"]:
                raise WorkingCopyError(
                    409,
                    "Working copy changed while Save was committing",
                    reason="stale",
                    currentHash=after["hash"],
                )
            self._delete_dir(working.parent)
            self._write_guard_state()
            return {"state": "clean", **result}

    def discard(self, rel: str, *, expect_hash: str | None) -> dict[str, Any]:
        logical, _real, doc_id, working, _meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            self._ensure_not_turn(doc_id)
            if working.exists():
                current = self._working_snapshot(working)
                if not isinstance(expect_hash, str) or expect_hash != current["hash"]:
                    raise WorkingCopyError(
                        409,
                        "Working copy changed since the browser last acknowledged it",
                        reason="stale",
                        currentHash=current["hash"],
                    )
                self._delete_dir(working.parent)
                self._write_guard_state()
            return {"ok": True, "path": logical, "state": "clean"}

    def begin_turn(self, rel: str, expect_hash: str | None) -> dict[str, Any]:
        logical, real, doc_id, working, _meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            turn = self._turn_state(doc_id)
            if turn.active:
                raise WorkingCopyError(409, "Pi is already editing this working copy", reason="pi_turn")
            had_work = working.exists()
            if not had_work:
                saved = read_text_snapshot(real, self.max_bytes)
                # A clean document still needs a durable target while Pi owns the turn.
                raw = self._normalized_text(saved["content"]).encode("utf-8")
                self._atomic_replace_bytes(working, raw)
                meta = self._meta_payload(
                    doc_id=doc_id,
                    logical=logical,
                    real=real,
                    working=working,
                    base=saved,
                    work_hash=self._hash_bytes(raw),
                )
                self._write_meta(self._paths(logical)[4], meta)
            current = self._working_snapshot(working)
            if had_work and (not isinstance(expect_hash, str) or expect_hash != current["hash"]):
                raise WorkingCopyError(
                    409,
                    "Browser draft is not flushed to the working copy",
                    reason="stale",
                    currentHash=current["hash"],
                )
            if not had_work and expect_hash not in (None, "", current["hash"]):
                raise WorkingCopyError(
                    409,
                    "Browser draft is not flushed to the working copy",
                    reason="stale",
                    currentHash=current["hash"],
                )
            turn.active = True
            turn.start_real_hash = read_text_snapshot(real, self.max_bytes)["version"]
            self._write_guard_state()
            return {
                "path": logical,
                "workingPath": str(working),
                "hash": current["hash"],
                "startRealHash": turn.start_real_hash,
            }

    def peek_hash(self, rel: str) -> str | None:
        _logical, _real, _doc_id, working, _meta_path = self._paths(rel)
        if not working.exists():
            return None
        return self._working_snapshot(working)["hash"]

    def end_turn(self, rel: str) -> dict[str, Any]:
        logical, real, doc_id, working, _meta_path = self._paths(rel)
        lock = self._lock_for(doc_id)
        with lock:
            turn = self._turn_state(doc_id)
            current_hash = None
            if working.exists():
                current = self._working_snapshot(working)
                normalized_raw = self._normalized_text(current["content"]).encode("utf-8")
                normalized_hash = self._hash_bytes(normalized_raw)
                if normalized_hash != current["hash"]:
                    self._atomic_replace_bytes(working, normalized_raw)
                current_hash = normalized_hash
                try:
                    meta_path = self._paths(logical)[4]
                    meta = self._read_meta(meta_path)
                    meta["workHash"] = current_hash
                    meta["updatedAt"] = time.time()
                    self._write_meta(meta_path, meta)
                except WorkingCopyError:
                    pass
            try:
                real_hash = read_text_snapshot(real, self.max_bytes)["version"]
            except TextFileError:
                real_hash = ""
            real_touched = bool(turn.start_real_hash and real_hash != turn.start_real_hash)
            turn.active = False
            turn.start_real_hash = ""
            self._write_guard_state()
            return {
                "path": logical,
                "hash": current_hash,
                "realTouched": real_touched,
            }

    def working_path(self, rel: str) -> Path | None:
        _logical, _real, _doc_id, working, _meta_path = self._paths(rel)
        return working if working.exists() else None

    def _staged_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        if not self.work_dir.exists():
            return entries
        for meta_path in self.work_dir.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                real = str(meta.get("realPath") or "")
                working = str(meta.get("workingPath") or "")
                if real and working and Path(working).is_file():
                    entries.append({
                        "real": os.path.normcase(str(Path(real).resolve())),
                        "working": os.path.normcase(str(Path(working).resolve())),
                    })
            except Exception:
                continue
        return entries

    def _write_guard_state(self) -> None:
        staged = self._staged_entries()
        writable: list[str] = []
        for item in staged:
            real = Path(item["real"])
            try:
                rel = real.resolve().relative_to(self.root).as_posix()
                _logical, _path, doc_id = self._resolve(rel)
            except Exception:
                continue
            if self._turn_state(doc_id).active:
                writable.append(item["working"])
        payload = {
            "staged": staged,
            "turnWritable": writable,
            "protectedDir": os.path.normcase(str(self.work_dir.parent.resolve())),
        }
        self._atomic_replace_bytes(
            self.guard_path,
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )

"""Live Markdown editing: project .md is authoritative, md_temp is an accepted snapshot.

A write from the browser updates the real .md with compare-and-swap. Pi edits
that same real path through its native edit tool; VS Code changes are observed
by reading the real file. Ctrl+S accepts the current bytes into md_temp only.

Legacy unsaved staged edits are never silently discarded or promoted.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .text_file import (
    MAX_TEXT_FILE_BYTES, TextFileError, read_text_snapshot,
    patch_text_cas, save_text_cas, snapshot_from_bytes,
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
        self.versions_dir = self.legacy_dir / "md_versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)
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

    def _check_not_in_bot_turn(self, identifier: str) -> None:
        if identifier in self.turns:
            raise WorkingCopyError(
                409,
                "File is locked while LanternBot is editing it",
                reason="pi_turn",
            )

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
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            for attempt in range(6):
                try:
                    os.replace(tmp, dst)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.025)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _version_dir_for(self, identifier: str) -> Path:
        d = self.versions_dir / identifier
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_version_index(self, identifier: str) -> list[dict[str, Any]]:
        vdir = self._version_dir_for(identifier)
        idx_path = vdir / "index.json"
        if not idx_path.is_file():
            return []
        try:
            raw = json.loads(idx_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
        except Exception:
            pass
        return []

    def _save_version_index(self, identifier: str, entries: list[dict[str, Any]]) -> None:
        vdir = self._version_dir_for(identifier)
        idx_path = vdir / "index.json"
        self._atomic_copy_bytes(
            idx_path,
            (json.dumps(entries[-120:], ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )

    def _record_version_snapshot(self, identifier: str, raw: bytes, *, ts: float | None = None) -> dict[str, Any] | None:
        """Record a version snapshot if and only if its content hash differs from the most recent saved version."""
        ver_hash = hashlib.sha256(raw).hexdigest()
        vdir = self._version_dir_for(identifier)
        blob_path = vdir / f"{ver_hash}.md"
        if not blob_path.is_file():
            self._atomic_copy_bytes(blob_path, raw)
        entries = self._load_version_index(identifier)
        if entries and str(entries[-1].get("version") or "") == ver_hash:
            # Also clean up any older duplicate entries with the same hash if present
            deduped = [e for e in entries[:-1] if str(e.get("version") or "") != ver_hash] + [entries[-1]]
            if len(deduped) != len(entries):
                self._save_version_index(identifier, deduped)
            return None
        # When restoring an older version B and pressing Save, promote B to the new
        # current entry C and remove the old duplicate B so only A and C remain.
        entries = [e for e in entries if str(e.get("version") or "") != ver_hash]
        now_ts = float(ts if ts is not None else time.time())
        entry = {
            "id": f"v-{int(now_ts * 1000)}-{uuid4().hex[:6]}",
            "version": ver_hash,
            "timestamp": now_ts,
            "bytes": len(raw),
        }
        entries.append(entry)
        self._save_version_index(identifier, entries)
        return entry

    def record_version_if_changed(self, rel: str, raw: bytes) -> dict[str, Any] | None:
        _logical, _real, identifier, _temp = self._resolve(rel)
        with self.lock:
            return self._record_version_snapshot(identifier, raw)

    def ensure_baseline(self, rel: str) -> dict[str, Any]:
        """Ensure an accepted md_temp baseline exists for a real project Markdown file
        before Lanbot begins a turn, even if the file was never opened in Lantern UI.
        - If a baseline already exists, keeps it untouched (never overwrites).
        - Creates baseline strictly from the original project file, rejecting uploaded copies
          in .lantern_uploads/ or non-existent paths with a clear error rather than guessing.
        """
        if not isinstance(rel, str) or not rel.strip():
            raise WorkingCopyError(400, "Markdown attachment path is required", reason="invalid_attachment")
        norm = rel.strip().replace("\\", "/")
        try:
            cand = Path(norm)
            if cand.is_absolute():
                rel_posix = cand.resolve().relative_to(self.root).as_posix()
            else:
                rel_posix = norm.lstrip("/")
        except ValueError as exc:
            raise WorkingCopyError(403, "Markdown attachment escapes project root", reason="outside_root") from exc

        if rel_posix == ".lantern_uploads" or rel_posix.startswith(".lantern_uploads/"):
            raise WorkingCopyError(
                400,
                f"Cannot create Markdown baseline for uploaded copy '{Path(rel_posix).name}': "
                "original project file cannot be determined from an uploaded copy. "
                "Please attach or drag the original Markdown file from the Lantern workspace.",
                reason="upload_copy_no_original",
                path=rel_posix,
            )
        logical, real, identifier, temp = self._resolve(rel_posix)
        if not real.exists() or not real.is_file():
            raise WorkingCopyError(
                404,
                f"Original Markdown file not found in project: {logical}",
                reason="missing_original",
                path=logical,
            )
        with self.lock:
            already_existed = temp.is_file()
            baseline = self._baseline(real, identifier, temp)
            return {
                "path": logical,
                "realPath": str(real),
                "tempPath": str(temp),
                "version": baseline["version"],
                "created": not already_existed,
            }

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
            try:
                mtime = real.stat().st_mtime
            except OSError:
                mtime = time.time()
            self._record_version_snapshot(identifier, raw, ts=mtime)
        else:
            # Ensure initial baseline is present in version index if index is empty
            if not self._load_version_index(identifier):
                try:
                    raw_temp = temp.read_bytes()
                    self._record_version_snapshot(identifier, raw_temp, ts=temp.stat().st_mtime)
                except Exception:
                    pass
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
            self._check_not_in_bot_turn(identifier)
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

    def patch(self, rel: str, patches: list[dict[str, Any]], *,
              expect_hash: str | None, base_version: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            self._check_not_in_bot_turn(identifier)
            baseline = self._baseline(real, identifier, temp)
            if baseline["version"] != base_version:
                raise WorkingCopyError(
                    409,
                    "Accepted Markdown baseline changed",
                    reason="baseline_changed",
                    currentVersion=baseline["version"],
                )
            before = self._read_real(real)
            expected = expect_hash or base_version
            if before["version"] != expected:
                raise WorkingCopyError(
                    409,
                    "Project file changed in another editor",
                    reason="stale",
                    currentHash=(before["version"]
                                 if before["version"] != base_version else None),
                    currentVersion=before["version"],
                )
            try:
                result = patch_text_cas(real, patches, expected, self.max_bytes)
            except TextFileError as exc:
                reason = "stale" if exc.status == 409 else "invalid_patch"
                raise WorkingCopyError(exc.status, str(exc), reason=reason,
                                       **exc.details) from exc
            changed = result["version"] != baseline["version"]
            return {
                "path": logical,
                "state": "pending" if changed else "clean",
                "hash": result["version"] if changed else None,
                "currentVersion": result["version"],
                "updatedAt": time.time(),
            }

    def save(self, rel: str, *, expect_hash: str | None,
             expect_saved_version: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            self._check_not_in_bot_turn(identifier)
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
            self._record_version_snapshot(identifier, raw)
            return {"state": "clean", "version": current["version"],
                    "bytes": len(raw), "tempPath": str(temp)}

    def list_versions(self, rel: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            current = self._read_real(real)
            baseline = self._baseline(real, identifier, temp)
            entries = self._load_version_index(identifier)
            today_date = datetime.date.today()
            yesterday_date = today_date - datetime.timedelta(days=1)
            grouped_map: dict[str, dict[str, Any]] = {}
            flat_versions: list[dict[str, Any]] = []
            seen_hashes: set[str] = set()
            for item in reversed(entries):
                ver_hash_chk = str(item.get("version") or "")
                if ver_hash_chk and ver_hash_chk in seen_hashes:
                    continue
                if ver_hash_chk:
                    seen_hashes.add(ver_hash_chk)
                ts = float(item.get("timestamp") or time.time())
                dt = datetime.datetime.fromtimestamp(ts)
                d_key = dt.strftime("%Y-%m-%d")
                if dt.date() == today_date:
                    date_label = "Today"
                    date_sub = dt.strftime("%d/%m")
                elif dt.date() == yesterday_date:
                    date_label = dt.strftime("%d/%m")
                    date_sub = "Yesterday"
                else:
                    date_label = dt.strftime("%d/%m") if dt.year == today_date.year else dt.strftime("%d/%m/%Y")
                    date_sub = ""
                ver_hash = str(item.get("version") or "")
                v_info = {
                    "id": str(item.get("id") or ver_hash[:10]),
                    "version": ver_hash,
                    "timestamp": ts,
                    "dateKey": d_key,
                    "dateLabel": date_label,
                    "dateSub": date_sub,
                    "timeLabel": dt.strftime("%Hh%M"),
                    "timeFull": dt.strftime("%H:%M:%S"),
                    "bytes": int(item.get("bytes") or 0),
                    "isBaseline": ver_hash == baseline["version"],
                    "isCurrent": ver_hash == current["version"],
                }
                flat_versions.append(v_info)
                if d_key not in grouped_map:
                    grouped_map[d_key] = {
                        "dateKey": d_key,
                        "dateLabel": date_label,
                        "dateSub": date_sub,
                        "items": [],
                    }
                grouped_map[d_key]["items"].append(v_info)
            return {
                "path": logical,
                "currentVersion": current["version"],
                "baselineVersion": baseline["version"],
                "groups": list(grouped_map.values()),
                "versions": flat_versions,
            }

    def restore_version(self, rel: str, *, version_id: str = "", version_hash: str = "") -> dict[str, Any]:
        """Write a saved version snapshot directly into the real project .md file (leaving md_temp untouched)
        so Lantern's live diff engine immediately shows the diff against the last Ctrl+S baseline."""
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            self._check_not_in_bot_turn(identifier)
            baseline = self._baseline(real, identifier, temp)
            entries = self._load_version_index(identifier)
            target_entry = None
            for item in entries:
                if version_id and str(item.get("id") or "") == version_id:
                    target_entry = item
                    break
                if version_hash and str(item.get("version") or "") == version_hash:
                    target_entry = item
                    break
            target_hash = str((target_entry or {}).get("version") or version_hash or "").strip()
            if not target_hash:
                raise WorkingCopyError(404, "Requested Markdown version not found")
            vdir = self._version_dir_for(identifier)
            blob_path = vdir / f"{target_hash}.md"
            if not blob_path.is_file():
                raise WorkingCopyError(404, "Version snapshot file is missing")
            raw_bytes = blob_path.read_bytes()
            snap = snapshot_from_bytes(raw_bytes)
            current = self._read_real(real)
            try:
                save_text_cas(real, snap["content"], current["version"], self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
            state = self.get(rel)
            return {
                "restoredVersion": target_hash,
                "restoredId": str((target_entry or {}).get("id") or ""),
                **state,
            }

    def accept_partial(self, rel: str, content: str, *,
                       expect_saved_version: str,
                       expect_current_version: str) -> dict[str, Any]:
        """Accept only selected diff hunks into md_temp; never write real .md."""
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            self._check_not_in_bot_turn(identifier)
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
            self._check_not_in_bot_turn(identifier)
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
            "rootDir": str(self.root),
            "tempDir": str(self.temp_dir),
            "markdownSuffixes": sorted(self.suffixes),
        }
        self._atomic_copy_bytes(
            self.guard_path,
            (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"),
        )

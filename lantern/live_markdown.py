"""Live Markdown editing: project .md is authoritative, md_temp is an accepted snapshot.

A write from the browser updates the real .md with compare-and-swap. Pi edits
that same real path through its native edit tool; VS Code changes are observed
by reading the real file. Ctrl+S accepts the current bytes into md_temp only.

v7.92 upgrades:
- 60-second save window coalescing (saves within 60s of the current save window update
  the latest version snapshot in-place; saves >= 60s open a new version snapshot).
- Automatic migration of md_temp baseline and md_versions history when a .md file is
  renamed or moved (via inode + SHA-256 tracking and explicit Explorer hooks).
- Automatic garbage collection of orphaned / ghost md_temp and md_versions folders.
- Concurrent user Save / Undo and shadow-draft 3-way merge while Lanbot is editing.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import os
import shutil
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

VERSION_COALESCE_WINDOW_SEC = 60.0
ORPHAN_GC_INTERVAL_SEC = 60.0


def _merge3_text(base: str, user: str, bot: str) -> tuple[str, bool]:
    """Perform a line-based 3-way merge between base, user, and bot texts.
    Returns (merged_text, has_conflict).
    """
    if user == bot:
        return user, False
    if user == base:
        return bot, False
    if bot == base:
        return user, False

    base_lines = base.splitlines(keepends=True)
    user_lines = user.splitlines(keepends=True)
    bot_lines = bot.splitlines(keepends=True)

    user_ops = [
        op for op in difflib.SequenceMatcher(None, base_lines, user_lines).get_opcodes()
        if op[0] != "equal"
    ]
    bot_ops = [
        op for op in difflib.SequenceMatcher(None, base_lines, bot_lines).get_opcodes()
        if op[0] != "equal"
    ]

    out: list[str] = []
    bi = 0
    ui = 0
    ki = 0
    conflict = False

    while ui < len(user_ops) or ki < len(bot_ops):
        u_op = user_ops[ui] if ui < len(user_ops) else None
        k_op = bot_ops[ki] if ki < len(bot_ops) else None

        if u_op and (not k_op or u_op[2] < k_op[1] or (u_op[2] == k_op[1] and u_op[1] < k_op[1])):
            out.extend(base_lines[bi:u_op[1]])
            out.extend(user_lines[u_op[3]:u_op[4]])
            bi = u_op[2]
            ui += 1
        elif k_op and (not u_op or k_op[2] < u_op[1] or (k_op[2] == u_op[1] and k_op[1] < u_op[1])):
            out.extend(base_lines[bi:k_op[1]])
            out.extend(bot_lines[k_op[3]:k_op[4]])
            bi = k_op[2]
            ki += 1
        else:
            # Overlapping change region
            assert u_op is not None and k_op is not None
            start_b = min(u_op[1], k_op[1])
            end_b = max(u_op[2], k_op[2])
            if start_b > bi:
                out.extend(base_lines[bi:start_b])
            u_slice = user_lines[u_op[3]:u_op[4]]
            k_slice = bot_lines[k_op[3]:k_op[4]]
            if u_op[1] == k_op[1] and u_op[2] == k_op[2] and u_slice == k_slice:
                out.extend(u_slice)
            else:
                conflict = True
                # Preserve user's edit in the primary text; bot's full version is also kept in botConflict
                out.extend(u_slice)
            bi = end_b
            ui += 1
            ki += 1

    if bi < len(base_lines):
        out.extend(base_lines[bi:])
    return "".join(out), conflict


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
        self._turn_contexts: dict[str, dict[str, Any]] = {}
        self._bot_conflicts: dict[str, dict[str, Any]] = {}
        self._last_gc_ts: float = 0.0
        # Fail closed before a trusted prompt provides its origin-derived scope.
        self.active_scope = "lan"
        self.active_tools: tuple[str, ...] = ("read", "grep", "find", "ls")
        self.guard_path = self.temp_dir / ("live-guard-" +
            hashlib.sha256(os.path.normcase(str(self.root)).encode()).hexdigest()[:12] + ".json")
        self._write_guard()

    def _compute_identifier(self, logical: str) -> str:
        key = os.path.normcase(str(self.root)) + "\0" + os.path.normcase(logical)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]

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
        identifier = self._compute_identifier(logical)
        return logical, candidate, identifier, self.temp_dir / identifier / candidate.name

    def _user_draft_path(self, identifier: str) -> Path:
        return self.temp_dir / identifier / ".user_draft.md"

    def _user_base_real_path(self, identifier: str) -> Path:
        return self.temp_dir / identifier / ".user_base_real.md"

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

    def _meta_path_for(self, identifier: str) -> Path:
        return self._version_dir_for(identifier) / "meta.json"

    def _load_meta(self, identifier: str) -> dict[str, Any]:
        mp = self.versions_dir / identifier / "meta.json"
        if not mp.is_file():
            return {}
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _update_meta(self, identifier: str, logical: str, real: Path, temp: Path,
                     *, real_sha: str | None = None, temp_sha: str | None = None) -> None:
        try:
            st = real.stat() if real.is_file() else None
            if real_sha is None and real.is_file():
                real_sha = hashlib.sha256(real.read_bytes()).hexdigest()
            if temp_sha is None and temp.is_file():
                temp_sha = hashlib.sha256(temp.read_bytes()).hexdigest()
            meta = {
                "identifier": identifier,
                "root": os.path.normcase(str(self.root)),
                "logicalPath": logical,
                "fileName": real.name,
                "inode": int(st.st_ino) if st else 0,
                "dev": int(st.st_dev) if st else 0,
                "size": int(st.st_size) if st else 0,
                "realSha256": real_sha or "",
                "tempSha256": temp_sha or "",
                "updatedAt": time.time(),
            }
            self._atomic_copy_bytes(
                self._meta_path_for(identifier),
                (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except Exception:
            pass

    def _migrate_identifier_storage(self, old_id: str, new_id: str, new_logical: str, new_real: Path, new_temp: Path) -> bool:
        if old_id == new_id:
            return False
        old_temp_dir = self.temp_dir / old_id
        old_vdir = self.versions_dir / old_id
        migrated = False
        try:
            if old_temp_dir.is_dir():
                temp_files = [f for f in old_temp_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
                if temp_files:
                    new_temp.parent.mkdir(parents=True, exist_ok=True)
                    self._atomic_copy_bytes(new_temp, temp_files[0].read_bytes())
                    migrated = True
                shutil.rmtree(old_temp_dir, ignore_errors=True)
            if old_vdir.is_dir():
                new_vdir = self.versions_dir / new_id
                if new_vdir.exists():
                    shutil.rmtree(new_vdir, ignore_errors=True)
                shutil.move(str(old_vdir), str(new_vdir))
                migrated = True
            if migrated:
                self._update_meta(new_id, new_logical, new_real, new_temp)
        except Exception:
            return False
        return migrated

    def _try_migrate_renamed_or_moved(self, logical: str, real: Path, identifier: str, temp: Path) -> bool:
        """If `real` was renamed or moved on disk (externally or via Explorer),
        locate its previous md_temp/md_versions entry by OS inode or SHA-256 content hash
        and migrate its history seamlessly to the new path."""
        if not real.is_file():
            return False
        try:
            st = real.stat()
            raw = real.read_bytes()
            real_sha = hashlib.sha256(raw).hexdigest()
        except OSError:
            return False

        best_old_id: str | None = None
        # Pass 1: Look for an orphaned entry from the SAME root with matching inode or content hash
        norm_root = os.path.normcase(str(self.root))
        try:
            for vdir in self.versions_dir.iterdir():
                if not vdir.is_dir() or vdir.name == identifier:
                    continue
                meta = self._load_meta(vdir.name)
                meta_root = str(meta.get("root") or "")
                if meta_root and meta_root != norm_root:
                    continue
                old_logical = str(meta.get("logicalPath") or "")
                if old_logical:
                    old_real = (self.root / old_logical).resolve()
                    if old_real.exists():
                        continue
                # Check inode match first (survives external rename + edit on same filesystem)
                old_ino = int(meta.get("inode") or 0)
                old_dev = int(meta.get("dev") or 0)
                if old_ino > 0 and st.st_ino > 0 and old_ino == st.st_ino and (old_dev == 0 or old_dev == st.st_dev):
                    best_old_id = vdir.name
                    break
                # Check SHA-256 match against realSha256, tempSha256, or any saved version snapshot
                if len(raw) > 0:
                    if real_sha and real_sha in {str(meta.get("realSha256") or ""), str(meta.get("tempSha256") or "")}:
                        best_old_id = vdir.name
                        break
                    if (vdir / f"{real_sha}.md").is_file():
                        best_old_id = vdir.name
                        break
        except Exception:
            return False

        if best_old_id:
            return self._migrate_identifier_storage(best_old_id, identifier, logical, real, temp)
        return False

    def notify_moved(self, old_rel: str, new_rel: str) -> bool:
        """Explicitly migrate md_temp and md_versions when a file or folder is renamed/moved in Lantern."""
        with self.lock:
            old_clean = old_rel.strip().replace("\\", "/").lstrip("/")
            new_clean = new_rel.strip().replace("\\", "/").lstrip("/")
            if not old_clean or not new_clean:
                return False
            # Support both single Markdown file move and parent directory move
            old_cand = (self.root / old_clean).resolve()
            new_cand = (self.root / new_clean).resolve()
            if new_cand.suffix.lower() in self.suffixes:
                old_id = self._compute_identifier(old_clean)
                new_id = self._compute_identifier(new_clean)
                new_temp = self.temp_dir / new_id / new_cand.name
                return self._migrate_identifier_storage(old_id, new_id, new_clean, new_cand, new_temp)
            # Directory move: migrate any tracked markdown files under old_clean/
            migrated_any = False
            prefix = old_clean.rstrip("/") + "/"
            new_prefix = new_clean.rstrip("/") + "/"
            try:
                for vdir in list(self.versions_dir.iterdir()):
                    if not vdir.is_dir():
                        continue
                    meta = self._load_meta(vdir.name)
                    tracked_rel = str(meta.get("logicalPath") or "")
                    if tracked_rel.startswith(prefix):
                        sub = tracked_rel[len(prefix):]
                        target_rel = new_prefix + sub
                        target_real = (self.root / target_rel).resolve()
                        target_id = self._compute_identifier(target_rel)
                        target_temp = self.temp_dir / target_id / target_real.name
                        if self._migrate_identifier_storage(vdir.name, target_id, target_rel, target_real, target_temp):
                            migrated_any = True
            except Exception:
                pass
            return migrated_any

    def notify_deleted(self, rel: str) -> int:
        """Clean up md_temp and md_versions when a Markdown file or folder is deleted."""
        with self.lock:
            clean = rel.strip().replace("\\", "/").lstrip("/")
            if not clean:
                return 0
            removed = 0
            cand = (self.root / clean).resolve()
            if cand.suffix.lower() in self.suffixes:
                ident = self._compute_identifier(clean)
                if (self.temp_dir / ident).exists():
                    shutil.rmtree(self.temp_dir / ident, ignore_errors=True)
                    removed += 1
                if (self.versions_dir / ident).exists():
                    shutil.rmtree(self.versions_dir / ident, ignore_errors=True)
                    removed += 1
                return removed
            prefix = clean.rstrip("/") + "/"
            try:
                for vdir in list(self.versions_dir.iterdir()):
                    if not vdir.is_dir():
                        continue
                    meta = self._load_meta(vdir.name)
                    tracked_rel = str(meta.get("logicalPath") or "")
                    if tracked_rel.startswith(prefix):
                        shutil.rmtree(self.temp_dir / vdir.name, ignore_errors=True)
                        shutil.rmtree(vdir, ignore_errors=True)
                        removed += 1
            except Exception:
                pass
            return removed

    def cleanup_orphans(self, *, max_orphan_age_sec: float = 0.0) -> int:
        """Scan md_temp and md_versions for ghost/orphaned entries whose project file no longer
        exists (after attempting migration to any renamed/moved file in the workspace)."""
        with self.lock:
            self._last_gc_ts = time.time()
            removed = 0
            # Collect all orphaned identifiers
            orphan_ids: list[str] = []
            seen_ids: set[str] = set()
            for base_dir in (self.versions_dir, self.temp_dir):
                if not base_dir.is_dir():
                    continue
                for child in list(base_dir.iterdir()):
                    if not child.is_dir() or child.name in seen_ids:
                        continue
                    seen_ids.add(child.name)
                    meta = self._load_meta(child.name)
                    meta_root = str(meta.get("root") or "")
                    if meta_root and meta_root != os.path.normcase(str(self.root)):
                        continue
                    logical = str(meta.get("logicalPath") or "")
                    if logical:
                        real_path = (self.root / logical).resolve()
                        if real_path.is_file():
                            continue
                        # File is missing at its old path; check if it was renamed/moved anywhere in root
                        migrated = False
                        try:
                            for md_cand in self.root.rglob("*"):
                                if not md_cand.is_file() or md_cand.suffix.lower() not in self.suffixes:
                                    continue
                                rel_cand = md_cand.relative_to(self.root).as_posix()
                                if rel_cand.startswith(".lantern"):
                                    continue
                                cand_id = self._compute_identifier(rel_cand)
                                if (self.temp_dir / cand_id / md_cand.name).is_file():
                                    continue
                                st = md_cand.stat()
                                old_ino = int(meta.get("inode") or 0)
                                if old_ino > 0 and st.st_ino == old_ino:
                                    cand_temp = self.temp_dir / cand_id / md_cand.name
                                    if self._migrate_identifier_storage(child.name, cand_id, rel_cand, md_cand, cand_temp):
                                        migrated = True
                                        break
                                if st.st_size > 0 and st.st_size == int(meta.get("size") or -1):
                                    sha = hashlib.sha256(md_cand.read_bytes()).hexdigest()
                                    if sha in {str(meta.get("realSha256") or ""), str(meta.get("tempSha256") or "")}:
                                        cand_temp = self.temp_dir / cand_id / md_cand.name
                                        if self._migrate_identifier_storage(child.name, cand_id, rel_cand, md_cand, cand_temp):
                                            migrated = True
                                            break
                        except Exception:
                            pass
                        if migrated:
                            continue
                        updated_at = float(meta.get("updatedAt") or 0.0)
                        if max_orphan_age_sec <= 0.0 or (time.time() - updated_at) >= max_orphan_age_sec:
                            orphan_ids.append(child.name)
                    else:
                        # No meta.json: check if any matching temp file still maps to an existing file
                        try:
                            mtime = child.stat().st_mtime
                        except OSError:
                            mtime = 0.0
                        if max_orphan_age_sec > 0.0 and (time.time() - mtime) < max(60.0, max_orphan_age_sec):
                            continue
                        orphan_ids.append(child.name)

            for oid in orphan_ids:
                t_dir = self.temp_dir / oid
                v_dir = self.versions_dir / oid
                if t_dir.exists():
                    shutil.rmtree(t_dir, ignore_errors=True)
                    removed += 1
                if v_dir.exists():
                    shutil.rmtree(v_dir, ignore_errors=True)
                    removed += 1
            return removed

    def _maybe_periodic_gc(self) -> None:
        now = time.time()
        if (now - self._last_gc_ts) >= ORPHAN_GC_INTERVAL_SEC:
            self.cleanup_orphans(max_orphan_age_sec=300.0)

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

    def _record_version_snapshot(
        self,
        identifier: str,
        raw: bytes,
        *,
        ts: float | None = None,
        is_initial: bool = False,
        coalesce_window_sec: float = VERSION_COALESCE_WINDOW_SEC,
    ) -> dict[str, Any] | None:
        """Record a version snapshot with 1-minute (60s) save-window coalescing:
        - If content hash equals the latest version, no duplicate is created.
        - If restoring an older version B and pressing Save, promotes B to the latest entry.
        - For user saves within `coalesce_window_sec` (60s) of the current save window's `windowStart`,
          updates the most recent non-initial version entry in-place instead of creating a new entry.
        - Once `>= 60s` have elapsed since `windowStart`, creates a new version entry and starts a new window.
        """
        ver_hash = hashlib.sha256(raw).hexdigest()
        vdir = self._version_dir_for(identifier)
        blob_path = vdir / f"{ver_hash}.md"
        if not blob_path.is_file():
            self._atomic_copy_bytes(blob_path, raw)
        entries = self._load_version_index(identifier)
        now_ts = float(ts if ts is not None else time.time())

        if entries:
            last_ver = str(entries[-1].get("version") or "")
            if last_ver == ver_hash:
                deduped = [e for e in entries[:-1] if str(e.get("version") or "") != ver_hash] + [entries[-1]]
                if len(deduped) != len(entries):
                    self._save_version_index(identifier, deduped)
                return None
            # Also check normalized text diff so CRLF/LF or no-diff saves never create a redundant version
            last_blob = vdir / f"{last_ver}.md"
            if last_blob.is_file():
                try:
                    norm_new = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").rstrip("\n")
                    norm_old = last_blob.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n").rstrip("\n")
                    if norm_new == norm_old:
                        return None
                except Exception:
                    pass

        # Check if ver_hash already existed as an older version (e.g. user restored an older version B and pressed Save)
        existed_previously = any(str(e.get("version") or "") == ver_hash for e in entries)
        if existed_previously:
            entries = [e for e in entries if str(e.get("version") or "") != ver_hash]
            entry = {
                "id": f"v-{int(now_ts * 1000)}-{uuid4().hex[:6]}",
                "version": ver_hash,
                "timestamp": now_ts,
                "windowStart": now_ts,
                "bytes": len(raw),
                "isInitial": False,
            }
            entries.append(entry)
            self._save_version_index(identifier, entries)
            return entry

        # Coalesce consecutive user saves within the 60-second window
        if not is_initial and entries and coalesce_window_sec > 0:
            last = entries[-1]
            last_is_initial = bool(last.get("isInitial", len(entries) == 1))
            window_start = float(last.get("windowStart") or last.get("timestamp") or 0.0)
            if not last_is_initial and window_start > 0 and 0.0 <= (now_ts - window_start) < coalesce_window_sec:
                old_hash = str(last.get("version") or "")
                last["version"] = ver_hash
                last["timestamp"] = now_ts
                last["bytes"] = len(raw)
                last["windowStart"] = window_start
                last["isInitial"] = False
                self._save_version_index(identifier, entries)
                # Remove superseded blob if no other entry references it
                if old_hash and old_hash != ver_hash and not any(str(e.get("version") or "") == old_hash for e in entries):
                    try:
                        (vdir / f"{old_hash}.md").unlink(missing_ok=True)
                    except OSError:
                        pass
                return last

        entry = {
            "id": f"v-{int(now_ts * 1000)}-{uuid4().hex[:6]}",
            "version": ver_hash,
            "timestamp": now_ts,
            "windowStart": now_ts,
            "bytes": len(raw),
            "isInitial": bool(is_initial or not entries),
        }
        entries.append(entry)
        self._save_version_index(identifier, entries)
        return entry

    def record_version_if_changed(self, rel: str, raw: bytes) -> dict[str, Any] | None:
        _logical, _real, identifier, _temp = self._resolve(rel)
        with self.lock:
            return self._record_version_snapshot(identifier, raw)

    def ensure_baseline(self, rel: str) -> dict[str, Any]:
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
            baseline = self._baseline(real, identifier, temp, logical=logical)
            return {
                "path": logical,
                "realPath": str(real),
                "tempPath": str(temp),
                "version": baseline["version"],
                "created": not already_existed,
            }

    def _baseline(self, real: Path, identifier: str, temp: Path, *, logical: str = "") -> dict[str, Any]:
        if not logical:
            try:
                logical = real.resolve().relative_to(self.root).as_posix()
            except Exception:
                logical = real.name
        if not temp.is_file():
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
            # Attempt migration if this file was renamed or moved from an existing tracked .md file
            self._try_migrate_renamed_or_moved(logical, real, identifier, temp)

        if not temp.is_file():
            raw = real.read_bytes()
            if len(raw) > self.max_bytes:
                raise WorkingCopyError(413, "Markdown exceeds live edit size limit")
            snapshot_from_bytes(raw)
            self._atomic_copy_bytes(temp, raw)
            try:
                mtime = real.stat().st_mtime
            except OSError:
                mtime = time.time()
            self._record_version_snapshot(identifier, raw, ts=mtime, is_initial=True)
            sha = hashlib.sha256(raw).hexdigest()
            self._update_meta(identifier, logical, real, temp, real_sha=sha, temp_sha=sha)
        else:
            if not self._load_version_index(identifier):
                try:
                    raw_temp = temp.read_bytes()
                    self._record_version_snapshot(identifier, raw_temp, ts=temp.stat().st_mtime, is_initial=True)
                except Exception:
                    pass
            self._update_meta(identifier, logical, real, temp)
        return self._read_real(temp)

    def get(self, rel: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            real_snap = self._read_real(real)
            baseline = self._baseline(real, identifier, temp, logical=logical)
            user_temp = self._user_draft_path(identifier)
            user_snap: dict[str, Any] | None = None
            if user_temp.is_file():
                try:
                    user_snap = self._read_real(user_temp)
                except Exception:
                    user_snap = None
            turn_ctx = self._turn_contexts.get(identifier)
            if user_snap is None and turn_ctx and turn_ctx.get("userDraftContent") is not None:
                user_content = str(turn_ctx["userDraftContent"])
                user_hash = str(turn_ctx.get("userDraftHash") or hashlib.sha256(user_content.encode("utf-8")).hexdigest())
                user_snap = {
                    **real_snap,
                    "content": user_content,
                    "version": user_hash,
                }
            if user_snap is not None:
                ubase_path = self._user_base_real_path(identifier)
                ubase_snap = None
                if ubase_path.is_file():
                    try:
                        ubase_snap = self._read_real(ubase_path)
                    except Exception:
                        ubase_snap = None
                merge_base_content = ubase_snap["content"] if ubase_snap is not None else baseline["content"]
                if ubase_snap is not None and ubase_snap["version"] == real_snap["version"]:
                    merged_text, has_conflict = user_snap["content"], False
                else:
                    merged_text, has_conflict = _merge3_text(
                        merge_base_content, user_snap["content"], real_snap["content"]
                    )
                merged_hash = hashlib.sha256(merged_text.encode("utf-8")).hexdigest()
                changed = (
                    merged_hash != baseline["version"]
                    or real_snap["version"] != baseline["version"]
                    or user_snap["version"] != baseline["version"]
                )
                current_version = hashlib.sha256(
                    f"{real_snap['version']}:{user_snap['version']}:{merged_hash}".encode("utf-8")
                ).hexdigest()
                work_obj = {
                    "content": merged_text,
                    "hash": user_snap["version"],
                    "mergedHash": merged_hash,
                    "baseVersion": baseline["version"],
                    "realContent": real_snap["content"],
                    "realHash": real_snap["version"],
                    "userContent": user_snap["content"],
                    "userHash": user_snap["version"],
                    "hasConflict": has_conflict,
                    "updatedAt": (user_temp.stat().st_mtime if user_temp.is_file() else time.time()),
                } if changed else None
            else:
                changed = real_snap["version"] != baseline["version"]
                current_version = real_snap["version"]
                work_obj = {
                    "content": real_snap["content"],
                    "hash": real_snap["version"],
                    "mergedHash": real_snap["version"],
                    "baseVersion": baseline["version"],
                    "realContent": real_snap["content"],
                    "realHash": real_snap["version"],
                    "userContent": None,
                    "userHash": None,
                    "hasConflict": False,
                    "updatedAt": real.stat().st_mtime,
                } if changed else None

            conflict_info = self._bot_conflicts.get(identifier)
            res: dict[str, Any] = {
                "path": logical, "live": True,
                "realPath": str(real), "tempPath": str(temp),
                "currentVersion": current_version,
                "turnActive": identifier in self.turns,
                "state": "pending" if changed else "clean",
                "saved": baseline,
                "work": work_obj,
            }
            if changed or user_snap is not None:
                res["realVersion"] = real_snap["version"]
                res["realContent"] = real_snap["content"]
                res["userDraft"] = ({
                    "content": user_snap["content"],
                    "version": user_snap["version"],
                    "hash": user_snap["version"],
                } if user_snap is not None else None)
            if conflict_info:
                res["botConflict"] = conflict_info
            return res

    def write(self, rel: str, content: str, *, expect_hash: str | None,
              base_version: str, allow_concurrent: bool = False,
              user_draft: bool = False) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            if user_draft:
                baseline = self._baseline(real, identifier, temp, logical=logical)
                real_snap = self._read_real(real)
                user_temp = self._user_draft_path(identifier)
                ubase_path = self._user_base_real_path(identifier)
                if not user_temp.is_file():
                    self._atomic_copy_bytes(user_temp, real.read_bytes())
                if not ubase_path.is_file() or identifier not in self.turns:
                    self._atomic_copy_bytes(ubase_path, real.read_bytes())
                u_before = self._read_real(user_temp)
                try:
                    save_text_cas(user_temp, content, u_before["version"], self.max_bytes)
                except Exception:
                    raw_u = content.encode("utf-8")
                    self._atomic_copy_bytes(user_temp, raw_u)
                u_after = self._read_real(user_temp)
                user_hash = u_after["version"]
                user_content_norm = u_after["content"]
                ubase_snap = self._read_real(ubase_path) if ubase_path.is_file() else baseline
                if ubase_snap["version"] == real_snap["version"]:
                    merged_text, has_conflict = user_content_norm, False
                else:
                    merged_text, has_conflict = _merge3_text(
                        ubase_snap["content"], user_content_norm, real_snap["content"]
                    )
                merged_hash = hashlib.sha256(merged_text.encode("utf-8")).hexdigest()
                changed = (
                    user_hash != baseline["version"]
                    or real_snap["version"] != baseline["version"]
                    or merged_hash != baseline["version"]
                )
                if not changed and user_hash == real_snap["version"]:
                    user_temp.unlink(missing_ok=True)
                    composite_ver = real_snap["version"]
                else:
                    composite_ver = hashlib.sha256(
                        f"{real_snap['version']}:{user_hash}:{merged_hash}".encode("utf-8")
                    ).hexdigest()
                return {
                    "state": "pending" if changed else "clean",
                    "hash": user_hash if changed else None,
                    "currentVersion": composite_ver,
                    "realVersion": real_snap["version"],
                    "mergedHash": merged_hash,
                    "mergedContent": merged_text,
                    "hasConflict": has_conflict,
                    "userDraft": True,
                    "concurrentStaged": identifier in self.turns,
                    "updatedAt": time.time(),
                }

            if identifier in self.turns:
                if not allow_concurrent:
                    self._check_not_in_bot_turn(identifier)
                # Concurrent user edit during an active bot turn: stage into _turn_contexts
                # so Pi Coding Agent can still edit the untouched real file on disk without retry loops!
                baseline = self._baseline(real, identifier, temp, logical=logical)
                turn_ctx = self._turn_contexts.setdefault(identifier, {})
                turn_ctx["userDraftContent"] = content
                user_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                turn_ctx["userDraftHash"] = user_hash
                changed = user_hash != baseline["version"]
                return {
                    "state": "pending" if changed else "clean",
                    "hash": user_hash if changed else None,
                    "currentVersion": user_hash,
                    "concurrentStaged": True,
                    "updatedAt": time.time(),
                }
            baseline = self._baseline(real, identifier, temp, logical=logical)
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
            self._update_meta(identifier, logical, real, temp, real_sha=result["version"], temp_sha=baseline["version"])
            changed = result["version"] != baseline["version"]
            return {"state": "pending" if changed else "clean",
                    "hash": result["version"] if changed else None,
                    "currentVersion": result["version"], "updatedAt": time.time()}

    def patch(self, rel: str, patches: list[dict[str, Any]], *,
              expect_hash: str | None, base_version: str,
              allow_concurrent: bool = False,
              user_draft: bool = False) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            if user_draft:
                baseline = self._baseline(real, identifier, temp, logical=logical)
                real_snap = self._read_real(real)
                user_temp = self._user_draft_path(identifier)
                if not user_temp.is_file():
                    self._atomic_copy_bytes(user_temp, real.read_bytes())
                u_before = self._read_real(user_temp)
                try:
                    result = patch_text_cas(user_temp, patches, u_before["version"], self.max_bytes)
                except TextFileError as exc:
                    reason = "stale" if exc.status == 409 else "invalid_patch"
                    raise WorkingCopyError(exc.status, str(exc), reason=reason,
                                           **exc.details) from exc
                u_after = self._read_real(user_temp)
                if identifier in self.turns:
                    turn_ctx = self._turn_contexts.setdefault(identifier, {})
                    turn_ctx["userDraftContent"] = u_after["content"]
                    turn_ctx["userDraftHash"] = result["version"]
                ubase_path = self._user_base_real_path(identifier)
                if not ubase_path.is_file() or identifier not in self.turns:
                    self._atomic_copy_bytes(ubase_path, real.read_bytes())
                ubase_snap = self._read_real(ubase_path) if ubase_path.is_file() else baseline
                if ubase_snap["version"] == real_snap["version"]:
                    merged_text, has_conflict = u_after["content"], False
                else:
                    merged_text, has_conflict = _merge3_text(
                        ubase_snap["content"], u_after["content"], real_snap["content"]
                    )
                merged_hash = hashlib.sha256(merged_text.encode("utf-8")).hexdigest()
                changed = (
                    result["version"] != baseline["version"]
                    or real_snap["version"] != baseline["version"]
                    or merged_hash != baseline["version"]
                )
                if not changed and result["version"] == real_snap["version"]:
                    user_temp.unlink(missing_ok=True)
                    composite_ver = real_snap["version"]
                else:
                    composite_ver = hashlib.sha256(
                        f"{real_snap['version']}:{result['version']}:{merged_hash}".encode("utf-8")
                    ).hexdigest()
                return {
                    "path": logical,
                    "state": "pending" if changed else "clean",
                    "hash": result["version"] if changed else None,
                    "currentVersion": composite_ver,
                    "realVersion": real_snap["version"],
                    "mergedHash": merged_hash,
                    "mergedContent": merged_text,
                    "hasConflict": has_conflict,
                    "userDraft": True,
                    "updatedAt": time.time(),
                }

            if not allow_concurrent:
                self._check_not_in_bot_turn(identifier)
            baseline = self._baseline(real, identifier, temp, logical=logical)
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
            self._update_meta(identifier, logical, real, temp, real_sha=result["version"], temp_sha=baseline["version"])
            changed = result["version"] != baseline["version"]
            return {
                "path": logical,
                "state": "pending" if changed else "clean",
                "hash": result["version"] if changed else None,
                "currentVersion": result["version"],
                "updatedAt": time.time(),
            }

    def save(self, rel: str, *, expect_hash: str | None,
             expect_saved_version: str, now_ts: float | None = None) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            # Allow Save (Ctrl+S) even while Lanbot is running so the user is never blocked!
            baseline = self._baseline(real, identifier, temp, logical=logical)
            if expect_saved_version and baseline["version"] != expect_saved_version:
                raise WorkingCopyError(409, "Baseline changed in another browser",
                                       reason="baseline_changed",
                                       currentVersion=baseline["version"])
            user_temp = self._user_draft_path(identifier)
            turn_ctx = self._turn_contexts.get(identifier)
            if user_temp.is_file() or (turn_ctx and turn_ctx.get("userDraftContent") is not None):
                real_snap = self._read_real(real)
                if user_temp.is_file():
                    user_text = self._read_real(user_temp)["content"]
                else:
                    user_text = str(turn_ctx["userDraftContent"])
                ubase_path = self._user_base_real_path(identifier)
                ubase_snap = self._read_real(ubase_path) if ubase_path.is_file() else baseline
                if ubase_snap["version"] == real_snap["version"]:
                    merged_text = user_text
                else:
                    merged_text, _ = _merge3_text(ubase_snap["content"], user_text, real_snap["content"])
                try:
                    save_text_cas(real, merged_text, real_snap["version"], self.max_bytes)
                except Exception:
                    self._atomic_copy_bytes(real, merged_text.encode("utf-8"))
                raw = real.read_bytes()
                ver = hashlib.sha256(raw).hexdigest()
                self._atomic_copy_bytes(temp, raw)
                user_temp.unlink(missing_ok=True)
                self._user_base_real_path(identifier).unlink(missing_ok=True)
                if turn_ctx:
                    turn_ctx.pop("userDraftContent", None)
                    turn_ctx.pop("userDraftHash", None)
                self._record_version_snapshot(identifier, raw, ts=now_ts, is_initial=False)
                self._bot_conflicts.pop(identifier, None)
                self._update_meta(identifier, logical, real, temp, real_sha=ver, temp_sha=ver)
                return {
                    "state": "clean",
                    "version": ver,
                    "bytes": len(raw),
                    "tempPath": str(temp),
                    "mergedContent": merged_text,
                }

            current = self._read_real(real)
            expected = expect_hash or baseline["version"]
            if current["version"] != expected:
                raise WorkingCopyError(409, "Project file changed before Accept",
                                       reason="stale", currentVersion=current["version"])
            raw = real.read_bytes()
            if hashlib.sha256(raw).hexdigest() != current["version"]:
                raise WorkingCopyError(409, "Project file changed during snapshot",
                                       reason="stale")
            self._atomic_copy_bytes(temp, raw)
            self._record_version_snapshot(identifier, raw, ts=now_ts, is_initial=False)
            self._bot_conflicts.pop(identifier, None)
            self._update_meta(identifier, logical, real, temp, real_sha=current["version"], temp_sha=current["version"])
            return {"state": "clean", "version": current["version"],
                    "bytes": len(raw), "tempPath": str(temp)}

    def list_versions(self, rel: str) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            current = self._read_real(real)
            baseline = self._baseline(real, identifier, temp, logical=logical)
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
                    "windowStart": float(item.get("windowStart") or ts),
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
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp, logical=logical)
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
            self._update_meta(identifier, logical, real, temp, real_sha=target_hash, temp_sha=baseline["version"])
            state = self.get(rel)
            return {
                "restoredVersion": target_hash,
                "restoredId": str((target_entry or {}).get("id") or ""),
                **state,
            }

    def accept_partial(self, rel: str, content: str, *,
                       expect_saved_version: str,
                       expect_current_version: str,
                       next_real_content: str | None = None,
                       next_user_content: str | None = None) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp, logical=logical)
            current = self._read_real(real)
            user_temp = self._user_draft_path(identifier)
            if next_real_content is not None or next_user_content is not None:
                if next_real_content is not None:
                    try:
                        save_text_cas(real, next_real_content, current["version"], self.max_bytes)
                        current = self._read_real(real)
                    except TextFileError as exc:
                        raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
                if content is not None:
                    try:
                        b_res = save_text_cas(temp, content, baseline["version"], self.max_bytes)
                    except TextFileError as exc:
                        raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
                    if b_res["version"] != baseline["version"]:
                        self._record_version_snapshot(identifier, temp.read_bytes(), is_initial=False)
                else:
                    b_res = baseline
                ubase_path = self._user_base_real_path(identifier)
                if next_user_content is not None:
                    if self._normalized_text(next_user_content) == self._normalized_text(current["content"]):
                        user_temp.unlink(missing_ok=True)
                        ubase_path.unlink(missing_ok=True)
                    else:
                        if not user_temp.is_file():
                            self._atomic_copy_bytes(user_temp, real.read_bytes())
                        u_cur = self._read_real(user_temp)
                        save_text_cas(user_temp, next_user_content, u_cur["version"], self.max_bytes)
                        self._atomic_copy_bytes(ubase_path, real.read_bytes())
                else:
                    user_temp.unlink(missing_ok=True)
                    ubase_path.unlink(missing_ok=True)
                self._update_meta(identifier, logical, real, temp, real_sha=current["version"], temp_sha=b_res["version"])
                st = self.get(rel)
                return {
                    **st,
                    "state": st["state"],
                    "version": b_res["version"],
                    "currentVersion": st["currentVersion"],
                    "realVersion": current["version"],
                }

            if baseline["version"] != expect_saved_version or (
                current["version"] != expect_current_version and not user_temp.is_file()
            ):
                raise WorkingCopyError(409, "Project file/baseline changed before accepting hunk",
                                       reason="stale")
            try:
                result = save_text_cas(temp, content, expect_saved_version, self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
            self._update_meta(identifier, logical, real, temp, real_sha=current["version"], temp_sha=result["version"])
            return {"state": "clean" if current["version"] == result["version"]
                    else "pending", "version": result["version"],
                    "currentVersion": current["version"]}

    def discard(self, rel: str, *, expect_hash: str | None) -> dict[str, Any]:
        """Explicit Restore All: revert real .md and user_temp to the accepted snapshot via CAS.
        Allowed even during a bot turn so the user is never stuck unable to Undo."""
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            baseline = self._baseline(real, identifier, temp, logical=logical)
            user_temp = self._user_draft_path(identifier)
            had_user_temp = user_temp.is_file()
            u_hash = self._read_real(user_temp)["version"] if had_user_temp else None
            user_temp.unlink(missing_ok=True)
            self._user_base_real_path(identifier).unlink(missing_ok=True)
            turn_ctx = self._turn_contexts.get(identifier)
            if turn_ctx and turn_ctx.get("userDraftContent") is not None:
                turn_ctx.pop("userDraftContent", None)
                turn_ctx.pop("userDraftHash", None)
            self._bot_conflicts.pop(identifier, None)
            current = self._read_real(real)
            if expect_hash and current["version"] != expect_hash and current["version"] != baseline["version"] and expect_hash != u_hash:
                raise WorkingCopyError(409, "Cannot undo newer external file changes",
                                       reason="stale", currentVersion=current["version"])
            try:
                result = save_text_cas(real, baseline["content"],
                                       current["version"], self.max_bytes)
            except TextFileError as exc:
                raise WorkingCopyError(exc.status, str(exc), **exc.details) from exc
            self._update_meta(identifier, logical, real, temp, real_sha=result["version"], temp_sha=baseline["version"])
            return {"ok": True, "path": logical, "state": "clean",
                    "version": result["version"]}

    def begin_turn(self, rel: str, expect_hash: str | None) -> dict[str, Any]:
        logical, real, identifier, temp = self._resolve(rel)
        with self.lock:
            if identifier in self.turns:
                raise WorkingCopyError(409, "LanternBot is already editing this file",
                                       reason="pi_turn")
            baseline = self._baseline(real, identifier, temp, logical=logical)
            current = self._read_real(real)
            user_temp = self._user_draft_path(identifier)
            u_hash = self._read_real(user_temp)["version"] if user_temp.is_file() else None
            if expect_hash and current["version"] != expect_hash and expect_hash != u_hash and expect_hash != baseline["version"]:
                # Allow bot turn to proceed on latest real disk version without blocking
                pass
            self.turns[identifier] = current["version"]
            self._turn_contexts[identifier] = {
                "baseVersion": current["version"],
                "baseContent": current["content"],
                "userDraftContent": None,
                "userDraftHash": None,
            }
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
            turn_ctx = self._turn_contexts.pop(identifier, None) or {}
            after_snap = self._read_real(real)
            after = after_snap["version"]
            bot_touched = bool(before and after != before)
            user_draft = turn_ctx.get("userDraftContent")
            merged_conflict = False
            if user_draft is not None:
                base_text = str(turn_ctx.get("baseContent") or "")
                bot_text = after_snap["content"]
                merged_text, has_conflict = _merge3_text(base_text, str(user_draft), bot_text)
                merged_conflict = has_conflict
                try:
                    res = save_text_cas(real, merged_text, after, self.max_bytes)
                    after = res["version"]
                except Exception:
                    pass
                if has_conflict:
                    self._bot_conflicts[identifier] = {
                        "botContent": bot_text,
                        "botVersion": after_snap["version"],
                        "userContent": str(user_draft),
                        "baseContent": base_text,
                        "timestamp": time.time(),
                    }
                else:
                    self._bot_conflicts.pop(identifier, None)
            self._update_meta(identifier, logical, real, temp, real_sha=after)
            self._write_guard()
            return {
                "path": logical,
                "hash": after,
                "realTouched": bot_touched or (user_draft is not None),
                "conflict": merged_conflict,
            }

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

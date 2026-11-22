
import email.utils
import gzip
import json
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import tarfile
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from lantern.config import (CHUNK_SIZE, MAX_TEXT_PREVIEW, MAX_ZIP_PAYLOAD, normalize_conflict, normalize_recursive_depth, normalize_sort)
from lantern.filesystem import BadRequest
from lantern.md_editor import MarkdownEditorError, read_document as read_markdown_document


MAX_UPLOAD_CHUNK_BYTES = 64 * 1024 * 1024  # 64 MiB per chunk cap
CHUNK_STAGE_TTL_SEC = 24 * 3600
_CHUNK_LOCKS_GUARD = threading.Lock()
_CHUNK_LOCKS: dict[str, threading.Lock] = {}
_CANCEL_LOCKS: dict[str, threading.Lock] = {}
_LAST_CHUNK_SWEEP_AT = 0.0


def _get_chunk_lock(upload_id: str) -> threading.Lock:
    with _CHUNK_LOCKS_GUARD:
        lock = _CHUNK_LOCKS.get(upload_id)
        if lock is None:
            lock = threading.Lock()
            _CHUNK_LOCKS[upload_id] = lock
        return lock


def _drop_chunk_lock(upload_id: str) -> None:
    with _CHUNK_LOCKS_GUARD:
        _CHUNK_LOCKS.pop(upload_id, None)


def _get_cancel_lock(upload_id: str) -> threading.Lock:
    with _CHUNK_LOCKS_GUARD:
        lock = _CANCEL_LOCKS.get(upload_id)
        if lock is None:
            lock = threading.Lock()
            _CANCEL_LOCKS[upload_id] = lock
        return lock


class FilesRoutes:
    def api_list(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("path", [""])[0]
        offset = int(qs.get("offset", ["0"])[0] or 0)
        limit = int(qs.get("limit", [str(self.app.config.page_limit)])[0] or self.app.config.page_limit)
        sort_mode = normalize_sort(qs.get("sort", [self.app.config.default_sort])[0])
        q = qs.get("q", [""])[0]
        recursive_depth_raw = qs.get("recursive_depth", ["0"])[0]
        recursive_depth = normalize_recursive_depth(recursive_depth_raw)
        folders_first_raw = qs.get("folders_first", ["true" if self.app.config.folders_first else "false"])[0]
        folders_first = str(folders_first_raw).lower() not in {"0", "false", "no", "off"}
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_dir():
            self.send_json(404, {"error": "not a folder"}); return
        sh_raw = qs.get("show_hidden", [None])[0]
        ss_raw = qs.get("show_system", [None])[0]
        show_hidden = None if sh_raw is None else (str(sh_raw).lower() in {"1", "true", "yes", "on"})
        show_system = show_hidden if ss_raw is None else (str(ss_raw).lower() in {"1", "true", "yes", "on"})
        media_filter = str(qs.get("media_filter", [""])[0] or "").strip().lower()
        if media_filter not in {"", "all", "media", "image", "video"}:
            media_filter = ""
        items, next_offset, has_more, errors, total = self.app.files.list_entries_page(
            target, offset, limit, sort_mode, q, folders_first, recursive_depth,
            show_hidden=show_hidden, show_system=show_system, media_filter=media_filter,
        )
        if offset == 0 and not media_filter:
            rel_norm = target.resolve().relative_to(self.app.config.root.resolve()).as_posix()
            if rel_norm != ".":
                parent = Path(rel_norm).parent.as_posix()
                href = "/" if parent == "." else "/" + self.app.files.quote_path(parent) + "/"
                items.insert(0, {"special": "back", "href": href})
        payload = {"items": items, "nextOffset": next_offset, "hasMore": has_more, "errors": errors, "total": total, "sort": sort_mode, "folders_first": folders_first, "recursive_depth": recursive_depth_raw if q.strip() else "0"}
        if media_filter:
            payload["media_filter"] = media_filter
        self.send_json(200, payload)


    def api_tree(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("path", qs.get("p", [""]))[0]
        ancestors = str(qs.get("ancestors", ["0"])[0]).lower() in {"1", "true", "yes"}
        try:
            max_children = max(50, min(int(qs.get("limit", ["500"])[0] or 500), 2000))
        except Exception:
            max_children = 500
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_dir():
            self.send_json(404, {"error": "not a folder"}); return
        sh_raw = qs.get("show_hidden", [None])[0]
        ss_raw = qs.get("show_system", [None])[0]
        show_hidden = None if sh_raw is None else (str(sh_raw).lower() in {"1", "true", "yes", "on"})
        show_system = show_hidden if ss_raw is None else (str(ss_raw).lower() in {"1", "true", "yes", "on"})
        if ancestors:
            payload = self.app.files.list_tree_with_ancestors(target, max_children=max_children, show_hidden=show_hidden, show_system=show_system)
        else:
            payload = self.app.files.list_tree_children(target, max_children=max_children, show_hidden=show_hidden, show_system=show_system)
        self.send_json(200, payload)

    def api_properties(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", qs.get("path", [""]))[0]
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.exists():
            self.send_json(404, {"error": "not found"}); return
        self.send_json(200, self.app.files.get_item_properties(target))

    def resolve_upload_target(self, base_rel: str, name: str) -> Path:
        """Use identical path validation for lightweight preflight and upload."""
        if not name:
            raise BadRequest("missing name")
        # Query fields are already decoded by parse_qs. Encode as URL path
        # before safe_join so folders containing #, ? or % survive intact.
        base = self.app.files.safe_join("/" + self.app.files.quote_path(base_rel))
        if base.exists() and not base.is_dir():
            raise BadRequest("upload path is not a folder")
        parts: List[str] = []
        for part in name.replace("\\", "/").split("/"):
            if part and part not in {".", ".."}:
                parts.append(self.app.files.clean_component(part))
        if not parts:
            raise BadRequest("bad filename")
        return self.app.files.ensure_under_root(base.joinpath(*parts))

    def api_upload_check(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        dest = self.resolve_upload_target(qs.get("path", [""])[0], qs.get("name", [""])[0])
        self.send_json(200, {"exists": dest.exists()})

    def api_upload(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        base_rel = qs.get("path", [""])[0]
        name = qs.get("name", [""])[0]
        conflict = normalize_conflict(qs.get("conflict", [self.app.config.upload_conflict])[0])
        total = self.content_length()
        try:
            dest = self.resolve_upload_target(base_rel, name)
        except (BadRequest, PermissionError):
            self.app.files.drain_stream(self.rfile, total)
            raise
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if conflict == "skip":
                self.app.files.drain_stream(self.rfile, total)
                self.send_json(200, {"ok": True, "skipped": True, "file": self.app.files.rel_url_for_path(dest), "reason": "exists"}); return
            if conflict == "ask":
                self.app.files.drain_stream(self.rfile, total)
                self.send_json(409, {"error": "exists", "file": self.app.files.rel_url_for_path(dest)}); return
            # Rename is finalized *after* receiving the complete upload.
            # An exists() / os.replace() pair is not atomic under concurrency.

        tmp: Optional[Path] = None
        written = 0
        remaining = total
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".lantern-uploading-", dir=str(dest.parent))
            tmp = Path(tmp_name)
            with os.fdopen(fd, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            if written != total or remaining != 0:
                raise BadRequest(f"incomplete upload: got {written} of {total} bytes")
            if conflict == "overwrite":
                # Share the image content-version lock with Crop Overwrite.
                # Otherwise a simultaneous ordinary upload could bypass the
                # expected-version check before publishing an image.
                with self.app.crop.lock:
                    os.replace(tmp, dest)
                tmp = None
            else:
                # Atomic no-clobber publication: bytes are complete in a
                # same-directory temp; os.link never replaces an existing name.
                # On an unsupported filesystem, fail closed (not os.replace).
                for index in range(10000 if conflict == "rename" else 1):
                    candidate = dest if index == 0 else dest.with_name(f"{dest.stem} ({index}){dest.suffix}")
                    try:
                        os.link(tmp, candidate)
                    except FileExistsError:
                        if conflict == "skip":
                            self.send_json(200, {"ok": True, "skipped": True,
                                                 "file": self.app.files.rel_url_for_path(dest), "reason": "exists"}); return
                        if conflict == "ask":
                            self.send_json(409, {"error": "exists", "file": self.app.files.rel_url_for_path(dest)}); return
                        continue
                    except OSError as exc:
                        raise BadRequest(f"atomic no-overwrite upload unsupported on this filesystem: {exc}") from exc
                    dest = candidate
                    tmp.unlink()
                    tmp = None
                    break
                else:
                    self.send_json(409, {"error": "all rename candidates exist",
                                         "file": self.app.files.rel_url_for_path(dest)}); return
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        self.send_json(200, {"ok": True, "file": self.app.files.rel_url_for_path(dest), "bytes": written})


    def _cleanup_stale_chunk_stages(self, base: Path) -> None:
        global _LAST_CHUNK_SWEEP_AT
        now = time.time()
        with _CHUNK_LOCKS_GUARD:
            if now - _LAST_CHUNK_SWEEP_AT < 300.0:
                return
            _LAST_CHUNK_SWEEP_AT = now
        cutoff = now - CHUNK_STAGE_TTL_SEC
        for root_dir in (base, (self.app.config.cache_dir / "upload_outcomes").resolve()):
            if not root_dir.is_dir():
                continue
            try:
                for entry in root_dir.iterdir():
                    try:
                        if entry.stat().st_mtime < cutoff:
                            if entry.is_dir():
                                shutil.rmtree(entry, ignore_errors=True)
                            else:
                                entry.unlink(missing_ok=True)
                    except OSError:
                        continue
            except OSError:
                pass

    def _chunk_stage_dir(self, upload_id: str) -> Tuple[str, Path]:
        clean_id = re.sub(r"[^A-Za-z0-9._-]", "", str(upload_id or ""))[:80]
        if len(clean_id) < 6:
            raise BadRequest("invalid upload id")
        base = (self.app.config.cache_dir / "upload_chunks").resolve()
        self._cleanup_stale_chunk_stages(base)
        stage = (base / clean_id).resolve()
        try:
            stage.relative_to(base)
        except ValueError:
            raise BadRequest("invalid upload id")
        return clean_id, stage

    def _outcome_path(self, clean_id: str) -> Path:
        base = (self.app.config.cache_dir / "upload_outcomes").resolve()
        base.mkdir(parents=True, exist_ok=True)
        return (base / f"{clean_id}.json").resolve()

    def _cancel_path(self, clean_id: str) -> Path:
        base = (self.app.config.cache_dir / "upload_outcomes").resolve()
        base.mkdir(parents=True, exist_ok=True)
        return (base / f"{clean_id}.cancel").resolve()

    def _cancel_requested(self, clean_id: str) -> bool:
        with _get_cancel_lock(clean_id):
            return self._cancel_path(clean_id).is_file()

    def _request_cancel(self, clean_id: str) -> None:
        with _get_cancel_lock(clean_id):
            marker = self._cancel_path(clean_id)
            tmp = marker.with_name(f".{clean_id}.{os.getpid()}.{threading.get_ident()}.cancel.tmp")
            try:
                tmp.write_text("cancel", encoding="utf-8")
                os.replace(tmp, marker)
            finally:
                tmp.unlink(missing_ok=True)

    def _clear_cancel(self, clean_id: str) -> None:
        with _get_cancel_lock(clean_id):
            self._cancel_path(clean_id).unlink(missing_ok=True)

    def _record_aborted_upload(self, clean_id: str, stage: Path) -> dict:
        shutil.rmtree(stage, ignore_errors=True)
        record = {
            "state": "aborted-before-publication",
            "published": False,
            "aborted": True,
            "updatedAt": time.time(),
        }
        self._write_upload_outcome(clean_id, record)
        self._clear_cancel(clean_id)
        return record

    def _read_upload_outcome(self, clean_id: str) -> Optional[dict]:
        p = self._outcome_path(clean_id)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_upload_outcome(self, clean_id: str, record: dict) -> None:
        p = self._outcome_path(clean_id)
        tmp = p.with_name(f".{clean_id}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def api_upload_status(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        upload_id = qs.get("id", [""])[0]
        clean_id, stage = self._chunk_stage_dir(upload_id)
        with _get_chunk_lock(clean_id):
            outcome = self._read_upload_outcome(clean_id)
            if outcome:
                self.send_json(200, {"ok": True, "id": clean_id, **outcome})
                return
            if self._cancel_requested(clean_id):
                record = self._record_aborted_upload(clean_id, stage)
                self.send_json(409, {"error": "upload aborted before publication", "code": "aborted", **record})
                return
        self.send_json(200, {
            "ok": True, "id": clean_id,
            "state": "not-published", "published": False, "aborted": False,
        })

    def api_upload_chunk(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        upload_id = qs.get("id", [""])[0]
        try:
            index = int(qs.get("index", ["-1"])[0])
            total_chunks = int(qs.get("total", ["0"])[0])
        except ValueError:
            raise BadRequest("invalid chunk index")
        if index < 0 or total_chunks <= 0 or index >= total_chunks or total_chunks > 10000:
            raise BadRequest("chunk index out of range")
        total = self.content_length()
        if total < 0 or total > MAX_UPLOAD_CHUNK_BYTES:
            raise BadRequest(f"chunk size out of range (max {MAX_UPLOAD_CHUNK_BYTES} bytes)")
        clean_id, stage = self._chunk_stage_dir(upload_id)

        with _get_chunk_lock(clean_id):
            outcome = self._read_upload_outcome(clean_id)
            if outcome and outcome.get("state") in {"aborted-before-publication", "published"}:
                self.send_json(409, {
                    "error": f"upload already {outcome.get('state')}",
                    "code": "aborted" if outcome.get("state") == "aborted-before-publication" else "published",
                    "state": outcome.get("state"),
                    "published": bool(outcome.get("published")),
                })
                return
            if self._cancel_requested(clean_id):
                record = self._record_aborted_upload(clean_id, stage)
                self.send_json(409, {"error": "upload aborted before publication", "code": "aborted", **record})
                return
            stage.mkdir(parents=True, exist_ok=True)
            if not outcome:
                self._write_upload_outcome(clean_id, {
                    "state": "not-published", "published": False, "aborted": False, "updatedAt": time.time(),
                })

        part_path = stage / f"part-{index:06d}"
        tmp: Optional[Path] = None
        written = 0
        remaining = total
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=f".chunk-{index:06d}-", dir=str(stage))
            tmp = Path(tmp_name)
            with os.fdopen(fd, "wb") as out:
                while remaining > 0:
                    buf = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not buf:
                        break
                    out.write(buf)
                    written += len(buf)
                    remaining -= len(buf)
            if written != total or remaining != 0:
                raise BadRequest("incomplete chunk body")
            with _get_chunk_lock(clean_id):
                outcome = self._read_upload_outcome(clean_id)
                if (outcome and outcome.get("state") in {"aborted-before-publication", "published"}) or not stage.is_dir():
                    self.send_json(409, {
                        "error": "upload aborted or completed",
                        "code": "aborted",
                        "state": (outcome or {}).get("state", "aborted-before-publication"),
                        "published": bool((outcome or {}).get("published")),
                    })
                    return
                if self._cancel_requested(clean_id):
                    record = self._record_aborted_upload(clean_id, stage)
                    self.send_json(409, {"error": "upload aborted before publication", "code": "aborted", **record})
                    return
                os.replace(tmp, part_path)
                tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
        self.send_json(200, {"ok": True, "id": clean_id, "index": index, "written": written, "state": "not-published"})

    def api_upload_complete(self) -> None:
        data = self.read_json()
        upload_id = str(data.get("id") or "")
        base_rel = str(data.get("path") or "")
        name = str(data.get("name") or "")
        conflict = normalize_conflict(str(data.get("conflict") or self.app.config.upload_conflict))
        try:
            total_chunks = int(data.get("total") or 0)
        except (TypeError, ValueError):
            raise BadRequest("invalid total chunks")
        if total_chunks <= 0 or total_chunks > 10000:
            raise BadRequest("invalid total chunks")
        clean_id, stage = self._chunk_stage_dir(upload_id)

        dest = self.resolve_upload_target(base_rel, name)
        self.app.files.protect_config_mutation(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with _get_chunk_lock(clean_id):
            outcome = self._read_upload_outcome(clean_id)
            if outcome:
                st = outcome.get("state")
                if st == "published":
                    self.send_json(200, {"ok": True, "id": clean_id, **outcome})
                    return
                if st == "aborted-before-publication":
                    self.send_json(409, {
                        "error": "upload aborted before publication",
                        "code": "aborted",
                        "state": "aborted-before-publication",
                        "published": False,
                        "aborted": True,
                    })
                    return
            if not stage.is_dir():
                self.send_json(409, {
                    "error": "upload session already completed or aborted",
                    "code": "aborted",
                    "state": "aborted-before-publication",
                    "published": False,
                    "aborted": True,
                })
                return
            parts = [stage / f"part-{i:06d}" for i in range(total_chunks)]
            missing = [i for i, p in enumerate(parts) if not p.is_file()]
            if missing:
                raise BadRequest(f"missing chunks: {missing[:5]}")

            self._write_upload_outcome(clean_id, {
                "state": "publishing", "published": False, "aborted": False, "updatedAt": time.time(),
            })

            tmp: Optional[Path] = None
            written = 0
            final_dest = dest
            try:
                fd, tmp_name = tempfile.mkstemp(prefix=".lantern-uploading-", dir=str(dest.parent))
                tmp = Path(tmp_name)
                with os.fdopen(fd, "wb") as out:
                    for p in parts:
                        with open(p, "rb") as src_f:
                            while True:
                                buf = src_f.read(CHUNK_SIZE)
                                if not buf:
                                    break
                                out.write(buf)
                                written += len(buf)
                    out.flush()
                    try:
                        os.fsync(out.fileno())
                    except OSError:
                        pass

                if conflict == "overwrite":
                    # Serialize explicit overwrite with image content-version/CAS lock.
                    cancelled = False
                    with self.app.crop.lock:
                        with _get_cancel_lock(clean_id):
                            cancelled = self._cancel_path(clean_id).is_file()
                            if not cancelled:
                                os.replace(tmp, dest)
                    if cancelled:
                        record = self._record_aborted_upload(clean_id, stage)
                        self.send_json(409, {"error": "upload aborted before publication", "code": "aborted", **record})
                        return
                    final_dest = dest
                    tmp = None
                else:
                    # Atomic no-clobber publication via os.link (never replaces an existing path).
                    for index in range(10000 if conflict == "rename" else 1):
                        candidate = dest if index == 0 else dest.with_name(f"{dest.stem} ({index}){dest.suffix}")
                        cancelled = False
                        try:
                            with _get_cancel_lock(clean_id):
                                cancelled = self._cancel_path(clean_id).is_file()
                                if not cancelled:
                                    os.link(tmp, candidate)
                            if cancelled:
                                record = self._record_aborted_upload(clean_id, stage)
                                self.send_json(409, {"error": "upload aborted before publication", "code": "aborted", **record})
                                return
                        except FileExistsError:
                            if conflict == "skip":
                                record = {
                                    "state": "published",
                                    "published": True,
                                    "aborted": False,
                                    "skipped": True,
                                    "file": self.app.files.rel_url_for_path(dest),
                                    "reason": "exists",
                                    "updatedAt": time.time(),
                                }
                                self._write_upload_outcome(clean_id, record)
                                shutil.rmtree(stage, ignore_errors=True)
                                self.send_json(200, {"ok": True, "id": clean_id, **record})
                                return
                            if conflict == "ask":
                                self._write_upload_outcome(clean_id, {
                                    "state": "not-published", "published": False, "aborted": False, "updatedAt": time.time(),
                                })
                                self.send_json(409, {
                                    "error": "exists",
                                    "file": self.app.files.rel_url_for_path(dest),
                                    "state": "not-published",
                                })
                                return
                            continue
                        except OSError as exc:
                            self._write_upload_outcome(clean_id, {
                                "state": "failed", "published": False, "aborted": False,
                                "error": str(exc), "updatedAt": time.time(),
                            })
                            raise BadRequest(f"atomic no-overwrite upload unsupported on this filesystem: {exc}") from exc
                        final_dest = candidate
                        tmp.unlink()
                        tmp = None
                        break
                    else:
                        self._write_upload_outcome(clean_id, {
                            "state": "failed", "published": False, "aborted": False,
                            "error": "all rename candidates exist", "updatedAt": time.time(),
                        })
                        self.send_json(409, {
                            "error": "all rename candidates exist",
                            "file": self.app.files.rel_url_for_path(dest),
                            "state": "failed",
                        })
                        return
            except Exception as exc:
                if not isinstance(exc, BadRequest):
                    self._write_upload_outcome(clean_id, {
                        "state": "failed", "published": False, "aborted": False,
                        "error": str(exc), "updatedAt": time.time(),
                    })
                raise
            finally:
                if tmp is not None:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass

            # Persist durable terminal published state BEFORE removing stage or returning.
            record = {
                "state": "published",
                "published": True,
                "aborted": False,
                "file": self.app.files.rel_url_for_path(final_dest),
                "size": written,
                "bytes": written,
                "updatedAt": time.time(),
            }
            self._clear_cancel(clean_id)
            self._write_upload_outcome(clean_id, record)
            shutil.rmtree(stage, ignore_errors=True)
        self.send_json(200, {"ok": True, "id": clean_id, **record})

    def api_upload_abort(self) -> None:
        data = self.read_json()
        upload_id = str(data.get("id") or "")
        if not upload_id:
            self.send_json(200, {"ok": True, "state": "aborted-before-publication", "aborted": True, "published": False})
            return
        try:
            clean_id, stage = self._chunk_stage_dir(upload_id)
        except BadRequest:
            self.send_json(200, {"ok": True, "state": "aborted-before-publication", "aborted": True, "published": False})
            return
        # Publish the cancellation intent before waiting for the completion
        # transaction.  Completion observes this marker at its final
        # pre-publication gate, including while waiting on the crop lock.
        self._request_cancel(clean_id)
        with _get_chunk_lock(clean_id):
            outcome = self._read_upload_outcome(clean_id)
            if outcome and outcome.get("state") == "published":
                # Publication already committed; NEVER report aborted or delete the file.
                self._clear_cancel(clean_id)
                self.send_json(200, {"ok": True, "id": clean_id, **outcome})
                return
            record = self._record_aborted_upload(clean_id, stage)
        self.send_json(200, {"ok": True, "id": clean_id, **record})

    def api_save(self) -> None:
        data = self.read_json()
        rel = str(data.get("path", ""))
        content = str(data.get("content", ""))
        target = self.app.files.safe_join("/" + self.app.files.quote_path(str(rel)))
        if not target.is_file():
            self.send_json(404, {"error": "file not found"}); return
        if self.app.files.classify(target) != "text":
            self.send_json(400, {"error": "not a text file"}); return
        tmp = target.with_name(target.name + f".save-{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, target)
        self.send_json(200, {"ok": True})

    def api_mkdir(self) -> None:
        data = self.read_json()
        base = self.app.files.safe_join("/" + self.app.files.quote_path(str(data.get("path", ""))))
        name = self.app.files.clean_component(str(data.get("name", "")))
        dest = (base / name).resolve()
        dest.relative_to(self.app.config.root.resolve())
        dest.mkdir(parents=True, exist_ok=False)
        self.send_json(200, {"ok": True, "path": self.app.files.rel_url_for_path(dest)})

    def api_newfile(self) -> None:
        data = self.read_json()
        base = self.app.files.safe_join("/" + self.app.files.quote_path(str(data.get("path", ""))))
        name = self.app.files.clean_component(str(data.get("name", "")))
        dest = (base / name).resolve()
        dest.relative_to(self.app.config.root.resolve())
        if dest.exists():
            self.send_json(409, {"error": "file already exists"}); return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("", encoding="utf-8")
        self.send_json(200, {"ok": True, "edit_url": self.app.files.rel_url_for_path(dest) + "?edit=1"})

    def api_rename(self) -> None:
        data = self.read_json()
        target = self.app.files.safe_join("/" + self.app.files.quote_path(str(data.get("path", ""))))
        name = self.app.files.clean_component(str(data.get("name", "")))
        if not target.exists():
            self.send_json(404, {"error": "not found"}); return
        dest = self.app.files.ensure_under_root(target.parent / name)
        self.app.files.protect_config_mutation(target)
        if dest.exists():
            self.send_json(409, {"error": "target exists"}); return
        old_rel = self.app.files.rel_url_for_path(target).lstrip("/")
        target.rename(dest)
        new_rel = self.app.files.rel_url_for_path(dest).lstrip("/")
        if getattr(self.app, "work", None) is not None:
            try:
                self.app.work.notify_moved(old_rel, new_rel)
            except Exception:
                pass
        self.send_json(200, {"ok": True, "path": self.app.files.rel_url_for_path(dest)})

    def api_copy(self) -> None:
        data = self.read_json()
        dest_dir = self.app.files.resolve_destination_dir(data, current_path if (current_path := str(data.get("dest", data.get("dest_dir", "")))) is not None else "")
        conflict = normalize_conflict(data.get("conflict", "rename"))
        copied = []
        skipped = 0
        for rel in self.app.files.payload_paths(data):
            src = self.app.files.resolve_existing(rel)
            result = self.app.files.copy_item(src, dest_dir, conflict=conflict)
            if result is None:
                skipped += 1
            else:
                copied.append(self.app.files.rel_url_for_path(result).lstrip("/"))
        self.send_json(200, {"ok": True, "copied": copied, "skipped": skipped})

    def api_move(self) -> None:
        data = self.read_json()
        dest_dir = self.app.files.resolve_destination_dir(data)
        conflict = normalize_conflict(data.get("conflict", "rename"))
        moved = []
        skipped = 0
        for rel in self.app.files.payload_paths(data):
            src = self.app.files.resolve_existing(rel)
            if src.resolve() == self.app.config.root.resolve():
                raise BadRequest("cannot move root")
            self.app.files.protect_config_mutation(src)
            old_rel = self.app.files.rel_url_for_path(src).lstrip("/")
            result = self.app.files.move_item(src, dest_dir, conflict=conflict)
            if result is None:
                skipped += 1
            else:
                new_rel = self.app.files.rel_url_for_path(result).lstrip("/")
                if getattr(self.app, "work", None) is not None:
                    try:
                        self.app.work.notify_moved(old_rel, new_rel)
                    except Exception:
                        pass
                moved.append(new_rel)
        self.send_json(200, {"ok": True, "moved": moved, "skipped": skipped})

    def api_duplicate(self) -> None:
        data = self.read_json()
        conflict = normalize_conflict(data.get("conflict", "rename"))
        duplicated = []
        skipped = 0
        for rel in self.app.files.payload_paths(data):
            src = self.app.files.resolve_existing(rel)
            if src.resolve() == self.app.config.root.resolve():
                raise BadRequest("cannot duplicate root")
            result = self.app.files.copy_item(src, src.parent, name=self.app.files.duplicate_name(src), conflict=conflict)
            if result is None:
                skipped += 1
            else:
                duplicated.append(self.app.files.rel_url_for_path(result).lstrip("/"))
        self.send_json(200, {"ok": True, "duplicated": duplicated, "skipped": skipped})

    def api_batch_rename(self) -> None:
        data = self.read_json()
        items = data.get("items")
        if not isinstance(items, list) or not items:
            raise BadRequest("items must be a non-empty list")
        planned: List[Tuple[Path, Path]] = []
        seen: set[Path] = set()
        for item in items:
            if not isinstance(item, dict):
                raise BadRequest("each batch rename item must be an object")
            src = self.app.files.resolve_existing(str(item.get("path", "")))
            if src.resolve() == self.app.config.root.resolve():
                raise BadRequest("cannot rename root")
            name = self.app.files.clean_component(str(item.get("name", "")))
            dest = self.app.files.ensure_under_root(src.parent / name)
            if src.resolve() == dest.resolve():
                continue
            if dest in seen:
                raise BadRequest(f"duplicate target in batch: {name}")
            if dest.exists():
                raise BadRequest(f"target exists: {name}")
            self.app.files.protect_config_mutation(src)
            planned.append((src, dest))
            seen.add(dest)
        renamed = []
        for src, dest in planned:
            old_rel = self.app.files.rel_url_for_path(src).lstrip("/")
            src.rename(dest)
            new_rel = self.app.files.rel_url_for_path(dest).lstrip("/")
            if getattr(self.app, "work", None) is not None:
                try:
                    self.app.work.notify_moved(old_rel, new_rel)
                except Exception:
                    pass
            renamed.append({"from": old_rel, "to": new_rel})
        self.send_json(200, {"ok": True, "renamed": renamed})

    def api_extract(self) -> None:
        data = self.read_json()
        archive = self.app.files.resolve_existing(str(data.get("path", "")))
        if not archive.is_file():
            raise BadRequest("archive path must be a file")
        dest = self.app.files.resolve_destination_dir(data, archive.parent.resolve().relative_to(self.app.config.root.resolve()).as_posix())
        conflict = normalize_conflict(data.get("conflict", "rename"))
        result = self.app.files.extract_archive(archive, dest, conflict)
        result["dest"] = self.app.files.rel_url_for_path(dest).lstrip("/")
        self.send_json(200, result)

    def api_archive(self) -> None:
        payload = self.app.files.parse_archive_payload(self)
        md_rel = str(payload.get("mdPath") or "").strip() if isinstance(payload, dict) else ""
        if md_rel:
            md_target = self.app.files.resolve_existing(md_rel)
            if not md_target.is_file():
                raise BadRequest("Markdown path must be an existing file")
            md_dir = md_target.parent.resolve()
            stem = md_target.stem
            default_zip = self.app.files.ensure_under_root(md_dir / f"{stem}.zip")
            conflict_mode = str(payload.get("conflict") or "ask").strip().lower()
            if default_zip.exists() and conflict_mode == "ask":
                ts = int(time.time())
                self.send_json(200, {
                    "ok": False,
                    "conflict": True,
                    "existingName": default_zip.name,
                    "copyName": f"{stem}_{ts}.zip",
                })
                return
            if default_zip.exists() and conflict_mode == "copy":
                ts = int(time.time())
                dest_zip = self.app.files.ensure_under_root(md_dir / f"{stem}_{ts}.zip")
                idx = 1
                while dest_zip.exists():
                    dest_zip = self.app.files.ensure_under_root(md_dir / f"{stem}_{ts}_{idx}.zip")
                    idx += 1
            else:
                dest_zip = default_zip

            arch_paths: List[Path] = [md_target]
            for sub_name in ("assets", f"{stem}_assets", f"{stem}.assets", "images", "img", "media"):
                sub_dir = (md_dir / sub_name).resolve()
                if sub_dir.is_dir():
                    arch_paths.append(sub_dir)
            if hasattr(self, "_compute_md_image_audit"):
                try:
                    audit = self._compute_md_image_audit(md_target)
                    for ref_rel in (audit.get("valid") or []):
                        cand = (md_dir / str(ref_rel).lstrip("/")).resolve()
                        if cand.is_file() and not any(cand == p.resolve() or p.resolve() in cand.parents for p in arch_paths):
                            arch_paths.append(cand)
                except Exception:
                    pass

            tmp_zip = dest_zip.with_name(f".{dest_zip.name}.{os.getpid()}.tmp")
            written_count = 0
            try:
                with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
                    for p_entry, arc in self.app.files.iter_archive_entries(arch_paths):
                        try:
                            if p_entry.resolve() in {dest_zip.resolve(), tmp_zip.resolve()}:
                                continue
                            if p_entry.is_dir():
                                zf.writestr(arc.rstrip("/") + "/", b"")
                            else:
                                zf.write(p_entry, arc)
                                written_count += 1
                        except Exception:
                            pass
                os.replace(tmp_zip, dest_zip)
            finally:
                if tmp_zip.exists():
                    try:
                        tmp_zip.unlink()
                    except OSError:
                        pass
            self.send_json(200, {
                "ok": True,
                "conflict": False,
                "name": dest_zip.name,
                "path": self.app.files.rel_url_for_path(dest_zip).lstrip("/"),
                "filesCount": written_count,
            })
            return
        rels = self.app.files.payload_paths(payload)
        paths = [self.app.files.resolve_existing(rel) for rel in rels]
        fmt = str(payload.get("format", "zip")).lower()
        compression = str(payload.get("compression", "compress")).lower()
        if compression not in {"store", "compress"}:
            raise BadRequest("compression must be store or compress")
        filename, ctype, mode = self.app.files.archive_response_meta(fmt, compression)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if mode == "zip":
            zip_compression = zipfile.ZIP_STORED if compression == "store" else zipfile.ZIP_DEFLATED
            with zipfile.ZipFile(self.wfile, "w", compression=zip_compression, compresslevel=(0 if compression == "store" else 3)) as zf:
                for path, arc in self.app.files.iter_archive_entries(paths):
                    try:
                        if path.is_dir():
                            zf.writestr(arc.rstrip("/") + "/", b"")
                        else:
                            zf.write(path, arc)
                    except Exception:
                        pass
        else:
            with tarfile.open(fileobj=self.wfile, mode=mode) as tf:
                for path, arc in self.app.files.iter_archive_entries(paths):
                    try:
                        tf.add(path, arcname=arc, recursive=False)
                    except Exception:
                        pass

    def api_delete(self) -> None:
        data = self.read_json()
        paths = data.get("paths") or []
        deleted = 0
        for rel in paths:
            target = self.app.files.safe_join("/" + self.app.files.quote_path(str(rel)))
            if target.resolve() == self.app.config.root.resolve():
                continue
            self.app.files.protect_config_mutation(target)
            rel_del = self.app.files.rel_url_for_path(target).lstrip("/")
            if target.is_dir():
                shutil.rmtree(target)
                deleted += 1
                if getattr(self.app, "work", None) is not None:
                    try:
                        self.app.work.notify_deleted(rel_del)
                    except Exception:
                        pass
            elif target.exists():
                target.unlink()
                deleted += 1
                if getattr(self.app, "work", None) is not None:
                    try:
                        self.app.work.notify_deleted(rel_del)
                    except Exception:
                        pass
        self.send_json(200, {"ok": True, "deleted": deleted})

    def api_zip(self) -> None:
        # Accept form because browser download from fetch is more awkward; JSON fallback too.
        n = self.content_length(max_bytes=MAX_ZIP_PAYLOAD)
        raw = self.read_body_exact(n) if n else b""
        payload = {}
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            payload = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        else:
            form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
            payload = json.loads(form.get("payload", ["{}"])[0])
        paths = payload.get("paths") or []
        filename = f"lan-drive-{int(time.time())}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        # ZipFile needs seekable output for central directory? It can write to unseekable in py3.5+ via data descriptors.
        with zipfile.ZipFile(self.wfile, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
            for rel in paths:
                target = self.app.files.safe_join("/" + self.app.files.quote_path(str(rel)))
                if not target.exists():
                    continue
                if target.is_dir():
                    base = target.parent
                    for root, dirs, files in os.walk(target):
                        dirs[:] = [d for d in dirs if not self.app.files.should_hide_entry(Path(root), d)]
                        for fn in files:
                            if self.app.files.should_hide_entry(Path(root), fn):
                                continue
                            p = Path(root) / fn
                            try:
                                arc = p.relative_to(base).as_posix()
                                zf.write(p, arc)
                            except Exception:
                                pass
                else:
                    zf.write(target, target.name)

    def serve_directory(self, path: Path) -> None:
        rel = path.resolve().relative_to(self.app.config.root.resolve()).as_posix()
        if rel == ".": rel = ""
        esc_title = self.app.files.html_escape(self.app.config.title)
        esc_root = self.app.files.html_escape(str(self.app.config.root))
        esc_rel = self.app.files.html_escape(rel)
        body = f"""
<div class="app explorer-app">
  <header class="top" id="topHeader">
    <div class="top-inner">
      <div class="brand">
        <button id="treeToggleBtn" class="btn icon-only" onclick="toggleTreePane()" title="Toggle folder tree (Ctrl+B)" aria-label="Toggle folder tree" aria-expanded="false" aria-controls="treePane">☰</button>
        <div class="logo" aria-hidden="true">LD</div>
        <div class="brand-meta"><div class="brand-title">{esc_title}</div><div class="brand-sub" title="{esc_root}">{esc_root}</div></div>
      </div>
      <div class="nav-cluster" role="group" aria-label="Folder history">
        <button id="navBackBtn" class="btn icon-only" onclick="navHistoryBack()" title="Back (Alt+Left)" aria-label="Back" disabled>←</button>
        <button id="navFwdBtn" class="btn icon-only" onclick="navHistoryForward()" title="Forward (Alt+Right)" aria-label="Forward" disabled>→</button>
        <button id="navUpBtn" class="btn icon-only" onclick="navParentFolder()" title="Parent folder (Alt+Up)" aria-label="Up">↑</button>
      </div>
      <div class="address-wrap" id="addressWrap" title="Click empty area or press Ctrl+L to type a path">
        <nav class="crumbs" id="crumbsBar" aria-label="Breadcrumb">{self.app.views.breadcrumb(rel)}</nav>
        <input id="addressInput" class="address-input hidden" type="text" spellcheck="false" autocomplete="off" placeholder="Enter path, e.g. Photos/2026" aria-label="Folder path">
      </div>
      <div class="search" id="searchCluster" role="search">
        <select id="recursiveDepth" class="search-depth" onchange="changeRecursiveDepth(this)" title="Search scope" aria-label="Search scope">
          <option value="0" data-i18n="scopeHere">Here</option>
          <option value="all" data-i18n="scopeAll">All</option>
          <option value="1">1 lvl</option>
          <option value="2">2 lvl</option>
          <option value="3">3 lvl</option>
        </select>
        <input id="q" type="search" placeholder="Search files... (Ctrl+F)" aria-label="Search files">
        <button id="searchClearBtn" class="btn ghost icon-only hidden" onclick="clearSearchInput()" title="Clear search" aria-label="Clear search">✕</button>
      </div>
      <div class="actions">
        <button id="mobileSearchBtn" class="btn icon-only mobile-only" onclick="toggleMobileSearch()" title="Search files" aria-label="Search" aria-expanded="false" aria-controls="mobileSearchBar">🔍</button>
        <button class="btn primary" onclick="openUploadDialog()" title="Upload files or folders" aria-label="Upload">⬆️ <span class="label" data-i18n="upload">Upload</span></button>
        <button class="btn desktop-only" onclick="mkdir()" title="Create new folder" aria-label="New folder">➕ <span class="label" data-i18n="newFolder">New</span></button>
        <button id="optionsBtn" class="btn" onclick="toggleOptionsMenu(event)" title="View, sort &amp; settings" aria-label="Options" aria-haspopup="dialog" aria-expanded="false" aria-controls="optionsMenu">⚙ <span class="label" data-i18n="options">Options</span></button>
        <button class="btn terminal-btn desktop-only" onclick="toggleTerminal()" title="Open Terminal &amp; Git" aria-label="Terminal">⌨️ <span class="label">Terminal</span></button>
      </div>
    </div>
    <div id="mobileSearchBar" class="mobile-search-bar hidden" role="search" aria-label="Mobile file search">
      <select id="mobileRecursiveDepth" class="search-depth" onchange="changeRecursiveDepth(this)" aria-label="Search depth">
        <option value="0" data-i18n="scopeHere">Here</option><option value="all" data-i18n="scopeAll">All</option><option value="1">1 lvl</option><option value="2">2 lvl</option>
      </select>
      <input id="mobileQ" type="search" placeholder="Search files..." aria-label="Search files">
      <button class="btn icon-only ghost" onclick="clearSearchInput(); toggleMobileSearch(false)" aria-label="Close search">✕</button>
    </div>
    <div class="toolbar" id="subToolbar">
      <div class="mode-toggle" role="group" aria-label="Workspace mode">
        <button data-mode="explorer" class="active" aria-pressed="true" onclick="setAppMode('explorer')" data-i18n="modeExplorer">Explorer</button>
        <button data-mode="gallery" aria-pressed="false" onclick="setAppMode('gallery')" data-i18n="modeGallery">Gallery</button>
      </div>
      <div class="view-toggle desktop-only" role="group" aria-label="View layout">
        <button data-view="large" onclick="setView('large')" title="Large thumbnails">Large</button>
        <button data-view="grid" onclick="setView('grid')" title="Standard grid">Grid</button>
        <button data-view="list" onclick="setView('list')" title="Compact list">List</button>
        <button data-view="details" onclick="setView('details')" title="Detailed table">Details</button>
      </div>
      <div id="galleryFilterBar" class="gallery-filters hidden" role="group" aria-label="Media filter">
        <button data-media="all" class="active" aria-pressed="true" onclick="setMediaFilter('all')" data-i18n="filterAll">All</button>
        <button data-media="image" aria-pressed="false" onclick="setMediaFilter('image')" data-i18n="filterPhotos">Photos</button>
        <button data-media="video" aria-pressed="false" onclick="setMediaFilter('video')" data-i18n="filterVideos">Videos</button>
      </div>
      <select id="sortSelect" class="select desktop-only" onchange="changeSort(this)" title="Sort items" aria-label="Sort items">
        <option value="name-asc">Name A→Z</option>
        <option value="name-desc">Name Z→A</option>
        <option value="mtime-desc">Newest</option>
        <option value="mtime-asc">Oldest</option>
        <option value="size-desc">Largest</option>
        <option value="size-asc">Smallest</option>
        <option value="type-asc">Type A→Z</option>
        <option value="ext-asc">Extension A→Z</option>
      </select>
      <button id="previewPaneBtn" class="btn small desktop-only" onclick="togglePreviewPane()" title="Toggle side preview pane" aria-pressed="false">👁 <span class="label" data-i18n="preview">Preview</span></button>
      <button class="btn small icon-only desktop-only" onclick="refreshFolder()" title="Refresh folder (F5)" aria-label="↻ Refresh">↻</button>
      <span id="selCount" class="sub desktop-only"></span>
      <div class="grow"></div>
      <button id="pasteBtn" class="btn small primary hidden" onclick="pasteClipboard()" title="Paste here (Ctrl+V)">📋 <span data-i18n="paste">Paste</span></button>
    </div>
    <div id="selectionBar" class="selection-bar hidden" role="toolbar" aria-label="Selection actions">
      <span id="mobileSelCount" class="mobile-sel-count mobile-only"></span>
      <button class="btn small desktop-only" onclick="selectVisible()" title="Select all (Ctrl+A)" data-i18n="selectAll">Select all</button>
      <button class="btn small ghost desktop-only" onclick="clearSel()" data-i18n="clearSel">Clear</button>
      <button id="previewBtn" class="btn small desktop-only hidden" onclick="previewSelected()">👁 <span data-i18n="open">Open</span></button>
      <button id="downloadBtn" class="btn small hidden" onclick="downloadSelected()">⬇️ <span data-i18n="download">Download</span></button>
      <button id="copyBtn" class="btn small desktop-only hidden" onclick="copySel()" title="Copy (Ctrl+C)">📋 <span data-i18n="copy">Copy</span></button>
      <button id="moveBtn" class="btn small desktop-only hidden" onclick="moveSel()" title="Move">➡️ <span data-i18n="move">Move</span></button>
      <button id="renameBtn" class="btn small warn desktop-only hidden" onclick="renameOne()" title="Rename (F2)">✏️ <span data-i18n="rename">Rename</span></button>
      <button id="duplicateBtn" class="btn small desktop-only hidden" onclick="duplicateSel()">⧉ <span data-i18n="duplicate">Duplicate</span></button>
      <button id="batchRenameBtn" class="btn small desktop-only hidden" onclick="batchRenameSel()">🔤 <span data-i18n="batchRename">Batch</span></button>
      <button id="archiveBtn" class="btn small desktop-only hidden" onclick="archiveSelected()">🗜 Zip</button>
      <button id="extractBtn" class="btn small desktop-only hidden" onclick="extractSelected()">📦 <span data-i18n="extract">Extract</span></button>
      <button id="shareBtn" class="btn small desktop-only hidden" onclick="shareOne()">🔗 Link</button>
      <button id="mobileMoreActBtn" class="btn small mobile-only" onclick="openMobileSelectionMenu(event)" aria-haspopup="menu" aria-expanded="false" aria-controls="ctxMenu">⋯ <span data-i18n="more">More</span></button>
      <button id="deleteBtn" class="btn small danger desktop-only hidden" onclick="deleteSel()" title="Delete (Del)">🗑️ <span data-i18n="delete">Delete</span></button>
    </div>
  </header>

  <div id="optionsMenu" class="options-menu hidden" role="dialog" aria-labelledby="optionsMenuTitle" onclick="event.stopPropagation()">
    <div class="opt-head">
      <span id="optionsMenuTitle" class="opt-title" data-i18n="optionsTitle">View &amp; Explorer Options</span>
      <button id="optionsCloseBtn" class="btn small icon-only ghost" onclick="closeOptionsMenu(true)" aria-label="Close options">✕</button>
    </div>
    <div class="opt-row">
      <span data-i18n="optViewLayout">Layout</span>
      <div class="view-toggle" role="group" aria-label="View layout">
        <button data-view="large" onclick="setView('large')">Large</button>
        <button data-view="grid" onclick="setView('grid')">Grid</button>
        <button data-view="list" onclick="setView('list')">List</button>
        <button data-view="details" onclick="setView('details')">Details</button>
      </div>
    </div>
    <label class="opt-row"><span data-i18n="optSort">Sort by</span><select id="optSortSelect" class="select compact" onchange="changeSort(this)"><option value="name-asc">Name A→Z</option><option value="name-desc">Name Z→A</option><option value="mtime-desc">Newest</option><option value="mtime-asc">Oldest</option><option value="size-desc">Largest</option><option value="size-asc">Smallest</option></select></label>
    <label class="opt-row"><span data-i18n="optFoldersFirst">Folders before files</span><input id="foldersFirst" type="checkbox" onchange="changeFoldersFirst(this)"></label>
    <label class="opt-row"><span data-i18n="optShowHidden">Show hidden &amp; system (this tab)</span><input id="showHiddenToggle" type="checkbox" onchange="toggleShowHidden(this)"></label>
    <label class="opt-row"><span data-i18n="optFolderMosaic">Folder 2×2 preview mosaic</span><input id="folderPreviewToggle" type="checkbox" onchange="toggleFolderPreview(this)"></label>
    <label class="opt-row"><span data-i18n="optThumbFit">Thumbnail framing</span><select id="thumbFit" class="select compact" onchange="changeThumbFit(this)"><option value="contain">Fit (Full)</option><option value="cover">Crop (Fill)</option></select></label>
    <label class="opt-row"><span data-i18n="optPreviewAnim">Mosaic animation</span><select id="previewAnim" class="select compact" onchange="changePreviewAnimation(this)"><option value="none">None</option><option value="fade">Fade</option><option value="flip">Flip</option><option value="slide">Slide</option></select></label>
    <label class="opt-row"><span data-i18n="optPageLimit">Items per page</span><select id="limitSelect" class="select compact" onchange="changeLimit(this)"><option value="100">100</option><option value="220">220</option><option value="500">500</option><option value="1000">1000</option></select></label>
    <label class="opt-row"><span data-i18n="optLanguage">Language</span><select id="langSelect" class="select compact" onchange="setLanguage(this.value)"><option value="en">English</option><option value="vi">Tiếng Việt</option></select></label>
    <div class="opt-actions">
      <button class="btn small" onclick="mkdir(); closeOptionsMenu()">➕ <span data-i18n="newFolder">New Folder</span></button>
      <button class="btn small" onclick="newFile(); closeOptionsMenu()">📝 <span data-i18n="newFile">New File</span></button>
      <button class="btn small" onclick="togglePreviewPane(); closeOptionsMenu()">👁 <span data-i18n="preview">Preview</span></button>
      <button class="btn small" onclick="toggleTerminal(); closeOptionsMenu()">⌨️ Terminal</button>
      <button class="btn small" onclick="addPreviewExtension(); closeOptionsMenu()">＋ Ext</button>
    </div>
  </div>

  <div id="treeBackdrop" class="tree-backdrop hidden" onclick="closeMobileTree(true)" aria-hidden="true"></div>

  <main class="main explorer-shell" id="explorerShell">
    <aside id="treePane" class="tree-pane" aria-label="Folder navigation">
      <div class="tree-head">
        <span id="treeHeadTitle" class="tree-head-title" data-i18n="folders">Folders</span>
        <div class="tree-head-actions">
          <button class="btn small icon-only ghost" onclick="window.LanternTree?.refresh()" title="Refresh folder tree" aria-label="Refresh folder tree">↻</button>
          <button class="btn small icon-only ghost" onclick="window.LanternTree?.collapseAll()" title="Collapse all branches" aria-label="Collapse all folders">⊟</button>
          <button id="treeCloseBtn" class="btn small icon-only ghost mobile-only" onclick="closeMobileTree(true)" title="Close folder tree" aria-label="Close folder tree">✕</button>
        </div>
      </div>
      <div id="treeBody" class="tree-body" role="tree" aria-label="Folder navigation"></div>
      <div id="treeLive" class="sr-only" aria-live="polite" aria-atomic="true"></div>
    </aside>
    <div id="treeResizer" class="tree-resizer" title="Drag to resize folder tree" role="separator" aria-orientation="vertical" aria-label="Resize folder tree"></div>
    <div id="browserArea" class="browser-area">
      <section id="grid" class="dropzone grid" aria-label="File list" tabindex="-1"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></section>
      <aside id="sidePreview" class="side-preview" aria-label="File preview">
        <div class="side-title">
          <button id="sideCloseBtn" class="btn small ghost" onclick="closeSidePreview()" title="Close preview (Esc)" aria-label="Close preview">← <span data-i18n="close">Close</span></button>
          <span class="side-title-text" id="sidePreviewTitle" data-i18n="preview">Preview</span>
          <div class="side-nav top" id="sidePreviewActions"></div>
        </div>
        <div class="side-body" id="sidePreviewBody"><div class="side-empty" data-i18n="selectToPreview">Select a file to preview</div></div>
      </aside>
    </div>
  </main>

  <footer id="statusBar" class="status-bar">
    <span id="statusItems">0 items</span>
    <span id="statusSel" class="status-sep hidden"></span>
    <span id="statusClip" class="status-clip hidden"></span>
    <span class="status-grow"></span>
    <span id="statusHint" class="status-hint">F2 Rename · Ctrl+C/X/V · Ctrl+L Address · Space Preview</span>
    <button type="button" id="sysTelemetryPill" class="sys-telemetry-pill" onclick="refreshSysTelemetry()" title="System GPU / VRAM / CPU / RAM" aria-label="Refresh system telemetry">💻 <span>System</span></button>
  </footer>
  <div id="a11yLive" class="sr-only" aria-live="polite" aria-atomic="true"></div>
</div>
<input id="fileInput" class="hidden" type="file" multiple>
<input id="folderInput" class="hidden" type="file" webkitdirectory directory multiple>
<div id="modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-head">
      <div class="modal-title-wrap"><div id="modalTitle" class="modal-title"></div><div id="modalMeta" class="modal-meta"></div></div>
      <div class="actions">
        <div id="modalImageTools" class="media-tools hidden">
          <button class="btn small icon-only" onclick="window.LanternMedia?.zoomBy(-0.25)" title="Zoom out (-)" aria-label="Zoom out">−</button>
          <button id="modalZoomLabel" class="btn small" onclick="window.LanternMedia?.resetZoom()" title="Fit to screen (0)" aria-label="Fit to screen">Fit</button>
          <button class="btn small" onclick="window.LanternMedia?.setActualSize()" title="Actual size 100% (1)" aria-label="Actual size 100%">1:1</button>
          <button class="btn small icon-only" onclick="window.LanternMedia?.zoomBy(0.25)" title="Zoom in (+)" aria-label="Zoom in">＋</button>
          <button class="btn small icon-only" onclick="window.LanternMedia?.rotateBy(90)" title="Rotate 90° (R)" aria-label="Rotate 90 degrees">↻</button>
        </div>
        <select id="modalVideoSpeed" class="select compact hidden" onchange="window.LanternMedia?.setVideoSpeed(this.value)" title="Playback speed" aria-label="Playback speed">
          <option value="0.5">0.5×</option><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option>
        </select>
        <button id="modalCropBtn" class="btn small hidden" onclick="cropViewedImage()" title="Crop into a new image" aria-label="Crop into a new image">✂ Crop</button>
        <button id="modalCropOverwriteBtn" class="btn small hidden" onclick="cropViewedImage(true)" title="Crop and overwrite original" aria-label="Crop and overwrite original">✂ Overwrite</button>
        <button class="btn small icon-only" onclick="window.LanternMedia?.toggleFullscreen()" title="Fullscreen (F)" aria-label="Toggle fullscreen">⛶</button>
        <button id="modalPrevBtn" class="btn small icon-only" onclick="stepMedia(-1,event)" title="Previous (Left)" aria-label="Previous media">←</button>
        <button id="modalNextBtn" class="btn small icon-only" onclick="stepMedia(1,event)" title="Next (Right)" aria-label="Next media">→</button>
        <button id="modalCloseBtn" class="btn small icon-only" onclick="closeModal()" title="Close (Esc)" aria-label="Close viewer">✕</button>
      </div>
    </div>
    <div class="modal-stage">
      <button id="modalPrevFloat" class="modal-nav modal-prev" onclick="stepMedia(-1,event)" title="Previous" aria-label="Previous media">‹</button>
      <div id="modalBody" class="modal-body"></div>
      <button id="modalNextFloat" class="modal-nav modal-next" onclick="stepMedia(1,event)" title="Next" aria-label="Next media">›</button>
    </div>
  </div>
</div>
<div id="uploadModal" class="upload-backdrop" role="dialog" aria-modal="true" aria-labelledby="uploadTargetTitle" onclick="if(event.target===this)closeUploadDialog()">
  <div class="upload-box">
    <div class="upload-head">
      <div><div id="uploadTargetTitle" class="upload-title">⬆️ Upload to: /{esc_rel}</div><div class="sub" data-i18n="uploadSub">Drop files or folders anytime. Large files (≥32 MB) upload in resumable 16 MB chunks.</div></div>
      <div style="display:flex;gap:6px"><button class="btn small ghost" onclick="closeUploadDialog()" title="Minimize to background" aria-label="Minimize upload dialog">—</button><button id="uploadCloseBtn" class="btn small" onclick="closeUploadDialog()" aria-label="Close upload dialog">✕</button></div>
    </div>
    <div class="upload-body">
      <div id="uploadDrop" class="upload-drop" role="button" tabindex="0" aria-label="Drop files or folders here"><div><div class="upload-plus">＋</div><b data-i18n="dropHere">Drop files or folders here</b><div data-i18n="orPickBelow">or use the buttons below</div></div></div>
      <div class="upload-options">
        <button class="btn" onclick="pickUploadFiles()" data-i18n="selectFiles">Select Files</button>
        <button class="btn" onclick="pickUploadFolder()" data-i18n="selectFolder">Select Folder</button>
        <label class="checkline"><span data-i18n="onConflict">On conflict:</span> <select id="uploadConflict" class="select compact"><option value="ask">Ask</option><option value="overwrite">Overwrite</option><option value="skip">Skip</option><option value="rename">Auto-rename</option></select></label>
        <button id="uploadPauseBtn" class="btn small hidden" onclick="window.LanternUpload?.togglePause()">⏸ Pause</button>
        <button id="uploadRetryBtn" class="btn small warn hidden" onclick="window.LanternUpload?.retryFailed()">↻ Retry Failed</button>
      </div>
      <div id="uploadQueue" class="upload-queue"></div>
    </div>
    <div class="upload-foot">
      <div id="uploadSummary" class="upload-summary">0 files</div>
      <div class="upload-progress"><span id="uploadModalBar"></span></div>
      <button class="btn ghost" onclick="clearUploadQueue()" data-i18n="clearSel">Clear</button>
      <button id="uploadStartBtn" class="btn primary" onclick="startUploadQueue()" data-i18n="startUpload">Start Upload</button>
    </div>
  </div>
</div>
<button type="button" id="uploadFloatPill" class="upload-float-pill hidden" onclick="openUploadDialog()" title="Open upload queue" aria-label="Open upload queue">
  <span id="uploadFloatText">⬆️ Uploading...</span>
  <div class="upload-float-bar"><span id="uploadFloatFill"></span></div>
</button>
<div id="propsModal" class="modal" role="dialog" aria-modal="true" aria-labelledby="propsTitle" onclick="if(event.target===this)closePropsModal()">
  <div class="props-box">
    <div class="modal-head"><div id="propsTitle" class="modal-title">Properties</div><button id="propsCloseBtn" class="btn small" onclick="closePropsModal()" aria-label="Close properties">✕</button></div>
    <div id="propsBody" class="props-body"></div>
  </div>
</div>
<div id="termDrawer" class="term-drawer" style="height:{int(self.app.config.terminal_start_height_px)}px" role="region" aria-label="Terminal and source control"></div>
<div id="ctxMenu" class="ctx-menu hidden" role="menu" aria-label="File actions" onclick="event.stopPropagation()">
  <button role="menuitem" tabindex="-1" data-act="selectAll" onclick="contextAction('selectAll')">☑️ <span data-i18n="selectAll">Select all</span></button>
  <button role="menuitem" tabindex="-1" data-act="clearSel" onclick="contextAction('clearSel')">⬜ <span data-i18n="clearSel">Clear selection</span></button>
  <button role="menuitem" tabindex="-1" data-act="open" onclick="contextAction('open')">↗ <span data-i18n="open">Open</span></button>
  <button role="menuitem" tabindex="-1" data-act="preview" onclick="contextAction('preview')">👁 <span data-i18n="preview">Quick Preview</span></button>
  <button role="menuitem" tabindex="-1" data-act="edit" onclick="contextAction('edit')">📝 Edit</button>
  <button role="menuitem" tabindex="-1" data-act="rename" onclick="contextAction('rename')">✏️ <span data-i18n="rename">Rename</span> (F2)</button>
  <button role="menuitem" tabindex="-1" data-act="download" onclick="contextAction('download')">⬇️ <span data-i18n="download">Download</span></button>
  <button role="menuitem" tabindex="-1" data-act="copy" onclick="contextAction('copy')">📋 <span data-i18n="copy">Copy</span> (Ctrl+C)</button>
  <button role="menuitem" tabindex="-1" data-act="cut" onclick="contextAction('cut')">✂️ Cut (Ctrl+X)</button>
  <button role="menuitem" tabindex="-1" data-act="paste" onclick="contextAction('paste')">📥 <span data-i18n="paste">Paste</span> (Ctrl+V)</button>
  <button role="menuitem" tabindex="-1" data-act="move" onclick="contextAction('move')">➡️ <span data-i18n="move">Move</span>...</button>
  <button role="menuitem" tabindex="-1" data-act="duplicate" onclick="contextAction('duplicate')">⧉ <span data-i18n="duplicate">Duplicate</span></button>
  <button role="menuitem" tabindex="-1" data-act="batch" onclick="contextAction('batch')">🔤 <span data-i18n="batchRename">Batch Rename</span></button>
  <button role="menuitem" tabindex="-1" data-act="archive" onclick="contextAction('archive')">🗜 Archive (Zip/Tar)</button>
  <button role="menuitem" tabindex="-1" data-act="extract" onclick="contextAction('extract')">📦 <span data-i18n="extract">Extract</span></button>
  <button role="menuitem" tabindex="-1" data-act="share" onclick="contextAction('share')">🔗 Copy Link</button>
  <button role="menuitem" tabindex="-1" data-act="properties" onclick="contextAction('properties')">ℹ️ Properties</button>
  <button role="menuitem" tabindex="-1" data-act="delete" class="danger" onclick="contextAction('delete')">🗑 <span data-i18n="delete">Delete</span> (Del)</button>
</div>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
"""
        self.send_bytes(200, self.app.views.page_shell(self.app.config.title, body, "/" + rel), "text/html; charset=utf-8")

    def serve_editor(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "file not found"); return
        if self.app.files.classify(path) != "text":
            self.send_error(400, "not editable text"); return
        st = path.stat()
        if st.st_size > MAX_TEXT_PREVIEW:
            self.send_error(413, "text file too large to edit safely"); return
        rel = path.resolve().relative_to(self.app.config.root.resolve()).as_posix()
        is_markdown = path.suffix.lower() in {".md", ".markdown"}
        version = None
        try:
            if is_markdown:
                document = read_markdown_document(path)
                content = document["content"]
                version = document["version"]
            else:
                content = path.read_text(encoding="utf-8", errors="replace")
        except MarkdownEditorError as e:
            self.send_error(e.status, str(e)); return
        except Exception as e:
            self.send_error(500, f"cannot read file: {e}"); return
        parent = Path(rel).parent.as_posix()
        back = "/" if parent == "." else "/" + self.app.files.quote_path(parent) + "/"
        body = f"""
<div class="editor">
  <div class="editorbar">
    <a class="btn" href="{back}">↩ Back</a>
    {f'<a class="btn" href="/api/plugin/preview?p={urllib.parse.quote(rel)}">Preview</a>' if is_markdown else ''}
    <div class="title">📝 {self.app.files.html_escape(rel)}</div>
    <div class="grow"></div>
    <span id="saveStatus" class="sub"></span>
    <button class="btn" type="button" onclick="toggleTerminal()">⌨️ Terminal</button>
    <button class="btn primary" onclick="saveEdit()">💾 Save</button>
  </div>
  <textarea id="editarea" class="editarea" spellcheck="false">{self.app.files.html_escape(content)}</textarea>
</div>
<div id="termDrawer" class="term-drawer" style="height:{int(self.app.config.terminal_start_height_px)}px" role="region" aria-label="Terminal and source control"></div>
<div id="toast" class="toast"></div>
<script>
const markdownSource = {self.app.files.json_dumps(is_markdown)};
let sourceVersion = {self.app.files.json_dumps(version)};
document.body.dataset.lanternChatKind = markdownSource ? "markdown" : "file";
document.body.dataset.lanternChatPath = {self.app.files.json_dumps(rel)};
if (window.APP) window.APP.currentPath = {self.app.files.json_dumps("" if parent == "." else parent)};
async function saveEdit(){{
  const st=document.getElementById('saveStatus'); st.textContent='Saving...';
  try{{
    const data={{path:{self.app.files.json_dumps(rel)},content:document.getElementById('editarea').value}};
    if(markdownSource)data.version=sourceVersion;
    const r=await fetch(markdownSource?'/api/md/save':'/api/save',{{
      method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)
    }});
    const j=await r.json();
    if(r.status===409)throw new Error('Conflict: file changed on disk or another client. Your draft is retained; reload to reconcile.');
    if(!r.ok||j.error) throw new Error(j.error||r.statusText);
    if(markdownSource)sourceVersion=j.version;
    st.textContent='Saved'; setTimeout(()=>st.textContent='',2000);
  }}catch(e){{ st.textContent='Error: '+e.message; }}
}}
document.addEventListener('keydown',e=>{{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){{e.preventDefault();saveEdit();}}}});
</script>
"""
        self.send_bytes(200, self.app.views.page_shell(f"Edit {path.name}", body, "/" + rel), "text/html; charset=utf-8")

    def serve_file(self, path: Path) -> None:
        # Revalidate images that external editors (Paint, Photoshop, etc.)
        # rewrite in place. Versioned list URLs avoid stale decoded bitmaps.
        mime = mimetypes.guess_type(str(path))[0] or ""
        self.serve_static_file(path, download=False,
                               cache_control="no-cache" if mime.startswith("image/") else None)

    def serve_static_file(self, path: Path, download: bool = False, ctype: Optional[str] = None, cache_control: Optional[str] = None) -> None:
        st = path.stat()
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        raw_etag = f'"{self.app.files.file_etag(path, st)}"'
        variant = (
            not download
            and not (self.headers.get("Range") or "")
            and 1024 <= st.st_size <= 8 * 1024 * 1024
            and self._is_compressible_ctype(ctype)
        )
        etag = raw_etag
        if variant and not raw_etag.startswith("W/"):
            # Identity and gzip representations share bytes but not wire
            # representation; use a weak validator for both variants.
            etag = "W/" + raw_etag
        if self.headers.get("If-None-Match") in {raw_etag, etag}:
            self.send_response(304)
            if variant:
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("ETag", etag)
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers(); return

        range_header = self.headers.get("Range")
        if (
            not download
            and not range_header
            and 1024 <= st.st_size <= 8 * 1024 * 1024
            and hasattr(self, "_accepts_gzip")
            and self._accepts_gzip()
            and self._is_compressible_ctype(ctype)
        ):
            raw_bytes = path.read_bytes()
            gz_bytes = gzip.compress(raw_bytes, compresslevel=5)
            if len(gz_bytes) < len(raw_bytes):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
                self.send_header("Content-Length", str(len(gz_bytes)))
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
                if cache_control:
                    self.send_header("Cache-Control", cache_control)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(gz_bytes)
                return
        start, end = 0, st.st_size - 1
        status = 200
        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if m:
                a, b = m.group(1), m.group(2)
                if a == "" and b:
                    length = int(b)
                    start = max(0, st.st_size - length)
                else:
                    start = int(a or 0)
                    end = int(b) if b else st.st_size - 1
                if start >= st.st_size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{st.st_size}")
                    self.end_headers(); return
                end = min(end, st.st_size - 1)
                status = 206

        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", etag)
        if variant:
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{st.st_size}")
        if download:
            safe_ascii = path.name.encode("ascii", "ignore").decode("ascii").replace('"', "_").replace("\r", "").replace("\n", "") or "download"
            utf8_name = urllib.parse.quote(path.name, safe="")
            self.send_header("Content-Disposition", f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{utf8_name}')
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)

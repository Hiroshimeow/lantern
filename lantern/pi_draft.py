"""Transient Markdown shadow files for Lantern's embedded Pi chatbot.

The browser remains authoritative for unsaved Markdown. Before a Pi turn, Lantern
copies that exact draft into a private shadow file. Pi may mutate the shadow; the
real document is committed only by the existing explicit /api/md/save path.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .md_editor import MarkdownEditorError, read_document

MAX_PI_DRAFT_BYTES = 1024 * 1024
_PROMPT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


@dataclass(frozen=True)
class ActiveMarkdownDraft:
    prompt_id: str
    real_path: Path
    shadow_path: Path
    base_version: str
    prompt_base: str
    shadow_hash: str
    real_version_start: str
    draft_revision: int


class MarkdownDraftShadow:
    def __init__(self, root: Path, *, storage_dir: Optional[Path] = None) -> None:
        self.root = Path(root).resolve()
        self.storage_dir = (Path(storage_dir) if storage_dir else
                            Path.home() / ".lantern" / "pi-drafts").resolve()
        self.guard_path = self.storage_dir / "guard.json"
        self.lock = threading.RLock()
        self.active: Optional[ActiveMarkdownDraft] = None

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _inside_root(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Markdown path must stay inside the configured root") from exc
        return resolved

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(prefix=".lantern-pi-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)

    def _write_guard(self, payload: dict[str, Any]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.guard_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, self.guard_path)

    def clear(self) -> None:
        with self.lock:
            self.active = None
            self._write_guard({"active": False})

    def prepare(
        self,
        real_path: Path,
        text: str,
        *,
        prompt_id: str,
        base_version: str,
        draft_revision: int = 0,
    ) -> ActiveMarkdownDraft:
        real = self._inside_root(real_path)
        if real.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError("Pi draft staging only supports Markdown")
        if not _PROMPT_ID.fullmatch(str(prompt_id or "")):
            raise ValueError("Invalid chat draft promptId")
        if not isinstance(text, str) or "\x00" in text:
            raise ValueError("Markdown draft must be text")
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_PI_DRAFT_BYTES:
            raise ValueError("Markdown draft is too large for Pi staging (1 MiB limit)")
        try:
            current = read_document(real)
        except MarkdownEditorError as exc:
            raise ValueError(str(exc)) from exc
        if current["version"] != base_version:
            raise RuntimeError("Saved Markdown changed on disk; reload or reconcile before asking Pi")

        key = hashlib.sha256(str(real).casefold().encode("utf-8")).hexdigest()[:16]
        shadow = self.storage_dir / key / real.name
        self._atomic_text(shadow, text)
        shadow_hash = self._hash_text(text)
        active = ActiveMarkdownDraft(
            prompt_id=str(prompt_id),
            real_path=real,
            shadow_path=shadow,
            base_version=str(base_version),
            prompt_base=text,
            shadow_hash=shadow_hash,
            real_version_start=current["version"],
            draft_revision=max(0, int(draft_revision or 0)),
        )
        with self.lock:
            self.active = active
            self._write_guard({
                "active": True,
                "promptId": active.prompt_id,
                "realPath": str(active.real_path),
                "shadowPath": str(active.shadow_path),
            })
        return active

    def context_fields(self) -> dict[str, Any]:
        with self.lock:
            active = self.active
        if not active:
            return {}
        return {
            "promptId": active.prompt_id,
            "draftPath": str(active.shadow_path),
            "savedPath": str(active.real_path),
            "baseVersion": active.base_version,
            "draftRevision": active.draft_revision,
        }

    def read_update(self, *, final: bool = False) -> Optional[dict[str, Any]]:
        with self.lock:
            active = self.active
        if not active:
            return None
        try:
            raw = active.shadow_path.read_bytes()
        except FileNotFoundError:
            return {
                "type": "chat_draft_error",
                "promptId": active.prompt_id,
                "error": "Pi Markdown shadow file disappeared",
                "final": bool(final),
            }
        if len(raw) > MAX_PI_DRAFT_BYTES:
            return {
                "type": "chat_draft_error",
                "promptId": active.prompt_id,
                "error": "Pi Markdown shadow exceeded the 1 MiB staging limit",
                "final": bool(final),
            }
        try:
            text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            return {
                "type": "chat_draft_error",
                "promptId": active.prompt_id,
                "error": "Pi Markdown shadow is no longer valid UTF-8",
                "final": bool(final),
            }
        digest = self._hash_text(text)
        changed = digest != active.shadow_hash
        if changed:
            replacement = ActiveMarkdownDraft(
                prompt_id=active.prompt_id,
                real_path=active.real_path,
                shadow_path=active.shadow_path,
                base_version=active.base_version,
                prompt_base=active.prompt_base,
                shadow_hash=digest,
                real_version_start=active.real_version_start,
                draft_revision=active.draft_revision,
            )
            with self.lock:
                if self.active and self.active.prompt_id == active.prompt_id:
                    self.active = replacement
        if not changed and not final:
            return None
        return {
            "type": "chat_draft_update",
            "promptId": active.prompt_id,
            "text": text,
            "final": bool(final),
        }

    def real_file_changed(self) -> Optional[dict[str, Any]]:
        with self.lock:
            active = self.active
        if not active:
            return None
        try:
            current = read_document(active.real_path)
        except MarkdownEditorError as exc:
            return {
                "type": "chat_real_file_touched",
                "promptId": active.prompt_id,
                "error": str(exc),
            }
        if current["version"] == active.real_version_start:
            return None
        return {
            "type": "chat_real_file_touched",
            "promptId": active.prompt_id,
            "baseVersion": active.real_version_start,
            "currentVersion": current["version"],
        }

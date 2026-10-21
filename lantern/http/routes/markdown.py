import os
import re
import urllib.parse
from pathlib import Path

from lantern.md_editor import MarkdownEditorError, read_document as read_markdown_document, save_document as save_markdown_document, MAX_MARKDOWN_EDITOR_BYTES
from lantern.working_copy import WorkingCopyError
from lantern.live_markdown import LiveMarkdownStore

_MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)\r\n]+))(?:\s+["\'][^"\']*["\'])?\s*\)')
_HTML_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*(?:["\']([^"\']+)["\']|([^\s>]+))', re.IGNORECASE)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}


class MarkdownRoutes:
    def _work_store(self) -> LiveMarkdownStore:
        if self.app.work is None:
            raise WorkingCopyError(503, "Working-copy store is not initialized")
        return self.app.work

    def api_work_get(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        try:
            self.send_json(200, {"ok": True, **self._work_store().get(rel)})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_work_write(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 5)
        try:
            result = self._work_store().write(
                data.get("path"),
                data.get("content"),
                expect_hash=data.get("expectHash"),
                base_version=data.get("baseVersion"),
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_work_patch(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 2)
        try:
            result = self._work_store().patch(
                data.get("path"),
                data.get("patches"),
                expect_hash=data.get("expectHash"),
                base_version=data.get("baseVersion"),
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_work_save(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 2)
        try:
            result = self._work_store().save(
                data.get("path"),
                expect_hash=data.get("expectHash"),
                expect_saved_version=data.get("expectSavedVersion"),
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_work_accept_hunk(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 5)
        try:
            result = self._work_store().accept_partial(
                data.get("path"), data.get("content"),
                expect_saved_version=data.get("expectSavedVersion"),
                expect_current_version=data.get("expectCurrentVersion"),
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_work_discard(self) -> None:
        data = self.read_json(max_bytes=64 * 1024)
        try:
            result = self._work_store().discard(
                data.get("path"),
                expect_hash=data.get("expectHash"),
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_md_versions(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        try:
            result = self._work_store().list_versions(rel)
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_md_version_restore(self) -> None:
        data = self.read_json(max_bytes=64 * 1024)
        rel = str(data.get("path") or "").strip()
        version_id = str(data.get("versionId") or data.get("id") or "").strip()
        version_hash = str(data.get("version") or "").strip()
        try:
            result = self._work_store().restore_version(
                rel,
                version_id=version_id,
                version_hash=version_hash,
            )
            self.send_json(200, {"ok": True, **result})
        except WorkingCopyError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    @staticmethod
    def _extract_markdown_image_refs(md_text: str) -> list[str]:
        # Strip fenced code blocks before scanning for image references
        lines = md_text.splitlines()
        prose_lines: list[str] = []
        in_fence = False
        for line in lines:
            if re.match(r"^\s*(?:`{3,}|~{3,})", line):
                in_fence = not in_fence
                continue
            if not in_fence:
                prose_lines.append(line)
        cleaned = "\n".join(prose_lines)
        raw_refs: list[str] = []
        for m in _MD_IMAGE_RE.finditer(cleaned):
            ref = (m.group(1) or m.group(2) or "").strip()
            if ref:
                raw_refs.append(ref)
        for m in _HTML_IMG_RE.finditer(cleaned):
            ref = (m.group(1) or m.group(2) or "").strip()
            if ref:
                raw_refs.append(ref)
        filtered: list[str] = []
        for ref in raw_refs:
            lower = ref.lower()
            if lower.startswith(("http://", "https://", "data:", "blob:", "mailto:", "//")):
                continue
            clean_ref = urllib.parse.unquote(ref.split("#", 1)[0].split("?", 1)[0]).strip()
            if clean_ref:
                filtered.append(clean_ref)
        return filtered

    def api_md_image_audit(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        if not isinstance(rel, str) or not rel.strip():
            self.send_json(400, {"error": "Markdown path required"}); return
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_file() or target.suffix.lower() not in {".md", ".markdown"}:
            self.send_json(404, {"error": "Markdown file not found"}); return
        root = self.app.config.root.resolve()
        md_dir = target.parent.resolve()
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.send_json(400, {"error": str(exc)}); return

        refs = self._extract_markdown_image_refs(text)
        missing: list[str] = []
        valid: list[str] = []
        referenced_resolved: set[str] = set()
        seen_refs: set[str] = set()

        for ref in refs:
            norm_ref = ref.replace("\\", "/")
            if norm_ref.startswith("/"):
                cand = (root / norm_ref.lstrip("/")).resolve()
            else:
                cand = (md_dir / norm_ref).resolve()
            try:
                cand.relative_to(root)
            except ValueError:
                if norm_ref not in seen_refs:
                    seen_refs.add(norm_ref)
                    missing.append(norm_ref)
                continue
            norm_abs = os.path.normcase(str(cand))
            referenced_resolved.add(norm_abs)
            if cand.is_file():
                if norm_ref not in seen_refs:
                    seen_refs.add(norm_ref)
                    valid.append(norm_ref)
            else:
                if norm_ref not in seen_refs:
                    seen_refs.add(norm_ref)
                    missing.append(norm_ref)

        # Also collect image references from sibling .md files in the same folder so shared folder assets
        # are only flagged as unused if NO .md file in the folder references them (unless in a doc-specific folder).
        sibling_referenced: set[str] = set(referenced_resolved)
        try:
            for sib in md_dir.glob("*.md"):
                if sib.resolve() == target.resolve():
                    continue
                sib_txt = sib.read_text(encoding="utf-8", errors="ignore")
                for sref in self._extract_markdown_image_refs(sib_txt):
                    snorm = sref.replace("\\", "/")
                    scand = (root / snorm.lstrip("/")).resolve() if snorm.startswith("/") else (md_dir / snorm).resolve()
                    sibling_referenced.add(os.path.normcase(str(scand)))
        except Exception:
            pass

        scan_dirs: list[Path] = [md_dir]
        for sub_name in ("assets", "images", "img", "media", f"{target.stem}_assets", f"{target.stem}.assets"):
            sub_dir = md_dir / sub_name
            if sub_dir.is_dir():
                scan_dirs.append(sub_dir.resolve())

        unreferenced: list[str] = []
        seen_unused: set[str] = set()
        for sdir in scan_dirs:
            try:
                for entry in sorted(sdir.iterdir()):
                    if not entry.is_file() or entry.name.startswith("."):
                        continue
                    if entry.suffix.lower() not in _IMAGE_SUFFIXES:
                        continue
                    resolved_entry = entry.resolve()
                    norm_entry = os.path.normcase(str(resolved_entry))
                    if norm_entry not in sibling_referenced and norm_entry not in seen_unused:
                        seen_unused.add(norm_entry)
                        try:
                            rel_to_md = resolved_entry.relative_to(md_dir).as_posix()
                        except ValueError:
                            rel_to_md = resolved_entry.relative_to(root).as_posix()
                        unreferenced.append(rel_to_md)
            except Exception:
                continue

        self.send_json(200, {
            "ok": True,
            "path": self.app.files.rel_url_for_path(target),
            "referencedCount": len(seen_refs),
            "validCount": len(valid),
            "missing": missing,
            "missingCount": len(missing),
            "unreferenced": unreferenced,
            "unreferencedCount": len(unreferenced),
        })

    def api_md_document(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        rel = qs.get("p", [""])[0]
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        try:
            result = read_markdown_document(target)
            self.send_json(200, {"ok": True, "path": self.app.files.rel_url_for_path(target), **result})
        except MarkdownEditorError as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

    def api_md_render(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 5)
        rel = data.get("path")
        content = data.get("content")
        if not isinstance(rel, str) or not rel:
            self.send_json(400, {"error": "Markdown path required"}); return
        if not isinstance(content, str):
            self.send_json(400, {"error": "Markdown content must be text"}); return
        if len(content.encode("utf-8")) > MAX_MARKDOWN_EDITOR_BYTES:
            self.send_json(413, {"error": "Markdown draft exceeds editor size limit"}); return
        if self.app.plugin is None or not hasattr(self.app.plugin, "render_markdown_draft"):
            self.send_json(503, {"error": "Markdown preview plugin unavailable"}); return
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        if not target.is_file() or target.suffix.lower() not in {".md", ".markdown"}:
            self.send_json(404, {"error": "Markdown file not found"}); return
        try:
            body = self.app.plugin.render_markdown_draft(content, target, self.app.config.root)
            self.send_json(200, {"ok": True, "html": body})
        except (ValueError, OSError) as exc:
            self.send_json(400, {"error": str(exc)})

    def api_md_save(self) -> None:
        data = self.read_json(max_bytes=MAX_MARKDOWN_EDITOR_BYTES * 5)
        rel = data.get("path")
        if not isinstance(rel, str) or not rel:
            self.send_json(400, {"error": "Markdown path required"}); return
        target = self.app.files.safe_join("/" + self.app.files.quote_path(rel))
        try:
            # Block section-editor saves while LanternBot is actively editing this file.
            state = self._work_store().get(rel)
            if state.get("turnActive"):
                raise WorkingCopyError(409, "File is locked while LanternBot is editing it", reason="pi_turn")
            result = save_markdown_document(target, data.get("content"), data.get("version"))
            try:
                self._work_store().record_version_if_changed(rel, target.read_bytes())
            except Exception:
                pass
            self.send_json(200, {"ok": True, **result})
        except (MarkdownEditorError, WorkingCopyError) as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

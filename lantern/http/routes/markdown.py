
import urllib.parse

from lantern.md_editor import MarkdownEditorError, read_document as read_markdown_document, save_document as save_markdown_document, MAX_MARKDOWN_EDITOR_BYTES
from lantern.working_copy import WorkingCopyError
from lantern.live_markdown import LiveMarkdownStore

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
            # Section editing also changes the real .md. Pending diff merely
            # means the accepted md_temp snapshot differs; it is not a lock.
            self._work_store().get(rel)
            result = save_markdown_document(target, data.get("content"), data.get("version"))
            self.send_json(200, {"ok": True, **result})
        except (MarkdownEditorError, WorkingCopyError) as exc:
            self.send_json(exc.status, {"error": str(exc), **exc.details})

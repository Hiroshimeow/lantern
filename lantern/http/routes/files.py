
import email.utils
import json
import mimetypes
import os
import re
import shutil
import tempfile
import tarfile
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from lantern.config import (CHUNK_SIZE, MAX_TEXT_PREVIEW, MAX_ZIP_PAYLOAD, normalize_conflict, normalize_recursive_depth, normalize_sort)
from lantern.filesystem import BadRequest
from lantern.md_editor import MarkdownEditorError, read_document as read_markdown_document

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
        target = self.app.files.safe_join("/" + rel)
        if not target.is_dir():
            self.send_json(404, {"error": "not a folder"}); return
        items, next_offset, has_more, errors, total = self.app.files.list_entries_page(target, offset, limit, sort_mode, q, folders_first, recursive_depth)
        if offset == 0:
            rel_norm = target.resolve().relative_to(self.app.config.root.resolve()).as_posix()
            if rel_norm != ".":
                parent = Path(rel_norm).parent.as_posix()
                href = "/" if parent == "." else "/" + self.app.files.quote_path(parent) + "/"
                items.insert(0, {"special": "back", "href": href})
        self.send_json(200, {"items": items, "nextOffset": next_offset, "hasMore": has_more, "errors": errors, "total": total, "sort": sort_mode, "folders_first": folders_first, "recursive_depth": recursive_depth_raw if q.strip() else "0"})

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

    def api_save(self) -> None:
        data = self.read_json()
        rel = str(data.get("path", ""))
        content = str(data.get("content", ""))
        target = self.app.files.safe_join("/" + rel)
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
        base = self.app.files.safe_join("/" + str(data.get("path", "")))
        name = self.app.files.clean_component(str(data.get("name", "")))
        dest = (base / name).resolve()
        dest.relative_to(self.app.config.root.resolve())
        dest.mkdir(parents=True, exist_ok=False)
        self.send_json(200, {"ok": True, "path": self.app.files.rel_url_for_path(dest)})

    def api_newfile(self) -> None:
        data = self.read_json()
        base = self.app.files.safe_join("/" + str(data.get("path", "")))
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
        target = self.app.files.safe_join("/" + str(data.get("path", "")))
        name = self.app.files.clean_component(str(data.get("name", "")))
        if not target.exists():
            self.send_json(404, {"error": "not found"}); return
        dest = self.app.files.ensure_under_root(target.parent / name)
        self.app.files.protect_config_mutation(target)
        if dest.exists():
            self.send_json(409, {"error": "target exists"}); return
        target.rename(dest)
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
            result = self.app.files.move_item(src, dest_dir, conflict=conflict)
            if result is None:
                skipped += 1
            else:
                moved.append(self.app.files.rel_url_for_path(result).lstrip("/"))
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
            src.rename(dest)
            renamed.append({"from": self.app.files.rel_url_for_path(src).lstrip("/"), "to": self.app.files.rel_url_for_path(dest).lstrip("/")})
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
            target = self.app.files.safe_join("/" + str(rel))
            if target.resolve() == self.app.config.root.resolve():
                continue
            self.app.files.protect_config_mutation(target)
            if target.is_dir():
                shutil.rmtree(target)
                deleted += 1
            elif target.exists():
                target.unlink()
                deleted += 1
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
                target = self.app.files.safe_join("/" + str(rel))
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
        body = f"""
<div class="app">
  <header class="top">
    <div class="top-inner">
      <div class="brand"><div class="logo">LD</div><div><div class="brand-title">{self.app.files.html_escape(self.app.config.title)}</div><div class="brand-sub">Root: {self.app.files.html_escape(str(self.app.config.root))}</div></div></div>
      <div class="search">
        <select id="recursiveDepth" class="search-depth" onchange="changeRecursiveDepth(this)" title="Độ sâu tìm đệ quy; 0 chỉ tìm thư mục hiện tại">
          <option value="0">Hiện tại</option>
          <option value="all">All</option>
          <option value="1">1 cấp</option>
          <option value="2">2 cấp</option>
          <option value="3">3 cấp</option>
          <option value="4">4 cấp</option>
          <option value="5">5 cấp</option>
          <option value="6">6 cấp</option>
        </select>
        <input id="q" type="search" placeholder="Tìm tên, đường dẫn, đuôi file...">
      </div>
      <div class="actions">
        <div id="sysTelemetryPill" class="sys-telemetry-pill" onclick="refreshSysTelemetry()" title="GPU / VRAM &amp; RAM Status">🎮 <span>VRAM · GPU · RAM</span></div>
        <button class="btn primary" onclick="openUploadDialog()">⬆️ <span class="label">Upload</span></button>
        <button class="btn" onclick="mkdir()">➕ <span class="label">Thư mục</span></button>
        <button class="btn" onclick="newFile()">📝 <span class="label">File</span></button>
        <button class="btn terminal-btn" onclick="toggleTerminal()">⌨️ <span class="label">Terminal</span></button>
      </div>
    </div>
    <div class="crumbs">{self.app.views.breadcrumb(rel)}</div>
  </header>
  <main class="main">
    <div class="toolbar">
      <div class="view-toggle"><button data-view="grid" onclick="setView('grid')">Grid</button><button data-view="list" onclick="setView('list')">List</button></div>
      <select id="sortSelect" class="select" onchange="changeSort(this)" title="Sắp xếp">
        <option value="name-asc">Tên A→Z</option>
        <option value="name-desc">Tên Z→A</option>
        <option value="mtime-desc">Ngày mới nhất</option>
        <option value="mtime-asc">Ngày cũ nhất</option>
        <option value="size-desc">Dung lượng lớn nhất</option>
        <option value="size-asc">Dung lượng nhỏ nhất</option>
        <option value="type-asc">Loại file A→Z</option>
        <option value="type-desc">Loại file Z→A</option>
        <option value="ext-asc">Đuôi file A→Z</option>
        <option value="ext-desc">Đuôi file Z→A</option>
      </select>
      <select id="limitSelect" class="select compact" onchange="changeLimit(this)" title="Số mục tải thêm mỗi lần cuộn">
        <option value="100">Tải 100 mục</option>
        <option value="220">Tải 220 mục</option>
        <option value="500">Tải 500 mục</option>
        <option value="1000">Tải 1000 mục</option>
      </select>
      <label class="checkline" title="Giữ thư mục nằm trước file khi sắp xếp"><input id="foldersFirst" type="checkbox" onchange="changeFoldersFirst(this)"> 📁 trước</label>
      <select id="thumbFit" class="select compact" onchange="changeThumbFit(this)" title="Cách fit thumbnail"><option value="contain">Fit</option><option value="cover">Crop</option></select>
      <label class="checkline" title="Bật/tắt preview 2x2 cho folder"><input id="folderPreviewToggle" type="checkbox" onchange="toggleFolderPreview(this)"> Preview</label>
      <select id="previewAnim" class="select compact" onchange="changePreviewAnimation(this)" title="Animation folder preview"><option value="none">No anim</option><option value="fade">Fade</option><option value="flip">Flip</option><option value="slide">Slide</option></select>
      <button id="previewPaneBtn" class="btn small" onclick="togglePreviewPane()" title="Bật/tắt preview pane bên phải">👁 Preview on</button>
      <button class="btn small" onclick="refreshFolder()">↻ Refresh</button>
      <button class="btn small" onclick="selectVisible()">Chọn hiện</button>
      <button class="btn small ghost" onclick="clearSel()">Bỏ chọn</button>
      <span id="selCount" class="sub"></span>
      <div class="grow"></div>
      <button id="shareBtn" class="btn small hidden" onclick="shareOne()">🔗 Copy link</button>
      <button id="previewBtn" class="btn small hidden" onclick="previewSelected()">👁 Preview</button>
      <button class="btn small" onclick="addPreviewExtension()" title="Thêm đuôi/pattern để plugin đọc nhanh, ví dụ .foo hoặc *.env.*">＋ Đuôi đọc</button>
      <button id="copyBtn" class="btn small hidden" onclick="copySel()">📋 Copy</button>
      <button id="moveBtn" class="btn small hidden" onclick="moveSel()">➡️ Move</button>
      <button id="duplicateBtn" class="btn small hidden" onclick="duplicateSel()">⧉ Duplicate</button>
      <button id="batchRenameBtn" class="btn small hidden" onclick="batchRenameSel()">🔤 Batch rename</button>
      <button id="extractBtn" class="btn small hidden" onclick="extractSelected()">📦 Extract</button>
      <button id="archiveBtn" class="btn small hidden" onclick="archiveSelected()">🗜 Archive</button>
      <button id="renameBtn" class="btn small warn hidden" onclick="renameOne()">✏️ Rename</button>
      <button id="downloadBtn" class="btn small hidden" onclick="downloadSelected()">⬇️ Tải</button>
      <button id="deleteBtn" class="btn small danger hidden" onclick="deleteSel()">🗑️ Xoá</button>
    </div>
    <div id="browserArea" class="browser-area"><section id="grid" class="dropzone grid"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></section><aside id="sidePreview" class="side-preview"><div class="side-empty">Chọn file để preview</div></aside></div>
  </main>
</div>
<input id="fileInput" class="hidden" type="file" multiple>
<input id="folderInput" class="hidden" type="file" webkitdirectory directory multiple>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()"><div class="modal-box"><div class="modal-head"><div class="modal-title-wrap"><div id="modalTitle" class="modal-title"></div><div id="modalMeta" class="modal-meta"></div></div><div class="actions"><button id="modalCropBtn" class="btn small hidden" onclick="cropViewedImage()" title="Crop into a new image">✂ Crop</button><button id="modalCropOverwriteBtn" class="btn small hidden" onclick="cropViewedImage(true)" title="Crop and overwrite original (requires confirmation)">✂ Overwrite original</button><button id="modalPrevBtn" class="btn small" onclick="stepMedia(-1,event)" title="Trước">←</button><button id="modalNextBtn" class="btn small" onclick="stepMedia(1,event)" title="Tiếp">→</button><button class="btn small" onclick="closeModal()">✕</button></div></div><div class="modal-stage"><button id="modalPrevFloat" class="modal-nav modal-prev" onclick="stepMedia(-1,event)" title="Trước">‹</button><div id="modalBody" class="modal-body"></div><button id="modalNextFloat" class="modal-nav modal-next" onclick="stepMedia(1,event)" title="Tiếp">›</button></div></div></div>
<div id="uploadModal" class="upload-backdrop" onclick="if(event.target===this)closeUploadDialog()">
  <div class="upload-box">
    <div class="upload-head"><div><div class="upload-title">⬆️ Upload vào: /{self.app.files.html_escape(rel)}</div><div class="sub">Kéo file/folder vào vùng dấu +, hoặc bấm chọn file/folder. Folder drag/drop tốt nhất trên Chrome/Edge.</div></div><button class="btn small" onclick="closeUploadDialog()">✕</button></div>
    <div class="upload-body">
      <div id="uploadDrop" class="upload-drop"><div><div class="upload-plus">＋</div><b>Kéo file/folder vào đây</b><div>hoặc bấm để chọn file</div></div></div>
      <div class="upload-options">
        <button class="btn" onclick="pickUploadFiles()">Chọn file</button>
        <button class="btn" onclick="pickUploadFolder()">Chọn folder</button>
        <label class="checkline">Trùng tên: <select id="uploadConflict" class="select compact"><option value="ask">Hỏi</option><option value="overwrite">Ghi đè</option><option value="skip">Bỏ qua</option><option value="rename">Tự đổi tên</option></select></label>
      </div>
      <div id="uploadQueue" class="upload-queue"></div>
    </div>
    <div class="upload-foot"><div id="uploadSummary" class="upload-summary">0 file</div><div class="upload-progress"><span id="uploadModalBar"></span></div><button class="btn ghost" onclick="clearUploadQueue()">Clear</button><button class="btn primary" onclick="startUploadQueue()">Start Upload</button></div>
  </div>
</div>
<div id="termDrawer" class="term-drawer" style="height:{int(self.app.config.terminal_start_height_px)}px" role="region" aria-label="Terminal and source control"></div>\n<div id="ctxMenu" class="ctx-menu hidden" onclick="event.stopPropagation()">
  <button data-act="open" onclick="contextAction('open')">↗ Open</button>
  <button data-act="preview" onclick="contextAction('preview')">👁 Preview</button>
  <button data-act="edit" onclick="contextAction('edit')">📝 Edit</button>
  <button data-act="rename" onclick="contextAction('rename')">✏️ Rename</button>
  <button data-act="download" onclick="contextAction('download')">⬇️ Download</button>
  <button data-act="archive" onclick="contextAction('archive')">🗜 Archive</button>
  <button data-act="extract" onclick="contextAction('extract')">📦 Extract</button>
  <button data-act="copy" onclick="contextAction('copy')">📋 Copy</button>
  <button data-act="move" onclick="contextAction('move')">➡️ Move</button>
  <button data-act="duplicate" onclick="contextAction('duplicate')">⧉ Duplicate</button>
  <button data-act="batch" onclick="contextAction('batch')">🔤 Batch rename</button>
  <button data-act="share" onclick="contextAction('share')">🔗 Copy link</button>
  <button data-act="delete" class="danger" onclick="contextAction('delete')">🗑 Delete</button>
</div>
<div id="toast" class="toast"></div>
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
    <button class="btn primary" onclick="saveEdit()">💾 Save</button>
  </div>
  <textarea id="editarea" class="editarea" spellcheck="false">{self.app.files.html_escape(content)}</textarea>
</div>
<div id="toast" class="toast"></div>
<script>
const markdownSource = {self.app.files.json_dumps(is_markdown)};
let sourceVersion = {self.app.files.json_dumps(version)};
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
        etag = self.app.files.file_etag(path, st)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers(); return

        range_header = self.headers.get("Range")
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
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{st.st_size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
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

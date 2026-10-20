
import os
import re
import tempfile
import urllib.parse
from pathlib import Path

from lantern.filesystem import BadRequest

class CropRoutes:
    def api_image_version(self, query: str) -> None:
        rel = urllib.parse.parse_qs(query).get("p", [""])[0]
        target = self.app.crop._image_crop_target(rel)
        if not target.is_file():
            self.send_json(404, {"error": "image not found"}); return
        if target.suffix.lower() not in self.app.crop.mimes:
            self.send_json(415, {"error": "overwrite unsupported for this image format"}); return
        if target.stat().st_size > self.app.crop.max_bytes:
            self.send_json(413, {"error": "image is too large for overwrite"}); return
        with self.app.crop.lock:
            data = target.read_bytes()
        self.send_json(200, {"version": self.app.crop._image_version(data), "bytes": len(data),
                             "mime": self.app.crop.mimes[target.suffix.lower()]})

    def api_image_overwrite(self, query: str) -> None:
        rel = urllib.parse.parse_qs(query).get("p", [""])[0]
        target = self.app.crop._image_crop_target(rel)
        if target.suffix.lower() not in self.app.crop.mimes:
            self.send_json(415, {"error": "unsupported image format; use Save As"}); return
        expected = self.headers.get("If-Match", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
            self.send_json(428, {"error": "image content version required"}); return
        n = self.content_length(max_bytes=self.app.crop.max_bytes)
        if n < 32:
            raise BadRequest("invalid cropped image")
        body = self.read_body_exact(n)
        mime = self.app.crop._image_crop_mime(target, body)
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != mime:
            self.send_json(415, {"error": "image MIME header does not match bytes"}); return
        temp_path = None
        with self.app.crop.lock:
            if not target.is_file() or target.is_symlink():
                self.send_json(404, {"error": "original image missing"}); return
            if target.stat().st_nlink > 1:
                self.send_json(409, {"error": "image has multiple hardlinks; Save As instead"}); return
            old = target.read_bytes()
            if self.app.crop._image_version(old) != expected:
                self.send_json(409, {"error": "image changed; reload before overwriting"}); return
            # The existing thumbnail may reuse the same stat-based cache key
            # on coarse-timestamp filesystems. Invalidate it explicitly.
            stale_thumb = self.app.media.thumb_cache_path(target, "image")
            fd, tmp = tempfile.mkstemp(prefix=".lantern-uploading-", dir=str(target.parent))
            temp_path = Path(tmp)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                # A replaced image remains the same logical filename; original
                # Markdown references are never rewritten by this endpoint.
                os.chmod(temp_path, target.stat().st_mode)
                outcome = self.app.crop._replace_crop_with_retry(temp_path, target, expected)
                if outcome == "stale":
                    self.send_json(409, {"error": "image changed during overwrite; reload before retrying"})
                    return
                if outcome == "locked":
                    self.send_json(423, {"error": "image is locked by another application; close it and retry"})
                    return
                temp_path = None
                # fsync of a directory is supported on POSIX, best effort on
                # other platforms. A failure here must not misreport a commit.
                if hasattr(os, "O_DIRECTORY"):
                    directory_fd = None
                    try:
                        directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(directory_fd)
                        except OSError:
                            pass
                    except OSError:
                        pass
                    finally:
                        if directory_fd is not None:
                            os.close(directory_fd)
                try:
                    stale_thumb.unlink(missing_ok=True)
                except OSError:
                    pass
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
        self.send_json(200, {"ok": True, "file": self.app.files.rel_url_for_path(target),
                             "version": self.app.crop._image_version(body), "bytes": len(body)})

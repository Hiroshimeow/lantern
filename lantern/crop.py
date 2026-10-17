
import hashlib
import os
import threading
import time
from pathlib import Path

from .filesystem import FileService, BadRequest

class CropService:
    def __init__(self, files: FileService):
        self.files = files
        self.lock = threading.Lock()
        self.max_bytes = 20 * 1024 * 1024
        self.mimes = {'.png': 'image/png', '.jpg': 'image/jpeg',
                      '.jpeg': 'image/jpeg', '.webp': 'image/webp'}

    def _image_crop_mime(self, path: Path, data: bytes) -> str:
        expected = self.mimes.get(path.suffix.lower())
        if not expected:
            raise BadRequest("overwrite is supported for PNG/JPEG/WebP only; use Save As")
        if (data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33
                and data[12:16] == b"IHDR"):
            detected = "image/png"
        elif len(data) >= 8 and data[:3] == b"\xff\xd8\xff" and data[-2:] == b"\xff\xd9":
            detected = "image/jpeg"
        elif (len(data) >= 20 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
              and int.from_bytes(data[4:8], "little") + 8 == len(data)):
            detected = "image/webp"
        else:
            raise BadRequest("invalid or unsupported image bytes")
        if detected != expected:
            raise BadRequest("cropped image type does not match original extension; use Save As")
        return expected

    def _image_version(self, data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _replace_crop_with_retry(self, temp_path: Path, target: Path, expected: str) -> str:
        """Bound transient Windows image locks; never retry against changed bytes."""
        for attempt in range(6):
            try:
                if self._image_version(target.read_bytes()) != expected:
                    return "stale"
            except FileNotFoundError:
                return "stale"
            except PermissionError:
                if attempt == 5:
                    return "locked"
                time.sleep(.03)
                continue
            try:
                os.replace(temp_path, target)
                return "ok"
            except PermissionError:
                if attempt == 5:
                    return "locked"
                time.sleep(.03)
        return "locked"

    def _image_crop_target(self, rel: str) -> Path:
        """Resolve a crop target without normalizing away '..' or following links.

        Crop overwrite changes the identity of one file. A symlink or a hardlink
        would silently affect a different filename (or detach other link names).
        Existing generic browse routes keep their own path behavior.
        """
        parts = rel.replace("\\", "/").split("/")
        if not rel or rel.startswith(("/", "\\")) or any(part in {".", ".."} for part in parts):
            raise BadRequest("invalid image path")
        root = self.files.cfg.root.resolve()
        candidate = root
        for part in parts:
            if part:
                candidate = candidate / part
                if candidate.is_symlink():
                    raise BadRequest("crop overwrite does not follow symbolic links")
        target = self.files.safe_join("/" + self.files.quote_path(rel))
        if target.exists() and target.stat().st_nlink > 1:
            raise BadRequest("crop overwrite does not replace hardlinked images")
        return target

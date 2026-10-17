
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AppConfig, SUBTITLE_EXTS
from .filesystem import FileService
try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except Exception:
    HAS_PIL = False
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

class MediaService:
    def __init__(self, config: AppConfig, files: FileService):
        self.cfg = config
        self.files = files


    def thumb_cache_path(self, path: Path, kind: str) -> Path:
        try:
            st = path.stat()
            raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{kind}".encode("utf-8", "surrogateescape")
        except Exception:
            raw = f"{path}|{time.time()}|{kind}".encode("utf-8", "surrogateescape")
        name = hashlib.sha1(raw).hexdigest() + ".jpg"
        return self.cfg.cache_dir / "thumbs" / name[:2] / name

    def folder_preview_cache_path(self, folder: Path) -> Path:
        try:
            st = folder.stat()
            raw = f"{folder.resolve()}|{st.st_mtime_ns}|{self.cfg.folder_preview_scan_limit}|{self.cfg.folder_preview_max_items}|{self.cfg.folder_preview_include_video}".encode("utf-8", "surrogateescape")
        except Exception:
            raw = f"{folder}|{time.time()}".encode("utf-8", "surrogateescape")
        name = hashlib.sha1(raw).hexdigest() + ".json"
        return self.cfg.cache_dir / "folder_previews" / name[:2] / name

    def folder_preview_items(self, folder: Path) -> List[Dict[str, Any]]:
        """Return lightweight preview metadata for a folder.

        Important for performance: scan only one level, prefer images, and only fall
        back to videos when there are not enough images. This avoids spawning ffmpeg
        thumbnails for every video-heavy folder while browsing.
        """
        if not self.cfg.folder_preview_enabled or not folder.is_dir():
            return []
        cache = self.folder_preview_cache_path(folder)
        cached_items = None
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, list):
                    cached_items = data
            except Exception:
                pass
        images: List[Dict[str, Any]] = []
        videos: List[Dict[str, Any]] = []
        scanned = 0

        def add_item(p: Path, name: str, kind: str) -> Dict[str, Any]:
            rel = p.resolve().relative_to(self.cfg.root.resolve()).as_posix()
            version = self.files.file_etag(p, p.stat())
            return {
                "name": name,
                "kind": kind,
                "url": "/" + self.files.quote_path(rel) + "?v=" + version,
                "thumb": f"/api/thumb?p={urllib.parse.quote(rel)}&v={version}",
            }

        # Parent directory mtime does not change when Paint overwrites an image.
        # Keep the cached selection but refresh the small set of image versions.
        if cached_items is not None:
            fresh = []
            for item in cached_items[:int(self.cfg.folder_preview_max_items)]:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str) or "/" in name or "\\" in name:
                    continue
                candidate = folder / name
                try:
                    if candidate.is_file():
                        kind = self.files.classify(candidate, False)
                        if kind in {"image", "video"}:
                            fresh.append(add_item(candidate, name, kind))
                except (OSError, ValueError):
                    continue
            return fresh

        try:
            with os.scandir(folder) as it:
                for de in it:
                    if scanned >= int(self.cfg.folder_preview_scan_limit):
                        break
                    scanned += 1
                    name = de.name
                    if self.files.should_hide_entry(folder, name):
                        continue
                    try:
                        if not de.is_file(follow_symlinks=False):
                            continue
                        p = folder / name
                        kind = self.files.classify(p, False)
                        if kind == "image":
                            images.append(add_item(p, name, kind))
                            if len(images) >= int(self.cfg.folder_preview_max_items):
                                break
                        elif self.cfg.folder_preview_include_video and kind == "video" and len(videos) < int(self.cfg.folder_preview_max_items):
                            videos.append(add_item(p, name, kind))
                    except Exception:
                        continue
        except Exception:
            images, videos = [], []

        # Prefer images. Only add video thumbs if image count is too low.
        items = (images + videos)[: int(self.cfg.folder_preview_max_items)]
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(self.files.json_dumps(items), encoding="utf-8")
        except Exception:
            pass
        return items

    def make_image_thumb(self, src: Path, dst: Path) -> bool:
        if not HAS_PIL:
            return False
        if src.suffix.lower() in {".svg", ".avif", ".heic", ".heif"}:
            return False
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((420, 420))
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(dst, "JPEG", quality=82, optimize=True)
            return True
        except Exception:
            return False

    def make_video_thumb(self, src: Path, dst: Path) -> bool:
        if not FFMPEG:
            return False
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", "00:00:01.000", "-i", str(src),
                "-frames:v", "1", "-vf", "scale='min(420,iw)':-2", "-q:v", "3", str(dst)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            return dst.exists() and dst.stat().st_size > 0
        except Exception:
            return False

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            if value in (None, "", "N/A"):
                return None
            return float(value)
        except Exception:
            return None

    def _fps(self, value: str) -> str:
        try:
            if not value or value == "0/0":
                return ""
            a, b = value.split("/", 1)
            fps = float(a) / float(b)
            return f"{fps:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return ""

    def bitrate_fmt(self, value: Any) -> str:
        try:
            n = int(float(value))
        except Exception:
            return ""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.2f} Mbps"
        if n >= 1_000:
            return f"{n / 1_000:.0f} kbps"
        return f"{n} bps"

    def video_subtitle_sidecars(self, video: Path) -> List[Path]:
        found: List[Path] = []
        try:
            parent = video.parent
            stem = video.stem
            for ext in sorted(SUBTITLE_EXTS):
                p = parent / f"{stem}{ext}"
                if p.is_file():
                    found.append(p)
            for p in parent.glob(stem + ".*"):
                try:
                    if p.is_file() and p.suffix.lower() in SUBTITLE_EXTS and p not in found:
                        found.append(p)
                except Exception:
                    continue
        except Exception:
            pass
        return found[:12]

    def srt_to_vtt(self, text: str) -> str:
        text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
        if text.lstrip().startswith("WEBVTT"):
            return text
        text = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
        return "WEBVTT\n\n" + text.strip() + "\n"

    def _ass_time_to_vtt(self, t: str) -> str:
        try:
            h, m, rest = t.strip().split(":", 2)
            s, cs = rest.split(".", 1)
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int(cs[:2]) * 10:03d}"
        except Exception:
            return "00:00:00.000"

    def ass_to_vtt(self, text: str) -> str:
        out = ["WEBVTT", ""]
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            start, end, body = parts[1], parts[2], parts[9]
            body = re.sub(r"\{.*?\}", "", body).replace("\\N", "\n").replace("\\n", "\n")
            if body.strip():
                out.append(f"{self._ass_time_to_vtt(start)} --> {self._ass_time_to_vtt(end)}")
                out.append(body.strip())
                out.append("")
        return "\n".join(out).strip() + "\n"

    def subtitle_to_vtt(self, path: Path) -> str:
        data = path.read_bytes()[: 4 * 1024 * 1024]
        text = data.decode("utf-8-sig", "replace")
        ext = path.suffix.lower()
        if ext == ".vtt":
            return text if text.lstrip().startswith("WEBVTT") else "WEBVTT\n\n" + text
        if ext == ".srt":
            return self.srt_to_vtt(text)
        if ext in {".ass", ".ssa"}:
            return self.ass_to_vtt(text)
        return "WEBVTT\n\n" + text

    def ffprobe_video_info(self, path: Path) -> Dict[str, Any]:
        if not FFPROBE:
            return {}
        try:
            r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, timeout=12, errors="replace")
            if r.returncode != 0:
                return {}
            data = json.loads(r.stdout or "{}")
        except Exception:
            return {}
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        astream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        duration = self._float_or_none(vstream.get("duration")) or self._float_or_none(fmt.get("duration"))
        bitrate = vstream.get("bit_rate") or fmt.get("bit_rate")
        return {
            "duration": duration, "width": vstream.get("width"), "height": vstream.get("height"),
            "video_codec": vstream.get("codec_name") or "", "audio_codec": astream.get("codec_name") or "",
            "fps": self._fps(vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or ""),
            "bitrate": int(float(bitrate)) if bitrate not in (None, "", "N/A") else None,
            "bitrateText": self.bitrate_fmt(bitrate), "container": fmt.get("format_name") or "",
        }

    def video_info(self, path: Path) -> Dict[str, Any]:
        st = path.stat()
        rel = path.resolve().relative_to(self.cfg.root.resolve()).as_posix()
        info: Dict[str, Any] = {"ok": True, "name": path.name, "rel": rel, "size": st.st_size, "sizeText": self.files.size_fmt(st.st_size), "mtime": st.st_mtime, "mtimeText": self.files.mtime_fmt(st.st_mtime), "mime": mimetypes.guess_type(str(path))[0] or "application/octet-stream", "ffprobe": bool(FFPROBE)}
        info.update(self.ffprobe_video_info(path))
        subtitles = []
        for idx, sub in enumerate(self.video_subtitle_sidecars(path)):
            try:
                srel = sub.resolve().relative_to(self.cfg.root.resolve()).as_posix()
                lang = sub.stem[len(path.stem):].strip("._-") or f"s{idx}"
                subtitles.append({"name": sub.name, "rel": srel, "label": lang or sub.name, "lang": re.sub(r"[^A-Za-z0-9_-]+", "", lang)[:16] or f"s{idx}", "ext": sub.suffix.lower(), "url": f"/api/subtitle?p={urllib.parse.quote(rel)}&i={idx}"})
            except Exception:
                continue
        info["subtitles"] = subtitles
        return info

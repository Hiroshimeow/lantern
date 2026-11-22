
import hashlib
import html
import json
import os
import re
import shutil
import socket
import tempfile
import tarfile
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import AppConfig, config_file_default_path, normalize_conflict, normalize_sort, TEXT_EXTS, IMAGE_EXTS, VIDEO_EXTS, AUDIO_EXTS, ARCHIVE_EXTS, OFFICE_EXTS, SYSTEM_SKIP_NAMES, CHUNK_SIZE, MAX_ZIP_PAYLOAD

class BadRequest(ValueError):
    pass

class FileService:
    def __init__(self, config: AppConfig, plugin):
        self.cfg = config
        self.plugin = plugin


    def plugin_config_path(self) -> Path:
        try:
            return self.cfg.cache_dir / "plugin_config.json"
        except Exception:
            return Path(tempfile.gettempdir()) / "lan-drive-plugin-config.json"

    def plugin_enabled(self) -> bool:
        return self.plugin is not None

    def plugin_can_preview(self, path: Path) -> bool:
        if self.plugin is None:
            return False
        try:
            return bool(self.plugin.can_preview(path, self.plugin_config_path()))
        except Exception:
            return False

    def is_windows_drive_listing_request(self, rel: str) -> bool:
        return os.name == "nt" and rel in ("", "/") and str(self.cfg.root) in ("/", "\\")

    def is_protected_config(self, path: Path) -> bool:
        candidate = path.resolve()
        cfg = Path(getattr(self.cfg, "config_path", config_file_default_path())).resolve()
        return candidate == cfg or candidate.name.lower() == "lan_drive_config.yaml"

    def protect_config_mutation(self, path: Path) -> None:
        candidate = path.resolve()
        cfg = Path(getattr(self.cfg, "config_path", config_file_default_path())).resolve()
        if self.is_protected_config(candidate) or (candidate != self.cfg.root.resolve() and candidate in cfg.parents):
            raise PermissionError("Lantern authentication configuration is local-only")

    def safe_join(self, rel_url_path: str) -> Path:
        """Map URL path to filesystem path inside CONFIG.root."""
        raw = urllib.parse.unquote(rel_url_path.split("?", 1)[0].split("#", 1)[0])
        raw = raw.replace("\\", "/")
        parts = []
        for part in raw.split("/"):
            if not part or part in (".", ".."):
                continue
            if part.startswith((".lantern-uploading-", ".lantern-password-")):
                raise PermissionError("Internal staging files are not published")
            parts.append(part)
        candidate = self.cfg.root.joinpath(*parts).resolve()
        root = self.cfg.root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise PermissionError("Path is outside root")
        if self.is_protected_config(candidate):
            raise PermissionError("Lantern configuration is local-only")
        return candidate

    def rel_url_for_path(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self.cfg.root.resolve()).as_posix()
        except Exception:
            rel = path.name
        if not rel or rel == ".":
            return "/"
        return "/" + self.quote_path(rel)

    def quote_path(self, path: str) -> str:
        path = path.replace("\\", "/")
        return "/".join(urllib.parse.quote(p) for p in path.split("/"))

    def clean_name(self, name: str) -> str:
        name = name.replace("\x00", "").strip()
        name = name.replace("/", "_").replace("\\", "_")
        return name or f"unnamed-{int(time.time())}"

    def clean_component(self, name: str, *, fallback: Optional[str] = None) -> str:
        raw = str(name).replace("\x00", "").replace("/", "_").replace("\\", "_").strip()
        raw = "".join(ch for ch in raw if ch == "\t" or ord(ch) >= 32).strip()
        if not raw and fallback is not None:
            raw = fallback
        if not raw or raw in {".", ".."}:
            raise BadRequest("bad filename component")
        return raw

    def drain_stream(self, stream: Any, remaining: int) -> None:
        while remaining > 0:
            chunk = stream.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def ensure_under_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.cfg.root.resolve())
        except ValueError:
            raise PermissionError("Path is outside root")
        if self.is_protected_config(resolved):
            raise PermissionError("Lantern configuration is local-only")
        return resolved

    def payload_paths(self, data: Dict[str, Any], key: str = "paths") -> List[str]:
        raw = data.get(key)
        if raw is None and "path" in data:
            raw = [data.get("path")]
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raise BadRequest(f"{key} must be a list")
        out: List[str] = []
        for item in raw:
            rel = str(item or "").strip()
            if rel:
                out.append(rel)
        if not out:
            raise BadRequest("no paths supplied")
        return out

    def resolve_existing(self, rel: str) -> Path:
        p = self.safe_join("/" + self.quote_path(str(rel)))
        if not p.exists():
            raise BadRequest(f"not found: {rel}")
        return p

    def resolve_destination_dir(self, data: Dict[str, Any], default: str = "") -> Path:
        rel = str(data.get("dest") if data.get("dest") is not None else data.get("dest_dir", default))
        dest = self.safe_join("/" + self.quote_path(str(rel)))
        if dest.exists() and not dest.is_dir():
            raise BadRequest("destination is not a folder")
        dest.mkdir(parents=True, exist_ok=True)
        return self.ensure_under_root(dest)

    def split_stem_suffix(self, name: str) -> Tuple[str, str]:
        p = Path(name)
        return p.stem, p.suffix

    def unique_path(self, candidate: Path) -> Path:
        candidate = self.ensure_under_root(candidate)
        if not candidate.exists():
            return candidate
        stem, suffix = self.split_stem_suffix(candidate.name)
        for i in range(1, 10000):
            alt = candidate.with_name(f"{stem} ({i}){suffix}")
            if not alt.exists():
                return self.ensure_under_root(alt)
        raise BadRequest("cannot find free target name")

    def conflict_target(self, candidate: Path, conflict: str) -> Optional[Path]:
        conflict = normalize_conflict(conflict)
        candidate = self.ensure_under_root(candidate)
        if not candidate.exists():
            return candidate
        if conflict == "skip":
            return None
        if conflict == "rename":
            return self.unique_path(candidate)
        if conflict == "overwrite":
            return candidate
        raise BadRequest(f"target exists: {candidate.name}")

    def reject_self_nesting(self, src: Path, dest: Path) -> None:
        src_r, dest_r = src.resolve(), dest.resolve()
        if src_r == dest_r:
            raise BadRequest("source and destination are the same")
        if src.is_dir():
            try:
                dest_r.relative_to(src_r)
                raise BadRequest("cannot place a folder inside itself")
            except ValueError:
                pass

    def remove_existing_target(self, path: Path) -> None:
        self.protect_config_mutation(path)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()

    def copy_item(self, src: Path, dest_dir: Path, *, name: Optional[str] = None, conflict: str = "rename") -> Optional[Path]:
        self.protect_config_mutation(src)
        final_name = self.clean_component(name if name is not None else src.name)
        dest = self.conflict_target(dest_dir / final_name, conflict)
        if dest is None:
            return None
        self.reject_self_nesting(src, dest)
        if dest.exists() and normalize_conflict(conflict) == "overwrite":
            self.remove_existing_target(dest)
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, dest, symlinks=True, copy_function=shutil.copy2)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest, follow_symlinks=False)
        return dest

    def move_item(self, src: Path, dest_dir: Path, *, name: Optional[str] = None, conflict: str = "rename") -> Optional[Path]:
        final_name = self.clean_component(name if name is not None else src.name)
        dest = self.conflict_target(dest_dir / final_name, conflict)
        if dest is None:
            return None
        self.reject_self_nesting(src, dest)
        if dest.exists() and normalize_conflict(conflict) == "overwrite":
            self.remove_existing_target(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return dest

    def duplicate_name(self, src: Path) -> str:
        stem, suffix = self.split_stem_suffix(src.name)
        return f"{stem} copy{suffix}" if suffix else f"{src.name} copy"

    def unique_arcname(self, name: str, used: set[str]) -> str:
        clean = name.strip("/") or "item"
        if clean not in used:
            used.add(clean)
            return clean
        p = Path(clean)
        stem, suffix = p.stem, p.suffix
        parent = p.parent.as_posix()
        for i in range(1, 10000):
            cand = f"{stem} ({i}){suffix}"
            if parent not in ("", "."):
                cand = parent.rstrip("/") + "/" + cand
            if cand not in used:
                used.add(cand)
                return cand
        raise BadRequest("cannot allocate archive name")

    def iter_archive_entries(self, paths: List[Path]) -> Iterable[Tuple[Path, str]]:
        used: set[str] = set()
        for target in paths:
            top = self.unique_arcname(target.name, used)
            if target.is_dir() and not target.is_symlink():
                yielded = False
                for root, dirs, files in os.walk(target):
                    rootp = Path(root)
                    dirs[:] = [d for d in dirs if not self.should_hide_entry(rootp, d)]
                    for fn in files:
                        if self.should_hide_entry(rootp, fn):
                            continue
                        p = rootp / fn
                        try:
                            rel = p.relative_to(target).as_posix()
                        except Exception:
                            continue
                        yielded = True
                        yield p, top + "/" + rel
                if not yielded:
                    yield target, top + "/"
            else:
                yield target, top

    def parse_archive_payload(self, handler: Any) -> Dict[str, Any]:
        n = handler.content_length(max_bytes=MAX_ZIP_PAYLOAD)
        raw = handler.read_body_exact(n) if n else b""
        if not raw:
            return {}
        ctype = handler.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return json.loads(raw.decode("utf-8", "replace"))
        form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
        return json.loads(form.get("payload", ["{}"])[0])

    def archive_response_meta(self, fmt: str, compression: str) -> Tuple[str, str, str]:
        fmt = str(fmt or "zip").lower()
        compression = str(compression or "compress").lower()
        stamp = int(time.time())
        if fmt == "tar":
            if compression == "compress":
                return f"lan-drive-{stamp}.tar.gz", "application/gzip", "w|gz"
            return f"lan-drive-{stamp}.tar", "application/x-tar", "w|"
        if fmt != "zip":
            raise BadRequest("archive format must be zip or tar")
        return f"lan-drive-{stamp}.zip", "application/zip", "zip"

    def safe_extract_member_path(self, dest: Path, member_name: str) -> Path:
        name = str(member_name or "").replace("\\", "/")
        if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise BadRequest(f"unsafe archive member: {member_name}")
        parts = []
        for part in name.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise BadRequest(f"unsafe archive member: {member_name}")
            parts.append(self.clean_component(part))
        if not parts:
            raise BadRequest(f"unsafe archive member: {member_name}")
        return self.ensure_under_root(dest.joinpath(*parts))

    def write_extracted_file(self, src_file: Any, out_path: Path, conflict: str) -> Optional[Path]:
        target = self.conflict_target(out_path, conflict)
        if target is None:
            return None
        if target.exists() and normalize_conflict(conflict) == "overwrite":
            self.remove_existing_target(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp: Optional[Path] = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".extract-", dir=str(target.parent))
            tmp = Path(tmp_name)
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(src_file, out, CHUNK_SIZE)
            os.replace(tmp, target)
            tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        return target

    def extract_archive(self, archive_path: Path, dest: Path, conflict: str = "rename") -> Dict[str, Any]:
        written = 0
        skipped = 0
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as zf:
                for info in zf.infolist():
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        skipped += 1
                        continue
                    out_path = self.safe_extract_member_path(dest, info.filename)
                    if info.is_dir():
                        out_path.mkdir(parents=True, exist_ok=True)
                        continue
                    with zf.open(info) as src:
                        result = self.write_extracted_file(src, out_path, conflict)
                    if result is None:
                        skipped += 1
                    else:
                        written += 1
            return {"ok": True, "format": "zip", "written": written, "skipped": skipped}
        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as tf:
                for member in tf.getmembers():
                    out_path = self.safe_extract_member_path(dest, member.name)
                    if member.isdir():
                        out_path.mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        skipped += 1
                        continue
                    src = tf.extractfile(member)
                    if src is None:
                        skipped += 1
                        continue
                    with src:
                        result = self.write_extracted_file(src, out_path, conflict)
                    if result is None:
                        skipped += 1
                    else:
                        written += 1
            return {"ok": True, "format": "tar", "written": written, "skipped": skipped}
        raise BadRequest("unsupported archive; use zip/tar/tar.gz/tgz/tbz2/txz")

    def html_escape(self, s: Any) -> str:
        return html.escape(str(s), quote=True)

    def json_dumps(self, obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    def size_fmt(self, num: int) -> str:
        try:
            n = float(num)
        except Exception:
            return ""
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if n < 1024 or unit == "PB":
                if unit == "B":
                    return f"{int(n)} B"
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    def mtime_fmt(self, ts: float) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        except Exception:
            return ""

    def classify(self, path: Path, is_dir: bool = False) -> str:
        if is_dir:
            return "folder"

        name = path.name.lower()
        ext = path.suffix.lower()

        TEXT_NAMES = {
            "dockerfile",
            "makefile",
            "readme",
            "license",

            # dot/config files không có suffix thật
            ".env",
            ".gitignore",
            ".dockerignore",
            ".npmrc",
            ".yarnrc",
            ".pnpmrc",
            ".bashrc",
            ".zshrc",
            ".profile",
            ".bash_profile",
            ".bash_aliases",
            ".vimrc",
            ".editorconfig",
            ".prettierrc",
            ".eslintrc",

            # config/text files thường không có extension
            "authorized_keys",
            "known_hosts",
            "config",
            "hosts",
        }

        if ext in IMAGE_EXTS:
            return "image"
        if ext in VIDEO_EXTS:
            return "video"
        if ext in AUDIO_EXTS:
            return "audio"

        if (
            ext in TEXT_EXTS
            or name in TEXT_NAMES
            or name.startswith(".env.")      # .env.local, .env.production
            or name.startswith(".env-")      # .env-prod
        ):
            return "text"

        if ext == ".pdf":
            return "pdf"
        if ext in OFFICE_EXTS:
            return "office"
        if ext in ARCHIVE_EXTS:
            return "archive"
        return "file"

    def icon_for(self, kind: str) -> str:
        return {
            "folder": "📁", "image": "🖼️", "video": "🎬", "audio": "🎵", "text": "📝",
            "pdf": "📕", "office": "📄", "archive": "🗜️", "file": "📦",
        }.get(kind, "📦")

    def should_hide_entry(self, parent: Path, name: str, *, show_hidden: Optional[bool] = None, show_system: Optional[bool] = None) -> bool:
        # Avoid resolving every entry in a large directory. Only matching names
        # and symlinks need expensive realpath checks to hide the local YAML.
        if name.casefold() == "lan_drive_config.yaml":
            return True
        configured = getattr(self.cfg, "config_path", None)
        cfg_name = Path(configured).name.casefold() if configured else "lan_drive_config.yaml"
        if (name.casefold() == cfg_name or (parent / name).is_symlink()) and self.is_protected_config(parent / name):
            return True
        # Upload staging is never a published file, even when "show hidden" is on.
        if name.startswith((".lantern-uploading-", ".lantern-password-")):
            return True
        eff_hidden = self.cfg.show_hidden if show_hidden is None else bool(show_hidden)
        eff_system = self.cfg.show_system if show_system is None else bool(show_system)
        if not eff_hidden and name.startswith("."):
            return True
        if not eff_system:
            low = name.casefold()
            if low in {
                "$recycle.bin", "system volume information", "recovery",
                "$winreagent", "$sysreset", "config.msi", "msocache",
                "pagefile.sys", "hiberfil.sys", "swapfile.sys",
                "dumpstack.log.tmp", "thumbs.db", "desktop.ini",
            } or (name.startswith("$") and len(name) > 1):
                return True
            if os.name != "nt" and self.cfg.root == Path("/").resolve() and parent.resolve() == Path("/"):
                if name in SYSTEM_SKIP_NAMES:
                    return True
        return False

    def get_local_ip_guess(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def file_etag(self, path: Path, st: os.stat_result) -> str:
        raw = f"{path}:{st.st_size}:{st.st_mtime_ns}".encode("utf-8", "surrogateescape")
        return hashlib.sha1(raw).hexdigest()[:16]

    def entry_to_json(self, path: Path, dirent_name: str, st: os.stat_result, is_dir: bool, base_path: Optional[Path] = None) -> Dict[str, Any]:
        kind = self.classify(path, is_dir)
        rel_item = path.resolve().relative_to(self.cfg.root.resolve()).as_posix()
        version = self.file_etag(path, st) if not is_dir and kind in ("image", "video") else ""
        thumb = f"/api/thumb?p={urllib.parse.quote(rel_item)}&v={version}" if version else ""
        raw_media_url = "/" + self.quote_path(rel_item) + "?v=" + version if kind == "image" else ""
        search_path_text = ""
        if base_path is not None:
            try:
                parent_rel = path.resolve().parent.relative_to(base_path.resolve()).as_posix()
                if parent_rel != ".":
                    search_path_text = parent_rel
            except ValueError:
                search_path_text = ""
        return {
            "name": dirent_name,
            "nameEsc": self.html_escape(dirent_name),
            "nameLowerEsc": self.html_escape(dirent_name.lower()),
            "rel": rel_item,
            "relEsc": self.html_escape(rel_item),
            "relJs": self.html_escape(rel_item).replace("'", "&#39;"),
            "is_dir": is_dir,
            "kind": kind,
            "icon": self.icon_for(kind),
            "size": 0 if is_dir else st.st_size,
            "sizeText": "Folder" if is_dir else self.size_fmt(st.st_size),
            "sizeTextEsc": self.html_escape("Folder" if is_dir else self.size_fmt(st.st_size)),
            "mtime": st.st_mtime,
            "mtimeText": self.mtime_fmt(st.st_mtime),
            "mtimeTextEsc": self.html_escape(self.mtime_fmt(st.st_mtime)),
            "searchPathText": search_path_text,
            "searchPathTextEsc": self.html_escape(search_path_text),
            "ext": "" if is_dir else path.suffix.lower(),
            "size_text": "Folder" if is_dir else self.size_fmt(st.st_size),
            "mtime_text": self.mtime_fmt(st.st_mtime),
            "thumb": thumb,
            "url": raw_media_url,
            "preview": (not is_dir) and self.plugin_can_preview(path),
            "can_preview": (not is_dir) and self.plugin_can_preview(path),
        }

    def sort_key_for(self, name: str, is_dir: bool, st: Optional[os.stat_result], sort_mode: str, path: Optional[Path] = None) -> Any:
        lname = name.lower()
        ext = Path(name).suffix.lower().lstrip(".")
        if sort_mode.startswith("mtime"):
            return getattr(st, "st_mtime", 0.0)
        if sort_mode.startswith("size"):
            if is_dir:
                return -1
            return getattr(st, "st_size", 0)
        if sort_mode.startswith("type"):
            fake = path if path is not None else Path(name)
            return (self.classify(fake, is_dir), ext, lname)
        if sort_mode.startswith("ext"):
            return (ext, lname)
        return lname

    def list_entries_page(self, path: Path, offset: int, limit: int, sort_mode: str, query: str, folders_first: Optional[bool] = None, recursive_depth: Optional[int] = 0, show_hidden: Optional[bool] = None, show_system: Optional[bool] = None, media_filter: str = "") -> Tuple[List[Dict[str, Any]], int, bool, int, int]:
        offset = max(0, int(offset or 0))
        limit = max(20, min(int(limit or 220), 1000))
        query_l = (query or "").strip().lower()
        sort_mode = normalize_sort(sort_mode)
        reverse = sort_mode.endswith("desc")
        folders_first = self.cfg.folders_first if folders_first is None else bool(folders_first)
        # Recursive mode is only meaningful with a keyword. Without this guard, choosing
        # "all" at / would accidentally enumerate the whole root just to show a folder.
        recursive_enabled = bool(query_l) and recursive_depth != 0
        needs_stat = sort_mode.startswith("mtime") or sort_mode.startswith("size")
        rows: List[Any] = []
        errors = 0

        mf = str(media_filter or "").strip().lower()
        def _matches_media_filter(p: Path, is_dir: bool) -> bool:
            if not mf or mf == "all":
                return True
            if is_dir:
                return True
            k = self.classify(p, False)
            if mf == "image":
                return k == "image"
            if mf == "video":
                return k == "video"
            if mf == "media":
                return k in ("image", "video", "audio")
            return True

        def maybe_add_row(p: Path, name: str, is_dir: bool, st: Optional[os.stat_result], match_text: str) -> None:
            if query_l and query_l not in match_text.lower():
                return
            if not _matches_media_filter(p, is_dir):
                return
            key = self.sort_key_for(name, is_dir, st, sort_mode, p)
            rows.append((is_dir, key, name.lower(), name, st, p))

        if recursive_enabled:
            eff_show_hidden = self.cfg.show_hidden if show_hidden is None else bool(show_hidden)
            skip_heavy_dirs = set() if eff_show_hidden else {"node_modules", "__pycache__", ".git", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
            scanned_total = 0
            max_recursive_scan = 40000
            stack: List[Tuple[Path, int]] = [(path, 0)]
            while stack and scanned_total < max_recursive_scan:
                folder, depth = stack.pop()
                try:
                    with os.scandir(folder) as it:
                        entries = list(it)
                except OSError:
                    errors += 1
                    continue
                for de in entries:
                    scanned_total += 1
                    if scanned_total > max_recursive_scan:
                        break
                    name = de.name
                    if name in skip_heavy_dirs:
                        continue
                    if self.should_hide_entry(folder, name, show_hidden=show_hidden, show_system=show_system):
                        continue
                    p = folder / name
                    try:
                        is_dir = de.is_dir(follow_symlinks=False)
                        st = de.stat(follow_symlinks=False) if needs_stat else None
                        rel_under_search = p.relative_to(path).as_posix()
                        maybe_add_row(p, name, is_dir, st, f"{name}\n{rel_under_search}")
                        if is_dir and (recursive_depth is None or depth < recursive_depth):
                            stack.append((p, depth + 1))
                    except OSError:
                        errors += 1
        else:
            try:
                with os.scandir(path) as it:
                    for de in it:
                        name = de.name
                        if self.should_hide_entry(path, name, show_hidden=show_hidden, show_system=show_system):
                            continue
                        if query_l and query_l not in name.lower():
                            continue
                        try:
                            is_dir = de.is_dir(follow_symlinks=False)
                            item_p = path / name
                            if not _matches_media_filter(item_p, is_dir):
                                continue
                            st = de.stat(follow_symlinks=False) if needs_stat else None
                            key = self.sort_key_for(name, is_dir, st, sort_mode, item_p)
                            rows.append((is_dir, key, name.lower(), name, st, item_p))
                        except OSError:
                            errors += 1
            except OSError:
                raise

        def row_sort(row: Any) -> Any:
            is_dir, key, lname, _name, _st, _path = row
            if folders_first:
                # Keep folders at top, but sort folders by name for size sort so folders do not look random.
                group = 0 if is_dir else 1
                if is_dir and sort_mode.startswith("size"):
                    key = lname
                return (group, key, lname)
            return (key, lname)

        rows.sort(key=row_sort, reverse=reverse if not folders_first else False)
        if folders_first and reverse:
            # Reverse inside each group, not the folder/file grouping itself.
            dirs = [r for r in rows if r[0]]
            files = [r for r in rows if not r[0]]
            dirs.sort(key=lambda r: row_sort(r)[1:], reverse=True)
            files.sort(key=lambda r: row_sort(r)[1:], reverse=True)
            rows = dirs + files

        total = len(rows)
        page = rows[offset:offset + limit + 1]
        has_more = len(page) > limit
        page = page[:limit]
        out: List[Dict[str, Any]] = []
        for row in page:
            try:
                is_dir, _key, _lname, name, st, p = row
                if st is None:
                    st = p.stat()
                out.append(self.entry_to_json(p, name, st, is_dir, path if recursive_enabled else None))
            except OSError:
                errors += 1
        return out, offset + len(out), has_more, errors, total

    def _has_visible_subdir(self, folder: Path, *, show_hidden: Optional[bool] = None, show_system: Optional[bool] = None) -> bool:
        try:
            with os.scandir(folder) as it:
                for de in it:
                    if self.should_hide_entry(folder, de.name, show_hidden=show_hidden, show_system=show_system):
                        continue
                    try:
                        if de.is_dir(follow_symlinks=False):
                            return True
                    except OSError:
                        continue
        except OSError:
            return False
        return False

    def list_tree_children(self, path: Path, *, max_children: int = 500, show_hidden: Optional[bool] = None, show_system: Optional[bool] = None) -> Dict[str, Any]:
        """Return lazy-loadable child folders for Windows Explorer-style tree sidebar."""
        root = self.cfg.root.resolve()
        resolved = path.resolve()
        rel = resolved.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        children: List[Dict[str, Any]] = []
        errors = 0
        try:
            with os.scandir(resolved) as it:
                entries = list(it)
        except OSError:
            entries = []
            errors += 1

        dir_rows: List[Tuple[str, str, Path]] = []
        for de in entries:
            name = de.name
            if self.should_hide_entry(resolved, name, show_hidden=show_hidden, show_system=show_system):
                continue
            try:
                if de.is_dir(follow_symlinks=False):
                    dir_rows.append((name.lower(), name, resolved / name))
            except OSError:
                errors += 1

        dir_rows.sort(key=lambda r: r[0])
        total = len(dir_rows)
        truncated = total > max_children
        for _lname, name, child_path in dir_rows[:max_children]:
            child_rel = f"{rel}/{name}" if rel else name
            children.append({
                "name": name,
                "rel": child_rel,
                "href": "/" + self.quote_path(child_rel) + "/",
                "hasChildren": self._has_visible_subdir(child_path, show_hidden=show_hidden, show_system=show_system),
            })

        parent_rel = ""
        if rel:
            p = Path(rel).parent.as_posix()
            parent_rel = "" if p == "." else p
        return {
            "ok": True,
            "path": rel,
            "name": resolved.name or str(root),
            "href": "/" if not rel else "/" + self.quote_path(rel) + "/",
            "parent": parent_rel,
            "children": children,
            "total": total,
            "truncated": truncated,
            "errors": errors,
        }

    def list_tree_with_ancestors(self, path: Path, *, max_children: int = 500, show_hidden: Optional[bool] = None, show_system: Optional[bool] = None) -> Dict[str, Any]:
        """Return tree nodes for root and every ancestor down to `path` in one round-trip."""
        root = self.cfg.root.resolve()
        resolved = path.resolve()
        rel = resolved.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        parts = [p for p in rel.split("/") if p]
        nodes: Dict[str, Dict[str, Any]] = {}
        acc = root
        nodes[""] = self.list_tree_children(acc, max_children=max_children, show_hidden=show_hidden, show_system=show_system)
        cur_rel = ""
        for part in parts:
            acc = acc / part
            cur_rel = f"{cur_rel}/{part}" if cur_rel else part
            if acc.is_dir():
                nodes[cur_rel] = self.list_tree_children(acc, max_children=max_children, show_hidden=show_hidden, show_system=show_system)
        return {
            "ok": True,
            "rootName": root.name or str(root),
            "rootPath": str(root),
            "activePath": rel,
            "nodes": nodes,
        }

    def get_item_properties(self, path: Path, *, max_scan: int = 5000) -> Dict[str, Any]:
        """Return detailed Windows Explorer-style properties for a file or folder."""
        resolved = path.resolve()
        st = resolved.stat()
        is_dir = resolved.is_dir()
        rel = self.rel_url_for_path(resolved)
        kind = self.classify(resolved, is_dir)
        props: Dict[str, Any] = {
            "ok": True,
            "name": resolved.name or str(resolved),
            "rel": rel,
            "fullPath": str(resolved),
            "isDir": is_dir,
            "kind": kind,
            "ext": "" if is_dir else resolved.suffix.lower(),
            "mtime": st.st_mtime,
            "mtimeText": self.mtime_fmt(st.st_mtime),
            "ctime": st.st_ctime,
            "ctimeText": self.mtime_fmt(st.st_ctime),
        }
        if is_dir:
            file_count = 0
            dir_count = 0
            total_bytes = 0
            truncated = False
            stack = [resolved]
            scanned = 0
            while stack:
                cur = stack.pop()
                try:
                    with os.scandir(cur) as it:
                        for de in it:
                            scanned += 1
                            if scanned > max_scan:
                                truncated = True
                                break
                            if self.should_hide_entry(cur, de.name):
                                continue
                            try:
                                if de.is_dir(follow_symlinks=False):
                                    dir_count += 1
                                    stack.append(cur / de.name)
                                else:
                                    file_count += 1
                                    total_bytes += de.stat(follow_symlinks=False).st_size
                            except OSError:
                                continue
                except OSError:
                    continue
                if truncated:
                    break
            props.update({
                "size": total_bytes,
                "sizeText": self.size_fmt(total_bytes) + ("+" if truncated else ""),
                "files": file_count,
                "folders": dir_count,
                "truncated": truncated,
            })
        else:
            import mimetypes as _mt
            mime = _mt.guess_type(str(resolved))[0] or "application/octet-stream"
            props.update({
                "size": st.st_size,
                "sizeText": self.size_fmt(st.st_size),
                "mime": mime,
            })
            if kind == "image":
                dims = self._read_image_dimensions(resolved)
                if dims:
                    props["width"], props["height"], props["format"] = dims
        return props

    def _read_image_dimensions(self, path: Path) -> Optional[Tuple[int, int, str]]:
        """Read image (width, height, format) via Pillow or pure-Python binary header fallback."""
        try:
            from PIL import Image
            with Image.open(path) as im:
                return int(im.size[0]), int(im.size[1]), str(im.format or "")
        except Exception:
            pass
        import struct as _struct
        try:
            with open(path, "rb") as f:
                head = f.read(32)
                if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
                    w, h = _struct.unpack(">II", head[16:24])
                    return int(w), int(h), "PNG"
                if len(head) >= 10 and head[:6] in (b"GIF87a", b"GIF89a"):
                    w, h = _struct.unpack("<HH", head[6:10])
                    return int(w), int(h), "GIF"
                if len(head) >= 26 and head[:2] == b"BM":
                    w, h = _struct.unpack("<ii", head[18:26])
                    return abs(int(w)), abs(int(h)), "BMP"
                if len(head) >= 30 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                    chunk = head[12:16]
                    if chunk == b"VP8X":
                        w = 1 + int.from_bytes(head[24:27], "little")
                        h = 1 + int.from_bytes(head[27:30], "little")
                        return w, h, "WEBP"
                    if chunk == b"VP8 " and len(head) >= 30:
                        w, h = _struct.unpack("<HH", head[26:30])
                        return w & 0x3FFF, h & 0x3FFF, "WEBP"
                    if chunk == b"VP8L" and len(head) >= 25:
                        b0, b1, b2, b3 = head[21:25]
                        w = 1 + (((b1 & 0x3F) << 8) | b0)
                        h = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
                        return w, h, "WEBP"
                if len(head) >= 2 and head[:2] == b"\xff\xd8":
                    f.seek(2)
                    while True:
                        marker = f.read(2)
                        if len(marker) < 2:
                            break
                        while marker[0] == 0xFF and marker[1] == 0xFF:
                            nxt = f.read(1)
                            if not nxt:
                                break
                            marker = b"\xff" + nxt
                        if marker[0] != 0xFF:
                            break
                        code = marker[1]
                        if code in (0xD8, 0xD9, 0x01) or (0xD0 <= code <= 0xD7):
                            continue
                        seg_len_b = f.read(2)
                        if len(seg_len_b) < 2:
                            break
                        seg_len = _struct.unpack(">H", seg_len_b)[0]
                        if code in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                            sof = f.read(5)
                            if len(sof) == 5:
                                h, w = _struct.unpack(">HH", sof[1:5])
                                return int(w), int(h), "JPEG"
                            break
                        if seg_len < 2:
                            break
                        f.seek(seg_len - 2, 1)
        except Exception:
            return None
        return None

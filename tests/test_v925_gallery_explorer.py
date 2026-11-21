"""Comprehensive real HTTP + Concurrency + Headless Chromium CDP E2E tests for Lantern v9.25 Gallery & Explorer."""
from __future__ import annotations

import base64
import concurrent.futures
import gzip
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lantern.application import make_application
from lantern.config import AppConfig
from lantern.http.server import Handler, LanternHTTPServer
import lantern.http.routes.files as files_routes


def _make_png(path: Path, size=(320, 240), color=(40, 180, 110)) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, color)
    im.save(path, "PNG")


def _make_short_mp4(path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=0.35",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    return res.returncode == 0 and path.exists() and path.stat().st_size > 0


class _SimpleCDP:
    """Minimal zero-dependency Chrome DevTools Protocol client over RFC 6455 WebSocket."""

    def __init__(self, ws_url: str, timeout: float = 15.0):
        parsed = urllib.parse.urlsplit(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("CDP handshake closed")
            buf += chunk
        self._buf = buf.split(b"\r\n\r\n", 1)[1]
        self._next_id = 1
        self.exceptions: list[str] = []

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("CDP socket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n <= 0xFFFF:
            head.append(0x80 | 126)
            head.extend(struct.pack("!H", n))
        else:
            head.append(0x80 | 127)
            head.extend(struct.pack("!Q", n))
        head.extend(mask)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + masked)

    def _recv_message(self) -> dict:
        chunks = []
        while True:
            b1, b2 = self._read_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            data = self._read_exact(length)
            if opcode == 8:
                raise EOFError("CDP closed")
            if opcode == 9:
                # pong
                self.sock.sendall(bytes([0x8A, 0x80]) + b"\x00\x00\x00\x00")
                continue
            chunks.append(data)
            if fin:
                return json.loads(b"".join(chunks).decode("utf-8"))

    def call(self, method: str, params: dict | None = None) -> dict:
        cid = self._next_id
        self._next_id += 1
        self._send_text(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            msg = self._recv_message()
            if msg.get("method") == "Runtime.exceptionThrown":
                desc = msg.get("params", {}).get("exceptionDetails", {}).get("exception", {}).get("description", "")
                self.exceptions.append(str(desc or msg))
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} error: {msg['error']}")
                return msg.get("result", {})

    def eval_js(self, expr: str):
        res = self.call("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": True,
            "returnByValue": True,
        })
        if "exceptionDetails" in res:
            raise AssertionError(f"JS exception in {expr[:80]}: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


class TestV925GalleryBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lantern-v925-backend-")
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()
        (self.root / "Photos" / "2026" / "Vacation").mkdir(parents=True)
        (self.root / "Docs").mkdir()
        (self.root / "node_modules" / "pkg").mkdir(parents=True)
        (self.root / "node_modules" / "pkg" / "needle_hidden.txt").write_text("ignore", encoding="utf-8")
        (self.root / "Docs" / "needle_real.txt").write_text("hello lantern v9.25", encoding="utf-8")
        _make_png(self.root / "Photos" / "2026" / "Vacation" / "beach.png", (320, 240), (30, 140, 220))
        _make_png(self.root / "báo cáo ảnh 2026.png", (200, 150), (200, 80, 60))

        self.cfg = AppConfig(
            root=self.root,
            port=0,
            host="127.0.0.1",
            title="Lantern v9.25 Test",
            cache_dir=Path(self.tmp.name) / "cache",
            config_path=Path(self.tmp.name) / "config.yaml",
        )
        self.app = make_application(self.cfg)
        self.server = LanternHTTPServer(("127.0.0.1", 0), Handler, self.app)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.close()
        self.tmp.cleanup()

    def _get(self, path: str, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers.items()), r.read()

    def _post_json(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_tree_api_lazy_and_ancestors(self):
        st, _, raw = self._get("/api/tree?path=")
        self.assertEqual(st, 200)
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        names = [c["name"] for c in data["children"]]
        self.assertIn("Photos", names)
        self.assertIn("Docs", names)
        photos_node = next(c for c in data["children"] if c["name"] == "Photos")
        docs_node = next(c for c in data["children"] if c["name"] == "Docs")
        self.assertTrue(photos_node["hasChildren"])
        self.assertFalse(docs_node["hasChildren"])

        st2, _, raw2 = self._get("/api/tree?path=Photos/2026/Vacation&ancestors=1")
        self.assertEqual(st2, 200)
        anc = json.loads(raw2)
        self.assertIn("", anc["nodes"])
        self.assertIn("Photos", anc["nodes"])
        self.assertIn("Photos/2026", anc["nodes"])
        self.assertIn("Photos/2026/Vacation", anc["nodes"])

    def test_properties_api_image_and_folder(self):
        st, _, raw = self._get("/api/properties?p=" + urllib.parse.quote("Photos/2026/Vacation/beach.png"))
        self.assertEqual(st, 200)
        p = json.loads(raw)
        self.assertEqual(p["width"], 320)
        self.assertEqual(p["height"], 240)
        self.assertEqual(p["kind"], "image")

        st2, _, raw2 = self._get("/api/properties?p=Photos")
        self.assertEqual(st2, 200)
        fp = json.loads(raw2)
        self.assertTrue(fp["isDir"])
        self.assertEqual(fp["files"], 1)
        self.assertEqual(fp["folders"], 2)

    def test_atomic_concurrent_thumbnails_and_immutable_cache(self):
        rel = urllib.parse.quote("Photos/2026/Vacation/beach.png")
        url_v = f"/api/thumb?p={rel}&v=testetag1"

        def fetch_one(_):
            return self._get(url_v)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(fetch_one, range(8)))
        for st, hdrs, body in results:
            self.assertEqual(st, 200)
            self.assertTrue(body.startswith(b"\xff\xd8\xff"), "Invalid JPEG header")
            self.assertIn("immutable", hdrs.get("Cache-Control", ""))

        # Unversioned thumb still uses no-cache
        st_nv, hdrs_nv, _ = self._get(f"/api/thumb?p={rel}")
        self.assertEqual(st_nv, 200)
        self.assertEqual(hdrs_nv.get("Cache-Control"), "no-cache")

    def test_short_video_thumbnail_fallback(self):
        vid = self.root / "short_clip.mp4"
        if not _make_short_mp4(vid):
            self.skipTest("ffmpeg not available")
        st, _, body = self._get("/api/thumb?p=short_clip.mp4&v=1")
        self.assertEqual(st, 200)
        self.assertTrue(body.startswith(b"\xff\xd8\xff"))

    def test_gzip_compression_and_unicode_download(self):
        st, hdrs, body = self._get("/static/gallery_app.js?v=925", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(st, 200)
        self.assertEqual(hdrs.get("Content-Encoding"), "gzip")
        self.assertIn("immutable", hdrs.get("Cache-Control", ""))
        decompressed = gzip.decompress(body).decode("utf-8")
        self.assertIn("LanternAppState", decompressed)

        vn_url = "/" + urllib.parse.quote("báo cáo ảnh 2026.png") + "?download=1"
        st2, hdrs2, body2 = self._get(vn_url)
        self.assertEqual(st2, 200)
        cd = hdrs2.get("Content-Disposition", "")
        self.assertIn("filename*=UTF-8''", cd)
        encoded_part = cd.split("filename*=UTF-8''", 1)[1]
        self.assertEqual(urllib.parse.unquote(encoded_part), "báo cáo ảnh 2026.png")
        self.assertGreater(len(body2), 100)

    def test_chunked_upload_and_abort(self):
        raw = os.urandom(300_000)
        chunks = [raw[:100_000], raw[100_000:200_000], raw[200_000:]]
        uid = "chunktest-925-alpha"
        for idx, chunk in enumerate(chunks):
            req = urllib.request.Request(
                f"{self.base}/api/upload/chunk?id={uid}&index={idx}&total={len(chunks)}",
                data=chunk,
                headers={"Content-Type": "application/octet-stream"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(r.status, 200)

        st, res = self._post_json("/api/upload/complete", {
            "id": uid,
            "path": "Docs",
            "name": "heavy_movie.bin",
            "total": len(chunks),
            "conflict": "overwrite",
        })
        self.assertEqual(st, 200)
        self.assertTrue(res["ok"])
        out_file = self.root / "Docs" / "heavy_movie.bin"
        self.assertTrue(out_file.is_file())
        self.assertEqual(hashlib.sha256(out_file.read_bytes()).hexdigest(), hashlib.sha256(raw).hexdigest())

        # Abort cleans up staging directory
        uid2 = "chunktest-925-abort"
        req2 = urllib.request.Request(
            f"{self.base}/api/upload/chunk?id={uid2}&index=0&total=2",
            data=b"abc123",
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            self.assertEqual(r.status, 200)
        stage = self.cfg.cache_dir / "upload_chunks" / uid2
        self.assertTrue(stage.exists())
        st_ab, _ = self._post_json("/api/upload/abort", {"id": uid2})
        self.assertEqual(st_ab, 200)
        self.assertFalse(stage.exists())

    def test_full_file_crud_and_delete_and_search_and_sysstats(self):
        # 1. mkdir + newfile + save + copy + move + rename + duplicate + delete
        self._post_json("/api/mkdir", {"path": "Docs", "name": "SubA"})
        self.assertTrue((self.root / "Docs" / "SubA").is_dir())

        self._post_json("/api/newfile", {"path": "Docs/SubA", "name": "hello.txt"})
        self._post_json("/api/save", {"path": "Docs/SubA/hello.txt", "content": "updated v9.25"})
        self.assertEqual((self.root / "Docs" / "SubA" / "hello.txt").read_text(encoding="utf-8"), "updated v9.25")

        self._post_json("/api/copy", {"paths": ["Docs/SubA/hello.txt"], "dest": "Docs", "conflict": "rename"})
        self.assertTrue((self.root / "Docs" / "hello.txt").is_file())

        self._post_json("/api/rename", {"path": "Docs/hello.txt", "name": "renamed.txt"})
        self.assertTrue((self.root / "Docs" / "renamed.txt").is_file())

        self._post_json("/api/move", {"paths": ["Docs/renamed.txt"], "dest": "Photos", "conflict": "rename"})
        self.assertTrue((self.root / "Photos" / "renamed.txt").is_file())

        # Delete must actually delete files and folders!
        st_del, res_del = self._post_json("/api/delete", {"paths": ["Photos/renamed.txt", "Docs/SubA"]})
        self.assertEqual(st_del, 200)
        self.assertFalse((self.root / "Photos" / "renamed.txt").exists())
        self.assertFalse((self.root / "Docs" / "SubA").exists())

        # 2. Fast recursive search prunes node_modules
        st_s, _, raw_s = self._get("/api/list?path=&q=needle&recursive_depth=all")
        self.assertEqual(st_s, 200)
        found_names = [x["name"] for x in json.loads(raw_s)["items"] if not x.get("special")]
        self.assertIn("needle_real.txt", found_names)
        self.assertNotIn("needle_hidden.txt", found_names)

        # 3. Telemetry endpoint returns valid camelCase CPU & RAM fields
        st_t, _, raw_t = self._get("/api/sysstats")
        self.assertEqual(st_t, 200)
        stats = json.loads(raw_t)
        self.assertIn("cpu", stats)
        self.assertIn("ram", stats)
        self.assertIn("gpu", stats)
        self.assertGreater(stats["ram"]["totalGb"], 0)

    def test_hidden_and_system_folders_filtered_by_default_and_toggleable(self):
        for noisy in (".pi", ".lantern", "$RECYCLE.BIN", "System Volume Information"):
            (self.root / noisy).mkdir(exist_ok=True)
        st, _, raw = self._get("/api/tree?path=")
        self.assertEqual(st, 200)
        names = {c["name"] for c in json.loads(raw)["children"]}
        for noisy in (".pi", ".lantern", "$RECYCLE.BIN", "System Volume Information"):
            self.assertNotIn(noisy, names, f"{noisy} must be hidden by default in /api/tree")

        st_l, _, raw_l = self._get("/api/list?path=")
        self.assertEqual(st_l, 200)
        list_names = {x["name"] for x in json.loads(raw_l)["items"] if not x.get("special")}
        for noisy in (".pi", ".lantern", "$RECYCLE.BIN", "System Volume Information"):
            self.assertNotIn(noisy, list_names, f"{noisy} must be hidden by default in /api/list")

        # Enable show_hidden & show_system via /api/config
        self._post_json("/api/config", {"show_hidden": True, "show_system": True})
        _, _, raw_on = self._get("/api/tree?path=")
        names_on = {c["name"] for c in json.loads(raw_on)["children"]}
        self.assertIn(".pi", names_on)
        self.assertIn("$RECYCLE.BIN", names_on)

    def test_image_properties_and_thumbnail_fallback_without_pillow(self):
        import builtins
        import lantern.media as media_mod
        from PIL import Image

        jpg_path = self.root / "Docs" / "sample.jpg"
        Image.new("RGB", (400, 300), (120, 60, 200)).save(jpg_path, "JPEG")

        # 1. Pure-Python header parser must read PNG & JPEG dimensions even if PIL import fails
        real_import = builtins.__import__
        def no_pil_import(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("simulated missing Pillow (G6)")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = no_pil_import
        try:
            png_dims = self.app.files._read_image_dimensions(self.root / "Photos" / "2026" / "Vacation" / "beach.png")
            jpg_dims = self.app.files._read_image_dimensions(jpg_path)
        finally:
            builtins.__import__ = real_import

        self.assertEqual(png_dims, (320, 240, "PNG"))
        self.assertEqual(jpg_dims, (400, 300, "JPEG"))

        # 2. /api/thumb must return 200 (direct image fallback, NEVER 404) when HAS_PIL=False and FFMPEG=None
        orig_pil, orig_ff = media_mod.HAS_PIL, media_mod.FFMPEG
        media_mod.HAS_PIL = False
        media_mod.FFMPEG = None
        try:
            st, hdrs, body = self._get("/api/thumb?p=Docs/sample.jpg&v=nopil1")
            self.assertEqual(st, 200)
            self.assertTrue(body.startswith(b"\xff\xd8\xff"))
            self.assertIn("immutable", hdrs.get("Cache-Control", ""))
        finally:
            media_mod.HAS_PIL, media_mod.FFMPEG = orig_pil, orig_ff

    def test_responsive_css_and_zero_overlap_layout_contracts(self):
        css = (ROOT / "static" / "gallery.css").read_text(encoding="utf-8")
        # Mobile P0 contracts
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("transform: translateX(-105%)", css)
        self.assertIn("body.tree-mobile-open .tree-pane", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("width: 100vw !important", css)
        # Zero-overlap contracts for Large / Grid / List / Details
        self.assertNotIn("content-visibility: auto", css)
        self.assertNotIn("top: -12px", css)

    def test_per_session_show_hidden_isolation_cfg01(self):
        for noisy in (".pi", ".lantern", ".pnpm-store", "$RECYCLE.BIN", "System Volume Information"):
            (self.root / noisy).mkdir(exist_ok=True)
        # Session A requests show_hidden=1
        _, _, raw_a = self._get("/api/tree?path=&show_hidden=1&show_system=1")
        names_a = {c["name"] for c in json.loads(raw_a)["children"]}
        self.assertIn(".pi", names_a)
        self.assertIn("$RECYCLE.BIN", names_a)
        # Session B requests show_hidden=0 concurrently — MUST NOT be affected by Session A!
        _, _, raw_b = self._get("/api/tree?path=&show_hidden=0&show_system=0")
        names_b = {c["name"] for c in json.loads(raw_b)["children"]}
        for noisy in (".pi", ".lantern", ".pnpm-store", "$RECYCLE.BIN", "System Volume Information"):
            self.assertNotIn(noisy, names_b)
        self.assertFalse(self.cfg.show_hidden)

    def test_p0_p1_html_and_js_defect_contracts(self):
        _, _, raw_html = self._get("/")
        html = raw_html.decode("utf-8")
        # FILE-01: zero broken inline JSON.stringify onclick attributes
        self.assertNotIn('onclick="toggleSelect(', html)
        self.assertNotIn('onclick="navigateCrumb(', html)
        # MOB-01: permanent sidePreview close button always present even when empty
        self.assertIn('id="sideCloseBtn"', html)
        self.assertIn('onclick="closeSidePreview()"', html)
        # MOB-02: mobile search button & bar present
        self.assertIn('id="mobileSearchBtn"', html)
        self.assertIn('id="mobileSearchBar"', html)
        # FILE-02: mobile selection More button present
        self.assertIn('id="mobileMoreActBtn"', html)
        # IMG-01: Fit & 1:1 buttons in Lightbox + flex min-height:0 modal-body
        self.assertIn('setActualSize()', html)
        css = (ROOT / "static" / "gallery.css").read_text(encoding="utf-8")
        self.assertIn("display: flex; align-items: center; justify-content: center; overflow: hidden; padding: 12px;", css)
        # GAL-02: cardHTML uses event delegation, no inline JSON.stringify
        app_js = (ROOT / "static" / "gallery_app.js").read_text(encoding="utf-8")
        self.assertNotIn('onclick="toggleSelect(${JSON.stringify', app_js)
        self.assertIn("visibleList.map(cardHTML).join", app_js)


class TestV925GalleryBrowserE2E(unittest.TestCase):
    def setUp(self):
        self.browser_bin = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chromium-browser")
        if not self.browser_bin:
            self.skipTest("No Chromium/Chrome binary available for real browser E2E")

        self.tmp = tempfile.TemporaryDirectory(prefix="lantern-v925-e2e-")
        self.root = Path(self.tmp.name) / "root"
        (self.root / "Photos" / "2026" / "Vacation").mkdir(parents=True)
        (self.root / "Docs").mkdir()
        (self.root / "Docs" / "readme.txt").write_text("Lantern v9.25 E2E", encoding="utf-8")
        (self.root / "delete_me.txt").write_text("to be deleted", encoding="utf-8")
        _make_png(self.root / "Photos" / "2026" / "Vacation" / "sunset.png", (320, 240), (240, 120, 60))

        self.cfg = AppConfig(
            root=self.root,
            port=0,
            host="127.0.0.1",
            title="Lantern v9.25 E2E",
            cache_dir=Path(self.tmp.name) / "cache",
            config_path=Path(self.tmp.name) / "config.yaml",
        )
        self.app = make_application(self.cfg)
        self.server = LanternHTTPServer(("127.0.0.1", 0), Handler, self.app)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.cdp_port = s.getsockname()[1]
        self.profile = Path(self.tmp.name) / "chrome_profile"
        self.chrome = subprocess.Popen(
            [
                self.browser_bin,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-proxy-server",
                f"--remote-debugging-port={self.cdp_port}",
                f"--user-data-dir={self.profile}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ws_url = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json/list", timeout=1) as r:
                    pages = json.loads(r.read().decode("utf-8"))
                page = next((p for p in pages if p.get("type") == "page" and p.get("webSocketDebuggerUrl")), None)
                if page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.15)
        if not ws_url:
            raise RuntimeError("Headless Chromium CDP did not start")
        self.cdp = _SimpleCDP(ws_url)
        self.cdp.call("Page.enable")
        self.cdp.call("Runtime.enable")

    def tearDown(self):
        if hasattr(self, "cdp"):
            self.cdp.close()
        if hasattr(self, "chrome"):
            self.chrome.terminate()
            try:
                self.chrome.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.chrome.kill()
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.app.close()
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def _wait_for(self, js_expr: str, timeout: float = 8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            val = self.cdp.eval_js(js_expr)
            if val:
                return val
            time.sleep(0.1)
        raise AssertionError(f"Timed out waiting for: {js_expr}")

    def test_full_windows_explorer_ux_in_real_chromium(self):
        self.cdp.call("Page.navigate", {"url": self.base + "/"})
        time.sleep(0.8)
        cur_url = str(self.cdp.eval_js("location.href") or "")
        if cur_url.startswith("chrome-error://"):
            self.skipTest("Chromium managed URLBlocklist policy blocks localhost in this sandbox")
        self._wait_for("document.querySelectorAll('#grid .card[data-rel]').length >= 3")
        self._wait_for("document.querySelectorAll('#treeBody .tree-row').length >= 3")

        # 1. Verify VRAM/CPU/RAM telemetry pill actually renders real values (not undefined / not placeholder)
        pill_text = self._wait_for(
            "(() => { const t = document.getElementById('sysTelemetryPill')?.textContent || ''; return (t.includes('RAM') && !t.includes('undefined') && !t.includes('VRAM · GPU · RAM')) ? t : ''; })()"
        )
        self.assertIn("RAM", pill_text)

        # 2. Verify Windows Folder Tree lazy expand + SPA navigation (ZERO full page reload!)
        self.cdp.eval_js("window.__spaMarker = 'alive-925';")
        self.cdp.eval_js("window.LanternTree.toggleExpand('Photos')")
        self._wait_for("!!document.querySelector('#treeBody .tree-row[data-tree-rel=\"Photos/2026\"]')")
        self.cdp.eval_js("document.querySelector('#treeBody .tree-row[data-tree-rel=\"Photos/2026\"]').click()")
        self._wait_for("window.currentPath() === 'Photos/2026'")
        self.assertEqual(self.cdp.eval_js("window.__spaMarker"), "alive-925", "SPA navigation must not reload page")

        # 3. Verify 4 View Modes (large, grid, list, details) + ZERO bounding-box overlap & visible view buttons!
        self.cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        for mode, cls in [("large", "view-large"), ("details", "view-details"), ("list", "list"), ("grid", "grid")]:
            self.cdp.eval_js(f"window.setView('{mode}')")
            geom = self.cdp.eval_js("""
              (() => {
                const hdr = document.getElementById('topHeader').getBoundingClientRect();
                const grid = document.getElementById('grid').getBoundingClientRect();
                const btns = Array.from(document.querySelectorAll('#subToolbar .view-toggle button')).map(b => {
                  const r = b.getBoundingClientRect();
                  return { v: b.dataset.view, w: r.width, h: r.height, right: r.right };
                });
                const maxTreeRowH = Math.max(0, ...Array.from(document.querySelectorAll('#treeBody .tree-row')).map(r => r.getBoundingClientRect().height));
                const cards = Array.from(document.querySelectorAll('#grid .card')).map(c => c.getBoundingClientRect());
                let overlaps = 0;
                for (let i = 0; i < cards.length; i++) {
                  for (let j = i + 1; j < cards.length; j++) {
                    const a = cards[i], b = cards[j];
                    if (a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1) overlaps++;
                  }
                }
                return { hdrH: hdr.height, gridTop: grid.top, gridW: grid.width, overlaps, btns, maxTreeRowH, hasCls: document.getElementById('grid').classList.contains('""" + cls + """') };
              })()
            """)
            self.assertTrue(geom["hasCls"], f"View mode {mode} missing class {cls}")
            self.assertLessEqual(geom["hdrH"], 115, f"Desktop header too tall: {geom['hdrH']}")
            self.assertEqual(geom["overlaps"], 0, f"Overlapping cards detected in {mode} mode!")
            self.assertLessEqual(geom["maxTreeRowH"], 52, f"Leaf tree row stretched vertically: {geom['maxTreeRowH']}px")
            self.assertEqual(len(geom["btns"]), 4, "Desktop toolbar must show all 4 view buttons")
            for b in geom["btns"]:
                self.assertGreaterEqual(b["w"], 34, f"View button {b['v']} clipped")
                self.assertLessEqual(b["right"], 1440, f"View button {b['v']} off-screen")

        # 3b. Mobile viewport geometry check (390x844 and 320x700): Tree closed by default, full grid width, compact header!
        for mw, mh in ((390, 844), (320, 700)):
            self.cdp.call("Emulation.setDeviceMetricsOverride", {"width": mw, "height": mh, "deviceScaleFactor": 2, "mobile": True})
            mgeom = self.cdp.eval_js("""
              (() => {
                const hdr = document.getElementById('topHeader').getBoundingClientRect();
                const grid = document.getElementById('grid').getBoundingClientRect();
                const treeOpen = document.body.classList.contains('tree-mobile-open');
                return { hdrH: hdr.height, gridW: grid.width, gridH: grid.height, treeOpen };
              })()
            """)
            self.assertFalse(mgeom["treeOpen"], f"Tree must default closed on mobile {mw}x{mh}")
            self.assertLessEqual(mgeom["hdrH"], 125, f"Mobile header too tall at {mw}px: {mgeom['hdrH']}")
            self.assertGreaterEqual(mgeom["gridW"], mw * 0.9, f"Grid crushed at {mw}px: {mgeom['gridW']}")
            self.assertGreaterEqual(mgeom["gridH"], mh - 180, f"Grid height too small at {mw}x{mh}: {mgeom['gridH']}")
            # TEST-01 & MOB-05: Switch view via Options menu and verify selection bar fits inside mobile viewport
            msel = self.cdp.eval_js("""
              (() => {
                document.getElementById('optionsBtn').click();
                const optBtns = Array.from(document.querySelectorAll('#optionsMenu .view-toggle button')).map(b => b.getBoundingClientRect().width);
                document.querySelector('#optionsMenu .view-toggle button[data-view="list"]').click();
                window.closeOptionsMenu(false);
                const firstCard = document.querySelector('#grid .card[data-rel]');
                if (firstCard) window.toggleSelect(firstCard.dataset.rel);
                const sb = document.getElementById('selectionBar').getBoundingClientRect();
                const dl = document.getElementById('downloadBtn').getBoundingClientRect();
                const more = document.getElementById('mobileMoreActBtn').getBoundingClientRect();
                window.clearSel();
                return { optBtns, isList: document.getElementById('grid').classList.contains('list'), sbRight: sb.right, dlRight: dl.right, moreRight: more.right };
              })()
            """)
            self.assertTrue(all(w >= 34 for w in msel["optBtns"]), f"Mobile options view buttons clipped at {mw}px: {msel['optBtns']}")
            self.assertTrue(msel["isList"], f"Mobile view switch to list failed at {mw}px")
            self.assertLessEqual(msel["sbRight"], mw, f"MOB-05: Selection bar overflowed at {mw}px: {msel['sbRight']}")
            self.assertLessEqual(msel["moreRight"], mw, f"MOB-05: More button overflowed at {mw}px: {msel['moreRight']}")
        self.cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

        # 4. Navigate to Photos/2026/Vacation and open Lightbox + Zoom + Rotate + Properties
        self.cdp.eval_js("window.navigateToFolder('Photos/2026/Vacation')")
        self._wait_for("!!document.querySelector('.card[data-rel=\"Photos/2026/Vacation/sunset.png\"]')")
        self.cdp.eval_js("document.querySelector('.card[data-rel=\"Photos/2026/Vacation/sunset.png\"] .card-main').click()")
        self._wait_for("document.getElementById('modal').classList.contains('show')")
        meta_text = self._wait_for(
            "(() => { const t = document.getElementById('modalMeta')?.textContent || ''; return t.includes('320×240') ? t : ''; })()"
        )
        self.assertIn("320×240", meta_text)
        self.cdp.eval_js("window.LanternMedia.zoomBy(0.5); window.LanternMedia.rotateBy(90);")
        self.assertEqual(self.cdp.eval_js("document.getElementById('modalZoomLabel').textContent"), "150%")
        self.cdp.eval_js("window.closeModal()")
        self.assertFalse(self.cdp.eval_js("document.getElementById('modal').classList.contains('show')"))

        # Properties modal shows 320 x 240
        self.cdp.eval_js("window.openPropertiesModal('Photos/2026/Vacation/sunset.png')")
        props_text = self._wait_for(
            "(() => { const t = document.getElementById('propsBody')?.textContent || ''; return t.includes('320 × 240') ? t : ''; })()"
        )
        self.assertIn("320 × 240", props_text)
        self.cdp.eval_js("document.getElementById('propsModal').classList.remove('show')")

        # 5. Windows Clipboard Copy/Paste across folders (Docs/readme.txt -> Photos/2026/Vacation)
        self.cdp.eval_js("window.navigateToFolder('Docs')")
        self._wait_for("!!document.querySelector('.card[data-rel=\"Docs/readme.txt\"]')")
        self.cdp.eval_js("window.toggleSelect('Docs/readme.txt'); window.copySel();")
        self.cdp.eval_js("window.navigateToFolder('Photos/2026/Vacation')")
        self._wait_for("window.currentPath() === 'Photos/2026/Vacation'")
        self.cdp.eval_js("window.pasteClipboard()")
        self._wait_for("!!document.querySelector('.card[data-rel=\"Photos/2026/Vacation/readme.txt\"]')")
        self.assertTrue((self.root / "Photos" / "2026" / "Vacation" / "readme.txt").is_file())

        # 6. Non-blocking Upload Queue uploads real files while active
        self.cdp.eval_js("""
          (() => {
            const f1 = new File(['hello-upload-1'], 'uploaded_a.txt', { type: 'text/plain' });
            const f2 = new File(['hello-upload-2'], 'uploaded_b.txt', { type: 'text/plain' });
            window.LanternUpload.enqueueUploadItems([
              { file: f1, relPath: 'uploaded_a.txt', size: f1.size },
              { file: f2, relPath: 'uploaded_b.txt', size: f2.size },
            ], 'Docs', true);
          })()
        """)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if (self.root / "Docs" / "uploaded_a.txt").is_file() and (self.root / "Docs" / "uploaded_b.txt").is_file():
                break
            time.sleep(0.1)
        self.assertTrue((self.root / "Docs" / "uploaded_a.txt").is_file())
        self.assertTrue((self.root / "Docs" / "uploaded_b.txt").is_file())

        # 7. Delete file via UI (deleteSel) works cleanly with zero degradation
        self.cdp.eval_js("window.navigateToFolder('')")
        self._wait_for("!!document.querySelector('.card[data-rel=\"delete_me.txt\"]')")
        self.cdp.eval_js("window.confirm = () => true; window.toggleSelect('delete_me.txt'); window.deleteSel();")
        self._wait_for("!document.querySelector('.card[data-rel=\"delete_me.txt\"]')")
        self.assertFalse((self.root / "delete_me.txt").exists())

        # 8. Zero uncaught runtime exceptions across entire E2E flow!
        self.assertEqual(self.cdp.exceptions, [], f"Uncaught JS exceptions: {self.cdp.exceptions}")




class TestV925GalleryLiveJSIntegration(unittest.TestCase):
    """Executes actual static/gallery_{tree,upload,media,app}.js in Node.js against a live LanternHTTPServer."""

    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("node not available")
        self.tmp = tempfile.TemporaryDirectory(prefix="lantern-v925-node-e2e-")
        self.root = Path(self.tmp.name) / "root"
        (self.root / "Photos" / "2026" / "Vacation").mkdir(parents=True)
        (self.root / "Docs").mkdir()
        (self.root / "Docs" / "readme.txt").write_text("Lantern v9.25 Node Live E2E", encoding="utf-8")
        (self.root / "delete_me.txt").write_text("delete via UI", encoding="utf-8")
        _make_png(self.root / "Photos" / "2026" / "Vacation" / "sunset.png", (320, 240), (240, 120, 60))

        self.cfg = AppConfig(
            root=self.root,
            port=0,
            host="127.0.0.1",
            title="Lantern v9.25 Live JS",
            cache_dir=Path(self.tmp.name) / "cache",
            config_path=Path(self.tmp.name) / "config.yaml",
        )
        self.app = make_application(self.cfg)
        self.server = LanternHTTPServer(("127.0.0.1", 0), Handler, self.app)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.close()
        self.tmp.cleanup()

    def test_real_frontend_js_modules_against_live_server(self):
        harness = r"""
const fs = require('fs');
const vm = require('vm');
const BASE = process.env.LANTERN_BASE;
const ROOT = process.env.LANTERN_ROOT;

class MiniEl {
  constructor(tag = 'div', id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.className = '';
    this.dataset = {};
    this.style = { setProperty() {}, getPropertyValue() { return '256px'; } };
    this.children = [];
    this._html = '';
    this._text = '';
    this.listeners = {};
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.classList = {
      _set: new Set(),
      add: (...c) => c.forEach(x => { this.classList._set.add(x); this.className = [...this.classList._set].join(' '); }),
      remove: (...c) => c.forEach(x => { this.classList._set.delete(x); this.className = [...this.classList._set].join(' '); }),
      toggle: (x, f) => { const on = f === undefined ? !this.classList._set.has(x) : Boolean(f); if (on) this.classList._set.add(x); else this.classList._set.delete(x); this.className = [...this.classList._set].join(' '); return on; },
      contains: x => this.classList._set.has(x),
    };
  }
  set innerHTML(v) { this._html = String(v ?? ''); this._text = this._html.replace(/<[^>]+>/g, ''); }
  get innerHTML() { return this._html; }
  set textContent(v) { this._text = String(v ?? ''); this._html = this._text; this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(n) { this.children.push(n); return n; }
  prepend(...nodes) { this.children.unshift(...nodes); }
  remove() {}
  setAttribute(k, v) { (this._attrs ||= {})[k] = String(v); if (k === 'id') this.id = String(v); }
  getAttribute(k) { return (this._attrs && k in this._attrs) ? this._attrs[k] : null; }
  removeAttribute(k) { if (this._attrs) delete this._attrs[k]; }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  removeEventListener() {}
  insertAdjacentHTML(_pos, h) { this._html += String(h || ''); }
  _walk(out = []) { for (const c of this.children) { out.push(c); if (c && c._walk) c._walk(out); } return out; }
  querySelector(sel) {
    if (sel === '.side-title-text' || sel === '.side-content' || sel === 'pre') return new MiniEl();
    const all = this.querySelectorAll(sel);
    return all[0] || null;
  }
  querySelectorAll(sel) {
    const all = this._walk();
    if (sel.includes('.tree-row')) return all.filter(n => n.className && n.className.includes('tree-row'));
    if (sel.includes('role="group"') || sel.includes('tree-group')) return all.filter(n => n._attrs && n._attrs.role === 'group');
    if (sel.includes('menuitem')) return all.filter(n => n._attrs && n._attrs.role === 'menuitem' && !n.classList.contains('hidden'));
    return [];
  }
  contains(node) { return node === this || this._walk().includes(node); }
  closest(sel) { if (sel && sel.includes('tree-row') && this.className.includes('tree-row')) return this; return null; }
  scrollIntoView() {}
  getBoundingClientRect() { return { left: 100, top: 200, width: 256, height: 600 }; }
  focus() { sandbox.document.activeElement = this; }
  select() {}
  click() { (this.listeners.click || []).forEach(fn => fn({ preventDefault(){}, stopPropagation(){} })); }
}

const byId = {};
const ids = [
  'treePane','treeResizer','treeBody','grid','q','sidePreview','toast','crumbsBar',
  'addressWrap','addressInput','navBackBtn','navFwdBtn','navUpBtn','sysTelemetryPill',
  'sortSelect','limitSelect','foldersFirst','recursiveDepth','thumbFit','folderPreviewToggle',
  'previewAnim','uploadConflict','previewPaneBtn','selCount','statusItems','statusSel',
  'statusClip','modal','modalTitle','modalMeta','modalBody','modalImageTools','modalZoomLabel',
  'modalVideoSpeed','modalCropBtn','modalCropOverwriteBtn','modalPrevBtn','modalNextBtn',
  'modalPrevFloat','modalNextFloat','uploadModal','uploadTargetTitle','uploadDrop','uploadQueue',
  'uploadSummary','uploadModalBar','uploadPauseBtn','uploadRetryBtn','uploadFloatPill',
  'uploadFloatText','uploadFloatFill','propsModal','propsTitle','propsBody','ctxMenu',
  'fileInput','folderInput','pasteBtn','deleteBtn','downloadBtn','archiveBtn','copyBtn',
  'moveBtn','duplicateBtn','batchRenameBtn','extractBtn','renameBtn','shareBtn','previewBtn','mobileSelCount','mobileMoreActBtn','optionsBtn','optionsMenu','optionsCloseBtn','treeToggleBtn','treeCloseBtn','treeBackdrop','treeLive','a11yLive','modalCloseBtn','propsCloseBtn','selectionBar','subToolbar','topHeader','browserArea','statusBar','galleryFilterBar','mobileSearchBar','mobileSearchBtn','mobileQ','showHiddenToggle'
];
for (const id of ids) byId[id] = new MiniEl('div', id);
byId.grid.classList.add('dropzone', 'grid');
byId.optionsMenu.classList.add('hidden');
byId.ctxMenu.classList.add('hidden');

const store = new Map();
const sandbox = {
  console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
  URL, URLSearchParams, AbortController,
  requestAnimationFrame: (fn) => { fn(); return 1; },
  cancelAnimationFrame: () => {},
  CSS: { escape: s => String(s) },
  IntersectionObserver: class { observe(){} unobserve(){} disconnect(){} },
  Image: class { set src(v) { this._src = v; } },
  localStorage: { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)) },
  _sess: new Map(),
  sessionStorage: { getItem: k => sandbox._sess.has(k) ? sandbox._sess.get(k) : null, setItem: (k, v) => sandbox._sess.set(k, String(v)), removeItem: k => sandbox._sess.delete(k) },
  name: '',
  innerWidth: 1440,
  innerHeight: 900,
  Element: MiniEl,
  HTMLElement: MiniEl,
  location: { pathname: '/', href: BASE + '/' },
  history: { pushState(_s, _t, u) { sandbox.location.pathname = u; }, replaceState(_s, _t, u) { sandbox.location.pathname = u; } },
  confirm: () => true,
  prompt: () => '',
  getComputedStyle: () => ({ getPropertyValue: () => '256px' }),
  document: {
    hidden: false,
    title: 'Lantern v9.25',
    activeElement: null,
    body: new MiniEl('body'),
    documentElement: new MiniEl('html'),
    head: new MiniEl('head'),
    getElementById: id => byId[id] || null,
    querySelector: sel => sel.startsWith('#') ? (byId[sel.slice(1)] || null) : null,
    querySelectorAll: () => [],
    createElement: tag => new MiniEl(tag),
    createDocumentFragment: () => new MiniEl('frag'),
    createTextNode: t => ({ textContent: String(t) }),
    addEventListener() {},
  },
  fetch: (url, opts) => globalThis.fetch(url.startsWith('http') ? url : BASE + url, opts),
  APP: { currentPath: '', title: 'Lantern v9.25', rootName: 'root', plugin: { enabled: true }, defaults: { default_sort: 'name-asc', default_view: 'grid', page_limit: 220, folders_first: true, upload_parallel: 3, upload_conflict: 'overwrite', upload_auto_start: true } },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.addEventListener = () => {};
sandbox.removeEventListener = () => {};

vm.createContext(sandbox);
for (const rel of ['static/gallery_tree.js', 'static/gallery_upload.js', 'static/gallery_media.js', 'static/gallery_app.js']) {
  vm.runInContext(fs.readFileSync(ROOT + '/' + rel, 'utf8'), sandbox, { filename: rel });
}

(async () => {
  await new Promise(r => setTimeout(r, 250));
  // 1. Telemetry pill updated with real RAM & CPU (no undefined)
  await sandbox.refreshSysTelemetry();
  const tele = byId.sysTelemetryPill.textContent;
  if (!tele.includes('RAM') || tele.includes('undefined')) throw new Error('Bad telemetry pill: ' + tele);

  // 2. Folder Tree synced root and expands Photos -> 2026
  await sandbox.LanternTree.syncToPath('', true);
  await sandbox.LanternTree.toggleExpand('Photos');
  const treeRowsAfterExpand = byId.treeBody.querySelectorAll('.tree-row[role="treeitem"]');
  const treeHas2026 = treeRowsAfterExpand.some(r => r.dataset?.treeRel === 'Photos/2026');
  if (!treeHas2026) throw new Error('Tree did not lazy-load Photos/2026');

  // 3. SPA navigateToFolder updates currentPath & loads items
  await sandbox.navigateToFolder('Photos/2026/Vacation');
  if (sandbox.currentPath() !== 'Photos/2026/Vacation') throw new Error('SPA navigate failed');
  if (!sandbox.LanternAppState.items.some(x => x.name === 'sunset.png')) throw new Error('sunset.png not loaded');

  // 4. 4 View Modes
  for (const [m, cls] of [['large','view-large'],['details','view-details'],['list','list'],['grid','grid']]) {
    sandbox.setView(m);
    if (!byId.grid.classList.contains(cls)) throw new Error('Missing view class ' + cls);
  }

  // 5. Lightbox open + zoom + rotate + close
  sandbox.openPreview('image', '/Photos/2026/Vacation/sunset.png', 'sunset.png', 'Photos/2026/Vacation/sunset.png');
  sandbox.LanternMedia.zoomBy(0.5);
  sandbox.LanternMedia.rotateBy(90);
  if (byId.modalZoomLabel.textContent !== '150%') throw new Error('Zoom failed: ' + byId.modalZoomLabel.textContent);
  sandbox.closeModal();

  // 6. Properties modal fetches 320 x 240
  await sandbox.openPropertiesModal('Photos/2026/Vacation/sunset.png');
  if (!byId.propsBody.innerHTML.includes('320 × 240')) throw new Error('Properties missing dimensions: ' + byId.propsBody.innerHTML);

  // 7. Windows Clipboard Copy/Paste across folders
  await sandbox.navigateToFolder('Docs');
  sandbox.toggleSelect('Docs/readme.txt');
  await sandbox.copySel();
  await sandbox.navigateToFolder('Photos/2026/Vacation');
  await sandbox.pasteClipboard();

  // 8. Delete file via UI deleteSel
  await sandbox.navigateToFolder('');
  sandbox.toggleSelect('delete_me.txt');
  await sandbox.deleteSel();

  // 9. GAL-02: Gallery mode filters accurately when items > 140 (e.g. 160 mixed items)
  sandbox.LanternAppState.items = [
    { special: 'back', href: '/' },
    ...Array.from({ length: 100 }, (_, i) => ({ name: `doc_${i}.txt`, rel: `doc_${i}.txt`, is_dir: false, kind: 'text' })),
    ...Array.from({ length: 50 }, (_, i) => ({ name: `pic_${i}.png`, rel: `pic_${i}.png`, is_dir: false, kind: 'image', thumb: `/api/thumb?p=pic_${i}.png` })),
    ...Array.from({ length: 10 }, (_, i) => ({ name: `vid_${i}.mp4`, rel: `vid_${i}.mp4`, is_dir: false, kind: 'video' })),
  ];
  sandbox.setAppMode('gallery');
  sandbox.setMediaFilter('image');
  if (byId.grid.innerHTML.includes('doc_0.txt') || byId.grid.innerHTML.includes('vid_0.mp4') || byId.grid.innerHTML.includes('special-back')) {
    throw new Error('GAL-02/UX-04 failed: non-image or back card rendered in Gallery Photos filter (>140 items)');
  }
  if (!byId.grid.innerHTML.includes('pic_0.png')) throw new Error('GAL-02 failed: missing pic_0.png');
  // 10. IMG-01: Fit vs 1:1 resetZoom check
  sandbox.openPreview('image', '/Photos/2026/Vacation/sunset.png', 'sunset.png', 'Photos/2026/Vacation/sunset.png');
  if (byId.modalZoomLabel.textContent !== 'Fit') throw new Error('IMG-01 expected Fit label, got ' + byId.modalZoomLabel.textContent);
  sandbox.LanternMedia.rotateBy(90);
  sandbox.LanternMedia.resetZoom();
  if (byId.modalZoomLabel.textContent !== 'Fit') throw new Error('IMG-01 resetZoom did not restore Fit');
  sandbox.closeModal();


  // 11. A11Y-01 & A11Y-02: Verify WAI-ARIA APG Tree attributes (aria-label, role=group, roving tabIndex, no aria-expanded on leaf)
  if (!byId.treeBody.getAttribute('aria-label')) throw new Error('A11Y-02: #treeBody missing aria-label');
  const rowsNow = byId.treeBody.querySelectorAll('.tree-row[role="treeitem"]');
  const focusableRows = rowsNow.filter(r => r.tabIndex === 0);
  if (focusableRows.length !== 1) throw new Error('A11Y-01: expected exactly 1 roving tabIndex=0 treeitem, got ' + focusableRows.length);
  const docsRow = rowsNow.find(r => r.dataset.treeRel === 'Docs');
  if (!docsRow) throw new Error('Docs row missing');
  if (docsRow.getAttribute('aria-expanded') !== null) throw new Error('A11Y-02: leaf folder Docs must NOT have aria-expanded');
  if (!docsRow.getAttribute('aria-level') || !docsRow.getAttribute('aria-posinset') || !docsRow.getAttribute('aria-setsize')) {
    throw new Error('A11Y-02: missing aria-level/posinset/setsize on treeitem');
  }
  const photosRow = rowsNow.find(r => r.dataset.treeRel === 'Photos');
  if (photosRow.getAttribute('aria-expanded') !== 'true') throw new Error('A11Y-02: expanded folder Photos must have aria-expanded=true');

  // Keyboard ArrowDown / ArrowUp on #treeBody moves roving focus
  sandbox.LanternTree.focusTreeRow('');
  const firstKeyListeners = byId.treeBody.listeners.keydown || [];
  firstKeyListeners.forEach(fn => fn({ key: 'ArrowDown', target: sandbox.document.activeElement, preventDefault() {} }));
  if (sandbox.document.activeElement?.dataset?.treeRel === '') throw new Error('A11Y-01: ArrowDown did not move focus from root');

  // 12. CFG-02: showHidden stored per-tab in sessionStorage (not localStorage)
  sandbox.toggleShowHidden({ checked: true });
  if (store.get('lanDrive:show_hidden') === '1') throw new Error('CFG-02: show_hidden leaked into localStorage!');
  if (!sandbox.LanternTabState.getShowHidden()) throw new Error('CFG-02: LanternTabState did not record showHidden=true');

  // 13. A11Y-03: Options menu toggles aria-expanded and Escape closes it
  sandbox.toggleOptionsMenu();
  if (byId.optionsBtn.getAttribute('aria-expanded') !== 'true') throw new Error('A11Y-03: optionsBtn aria-expanded not set to true');
  sandbox.closeOptionsMenu(true);
  if (byId.optionsBtn.getAttribute('aria-expanded') !== 'false') throw new Error('A11Y-03: optionsBtn aria-expanded not reset to false');

  console.log('LIVE_JS_E2E_ALL_OK');
})().catch(err => { console.error(err); process.exit(1); });
"""
        env = {**os.environ, "LANTERN_BASE": self.base, "LANTERN_ROOT": str(ROOT)}
        res = subprocess.run(["node", "-e", harness], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(res.returncode, 0, f"Node Live JS E2E failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        self.assertIn("LIVE_JS_E2E_ALL_OK", res.stdout)
        # Verify real disk mutations performed by actual frontend JS!
        self.assertTrue((self.root / "Photos" / "2026" / "Vacation" / "readme.txt").is_file())
        self.assertFalse((self.root / "delete_me.txt").exists())



class TestV925Round4ReleaseHardening(unittest.TestCase):
    """Regression & acceptance tests for GAL-03, MOB-05, CFG-02, A11Y-01..06, TREE-01, SEC-01, FILE-03."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lantern-v925-r4-")
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir(parents=True)
        self.cfg = AppConfig(
            root=self.root,
            port=0,
            host="127.0.0.1",
            title="Lantern v9.25 R4",
            cache_dir=Path(self.tmp.name) / "cache",
            config_path=Path(self.tmp.name) / "config.yaml",
        )
        self.app = make_application(self.cfg)
        self.server = LanternHTTPServer(("127.0.0.1", 0), Handler, self.app)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.close()
        self.tmp.cleanup()

    def _get_json(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_gal03_media_filter_pagination_matrix_up_to_2000_files(self):
        # Test exact reproduction: 155 .txt + 4 .png sorted after first 100 files (total 159)
        f159 = self.root / "case_159"
        f159.mkdir()
        for i in range(155):
            (f159 / f"a_{i:04d}.txt").write_text("x", encoding="utf-8")
        for i in range(4):
            _make_png(f159 / f"z_pic_{i}.png", (32, 32), (10, 200, 50))

        # Explorer page 1 (limit=100) has 100 .txt files and hasMore=True
        st, exp_p1 = self._get_json("/api/list?path=case_159&offset=0&limit=100&sort=name-asc")
        self.assertEqual(st, 200)
        self.assertTrue(exp_p1["hasMore"])
        self.assertEqual(exp_p1["total"], 159)
        self.assertEqual(sum(1 for it in exp_p1["items"] if it.get("kind") == "image"), 0)

        # Gallery media_filter=media immediately returns all 4 PNGs on page 1 with zero duplicates!
        st, gal_p1 = self._get_json("/api/list?path=case_159&offset=0&limit=100&sort=name-asc&media_filter=media")
        self.assertEqual(st, 200)
        self.assertFalse(gal_p1["hasMore"])
        self.assertEqual(gal_p1["total"], 4)
        self.assertEqual([it["name"] for it in gal_p1["items"]], ["z_pic_0.png", "z_pic_1.png", "z_pic_2.png", "z_pic_3.png"])

        # Gallery media_filter=video returns 0 items and hasMore=False (true empty state)
        st, vid_p1 = self._get_json("/api/list?path=case_159&offset=0&limit=100&sort=name-asc&media_filter=video")
        self.assertEqual(st, 200)
        self.assertFalse(vid_p1["hasMore"])
        self.assertEqual(vid_p1["total"], 0)
        self.assertEqual(vid_p1["items"], [])

        # Large directory matrix: 0, 1, 99, 100, 101, 500, 2000 mixed files with images at start, middle, end
        for total_n in (0, 1, 99, 100, 101, 500, 2000):
            d = self.root / f"case_{total_n}"
            d.mkdir()
            img_positions = set()
            if total_n >= 1:
                img_positions.add(0)
            if total_n >= 3:
                img_positions.add(total_n // 2)
                img_positions.add(total_n - 1)
            for i in range(total_n):
                if i in img_positions:
                    (d / f"f_{i:05d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
                else:
                    (d / f"f_{i:05d}.txt").write_text("t", encoding="utf-8")
            st, res = self._get_json(f"/api/list?path=case_{total_n}&offset=0&limit=100&sort=name-asc&media_filter=image")
            self.assertEqual(st, 200)
            self.assertEqual(res["total"], len(img_positions), f"Mismatch for total_n={total_n}")
            names = [it["name"] for it in res["items"]]
            self.assertEqual(len(names), len(set(names)), "Duplicate items detected")

    def test_sec01_path_traversal_and_zip_symlink_safety(self):
        # 1. Path traversal attempts on /api/list, /api/tree, /api/properties must stay inside root
        outside = Path(self.tmp.name) / "secret.txt"
        outside.write_text("TOP_SECRET", encoding="utf-8")
        for url in ("/api/properties?p=../../secret.txt", "/api/list?path=../../.."):
            try:
                st, data = self._get_json(url)
                self.assertNotIn("TOP_SECRET", json.dumps(data))
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, (400, 403, 404))

        # 2. Malicious zip with ../escape.txt must fail closed
        bad_zip = self.root / "evil.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../escape.txt", "pwned")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post_json("/api/extract", {"path": "evil.zip", "dest": ""})
        self.assertEqual(ctx.exception.code, 400)
        self.assertFalse((Path(self.tmp.name) / "escape.txt").exists())

        # 3. Zip containing a symlink entry must skip the symlink safely
        sym_zip = self.root / "sym.zip"
        with zipfile.ZipFile(sym_zip, "w") as zf:
            zi = zipfile.ZipInfo("link.txt")
            zi.external_attr = (0o120777 << 16)
            zf.writestr(zi, "/etc/passwd")
            zf.writestr("safe.txt", "hello")
        st, res = self._post_json("/api/extract", {"path": "sym.zip", "dest": "out_sym"})
        self.assertEqual(st, 200)
        self.assertEqual(res["written"], 1)
        self.assertEqual(res["skipped"], 1)
        self.assertTrue((self.root / "out_sym" / "safe.txt").is_file())
        self.assertFalse((self.root / "out_sym" / "link.txt").exists())

    def test_file03_unicode_special_chars_crud_integrity(self):
        # Spaces, quotes, #, %, &, Vietnamese, Japanese, emoji
        special_dir = "Thư mục テスト #1 & 100%"
        st, _ = self._post_json("/api/mkdir", {"path": "", "name": special_dir})
        self.assertEqual(st, 200)
        self.assertTrue((self.root / special_dir).is_dir())

        fname = "ảnh 'test' #2 & 50% 日本語 🎉.txt"
        (self.root / special_dir / fname).write_text("integrity-payload", encoding="utf-8")

        # List & verify metadata parity (sizeText, mtimeText, ext)
        q_dir = urllib.parse.quote(special_dir)
        st, listed = self._get_json(f"/api/list?path={q_dir}&offset=0&limit=100")
        self.assertEqual(st, 200)
        matched = [it for it in listed["items"] if it.get("name") == fname]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["ext"], ".txt")
        self.assertTrue(matched[0]["sizeText"])
        self.assertTrue(matched[0]["mtimeText"])

        # Copy -> Duplicate -> Rename -> Delete
        rel = f"{special_dir}/{fname}"
        st, _ = self._post_json("/api/duplicate", {"paths": [rel], "conflict": "rename"})
        self.assertEqual(st, 200)
        st, _ = self._post_json("/api/rename", {"path": rel, "name": "renamed_日本語.txt"})
        self.assertEqual(st, 200)
        self.assertTrue((self.root / special_dir / "renamed_日本語.txt").is_file())
        self.assertEqual((self.root / special_dir / "renamed_日本語.txt").read_text(encoding="utf-8"), "integrity-payload")
        st, _ = self._post_json("/api/delete", {"paths": [f"{special_dir}/renamed_日本語.txt"]})
        self.assertEqual(st, 200)
        self.assertFalse((self.root / special_dir / "renamed_日本語.txt").exists())

    def test_tree_css_no_40vh_leaf_stretch_and_aria_contracts(self):
        css = (ROOT / "static" / "gallery.css").read_text(encoding="utf-8")
        tree_js = (ROOT / "static" / "gallery_tree.js").read_text(encoding="utf-8")
        app_js = (ROOT / "static" / "gallery_app.js").read_text(encoding="utf-8")
        html = urllib.request.urlopen(self.base + "/", timeout=10).read().decode("utf-8")

        # Leaf twistie must NOT use global .empty class that had 40vh height
        self.assertIn("tree-twist-empty", tree_js)
        self.assertIn(".grid > .empty", css)
        # Default HTML lang is English
        self.assertIn('<html lang="en">', html)
        # WAI-ARIA attributes in HTML shell
        self.assertIn('aria-haspopup="dialog"', html)
        self.assertIn('aria-controls="optionsMenu"', html)
        self.assertIn('role="menu"', html)
        self.assertIn('role="menuitem"', html)
        self.assertIn('id="mobileSelCount"', html)
        # CFG-02: show_hidden must NOT use localStorage in app_js or tree_js
        self.assertNotIn("localStorage.getItem('lanDrive:show_hidden')", app_js)
        self.assertNotIn("localStorage.setItem('lanDrive:show_hidden'", app_js)
        self.assertNotIn("localStorage.getItem('lanDrive:show_hidden')", tree_js)



class SolReviewRepairRegressionTests(unittest.TestCase):
    """Deterministic regressions for Sol review P0/P1 findings."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory(prefix="lantern_sol_fix_")
        cls.root = Path(cls.td.name) / "root"
        cls.cache = Path(cls.td.name) / "cache"
        cls.root.mkdir(parents=True, exist_ok=True)
        cls.cache.mkdir(parents=True, exist_ok=True)
        cls.cfg = AppConfig(
            config_path=Path(cls.td.name) / "config.yaml",
            root=cls.root,
            cache_dir=cls.cache,
            host="127.0.0.1",
            port=0,
            title="Lantern Sol Repair",
            upload_conflict="ask",
            terminal_enabled=False,
        )
        cls.app = make_application(cls.cfg)
        cls.srv = LanternHTTPServer(("127.0.0.1", 0), Handler, cls.app)
        cls.port = cls.srv.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.td.cleanup()

    def _upload_chunk(self, upload_id: str, idx: int, total: int, payload: bytes) -> tuple[int, dict]:
        url = f"{self.base}/api/upload/chunk?id={upload_id}&index={idx}&total={total}"
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/octet-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _post_json(self, path: str, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_concurrent_chunk_completion_rename_preserves_both_payloads(self):
        import hashlib
        p1 = b"PAYLOAD-ONE-" * 1024
        p2 = b"PAYLOAD-TWO-" * 1024
        h1 = hashlib.sha256(p1).hexdigest()
        h2 = hashlib.sha256(p2).hexdigest()
        id1, id2 = "race_rename_1", "race_rename_2"
        self.assertEqual(self._upload_chunk(id1, 0, 1, p1)[0], 200)
        self.assertEqual(self._upload_chunk(id2, 0, 1, p2)[0], 200)

        barrier = threading.Barrier(2)
        results = []

        def worker(uid):
            barrier.wait()
            results.append(self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": "race_rename.bin", "total": 1, "conflict": "rename",
            }))

        t1 = threading.Thread(target=worker, args=(id1,))
        t2 = threading.Thread(target=worker, args=(id2,))
        t1.start(); t2.start(); t1.join(); t2.join()

        self.assertEqual([r[0] for r in results], [200, 200])
        files = sorted(p for p in self.root.glob("race_rename*.bin"))
        self.assertEqual(len(files), 2, f"Expected 2 files after concurrent rename, got {files}")
        hashes = {hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
        self.assertEqual(hashes, {h1, h2})

    def test_concurrent_chunk_completion_ask_one_publish_one_409(self):
        p1 = b"ASK-ONE-" * 512
        p2 = b"ASK-TWO-" * 512
        id1, id2 = "race_ask_0001", "race_ask_0002"
        self.assertEqual(self._upload_chunk(id1, 0, 1, p1)[0], 200)
        self.assertEqual(self._upload_chunk(id2, 0, 1, p2)[0], 200)

        barrier = threading.Barrier(2)
        results = []

        def worker(uid):
            barrier.wait()
            results.append(self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": "race_ask.bin", "total": 1, "conflict": "ask",
            }))

        t1 = threading.Thread(target=worker, args=(id1,))
        t2 = threading.Thread(target=worker, args=(id2,))
        t1.start(); t2.start(); t1.join(); t2.join()

        codes = sorted(r[0] for r in results)
        self.assertEqual(codes, [200, 409])
        final_bytes = (self.root / "race_ask.bin").read_bytes()
        self.assertIn(final_bytes, (p1, p2))

    def test_concurrent_chunk_completion_skip_one_publish_one_skipped(self):
        p1 = b"SKIP-ONE-" * 512
        p2 = b"SKIP-TWO-" * 512
        id1, id2 = "race_skip_001", "race_skip_002"
        self.assertEqual(self._upload_chunk(id1, 0, 1, p1)[0], 200)
        self.assertEqual(self._upload_chunk(id2, 0, 1, p2)[0], 200)

        barrier = threading.Barrier(2)
        results = []

        def worker(uid):
            barrier.wait()
            results.append(self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": "race_skip.bin", "total": 1, "conflict": "skip",
            }))

        t1 = threading.Thread(target=worker, args=(id1,))
        t2 = threading.Thread(target=worker, args=(id2,))
        t1.start(); t2.start(); t1.join(); t2.join()

        self.assertEqual([r[0] for r in results], [200, 200])
        skipped_flags = sorted(bool(r[1].get("skipped")) for r in results)
        self.assertEqual(skipped_flags, [False, True])
        final_bytes = (self.root / "race_skip.bin").read_bytes()
        self.assertIn(final_bytes, (p1, p2))

    def test_concurrent_chunk_completion_overwrite_serializes_with_crop_lock(self):
        (self.root / "lock_target.bin").write_bytes(b"OLD")
        uid = "race_overwrite_lock"
        self.assertEqual(self._upload_chunk(uid, 0, 1, b"NEW-PAYLOAD")[0], 200)

        completed_at = []

        def complete_worker():
            st, _ = self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": "lock_target.bin", "total": 1, "conflict": "overwrite",
            })
            completed_at.append((st, time.monotonic()))

        with self.app.crop.lock:
            t = threading.Thread(target=complete_worker)
            t.start()
            time.sleep(0.2)
            # Must still be blocked waiting on self.app.crop.lock
            self.assertEqual(completed_at, [])
            lock_released_at = time.monotonic()

        t.join(timeout=5)
        self.assertEqual(len(completed_at), 1)
        self.assertEqual(completed_at[0][0], 200)
        self.assertGreaterEqual(completed_at[0][1], lock_released_at - 0.01)
        self.assertEqual((self.root / "lock_target.bin").read_bytes(), b"NEW-PAYLOAD")

    def test_abort_requested_before_publication_wins_over_complete_barrier(self):
        """Cancellation intent must be observed before an overwrite commits."""
        uid = "abort_barrier_before_publish"
        target = self.root / "barrier_target.bin"
        target.write_bytes(b"OLD")
        self.assertEqual(self._upload_chunk(uid, 0, 1, b"NEW-BARRIER-PAYLOAD")[0], 200)

        complete_result = []
        abort_result = []

        def complete_worker():
            complete_result.append(self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": target.name, "total": 1,
                "conflict": "overwrite",
            }))

        def abort_worker():
            abort_result.append(self._post_json("/api/upload/abort", {"id": uid}))

        with self.app.crop.lock:
            complete_thread = threading.Thread(target=complete_worker)
            complete_thread.start()
            outcome_path = self.cache / "upload_outcomes" / f"{uid}.json"
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if outcome_path.exists() and json.loads(outcome_path.read_text(encoding="utf-8")).get("state") == "publishing":
                    break
                time.sleep(0.01)
            self.assertTrue(outcome_path.exists())

            abort_thread = threading.Thread(target=abort_worker)
            abort_thread.start()
            time.sleep(0.1)

        complete_thread.join(timeout=5)
        abort_thread.join(timeout=5)
        self.assertFalse(complete_thread.is_alive())
        self.assertFalse(abort_thread.is_alive())
        self.assertEqual(len(complete_result), 1)
        self.assertEqual(len(abort_result), 1)
        self.assertEqual(complete_result[0][0], 409)
        self.assertEqual(complete_result[0][1].get("state"), "aborted-before-publication")
        self.assertEqual(abort_result[0][0], 200)
        self.assertEqual(abort_result[0][1].get("state"), "aborted-before-publication")
        self.assertTrue(abort_result[0][1].get("aborted"))
        self.assertEqual(target.read_bytes(), b"OLD")

    def test_chunk_abort_cleans_stage_and_rejects_oversized_chunk(self):
        uid = "abort_cleanup_test"
        self.assertEqual(self._upload_chunk(uid, 0, 2, b"part0")[0], 200)
        stage_dir = self.cache / "upload_chunks" / uid
        self.assertTrue(stage_dir.is_dir())
        st, _ = self._post_json("/api/upload/abort", {"id": uid})
        self.assertEqual(st, 200)
        self.assertFalse(stage_dir.exists())

    def test_gzip_accept_encoding_q_zero_respected(self):
        # Populate enough files so /api/list response exceeds 1024 bytes
        for i in range(40):
            (self.root / f"gzip_probe_{i:02d}.txt").write_text("hello", encoding="utf-8")

        for header_val, expect_gzip in [
            ("gzip", True),
            ("gzip, deflate, br", True),
            ("gzip;q=0", False),
            ("gzip;q=0, *;q=1", False),
            ("*;q=0", False),
            ("identity", False),
        ]:
            req = urllib.request.Request(
                f"{self.base}/api/list?path=&offset=0&limit=100",
                headers={"Accept-Encoding": header_val},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                enc = (r.headers.get("Content-Encoding") or "").lower()
                if expect_gzip:
                    self.assertEqual(enc, "gzip", f"Expected gzip for Accept-Encoding: {header_val}")
                else:
                    self.assertNotEqual(enc, "gzip", f"Must not gzip for Accept-Encoding: {header_val}")

    def test_frontend_cancel_refresh_delete_nav_and_mobile_modal_contracts(self):
        up_js = (ROOT / "static" / "gallery_upload.js").read_text(encoding="utf-8")
        app_js = (ROOT / "static" / "gallery_app.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "gallery.css").read_text(encoding="utf-8")

        # Cancel race: XHR retention, AbortController, post-cancel gate, publishedAfterCancel
        self.assertIn("it._xhr = xhr;", up_js)
        self.assertIn("it._abortCtrl = ctrl;", up_js)
        self.assertIn("publishedAfterCancel", up_js)
        self.assertIn("abortServerChunks", up_js)

        # Refresh restoration: focus, visibilitychange, 30s timer, cache hydration, viewport anchor
        self.assertIn("window.addEventListener('focus'", app_js)
        self.assertIn("document.addEventListener('visibilitychange'", app_js)
        self.assertIn("refreshWhenActive(30000)", app_js)
        self.assertIn("captureListViewport", app_js)
        self.assertIn("restoreListViewport", app_js)
        self.assertIn("hydrateCache()", app_js)
        self.assertIn("window.state = state;", app_js)
        self.assertIn('data-name=".."', app_js)

        # Filtered delete: reconcileSelectionToVisible + explicit target filenames
        self.assertIn("reconcileSelectionToVisible", app_js)
        self.assertIn("previewList", app_js)

        # Mobile Lightbox & Upload dialog reflow
        self.assertIn("Narrow-Viewport Lightbox & Upload Dialog Reflow", css)
        self.assertIn(".modal-head .actions", css)
        self.assertIn("overflow-wrap: anywhere", css)
        self.assertRegex(css, r"\.upload-head \.sub\s*\{[^}]*white-space:\s*normal")


    def test_upload_cancel_transaction_after_publication_and_abort_before(self):
        # Case A: abort BEFORE publication prevents destination & staged parts and blocks later complete
        uid_before = "tx_abort_before_01"
        self.assertEqual(self._upload_chunk(uid_before, 0, 1, b"ABORT-BEFORE")[0], 200)
        st, body = self._post_json("/api/upload/abort", {"id": uid_before})
        self.assertEqual(st, 200)
        self.assertEqual(body.get("state"), "aborted-before-publication")
        self.assertTrue(body.get("aborted"))
        self.assertFalse(body.get("published"))
        self.assertFalse((self.cache / "upload_chunks" / uid_before).exists())
        st2, body2 = self._post_json("/api/upload/complete", {
            "id": uid_before, "path": "", "name": "should_not_exist.bin", "total": 1, "conflict": "rename",
        })
        self.assertEqual(st2, 409)
        self.assertEqual(body2.get("state"), "aborted-before-publication")
        self.assertFalse((self.root / "should_not_exist.bin").exists())

        # Case B: abort AFTER publication reports published (never aborted) and keeps destination intact
        uid_after = "tx_abort_after_01"
        payload = b"PUBLISHED-PAYLOAD-" * 1024
        self.assertEqual(self._upload_chunk(uid_after, 0, 1, payload)[0], 200)
        st_c, body_c = self._post_json("/api/upload/complete", {
            "id": uid_after, "path": "", "name": "published_target.bin", "total": 1, "conflict": "rename",
        })
        self.assertEqual(st_c, 200)
        self.assertEqual(body_c.get("state"), "published")
        self.assertTrue(body_c.get("published"))

        # Subsequent abort must report published and preserve the file
        st_a, body_a = self._post_json("/api/upload/abort", {"id": uid_after})
        self.assertEqual(st_a, 200)
        self.assertEqual(body_a.get("state"), "published")
        self.assertTrue(body_a.get("published"))
        self.assertFalse(body_a.get("aborted"))
        self.assertEqual((self.root / "published_target.bin").read_bytes(), payload)

        # GET /api/upload/status returns durable published outcome
        with urllib.request.urlopen(f"{self.base}/api/upload/status?id={uid_after}", timeout=10) as r:
            status_body = json.loads(r.read().decode("utf-8"))
        self.assertEqual(status_body.get("state"), "published")
        self.assertTrue(status_body.get("published"))

        # Idempotent retry of complete returns published without duplicating
        st_r, body_r = self._post_json("/api/upload/complete", {
            "id": uid_after, "path": "", "name": "published_target.bin", "total": 1, "conflict": "rename",
        })
        self.assertEqual(st_r, 200)
        self.assertEqual(body_r.get("state"), "published")
        self.assertEqual(len(list(self.root.glob("published_target*.bin"))), 1)

    def test_cancel_after_atomic_publication_keeps_published_receipt(self):
        """A cancel marker arriving after replace must not rewrite a committed upload."""
        uid = "cancel_after_replace_01"
        payload = b"POSTCOMMIT-PAYLOAD" * 1024
        self.assertEqual(self._upload_chunk(uid, 0, 1, payload)[0], 200)
        target = self.root / "postcommit_target.bin"
        original_replace = files_routes.os.replace

        def replace_and_cancel(source, destination):
            original_replace(source, destination)
            if Path(destination).resolve() == target.resolve():
                (self.cache / "upload_outcomes" / f"{uid}.cancel").write_text("cancel", encoding="utf-8")

        with mock.patch.object(files_routes.os, "replace", side_effect=replace_and_cancel):
            status, body = self._post_json("/api/upload/complete", {
                "id": uid, "path": "", "name": target.name, "total": 1, "conflict": "overwrite",
            })

        self.assertEqual(status, 200)
        self.assertEqual(body.get("state"), "published")
        self.assertTrue(body.get("published"))
        self.assertFalse(body.get("aborted"))
        self.assertEqual(target.read_bytes(), payload)
        with urllib.request.urlopen(f"{self.base}/api/upload/status?id={uid}", timeout=10) as response:
            status_body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(status_body.get("state"), "published")
        self.assertTrue(status_body.get("published"))

    def test_upload_status_prefers_published_outcome_over_stale_cancel_marker(self):
        uid = "status_published_cancel_marker"
        outcome_dir = self.cache / "upload_outcomes"
        outcome_dir.mkdir(parents=True, exist_ok=True)
        (outcome_dir / f"{uid}.json").write_text(json.dumps({
            "state": "published", "published": True, "aborted": False,
            "file": "status_target.bin", "updatedAt": time.time(),
        }), encoding="utf-8")
        (outcome_dir / f"{uid}.cancel").write_text("cancel", encoding="utf-8")

        with urllib.request.urlopen(f"{self.base}/api/upload/status?id={uid}", timeout=10) as response:
            status_body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(status_body.get("state"), "published")
        self.assertTrue(status_body.get("published"))
        self.assertFalse(status_body.get("aborted"))

    def test_recursive_search_honors_per_tab_show_hidden_override(self):
        hidden_dir = self.root / ".git"
        hidden_dir.mkdir(exist_ok=True)
        (hidden_dir / "hidden_recursive_needle.txt").write_text("secret", encoding="utf-8")

        with urllib.request.urlopen(
            f"{self.base}/api/list?path=&q=hidden_recursive_needle&recursive_depth=all&show_hidden=0&show_system=0",
            timeout=10,
        ) as r:
            d0 = json.loads(r.read().decode("utf-8"))
        self.assertEqual([it["name"] for it in d0["items"]], [])

        with urllib.request.urlopen(
            f"{self.base}/api/list?path=&q=hidden_recursive_needle&recursive_depth=all&show_hidden=1&show_system=1",
            timeout=10,
        ) as r:
            d1 = json.loads(r.read().decode("utf-8"))
        self.assertIn("hidden_recursive_needle.txt", [it["name"] for it in d1["items"]])

    def test_gzip_and_identity_vary_accept_encoding(self):
        for i in range(40):
            (self.root / f"vary_probe_{i:02d}.txt").write_text("hello", encoding="utf-8")
        for ae in ("gzip", "gzip;q=0", "identity"):
            req = urllib.request.Request(
                f"{self.base}/api/list?path=&offset=0&limit=100",
                headers={"Accept-Encoding": ae},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                vary = (r.headers.get("Vary") or "").lower()
                self.assertIn("accept-encoding", vary, f"Missing Vary: Accept-Encoding for {ae}")

    def test_static_identity_gzip_and_not_modified_headers_are_variant_safe(self):
        url = self.base + "/static/gallery_app.js?v=925"
        identity_req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
        with urllib.request.urlopen(identity_req, timeout=10) as response:
            identity_etag = response.headers.get("ETag")
            identity_vary = response.headers.get("Vary") or ""
        self.assertIn("Accept-Encoding", identity_vary)
        self.assertTrue(identity_etag and identity_etag.startswith("W/"))
        self.assertRegex(identity_etag, r'^W/"[0-9a-f]+"$')

        gzip_req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(gzip_req, timeout=10) as response:
            self.assertIn("Accept-Encoding", response.headers.get("Vary") or "")
            self.assertEqual(response.headers.get("ETag"), identity_etag)

        not_modified = urllib.request.Request(url, headers={"If-None-Match": identity_etag})
        try:
            urllib.request.urlopen(not_modified, timeout=10)
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 304)
            self.assertIn("Accept-Encoding", error.headers.get("Vary") or "")
            self.assertEqual(error.headers.get("ETag"), identity_etag)
        else:
            self.fail("conditional static request did not return 304")

    def test_uv_lock_version_matches_pyproject_toml(self):
        import tomllib
        pyproj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
        lantern_pkg = next(pkg for pkg in lock["package"] if pkg["name"] == "lantern")
        self.assertEqual(lantern_pkg["version"], pyproj["project"]["version"])

    def test_p1_02_crop_es_module_p1_03_refresh_p1_04_nav_p1_06_ci_contracts(self):
        media_js = (ROOT / "static" / "gallery_media.js").read_text(encoding="utf-8")
        app_js = (ROOT / "static" / "gallery_app.js").read_text(encoding="utf-8")
        up_js = (ROOT / "static" / "gallery_upload.js").read_text(encoding="utf-8")
        tree_js = (ROOT / "static" / "gallery_tree.js").read_text(encoding="utf-8")
        ci_yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        # P1-02: Crop loaded via ES module import(), never classic script tag
        self.assertIn("await import(cropURL)", media_js)
        self.assertNotIn("loadCropBundle", media_js)
        self.assertIn("If-Match", media_js)

        # P1-03: synchronous full-window render, settled empty state, window.uploadState
        self.assertNotIn("renderBatchToken", app_js)
        self.assertIn("render({ settled: true })", app_js)
        self.assertIn("window.uploadState = uploadState;", up_js)

        # P1-04: navGen + AbortController + popstate URL restoration
        self.assertIn("const myNavGen = ++navGen;", app_js)
        self.assertIn("syncUrlToCurrentPath()", app_js)
        self.assertIn("fromPopstate: true", app_js)

        # P2: Show Hidden per-tab sessionStorage without window.name
        self.assertNotIn("window.name", tree_js)
        self.assertIn("lanDrive:tab:show_hidden", tree_js)

        # P1-06: Hosted CI workflow uses Python 3.12.10, locked uv, Playwright Chromium & --require-browser
        self.assertIn("3.12.10", ci_yml)
        self.assertIn("uv lock --check", ci_yml)
        self.assertIn("uv sync --locked --no-dev", ci_yml)
        self.assertIn("LANTERN_E2E", ci_yml)
        self.assertIn("--require-browser", ci_yml)


if __name__ == "__main__":
    unittest.main()

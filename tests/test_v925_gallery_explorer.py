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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lantern.application import make_application
from lantern.config import AppConfig
from lantern.http.server import Handler, LanternHTTPServer


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

        # 3. Verify 4 View Modes (large, grid, list, details)
        for mode, cls in [("large", "view-large"), ("details", "view-details"), ("list", "list"), ("grid", "grid")]:
            self.cdp.eval_js(f"window.setView('{mode}')")
            has_cls = self.cdp.eval_js(f"document.getElementById('grid').classList.contains('{cls}')")
            self.assertTrue(has_cls, f"View mode {mode} missing class {cls}")

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
  setAttribute(k, v) { if (k === 'id') this.id = v; }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  removeEventListener() {}
  insertAdjacentHTML(_pos, h) { this._html += String(h || ''); }
  querySelector(sel) { return sel === '.side-title-text' || sel === '.side-content' || sel === 'pre' ? new MiniEl() : null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  scrollIntoView() {}
  getBoundingClientRect() { return { width: 256, height: 600 }; }
  focus() {}
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
  'moveBtn','duplicateBtn','batchRenameBtn','extractBtn','renameBtn','shareBtn','previewBtn'
];
for (const id of ids) byId[id] = new MiniEl('div', id);
byId.grid.classList.add('dropzone', 'grid');

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
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
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
  const treeHas2026 = byId.treeBody.children.some(frag => (frag.children || []).some(r => r.dataset?.treeRel === 'Photos/2026'));
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


if __name__ == "__main__":
    unittest.main()

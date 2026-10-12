"""Image source/thumbnail cache regression after in-place Paint edits.

Optional Edge E2E: LANTERN_E2E=1 python -m unittest -v tests.test_image_cache_e2e.
Tests run on a temporary loopback-only Lantern instance and isolated data.
"""
from __future__ import annotations

import binascii
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def png_bytes(rgb: tuple[int, int, int], size: int = 40) -> bytes:
    """Construct a real RGB PNG without PIL or third-party test dependencies."""
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data) & 0xffffffff)
    payload = (b"\x00" + bytes(rgb) * size) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(payload, level=0)) + chunk(b"IEND", b""))


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "opt-in real Edge image E2E")
class ImageCacheBrowserE2E(unittest.TestCase):
    def test_external_image_overwrite_invalidates_gallery_grid_and_folder_mosaic(self):
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory(prefix="lantern-image-version-", ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            (root / "Album").mkdir()
            target = root / "Album" / "paint.png"
            old_bytes = png_bytes((255, 0, 0))
            new_bytes = png_bytes((0, 0, 255))
            self.assertEqual(len(old_bytes), len(new_bytes))
            target.write_bytes(old_bytes)
            (root / "Album" / "notes.md").write_text("![Photo](paint.png)\n", encoding="utf-8")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = root / "lantern-test.yaml"
            config.write_text(
                f'root: "{root.as_posix()}"\nhost: "127.0.0.1"\nport: {port}\n'
                f'cache_dir: "{(root / "cache").as_posix()}"\n'
                'terminal_enabled: false\nthumb_fit: "contain"\n'
                'folder_preview_enabled: true\n',
                encoding="utf-8",
            )
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "lan_drive.py"), "--config", str(config)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base + "/api/info", timeout=.5):
                            break
                    except OSError:
                        time.sleep(.1)
                else:
                    self.fail("Test server unavailable")

                def get_json(url: str) -> dict:
                    with urllib.request.urlopen(base + url, timeout=4) as response:
                        return json.load(response)

                def listing() -> dict:
                    items = get_json("/api/list?path=Album")["items"]
                    return next(item for item in items if item.get("name") == "paint.png")

                first = listing()
                self.assertIn("?v=", first["url"])
                self.assertIn("&v=", first["thumb"])
                folder_first = get_json("/api/folder_preview?p=Album")["items"][0]
                self.assertEqual(folder_first["url"], first["url"])

                with urllib.request.urlopen(base + first["url"], timeout=4) as response:
                    self.assertEqual(response.read(), old_bytes)
                    self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
                    etag = response.headers["ETag"]

                with sync_playwright() as play:
                    browser = play.chromium.launch(channel="msedge", headless=True)
                    try:
                        context = browser.new_context(viewport={"width": 1000, "height": 700})
                        page = context.new_page()
                        page.goto(base + "/Album/", wait_until="domcontentloaded", timeout=12000)
                        card = page.locator('.card[data-rel="Album/paint.png"]')
                        card.wait_for(timeout=12000)
                        img = card.locator("img.thumb")
                        img.wait_for(timeout=5000)
                        original_url = img.get_attribute("src")
                        self.assertIn("?v=", original_url)
                        page.wait_for_function(
                            "() => document.querySelector('.card img.thumb')?.naturalWidth === 40",
                            timeout=8000,
                        )
                        def color(element) -> list[int]:
                            return element.evaluate("""img => {
                              const c=document.createElement('canvas');c.width=1;c.height=1;
                              const x=c.getContext('2d');x.drawImage(img,0,0,1,1);
                              return [...x.getImageData(0,0,1,1).data].slice(0,3);
                            }""")
                        self.assertEqual(color(img), [255, 0, 0])
                        markdown_page = context.new_page()
                        markdown_page.goto(
                            base + "/api/plugin/preview?p=Album%2Fnotes.md",
                            wait_until="domcontentloaded", timeout=12000)
                        md_image = markdown_page.locator(".md-preview img").first
                        md_image.wait_for(timeout=8000)
                        self.assertEqual(color(md_image), [255, 0, 0])
                        page.evaluate("""() => {
                            if(!state.previewPane)togglePreviewPane();
                            document.querySelector('.card[data-rel="Album/paint.png"] .card-main').click();
                        }""")
                        side = page.locator(".side-fit-bg")
                        side.wait_for(timeout=7000)
                        old_background = side.evaluate("el => getComputedStyle(el).backgroundImage")
                        self.assertIn(first["url"], old_background)
                        page.evaluate("""() => openPreview(
                            'image','/Album/paint.png','paint.png','Album/paint.png')""")
                        modal = page.locator("#modalBody img")
                        modal.wait_for(timeout=7000)
                        self.assertEqual(color(modal), [255, 0, 0])
                        page.evaluate("closeModal()")

                        # Emulate Paint: same pathname, same dimensions and bytes,
                        # different content. Force a later timestamp even on coarse
                        # filesystem/VM clock implementations.
                        before = target.stat()
                        target.write_bytes(new_bytes)
                        next_mtime = max(before.st_mtime_ns + 2_000_000_000, time.time_ns())
                        os.utime(target, ns=(next_mtime, next_mtime))

                        second = listing()
                        self.assertNotEqual(first["url"], second["url"])
                        self.assertNotEqual(first["thumb"], second["thumb"])
                        folder_second = get_json("/api/folder_preview?p=Album")["items"][0]
                        self.assertNotEqual(folder_first["url"], folder_second["url"])
                        self.assertNotEqual(folder_first["thumb"], folder_second["thumb"])
                        self.assertEqual(folder_second["url"], second["url"])
                        with urllib.request.urlopen(urllib.request.Request(
                            base + first["url"], headers={"If-None-Match": etag},
                        ), timeout=4) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.read(), new_bytes)

                        page.evaluate("refreshFolder()")
                        page.wait_for_function(
                            "(old) => document.querySelector('.card img.thumb')?.getAttribute('src') !== old",
                            arg=original_url,
                            timeout=12000,
                        )
                        updated = page.locator('.card[data-rel="Album/paint.png"] img.thumb')
                        page.wait_for_function(
                            "() => { const i=document.querySelector('.card img.thumb');"
                            "return i && i.complete && i.naturalWidth === 40; }",
                            timeout=10000,
                        )
                        self.assertEqual(color(updated), [0, 0, 255])
                        page.wait_for_function(
                            "(old) => {const el=document.querySelector('.side-fit-bg');"
                            "return el && getComputedStyle(el).backgroundImage !== old;}",
                            arg=old_background, timeout=9000)
                        self.assertIn(second["url"],
                                      side.evaluate("el => getComputedStyle(el).backgroundImage"))
                        page.evaluate("""() => openPreview(
                            'image','/Album/paint.png','paint.png','Album/paint.png')""")
                        modal = page.locator("#modalBody img")
                        modal.wait_for(timeout=7000)
                        page.wait_for_function(
                            "() => {const i=document.querySelector('#modalBody img');"
                            "return i && i.complete && i.naturalWidth === 40;}",
                            timeout=9000,
                        )
                        self.assertEqual(color(modal), [0, 0, 255])

                        # Markdown keeps the same relative image URL, so
                        # Cache-Control revalidation must also refresh previews.
                        markdown_page.reload(wait_until="domcontentloaded")
                        md_image = markdown_page.locator(".md-preview img").first
                        md_image.wait_for(timeout=8000)
                        markdown_page.wait_for_function(
                            "() => {const i=document.querySelector('.md-preview img');"
                            "return i && i.complete && i.naturalWidth === 40;}",
                            timeout=9000)
                        self.assertEqual(color(md_image), [0, 0, 255])

                        # A fresh browser page must not replay the pre-Paint bitmap.
                        page.reload(wait_until="domcontentloaded")
                        final_img = page.locator('.card[data-rel="Album/paint.png"] img.thumb')
                        final_img.wait_for(timeout=12000)
                        page.wait_for_function(
                            "() => document.querySelector('.card img.thumb')?.naturalWidth === 40",
                            timeout=9000,
                        )
                        self.assertEqual(color(final_img), [0, 0, 255])
                        context.close()
                    finally:
                        browser.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

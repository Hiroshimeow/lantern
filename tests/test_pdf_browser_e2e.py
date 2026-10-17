"""Real Edge integration: PDF preview renders browser-native pages without text extraction.

Opt in: LANTERN_E2E=1 uv run --locked --with playwright
        python -m unittest -v tests.test_pdf_browser_e2e
"""
from __future__ import annotations

import html
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_pdf(path: Path) -> None:
    """Two visible pages; standards-conforming PDF generated without runtime dependencies."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number in (1, 2):
        payload = (
            b"0.08 0.12 0.18 rg 60 570 495 158 re f\n"
            b"1 1 1 rg BT /F1 26 Tf 72 682 Td "
            + f"(Lantern visual PDF - page {number})".encode("ascii")
            + b" Tj ET\n"
            b"0.2 0.7 0.3 RG 4 w 60 570 495 158 re S\n"
        )
        objects.append(
            f"<< /Length {len(payload)} >>\n".encode() +
            b"stream\n" + payload + b"endstream"
        )
    contents = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(contents))
        contents.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_at = len(contents)
    contents.extend(f"xref\n0 {len(offsets)}\n".encode())
    contents.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        contents.extend(f"{off:010d} 00000 n \n".encode())
    contents.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    path.write_bytes(contents)


@unittest.skipUnless(os.environ.get("LANTERN_E2E") == "1", "requires Edge browser E2E")
class PdfNativeBrowserE2E(unittest.TestCase):
    def test_pdf_preview_fast_and_native_viewer_with_range_support(self) -> None:
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory(prefix="lantern-pdf-native-", ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            filename = "Report 100% #2026 & figures.pdf"
            sample = root / filename
            make_pdf(sample)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "main.py"),
                 "--root", str(root), "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=0.5):
                            break
                    except Exception:
                        time.sleep(0.1)
                else:
                    self.fail("Isolated PDF test server did not start")

                base = f"http://127.0.0.1:{port}"
                safe_name = urllib.parse.quote(filename, safe="")
                preview = base + "/api/plugin/preview?p=" + safe_name
                with urllib.request.urlopen(preview, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    page_html = response.read().decode("utf-8")
                    self.assertIn("pdf-native", page_html)
                    self.assertIn("frame-src 'self'", html.unescape(page_html))
                    self.assertNotIn("Văn bản từ pdftotext", page_html)
                # The historical text view is still available, but is now
                # explicitly requested instead of blocking visual preview.
                with urllib.request.urlopen(preview + "&view=text", timeout=15) as response:
                    self.assertEqual(response.status, 200)
                    text_view = response.read().decode("utf-8")
                    self.assertNotIn('<iframe class="pdf-native"', text_view)
                    self.assertIn("View PDF pages", text_view)
                with urllib.request.urlopen(urllib.request.Request(
                    base + "/" + safe_name, headers={"Range": "bytes=0-127"},
                ), timeout=3) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.headers.get("Content-Type"), "application/pdf")
                    self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")
                    self.assertEqual(response.read(), sample.read_bytes()[:128])

                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel="msedge", headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1180, "height": 850})
                        failures = []
                        pdf_http = []
                        page.on("pageerror", lambda error: failures.append(str(error)))
                        page.on("console", lambda message: failures.append(str(message.text)) if message.type == "error" else None)
                        page.on("response", lambda response: pdf_http.append(
                            (response.status, response.headers.get("content-type", ""), response.url)
                        ) if safe_name in response.url and "/api/" not in response.url else None)
                        start = time.monotonic()
                        nav = page.goto(preview, wait_until="domcontentloaded", timeout=12000)
                        dom_ready = time.monotonic() - start
                        self.assertEqual(nav.status, 200)
                        self.assertLess(dom_ready, 3.0, "PDF wrapper must not wait on text extraction")
                        iframe = page.locator("iframe.pdf-native")
                        iframe.wait_for(state="attached", timeout=10000)
                        self.assertEqual(iframe.get_attribute("src"), "/" + safe_name)
                        self.assertGreater(iframe.bounding_box()["height"], 400)
                        self.assertIn("Extract text (slower)", page.locator("body").inner_text())
                        page.wait_for_timeout(2300)
                        self.assertTrue(pdf_http, "Browser must request PDF bytes through the native viewer")
                        self.assertTrue(any("application/pdf" in h[1] for h in pdf_http), pdf_http)
                        self.assertEqual(failures, [], failures)
                        if os.environ.get("LANTERN_PDF_SCREENSHOT") == "1":
                            screenshot = ROOT / ".test-artifacts" / "pdf-native-edge.png"
                            screenshot.parent.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=str(screenshot), full_page=True)
                        print("PDF_EDGE=" + json.dumps({
                            "domReadySeconds": round(dom_ready, 3),
                            "pdfResponses": pdf_http,
                            "frameHeight": round(iframe.bounding_box()["height"]),
                        }), flush=True)
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

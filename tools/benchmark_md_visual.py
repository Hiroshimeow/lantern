"""Isolated real-Edge Markdown visual editor benchmark (opt-in, no live Lantern restart).

Run: uv run --locked --with playwright python tools/benchmark_md_visual.py
Never writes to the user's real file tree or contacts an external origin.
"""
from __future__ import annotations
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZES = [100_000, 1_000_000, 4_900_000]

def sample(size: int) -> bytes:
    # Realistic stressor: many independently editable paragraphs and headings.
    block = "## Heading\n\nParagraph with **strong** text, [link](#a), and Vietnamese: xóa sửa.\n\n"
    data = (block * (size // len(block.encode('utf-8')) + 1)).encode('utf-8')
    return data[:size].rsplit(b'\n', 1)[0] + b'\n'

def main() -> None:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    with tempfile.TemporaryDirectory(prefix='lantern-visual-perf-', ignore_cleanup_errors=True) as name:
        dest = Path(name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        proc = subprocess.Popen([sys.executable, str(ROOT / 'main.py'),
                                  '--root', str(dest), '--host', '127.0.0.1', '--port', str(port)],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            until = time.monotonic() + 15
            while time.monotonic() < until:
                try:
                    with urllib.request.urlopen(base + '/api/info', timeout=0.5):
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError('isolated server failed')
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                try:
                    for size in SIZES:
                        (dest / 'sample.md').write_bytes(sample(size))
                        ctx = browser.new_context()
                        page = ctx.new_page()
                        measurements = {'bytes':size}
                        try:
                            start = time.perf_counter()
                            page.goto(base + '/api/plugin/preview?p=sample.md',
                                      wait_until='domcontentloaded', timeout=30000)
                            page.locator('article.md-preview').wait_for(timeout=30000)
                            measurements['preview_wall_ms'] = round((time.perf_counter()-start)*1000)
                            start = time.perf_counter()
                            page.get_by_role('button', name='Edit visually').click(timeout=12000)
                            page.locator('.md-visual-host .ProseMirror[contenteditable="true"]').wait_for(timeout=25000)
                            measurements['edit_wall_ms'] = round((time.perf_counter()-start)*1000)
                            metrics = page.evaluate("""() => ({
                              loadMs: window.__lanternMdMetrics?.loadMs,
                              nodes: document.querySelectorAll('.md-visual-host .ProseMirror p').length,
                              heap: performance.memory?.usedJSHeapSize ?? null,
                              roundtripSafe: window.__lanternMdPaged?.roundtripSafe ?? window.__lanternMdVisual?.state.roundtripSafe,
                              pageCount: window.__lanternMdPaged?.index.pages.length ?? 1,
                              indexedMs: window.__lanternMdMetrics?.indexMs ?? null,
                            })""")
                            measurements.update(metrics)
                            paragraph = page.locator('.md-visual-host .ProseMirror p').first
                            paragraph.click(timeout=2000)
                            start = time.perf_counter()
                            page.keyboard.type('X')
                            measurements['type_wall_ms'] = round((time.perf_counter()-start)*1000)
                            measurements['status'] = 'PASS'
                        except Exception as e:
                            measurements.update({'status':'FAIL','error':str(e)[:400]})
                        print('SAMPLE ' + json.dumps(measurements, ensure_ascii=True), flush=True)
                        try: ctx.close()
                        except Exception: pass
                finally:
                    browser.close()
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill();proc.wait(timeout=5)

if __name__ == '__main__':
    main()

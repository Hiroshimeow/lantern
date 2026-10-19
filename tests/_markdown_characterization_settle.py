"""Narrow test-only write-settlement helper for Markdown characterization E2Es."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

WORK_WRITE_SUFFIXES = ("/api/work/write", "/api/work/patch")
# Markdown's current input/diff/write timers are 90/110/120 ms.  A stable
# signature must survive five times the longest timer; this is a quiescence
# condition, not a one-shot sleep.
QUIET_MS = 600
POLL_MS = 120


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def count_work_write_posts(requests: list[tuple[str, str]]) -> int:
    """Count durable Markdown mutations, including Source patch batches."""
    return sum(
        method == "POST" and any(url.endswith(suffix) for suffix in WORK_WRITE_SUFFIXES)
        for method, url in requests
    )


def browser_text(text: str | None) -> str | None:
    if text is None:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _browser_sample(page: Any) -> dict[str, Any] | None:
    # Return only compact state.  In particular, do not shuttle a 5 MB editor
    # string over Playwright on every poll; compare it in-page.
    return page.evaluate(
        """() => {
          const view = window.__lanternMdVisual?.state;
          if (!view) return null;
          let editorText = null;
          try { editorText = view.instance?.getMarkdown?.() ?? null; }
          catch (_) {}
          const expected = window.__lanternCharacterizationExpected;
          return {
            revision:view.revision,
            saving:view.saving,
            loading:view.loading,
            conflict:view.conflict,
            currentVersion:view.currentVersion,
            workHash:view.workHash,
            savedVersion:view.version,
            editorMatchesExpected:editorText === expected,
            lastSavedMatchesExpected:view.lastSaved === expected
          };
        }"""
    )


def wait_for_stable_markdown_write(
    page: Any,
    *,
    rel: str,
    target: Path,
    expected_content: str,
    requests: list[tuple[str, str]],
    expected_saved_version: str,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Return one stable final server/file sample or fail closed.

    Stability requires the browser write state, real-file SHA/content and
    observed write-POST count to remain identical across a bounded quiet
    window.  Only then is /api/work fetched and correlated with the same final
    file bytes and accepted md_temp revision.
    """

    page.evaluate(
        "expected => { window.__lanternCharacterizationExpected = expected; }",
        expected_content,
    )
    expected_browser = browser_text(expected_content)
    deadline = time.monotonic() + timeout_s
    stable_since: float | None = None
    stable_signature: tuple[Any, ...] | None = None
    polls = 0
    latest: dict[str, Any] = {}

    while time.monotonic() < deadline:
        browser = _browser_sample(page)
        raw = target.read_bytes()
        file_sha = sha256_bytes(raw)
        file_content = browser_text(raw.decode("utf-8-sig"))
        write_posts = count_work_write_posts(requests)
        terminal = bool(
            browser
            and file_content == expected_browser
            and browser.get("editorMatchesExpected")
            and browser.get("lastSavedMatchesExpected")
            and browser.get("currentVersion") == file_sha
            and browser.get("workHash") == file_sha
            and browser.get("savedVersion") == expected_saved_version
            and not browser.get("saving")
            and not browser.get("loading")
            and not browser.get("conflict")
        )
        signature = (
            file_sha,
            write_posts,
            browser.get("revision") if browser else None,
            browser.get("currentVersion") if browser else None,
            browser.get("workHash") if browser else None,
            browser.get("savedVersion") if browser else None,
            browser.get("editorMatchesExpected") if browser else None,
            browser.get("lastSavedMatchesExpected") if browser else None,
        )
        now = time.monotonic()
        polls += 1
        latest = {
            "browser": browser,
            "raw": raw,
            "file_sha256": file_sha,
            "write_post_count": write_posts,
            "poll_count": polls,
            "terminal": terminal,
        }

        if terminal and signature == stable_signature:
            quiet_ms = (now - stable_since) * 1000 if stable_since is not None else 0
            if quiet_ms >= QUIET_MS:
                server = page.evaluate(
                    """rel => fetch('/api/work?p=' + encodeURIComponent(rel))
                       .then(response => response.json())""",
                    rel,
                )
                final_browser = _browser_sample(page)
                final_raw = target.read_bytes()
                final_sha = sha256_bytes(final_raw)
                final_posts = count_work_write_posts(requests)
                current = server.get("work") or server.get("saved") or {}
                final_ok = bool(
                    final_raw == raw
                    and final_posts == write_posts
                    and browser_text(current.get("content")) == expected_browser
                    and server.get("currentVersion") == final_sha
                    and (server.get("saved") or {}).get("version") == expected_saved_version
                    and final_browser
                    and final_browser.get("editorMatchesExpected")
                    and final_browser.get("lastSavedMatchesExpected")
                    and final_browser.get("currentVersion") == final_sha
                    and final_browser.get("workHash") == final_sha
                    and final_browser.get("savedVersion") == expected_saved_version
                    and not final_browser.get("saving")
                    and not final_browser.get("loading")
                    and not final_browser.get("conflict")
                )
                if final_ok:
                    return {
                        "state": server,
                        "browser": final_browser,
                        "raw": final_raw,
                        "file_sha256": final_sha,
                        "write_post_count": final_posts,
                        "poll_count": polls,
                        "quiet_ms": round(quiet_ms, 3),
                        "settled": True,
                    }
                stable_signature = None
                stable_since = None
        elif terminal:
            stable_signature = signature
            stable_since = now
        else:
            stable_signature = None
            stable_since = None

        page.wait_for_timeout(POLL_MS)

    raise AssertionError(
        "Markdown write did not reach a stable browser/server/file state within "
        f"{timeout_s:.1f}s: {latest}"
    )

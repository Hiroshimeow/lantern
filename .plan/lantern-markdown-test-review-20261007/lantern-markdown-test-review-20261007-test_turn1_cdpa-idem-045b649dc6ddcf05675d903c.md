# TEST + REVIEW report — lantern-markdown-test-review-20261007 — turn 1

Role: independent TEST + REVIEW owner  
Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`  
Branch: `feature/lantern-markdown-export-20261006`  
Baseline / current HEAD at intake: `387a5f17a30ab60f50ae290c8651511608f153d1`  
Execution device: `LPPDUONGNH66-1` (`lppduongnh66-1-7337f19f`, Windows)  
Python used for acceptance: CPython 3.12.13 at `C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe`  
Node: v24.14.1  
Browser evidence: Chrome 154.0.8037.93

Relevant reusable skills discovered/loaded before verification:
- `verification-before-completion`
- `webapp-testing`
- `python-engineering-conventions`

No implementation file was edited. A temporary browser-check script was written under `%LOCALAPPDATA%\Temp\lantern-md-t7`; its temporary Markdown fixture was removed by the script. Repository truth was not changed except for this required report path.

## Executive result

**FAIL — route DEV. The Markdown implementation is not technically mergeable yet.**

A reproducible parser/security defect violates the explicit raw-HTML escape contract (M-A1) and structural allowlist intent (M-A3): raw HTML embedded in a Markdown link label is inserted into a stashed anchor fragment without escaping, then restored *after* the main `h(work)` escape pass.

Exact source:
- `plugin.py:305` captures the raw label.
- `plugin.py:310` interpolates `{label}` into trusted/stashed HTML without `h(label)`.
- `plugin.py:314` escapes only the placeholder-bearing work string.
- `plugin.py:320-327` restores the stashed fragment verbatim, reintroducing the raw label.

Deterministic Python repro:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -c "import tempfile; from pathlib import Path; import plugin; td=tempfile.TemporaryDirectory(); root=Path(td.name); p=root/'x.md'; p.write_text('[<style>body{display:none}</style>](https://example.com)',encoding='utf-8'); page=plugin.render_preview_page(p,root).decode('utf-8'); assert '<style>' not in page, page[page.index('<article'):page.index('</article>')+10]"`

Actual: exit 1 with rendered output containing:

`<a href="https://example.com" ...><style>body{display:none}</style></a>`

Focused Chrome 154 confirmation used a temporary fixture containing:

`[<style>body{--lantern-review-injected: 1px}</style>](https://example.com)`

Actual browser observation:
- `.md-preview style` count: 1
- computed `body` custom property `--lantern-review-injected`: `1px`
- therefore the injected author CSS is parsed and applied.

This is not merely a governance residual risk. It is an implementation defect. The nonce-only script CSP still blocks author scripts, but the page deliberately allows inline styles for the app template, so this parser escape hole gives document content active CSS injection capability. Current tests cover top-level raw HTML (`test_plugin.py:50`) and a structural allowlist fixture (`test_plugin.py:170`) but do not exercise raw HTML nested inside link labels.

Required DEV action: escape link-label text before stashing/restoration while preserving the intended nested-stash behavior, and add a regression case that proves raw HTML inside Markdown labels remains escaped and the structural allowlist still holds.

## Required TEST matrix

### 1. Fresh full Python suite — PASS

First, the unqualified `python` launcher was unavailable on this device (Windows Store alias only). Execution identity was then resolved to the installed uv-managed CPython 3.12.13 above.

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest discover -v`

Expected: all repository Python tests pass.

Actual:
- exit code 0
- `Ran 37 tests in 8.550s`
- `OK`

### 2. Focused `test_plugin` — PASS

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest -v test_plugin`

Expected: all focused plugin tests pass.

Actual:
- exit code 0
- `Ran 13 tests in 0.081s`
- `OK`

Important limitation: these tests do not cover the failing nested-link-label raw-HTML case above.

### 3. JavaScript syntax + diff whitespace — PASS

Command:

`node --check static\markdown_preview.js && node --check static\terminal_scm.js && git diff --check`

Expected: exit 0, no diagnostics.

Actual:
- exit code 0
- no stdout/stderr

### 4. Mermaid SHA-256 — PASS

Command:

`certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256`

Expected:

`581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

Actual: exact match; `certutil` exit 0.

### 5. Immutable-file diff against baseline — PASS

Command:

`git diff --exit-code 387a5f17a30ab60f50ae290c8651511608f153d1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt`

Expected: no diff.

Actual:
- exit code 0
- no output

No UniKey/terminal scope was reopened.

### 6. Retained browser evidence — PASS for measured contract; aggregate long tasks correctly attributed

Evidence file:

`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-results.json`

File timestamp observed: 2026-10-07 10:34 local, immediately before this review. Browser: Chrome 154.0.8037.93.

Observed product acceptance:
- HTTP 200
- 9 Mermaid wrappers
- 7 successful SVG renders
- 1 malformed render failure isolated
- 1 oversize case isolated
- page cap evidence: 24 wrappers + 1 fallback
- plain Markdown: `mermaidLoaded=false`, zero Mermaid vendor requests
- same-origin non-nonce `/owned.js`: `owned_ran=false`; one expected CSP violation logged
- no page errors
- PNG: 4,454 bytes, valid PNG signature
- PDF: 75,596 bytes, `%PDF-` signature
- print action observed as called

Isolated Mermaid attribution across three runs:
- bundle long task: 216 ms, 220 ms, 209 ms — all **<=250 ms**
- initialize elapsed: 3.5 ms, 4.4 ms, 3.3 ms
- required render elapsed ranges:
  - flowchart: 41.3–42.5 ms
  - sequence: 20.0–22.9 ms
  - class: 25.4–26.1 ms
  - state: 22.9–23.1 ms
  - ER: 19.5–21.6 ms
  - Gantt: 11.8–14.1 ms
  - pie: 61.2–63.1 ms
- worst required render: 63.1 ms — **<=100 ms**

The full product page also recorded aggregate LongTask entries of 371 ms, 139 ms, and 97 ms. Per the authoritative contract, these are **not** classified as Mermaid parse failures: the isolated bundle-attribution measurements are 209–220 ms and therefore satisfy the <=250 ms first-load budget. No contrary attribution evidence was found.

### 7. Focused browser export timing — PASS

Because retained `acceptance-results.json` verified PNG generation but did not isolate export-task timing, a focused Chrome 154 check was rerun against the already-running local Lantern origin.

Procedure:
- only `http://127.0.0.1:18765` requests allowed;
- wait for `pendingRenders`;
- clear focused LongTask observations after idle;
- call `window.__lanternMarkdownPreview.exportPng(...)`;
- capture download and post-export LongTask observations.

Actual:
- export elapsed: 20.8 ms
- export LongTask entries: none
- filename: `all-diagram-1.png`

Result: measured export work satisfies the <=100 ms subsequent-task budget.

### 8. PNG dimensions — PASS

Procedure: parse the retained PNG IHDR directly with Python stdlib.

Artifact:

`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-diagram-1.png`

Actual:
- 4,454 bytes
- signature `89504e470d0a1a0a`
- dimensions: 176 x 336
- pixels: 59,136

This is within the implementation caps of <=8192 px per side and about 32 MP. Static export logic is at `static/markdown_preview.js:104`.

### 9. Security / parser / CSP / offline inspection

#### Unsafe URL normalization — PASS for tested corpus

Fresh `test_plugin` passed the adversarial URL cases covering C0, mixed-case script schemes, entity-decoded `javascript:`, `data:`, protocol-relative URLs, traversal, and double-encoding. Local paths are confined under root and external author images are rejected.

#### Raw HTML escaping — **FAIL / BLOCKER**

See executive result. Raw HTML inside a Markdown link label bypasses escaping and can inject active CSS.

#### Nonce coverage and same-origin uploaded script execution — PASS

Relevant implementation:
- `plugin.py:759`: nonce-only `script-src`
- `plugin.py:773`: exact CSP meta
- `plugin.py:777`: app script carries nonce
- `static/markdown_preview.js:17-18`: lazily created local Mermaid script uses the current app-script nonce

Retained Chrome evidence:
- exact nonce CSP present
- attempted same-origin non-nonce `/owned.js` was blocked
- `owned_ran=false`

#### Mermaid strict configuration — PASS

Relevant implementation:
- `static/markdown_preview.js:27`: `securityLevel: "strict"`, `startOnLoad:false`, error suppression
- `static/markdown_preview.js:37`: conservative DOMPurify config
- fixed theme / `htmlLabels:false` / text and edge caps / secure list are present in the same initialization block

#### Malformed / oversized / page cap isolation — PASS

Relevant implementation:
- `static/markdown_preview.js:52`: source-size rejection
- per-diagram render catches errors and continues
- `plugin.py:408`: server-side cap of 24 diagrams
- retained browser evidence: seven successful required types, one malformed isolated, one oversized isolated, 24+fallback cap behavior

#### Print / PDF path — PASS for required observed behavior

Relevant implementation:
- `static/markdown_preview.js:149`: print action waits for `pendingRenders` before `window.print()`
- print CSS sets the explicit light-print behavior, overflow changes, static table headers, wrapped `pre`, and responsive SVG

Retained browser evidence:
- print callback invoked
- print media made toolbar hidden and `pre` wrap
- generated PDF is non-empty (75,596 bytes) with valid signature

#### Offline / lazy behavior — PASS

Relevant implementation:
- Mermaid bundle URL is local: `/static/vendor/mermaid-11.17.2.min.js`
- bundle load is skipped when no Mermaid diagrams exist

Retained acceptance harness blocked every non-Lantern origin. No external blocked requests were recorded; plain Markdown made zero Mermaid vendor requests.

## REVIEW decision

**Not mergeable on the Markdown feature branch in the current working tree.**

Blocker:
- `plugin.py:305-310,314,320-327` — unescaped Markdown link-label HTML is restored verbatim after the escape pass.
- deterministic Python repro exits 1.
- focused Chrome 154 repro proves injected `<style>` is parsed and applied.

This is an implementation safety failure and must route to DEV. It is not appropriate to recommend commit while M-A1/M-A3 are false.

Everything else in the assigned Markdown/Mermaid/PNG/PDF lane that was measured is green: fresh suites, JS syntax, diff hygiene, exact Mermaid hash, immutable-file guard, lazy loading, first-load attribution, initialize/render/export performance, seven required Mermaid types, malformed/oversize isolation, page cap, nonce CSP behavior, local/offline loading, PNG bounds, and non-empty PDF.

## Governance residual-risk gate

Existing project reports explicitly state that:
- security-owner residual-risk sign-off is unavailable; and
- the follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving is absent.

Per the operator instruction, this is a **release-governance gate**, not a code-correctness failure. It does not change the DEV route caused by the parser defect above. After DEV fixes and re-verification, PLAN/release governance must still close that sign-off/ticket gate before release.

## Route

`DEV`

Reason: reproducible implementation failure in the assigned Markdown parser/security boundary. No product changes were made by TEST/REVIEW.

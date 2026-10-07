# DEV report — lantern-markdown-test-review-20261007 — turn 1

Role: DEV implementation owner under the TEST/REVIEW-only Markdown lane  
Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`  
Branch: `feature/lantern-markdown-export-20261006`  
Baseline / HEAD: `387a5f17a30ab60f50ae290c8651511608f153d1`  
Execution device: `LPPDUONGNH66-1` (`lppduongnh66-1-7337f19f`)  
Closing role: TEST

Relevant skills loaded/used:
- `executing-plans`
- `verification-before-completion`
- `webapp-testing`
- `python-engineering-conventions`
- `ponytail`

## Result

Route **TEST**.

The blocker reported by incoming TEST/REVIEW is no longer present in the current workspace. The workspace changed after the incoming report was written, outside this DEV turn:

- incoming TEST report timestamp observed: 2026-10-07 10:43:05 local
- `plugin.py` timestamp observed: 2026-10-07 10:44:10 local
- `test_plugin.py` timestamp observed: 2026-10-07 10:44:34 local

I did **not** edit either implementation or test source.

Current source now has the required escaping at `plugin.py:304-311`:

`f'<a href="{h(target)}" target="_blank" rel="noopener noreferrer">{h(label)}</a>'`

Current tests now include `test_plugin.py:118-125`, `test_link_label_raw_html_is_escaped_before_stash_restore`, which asserts the raw HTML label is escaped and not emitted as an active `<img>`.

Because source work is already present and only independent post-fix runtime/acceptance proof remains, the RouteContract sends this turn to TEST rather than making another product edit.

## Source/test changes made by this DEV turn

Repository implementation/test changes: **none**.

Created by this turn:
- this required report only:
  `.plan/lantern-markdown-test-review-20261007/lantern-markdown-test-review-20261007-dev_turn1_cdpa-idem-045b649dc6ddcf05675d903c.md`

Temporary test helper outside the repository:
- `C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\focused-current.py`

No terminal/UniKey files were modified.

## Fresh verification actually run

### 1. Full Python suite — PASS

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest discover -v`

Actual:
- exit 0
- `Ran 38 tests in 11.094s`
- `OK`
- includes the new link-label regression test

### 2. Focused `test_plugin` — PASS

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest -v test_plugin`

Actual:
- exit 0
- `Ran 14 tests in 0.083s`
- `OK`

### 3. Original parser symptom, corrected to inspect the Markdown article — PASS

The incoming report's one-line assertion used `assert '<style>' not in page`, which also matches Lantern's legitimate template `<style>` element. I reran the same attack while inspecting only the rendered `<article>`.

Actual rendered article:

`<article class='md-preview'><p><a href="https://example.com" target="_blank" rel="noopener noreferrer">&lt;style&gt;body{display:none}&lt;/style&gt;</a></p></article>`

Assertions:
- no active `<style>` inside the Markdown article
- escaped `&lt;style&gt;...&lt;/style&gt;` is present
- exit 0

This directly verifies the source-level injection symptom is fixed in current Python output.

### 4. JavaScript syntax and diff hygiene — PASS

Command:

`node --check static\markdown_preview.js && node --check static\terminal_scm.js && git diff --check`

Actual:
- exit 0
- no diagnostics

### 5. Mermaid SHA-256 — PASS

Command:

`certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256`

Actual exact SHA-256:

`581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

### 6. Immutable-file guard — PASS

Command:

`git diff --exit-code 387a5f17a30ab60f50ae290c8651511608f153d1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt`

Actual:
- exit 0
- no output

No UniKey/terminal scope was reopened.

## Retained browser evidence inspected

Retained evidence:
`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-results.json`

Chrome: `154.0.8037.93`.

The retained evidence remains internally consistent with the authoritative performance contract for the unchanged Mermaid/PNG/PDF code:
- plain Markdown: Mermaid not loaded; zero Mermaid vendor requests
- 7 required Mermaid types rendered
- malformed and oversize cases isolated
- page cap: 24 wrappers + fallback
- exact nonce CSP blocked same-origin non-nonce `/owned.js`
- PNG and PDF non-empty
- isolated bundle long tasks: 216 ms, 220 ms, 209 ms, all <=250 ms
- initialize: 3.3–4.4 ms
- required diagram renders: 11.8–63.1 ms
- aggregate full-page LongTask entries: 371 ms, 139 ms, 97 ms

Per the current contract, those aggregate page LongTasks are not Mermaid bundle parse failures because the isolated bundle-attribution measurements are 209–220 ms. I found no contrary attribution evidence.

## Focused post-fix browser check — NOT_MEASURED

A focused Chrome check against the current source was attempted because the incoming browser injection evidence predates the current `h(label)` fix.

Attempt 1:
- `node focused-review.js`
- failed before browser launch: `Cannot find module 'playwright'`

Attempt 2:
- uv-managed CPython 3.12.13 running `focused-current.py`
- failed before browser launch: `ModuleNotFoundError: No module named 'playwright'`

No browser result is claimed for the post-fix parser state in this DEV turn. TEST should rerun the focused Chrome injection check in the environment that produced the retained acceptance evidence.

## Targeted code review of current source

No new source blocker found in the inspected Markdown lane:

- unsafe URL handling: `plugin.py:237-278` trims C0/control whitespace, rejects protocol-relative targets, allows only `http`/`https`/`mailto` for external links, rejects external author images, and confines local paths under root
- raw label escaping: `plugin.py:304-311` now applies `h(label)` before stashing the anchor
- nested stash behavior remains covered by `test_plugin.py:111-116`
- Mermaid page cap: `plugin.py:408` limits active Mermaid wrappers to 24
- CSP: `plugin.py:756-777` generates a random nonce, uses nonce-only `script-src`, and nonces the app script
- lazy Mermaid nonce propagation: `static/markdown_preview.js:12-22`
- Mermaid strict configuration: `static/markdown_preview.js:25-44`, including `securityLevel: "strict"`, `htmlLabels:false`, bounded text/edge settings, DOMPurify forbids, and secure config keys
- malformed render isolation: `static/markdown_preview.js:47-70`
- PNG dimensions: `static/markdown_preview.js:99-131` caps dimensions at 8192 per side and about 32 MP
- print path: `static/markdown_preview.js:149` waits for pending renders before `window.print()`
- offline behavior: Mermaid bundle URL is local and is not requested on plain Markdown

Source-level status: the prior parser/security blocker is resolved in the current working tree. This DEV turn does **not** recommend commit yet because the required independent post-fix browser acceptance has not been re-measured.

## Remaining risk / governance

1. **Independent post-fix browser verification required.** TEST must confirm the escaped link-label HTML produces zero `.md-preview style` nodes and no applied injected CSS in Chrome 154, then rerun any acceptance subset it considers necessary.
2. The security-owner residual-risk sign-off and follow-up ticket for iframe sandboxing / same-origin uploaded HTML/SVG serving remain a release-governance gate, not a current code-correctness failure.
3. Regression RED evidence was not recreated by this DEV turn by reverting the fix; reverting concurrent source work would violate the preserve/no-product-change constraints. The incoming TEST report supplies the pre-fix failure evidence, while this turn supplies fresh GREEN current-source evidence.

## Route

`TEST`

Reason: current source/test already contain the parser fix and fresh Python/static verification is green; independent runtime/browser acceptance remains the legal next step and TEST is the closing role.

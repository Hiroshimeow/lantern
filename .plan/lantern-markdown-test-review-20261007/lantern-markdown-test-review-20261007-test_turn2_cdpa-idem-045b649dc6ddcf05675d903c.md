# TEST report — lantern-markdown-test-review-20261007 — turn 2

Role: independent TEST closing role  
Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`  
Branch: `feature/lantern-markdown-export-20261006`  
Baseline / HEAD: `387a5f17a30ab60f50ae290c8651511608f153d1`  
Execution device: `LPPDUONGNH66-1` (`lppduongnh66-1-7337f19f`)  
Python: CPython 3.12.13 at `C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe`  
Node: v24.14.1  
Browser: Chrome 154.0.8037.93

Loaded skills:
- `verification-before-completion`
- `webapp-testing`

## Result

**Markdown implementation acceptance is green. Route PLAN.**

The turn-1 parser/security blocker is fixed in current source:
- `plugin.py` now escapes Markdown link labels with `h(label)` before stashing/restoring the anchor fragment.
- The focused Chrome 154 check against a fresh server launched from the current workspace produced zero injected `<style>` nodes and no applied injected CSS.
- Fresh full and focused Python suites pass.
- All required static/hash/scope guards pass.
- Retained Mermaid/PNG/PDF acceptance evidence remains valid for the unchanged Mermaid/export code and satisfies the current performance contract.

This role does **not** route DONE because the release-governance gate remains open:
- security-owner residual-risk sign-off remains unavailable;
- the required follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving remains absent.

Per operator instruction, those are PLAN/release-governance gaps, not code-correctness failures.

## Incoming DEV handoff reviewed

Handoff:
`.plan/lantern-markdown-test-review-20261007/lantern-markdown-test-review-20261007-dev_turn1_cdpa-idem-045b649dc6ddcf05675d903c.md`

DEV reported that the source/test fix appeared in the workspace after TEST turn 1 and that DEV itself made no product changes. Current source confirms:
- `plugin.py:310` uses `{h(label)}` in the stashed anchor.
- `test_plugin.py` contains a regression for raw HTML in link labels across heading/table/paragraph contexts.

During this TEST turn, the first fresh run exposed a deterministic test-fixture issue: the regression initially audited the whole generated page and therefore counted Lantern's legitimate template `<meta>` and `<style>` elements. Before any successful TEST edit was applied, the workspace test changed to scope the audit to the `<article class="md-preview">...` region. The attempted exact edit did not match and therefore did not write. The current corrected test was then independently rerun and passed.

No implementation file was modified by TEST.

## Fresh verification

### 1. Full Python suite — PASS

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest discover -v`

Expected:
- all repository tests pass.

Actual:
- exit code 0
- `Ran 38 tests in 8.028s`
- `OK`

The new regression `test_link_label_raw_html_is_escaped_in_block_contexts` passed.

### 2. Focused `test_plugin` — PASS

Command:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe -m unittest -v test_plugin`

Actual:
- exit code 0
- `Ran 14 tests in 0.112s`
- `OK`

### 3. JavaScript syntax + diff hygiene — PASS

Command:

`node --check static\markdown_preview.js && node --check static\terminal_scm.js && git diff --check`

Actual:
- exit code 0
- no diagnostics

### 4. Mermaid SHA-256 — PASS

Command:

`certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256`

Actual exact SHA-256:

`581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

### 5. Immutable-file diff against baseline — PASS

Command:

`git diff --exit-code 387a5f17a30ab60f50ae290c8651511608f153d1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt`

Actual:
- exit code 0
- no output

No terminal/UniKey scope was reopened.

## Post-fix browser verification

The old server on port 18765 was still running a stale pre-fix Python process and reproduced the old injection. That observation was **not** treated as current-source evidence.

To measure the current workspace deterministically, TEST launched a fresh Lantern process from the current source on port 18766 with:

`C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe lan_drive.py --config C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\config.yaml --port 18766`

A focused Chrome 154 Playwright check then loaded a Markdown fixture containing:

`[<style>body{--lantern-review-injected: 1px}</style>](https://example.com)`

Non-Lantern requests were aborted.

Actual current-source browser result:
- Chrome: `154.0.8037.93`
- `.md-preview style` count: `0`
- computed `body` property `--lantern-review-injected`: empty
- rendered article:

`<p><a href="https://example.com" target="_blank" rel="noopener noreferrer">&lt;style&gt;body{--lantern-review-injected: 1px}&lt;/style&gt;</a></p>`

Result: **PASS**. The turn-1 raw-HTML/CSS injection blocker is closed in the current implementation.

The temporary current-source server was terminated after the check.

## Retained Mermaid / PNG / PDF evidence

Retained evidence remains:

`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-results.json`

Chrome 154.0.8037.93.

Previously verified and unchanged Mermaid/export implementation evidence:
- plain Markdown: zero Mermaid vendor requests
- seven required Mermaid types render
- malformed case isolated
- oversize case isolated
- page cap: 24 wrappers + fallback
- same-origin non-nonce script blocked by exact nonce CSP
- PNG non-empty
- PDF non-empty
- isolated Mermaid bundle long tasks: 216 ms, 220 ms, 209 ms — all <=250 ms
- initialize: 3.3–4.4 ms
- required diagram renders: 11.8–63.1 ms — all <=100 ms
- focused export timing from TEST turn 1: 20.8 ms, no export LongTask

The aggregate full-page LongTask values (371 ms, 139 ms, 97 ms) are not classified as Mermaid parse failures because the isolated bundle-attribution measurements are 209–220 ms. No evidence attributes the larger aggregate entries to Mermaid bundle parse/evaluation itself.

## REVIEW / mergeability decision

**Technically mergeable on the Markdown feature branch.**

No remaining code-correctness blocker was found in the assigned Markdown/Mermaid/PNG/PDF lane after the parser fix and fresh post-fix browser verification.

Recommendation:
- commit on the feature branch;
- do not push or merge from this role.

## Governance gate

Fresh repository search still finds prior project records stating:
- `Security-owner residual-risk sign-off remains unavailable.`
- `Required follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving remains absent.`

These are release-governance requirements, not implementation failures. They prevent DONE/release closure but do not invalidate the technical mergeability decision.

## Route

`PLAN`

Reason:
- TEST + REVIEW acceptance for the Markdown implementation is green.
- Remaining work is non-implementation release governance: obtain the security-owner sign-off and create/record the required follow-up ticket.

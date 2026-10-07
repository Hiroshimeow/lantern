# PLAN report — lantern-markdown-test-review-20261007 — turn 1

Role: PLAN scope/workflow owner  
Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`  
Branch: `feature/lantern-markdown-export-20261006`  
Baseline / current HEAD verified: `387a5f17a30ab60f50ae290c8651511608f153d1`  
Execution device: `LPPDUONGNH66-1` (`lppduongnh66-1-7337f19f`)  
Closing role per task: TEST

## Route decision

**Route DEV, for a documentation-contract correction only.**

The current Markdown/Mermaid/PNG/PDF implementation and browser evidence are technically green against the authoritative performance contract in this task, but the branch's changed `spec.md`, `plan.md`, and `tasks.md` explicitly replace the hard timing gates with non-binding telemetry language. That is a material contract mismatch in the current diff and must be corrected before final TEST/REVIEW can recommend commit.

No product-code change is currently justified. DEV must not touch Markdown implementation/test/runtime files unless a new TEST failure proves a separate deterministic issue. Terminal/UniKey scope remains deferred and immutable.

Installed-skill discovery found no repository test/review/code-review skill applicable to this task; no unrelated artifact/plugin skill was loaded.

## Repository truth verified

- Worktree root resolves to the requested repository.
- Current branch is exactly `feature/lantern-markdown-export-20261006`.
- Current `HEAD` is exactly the supplied implementation-diff baseline `387a5f17a30ab60f50ae290c8651511608f153d1`; Markdown work remains uncommitted.
- Tracked changes: `plugin.py` plus the three Spec-Kit documents.
- Untracked feature files include `test_plugin.py`, `static/markdown_preview.js`, `static/vendor/mermaid-11.17.2.min.js`, and `static/vendor/mermaid-11.17.2.LICENSES.txt`.
- Immutable terminal/backend/dependency files have zero diff against baseline:
  `static/terminal_scm.js`, `static/vendor/xterm.js`, `lantern_terminal.py`, `lantern_ws.py`, `lan_drive.py`, `requirements.txt`.

Fresh PLAN spot checks on the current workspace:
- `node --check static\markdown_preview.js`: PASS.
- `node --check static\terminal_scm.js`: PASS.
- `git diff --check`: PASS.
- Immutable-file `git diff --exit-code` against baseline: PASS.
- Mermaid SHA-256: exact PASS  
  `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`.

## Current implementation state

### COMPLETE / preserve

The turn-1 parser/security defect is fixed in current source:
- `plugin.py:304-311` escapes link labels with `h(label)` before stashing generated anchor HTML.
- `test_plugin.py:118-147` contains a regression that scopes adversarial structural checks to the Markdown article and proves nested raw HTML labels do not become active `meta`, `style`, `img`, or `svg` nodes.

Security/runtime boundaries inspected and found consistent with the intended design:
- URL normalization/confinement: `plugin.py:237-278`.
- Mermaid page cap and escaped source placeholders: `plugin.py:354-521`, active Mermaid wrappers capped at 24.
- Exact nonce-only preview CSP and nonce-covered app script: `plugin.py:756-777`.
- Lazy local Mermaid load with nonce propagation: `static/markdown_preview.js:12-22`.
- Strict Mermaid configuration, bounded text/edge settings, conservative DOMPurify config and secure keys: `static/markdown_preview.js:25-44`.
- Per-diagram render failure isolation: `static/markdown_preview.js:47-73`.
- Sequential/yield-separated rendering: `static/markdown_preview.js:75-88`.
- PNG dimension/pixel bounds and `toBlob` path: `static/markdown_preview.js:90-134`.
- Print waits for pending renders: `static/markdown_preview.js:144-160`.
- No terminal/UniKey implementation boundary was reopened.

### Current browser evidence — technically green

Retained evidence inspected at:
`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-results.json`

Current file is Chrome `154.0.8037.93` evidence and was updated after the prior TEST report. Its current measurements are:
- Product page HTTP 200.
- 9 Mermaid wrappers; 7 successful SVGs; one malformed case isolated; one oversize case isolated.
- Page-cap fixture: 24 wrappers + 1 fallback.
- Plain Markdown: `mermaidLoaded=false`, zero Mermaid vendor requests.
- Exact nonce CSP blocks same-origin non-nonce `/owned.js`; `owned_ran=false`; no page errors.
- PNG: 4,454 bytes, valid PNG signature.
- PDF: 75,599 bytes, `%PDF-` signature.
- Print action observed.

Isolated attribution, three runs:
- bundle long task: **219 ms, 199 ms, 189 ms** — all <= authoritative **250 ms** first-load limit;
- initialize: **3.2 ms, 3.4 ms, 3.2 ms** — <=100 ms;
- required diagram renders: worst observed **73.2 ms** — <=100 ms.

The same product page records larger aggregate LongTask entries (including 508 ms, 174 ms, 141 ms). Under the authoritative contract these are **not** Mermaid parse failures without attribution. The isolated bundle attribution is below 250 ms, and no contrary evidence currently proves the aggregate entries are Mermaid bundle parse/evaluation.

Prior independent TEST evidence also records focused PNG export work at 20.8 ms with no export LongTask and a successful post-fix Chrome injection check. Final TEST must decide whether that evidence remains sufficiently current after the docs-only correction or rerun the focused browser subset; missing/stale proof must be marked INCOMPLETE, never PASS.

## BLOCKER — changed documentation contradicts the authoritative contract

The user-supplied contract for this task is binding:
- Mermaid bundle is lazy and never loads on plain Markdown.
- Isolated first-load Mermaid bundle parse/evaluation must be <=250 ms once per Mermaid preview page.
- Every subsequent initialize/render/export main-thread task must be <=100 ms.
- Aggregate page LongTask entries are not Mermaid parse failures without attribution.

The current branch diff instead weakens/removes these hard gates:

1. `specs/001-terminal-ime-markdown-export/spec.md:203`
   says the performance contract is “behavioral, not a hardware-specific millisecond SLA” and timing is reference telemetry rather than a hard gate.

2. `specs/001-terminal-ime-markdown-export/spec.md:261`
   changes M-A11 to telemetry/invariants and omits the authoritative <=250 ms / <=100 ms acceptance thresholds.

3. `specs/001-terminal-ime-markdown-export/plan.md:132`
   says bundle/render/PNG durations are “regression telemetry rather than portable hard SLAs”.

4. `specs/001-terminal-ime-markdown-export/tasks.md:177`
   directs T6 to use “behavioral bounds rather than hardware-specific timing promises” and record timing as telemetry.

This mismatch is a branch/documentation correctness blocker even though the current implementation happens to pass the authoritative timing thresholds.

## Requirement classification

### PRESERVE
- All deferred terminal/UniKey files and requirements remain unchanged.
- Current Markdown parser/CSP/security implementation boundaries.
- Lazy local Mermaid load, strict config, page cap=24, sequential/yield-separated rendering.
- PNG dimension bounds, print path, offline/no-CDN behavior.
- Security-owner residual-risk sign-off plus follow-up ticket remain a **release-governance gate**, not a code-correctness defect unless new evidence demonstrates an unsafe implementation.

### COMPLETE
- Current product implementation is technically consistent with the Markdown feature contract.
- Current retained Chrome 154 evidence satisfies the authoritative <=250 ms isolated first-load bundle limit and <=100 ms initialize/render limits.
- Raw HTML/link-label injection blocker is fixed and independently browser-verified.
- Current static/hash/immutable-file spot checks are green.

### FIX
Documentation contract only:
- `specs/001-terminal-ime-markdown-export/spec.md`
- `specs/001-terminal-ime-markdown-export/plan.md`
- `specs/001-terminal-ime-markdown-export/tasks.md`

No product/runtime/test code change is requested by PLAN.

## DEV execution contract

DEV must make the smallest deterministic documentation-only correction necessary to align the three changed Spec-Kit files with the authoritative contract:

1. State that plain Markdown makes zero Mermaid-bundle requests and Mermaid loads lazily at most once when needed.
2. State the isolated first-load Mermaid bundle parse/evaluation acceptance gate: **<=250 ms once per Mermaid preview page**.
3. State that every subsequent initialize/render/export main-thread task must be **<=100 ms**.
4. State that a larger aggregate full-page LongTask is not by itself a Mermaid parse failure; it becomes a blocker only when evidence attributes the over-budget task to Mermaid bundle parse/evaluation or another governed Mermaid operation.
5. Preserve all bounded/sequential/yield invariants and the 24-diagram cap.
6. Preserve M-A12/security-owner residual-risk sign-off and the iframe/same-origin uploaded HTML/SVG follow-up ticket as a release-governance gate.
7. Do not edit `plugin.py`, `test_plugin.py`, `static/markdown_preview.js`, Mermaid assets, terminal files, backend files, or `requirements.txt`.
8. Do not push, merge, or commit.

After this docs-only correction, route directly to TEST.

## Required TEST/REVIEW after DEV

TEST must independently close the Markdown lane using the authoritative contract:

1. Fresh full Python suite and focused `test_plugin`.
2. `node --check static/markdown_preview.js` and `node --check static/terminal_scm.js`.
3. `git diff --check`.
4. Exact Mermaid SHA-256 equals `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`.
5. Immutable-file diff against baseline is empty for all deferred terminal/backend/dependency files.
6. Inspect current retained Chrome evidence and rerun focused browser acceptance where freshness/attribution is insufficient. Explicitly distinguish isolated Mermaid attribution from aggregate product-page LongTasks. Verify <=250 ms isolated first-load bundle parse/evaluation and <=100 ms subsequent initialize/render/export tasks.
7. Re-review unsafe URLs, raw HTML escaping, nonce coverage, same-origin non-nonce uploaded script blocking, Mermaid strict config, malformed/oversize isolation, PNG dimensions, print/PDF path, and offline behavior.
8. Verify the corrected spec/plan/tasks now encode the same binding performance contract used by TEST.
9. Decide technical mergeability. If green, recommend commit on the feature branch only; do not push or merge.
10. Record the security-owner sign-off/follow-up-ticket status as release governance. Do not misclassify their absence as a product-code failure unless implementation evidence itself is unsafe.

TEST remains the closing role and owns any final DONE transition allowed by its RouteContract.

# TEST report — lantern-markdown-export-impl-20261006 — turn 2

Role: independent TEST verification owner
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Baseline / HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1
Execution device: LPPDUONGNH66-1 (device_id lppduongnh66-1-7337f19f)
Node: v24.14.1
Python: uv-managed Python 3.14.3
Browser harness: Playwright-resolved Chromium 151.0.7922.34 from C:\Users\DuongNH66\Desktop\git\node_modules\playwright

## Decision

FAIL — route DEV.

Fresh deterministic tests and functional browser acceptance are green, but the corrected M-A11 performance contract is violated reproducibly by the isolated first-load Mermaid bundle parse/evaluation task.

Binding contract:
- isolated first-load Mermaid bundle parse/evaluation <=250 ms per Mermaid preview page
- subsequent attributable initialize/render/PNG-export task <=100 ms
- aggregate full-page Long Tasks are not failures without attribution
- any attributed first-load result >250 ms keeps acceptance INCOMPLETE and triggers re-review

Fresh TEST evidence:
- initial 3-run isolated first-load tasks: 254 ms, 208 ms, 239 ms
- independent 6-run rerun: 437 ms, 276 ms, 199 ms, 302 ms, 217 ms, 227 ms
- 3 of the 6 rerun samples exceed 250 ms, and the initial 3-run set also contains a 254 ms breach

This is not a single borderline observation. The <=250 ms first-load requirement is not reliably satisfied in the available accepted Chromium harness. Per the PLAN turn-4 routing contract, this is a reproducible implementation/performance blocker and routes to DEV.

No implementation files were edited by TEST. Temporary verification scripts/artifacts were created only under:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7

The fresh local server was terminated after verification.

## 1. Repository / execution identity — PASS

Procedure:
- pwd / host / user
- git branch --show-current
- git rev-parse HEAD
- git status --short
- node -e "console.log(require.resolve('playwright'))"

Actual:
- workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
- host: LPPDUONGNH66-1
- user: DuongNH66
- branch: feature/lantern-markdown-export-20261006
- HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1
- Playwright resolved to:
  C:\Users\DuongNH66\Desktop\git\node_modules\playwright\index.js

Status: PASS.

## 2. Focused plugin suite — PASS

Command:
uv run --no-project python -m unittest -v test_plugin

Actual:
- exit code 0
- Ran 14 tests in 0.190s
- OK

Status: PASS.

## 3. Full Python suite — PASS

Command:
uv run --no-project python -m unittest discover -v

Actual:
- exit code 0
- Ran 38 tests in 8.891s
- OK

Status: PASS.

## 4. JavaScript syntax / diff hygiene — PASS

Commands:
- node --check static\markdown_preview.js
- node --check static\terminal_scm.js
- git diff --check

Actual:
- all exit 0
- no diagnostics

Status: PASS.

## 5. Mermaid bundle SHA-256 — PASS

Command:
certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256

Expected:
581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8

Actual:
581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8

Status: PASS.

## 6. Immutable files against 387a5f1 — PASS

Command:
git diff --exit-code 387a5f1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt

Actual:
- exit code 0
- no diff output

Status: PASS.

No terminal/UniKey implementation scope was touched.

## 7. Fresh browser server / network isolation

Server command:
uv run --no-project python lan_drive.py --config C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\config.yaml --port 18768

Browser harness:
- Node Playwright with explicit NODE_PATH=C:\Users\DuongNH66\Desktop\git\node_modules
- Chromium 151.0.7922.34
- every request not under http://127.0.0.1:18768 was aborted
- fresh current-worktree process

Status: PASS for execution setup.

## 8. Fresh functional T7 browser acceptance — PASS

Fresh result:
- HTTP 200
- 9 Mermaid wrappers
- 7 successful SVG renders
- 1 malformed Mermaid isolated
- 1 oversized Mermaid isolated
- page-cap test: 24 Mermaid wrappers + 1 fallback
- plain Markdown:
  - mermaidLoaded=false
  - zero Mermaid vendor requests
- zero non-Lantern runtime requests observed
- zero non-Lantern blocked requests were attempted
- exact nonce CSP:
  default-src 'none'; script-src 'nonce-DH-x90vVb_Gkjk__-umQwDJ7R3KjNuOE'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'
- injected same-origin non-nonce /owned.js:
  - request made to Lantern origin
  - execution blocked by CSP
  - ownedRan=false
- PNG:
  - filename all-diagram-1.png
  - 4538 bytes
- generated PDF:
  - 75353 bytes
  - %PDF- signature
- no non-Lantern request appeared in product/plain/cap contexts

Status: PASS.

## 9. Print waits for pending renders — PASS

Procedure:
- before page scripts execute, replace window.print with a recorder
- navigate to all.md
- click Print immediately after DOMContentLoaded, before explicitly awaiting pendingRenders
- recorder captures Mermaid state at actual print invocation

Actual print snapshot:
- svg=7
- failed=1
- oversize=1

Interpretation:
- print was invoked only after all seven valid diagrams had rendered and malformed/oversized cases had settled
- this directly verifies the click path awaited the pending render chain before window.print()

Status: PASS.

## 10. Fresh subsequent governed operation timing — PASS

Initial 3-run attribution harness measured all seven required diagram types.

Initialize:
- run 1: 4.1 ms
- run 2: 3.7 ms
- run 3: 3.4 ms

All <=100 ms.

Render elapsed:
Run 1:
- flowchart 51.4 ms
- sequence 27.6 ms
- class 58.4 ms
- state 32.9 ms
- ER 32.0 ms
- Gantt 19.6 ms
- pie 93.8 ms

Run 2:
- flowchart 44.4 ms
- sequence 22.5 ms
- class 32.2 ms
- state 27.3 ms
- ER 23.8 ms
- Gantt 16.7 ms
- pie 75.2 ms

Run 3:
- flowchart 53.8 ms
- sequence 27.1 ms
- class 42.1 ms
- state 36.7 ms
- ER 33.2 ms
- Gantt 24.6 ms
- pie 98.4 ms

Worst required render: 98.4 ms.
All <=100 ms.

Status: PASS.

## 11. Fresh isolated PNG/export timing — PASS

Procedure:
- load all.md
- await pendingRenders
- clear LongTask observations
- invoke window.__lanternMarkdownPreview.exportPng(wrapper, 1) directly
- wait briefly for post-operation LongTask delivery
- capture download

Actual:
- export elapsed: 9.1 ms
- export LongTask entries: none
- filename: all-diagram-1.png
- size: 4538 bytes
- blocked non-Lantern requests: none

Status: PASS.

The earlier click-to-download wall-clock value of 541 ms is not used as governed main-thread attribution because it includes asynchronous browser/download handling outside the export task. The direct instrumented export operation is the relevant attributable measurement.

## 12. Fresh first-load Mermaid attribution — FAIL / BLOCKER

### Initial independent 3-run measurement

Procedure:
- start from plain Markdown page with no Mermaid loaded
- clear LongTask observer
- append nonce-authorized local Mermaid 11.17.2 script
- record LongTask entries covering first-load parse/evaluation
- repeat in fresh contexts

Actual:
- run 1: 254 ms LongTask
- run 2: 208 ms LongTask
- run 3: 239 ms LongTask

Expected:
- every isolated first-load bundle parse/evaluation task <=250 ms

Actual:
- run 1 exceeds contract by 4 ms

Status after first set: FAIL pending reproducibility check.

### Six-run reproducibility rerun

Same fresh-context procedure, six new contexts.

Actual:
- run 1: 437 ms
- run 2: 276 ms
- run 3: 199 ms
- run 4: 302 ms
- run 5: 217 ms
- run 6: 227 ms

Expected:
- every run <=250 ms

Actual:
- 437 ms >250
- 276 ms >250
- 302 ms >250
- 3 of 6 reruns violate the threshold

Status: FAIL / reproducible blocker.

The failure is specifically attributed to the governed first-load bundle task. It is not an aggregate-page LongTask classification issue.

## 13. Aggregate product Long Tasks — NOT A FAILURE BY THEMSELVES

Fresh product-page LongTasks:
- 281 ms
- 56 ms
- 92 ms

Per contract, the 281 ms aggregate page LongTask is not independently classified as failure because aggregate page LongTasks require attribution.

The blocker is instead the separate isolated first-load attribution in section 12.

Status: informational / contract applied correctly.

## 14. Parent UI responsiveness — INCOMPLETE as a separate manual criterion

Fresh browser evidence confirms:
- render sequence completes
- print click waits correctly
- required individual renders are <=100 ms

However, no direct human interaction/responsiveness study was performed.

Additionally, the isolated bundle task itself reaches 437 ms in one fresh run, so TEST cannot claim a general responsiveness PASS.

Status: INCOMPLETE.

## 15. PDF selectable text / arrowheads / readability / clipping — INCOMPLETE

Fresh PDF generation:
- 75353 bytes
- valid %PDF- signature
- print CSS applied light background/dark text
- print path verified after pending renders

Attempted local Chromium inspection:
- navigating headless Playwright Chromium directly to the generated file:// PDF caused a download rather than a renderable viewer page
- therefore the harness could not inspect selectable text, arrowheads, readability, or clipping

No new PDF parser/renderer dependency was installed.

Status: INCOMPLETE.
No speculative PASS.

## 16. M-A12 governance — INCOMPLETE / non-code

Fresh repository report search still finds prior project records stating:
- security-owner residual-risk sign-off unavailable
- required follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving absent

No new sign-off or ticket evidence was found.

Status: INCOMPLETE release-governance gate.

This is not the reason for DEV routing; the DEV route is caused by the reproducible M-A11 first-load performance failure.

## 17. Cleanup

Temporary harness files were written only under:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7

Fresh server PID tree was terminated with:
taskkill /PID 34320 /T /F

Actual:
- server process and child processes terminated successfully

Repository implementation truth was not modified by TEST.

## Required DEV action

Investigate the first-load Mermaid loading strategy / bundle execution path so the isolated first-load bundle parse/evaluation task reliably satisfies <=250 ms in the accepted Chromium harness.

Re-test must preserve:
- exact reviewed Mermaid 11.17.2 bundle and SHA-256
- no Mermaid load on non-Mermaid pages
- nonce-only CSP
- no new network/CDN dependency
- existing strict/security/bounded/sequential/yield invariants
- immutable terminal/backend files unchanged

Do not weaken or reinterpret the current <=250 ms contract inside DEV. If the threshold itself is considered inappropriate or platform-dependent, that is a PLAN decision, not a TEST pass.

## Route

DEV

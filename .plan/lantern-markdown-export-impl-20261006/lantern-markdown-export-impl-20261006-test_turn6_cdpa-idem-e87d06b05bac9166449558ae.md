# TEST turn 6 report

Role: TEST
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

Independent technical acceptance is GREEN under the revised authoritative M-A11 contract from PLAN turn 8.

Route REVIEW.

No source files were edited by TEST. No commit, push, or merge was performed.

M-A12 remains INCOMPLETE as a governance/release gate: no security-owner residual-risk sign-off and no follow-up ticket evidence were found. This is not an implementation defect and should be dispositioned by REVIEW/governance rather than sent back to DEV.

## 1. Repository identity and deterministic gates

Confirmed:
- branch: feature/lantern-markdown-export-20261006
- HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

Fresh checks:
- uv run --no-project python -m unittest -q
- uv run --no-project python -m unittest -q test_plugin
- node --check static\markdown_preview.js
- node --check static\terminal_scm.js
- git diff --check
- git diff --exit-code 387a5f1 -- static\terminal_scm.js static\vendor\xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
- certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256

Results:
- full Python suite: 39/39 PASS
- focused plugin suite: 15/15 PASS
- JS syntax: PASS
- diff hygiene: PASS
- immutable terminal/backend/dependency scope: PASS
- Mermaid SHA-256: 581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8: PASS

## 2. Current served product structure

Current product server used for browser acceptance:
http://127.0.0.1:18773

Actual served all.md preview verified:
- conditional Mermaid vendor script is in HEAD
- vendor has defer
- markdown_preview.js is in HEAD
- helper has defer
- vendor precedes helper

Normal product request trace contains exactly one Mermaid vendor request.

Plain Markdown product trace contains zero Mermaid vendor requests and window.mermaid remains false.

## 3. Revised M-A11 first-load guardrail — PASS

Accepted method from PLAN turn 8:
- FJP Playwright Chromium
- actual served product HTML
- nine fresh browser contexts
- intercept only static/markdown_preview.js with an empty response so helper initialize/render cannot contaminate vendor parse/evaluation attribution
- actual product-emitted HEAD+defer Mermaid vendor remains unchanged
- PASS: median <=300 ms and no sample >500 ms

Fresh nine samples:
1. 264 ms
2. 268 ms
3. 250 ms
4. 256 ms
5. 265 ms
6. 302 ms
7. 307 ms
8. 253 ms
9. 289 ms

Computed:
- median: 265 ms
- maximum: 307 ms
- median <=300 ms: PASS
- no individual sample >500 ms: PASS

M-A11 first-load: PASS.

## 4. Subsequent governed Mermaid work — PASS

Fresh post-load attribution used the already-loaded current product runtime, after the normal render chain completed, then invoked each required Mermaid family separately.

Measured elapsed values:
- flowchart: 19.7 ms
- sequence: 14.0 ms
- class: 20.9 ms
- state: 28.0 ms
- ER: 18.6 ms
- Gantt: 10.8 ms
- pie: 9.2 ms

Long Task entries attributable to each measured operation: none.

All seven subsequent render operations are <=100 ms: PASS.

Fresh PNG export attribution:
- elapsed: 12.6 ms
- attributable Long Task entries: none
- filename: all-diagram-1.png
- size: 4538 bytes
- blocked/non-Lantern requests: none

PNG export <=100 ms: PASS.

Diagnostic note:
An exploratory wrapper around the initial page render chain observed diagram-7 render elapsed above 100 ms in 3 of 8 cold page runs. This probe was not the accepted subsequent-operation method: it measures the initial render chain during page startup. The authoritative first-load gate is isolated vendor parse/evaluation, while the subsequent-operation gate is measured on the already-loaded runtime as above. The accepted post-load governed probe is green.

## 5. Functional/security/browser acceptance — PASS

Fresh current-product browser acceptance:
- Mermaid wrappers: 9
- valid SVG renders: 7
- malformed diagram isolated: 1
- oversized diagram isolated: 1
- page cap+1 fixture renders/carries only 24 Mermaid wrappers
- Mermaid runtime loaded on Mermaid page
- plain Markdown Mermaid runtime absent
- plain Markdown Mermaid vendor requests: 0
- non-Lantern runtime requests: 0
- blocked unexpected external requests: 0
- nonce-less same-origin /owned.js execution: blocked; ownedRan=false
- unexpected console errors: none
- CSP violation for nonce-less test script observed as expected
- PNG download non-empty and correctly named
- current PDF generation succeeded and produced a non-empty PDF

Exact CSP observed:
default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'

CSP/security acceptance: PASS.

## 6. Seven PNG exports — PASS

Fresh post-load product export set:
1. all-diagram-1.png — 4538 bytes
2. all-diagram-2.png — 20439 bytes
3. all-diagram-3.png — 6962 bytes
4. all-diagram-4.png — 11327 bytes
5. all-diagram-5.png — 16244 bytes
6. all-diagram-6.png — 22207 bytes
7. all-diagram-7.png — 90270 bytes

All seven are non-empty and follow <doc>-diagram-N.png.

## 7. Print waits for pending renders — PASS

Fresh browser harness delayed every Mermaid render by 400 ms and replaced window.print with a timestamp marker.

Observed:
- print click timestamp: 580.1 ms
- final delayed render completion timestamp: 3674.4 ms
- window.print timestamp: 3716.5 ms
- printedAfterRender: true

Therefore the Print / Save as PDF action waits for pendingRenders before invoking print: PASS.

Print media acceptance from current product:
- toolbar hidden in print
- preformatted text wraps for print
- generated PDF is non-empty (75361 bytes in the current functional run)

## 8. Responsiveness / PDF evidence classification

Automated browser interaction remained responsive enough to complete all acceptance actions, sequential renders, downloads, and print/PDF generation without timeouts.

Manual parent-UI responsiveness observation was not independently performed in this turn: INCOMPLETE / NOT_MEASURED.

PDF selectable-text, Mermaid arrowhead visual fidelity, and clipping/readability inspection were not manually/visually re-proven in this turn: INCOMPLETE / NOT_MEASURED.

No speculative PASS is claimed for those manual/visual properties.

## 9. M-A12 governance — INCOMPLETE

Fresh repository/report search found no new evidence that either required governance artifact exists:
- security-owner residual-risk sign-off: absent/unavailable
- follow-up ticket covering iframe sandboxing plus same-origin uploaded HTML/SVG serving: absent

This remains a release-governance gate, not a technical implementation failure.

## 10. Route rationale

Technical acceptance requested by PLAN turn 8 is green:
- revised M-A11 statistical first-load guardrail passes
- deterministic suites pass
- exact bundle/hash and immutable scope pass
- HEAD+defer product structure is active
- no duplicate/dynamic Mermaid fetch on normal path
- subsequent render and PNG-export timing pass
- functional/security/export/print-wait acceptance passes

Only governance/manual evidence remains incomplete.

Route REVIEW for independent correctness/security/governance disposition. Do not commit/push/merge from TEST.

## Route

REVIEW

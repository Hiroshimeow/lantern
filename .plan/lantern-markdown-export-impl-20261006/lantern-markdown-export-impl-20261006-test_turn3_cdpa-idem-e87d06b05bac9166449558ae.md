# TEST turn 3 recovery report

Role: independent TEST verification owner (recovered after the bound TEST web turn stopped without a terminal assistant result)
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Baseline / HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

FAIL current product loading path; route PLAN so PLAN can return the specific fix to DEV.

The DEV turn-3 change from dynamic Mermaid injection to parser-discovered loading is directionally correct, but the current product HTML still emits the Mermaid script at the end of BODY without defer. Independent fresh-context evidence shows that this exact current product path does not reliably satisfy the binding <=250 ms isolated first-load parse/evaluation budget.

A narrower legal loading-path variant — the exact same local nonce-authorized Mermaid script moved into HEAD with defer — passed a 9-context probe and should be evaluated by DEV as the next minimal fix. This probe did not modify repository files and is not a product PASS.

## Deterministic current-worktree gates — PASS

Fresh commands:
- uv run --no-project python -m unittest -q
- node --check static\markdown_preview.js
- git diff --check
- git diff --exit-code 387a5f1 -- static\terminal_scm.js static\vendor\xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
- certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256

Actual:
- Python: 39 tests PASS
- JS syntax: PASS
- diff hygiene: PASS
- all immutable terminal/backend/dependency files unchanged: PASS
- Mermaid SHA256: 581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8: PASS

## Current product first-load attribution — FAIL

Server: current worktree Lantern at 127.0.0.1:18769.
Harness: C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\parser-load-real.js
Method:
- use actual product preview HTML for all.md
- intercept only /static/markdown_preview.js and replace it with an empty response so initialize/render cannot contaminate vendor-script attribution
- keep the product-emitted parser-discovered Mermaid script unchanged
- repeat in nine fresh browser contexts
- collect Long Task API entries

Observed isolated first-load main-thread tasks:
1. 269 ms
2. 269 ms
3. 225 ms
4. 221 ms
5. 196 ms
6. 178 ms
7. 212 ms
8. 192 ms
9. 169 ms

Binding expectation: every isolated first-load parse/evaluation task <=250 ms.

Actual: 2/9 runs are 269 ms, therefore FAIL. This independently contradicts DEV's 9-run 174-236 ms sample and proves the current BODY parser-inserted path remains variable around the hard threshold.

## Viable narrow probe — HEAD + defer

Temporary harness only:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\head-defer-probe.js

The harness rewrites only the served HTML in Playwright:
- removes the current BODY Mermaid script
- inserts the exact same nonce-authorized /static/vendor/mermaid-11.17.2.min.js into HEAD with defer
- leaves the repository untouched
- disables helper execution so only first-load bundle work is measured

Nine fresh-context Long Tasks:
1. 231 ms
2. 209 ms
3. 196 ms
4. 182 ms
5. 214 ms
6. 206 ms
7. 203 ms
8. 231 ms
9. 217 ms

Range: 182-231 ms. 9/9 satisfy <=250 ms in this probe.

This is evidence of a plausible minimal DEV remediation, not acceptance evidence for the current product.

## Required next action

PLAN should preserve the existing contract and route DEV to evaluate the smallest product change:
- keep exact Mermaid 11.17.2 asset and SHA256
- keep nonce-only CSP
- keep Mermaid absent from non-Mermaid pages
- keep offline/no-CDN behavior and strict config
- emit the conditional Mermaid script in HEAD with defer rather than at the end of BODY
- ensure helper ordering remains correct: markdown_preview.js must not execute Mermaid work before the deferred vendor script is ready
- rerun deterministic tests and independent first-load attribution
- if product HEAD+defer still fails <=250 ms independently, return to PLAN rather than weakening the threshold inside DEV

No implementation files were edited by this TEST recovery.

## Route

PLAN

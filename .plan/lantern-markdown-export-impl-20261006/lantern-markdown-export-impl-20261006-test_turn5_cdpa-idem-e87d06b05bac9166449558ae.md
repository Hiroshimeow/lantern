# TEST turn 5 report

Role: TEST
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

FAIL the binding first-load Mermaid parse/evaluation performance gate on the current HEAD+defer product path. Route PLAN, per the prior PLAN contract that required returning to PLAN if the independently tested product HEAD+defer path still exceeded the <=250 ms threshold.

The structural remediation from DEV turn 4 is present and correct as implemented, but it does not satisfy the binding performance requirement in this independent run.

## Fresh deterministic gates

Executed from the current worktree:

- uv run --no-project python -m unittest -q
- node --check static\markdown_preview.js
- git diff --check
- git diff --exit-code 387a5f1 -- static\terminal_scm.js static\vendor\xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
- certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256

Results:
- Python suite: 39/39 PASS
- markdown_preview.js syntax: PASS
- diff hygiene: PASS
- immutable scope: PASS
- Mermaid SHA256: 581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8: PASS

## Fresh product structure

Current product server: http://127.0.0.1:18773

Read-only verification of actual served all.md preview:
- Mermaid vendor script has defer
- markdown_preview.js has defer
- vendor appears before helper
- vendor is inside HEAD

So this run measured the new DEV turn-4 product path, not the stale BODY/non-defer path.

## Binding first-load attribution — FAIL

Harness source:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\parser-load-real.js

Turn-5 copy:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\turn5-parser-load.js

Method:
- target current product server on 127.0.0.1:18773
- use actual served product HTML
- intercept only /static/markdown_preview.js and replace it with an empty JavaScript response, preventing initialize/render work from contaminating vendor attribution
- leave the actual product-emitted HEAD+defer Mermaid vendor script unchanged
- run nine fresh Playwright Chromium contexts
- capture Long Task API entries

Observed isolated first-load main-thread task maxima:
1. 282 ms
2. 278 ms
3. 258 ms
4. 279 ms
5. 255 ms
6. 305 ms
7. 346 ms
8. 265 ms
9. 247 ms

Binding threshold: every isolated first-load parse/evaluation task <=250 ms.

Actual:
- 8/9 runs exceed 250 ms
- range: 247-346 ms
- therefore FAIL

This supersedes the earlier temporary HEAD+defer probe as current product acceptance evidence. The earlier probe was explicitly non-product evidence and cannot justify PASS against this fresh product-path failure.

## Scope and preservation

No source files were edited by TEST turn 5.
No commit, push, or merge was performed.
The exact reviewed Mermaid asset, CSP, offline behavior, and immutable files remain unchanged.

## Required next action

Return to PLAN.

PLAN must resolve the contradiction between:
- the still-binding <=250 ms first-load parse/evaluation requirement, and
- the independently observed current-product HEAD+defer behavior above.

Per the prior PLAN instruction, DEV should not weaken the threshold unilaterally. PLAN should choose a legal implementation strategy that preserves the existing security/offline/bundle constraints or explicitly revise the acceptance contract through the proper planning path.

## Route

PLAN

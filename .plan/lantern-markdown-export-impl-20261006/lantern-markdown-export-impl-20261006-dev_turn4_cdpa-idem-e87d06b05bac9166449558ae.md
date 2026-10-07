# DEV turn 4 report

Role: DEV
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Baseline HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Incoming handoff

Reviewed:
.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-plan_turn5_cdpa-idem-e87d06b05bac9166449558ae.md

PLAN identified the current binding implementation defect: the conditional Mermaid 11.17.2 vendor script was still emitted at the end of BODY without defer, immediately before static/markdown_preview.js. TEST turn 3 had independently shown that exact product loading path exceeded the <=250 ms isolated first-load parse/evaluation budget in 2/9 fresh contexts, while a HEAD+defer probe using the same exact local bundle passed 9/9.

## Implementation

Implemented the narrow loading-path remediation in plugin.py.

Mermaid pages now emit, in HEAD and in deterministic parser order:

1. /static/vendor/mermaid-11.17.2.min.js with the existing response nonce and defer.
2. /static/markdown_preview.js with the same response nonce and defer.

Plain Markdown pages emit only /static/markdown_preview.js, also in HEAD with nonce and defer.

This preserves the existing helper fallback in static/markdown_preview.js. On the normal Mermaid product path the deferred helper is ordered after the deferred vendor script, so window.mermaid is expected to be present and loadMermaid() should not dynamically inject a duplicate vendor request.

No CDN, alternate Mermaid bundle, CSP relaxation, dependency change, terminal change, backend change, IME change, or UniKey change was made.

## Test updates

Updated test_plugin.py to lock the exact loading structure:

- structural allowlist permits the defer attribute on script elements;
- Mermaid page contains the vendor exactly once;
- vendor precedes helper;
- both script tags are inside HEAD;
- both Mermaid-page scripts carry nonce and defer;
- plain Markdown contains no Mermaid vendor script;
- plain Markdown helper remains nonce-authorized, deferred, and in HEAD.

## Deterministic verification

Fresh focused suite:
uv run --no-project python -m unittest -v test_plugin
Result: 15/15 PASS.

Fresh full suite:
uv run --no-project python -m unittest discover -v
Result: 39/39 PASS.

Fresh syntax/hygiene checks:
- node --check static\markdown_preview.js: PASS
- node --check static\terminal_scm.js: PASS
- git diff --check: PASS

Exact Mermaid bundle SHA-256:
581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8
Result: PASS / unchanged reviewed asset.

Immutable scope check:
git diff --exit-code 387a5f1 -- static\terminal_scm.js static\vendor\xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
Result: exit code 0 / PASS.

## Fresh runtime structural verification

Started a fresh current-worktree Lantern server on 127.0.0.1:18770 and loaded the actual product preview.

The fresh product HTML reported:
- Mermaid vendor script: defer=true, parent=document.head
- markdown_preview.js: defer=true, parent=document.head
- vendor ordered before helper
- Mermaid runtime loaded successfully

This confirms the product server was serving the new HEAD+defer source rather than the stale server still running on 18769.

## Performance verification status

The previously accepted independent probe from TEST turn 3 showed the exact same legal HEAD+defer shape with the exact same vendor asset at 182-231 ms across 9/9 fresh Playwright Chromium contexts.

I attempted to rerun the nine-context product-path attribution fresh in this turn.

Environment findings:
- the stale 18769 server was still serving the old BODY/non-defer product path, so it was not used for current acceptance;
- a fresh 18770 server was started from the current worktree;
- Python Playwright was not installed in the existing uv environment;
- a temporary uv --with playwright environment could launch system Google Chrome 154, but this is not the same accepted Playwright Chromium environment used for the prior binding probe;
- that Google Chrome diagnostic produced large aggregate long tasks and therefore is not claimed as acceptance evidence for the isolated Playwright Chromium contract;
- attempting default Playwright Chromium failed because the newly resolved Python Playwright package expected a browser binary that is not installed locally.

Accordingly, I do not claim a fresh DEV <=250 ms product-path PASS in the accepted Playwright Chromium environment from this turn. Independent TEST must rerun the binding nine-context isolated attribution using its established Playwright Chromium harness before acceptance.

The fresh structural product verification does confirm the source change requested by PLAN is active.

## Repository preservation

Existing dirty spec/report implementation state remains preserved. This turn modified only:
- plugin.py
- test_plugin.py
- this DEV report

No commit, push, or merge was performed.

## Decision

Route TEST.

Reason:
- the requested source remediation is implemented exactly;
- deterministic tests, syntax, SHA, diff hygiene, and immutable-scope checks all pass;
- fresh current-product structural verification confirms HEAD+defer ordering is active;
- independent TEST now needs to reproduce the binding <=250 ms first-load result and rerun browser functional acceptance on the changed product path.

DONE is not justified because independent acceptance is not yet complete.

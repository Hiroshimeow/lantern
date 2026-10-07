# DEV turn 3 report

## Scope and intake

Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

Incoming TEST handoff:
.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-test_turn2_cdpa-idem-e87d06b05bac9166449558ae.md

TEST turn 2 reproduced the corrected M-A11 failure on the dynamic first-load path:
- contract: isolated first-load Mermaid parse/evaluation <=250 ms; subsequent attributable initialize/render/export <=100 ms
- failing samples included 254 ms, 437 ms, 276 ms, and 302 ms
- deterministic suites and functional browser acceptance otherwise passed

This turn changed only the Markdown/Mermaid lane. No terminal persistence, IME, UniKey, backend, or dependency file was modified.

Pre-existing dirty authoritative spec files from PLAN were preserved:
- specs/001-terminal-ime-markdown-export/spec.md
- specs/001-terminal-ime-markdown-export/plan.md
- specs/001-terminal-ime-markdown-export/tasks.md

No commit, merge, or push was performed.

## Root cause and remediation

The exact reviewed Mermaid 11.17.2 standalone asset remains required and unchanged.

Prior product behavior:
- markdown_preview.js discovered Mermaid placeholders and dynamically appended the 3.57 MB Mermaid script.
- TEST showed this dynamic execution path had unstable first-load parse/evaluation and sometimes exceeded 250 ms.

Legal remediation implemented:
- plugin.py now emits the same exact local Mermaid script as a parser-discovered, nonce-authorized external script in the preview HTML, but only when rendered Markdown contains a Mermaid placeholder.
- The script remains absent on non-Mermaid pages.
- The helper remains nonce-authorized and follows the Mermaid script.
- static/markdown_preview.js retains its existing loadMermaid fallback: if window.mermaid is already present, no second load occurs; otherwise it can still load the exact local bundle.
- No CDN, no changed Mermaid version, no chunk substitution, no relaxed CSP, no weakened strict config, and no immutable-file changes.

Why this is within contract:
- exact reviewed bundle and SHA256 preserved
- Mermaid still does not load on pages without Mermaid fences
- CSP remains nonce-only for scripts
- same-origin/offline only
- strict config, page cap, sequential rendering, yields, PNG and print contracts unchanged

## Test changes

Updated test_plugin.py:
- structural script allowlist now permits exactly the local helper and reviewed Mermaid vendor script on Mermaid pages.
- added test_mermaid_bundle_is_parser_discovered_only_on_mermaid_pages:
  - Mermaid page contains vendor script then helper script
  - plain Markdown page contains no vendor script
  - both scripts carry non-empty nonce attributes

## Deterministic verification

Fresh focused suite:
uv run --no-project python -m unittest -v test_plugin
Result: 15/15 PASS.

Fresh full suite:
uv run --no-project python -m unittest discover -v
Result: 39/39 PASS.

Fresh JS/diff checks:
- node --check static/markdown_preview.js: PASS
- node --check static/terminal_scm.js: PASS
- git diff --check: PASS

Exact Mermaid bundle:
static/vendor/mermaid-11.17.2.min.js
SHA256:
581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8
Result: PASS / unchanged exact reviewed bundle.

Immutable scope check:
git diff --exit-code 387a5f1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
Result: exit code 0 / PASS.

## Fresh parser-discovered first-load attribution

Fresh current-worktree Lantern server on 127.0.0.1:18769.
Browser: locally installed Playwright Chromium.

Measurement method:
- use actual product preview HTML for all.md
- product emits parser-discovered Mermaid vendor script
- Playwright intercepts only /static/markdown_preview.js and returns an empty JS response so no initialization/render work can contaminate the first-load vendor measurement
- Long Task API captures main-thread tasks
- repeat in nine fresh browser contexts

Nine isolated first-load Long Tasks:
1. 203 ms
2. 236 ms
3. 211 ms
4. 185 ms
5. 176 ms
6. 208 ms
7. 174 ms
8. 216 ms
9. 200 ms

Range: 174-236 ms.
All nine samples satisfy corrected <=250 ms first-load contract.

This directly addresses the TEST turn-2 failure mode. It does not rely on aggregate page elapsed time.

## Fresh functional browser acceptance on changed product path

Current product page all.md:
- Mermaid wrappers: 9
- valid SVG renders: 7
- malformed isolated: 1
- oversize isolated: 1
- exact nonce CSP present
- non-Lantern requests: 0
- blocked non-Lantern attempted requests: 0
- nonce-less same-origin /owned.js execution: blocked; ownedRan=false
- PNG diagram 1: all-diagram-1.png, 4538 bytes
- PDF: 75351 bytes
- plain Markdown: mermaidLoaded=false and zero Mermaid vendor requests
- cap page: 24 Mermaid wrappers
- aggregate max Long Task in this run: 250 ms; per contract aggregate Long Tasks are informational unless attributed

## Fresh subsequent governed render evidence

After current product page completed its normal render chain, DEV invoked the same runtime for all seven required diagram families and measured each operation separately.

Elapsed:
- flowchart: 18.4 ms
- sequence: 11.7 ms
- class: 18.5 ms
- state: 23.2 ms
- ER: 15.2 ms
- Gantt: 7.6 ms
- pie: 5.8 ms

Long Task entries for all seven measured render operations: none.

All measured subsequent render operations are well below <=100 ms.

## Fresh seven-PNG export evidence

All seven valid rendered diagrams were exported through the product PNG action.

Downloads:
1. all-diagram-1.png — 4538 bytes
2. all-diagram-2.png — 20439 bytes
3. all-diagram-3.png — 6962 bytes
4. all-diagram-4.png — 11327 bytes
5. all-diagram-5.png — 16244 bytes
6. all-diagram-6.png — 22207 bytes
7. all-diagram-7.png — 90270 bytes

All seven filenames follow <doc>-diagram-N.png and all blobs are non-empty.
No non-Lantern requests were attempted during the probe.

## Remaining evidence classification

Still requires independent TEST/REVIEW ownership:
- independent reproduction of the parser-discovered <=250 ms first-load result
- print-waits-for-pending-render evidence after this loading-path change
- independent export timing <=100 ms
- parent UI responsiveness/manual observation
- PDF selectable-text/arrowhead/readability/clipping proof where tooling permits
- M-A12 governance: security-owner residual-risk sign-off and follow-up ticket

These are not claimed PASS by DEV beyond the direct measurements above.

## Repository state / preservation

Current status includes pre-existing PLAN/test report/spec dirt plus implementation:
- M plugin.py
- M specs/001-terminal-ime-markdown-export/plan.md
- M specs/001-terminal-ime-markdown-export/spec.md
- M specs/001-terminal-ime-markdown-export/tasks.md
- ?? .plan/lantern-markdown-export-impl-20261006/
- ?? .plan/lantern-markdown-test-review-20261007/
- ?? static/markdown_preview.js
- ?? static/vendor/mermaid-11.17.2.LICENSES.txt
- ?? static/vendor/mermaid-11.17.2.min.js
- ?? test_plugin.py

The spec/report dirt was not authored or rewritten by DEV turn 3 and was preserved.

## Route decision

Route TEST.

Reason:
- TEST provided an implementation/performance blocker.
- DEV implemented a narrow legal loading-path remediation.
- fresh DEV evidence now satisfies the corrected <=250 ms first-load requirement across nine isolated samples
- deterministic and functional gates are green
- independent TEST must now verify the changed product path before any commit is allowed

No commit/push/merge should occur until independent TEST passes and lifecycle proceeds to REVIEW.

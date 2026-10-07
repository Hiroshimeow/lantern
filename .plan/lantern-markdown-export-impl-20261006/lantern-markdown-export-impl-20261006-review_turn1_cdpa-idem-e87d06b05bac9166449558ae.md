# REVIEW turn 1 report

Role: REVIEW
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Planning baseline / HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

Route **TEST**.

I found no actionable implementation defect that requires DEV. Deterministic source, security-contract, test, syntax, vendor-integrity, and immutable-scope checks are green under the current PLAN-synchronized contract.

However, acceptance is not fully supported yet. The prior TEST handoff explicitly classifies manual parent-UI responsiveness and PDF visual/selectability fidelity as INCOMPLETE / NOT_MEASURED, and M-A12 governance evidence is absent. Per the REVIEW routing contract, implementation-complete work with missing independent runtime/acceptance proof routes to TEST rather than being promoted as complete.

No implementation files were edited by REVIEW.

## Repository / revision verification

Verified directly:
- worktree: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
- branch: feature/lantern-markdown-export-20261006
- HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1
- implementation remains uncommitted, as required before REVIEW pass
- changed product/test assets are confined to plugin.py, test_plugin.py, static/markdown_preview.js, static/vendor/mermaid-11.17.2.min.js, and static/vendor/mermaid-11.17.2.LICENSES.txt, plus PLAN/spec/report files

The authoritative M-A11 wording changes in spec.md / plan.md / tasks.md are traceable to PLAN turn 8 and the recorded operator decision; they are not treated as an unexplained DEV relaxation.

## Independent source/security review

Reviewed plugin.py, test_plugin.py, and static/markdown_preview.js against the Markdown/Mermaid/export contract.

Verified:
- raw Markdown HTML is escaped and literal NUL is removed before parsing
- URL normalization removes parser whitespace, trims C0 edge controls/spaces, html-unescapes once, normalizes backslashes, URL-unquotes path once, rejects encoded traversal/separator residue, rejects protocol-relative targets, confines local paths to configured root, and percent-encodes local segments
- links allow local/root/fragment/http/https/mailto; author images allow local/root only
- rejected targets degrade to escaped label/alt text rather than href="#"
- no <base> emission
- generated inline HTML is stashed before emphasis and restored recursively/reverse-order
- fenced blocks require matching fence character, sufficient closing length, and no closing info; first info token detects Mermaid case-insensitively; unclosed Mermaid fences render as escaped code
- Mermaid placeholders are capped at 24
- shared preview CSP exactly matches the required nonce-only contract
- every app-owned script carries the response nonce
- Back is a normal button handled by the local helper, not javascript:
- Mermaid vendor is emitted only on Mermaid pages, once, before the helper, both deferred in HEAD
- markdown_preview.js clears window.opener before Mermaid work
- Mermaid initialization matches strict/offline settings, bounded maxTextSize/maxEdges, light theme, htmlLabels:false, conservative DOMPurify config, and the required secure list
- rendering is sequential with yields after bundle load, after initialize, after render generation before DOM insertion, and between diagrams
- PNG export derives dimensions from SVG/viewBox, writes explicit dimensions, uses white canvas, targets 2x within <=8192 px/side and ~32 MP, requires toBlob success, names <doc>-diagram-N.png, and revokes object URLs
- print waits for pending renders and print CSS removes toolbar/UI and avoids table/code clipping

No duplicate owner/mechanism or terminal/IME implementation was introduced.

## Independent deterministic verification

Fresh commands/results:
- uv run --no-project python -m unittest -q
  - Ran 39 tests in 10.141s
  - OK
- node --check static\markdown_preview.js
  - PASS
- node --check static\terminal_scm.js
  - PASS
- git diff --check
  - PASS
- git diff --exit-code 387a5f1 -- static\terminal_scm.js static\vendor\xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
  - exit 0; all HARD IMMUTABLE files byte-identical to baseline
- certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256
  - 581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8
  - exact reviewed pin

test_plugin.py contains the required T3 coverage families: raw HTML/NUL safety; adversarial URL normalization; local/root/fragment/http/https/mailto allowlist; image restrictions; no <base>; nested stash restoration; fence rules; Mermaid placeholder detection; stdlib html.parser structural allowlist; exact nonce CSP; and normal Back behavior.

## Findings

### FINDING 1 — Acceptance evidence incomplete: manual parent responsiveness
Boundary: T7 / M-A11 responsiveness acceptance.
Evidence: TEST turn 6 states, “Manual parent-UI responsiveness observation was not independently performed in this turn: INCOMPLETE / NOT_MEASURED.”
Contract: missing/manual/runtime evidence is INCOMPLETE, never PASS.
Required correction: TEST must obtain independent accepted evidence for parent-UI responsiveness under the worst-case Mermaid fixture, or retain the item as INCOMPLETE. REVIEW cannot promote this lane to PLAN while this acceptance item is unproven.
Route owner: TEST.

### FINDING 2 — Acceptance evidence incomplete: PDF/selectability/visual fidelity
Boundary: T7 / M-A9 Print / Save as PDF.
Evidence: TEST turn 6 states that PDF selectable text, Mermaid arrowhead visual fidelity, and clipping/readability inspection were not manually/visually re-proven and are INCOMPLETE / NOT_MEASURED. A non-empty generated PDF alone does not prove the full contract.
Contract: Chromium PDF acceptance requires selectable text, visible arrowheads, readable diagrams/vector SVG where preserved, no UI chrome, and no material clipping.
Required correction: TEST must inspect and record those properties against a current generated PDF, or keep M-A9 partially INCOMPLETE.
Route owner: TEST.

### FINDING 3 — M-A12 governance gate absent
Boundary: release governance, not product implementation.
Evidence: TEST turn 6 records no security-owner residual-risk sign-off and no follow-up ticket for iframe sandboxing plus same-origin uploaded HTML/SVG serving. REVIEW also found no matching artifact in the available .plan tree.
Contract: M-A12 requires both artifacts before release.
Required correction: obtain and preserve security-owner sign-off and the follow-up ticket reference. This is not a DEV code defect. Until present, M-A12 remains INCOMPLETE.
Route owner: TEST for evidence collection / lifecycle handoff; PLAN/governance may need to supply the underlying sign-off/ticket.

## Non-findings / preserved boundaries

- No changes to static/terminal_scm.js.
- No changes to static/vendor/xterm.js.
- No changes to lantern_terminal.py.
- No changes to lantern_ws.py.
- No changes to lan_drive.py.
- No changes to requirements.txt.
- No terminal persistence work.
- No IME/UniKey behavior implemented.
- No CDN or new Python dependency.
- Mermaid bundle hash matches the reviewed 11.17.2 artifact.
- No source-level defect found that warrants DEV rework.

## Route rationale

The implementation is source-complete enough to avoid a DEV route, but the lane is not fully accepted because required runtime/manual and governance evidence remains incomplete. Under the supplied RouteContract, that state routes to TEST.


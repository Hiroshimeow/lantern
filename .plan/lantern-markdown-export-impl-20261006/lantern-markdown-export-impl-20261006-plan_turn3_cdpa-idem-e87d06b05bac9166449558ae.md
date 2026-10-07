# PLAN turn 3 report

## Decision

Route **TEST**.

The previously blocking Mermaid performance contract has now been explicitly revised by operator decision and encoded in the authoritative Spec-Kit documents. No further DEV implementation change is justified before independent TEST.

## Contract correction applied this turn

Updated only the Markdown/Mermaid performance contract in:

- `specs/001-terminal-ime-markdown-export/spec.md`
- `specs/001-terminal-ime-markdown-export/plan.md`
- `specs/001-terminal-ime-markdown-export/tasks.md`

The binding contract is now:

1. Non-Mermaid pages make zero Mermaid-bundle requests.
2. Mermaid 11.17.2 remains the exact reviewed local bundle.
3. Bundle loading remains lazy and at most once per Mermaid preview page.
4. In the accepted Chromium harness, the isolated first-load bundle parse/evaluation phase must be **<=250 ms** once per Mermaid preview page.
5. Every subsequent attributable Mermaid initialize, diagram-render, and PNG/export main-thread task must be **<=100 ms**.
6. Aggregate full-page Long Task entries are not failures by themselves; they become blockers only when evidence attributes an over-budget task to the governed Mermaid bundle/initialize/render/export operation.
7. Existing bounds remain unchanged:
   - `maxTextSize:60000`
   - `maxEdges:500`
   - 24 diagrams/page
   - sequential rendering only
   - yields after bundle load, after initialize, after render generation before DOM insertion, and between diagrams.
8. Any attributed first-load >250 ms, subsequent governed task >100 ms, or loss of the lazy/bounded/sequential/yield invariants keeps acceptance INCOMPLETE and triggers re-review.

This deliberately replaces both:
- the original impossible “all Mermaid work <=100 ms” contract; and
- the later overly broad “timing is telemetry only” wording.

## Current repository truth

Workspace:
`C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`

Branch:
`feature/lantern-markdown-export-20261006`

HEAD:
`387a5f17a30ab60f50ae290c8651511608f153d1`

Current worktree still contains the existing uncommitted Markdown/Mermaid implementation plus docs/reports. This PLAN turn did not modify product/runtime/test code.

The immutable terminal/backend/dependency boundary remains unchanged:
- `static/terminal_scm.js`
- `static/vendor/xterm.js`
- `lantern_terminal.py`
- `lantern_ws.py`
- `lan_drive.py`
- `requirements.txt`

## Verified document consistency

Fresh grep confirms the same numeric contract appears in all three authoritative documents:

- spec performance section: <=250 ms first-load, <=100 ms subsequent governed tasks;
- M-A11 acceptance row: same thresholds and attribution rule;
- implementation plan: same thresholds and attribution rule;
- task T6/T7 execution contract: same thresholds and attribution rule.

No stale “hard SLA removed” / “regression telemetry only” wording remains in these three performance sections.

`git diff --check`: PASS.

## Existing implementation/evidence state to preserve

Do not rediscover or rewrite implementation unless TEST finds a new deterministic failure.

Relevant current implementation behavior already inspected in prior turns:
- exact local Mermaid 11.17.2 bundle;
- lazy load only with Mermaid placeholders;
- nonce propagation;
- strict Mermaid security configuration;
- page cap 24;
- sequential rendering;
- explicit yields after bundle load/initialize and around diagram insertion;
- malformed/oversize isolation;
- PNG viewBox sizing, white canvas, 2x target, 8192 px/side and ~32 MP bounds, `toBlob`;
- Print / Save as PDF waits for pending renders;
- no terminal/IME product-code change.

Current retained independent evidence from the companion test/review lifecycle reports Chrome 154 measurements satisfying the newly authorized contract:
- isolated first-load bundle long tasks observed around 189-220 ms, all <=250 ms;
- initialize around 3-4 ms;
- required diagram renders worst observed <100 ms;
- focused PNG export <100 ms;
- plain Markdown zero Mermaid-bundle requests.

Those retained results are useful context, but TEST must decide freshness and rerun where needed. Missing/stale evidence is INCOMPLETE, never PASS.

## TEST execution contract

TEST should independently verify the current workspace against the corrected authoritative contract.

Required checks:

1. Fresh focused plugin suite.
2. Fresh full Python suite.
3. `node --check static/markdown_preview.js`.
4. `node --check static/terminal_scm.js` as unchanged regression evidence.
5. `git diff --check`.
6. Exact Mermaid SHA-256:
   `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`.
7. Immutable-file diff against `387a5f1`.
8. Verify spec/plan/tasks all encode the same <=250 ms / <=100 ms attributed timing contract.
9. Browser acceptance with Lantern origin reachable and non-Lantern origins blocked:
   - plain Markdown makes zero Mermaid vendor requests;
   - seven required diagram types render;
   - malformed, oversized, and page-cap+1 cases isolate;
   - exact nonce CSP behavior remains correct;
   - same-origin non-nonce script cannot execute;
   - zero non-Lantern runtime requests;
   - isolated first-load bundle parse/evaluation <=250 ms;
   - subsequent attributable initialize/render/PNG-export tasks <=100 ms;
   - aggregate Long Tasks are not classified as failures without attribution;
   - PNG output is non-empty with correct filename;
   - Print / Save as PDF waits for pending renders.
10. Reconfirm manual/runtime evidence truthfully:
   - PNG visual legibility;
   - PDF selectable text / arrowheads / readability / clipping;
   - parent UI/terminal responsiveness where measurable;
   - any unavailable proof remains INCOMPLETE.

## Governance state

M-A12 remains a separate release-governance gate:
- residual-risk security-owner sign-off;
- follow-up ticket covering iframe sandboxing plus same-origin uploaded HTML/SVG serving.

Do not reinterpret those as code PASS if they remain unavailable. Likewise, do not route back to DEV unless TEST finds an actionable implementation defect.

## Route rationale

The contract conflict that forced PAUSE is resolved by explicit operator decision and is now written into the authoritative documents. Existing implementation evidence is compatible with that contract, and no known implementation defect currently requires DEV.

The correct next role is **TEST** for independent acceptance on the corrected contract.

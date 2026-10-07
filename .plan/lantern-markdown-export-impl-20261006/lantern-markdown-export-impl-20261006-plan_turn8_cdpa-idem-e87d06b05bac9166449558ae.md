# PLAN turn 8 report

Role: PLAN
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

Route **TEST**.

A new explicit operator/spec-owner decision appeared after the turn-7 PAUSE handoff:

`.plan/lantern-markdown-export-impl-20261006/operator-ma11-decision-20261007.md`

That decision resolves the paused M-A11 contract conflict by replacing the obsolete absolute <=250 ms first-load cutoff with a reproducible statistical guardrail, while preserving the existing Mermaid asset, security, offline, functional, and subsequent-operation requirements.

## Authoritative contract synchronization completed

Per operator instruction, PLAN updated only the M-A11 first-load acceptance wording in:

- `specs/001-terminal-ime-markdown-export/spec.md`
- `specs/001-terminal-ime-markdown-export/plan.md`
- `specs/001-terminal-ime-markdown-export/tasks.md`

The synchronized first-load contract is now:

- accepted environment: FJP Playwright Chromium harness;
- actual served product preview HTML;
- nine fresh browser contexts;
- isolate the attributable Mermaid vendor parse/evaluation main-thread task by preventing helper initialize/render work from contaminating the measurement;
- PASS requires:
  - median of the nine isolated first-load samples <=300 ms; and
  - no individual first-load sample >500 ms.

Preserved unchanged:

- exact reviewed local Mermaid 11.17.2 asset/hash;
- no Mermaid request on non-Mermaid pages;
- local/offline runtime; no CDN;
- nonce-only CSP and existing security/sanitization contract;
- every subsequent attributable Mermaid initialize/render/PNG-export main-thread task <=100 ms;
- bounded/sequential rendering and yields;
- all functional/security/export acceptance gates;
- terminal/IME/UniKey lane remains deferred and must not change.

Fresh consistency check found no remaining `250 ms` / `<=250` wording in the three authoritative documents.

`git diff --check`: PASS.

No product/runtime/test code was changed by PLAN turn 8.

## Why TEST is next

The operator decision explicitly states this is an acceptance-contract-only change and the current HEAD+`defer` product source should be tested directly against the revised contract unless a document synchronization issue requires otherwise.

Document synchronization is complete and clean. No additional DEV source change is justified before independent acceptance.

The prior TEST turn-5 first-load sample set:
282, 278, 258, 279, 255, 305, 346, 265, 247 ms
would have median 278 ms and maximum 346 ms, which is compatible with the revised statistical guardrail. However, the operator specifically requires TEST to rerun the accepted nine-context method, so prior evidence is context only and not substituted for fresh acceptance.

## TEST execution contract

TEST must independently rerun the current product path using the exact accepted method:

1. Confirm branch and HEAD.
2. Fresh focused/full Python tests.
3. Fresh JS syntax checks and `git diff --check`.
4. Confirm exact Mermaid SHA-256 and immutable terminal/backend/dependency scope.
5. Confirm the current served product structure remains HEAD+`defer`, vendor before helper, and no duplicate/dynamic Mermaid fetch on the normal Mermaid path.
6. First-load M-A11:
   - FJP Playwright Chromium;
   - actual served product preview HTML;
   - nine fresh browser contexts;
   - prevent helper initialize/render work from contaminating first-load attribution;
   - record all nine isolated attributable vendor parse/evaluation samples;
   - compute median;
   - PASS only if median <=300 ms and no individual sample >500 ms.
7. Subsequent governed work:
   - attributable Mermaid initialize/render/PNG-export main-thread tasks <=100 ms.
8. Re-run relevant functional/security/export acceptance:
   - plain Markdown: zero Mermaid vendor requests;
   - seven required Mermaid types render;
   - malformed/oversized/page-cap+1 isolation;
   - exact nonce CSP;
   - nonce-less same-origin script blocked;
   - zero non-Lantern runtime requests;
   - PNG export non-empty and correct filenames;
   - Print / Save as PDF waits for pending renders.
9. Record parent responsiveness and PDF/manual evidence truthfully; unavailable evidence remains INCOMPLETE.
10. Preserve M-A12 governance status accurately; do not infer owner sign-off or follow-up ticket if absent.

If independent technical acceptance is green, route according to lifecycle toward REVIEW/governance. If a new deterministic implementation defect is found, route DEV with exact evidence. Do not commit, push, or merge from TEST.

## Route

TEST

# Operator decision — Mermaid M-A11 first-load acceptance

Date: 2026-10-07
Scope: lantern-markdown-export-impl-20261006
Authority: explicit operator/spec-owner decision to continue the Markdown/Mermaid/export lane after PLAN turn 6/7 PAUSE.

## Decision

Replace the brittle single-sample hard maximum for Mermaid first-load parse/evaluation with a reproducible statistical guardrail.

Accepted environment and method:
- FJP accepted Playwright Chromium harness.
- Actual served product preview HTML.
- Nine fresh browser contexts.
- Isolate Mermaid vendor parse/evaluation by preventing helper initialize/render work from contaminating the measurement.
- Measure the attributable first-load Mermaid bundle main-thread task for each context.

PASS criteria:
- median of the nine isolated first-load samples <= 300 ms; AND
- no individual first-load sample > 500 ms.

Rationale:
- Current independently reproduced product evidence is 247-346 ms and shows substantial runtime/browser scheduling variance around the prior 250 ms absolute cutoff.
- The bundle is the already-reviewed immutable local Mermaid 11.17.2 artifact; HEAD+defer fixed the actionable loading-order defect, while repeated independent tests showed the remaining variance is bundle/browser parse-evaluation cost rather than a product logic bug.
- A median guardrail plus a high-water ceiling remains regression-sensitive without treating scheduler jitter as deterministic correctness failure.

Preserve unchanged:
- exact reviewed local Mermaid 11.17.2 asset/hash;
- no Mermaid request on non-Mermaid pages;
- local/offline runtime; no CDN;
- nonce-only CSP and existing security/sanitization contract;
- every subsequent attributable Mermaid initialize/render/PNG-export main-thread task <= 100 ms;
- bounded/sequential rendering and yields;
- all functional/security/export acceptance gates;
- terminal/IME/UniKey lane remains deferred and must not change in this Markdown release.

## Required lifecycle action

PLAN must update the authoritative spec.md, plan.md, and tasks.md consistently to this exact method/threshold, removing the obsolete <=250 ms absolute-sample requirement.

Because this is an acceptance-contract-only change and the current HEAD+defer product source already exists, route TEST next without additional DEV source changes unless document synchronization requires otherwise.

TEST must rerun the nine-context accepted method and the relevant functional/security regression gates. REVIEW remains gated on independent technical acceptance.

No commit/push/merge is authorized until TEST and REVIEW are green.

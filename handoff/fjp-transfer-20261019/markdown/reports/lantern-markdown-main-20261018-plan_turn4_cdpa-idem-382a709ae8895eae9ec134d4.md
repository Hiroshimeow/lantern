# PLAN Turn 4 — Foundation 002 technical progression accepted; close remaining 001 runtime/export evidence next

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 4 / 2026-10-18 JST  
**Workspace:** owned G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn6_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE TEST**. Accept REVIEW Turn 6's Foundation-002 technical FJP/Windows progression disposition. Before starting 003 production implementation, independently close the remaining executable Spec-001 Markdown/Mermaid PNG/PDF/performance acceptance evidence (M-A8/M-A9/M-A11 and any directly coupled M-A6/7/10 checks). M-A12 personal owner/security acknowledgement remains explicitly pending and cannot be synthesized by TEST/PLAN.

## 1. Repository truth re-verified

- G6 `main` HEAD: **`ffe3decb4469cff36bb98f8afd6ba8e9e89af089`**.
- `origin/main`: **`b2ffd886795840f0db570b8c07a913b406e68e80`**; local main is **2 commits ahead / 0 behind**:
  - `3bfaa2e test(markdown): define typed preview CSP profiles`
  - `ffe3dec test(markdown): harden preview CSP evidence`
- The two local-only commits change only Spec-001 docs/tests (`spec.md/plan.md/tasks.md`, `tests/test_plugin.py`, `tests/test_preview_csp_e2e.py`), not runtime product code. For runtime-only 001/002 measurements, `b2ffd88` is product-runtime equivalent to current HEAD; final integration/push is still a later acceptance/integration gate.
- Tracked/staged tree is clean; `git diff --check` exit 0; only preserved unrelated `?? .pi/subagents.json`.
- Existing `.wt/lantern-bot` has independently advanced to `c1ee6cc0...`; it is outside this team's ownership and must remain untouched.
- No PLAN product source changes, service restart, CDPA modification, reset/stash/clean, or Pi/native-terminal edits.

## 2. Foundation 002 disposition after REVIEW Turn 6

**Accepted for technical dependency progression, not full release DONE.**

Fresh independent REVIEW Turn 6 on FJP reproduced, from a clean detached runtime-equivalent `b2ffd88` worktree while preserving dirty FJP main:

- real FJP Edge terminal lifecycle: **1 passed / exit 0**;
- remaining selected F-T011 Edge/WS/Markdown/Crop/launcher slice: **22 passed / exit 0**;
- combined selected FJP browser slice: **23/23 passed**;
- 1,000-item listing: p95 ratio **1.1093**, CPU ratio **1.0156**, RSS ratio **0.8253**;
- exact 102,400-byte Markdown Preview: p95 ratio **0.9744**, CPU ratio **1.0293**, RSS ratio **0.8026**;
- exact 204,800-byte replay: p95 ratio **0.6000**, CPU ratio **0.6849**, RSS ratio **1.0028**, retained/frame byte parity preserved.

REVIEW independently judged no new 002-owned architecture/performance/module-ownership defect and no reason for another refactor. Therefore **F-T011/F-T012 measured FJP Windows scope is sufficient to unblock dependency progression**, and F-T013's technical architecture review is satisfied for that scope.

Still **INCOMPLETE but not a reason to repeat Foundation verification or route DEV**:
- Linux smoke execution itself; concrete WSL environment blockers are documented and Spec 002 permits an evidenced blocker before merge.
- Manual/live owner acceptance.
- Explicit owner approval of the proposed <=20% p95 / <=25% RSS budget.
- Live deployment/restart.
These remain final acceptance/sign-off gates; they are not implementation defects. Do not call them PASS or impersonate owner approval.

## 3. Spec 001 status after accepted CSP slice

### Preserve / accepted evidence

- M-A1–M-A4 parser/security unit characterization has existing green focused/full-native evidence.
- Typed CSP contract and hardened browser oracle at local HEAD are independently REVIEW-accepted; do not reopen a generic CSP rewrite.
- TEST Turn 1 already measured in isolated G6 Edge:
  - non-Mermaid page: 0 Mermaid-bundle requests;
  - all seven Mermaid diagram types: **7/7 SVG render**;
  - one local Mermaid bundle request, 0 external requests in that fixture;
  - malformed/oversized failure isolation and **24-diagram cap**;
  - **7/7 PNG downloads**, correct numbered filenames, decodable/non-empty/nonwhite;
  - browser-generated **8-page PDF**, selectable text sentinel/section title.
- Current `.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/` evidence remains present.

### Still executable / materially incomplete

- **M-A8:** existing automated proof establishes nonempty/nonwhite PNGs + filenames, but **manual/visual legibility of every exported diagram** has not been independently accepted.
- **M-A9:** PDF text generation is partial evidence only. Must inspect the actual printed output for **visible arrowheads, readable diagrams/text, no clipping, no editor UI chrome**, and page/layout usability. A MIME response or PDF byte count is insufficient.
- **M-A11:** **NOT_MEASURED as specified.** Contract requires actual served product HTML on **FJP Playwright Chromium**, **nine fresh browser contexts**, isolated Mermaid bundle parse/evaluation attribution, median <=300 ms, each <=500 ms, and every attributable subsequent initialize/render/PNG-export main-thread task <=100 ms. Non-Mermaid zero bundle load and single lazy bundle load must remain true.
- **M-A10:** no runtime CDN was observed in TEST Turn 1, but preserve the local-only/no-new-Python-runtime-dependency invariant while testing.
- **M-A12:** **INCOMPLETE** until the user/security owner personally confirms the revised interactive Markdown `connect-src 'self'; worker-src 'self'` residual risk. Existing broad `LANTERN-SEC-001` acknowledgement is not a substitute for this newly explicit acceptance. Keep the ticket open.

## 4. Next TEST slice — remaining Spec-001 runtime/export/performance acceptance only

This is verification, not implementation. Reuse existing runtime and evidence wherever valid; do not create a second product renderer or test framework.

### TEST-A — visual PNG/PDF acceptance (M-A8/M-A9)

1. Use disposable Lantern root/ephemeral loopback port only. Do not touch live :9999/:10099.
2. Reuse or regenerate the seven-type Mermaid fixture against runtime-equivalent current product. Record browser version, exact SHA, request/console ledger and output paths.
3. For all seven PNG exports:
   - prove correct filename and decode;
   - **visually inspect** that node labels, connectors, arrowheads, state/class/ER relations, Gantt bars/labels and pie labels remain legible and not materially cropped;
   - retain screenshots/output files as evidence.
4. For Print / Save as PDF:
   - generate from actual served Preview after Mermaid render completion;
   - verify selectable text;
   - visually inspect **all pages**, not only page 1, for arrowheads, diagram readability, clipping/overflow, table/code wrapping where relevant, and absence of Lantern controls/UI chrome;
   - distinguish Chromium print rendering from native PDF viewer tests (`tests/test_pdf_browser_e2e.py` does not close M-A9).
5. If a concrete rendering/export defect reproduces, capture the smallest failing fixture and route **DEV** for at most two coherent product/test fixes. Do not weaken visual acceptance to make current output pass.

### TEST-B — FJP M-A11 timing/network acceptance

1. Use FJP only for the binding M-A11 measurement, preserving dirty FJP main. Prefer a clean detached `b2ffd88` worktree because it is runtime-equivalent to current HEAD; do not reset/stash/clean FJP main. The local G6 CSP docs/tests need not be pushed merely to time unchanged runtime.
2. Use the **Playwright Chromium-family harness required by Spec 001** and actual served product Preview HTML. Record exact executable/browser build. First inspect what Chromium-family runtime is already available. **Do not globally install browser/dependencies or mutate the dirty checkout solely to satisfy the gate.**
3. Run **nine fresh browser contexts**. Prevent helper initialize/render work from contaminating first-load attribution. Measure the attributable Mermaid standalone-bundle parse/evaluation task in each context:
   - median <= **300 ms**;
   - no individual sample > **500 ms**.
4. Measure attributable subsequent Mermaid operations under the same contract:
   - initialize <= **100 ms**;
   - diagram render <= **100 ms** per governed operation;
   - PNG/export <= **100 ms** per governed operation.
   An aggregate page Long Task is not failure unless attribution identifies a governed Mermaid operation.
5. Verify simultaneously:
   - plain Markdown causes **0** Mermaid bundle requests;
   - Mermaid page loads the local bundle lazily **at most once**;
   - no non-Lantern-origin runtime request escapes;
   - no unexpected CSP/page errors;
   - sequential/bounded/yield behavior remains intact.
6. If the exact required Chromium runtime is unavailable without unauthorized installation, record the precise executable/tooling blocker as **INCOMPLETE**, optionally gather clearly labelled non-binding Chromium-engine/Edge supplemental measurements, and return PLAN/REVIEW. Do not silently redefine FJP Edge as contractual Chromium acceptance without review.

Artifacts: raw JSON/timings, request/console logs, seven PNGs, PDF, all-page PDF render/screenshot set, browser/build and exact commands under this team's ignored `.plan/lantern-markdown-main-20261018/`.

## 5. Route after this TEST

- **Product defect reproduced:** route **DEV** for the smallest failing 001 fix, maximum two coherent subtasks, then independent REVIEW/TEST.
- **M-A8/M-A9/M-A11 pass:** route **PLAN** (or REVIEW only if material methodology/security ambiguity appears). PLAN will record 001 technical runtime acceptance while leaving M-A12 owner sign-off pending, then advance automatically to 003 Phase-0 proof work.
- **Only browser/tooling capability blocker:** route **PLAN** with exact blocker; do not PAUSE the whole team because 003 Phase 0 remains legally actionable.
- Do not route DONE: M-A12 and 002 owner/manual gates remain incomplete, and 003 MD-T000–T018 has not been completed.

## 6. Next dependency after 001 TEST: 003 Phase 0, not speculative UI code

Once the executable 001 acceptance slice above is dispositioned, next DEV work is still the planned pair:

1. **MD-T000** — repeatable Source performance characterization: 900/5,500 lines, 500KB/5MB, CJK/IME, 30-column fixture; input-to-paint, long tasks, DOM node/mutation counts, navigations, real `.md` writes and `md_temp` hashes. Preserve the existing proven classification: current 5,500-line full-backdrop rebuild is a pre-002 defect, not a Foundation regression.
2. **MD-T001** — byte-fidelity corpus: BOM, CRLF/mixed EOL/no-final-newline, frontmatter/comments, lists/tables/fences, 30-column text, duplicates, CJK; no-op and one-block edit; unchanged spans byte-identical.

No production Source editor rewrite in that first pair. After REVIEW/TEST, proceed MD-T002 source-range mapping + MD-T003 mature CodeMirror merge/unified POC before choosing the virtualized Source implementation. Preserve real `.md` source truth, `md_temp` accepted snapshot, CAS, exact mapping, no guessed locations, no serializer-wide rewrite, no long-debounce masking, and no Pi/native-terminal scope crossing.

**Turn 4 route = TEST.** Foundation 002 technical FJP progression is accepted; the smallest material remaining role is independent 001 PNG/PDF/performance acceptance.

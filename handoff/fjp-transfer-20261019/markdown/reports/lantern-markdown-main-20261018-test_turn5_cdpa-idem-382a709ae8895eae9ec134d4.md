# TEST Turn 5 — Spec 001 PNG/PDF/Mermaid performance acceptance

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4
Role: TEST turn 5
Date: 2026-10-18 JST
Workspace: G6 E:\git-project\lantern
Incoming PLAN: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-plan_turn4_cdpa-idem-382a709ae8895eae9ec134d4.md

## 1. Scope and preservation

PLAN Turn 4 assigned only the remaining executable Spec-001 Markdown runtime/export/performance acceptance:
- M-A8 visual PNG inspection;
- M-A9 Chromium Print / Save as PDF visual acceptance;
- M-A11 binding FJP Playwright Chromium timing/network acceptance;
- directly coupled M-A6/M-A7/M-A10 lazy/local/bounded behavior.

No product implementation file was edited.

Loaded:
- verification-before-completion
- webapp-testing

G6 identity before/after:
- branch main
- HEAD ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- tracked/staged clean
- only preserved ?? .pi/subagents.json
- git diff --check exit 0

Fresh runtime-equivalence check:
git diff --stat b2ffd886795840f0db570b8c07a913b406e68e80..HEAD -- plugin.py static/markdown_preview.js static/vendor/mermaid-11.17.2.min.js
produced no runtime diff. Therefore the existing Turn-1 export artifacts generated from current runtime remain valid for visual inspection, and the clean FJP b2ffd88 worktree is runtime-equivalent for M-A11.

Live Lantern :9999/:10099 was not touched. Dirty FJP main was preserved. No reset/stash/clean, no CDPA change, no Pi/native-terminal edit.

## 2. M-A8 — seven PNG exports

Existing raw export evidence:
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/

Files and exact decoded dimensions:
1. flowchart: mermaid-7-diagram-1.png — 504x134, 5,516 bytes
2. sequence: mermaid-7-diagram-2.png — 900x550, 25,836 bytes
3. class: mermaid-7-diagram-3.png — 215x534, 11,874 bytes
4. state: mermaid-7-diagram-4.png — 150x362, 8,939 bytes
5. ER: mermaid-7-diagram-5.png — 275x566, 16,206 bytes
6. Gantt: mermaid-7-diagram-6.png — 2400x248, 25,193 bytes
7. pie: mermaid-7-diagram-7.png — 1112x900, 89,839 bytes

Turn-1 automated checks already proved:
- all seven downloaded successfully;
- correct 1-based filenames;
- all decode as images;
- all are non-empty and contain non-white content;
- no SecurityError in the tested export path.

Fresh TEST Turn-5 visual inspection used the actual seven PNG files through the owned-device image preview tool.

Visual observations:
- flowchart: both node labels, connector and arrowhead visible;
- sequence: Alice/Bob lifelines, Hello/Ack labels, solid/dashed arrows visible;
- class: Animal/Dog boxes, inheritance triangle and +bark() visible;
- state: start/end markers, Ready label and arrowheads visible;
- ER: CUSTOMER/ORDER labels and cardinality relation visible;
- Gantt: complete timeline/bar/labels are present in the original 2400x248 export; the chat preview scales this very wide image down heavily, so tiny text in the rendered chat thumbnail is not treated as evidence of source-image clipping;
- pie: title, 40%/60% values and Alpha/Beta legend visible.

Classification:
**M-A8 PASS for the seven tested exports.**
This pass is limited to the tested fixtures and exact exported files; it is not a general visual guarantee for arbitrary Mermaid content.

## 3. M-A9 — Chromium Print / Save as PDF

Input artifact:
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/mermaid-seven-print.pdf

Existing automation proved:
- actual served Preview Print action invoked after Mermaid rendering;
- browser PDF generated;
- 8 pages;
- 61,248 bytes;
- selectable text includes "Printable sentinel 001 TEST." and section title text.

Turn-5 rendered **all 8 pages** to PNG at 1.5x using PyMuPDF:
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/pdf_pages_turn5/page-01.png ... page-08.png

Exact command:
C:\Users\admin\miniconda3\python.exe .plan\lantern-markdown-main-20261018\render_pdf_pages_turn5.py

Fresh visual inspection of every page found:
- page 1: flowchart and sequence are readable; arrowheads visible; no Lantern UI chrome;
- pages 2–3: the **class diagram is split across a page break** — Animal/inheritance top on page 2, Dog/+bark() continuation on page 3;
- pages 4–5: the **state diagram is split across a page break** — start/Ready on page 4, terminal state continuation on page 5;
- pages 6–7: the **ER diagram is split across a page break** — CUSTOMER/relation on page 6, ORDER continuation on page 7;
- page 7: Gantt is rendered extremely compact relative to the printed page;
- page 8: pie is readable;
- no Lantern controls/chrome were visible in the printed pages.

Expected contract:
selectable text, visible arrowheads, readable diagrams/vector SVG, no UI chrome, **no material clipping**.

Actual:
multiple single Mermaid diagrams are materially split by page boundaries, damaging readability and the document's print layout.

Classification:
**M-A9 FAIL — reproducible product rendering/export defect.**

Smallest concrete defect class:
Print CSS does not keep a Mermaid diagram together across a page boundary. Class/state/ER examples reproduce the issue.

This is sufficient to route DEV even without M-A11.

## 4. M-A11 — binding FJP Playwright Chromium measurement

### 4.1 Browser capability discovery

FJP device: LPP00374779A.

Fresh browser probe:
- Playwright-bundled default Chromium executable path does not exist; no browser was globally installed by TEST.
- Microsoft Edge channel exists: 155.0.4283.45.
- **Google Chrome channel exists and launches successfully: 155.0.8059.79.**

Thus there is no tooling blocker: the required Chromium-family Chrome runtime is already present.

### 4.2 Clean FJP runtime

Dirty FJP main remained untouched at its existing WIP state.

TEST created a clean detached worktree:
C:\Users\DuongNH66\Desktop\git\lantern-test-ma11-turn5
at b2ffd886795840f0db570b8c07a913b406e68e80.

Run environment:
- FJP Windows
- Google Chrome 155.0.8059.79
- uv locked environment
- actual served Lantern Preview HTML
- disposable document root/config/cache/work directory
- ephemeral 127.0.0.1 port
- nine fresh browser contexts
- no live service use.

The detached worktree and temporary helper/result files were removed after evidence was copied to G6.

Raw evidence:
.plan/lantern-markdown-main-20261018/test_turn5_fjp_ma11.json

### 4.3 Attribution method

For each fresh context:
1. Load actual served plain Markdown and record CDP Performance ScriptDuration.
2. Assert zero Mermaid bundle requests on plain Markdown.
3. Load actual served Mermaid Preview.
4. An init script gates the **first product setTimeout(0) after window.mermaid appears**. In current product code this is the deliberate yield immediately after Mermaid bundle script.onload and before initialize/render.
5. Read CDP ScriptDuration while helper initialize/render are still blocked.
6. Subtract the plain-page script duration for a conservative attributable bundle evaluation duration.
7. Wrap the real window.mermaid.initialize() and mermaid.render() before releasing the queued product continuation.
8. Record operation durations and Long Task entries.
9. Trigger the real product PNG action and record script time, toBlob callback duration, wall duration and Long Tasks.
10. Record request ledger and block any non-Lantern-origin request.

This isolates the bundle evaluation from product initialize/render. It does not add V8 compile time, so the recorded first-load number is a **conservative lower bound** for parse+evaluation rather than an inflated aggregate-page number.

### 4.4 Nine-context results

Attributable bundle ScriptDuration samples, ms:
1. 268.683
2. 402.405
3. 496.170
4. 477.004
5. 433.229
6. 533.535
7. 426.647
8. 475.300
9. 572.916

Summary:
- median: **475.300 ms**
- maximum: **572.916 ms**
- contractual median limit: <=300 ms
- contractual individual limit: <=500 ms

Therefore:
- median exceeds limit by ~175 ms;
- context 6 exceeds 500 ms;
- context 9 exceeds 500 ms.

Initialize:
- max **9.0 ms** — within <=100 ms.

Render:
- samples include 104.6, 116.2, 124.0 and 128.2 ms;
- max **128.2 ms**;
- attributed Long Tasks likewise reached 105, 116, 124 and 128 ms.

Therefore the governed render operation exceeds <=100 ms in multiple fresh contexts.

PNG:
- max ScriptDuration delta: 2.468 ms;
- max toBlob callback duration: 15.4 ms;
- max attributed PNG Long Task: 0 ms;
- wall download duration is larger (353–730 ms) but the contract is main-thread task attribution, not end-to-end download I/O.
- PNG governed main-thread evidence is within the 100 ms threshold in this fixture.

Network/lazy invariants:
- all 9 plain contexts: **0 Mermaid bundle requests**;
- all 9 Mermaid contexts: **exactly 1 Mermaid bundle request**;
- all contexts: **0 external/non-Lantern-origin runtime requests**.

Classification:
**M-A11 FAIL.**
Two independent contractual breaches:
1. first-load bundle median 475.3 ms and two samples >500 ms;
2. several attributed render operations >100 ms.

Because the first-load measurement omits explicit V8 compile duration, the failure is conservative; adding parse/compile cost cannot rescue it.

## 5. M-A10 / M-A6 / M-A7 coupled disposition

Within this turn's measured runtime:
- local Mermaid bundle only: PASS;
- no CDN/external runtime request: PASS;
- plain Markdown zero Mermaid bundle load: PASS;
- Mermaid page lazy bundle load at most once: PASS;
- existing Turn-1 seven-type render and 24-diagram cap/failure isolation evidence remains valid against unchanged runtime.

No new Python runtime dependency was introduced by the product. Verification-only uv/Playwright helpers do not change product dependencies.

## 6. Result and next role

Material product defects are now independently reproduced:

1. **M-A9 PDF print layout defect** — single Mermaid diagrams split across page boundaries (class, state, ER), violating readable/no-material-clipping print acceptance.
2. **M-A11 performance defect** — binding FJP Google Chrome:
   - bundle evaluation median 475.3 ms >300 ms;
   - 2/9 samples >500 ms;
   - render operation exceeds 100 ms in multiple contexts, max 128.2 ms.

M-A8 passes for the tested seven exports.
M-A12 remains INCOMPLETE pending personal owner/security acknowledgement and is not synthesized here.

Route **DEV** for at most two coherent fixes, matching the team limit:
- subtask 1: print/PDF page-break containment and readability;
- subtask 2: Mermaid first-load/render performance against the existing lazy/sequential/security constraints.

DEV must not weaken acceptance thresholds, remove security controls, add CDN runtime, cross into Pi/native terminal ownership, or touch live :9999. Independent REVIEW/TEST must follow.

No DONE.

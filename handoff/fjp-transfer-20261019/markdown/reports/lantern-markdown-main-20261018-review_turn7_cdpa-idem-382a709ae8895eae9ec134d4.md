# REVIEW Turn 7 — Mermaid print/performance fix review

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 7 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `1e3b77cda8d1d7e31019ccc79c38a6f63516817b`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn4_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE DEV.** The slice materially improves both original defects: class/state/ER diagrams no longer split across printed pages, and the official `@mermaid-js/tiny@11.17.2` substitution is a sound upstream/performance choice with seven-type/browser evidence. However, **M-A9 is still not satisfied**: the Gantt diagram is technically complete but its printed labels are reduced to ~4.8–5.3 pt in the generated PDF, which is not reasonably readable at normal print scale. This is a concrete reproducible product-output defect under the existing “readable diagrams/text” contract.

Do not reroute to TEST yet; fix the remaining print readability defect first, then independent TEST should rerun M-A9/M-A11.

## Repository / scope verification

Fresh repository facts:
- HEAD `1e3b77cda8d1d7e31019ccc79c38a6f63516817b`, commit `fix(markdown): bound Mermaid print and render work`.
- Commit changes 9 tracked files: print CSS, Mermaid helper, vendored Mermaid asset/license notice, 001 spec/plan/tasks, focused tests, and `.gitattributes`.
- `git diff HEAD~1 HEAD --check` -> **exit 0**.
- Final tree after REVIEW verification: only preserved `?? .pi/subagents.json`; no tracked/staged edits.
- No Pi/native-terminal, CDPA or live :9999 work performed.

Loaded `ponytail-review` and `verification-before-completion`.

## Fresh independent verification

### Unit / source

`C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py`:
- **28 passed, 5 subtests passed**
- **0.65 s**
- exit 0

The focused tests correctly lock:
- atomic Mermaid print wrapper CSS;
- no forced one-diagram-per-page break;
- official Tiny bundle size/hash;
- notice integrity metadata;
- explicit parse → yield → render ordering.

### Runtime browser regression

Fresh run of the existing disposable G6 browser harness:
`.plan/lantern-markdown-main-20261018/test_turn1_markdown_runtime.py`

Result:
- exit 0;
- all seven required types render SVG successfully;
- plain Markdown: 0 Mermaid requests;
- Mermaid page: exactly 1 Mermaid request;
- 0 external requests/page errors in the seven-type fixture;
- all 7 PNGs generated and non-white;
- 24-wrapper cap and malformed/oversized isolation remain intact;
- generated PDF: **5 pages**, selectable sentinel/title present.

The older harness still reads CSP from a response header although CSP is emitted as meta, so its empty `csp`/false nonce field is **not** used as CSP acceptance evidence; the dedicated CSP E2E already owns that gate.

### Upstream Tiny package / provenance

Fresh `npm view @mermaid-js/tiny@11.17.2` confirms:
- version 11.17.2;
- MIT;
- `dependencies: {}`;
- package integrity exactly `sha512-PmFr1c5cSfNf5AngLLR98DrbvR4U5KeD7I+hQkGqG5w5Veu3QT4dG0qu9f99cpn/sKj2XxRBK0q7EL6hr9NY/A==`.

Fresh upstream README query confirms Tiny explicitly removes:
- Mindmap;
- Architecture;
- KaTeX rendering;
- Mermaid internal lazy loading.

The vendored file is **2,516,850 bytes** and SHA-256 independently matches `9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd`.

This is a mature upstream alternative, not a hand-built custom subset. Lantern retains its own one-request page-level lazy load, so removing Mermaid’s internal lazy loader is acceptable for the seven required diagram types.

## Accepted parts

### A. Original page-fragmentation defect is fixed

Fresh regenerated PDF was rendered to all 5 pages and visually inspected by REVIEW.

Observed:
- page 1: flowchart + sequence complete;
- page 2: class complete on one sheet;
- page 3: state complete on one sheet;
- page 4: ER complete on one sheet;
- page 5: Gantt + pie on one sheet;
- no Mermaid diagram is split across page boundaries;
- no Lantern chrome is visible;
- arrowheads/cardinalities are visibly present in the inspected fixtures.

The chosen CSS is narrow and appropriate:
- `break-inside:avoid-page` + legacy `page-break-inside:avoid`;
- no `break-before:page`;
- `max-height:85vh` prevents tall diagrams from overflowing.

No extra print/layout framework is warranted.

### B. Tiny bundle choice is acceptable architecture/YAGNI

The previous 3.57 MB standalone bundle was the measured dominant first-load cost. Replacing it with the **official** Tiny distribution at the same pinned version is a smaller, upstream-supported change than maintaining a custom tree-shaken build.

The later custom seven-diagram experiment was correctly rejected and not left in the tree.

The explicit `runtime.parse(source)` before render adds a second governed step, but it is intentionally measured and separated by a yield rather than hidden. Since current acceptance requires parse/render task attribution separately, this is not an abstraction/YAGNI defect by itself.

## Concrete finding requiring DEV

### R7-1 — M-A9 print readability still fails for Gantt

**Contract:** Spec 001 M-A9 requires Chromium PDF output with **readable diagrams/text**, visible arrowheads, no material clipping and no UI chrome.

**Location:** print CSS in `plugin.py:~1279`:
`.mermaid-output svg{width:auto!important;max-width:100%!important;max-height:85vh!important;height:auto!important}`

**Fresh evidence:**
- regenerated current-HEAD PDF = 5 pages;
- page 5 visually shows the Gantt squeezed into a very shallow strip across the page;
- direct PDF text inspection on page 5 reports Gantt axis/task text at approximately:
  - date labels: **4.815 pt**;
  - `Task A` / `Demo`: **5.295 pt**;
  - title `Release`: **8.67 pt**.
- By contrast, pie text on the same page is ~17–26 pt and readily readable.
- Thus the diagram is complete and unclipped, but ordinary Gantt labels are effectively micro-text at normal print scale. The previous TEST already described the Gantt as “extremely compact”; the current fix did not resolve that part of M-A9.

**Why this matters:** “not split” is not equivalent to “readable”. The current CSS solves fragmentation by fitting an intrinsically 2400×248 SVG to portrait page width, shrinking its embedded text with it.

**Required correction:** keep the atomic/no-clipping behavior, but make wide/short Mermaid print output readable. Use the smallest robust print-specific rule/transform that preserves aspect and avoids arbitrary per-fixture hacks. Acceptable designs include a deliberate wide-diagram print treatment if Chromium can preserve readability without clipping; do not simply raise page count or force every diagram to its own page unless justified by the fixture/UX. Add a regression assertion for the chosen rule and regenerate/inspect the same seven-type PDF.

**Do not weaken M-A9** to “complete on page” or “selectable text exists”. The acceptance criterion is visual readability.

## M-A11 disposition

DEV’s controlled FJP Tiny diagnostic is encouraging:
- bundle median 176.656 ms;
- max 238.288 ms;
- initialize max 5.30 ms;
- explicit parse max 22.10 ms;
- render max 68.50 ms;
- no external requests/page errors.

But REVIEW did **not** independently rerun the binding nine-context FJP performance harness in this turn. Therefore:
- implementation choice: **technically acceptable**;
- M-A11 final acceptance: **INCOMPLETE pending independent TEST**, exactly as DEV reported.

The later heavy-host-load exploratory slowdown should remain in evidence as environment sensitivity, not be discarded and not be used alone as regression proof.

## Complexity / ownership / regression assessment

- **Over-engineering:** no material issue. Official Tiny beats a custom subset; CSS fix is local; no second renderer/runtime created.
- **Scope drift:** none beyond the two assigned defects plus necessary spec/test/license deltas.
- **UI/UX:** page fragmentation is fixed; Gantt print readability remains a user-visible defect.
- **Maintainability:** single pinned local asset and retained notice are manageable. `.gitattributes -text -diff` for a 2.5 MB minified vendor blob is reasonable.
- **Module separation:** Markdown Preview remains owned by `plugin.py` + `static/markdown_preview.js`; no terminal/Pi coupling.
- **Scalability/extensibility:** required seven types remain supported; intentionally unsupported Tiny types are now documented.
- **Mature upstream alternative:** official `@mermaid-js/tiny` is the correct upstream candidate here.
- **Regression/performance:** focused/unit/browser regressions are green; final FJP M-A11 independent acceptance is still missing.

Ponytail disposition: **Lean already; no complexity-driven rework requested.**

## Preservation / remaining gates

Preserved and still pending:
- M-A12 personal owner/security acknowledgement = INCOMPLETE;
- `LANTERN-SEC-001` remains open;
- 002 owner/manual/Linux residual gates unchanged;
- 003 MD-T000–T018 not touched;
- `.md` source truth, `md_temp`, CAS and mapping semantics unchanged;
- `.pi/subagents.json` untouched.

## Next DEV slice

Only one concrete correction is required from this REVIEW:

1. Fix **wide Gantt print readability** while preserving the newly-fixed no-split/no-clipping behavior; update the smallest focused regression test and regenerate evidence.

Do **not** spend the second subtask on unrelated 003 work in the same turn. After the print fix, route independent TEST to rerun:
- M-A9 visual all-page PDF acceptance;
- M-A11 nine-context FJP performance acceptance against the committed Tiny build.

**Required route: DEV.**

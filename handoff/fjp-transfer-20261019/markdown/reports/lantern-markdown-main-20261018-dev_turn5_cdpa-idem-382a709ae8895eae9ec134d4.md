# DEV Turn 5 — fix Gantt print readability

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18 JST  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed
Executed only REVIEW Turn 7 finding **R7-1**:
- keep the existing no-split/no-clipping Mermaid print behavior;
- make wide Gantt labels readable at normal A4 print scale;
- add the smallest focused regression assertion;
- regenerate and inspect the same seven-type PDF.

No 003 work was started. No Pi/native terminal, CDPA, live `:9999`, reset/stash/clean, dependency or bundle change. `.pi/subagents.json` remains untouched.

## Root cause / design choice
Fresh inspection of the actual rendered Gantt SVG showed:
- `viewBox="0 0 1200 124"`;
- date ticks at 10 px;
- task/section labels at 11 px;
- title at 18 px.

When the 1200-wide SVG is scaled to portrait A4 width, the PDF reduced those labels to the REVIEW-observed ~4.8–5.3 pt. The diagram was complete, but text was micro-sized.

The chosen fix is deliberately narrow and print-only:
- for Mermaid SVGs whose semantic `aria-roledescription` is `gantt`, print ordinary `text` at 20 px;
- keep `.titleText` at 24 px;
- retain the existing natural-aspect, `max-width:100%`, `max-height:85vh`, and atomic-wrapper rules;
- no forced page break, landscape page, A3 page, per-document special case, JavaScript classifier, or new print subsystem.

This uses Mermaid's semantic SVG role rather than fixture content and does not affect screen rendering or other diagram types.

## TDD evidence

### RED
First changed only the focused regression in `tests/test_plugin.py` to require:
- `.mermaid-output svg[aria-roledescription="gantt"] text{font-size:20px!important}`
- `.mermaid-output svg[aria-roledescription="gantt"] .titleText{font-size:24px!important}`

Command:
```
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py -k print_css_keeps_mermaid_diagram_atomic_and_natural_size
```

Observed expected failure:
- 1 failed, 27 deselected;
- missing Gantt print rule.

### GREEN
Added only those two print-specific CSS rules in `plugin.py`.

Focused rerun:
- **1 passed, 27 deselected**.

Post-commit focused rerun:
- **1 passed, 27 deselected in 0.39 s**, exit 0.

## Fresh browser/PDF acceptance evidence

Ran the existing disposable seven-type browser harness after the production change:
```
C:\Users\admin\miniconda3\python.exe .plan\lantern-markdown-main-20261018\test_turn1_markdown_runtime.py
```

Result:
- exit 0;
- all seven required Mermaid types render;
- exactly one local Mermaid request on Mermaid page;
- zero external requests in the seven-type fixture;
- all seven PNG exports remain non-empty;
- 24-wrapper cap/failure isolation remains intact;
- PDF regenerated successfully;
- **5 pages**;
- selectable sentinel/title preserved.

Evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn5_runtime.log`
- `.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/mermaid-seven-print.pdf`

Rendered all five PDF pages again:
```
C:\Users\admin\miniconda3\python.exe .plan\lantern-markdown-main-20261018\render_pdf_pages_turn5.py
```

Fresh visual inspection:
- page 1: flowchart + sequence complete;
- page 2: class complete;
- page 3: state complete;
- page 4: ER complete;
- page 5: Gantt + pie complete;
- no diagram split;
- no UI chrome;
- Gantt labels no longer use the previous micro-text sizing.

Fresh PDF text-metric extraction on page 5:
- date labels: **9.63 pt**;
- `Task A`: **9.63 pt**;
- `Demo`: **9.63 pt**;
- `Release`: **11.56 pt**.

Prior REVIEW evidence was ~4.815 pt for dates and ~5.295 pt for task/section text, so the production fix roughly doubles the effective printed text size while preserving the same five-page layout.

Raw metric evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn5_pdf_font_sizes.json`
- rendered pages under `test_turn1_markdown_artifacts/pdf_pages_turn5/`.

## Regression verification actually run

Focused plugin suite:
```
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py
```
Result: **28 passed, 5 subtests passed in 1.34 s**, exit 0.

Full native suite:
```
C:\Users\admin\miniconda3\python.exe -m pytest -q
```
Result: **210 passed, 110 skipped, 47 subtests passed in 81.56 s**, exit 0.

Evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn5_full_pytest.log`.

Hygiene:
- `git diff --check` exit 0;
- staged diff check exit 0;
- final tracked tree clean;
- final `git status --short`: only preserved `?? .pi/`.

## Commit
Committed bounded repair:
- **`16e538f04a84768eb540bb731d1ccc81e3547fbc`**
- `fix(markdown): keep Gantt print text readable`

Changed tracked files:
- `plugin.py`
- `tests/test_plugin.py`

No other tracked file changed in this turn.

## Remaining acceptance boundary
DEV has fresh evidence that the concrete R7-1 defect is repaired, but does **not** self-approve the release gates.

Still requires independent TEST:
1. **M-A9** — rerun/inspect the five-page seven-type PDF and independently judge Gantt readability/no clipping/no split.
2. **M-A11** — rerun the binding nine-fresh-context FJP Google Chrome timing/network harness against committed Tiny build `16e538f`.

M-A11 was not rerun by DEV in this turn because this fix is print-CSS-only and REVIEW explicitly reserved final performance acceptance for independent TEST.

M-A12 remains INCOMPLETE pending personal owner/security acknowledgement. 002 residual closure gates and 003 work remain unchanged.

## Route
**TEST** — REVIEW Turn 7 explicitly required independent TEST after this single print-readability correction, and the committed source work is complete.

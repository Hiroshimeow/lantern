# DEV Turn 4 — fix Mermaid print fragmentation and performance

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18 JST  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed
Executed exactly the two defects from TEST Turn 5 and stopped:
1. M-A9 print/PDF containment/readability.
2. M-A11 Mermaid first-load/render performance.

No Pi/native terminal work, no CDPA changes, no live `:9999` restart/use, no reset/stash/clean, and preserved `.pi/subagents.json`.

## Accepted implementation
Current committed HEAD:
- `1e3b77cda8d1d7e31019ccc79c38a6f63516817b`
- `fix(markdown): bound Mermaid print and render work`

Commit scope:
- `plugin.py`
- `static/markdown_preview.js`
- `static/vendor/mermaid-11.17.2.min.js`
- `static/vendor/mermaid-11.17.2.LICENSES.txt`
- `specs/001-terminal-ime-markdown-export/{spec,plan,tasks}.md`
- `tests/test_plugin.py`
- `.gitattributes` (marks the large Mermaid asset non-text/non-diff only; no runtime behavior)

### Subtask 1 — print/PDF
Root cause: Chromium was allowed to fragment one Mermaid wrapper across sheets, and wide/tall SVG sizing did not constrain page height.

Fix:
- Mermaid wrapper uses `break-inside:avoid-page` plus legacy `page-break-inside:avoid`.
- Mermaid SVG print sizing preserves natural aspect ratio with `width:auto; max-width:100%; max-height:85vh; height:auto`.
- Markdown headings avoid orphaning with `break-after:avoid-page`.
- No forced `break-before:page`; multiple small diagrams may still share a page.

Fresh G6 browser/runtime evidence after the fix:
- seven required Mermaid types render;
- PNG exports remain non-empty;
- print PDF regenerated as **5 pages** (previous defect artifact was 8 pages);
- rendered page images show:
  - page 1: flowchart + sequence complete;
  - page 2: class complete;
  - page 3: state complete;
  - page 4: ER complete;
  - page 5: Gantt + pie complete;
- class/state/ER are no longer split across page boundaries;
- no UI chrome visible in inspected pages.

Artifacts:
- `.plan/lantern-markdown-main-20261018/dev_turn4_official_tiny_runtime.log`
- `.plan/lantern-markdown-main-20261018/dev_turn4_official_tiny_pdf_pages.log`
- page PNGs under `test_turn1_markdown_artifacts/pdf_pages_turn5/`.

### Subtask 2 — Mermaid performance
Root causes measured:
- 3.57 MB full standalone Mermaid bundle was the dominant first-load parse/evaluation cost.
- first render included parser/diagram-registry warm-up, pushing governed render work over 100 ms on FJP.

Smallest production fix selected:
- same pinned version, **official `@mermaid-js/tiny@11.17.2` browser build**, still vendored locally/offline;
- production asset size: **2,516,850 bytes**;
- SHA-256: **9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd**;
- npm package integrity recorded in notice:
  `sha512-PmFr1c5cSfNf5AngLLR98DrbvR4U5KeD7I+hQkGqG5w5Veu3QT4dG0qu9f99cpn/sKj2XxRBK0q7EL6hr9NY/A==`;
- local lazy one-request behavior retained; no CDN/runtime chunk dependency added;
- all seven required types are covered by the browser runtime test.
- helper now explicitly `await runtime.parse(source)`, yields, then calls `runtime.render(...)`; parse remains a measured governed task rather than hidden/excluded work.

A post-commit experiment with a smaller custom seven-diagram build was **not accepted**. Its dirty files were restored byte-for-byte to committed HEAD without reset/stash/clean. Final tracked tree has no dirty product/spec/test files.

## Verification actually run

### Focused committed-tree unit
```
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py
```
Result on final HEAD: **28 passed, 5 subtests passed in 1.32 s, exit 0**.

### Full native suite
Run during this implementation slice against the same accepted working-tree source before commit:
```
C:\Users\admin\miniconda3\python.exe -m pytest -q
```
Result: **210 passed, 110 skipped, 47 subtests passed in 100.68 s**.
Evidence: `.plan/lantern-markdown-main-20261018/dev_turn4_full_pytest.log`.

### G6 real browser runtime
`.plan/lantern-markdown-main-20261018/test_turn1_markdown_runtime.py` on disposable loopback Lantern + browser:
- final run exit 0;
- all seven required types rendered;
- exactly one Mermaid bundle request on Mermaid page;
- no external requests;
- 24-wrapper cap/failure isolation still works;
- PDF regenerated and inspected as described above.

### FJP controlled DEV performance diagnostic
Raw copied evidence:
`.plan/lantern-markdown-main-20261018/dev_turn4_fjp_ma11_tiny.json`

Environment/method:
- FJP Google Chrome 155.0.8059.79;
- nine fresh contexts;
- actual served product Preview;
- each sample waited for host CPU <15% before context start;
- plain page remains zero Mermaid requests;
- Mermaid page exactly one bundle request;
- helper initialize/parse/render excluded only from first-load bundle attribution, then measured separately.

Observed:
- bundle median **176.656 ms** (limit <=300 ms);
- bundle max **238.288 ms** (limit <=500 ms);
- initialize max **5.30 ms**;
- explicit parse max **22.10 ms**;
- render max **68.50 ms**;
- render Long Task max **68 ms**;
- all external request counts zero;
- all page-error counts zero.

A later exploratory rerun under heavy FJP host load (~60–70% pre-context CPU) produced materially worse timings; it is recorded as noisy diagnostic evidence and is **not** promoted to independent acceptance. This is why DEV does not declare M-A11 final PASS. Independent TEST must rerun the binding harness under controlled, documented conditions.

### Hygiene
- `git diff --check` exit 0.
- final `git status --short`: only preserved `?? .pi/`.
- committed Mermaid asset restored exactly to HEAD hash above.
- no staged diff remains.

## Acceptance status / remaining risks
- M-A9: DEV source fix has strong fresh G6 visual evidence, but final gate requires independent TEST.
- M-A11: DEV controlled FJP diagnostic is within thresholds, but final gate requires independent TEST because performance is load-sensitive.
- M-A8 remained green in the final runtime fixture.
- M-A12 remains **INCOMPLETE** pending personal owner/security acknowledgement; DEV did not synthesize approval.
- 002 closure gates and 003 work remain outside this turn and unchanged.

## Route
**REVIEW**. This slice changes print CSS, execution scheduling, and the vendored Mermaid distribution, so it needs independent review for correctness, upstream choice, YAGNI/over-engineering, security/license claims, maintainability, UX/regression/performance, and test sufficiency before TEST re-runs M-A9/M-A11.

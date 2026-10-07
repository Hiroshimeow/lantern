# DEV turn 2 report

## Scope and verified state

Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Baseline/HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

Loaded PLAN handoff:
.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-plan_turn1_cdpa-idem-e87d06b05bac9166449558ae.md

This turn followed the PLAN requirement to reproduce and attribute the >100 ms Mermaid-caused main-thread task before making any further product-code changes.

No Markdown/Mermaid product source change was made in turn 2. The only new artifact created outside the repository was a retained diagnostic harness in:
C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\attribute.js

No immutable file was touched. No commit, merge, or push was performed.

## Exact bundle verification

Before measurement:
- Branch remained feature/lantern-markdown-export-20261006.
- HEAD remained 387a5f17a30ab60f50ae290c8651511608f153d1.
- Existing turn-1 implementation remained uncommitted.
- static/vendor/mermaid-11.17.2.min.js SHA256:
  581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8
  This exactly matches the reviewed T5 pin.
- node --check static/markdown_preview.js: PASS.

## Attribution method

Used local Lantern on 127.0.0.1:18765 and locally installed Node Playwright Chromium.

The diagnostic intentionally used plain.md, which has no Mermaid fence and therefore does not lazy-load Mermaid through the product helper. In each fresh browser context:

1. Navigate to the plain Markdown preview and wait for network idle.
2. Clear collected Long Task API entries.
3. Dynamically append only the exact local reviewed Mermaid 11.17.2 standalone bundle with the preview nonce.
4. Measure bundle script append -> load completion and collect Long Task API entries.
5. Clear long-task entries.
6. Run Mermaid initialize with the required strict configuration and measure it separately.
7. Clear long-task entries.
8. Render one small flowchart into an off-screen measurable container and measure that separately.

This isolates first-load bundle parse/evaluation from initialize and render work. No total-page elapsed-time inference was used as acceptance evidence.

## Raw attribution evidence

Fresh run 1:
- exact bundle load/parse/eval elapsed: 289.4 ms
- bundle-phase main-thread long task: 200 ms
- initialize elapsed: 4.1 ms
- initialize long tasks: none
- single flowchart render elapsed: 50.1 ms
- render-phase long task: 50 ms
- rendered SVG length: 12143 bytes/chars

Fresh run 2:
- exact bundle load/parse/eval elapsed: 265.9 ms
- bundle-phase main-thread long task: 184 ms
- initialize elapsed: 4.0 ms
- initialize long tasks: none
- single flowchart render elapsed: 36.5 ms
- render-phase long tasks: none
- rendered SVG length: 12143

Fresh run 3:
- exact bundle load/parse/eval elapsed: 228.8 ms
- bundle-phase main-thread long task: 158 ms
- initialize elapsed: 2.6 ms
- initialize long tasks: none
- single flowchart render elapsed: 31.1 ms
- render-phase long tasks: none
- rendered SVG length: 12143

Observed exact-bundle long tasks across three fresh contexts:
- 200 ms
- 184 ms
- 158 ms

All three exceed the binding <=100 ms Mermaid-caused main-thread-task requirement.

## Technical conclusion

The reproducible blocker is first-load JavaScript parse/compile/evaluation of the exact required 3.57 MB standalone Mermaid 11.17.2 bundle itself, not Mermaid initialize and not an individual small render.

The browser executes a classic external script evaluation as one main-thread task. The current helper can defer when that script loads, and can yield between diagrams, but it cannot split the browser's parse/evaluation of that exact standalone script into sub-100 ms tasks.

Legal helper-level changes such as:
- additional setTimeout/requestAnimationFrame before loading,
- later lazy load,
- more yields before/after script insertion,
- fewer diagrams after load,

do not break the bundle evaluation task and therefore cannot satisfy M-A11.

PLAN explicitly prohibited DEV from:
- changing the exact reviewed Mermaid 11.17.2 bundle/pin,
- silently substituting a CDN/chunk strategy,
- weakening/reinterpreting the <=100 ms rule,
- changing immutable terminal/backend/dependency files.

Therefore there is no legal in-scope DEV remediation under the current contract.

## Acceptance state

M-A11 / T7 responsiveness remains INCOMPLETE / FAILING:
- exact bundle first-load long task is independently attributed at 158–200 ms in fresh contexts.
- This is already enough to fail the <=100 ms requirement before testing worst-case multi-diagram render/export load.

Previous turn-1 and PLAN evidence for the rest of T7 remains preserved:
- seven required Mermaid types rendered;
- malformed and oversize isolation worked;
- page cap 24 worked;
- plain Markdown did not load Mermaid;
- exact nonce CSP behavior worked;
- nonce-less same-origin script did not execute;
- PNG toBlob/download produced a non-empty PNG;
- headless PDF was non-empty;
- no non-Lantern request was observed in the retained acceptance harness.

Still INCOMPLETE / NOT_MEASURED from prior evidence:
- parent terminal responsiveness under worst-case Mermaid load;
- manual visual PNG legibility;
- manual PDF selectable-text/arrowhead/readability/clipping proof;
- security-owner residual-risk sign-off;
- follow-up ticket for iframe sandboxing plus same-origin uploaded HTML/SVG serving.

Because the exact bundle parse/eval alone fails the binding responsiveness gate, these incomplete items do not change the current route decision.

## Checks not rerun

The full T7 and T8 suites were not rerun in turn 2 because PLAN explicitly said that if exact 11.17.2 first-load parse/compile itself exceeds 100 ms and cannot legally be split, DEV must stop implementation and report a hard spec/architecture blocker rather than manufacture PASS.

Turn-1/PLAN retained evidence already has:
- focused plugin tests 13/13 PASS;
- full Python suite 37/37 PASS;
- node --check PASS;
- git diff --check PASS;
- exact Mermaid hash PASS;
- immutable file diff PASS.

No new product-code change in turn 2 invalidates those retained results.

## Required decision / route

Hard spec/architecture blocker.

A PLAN-level contract decision is required before more DEV work. At least one currently immutable constraint must change to make M-A11 achievable, for example the allowed Mermaid artifact/loading architecture or the acceptance requirement itself. DEV has no authority to choose that change.

Do not commit, merge, or push the existing implementation while this blocker remains.

# PLAN turn 5 report

Role: PLAN
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

Route **DEV**.

TEST turn 3 independently reproduced a binding implementation failure in the current product loading path, and TEST turn 4 recovery confirmed that the failing source remains unchanged. The current Mermaid page still emits the exact local Mermaid 11.17.2 script at the end of BODY without `defer`, immediately before `static/markdown_preview.js`.

Independent TEST first-load attribution measured the current product path above the hard <=250 ms isolated parse/evaluation budget in 2/9 fresh contexts (269 ms, 269 ms). This is an implementation blocker, not an evidence-only gap.

TEST also produced a legal narrow probe: the exact same local nonce-authorized Mermaid asset moved into HEAD with `defer` measured 182-231 ms across 9/9 fresh contexts. That probe was not a repository product PASS, but it identifies the next minimal remediation to implement and verify.

There is therefore no basis to route TEST again before a source change, no basis for REVIEW while the binding technical acceptance is failing, and no external prerequisite requiring PAUSE.

## Incoming handoff reviewed

Incoming:
`.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-test_turn4_cdpa-idem-e87d06b05bac9166449558ae.md`

TEST turn 4 recovery correctly did not replay completed TEST work. It confirmed:

- no newer DEV implementation followed the TEST turn-3 failure;
- `plugin.py` still emits the conditional Mermaid vendor script without `defer`;
- it is still emitted after preview BODY content and immediately before `static/markdown_preview.js`;
- the exact product path that failed independent timing remains present;
- the durable next action is PLAN -> DEV.

Repository status remains intentionally dirty from the feature implementation and prior PLAN/spec work. No implementation file was edited by PLAN turn 5.

## Current source issue

Current `plugin.py` behavior:

- `mermaid_script` is conditional on rendered Mermaid markup;
- it is emitted at the end of BODY;
- vendor tag:
  `<script nonce="..." src="/static/vendor/mermaid-11.17.2.min.js"></script>`
- helper follows immediately:
  `<script nonce="..." src="/static/markdown_preview.js"></script>`

Current `static/markdown_preview.js` executes immediately when parsed. Its `renderAll()` calls `loadMermaid()`; if `window.mermaid` is absent, `loadMermaid()` dynamically injects the same vendor script into HEAD.

That means simply moving only the vendor tag to HEAD with `defer` is insufficient: the current non-deferred helper at the end of BODY can execute before the deferred vendor finishes and can re-enter the dynamic loading path. DEV must preserve execution ordering as part of the remediation.

## DEV implementation contract

Implement the smallest product loading-path change that realizes the successful TEST probe without weakening any acceptance requirement.

Required behavior:

1. Keep the exact reviewed local Mermaid asset:
   - `/static/vendor/mermaid-11.17.2.min.js`
   - SHA-256 must remain:
     `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

2. On pages containing Mermaid diagrams, emit the conditional Mermaid vendor script in HEAD with:
   - the existing per-response nonce;
   - `defer`;
   - no CDN or alternate bundle.

3. Preserve helper ordering so `static/markdown_preview.js` cannot begin Mermaid initialization/render work before the deferred vendor script is ready.
   - Preferred minimal structure: parser-discovered deferred scripts in HEAD, ordered vendor first and helper second on Mermaid pages.
   - On non-Mermaid pages, emit only the helper, still preserving nonce/CSP behavior.
   - An equivalent structure is acceptable only if the normal Mermaid product path provably does not exercise the dynamic fallback or issue a duplicate Mermaid request.

4. Do not remove the existing local fallback unless DEV has a concrete reason and tests cover the loss. The acceptance target is that the normal parser-discovered Mermaid page does not need that fallback.

5. Preserve all existing contracts:
   - Mermaid vendor absent on non-Mermaid pages;
   - nonce-only script CSP remains exact;
   - offline/same-origin operation; zero CDN or other non-Lantern runtime requests;
   - Mermaid `securityLevel: "strict"` and sanitization configuration unchanged;
   - malformed diagram isolation;
   - oversized diagram isolation;
   - page cap behavior;
   - sequential rendering and UI yields;
   - PNG export naming/non-empty output;
   - Print / Save as PDF waits for pending renders;
   - no terminal persistence, IME, UniKey, backend, dependency, or unrelated scope changes.

6. Do not weaken the binding performance contract:
   - isolated first-load Mermaid bundle parse/evaluation: every accepted sample <=250 ms;
   - subsequent attributable initialize/render/export work: <=100 ms;
   - aggregate page Long Tasks remain informational unless correctly attributed.

## Required DEV tests and evidence

Update/add structural tests so they prevent regression of this exact loading path. At minimum verify:

- Mermaid HTML contains exactly one parser-discovered vendor tag;
- the vendor tag is inside HEAD, nonce-authorized, and `defer`;
- helper execution ordering is deterministic after the vendor on Mermaid pages;
- plain Markdown contains no Mermaid vendor tag;
- helper remains nonce-authorized;
- product browser path performs no duplicate vendor fetch and does not take the dynamic fallback under normal Mermaid-page loading.

Then run fresh:

- `uv run --no-project python -m unittest -v test_plugin`;
- full Python unittest discovery;
- `node --check static/markdown_preview.js`;
- `node --check static/terminal_scm.js`;
- `git diff --check`;
- exact Mermaid SHA-256 check;
- immutable scope diff against `387a5f1` for terminal/backend/dependency files.

Performance verification must repeat the same isolated methodology used by TEST:

- actual current product preview HTML;
- fresh browser contexts;
- isolate vendor parse/evaluation from helper initialize/render contamination;
- at least nine fresh-context samples;
- all samples must be <=250 ms;
- record the actual per-run values.

Also rerun the functional browser acceptance on the changed product path, including zero non-Lantern requests, exact CSP, nonce-less script blocking, seven valid diagram families, malformed/oversize/cap isolation, plain-Markdown zero vendor requests, PNG, and print-waits-for-render behavior.

## Scope preservation

Existing dirty authoritative files:

- `specs/001-terminal-ime-markdown-export/spec.md`
- `specs/001-terminal-ime-markdown-export/plan.md`
- `specs/001-terminal-ime-markdown-export/tasks.md`

already encode the corrected performance contract. Preserve them unless a source/test change genuinely requires synchronization; do not rewrite the threshold or acceptance meaning to fit measurements.

Do not commit, push, or merge in this remediation turn.

## DEV exit criteria

If the product HEAD+`defer` implementation satisfies deterministic gates, functional acceptance, and DEV's fresh isolated <=250 ms sample, route to independent TEST for reproduction.

If the implemented product path still crosses <=250 ms, do not weaken the threshold, replace the reviewed asset, or broaden scope opportunistically. Return control for replanning with exact measurements and loading-path evidence.

## Route

DEV

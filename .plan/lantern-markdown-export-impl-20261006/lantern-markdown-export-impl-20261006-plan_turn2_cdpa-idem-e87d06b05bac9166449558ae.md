# PLAN turn 2 report

## Workspace and lifecycle state

Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`
Branch: `feature/lantern-markdown-export-20261006`
Baseline / HEAD: `387a5f17a30ab60f50ae290c8651511608f153d1`

Inspected handoff:
`.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-dev_turn2_cdpa-idem-e87d06b05bac9166449558ae.md`

Current worktree remains the uncommitted Markdown/Mermaid/export implementation from turn 1:
- modified `plugin.py`
- new `test_plugin.py`
- new `static/markdown_preview.js`
- new `static/vendor/mermaid-11.17.2.min.js`
- new `static/vendor/mermaid-11.17.2.LICENSES.txt`
- PLAN/DEV reports under `.plan/lantern-markdown-export-impl-20261006/`

No immutable file differs from `387a5f1`.

## Fresh verification

PLAN independently re-ran the current evidence rather than relying only on DEV claims.

### Repository/scope

- branch: `feature/lantern-markdown-export-20261006`
- HEAD: `387a5f17a30ab60f50ae290c8651511608f153d1`
- exact Mermaid bundle SHA-256:
  `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`
- immutable-file diff against `387a5f1`: PASS

### Automated suite

Fresh run:
- `python3 -m unittest -v` under WSL Python: **37/37 PASS**
- `node --check static/markdown_preview.js`: PASS
- `git diff --check`: PASS

### Reproduction / attribution of M-A11 failure

Using local Lantern at `127.0.0.1:18765` and the retained diagnostic harness
`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\attribute.js`,
PLAN repeated three fresh contexts that isolate only the exact local Mermaid 11.17.2 standalone bundle load/parse/evaluation.

Fresh PLAN results:

Run 1:
- script load/parse/eval elapsed: 304.2 ms
- Mermaid-caused main-thread long task: **207 ms**
- initialize: 3.2 ms, no long task
- one small flowchart render: 50.5 ms, 50 ms task

Run 2:
- script load/parse/eval elapsed: 279.9 ms
- Mermaid-caused main-thread long task: **194 ms**
- initialize: 2.8 ms, no long task
- render: 38.6 ms, no long task

Run 3:
- script load/parse/eval elapsed: 248.9 ms
- Mermaid-caused main-thread long task: **173 ms**
- initialize: 2.8 ms, no long task
- render: 32.9 ms, no long task

This independently confirms DEV turn 2: the binding failure is first-load evaluation of the exact 3.57 MB standalone bundle itself.

The authoritative specification says every Mermaid-caused main-thread task, including first bundle parse/compile, must be <=100 ms. Any task above 100 ms keeps acceptance INCOMPLETE and requires re-review of loading/pin/caps rather than a waiver.

Therefore T7 / M-A11 remains **INCOMPLETE / FAILING**.

## Contract-preserving alternatives checked

PLAN checked the plausible browser-loading alternatives before concluding that no legal DEV action remains.

### Worker execution

Under the exact required CSP:

`default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`

a Worker attempt using the same local Mermaid bundle generated a CSP violation with effective directive `worker-src`. Because no explicit `worker-src` exists, it falls back to `default-src 'none'`.

So moving Mermaid evaluation to a Worker requires changing the exact CSP contract. It is not a legal DEV-only fix under the present task.

Additionally, Mermaid rendering is DOM-dependent, so a Worker path would require a materially different runtime/render architecture even after CSP changes.

### Loading the exact same bundle as a module

PLAN loaded the exact same local file through `<script type="module">` in three fresh contexts.

Observed long tasks:
- **331 ms**
- **253 ms**
- **274 ms**

This is worse than classic-script loading and still fails the <=100 ms contract. It also did not expose `window.mermaid` as required by the current helper/runtime contract.

Therefore module loading is not a legal or effective solution.

### More yielding / delaying / lower diagram count

These cannot divide the browser's single main-thread parse/evaluation task for the exact standalone bundle. They can only move when it occurs.

The page-cap and render-yield controls therefore cannot fix this measured first-load task.

## Requirements classification

### PRESERVE / already green

- T3 parser/security tests and structural allowlist.
- T4 bounded stdlib Markdown parser and exact nonce CSP.
- T5 reviewed Mermaid 11.17.2 dependency/license gate.
- T6 local vendoring, strict config, sequential rendering, PNG export, Print / Save as PDF implementation.
- no CDN / no new Python dependency.
- immutable terminal/backend files untouched.
- exact reviewed Mermaid SHA-256.
- current automated suite: 37/37 green.

### INCOMPLETE / blocker

- M-A11 / T7 <=100 ms responsiveness: reproducibly fails from exact bundle evaluation alone.
- Parent-terminal worst-case responsiveness remains unproven.
- Manual PNG visual-legibility proof remains incomplete.
- Manual Chromium PDF selectable-text / arrowhead / readability / clipping proof remains incomplete.
- Security-owner residual-risk sign-off remains unavailable.
- Required follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving remains absent.

The latter manual items are not the reason for this route: M-A11 already makes acceptance impossible under the current immutable contract.

## PLAN decision

There is no remaining legal in-task DEV action that can satisfy M-A11 while preserving all of these simultaneously:

1. exact Mermaid 11.17.2 standalone bundle;
2. exact CSP with no Worker allowance;
3. no changed loading/runtime architecture;
4. <=100 ms for first-load Mermaid parse/compile/evaluation.

The evidence shows these constraints are mutually incompatible on the accepted Chromium runtime.

Routing back to DEV would only invite prohibited changes or repeated measurements. Routing to TEST is invalid because acceptance is known failing. REVIEW is premature because the implementation cannot meet the binding spec.

## PAUSE

`block_code: MERMAID_MA11_CONTRACT_CONFLICT`

External/spec-owner decision is required. At least one authoritative constraint must change before legal implementation work can resume.

Acceptable resume conditions include one explicitly reviewed contract change such as:

- permit a different Mermaid artifact/version/loading architecture that is demonstrated to keep each accepted main-thread task <=100 ms; or
- explicitly permit an off-main-thread execution architecture and update CSP/runtime requirements accordingly; or
- revise the M-A11 threshold/measurement contract based on an approved product-performance decision.

The owner must state the new authoritative contract in the spec/plan/tasks or equivalent approved handoff. DEV must not infer which constraint to relax.

Do not commit, merge, or push the existing implementation while this blocker remains.

## Route

PAUSE.

# PLAN turn 1 report

## Workspace and verified state

- Workspace: `C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export`
- Branch: `feature/lantern-markdown-export-20261006`
- Planning baseline / HEAD: `387a5f17a30ab60f50ae290c8651511608f153d1`
- Scope: Markdown / Mermaid / export lane only. Terminal persistence, IME, UniKey, and terminal product-code changes are out of scope.
- Current worktree is **not clean**. Uncommitted implementation already exists:
  - modified: `plugin.py`
  - new: `test_plugin.py`
  - new: `static/markdown_preview.js`
  - new: `static/vendor/mermaid-11.17.2.min.js`
  - new: `static/vendor/mermaid-11.17.2.LICENSES.txt`
- Existing DEV report inspected:
  `.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-dev_turn1_cdpa-idem-e87d06b05bac9166449558ae.md`

## Authoritative ownership and boundaries

Verified from the current spec/plan/tasks and lane-split review:

- `plugin.py` owns Markdown parsing and preview-page generation.
- `static/markdown_preview.js` owns the normal Back action, Mermaid runtime loading/rendering, PNG export, and Print / Save as PDF.
- `static/vendor/mermaid-11.17.2.min.js` is the exact locally vendored Mermaid runtime.
- `static/vendor/mermaid-11.17.2.LICENSES.txt` retains pin/advisory/license evidence.
- Tests for this lane live in `test_plugin.py`.

Hard immutable files remain:
- `static/terminal_scm.js`
- `static/vendor/xterm.js`
- `lantern_terminal.py`
- `lantern_ws.py`
- `lan_drive.py`
- `requirements.txt`

Independent scope check against `387a5f1` currently passes for all six immutable files.

## Requirement classification

### PRESERVE

1. Preserve all hard immutable files byte-identical to `387a5f1`.
2. Preserve no-new-Python-dependency / no-CDN / no runtime author remote-data image loads.
3. Preserve the exact CSP contract:
   `default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`
4. Preserve raw author HTML escaping, root confinement, no `<base>`, quoted URL attributes, and local/root-only author images.
5. Preserve the exact reviewed Mermaid 11.17.2 standalone bundle and SHA-256:
   `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`.
6. Preserve strict Mermaid config:
   - `startOnLoad:false`
   - `securityLevel:"strict"`
   - `suppressErrorRendering:true`
   - fixed light theme
   - `htmlLabels:false`
   - `maxTextSize:60000`
   - `maxEdges:500`
   - conservative `dompurifyConfig`
   - secure list containing `secure, securityLevel, startOnLoad, suppressErrorRendering, maxTextSize, maxEdges, theme, themeCSS, themeVariables, fontFamily, htmlLabels, dompurifyConfig`
7. Preserve page cap 24, sequential rendering, yields between diagrams, no Mermaid load on pages without Mermaid fences.
8. Preserve PNG contract and Print / Save as PDF contract exactly as the authoritative docs state.
9. Do not commit, merge, or push until the required TEST/REVIEW lifecycle is green.

### COMPLETE, with current evidence

#### T3 Markdown security/parser tests

`test_plugin.py` currently covers the requested parser/security classes:
- raw HTML escaping and NUL removal;
- C0/mixed-case/entity-decoded dangerous schemes;
- local/root/fragment/http/https/mailto link allowlist;
- local/root-only images;
- exactly-once unquote/segment encoding;
- no `<base>`;
- image-before-link parsing;
- nested stash restoration;
- quoted escaped URL attributes;
- fence character/length/closing-info behavior;
- case-insensitive first Mermaid info token;
- unclosed Mermaid fallback;
- lightweight tables/tasks/images/fence metadata;
- stdlib `html.parser` tag/attribute/scheme allowlist;
- exact nonce CSP and nonce matching;
- normal Back button;
- escaped same-origin author script;
- helper clears `window.opener` before Mermaid work.

Verified now under WSL Python 3.12.3:
- `python3 -m unittest -v test_plugin`: **13/13 PASS**
- full `python3 -m unittest -v`: **37/37 PASS**

#### T4 bounded Markdown parser + shared CSP

Current `plugin.py` implements the bounded stdlib-only parser, normalized URL classifier/rewrite, Mermaid placeholders, shared nonce CSP, and normal Back button. The current automated suite is green.

#### T5 dependency gate

Authoritative T5 record is PASS:
`.plan/lantern-ime-markdown-export-speckit-r2-20261006/t5-mermaid-research.md`.

#### T6 Mermaid/vendor/export implementation

Current files implement:
- exact vendored 11.17.2 bundle;
- retained third-party notice;
- lazy Mermaid loading only when placeholders exist;
- strict/offline config;
- sequential render loop with yields;
- malformed/oversize isolation;
- per-diagram PNG using SVG/viewBox dimensions, explicit dimensions, white canvas, 2x target bounded by 8192 px/side and ~32 MP, mandatory `toBlob`, and `<doc>-diagram-N.png`;
- Print / Save as PDF waiting for pending renders;
- light print CSS with clipping mitigations.

Current checks:
- `node --check static/markdown_preview.js`: PASS
- `git diff --check`: PASS
- Mermaid SHA-256: exact expected hash PASS
- immutable-file diff against `387a5f1`: PASS

### FIX / INCOMPLETE

#### T7 / M-A11 responsiveness is a binding blocker

The authoritative spec says every Mermaid-caused main-thread task, including first bundle parse/compile and render/export, must be <=100 ms. Any task above 100 ms keeps acceptance INCOMPLETE and triggers re-review of loading/pin/caps.

The previous DEV report recorded a 268 ms Mermaid-related long task.

PLAN independently re-ran the current browser harness against local Lantern on `127.0.0.1:18765` with Playwright Chromium and confirmed:

- 9 Mermaid wrappers on the combined fixture;
- 7 valid diagrams -> 7 SVGs;
- 1 malformed diagram isolated;
- 1 oversize diagram isolated;
- exact CSP present with fresh nonce;
- local requests only for preview page, local helper, and local Mermaid bundle before the deliberate CSP probe;
- deliberate same-origin `/owned.js` without nonce did not execute;
- PNG download succeeded and was non-empty;
- Print/PDF path produced a non-empty PDF;
- plain Markdown did not load Mermaid;
- page cap was 24;
- **maximum observed long task: 322 ms**;
- **long tasks over 100 ms: [322]**.

Therefore M-A11 is **INCOMPLETE / FAILING ACCEPTANCE**, not PASS.

#### T7 manual/runtime evidence still incomplete

These are not blockers that may be relabeled PASS without direct evidence:
- parent terminal responsiveness under worst-case Mermaid workload is not independently proven;
- manual visual proof that all exported PNGs are legible is incomplete;
- manual PDF proof for selectable text, visible arrowheads, readable diagrams, and no material clipping is incomplete;
- residual-risk security-owner sign-off is unavailable;
- required follow-up ticket for preview iframe sandboxing plus same-origin uploaded HTML/SVG serving does not exist.

These remain `INCOMPLETE` / `NOT_MEASURED`.

## Planning decision for DEV

Route to **DEV** because there is a reproducible in-scope acceptance failure. Do not route to TEST while M-A11 is failing.

DEV must treat the existing implementation as the starting point and must not redo T3/T4/T6 unless a fix requires a narrowly scoped change.

### Required DEV order

1. **Reproduce and attribute the >100 ms long task first.**
   - Use the existing local T7 fixture/harness under `C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7` or an equivalent retained fixture.
   - Measure first-load bundle parse/compile separately from Mermaid initialization and each individual render/export operation where possible.
   - Preserve raw timings in the DEV report.
   - Do not claim a responsiveness fix from total elapsed time; the acceptance unit is each Mermaid-caused main-thread long task.

2. **Attempt only legal remediations within this lane.**
   - The exact reviewed Mermaid 11.17.2 standalone bundle/pin remains required by this task; do not silently substitute another Mermaid version or CDN/chunk strategy.
   - Keep Mermaid unloaded on non-Mermaid pages.
   - Keep strict config, 24-page cap, sequential rendering, and yielding behavior unless a documented re-review proves a changed cap/loading contract still satisfies the authoritative requirement.
   - Do not weaken or reinterpret the <=100 ms rule.
   - Do not touch immutable terminal/backend/dependency files.

3. **If the 11.17.2 first-load parse/compile itself is >100 ms and cannot be broken into <=100 ms tasks without violating the exact bundle/runtime contract, stop implementation and report that as a hard spec/architecture blocker.**
   - Do not manufacture PASS.
   - Do not commit.
   - Return control for another PLAN decision rather than changing the reviewed pin or acceptance threshold on DEV authority.

4. **If a legal fix is found, rerun T7 acceptance completely.**
   Required evidence:
   - Lantern origin reachable while all non-Lantern origins are blocked/unavailable;
   - zero non-Lantern/runtime-extra requests;
   - seven Mermaid types all render: flowchart, sequence, class, state, ER, Gantt, pie;
   - malformed, >60000-char, and page-cap+1 cases isolate correctly;
   - exact nonce CSP behavior and same-origin nonce-less script blocking;
   - every valid type exports a non-empty PNG with correct filename and no `SecurityError`;
   - Print / Save as PDF waits for pending renders;
   - accepted Chromium evidence shows no Mermaid-caused main-thread task >100 ms;
   - parent terminal responsiveness evidence;
   - manual/visual PNG/PDF contract evidence, marking unavailable items INCOMPLETE.

5. **Then rerun Markdown-lane T8.**
   - focused plugin tests;
   - full Python suite;
   - `node --check` for changed JS;
   - `git diff --check`;
   - status/stat/scope diff;
   - exact Mermaid SHA-256;
   - immutable files byte-identical to `387a5f1`.

6. **Commit only after TEST is green.**
   - No merge to main.
   - No push before REVIEW passes.

## Non-goals

- No UniKey/IME behavior.
- No terminal persistence.
- No terminal input interception/filtering.
- No changes to `static/terminal_scm.js`, `static/vendor/xterm.js`, `lantern_terminal.py`, `lantern_ws.py`, `lan_drive.py`, or `requirements.txt`.
- No new Python package.
- No CDN or runtime network dependency.
- No acceptance-threshold waiver.
- No speculative PASS for manual/security evidence.

## Route decision

**DEV**. The implementation is mostly present and automated tests are green, but the independently reproduced 322 ms Mermaid long task violates the binding <=100 ms T7/M-A11 contract. That is an actionable implementation/architecture failure, so TEST/REVIEW are premature.

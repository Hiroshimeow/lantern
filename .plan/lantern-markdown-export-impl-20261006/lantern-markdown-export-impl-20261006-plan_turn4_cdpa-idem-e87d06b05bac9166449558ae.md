# PLAN turn 4 report

## Decision

Route **TEST** again.

TEST turn 1 found no implementation defect and deterministic checks were green, but it incorrectly concluded that fresh browser automation was unavailable. PLAN verified that Node Playwright is in fact resolvable from the workspace environment, and fresh browser acceptance can still be executed without installing anything.

Because the fresh browser path is available, the remaining browser/runtime evidence gap is actionable inside TEST. There is no reason to route DEV or PAUSE.

## Handoff reviewed

Incoming:
`.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-test_turn1_cdpa-idem-e87d06b05bac9166449558ae.md`

TEST turn 1 correctly established:

- focused plugin suite PASS: 14 tests;
- full Python suite PASS: 38 tests;
- `node --check` PASS;
- `git diff --check` PASS;
- exact Mermaid SHA-256 PASS;
- immutable terminal/backend/dependency files byte-identical to `387a5f1`;
- spec/plan/tasks all encode the corrected <=250 ms first-load / <=100 ms subsequent attributed timing contract;
- retained Chrome 154 evidence satisfies that contract;
- no actionable implementation defect was found.

TEST turn 1 also marked fresh browser rerun, parent responsiveness, and PDF visual/selectability proof INCOMPLETE.

## Important correction to TEST environment finding

TEST turn 1 stated that Node lacked Playwright/Puppeteer.

PLAN independently checked from the requested workspace:

`node -e "console.log(require.resolve('playwright'))"`

Actual result:

`C:\Users\DuongNH66\Desktop\git\node_modules\playwright\index.js`

The same path also resolves when `NODE_PATH=C:\Users\DuongNH66\Desktop\git\node_modules` is explicitly set.

Therefore fresh browser automation is available. The TEST turn-1 "browser automation unavailable" conclusion was an environment invocation error, not a real prerequisite blocker.

No dependency installation is required.

## Fresh PLAN browser spot-check

PLAN launched a fresh current-worktree Lantern instance on `127.0.0.1:18767` and ran the existing Node Playwright T7 harness after changing only the temporary harness origin.

Fresh product-page result:

- 9 Mermaid wrappers;
- 7 SVGs rendered;
- 1 malformed case isolated;
- 1 oversized case isolated;
- exact required CSP present;
- no non-Lantern requests;
- nonce-less same-origin `/owned.js` did not execute;
- PNG export succeeded:
  - `all-diagram-1.png`
  - 4538 bytes;
- print path produced PDF:
  - 75351 bytes;
- plain Markdown:
  - `mermaidLoaded=false`
  - zero Mermaid vendor requests;
- page cap:
  - 24 wrappers;
- aggregate maximum Long Task observed:
  - 230 ms.

Per the corrected contract, the aggregate 230 ms entry is not classified as failure without attribution.

## Fresh attributed timing spot-check

PLAN also reran the retained attribution harness against the fresh current-worktree server.

Three fresh contexts:

Run 1:
- bundle task: **215 ms**
- initialize: 4.2 ms
- small render task: 53 ms

Run 2:
- bundle task: **236 ms**
- initialize: 3.4 ms
- small render elapsed: 45.3 ms, no Long Task entry

Run 3:
- bundle task: **241 ms**
- initialize: 4.1 ms
- small render task: 52 ms

All three isolated first-load bundle tasks are <=250 ms.
All measured subsequent initialize/render operations are <=100 ms.

This confirms the corrected M-A11 contract is currently achievable in a fresh run on the current workspace.

The temporary PLAN server was terminated after measurement.

## Current routing state

### No DEV route

There is no reproduced implementation defect.

The current implementation already satisfies the corrected performance contract in fresh PLAN evidence, and prior deterministic test/scope checks are green.

### No PAUSE route

There is no external/manual prerequisite preventing legal work. Browser automation is locally available.

### REVIEW is premature

Independent TEST still needs to own and record the final fresh browser acceptance against the corrected contract, including any remaining manual/runtime evidence classification.

## TEST execution contract

TEST must rerun fresh browser acceptance using the available Node Playwright installation.

Use the current workspace runtime and a fresh local Lantern server. No new package installation is needed.

Required TEST evidence:

1. Reconfirm repository identity:
   - branch `feature/lantern-markdown-export-20261006`;
   - HEAD `387a5f1...`.

2. Fresh focused plugin tests.

3. Fresh full Python suite.

4. Fresh:
   - `node --check static/markdown_preview.js`;
   - `node --check static/terminal_scm.js`;
   - `git diff --check`.

5. Exact Mermaid SHA-256.

6. Immutable-file byte/diff check against `387a5f1`.

7. Fresh browser T7:
   - Lantern reachable;
   - block/abort every non-Lantern origin;
   - seven required Mermaid types render;
   - malformed isolated;
   - oversize isolated;
   - cap+1 isolated;
   - plain Markdown makes zero Mermaid vendor requests;
   - exact nonce CSP;
   - nonce-less same-origin script cannot execute;
   - zero non-Lantern runtime requests;
   - PNG export non-empty and correct filename;
   - Print / Save as PDF waits for pending renders.

8. Fresh attributed performance:
   - isolate first-load bundle parse/evaluation;
   - require <=250 ms;
   - initialize <=100 ms;
   - representative/required diagram render operations <=100 ms;
   - PNG/export governed work <=100 ms;
   - do not fail aggregate page Long Tasks without attribution.

9. Parent UI responsiveness:
   - use fresh browser evidence/manual observation where measurable;
   - record exact evidence or INCOMPLETE.

10. PDF contract:
   - if local Chrome/browser tooling can inspect/render the generated PDF, verify selectable text, visible arrowheads, readability, no material clipping;
   - otherwise keep only the unavailable pieces INCOMPLETE, do not infer PASS.

11. M-A12 governance:
   - residual-risk security-owner sign-off;
   - follow-up ticket for iframe sandboxing and same-origin uploaded HTML/SVG serving.
   - If absent, mark them explicitly as release-governance INCOMPLETE rather than code failure.

## Route after TEST

- If fresh technical acceptance is green and only M-A12 governance remains, route according to lifecycle for independent REVIEW/governance disposition; do not send back to DEV.
- If a deterministic implementation defect is reproduced, route DEV with exact evidence.
- Do not commit/push/merge from TEST.

## Route

TEST.

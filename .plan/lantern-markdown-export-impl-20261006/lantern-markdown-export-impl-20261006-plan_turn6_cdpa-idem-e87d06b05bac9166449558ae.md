# PLAN turn 6 report

Role: PLAN
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1

## Decision

Route **PAUSE**.

Block code: `MERMAID_MA11_250MS_CONTRACT_CONFLICT`.

TEST turn 5 independently measured the actual current HEAD+`defer` product path and found the exact reviewed Mermaid 11.17.2 bundle above the binding <=250 ms isolated first-load parse/evaluation threshold in 8/9 fresh accepted Playwright Chromium contexts:

- 282 ms
- 278 ms
- 258 ms
- 279 ms
- 255 ms
- 305 ms
- 346 ms
- 265 ms
- 247 ms

Range: 247-346 ms.

The structural remediation requested in PLAN turn 5 is present and correct:
- vendor script is in HEAD;
- vendor has `defer`;
- helper has `defer`;
- vendor precedes helper;
- deterministic tests and immutable-scope checks pass;
- exact reviewed Mermaid SHA-256 remains unchanged.

Therefore this is no longer an actionable script-order defect. It is a conflict between the approved hard first-load timing contract and the measured parse/evaluation cost of the immutable reviewed standalone bundle in the accepted harness.

## Incoming handoff reviewed

Incoming:
`.plan/lantern-markdown-export-impl-20261006/lantern-markdown-export-impl-20261006-test_turn5_cdpa-idem-e87d06b05bac9166449558ae.md`

TEST turn 5 established:

- Python suite: 39/39 PASS;
- `static/markdown_preview.js` syntax: PASS;
- `git diff --check`: PASS;
- immutable terminal/backend/dependency scope: PASS;
- exact Mermaid SHA-256: PASS;
- actual served product structure is the new HEAD+`defer` path;
- isolated first-load timing: FAIL, 8/9 samples >250 ms;
- no source edits by TEST;
- no commit, push, or merge.

The TEST result supersedes the earlier temporary HEAD+`defer` probe because the earlier probe was explicitly non-product evidence, while turn 5 measured the actual served current product path.

## Why PLAN is not routing DEV

A DEV retry is not justified without an authorized contract change.

The fixed first-load operation is parse/evaluation of the exact 3.57 MB Mermaid 11.17.2 standalone asset. Prior PLAN work already established that:

- extra yielding or delaying can move this task but cannot divide the browser's parse/evaluation of the exact standalone bundle into guaranteed smaller tasks;
- lowering diagram count does not affect this one-time bundle parse/evaluation task;
- loading the same file as a module did not solve the problem;
- moving evaluation to a Worker requires CSP/runtime architecture changes and Mermaid is DOM-dependent;
- replacing/chunking the Mermaid artifact, changing the pin, or adopting a materially different runtime architecture is outside the currently approved immutable dependency/runtime contract.

DEV turn 4 already implemented the remaining narrow legal loading-order remediation. Independent product-path testing now shows that remediation does not make the hard <=250 ms requirement reliable.

Sending DEV back without a changed contract would invite repeated measurement or unauthorized changes rather than a defined implementation task.

## Why PLAN is not routing TEST or REVIEW

TEST has already independently reproduced the binding failure on the current product path. More testing without a source or contract change would only replay accepted evidence.

REVIEW is premature because M-A11 remains a binding technical acceptance failure. Governance/manual evidence cannot convert a failing hard performance gate into PASS.

## Authority / precedent

This lifecycle already encountered the same class of conflict when the original M-A11 contract required every Mermaid task, including first-load bundle evaluation, to be <=100 ms.

PLAN turn 2 correctly PAUSEd because no legal implementation action could satisfy the immutable exact-bundle/runtime constraints and the timing threshold simultaneously.

PLAN turn 3 resumed only after an explicit operator decision revised the authoritative documents from the impossible <=100 ms first-load requirement to the current <=250 ms first-load requirement while retaining <=100 ms for subsequent governed work.

That <=250 ms value is therefore an operator-approved authoritative constraint. PLAN turn 6 must not silently inflate, weaken, reinterpret, or remove it based solely on new measurements.

## Current authoritative contract

The current Spec-Kit documents still require:

- exact local reviewed Mermaid 11.17.2;
- no Mermaid bundle request on non-Mermaid pages;
- local/offline loading and nonce-only script security contract;
- isolated first-load Mermaid bundle parse/evaluation <=250 ms in the accepted Chromium harness;
- every subsequent attributable Mermaid initialize/render/PNG-export main-thread task <=100 ms;
- bounded/sequential rendering and explicit yields;
- any attributed first-load result >250 ms keeps acceptance incomplete and triggers re-review.

The turn-5 8/9 failure therefore triggers exactly that re-review condition.

## External/spec-owner decision required

At least one authoritative constraint must change before legal implementation work can resume.

Acceptable resume paths include an explicitly approved decision to do one of the following:

1. **Revise the first-load performance contract.**
   Define a product-relevant and reproducible first-load criterion that accounts for runtime variance instead of silently raising the number ad hoc. The approved decision must specify the exact threshold/statistic/sample method and accepted browser/environment. Preserve the <=100 ms subsequent-operation rule unless separately changed.

2. **Permit a different Mermaid artifact/runtime/loading architecture.**
   This may include a different reviewed Mermaid artifact/version, a chunked/custom build, or another architecture demonstrated to reduce main-thread first-load work. Any such change requires renewed dependency, advisory, license, security, offline, and regression review.

3. **Permit off-main-thread/isolation architecture and corresponding CSP changes.**
   This requires explicit approval to alter the current CSP/runtime boundary and a design that still supports Mermaid's DOM-dependent rendering safely.

4. **Remove or defer Mermaid rendering from this deliverable.**
   This is a product-scope decision, not a DEV workaround.

The owner should state the selected contract change in an approved handoff and/or update the authoritative `spec.md`, `plan.md`, and `tasks.md` consistently before implementation resumes.

Do not treat a larger one-off observed number, including 346 ms, as an automatically authorized new SLA.

## Preservation

Current worktree remains intentionally dirty with the uncommitted Markdown/Mermaid implementation, authoritative planning edits, tests, assets, and lifecycle reports.

No implementation/spec file was edited by PLAN turn 6.

No commit, push, or merge is authorized while this blocker remains.

## Resume routing

After an explicit approved contract decision:

- route DEV if product/runtime/source changes are required;
- route TEST only if the approved decision changes acceptance criteria without requiring any product source change and the current implementation can be tested directly against that new contract;
- do not route REVIEW until independent technical acceptance is green.

## Route

PAUSE

# PLAN Turn 6 — accept stabilized MD-T000/T001; execute MD-T002 mapping proof + MD-T003 mature editor POC

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 6 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn9_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE DEV** for exactly two Phase-0 proof subtasks: **MD-T002 deterministic Markdown source-range ↔ ProseMirror mapping proof** and **MD-T003 isolated CodeMirror 6 merge/unified Source-editor POC**. Do not implement the actual Source replacement, Visual dirty-segment writer, canonical diff engine, watcher, or Crop in this turn.

## 1. Repository truth and accepted prior slice

Fresh G6 facts:

- `main` HEAD **`25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`**.
- `origin/main` **`b2ffd886795840f0db570b8c07a913b406e68e80`**.
- Local main is **6 commits ahead / 0 behind**.
- Latest two Phase-0 commits:
  - `247480b test(markdown): characterize source performance and fidelity`
  - `25e6c8c test(markdown): stabilize characterization settlement`
- Tracked/staged tree clean; only preserved unrelated `?? .pi/subagents.json`.
- Existing `.wt/lantern-bot` remains outside this team's ownership.
- Existing detached profiling worktree outside `.wt` was not created by this PLAN turn; do not mutate/remove unrelated worktrees in this slice.
- No PLAN source edit, service restart, CDPA mutation, reset/stash/clean, Pi/native-terminal edit, or dependency install.

REVIEW Turn 9 independently reran and accepted the two characterization harnesses:

### MD-T000 — ACCEPTED as Phase-0 evidence

Independent REVIEW:
- `tests.test_source_typing_perf_e2e`: **1 OK / exit 0 / 45.121 s**.
- 5,500 lines:
  - key-wall p95 **138.682 ms**;
  - input→paint p95 **46.9 ms**;
  - **20 Long Tasks**;
  - **99,018 added + 99,018 removed backdrop nodes**;
  - max add/remove **5,501 / 5,501**;
  - `full_backdrop_rebuild=true`;
  - **0 navigation**;
  - stable real-file/version/write quiescence.
- ~5 MB:
  - p95 **939.006 ms**;
  - input→paint p95 **109.2 ms**;
  - **50 Long Tasks**;
  - full backdrop rebuild true;
  - measured only, no invented final large-file threshold yet.
- CJK case remains **synthetic composition coverage**, not full native Windows IME acceptance.

Interpretation:
- Harness is accepted.
- Product remains **RED** at 5,500 lines against fixed `<40 ms` plus no-full-backdrop-rebuild criterion.
- Symptom is rendering/work amplification, **not real page reload/F5**.

### MD-T001 — ACCEPTED as Phase-0 exact-byte evidence

Independent REVIEW:
- `tests.test_markdown_roundtrip_corpus`: **2 OK / exit 0 / 24.018 s**.
- Stable settlement now proves actual persisted bytes/version, not transient hashes.
- Source:
  - BOM+CRLF PASS;
  - constructs PASS;
  - duplicates PASS;
  - no-final-newline PASS;
  - 30-column table PASS;
  - **mixed EOL/no-final-newline FAIL**: unrelated prefix bytes changed.
- Visual:
  - complex one-block edit **FAIL**: expected 655 bytes, actual 690, prefix+suffix changed;
  - 30-column table edit **FAIL**: expected 861 bytes, actual 1,521, prefix changed.
- Real `.md` write-through and `md_temp` accepted-snapshot semantics remained correct.

Interpretation:
- Harness/corpus is accepted.
- These product-red results are binding design inputs.
- Do **not** patch serializer or Source behavior before MD-T002/T003 evidence.

## 2. Carry-forward release gates — do not lose or block Phase 0

Unchanged:

- Spec 001 M-A8 = accepted fixture-scoped PASS.
- Spec 001 M-A9 = independent PASS on current five-page seven-type print fixture.
- Spec 001 **M-A11 remains INCOMPLETE**, not FAIL/PASS: independent FJP controlled timing could not run because host CPU never satisfied the low-load precondition. Retry later when FJP can legally settle; do not kill user processes to manufacture a sample.
- Spec 001 **M-A12 remains INCOMPLETE** pending the user's personal security-risk acknowledgement.
- Foundation 002 measured FJP technical progression remains accepted; Linux/manual/owner budget gates remain separately incomplete.
- None of those final gates justifies stalling legally actionable Spec 003 proof work.

## 3. Current mapping implementation truth before MD-T002

Current `tools/visual_markdown_entry.js::buildVerifiedBlockMap` already has a conservative top-level proof:

1. Requires input Markdown to equal current `crepe.getMarkdown()` or returns `stale`.
2. Parses current Markdown through Milkdown's current `remarkCtx`.
3. Enumerates top-level mdast blocks and top-level ProseMirror blocks.
4. Requires equal block count.
5. Reads mdast `position.start/end.offset` and line positions.
6. Re-parses each exact Markdown slice through Milkdown parser.
7. Requires one parsed child and serialized-block equivalence against the corresponding PM block.
8. Fails closed on missing position/count/slice parse/block proof.
9. Existing visual diff decorations map line-overlapping hunks only after that proof.
10. Existing debug map exposes PM range + line range, not a proven raw-byte range.

This is useful but **not yet sufficient to claim an exact dirty-segment write contract**:
- top-level order correspondence is not proof of exact nested table-cell/list-child source identity;
- a mdast JavaScript-string offset must **not be called a UTF-8 byte offset without conversion proof**;
- duplicate text must never be resolved by first/Nth textual match;
- CJK and non-BMP Unicode expose UTF-16-code-unit vs UTF-8-byte differences;
- BOM/mixed-EOL handling must remain explicit;
- source markup aliases that serialize to the same PM node may be semantically equal while having different raw source bytes.

MD-T002 therefore owns the GO/NO-GO evidence for exact source-safe mapping.

## 4. Current CodeMirror package truth before MD-T003

Repo package state:

- `package.json` declares:
  - `codemirror: ^6.0.2`;
  - Milkdown 7.22.2;
  - no `@codemirror/merge`.
- `@codemirror/merge` is **not** in `package-lock.json`.
- Local `node_modules` currently has no top-level CodeMirror install available to the PLAN probe; `npm ls ... --depth=0` returned empty.
- Current upstream registry check on 2026-10-18:
  - `codemirror` current umbrella/basic-setup package remains 6.0.2;
  - official `@codemirror/merge` current package is **6.12.2**, MIT, and documents both `MergeView` and `unifiedMergeView({original})`.
- This confirms a mature upstream exists; it **does not** authorize adding it to Lantern's product dependency graph yet.

### POC dependency boundary

PLAN authorizes **test-only, disposable** use of an exact pinned merge package for MD-T003, but not a product dependency change.

Allowed:
- first run `npm ci` if needed to materialize the already-locked existing dev dependencies;
- then, if necessary, install exact `@codemirror/merge@6.12.2` **without modifying package.json/package-lock**, e.g. test-only/no-save/no-package-lock behavior;
- verify `git diff -- package.json package-lock.json` remains empty;
- record exact package version/integrity/dependency compatibility in ignored evidence.

Not allowed in this slice:
- commit `@codemirror/merge` into `package.json` or `package-lock.json`;
- add a permanent second editor bundle;
- replace Source UI;
- add a custom diff editor because POC setup is inconvenient;
- globally install Node/browser tooling;
- change build/runtime dependencies to make the POC pass.

If exact test-only installation cannot be done without tracked dependency mutation, stop that subtask and route PLAN/REVIEW with the blocker.

## 5. DEV Turn 8 — exactly TWO coherent subtasks

# Subtask 1 — MD-T002: deterministic source-range mapping proof

**Primary new test:** `tests/test_md_source_mapping.py`.

Goal: prove which current Markdown source spans can be mapped deterministically to Milkdown/ProseMirror nodes and which must fail visibly. This is proof/design evidence, not the final write strategy.

### Required corpus

Reuse MD-T001 fixtures where possible and add only narrowly necessary cases:

- duplicate identical paragraphs;
- repeated identical headings;
- repeated identical table rows/cells;
- 30-column table;
- nested lists;
- fenced code with info string;
- raw HTML/comment/frontmatter boundaries;
- CJK;
- at least one non-BMP Unicode/emoji case;
- BOM;
- CRLF and mixed EOL;
- source markup aliases that produce equivalent semantic content, e.g. alternate emphasis/link/list notation where Milkdown normalizes representation.

Do not create a parallel broad fixture corpus if MD-T001 files can be reused.

### Required proof dimensions

For each mapped unit, evidence must distinguish:

1. **Raw source byte range** in the original file.
2. **Decoded source/string range** used by remark/Milkdown.
3. **mdast node identity/type + position**.
4. **ProseMirror node range/type**.
5. Revision/content hash the mapping belongs to.
6. Whether the proof is exact, block-only, nested-unproved, ambiguous, stale or unmapped.

### Critical offset rule

Do **not** equate `mdast.position.*.offset` with raw UTF-8 byte position by name alone.

DEV must explicitly test and document:
- what unit remark reports for ASCII;
- CJK;
- non-BMP characters;
- BOM;
- CRLF/mixed EOL.

If raw-byte mapping is needed, convert from the exact decoded substring boundary to raw bytes with a proven encoding/BOM contract and test that slicing raw bytes at the resulting range reproduces the intended source segment.

Any non-bijective/ambiguous case must return a typed fail-visible reason; no nearest text, first match, Nth occurrence or positional guess.

### Current product mapping may be minimally changed only if proof requires it

Allowed narrow production change:
- extend the existing verified mapping unit with **evidence fields** such as source decoded offsets/raw-byte-safe metadata if those are genuinely reusable for later exact mapping;
- expose those via existing `debugBlockMap()` or another test-visible narrow debug contract.

Not allowed:
- implement dirty-segment writes;
- patch Visual serialization;
- introduce a second parser;
- add regex source mapping;
- build a new canonical diff engine;
- change save/CAS semantics.

Prefer testing the existing `remarkCtx + parserCtx + PM view` path rather than reimplementing mapping logic in Python.

### Acceptance / GO-NO-GO

MD-T002 is successful even if some structures are **NO-GO**, provided the test proves and classifies them deterministically.

Required output:
- matrix by fixture/structure;
- exact mapping success cases;
- explicit unmapped/ambiguous cases;
- whether **block-level dirty-segment patching** is safe;
- whether **nested table/list inline patching** is safe;
- what cases must fall back to exact Source mode.

Do not call a block-level proof an exact cell/inline proof.

# Subtask 2 — MD-T003: isolated CodeMirror 6 merge/unified Source POC

**Primary new test:** `tests/test_md_source_merge_e2e.py`.

Goal: test a mature upstream Source editor/diff primitive before choosing implementation.

### POC modes

Evaluate at least:
- `unifiedMergeView({original})` as the preferred single-editor Source UX candidate;
- split `MergeView` only as a comparison if needed to understand missing features/performance, not as an automatic product choice.

### Required functional cases

1. add/change/delete same line and bottom-of-file;
2. visible inline/gutter hunk indication;
3. deletion widget/removed-text affordance;
4. keyboard selection, Undo/Redo;
5. CRLF input without normalization merely by loading/editing;
6. UTF-8 BOM preservation strategy;
7. CJK typing;
8. composition events with synthetic IME coverage, labelled as synthetic;
9. 500 KB document;
10. 5 MB characterization if feasible without hanging; do not invent a final pass threshold;
11. viewport behavior: DOM size/mutations should reflect virtualization rather than one node per full document line;
12. no full-document Markdown serialization merely to type one character;
13. no format normalization in untouched bytes;
14. baseline/original can update without replacing the authoritative current document.

### Performance comparison

Reuse the same conceptual metrics from MD-T000:
- input→paint / wall latency;
- Long Tasks;
- DOM node/mutation counts;
- focus/caret;
- navigation count;
- 500 KB and 5 MB behavior.

The fixed product target remains:
- at 5,500 lines, eventual product Source p95 <40 ms;
- no full-backdrop rebuild.

MD-T003 POC should establish whether the mature editor is plausibly capable of that target; it does not need to become production Source in this turn.

### Data ownership rule

POC state is not Lantern document truth.

- real `.md` remains authoritative in product;
- `md_temp` remains accepted snapshot;
- do not wire POC writes into live `/api/work/write`;
- do not modify CAS/store contracts;
- use disposable test data only.

### POC conclusion must be explicit

Return one:
- **GO — unifiedMergeView is technically suitable**, with exact limitations;
- **GO WITH CONSTRAINTS**, e.g. byte preservation requires a thin adapter;
- **NO-GO**, with evidence and a named mature alternative/review question.

Do not react to NO-GO by inventing a custom editor in the same turn.

## 6. Expected changed-file boundary

Expected tracked changes:

- `tests/test_md_source_mapping.py`;
- `tests/test_md_source_merge_e2e.py`;
- minimal additions to existing MD-T001 fixtures if strictly necessary;
- **optionally** a narrow `tools/visual_markdown_entry.js` mapping-evidence change required for MD-T002.

Potential test-only helper under `tests/` is allowed only if both new tests genuinely share it; do not create a generic framework.

Not expected / not authorized:

- `static/markdown_visual_shell.js` Source replacement;
- new `static/markdown_source_editor.js` production code;
- `lantern/live_markdown.py` behavior changes;
- new `lantern/md_diff.py`;
- `package.json` or `package-lock.json` dependency change;
- Crop code;
- Pi/native-terminal code;
- live service config;
- security/auth changes.

Evidence/logs/temporary POC artifacts belong under ignored `.plan/lantern-markdown-main-20261018/`.

## 7. Verification requirements for DEV

Before routing onward:

1. Run MD-T002 proof suite and retain detailed matrix/raw output.
2. Run MD-T003 POC suite using the exact pinned test-only package environment and record browser/runtime/package versions.
3. Run relevant existing:
   - MD-T000 characterization;
   - MD-T001 corpus;
   - `tests/test_live_markdown.py`;
   - current Markdown mapping/visual focused tests if touched.
4. Run syntax/build checks for any JS source touched.
5. `git diff --check`.
6. Verify `package.json` and `package-lock.json` unchanged.
7. Verify final tracked tree contains only the two proof subtasks and any explicitly allowed mapping evidence field.
8. Preserve `.pi/subagents.json`, `.wt/lantern-bot`, live :9999/:10099, CDPA and unrelated worktrees.

A proof test may be green while the product remains red. Reports must separate:
- harness execution success;
- mapping GO/NO-GO;
- CodeMirror POC GO/NO-GO;
- current product acceptance status.

## 8. Independent next hop after DEV

Route **REVIEW** after this bounded pair.

REVIEW must independently challenge:

- mdast offset-unit assumptions and raw-byte conversion;
- duplicate/table/CJK/BOM/mixed-EOL false mappings;
- fail-closed behavior vs guessed mapping;
- whether current top-level block proof is being overstated as nested exact proof;
- POC dependency isolation/reproducibility;
- CodeMirror official API usage and mature-upstream choice;
- viewport/performance evidence vs MD-T000 baseline;
- IME evidence labels;
- byte normalization;
- YAGNI/over-engineering;
- whether adding the actual merge package to Lantern is justified.

Only after MD-T002/T003 independent acceptance may PLAN/REVIEW choose the next product implementation ordering.

Likely dependency outcome:
- if mapping proof is sufficient and CM6 POC is GO: proceed to MD-T004/T005 or MD-T006 contract, then T007/T017 Source implementation in bounded slices;
- if exact Visual mapping is NO-GO: preserve Source as exact fallback and constrain MD-T009 accordingly;
- if CM6 POC is NO-GO: return PLAN before any custom-editor work.

## 9. Completion status

Accepted Phase-0:
- MD-T000 = characterization complete, product Source performance still FAIL.
- MD-T001 = corpus complete, current mixed-EOL Source and Visual fidelity still FAIL.

Now actionable:
- MD-T002;
- MD-T003.

Still not DONE:
- remaining 001 M-A11/M-A12;
- residual 002 owner/manual/Linux gates;
- 003 T002–T018 product/UX/Crop/release work;
- final integration/push/manual owner acceptance.

**Turn 6 route = DEV.**

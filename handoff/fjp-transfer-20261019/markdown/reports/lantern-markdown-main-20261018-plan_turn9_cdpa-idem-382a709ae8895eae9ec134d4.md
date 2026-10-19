# PLAN Turn 9 — accept MD-T006; integrate CodeMirror Source + patch-CAS performance path (MD-T007/T017)

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 9 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn15_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE DEV** for exactly two coherent product tasks: **MD-T007 Source inline diff/editor integration** + **MD-T017 Source viewport/performance/write-through integration**. MD-T006 is independently accepted. Do not bundle Visual/Preview/Crop/anchor-polish tasks beyond the minimum compatibility required to keep existing Source mode transitions working.

## 1. Fresh repository truth

- branch: `main`
- HEAD: **`44b65ff5aac4bffa015385bbed3d0ce8643484c9`**
- commit: `fix(markdown): preserve exact diff source spans`
- `origin/main`: **`b2ffd886795840f0db570b8c07a913b406e68e80`**
- local main: **14 commits ahead / 0 behind**
- tracked content diff: clean
- staged diff: clean
- preserved unrelated `?? .pi/subagents.json`
- six generated vendor paths still show status-only EOL/index noise already independently reviewed; do not reset/stash/clean/stage them merely to cosmetically alter status
- preserve `.wt/lantern-bot`, detached profiling worktree, live :9999/:10099, CDPA and Pi/native-terminal ownership

No PLAN product edit, service restart, dependency install or destructive Git operation occurred.

## 2. MD-T006 accepted

REVIEW Turn 15 independently accepted the canonical exact-source diff contract.

Fresh independent evidence:

- `tests/test_md_diff_contract.py + tests/test_markdown_draft_diff.py + tests/test_live_markdown.py`: **25 passed + 6 subtests**, exit 0
- real Edge exact five-case acceptance set: **5 tests OK**, exit 0
- mixed-EOL partial Accept/Undo exact raw bytes: PASS
- stale external hunk collision: PASS
- two-hunk partial Accept/Undo: PASS
- two-browser same-line collision: PASS
- Visual hunk Undo: PASS

Accepted architecture:

- `static/markdown_draft_diff.js` is the **single canonical browser hunk/merge owner**
- hunk metadata carries exact source UTF-16 spans while logical comparison remains EOL-insensitive
- `applyHunk()` is the single forward/reverse mutation primitive
- `merge3()` uses the same exact hunk/application contract
- view adapter no longer reconstructs source via normalized split/join
- CAS/file I/O remains in `LiveMarkdownStore`

No new diff engine is needed.

## 3. Dependency state before Source integration

Accepted enough to progress:

- MD-T000 — Source baseline/performance characterization
- MD-T001 — exact-byte fidelity corpus
- MD-T002 — source mapping GO/NO-GO
- MD-T003 — CodeMirror 6 POC GO_WITH_CONSTRAINTS
- MD-T004 — real `.md` / `md_temp` / CAS contract
- MD-T005 — external-change/polling/concurrency contract
- MD-T006 — canonical exact-source diff contract

The dependency chain now permits the first actual Source replacement slice:

- **MD-T007**
- **MD-T017**

Do not continue Phase-0 research unless integrated code produces a new concrete counterexample.

## 4. Source architecture decision

### 4.1 CodeMirror 6 is now the Source editor/viewport owner

Repo already pins:

- `codemirror 6.0.2`
- `@codemirror/theme-one-dark 6.1.3`
- CodeMirror state/view packages in the current lock
- an existing CodeMirror bundle for oversized code blocks

MD-T003 proved mature CodeMirror 6 editor/transaction/viewport viability.

Create a **separate lazy Source bundle**, e.g.:

- source entry: `tools/source_markdown_entry.js`
- output: `static/vendor/lantern-source-editor.min.js`

Reason:

- Source must not load the ~Milkdown/Crepe visual bundle merely to edit Markdown
- Preview must still load neither Source nor Visual editor
- Source and oversized code block can share the same dependency class but remain separate bundles because their UI contracts differ

Update `tools/build_markdown.mjs` and the vendor manifest accordingly.

### 4.2 Do NOT make `@codemirror/merge` a second diff truth

MD-T003 proved `unifiedMergeView` is a viable upstream UX/performance reference, but MD-T006 now owns canonical hunk semantics.

Product Source should therefore use:

- CodeMirror 6 for editing, viewport virtualization, selection, Undo/Redo and decorations
- **T006 canonical hunks** for add/mod/delete semantics and Accept/Undo identity

Render T006 hunks in CodeMirror using CodeMirror's mature view APIs:

- line/background decorations
- gutter markers
- deletion widgets/ghosts
- viewport rendering

Do not let `@codemirror/merge` independently recompute business hunks while T006 computes another set.

Therefore:

- **no `@codemirror/merge` product dependency is required by default**
- if DEV finds a concrete reason to use it, it must remain presentation-only and prove hunk identity cannot diverge; otherwise stop and route REVIEW/PLAN

This is the simplest way to satisfy both mature-upstream and FR04 one-diff-owner constraints.

## 5. Why the old whole-document write path cannot remain for Source

Current Source is a textarea:

- textarea normalizes CRLF/CR to LF
- current shell sends whole text to `/api/work/write`
- mixed-EOL source can therefore lose untouched byte spelling

MD-T001 already reproduced this product failure.

CodeMirror also normalizes logical line breaks internally.

Therefore integrated Source must **not** persist a whole CodeMirror document string after each edit.

The accepted MD-T003 POC proved the required bridge:

> normalized CodeMirror transaction coordinates -> authoritative source coordinates -> exact raw source patch

MD-T017 must turn that into the production write path.

## 6. Product persistence design for MD-T017

### 6.1 Add one patch operation inside the existing owner

Extend the existing Markdown store/API, not a new service.

Recommended boundary:

- `LiveMarkdownStore.patch(...)`
- `POST /api/work/patch`

Keep:

- real `.md` as truth
- `md_temp` unchanged until Accept/Save
- existing full-document `/api/work/write` for Visual/paged/legacy consumers where still needed
- existing CAS full-file version checks

Do not replace the store.

### 6.2 Patch request semantics

A Source flush should send only transaction changes plus the exact version it was based on.

Recommended patch item representation:

- old normalized document line number + UTF-16 column for start
- old normalized document line number + UTF-16 column for end
- inserted text
- optional expected normalized old span for fail-closed validation

Request also includes:

- path
- `expectHash`
- `baseVersion`
- ordered/non-overlapping patch list from one composed Source batch

Why line + UTF-16 column:

- CodeMirror positions are UTF-16 logical positions
- CRLF/CR/LF all still preserve logical line identity
- server already has the exact authoritative raw source
- this avoids an O(document-size) browser scan to calculate raw byte offsets on every change

Server maps each patch against the exact CAS-validated current raw document, then applies raw changes atomically.

Full-file CAS remains the concurrency authority.

### 6.3 Multi-change transaction

MD-T003 Phase 0 only proved one change.

Production must support CodeMirror transactions containing multiple changes/multi-cursor edits.

Requirements:

- collect all changes relative to the old acknowledged Source document
- map all spans against that same old document
- reject overlap/invalid ranges
- apply raw patches in descending byte/source order
- one atomic CAS write per flush batch
- no partial write if any patch validation fails

Do not serialize/send the full document just because multi-change is harder.

### 6.4 Inserted newline policy

Must be explicit now.

For inserted `\n` from CodeMirror:

- uniform CRLF source -> write CRLF
- uniform LF source -> write LF
- mixed-EOL source -> use the local source line separator at the insertion start when available; otherwise nearest preceding separator; otherwise nearest following separator; final fallback LF
- replacing a selected multi-line range uses the start-line local policy for newly inserted newlines

Untouched existing separators must remain byte-identical.

Tests must lock this policy.

### 6.5 BOM / Unicode

- BOM remains preserved outside patch spans
- UTF-8 source only, consistent with current editor/store contract
- CJK/non-BMP columns must map correctly from UTF-16 editor columns to raw UTF-8
- reject a range that would split a surrogate pair
- no whole-document normalization to obtain byte positions

## 7. Source editor instance contract

The new Source bundle should expose one compact interface to the existing shell, conceptually:

- `getMarkdown()` — normalized editor text for UI/diff display only
- `focus()`
- `destroy()`
- `setHunks(hunks, actionCallback)`
- `replaceExternalText(text)` / apply remote current source without echo
- `takePendingPatches()` or equivalent composed-change batch
- `acknowledgePatches(version)`
- selection/scroll helpers needed only for current compatibility
- debug viewport/mutation metrics for T017 acceptance

Do not expose the whole CodeMirror view as application state unless a specific adapter needs it.

### Accessibility compatibility

Preserve:

- role/textbox semantics
- accessible name **Markdown source**
- multiline editing
- keyboard focus
- Ctrl+A/C/V/Z/Y/Shift+Z
- Home/End/PageUp/PageDown and selection behavior

Prefer configuring CodeMirror content attributes rather than preserving a fake hidden textarea.

## 8. Canonical Source diff rendering (MD-T007)

Replace the current Source-only stack:

- textarea
- full backdrop
- absolute deletion list

with CodeMirror viewport decorations driven by T006 hunks.

Required visuals:

- add line = green-ish Source decoration
- modified line = yellow-ish decoration
- deletion = red/faded inline/block widget at canonical `draftStart`
- gutter marker for changed lines/hunks
- Accept/Undo controls tied to **canonical hunk index**, not CodeMirror-computed chunk identity

The existing `actionHunk(index, action)` CAS path may remain shell-owned.

The Source editor only renders and sends the action callback.

Remove or retire:

- `syncSourceBackdrop()`
- full `.md-source-diff-backdrop-content` rebuild
- bottom/right absolute deletion-row UI
- textarea-specific source replacement helper after migration is complete

Do not delete legacy code until all Source paths/tests have moved.

## 9. Source persistence flow

### Normal typing

1. CodeMirror transaction updates viewport immediately.
2. Source adapter composes pending changes relative to the last acknowledged document.
3. canonical hunks are refreshed without rebuilding full DOM.
4. existing short debounce remains bounded; do not make it longer to hide cost.
5. flush sends only patch batch to `/api/work/patch`.
6. server applies exact raw patch under CAS.
7. result updates `workHash/currentVersion`.
8. `md_temp` is untouched.

### Ctrl+S

Before Accept:

- flush pending Source patches
- wait for patch completion
- then execute existing `/api/work/save`
- Accept copies exact current real bytes into `md_temp`

### Mode switch / close / Preview

Before leaving Source:

- flush pending patches
- if success, use current acknowledged project state
- if stale/conflict, preserve local Source state and refuse destructive transition until conflict handling completes

Do not serialize the whole CodeMirror doc as a persistence shortcut.

### External/Pi update

- current polling/focus remains
- remote source update should dispatch a minimal CodeMirror transaction with echo suppression
- preserve selection/caret when safely possible
- no destroy/recreate Source editor merely to apply external content
- no full-page navigation

## 10. Concurrency and stale CAS

Preserve accepted T004/T005 behavior.

On patch 409:

- fetch current real state
- do not blind retry
- canonical merge3 may reconcile non-overlap
- overlap retains local editor text/recovery and shows visible conflict
- stale patch cannot overwrite external bytes
- no patch echo loop

If automatic non-overlap rebase cannot be implemented safely inside this slice, fail visibly and preserve local edits rather than weakening CAS.

## 11. Minimum anchor/mode compatibility — do NOT absorb MD-T011

Current `markdown_anchor_bridge.js` assumes `textarea.md-source-area`.

T007 may make only the minimum adapter change required so existing Source mode transitions do not regress:

- source capture can query the Source instance for current selection/visible line
- source restore can ask the Source instance to select/scroll to a line

Do not implement the full MD-T011 UX matrix here:

- no new cross-mode anchor heuristic
- no layout redesign
- no 390/1080/1920 polishing beyond preventing regression
- no new flash behavior
- no paged-editor redesign

Full scroll/anchor/layout acceptance remains T011/T018.

## 12. Test migration rule

Many existing tests currently query:

- `textarea.md-source-area`
- `.md-source-diff-backdrop-content`
- `.md-source-deletion`

Do not keep fake textarea/backdrop DOM only to satisfy old tests.

Update tests to assert the user contract:

- accessible Source textbox
- Source value/content via editor semantics
- selection/caret/keyboard
- line/gutter/deletion decorations
- hunk actions
- exact persisted bytes
- viewport-bounded DOM

A small stable Source debug/metrics API is allowed if it is useful for performance/anchor integration, not just a test-only imitation of textarea properties.

## 13. MD-T017 performance acceptance

Update `tests/test_source_typing_perf_e2e.py` from the old textarea/backdrop instrumentation to the integrated CodeMirror Source.

### Fixed 5,500-line gate

Binding PASS requirements:

- p95 key wall time **<40 ms**
- no full-document DOM/backdrop rebuild
- bounded viewport DOM
- no main-frame navigation
- focus preserved
- caret preserved
- real `.md` write-through settles
- `md_temp` unchanged before Accept
- no whole-document Source POST per keypress
- no hidden long debounce introduced to manufacture the result

### 900 lines

Record same metrics; must preserve functional contract and should not regress grossly from current behavior.

### 500 KB and 5 MB

Run integrated Source and the accepted Phase-0 CodeMirror reference on the same G6/Edge conditions where feasible.

Record:

- p50/p95
- input->paint
- Long Tasks
- DOM nodes/mutations
- patch request count/payload bytes
- memory if reliably attributable
- focus/caret
- write-through settlement

Do not invent a false fixed threshold if the spec did not define one.

Binding qualitative requirements:

- viewport DOM remains bounded
- no full-document DOM rebuild
- no browser/page navigation
- no multi-megabyte request body for a one-character edit
- no repeated whole-document JS serialization on each keypress
- no UI lockup attributable to Source adapter

If integrated 5 MB is materially worse than the Phase-0 reference, report measured delta and route REVIEW/PLAN rather than hiding it with debounce.

## 14. IME coverage

This slice must preserve:

- compositionstart/update/end
- synthetic CJK composition
- Undo/Redo after composition
- no duplicate persistence events during composition

But:

- physical/native Japanese/Vietnamese IME remains **NOT_MEASURED** until an actual native-input acceptance run occurs
- do not claim synthetic composition as native IME PASS

## 15. Expected tracked files

Likely product scope:

- `tools/source_markdown_entry.js` (new)
- `tools/build_markdown.mjs`
- generated `static/vendor/lantern-source-editor.min.js` + legal/manifest artifacts
- `static/markdown_visual_shell.js`
- `static/markdown_visual_shell.css`
- minimal `static/markdown_anchor_bridge.js` compatibility adaptation
- `lantern/live_markdown.py`
- `lantern/http/routes/markdown.py`
- possibly a narrow shared text-file patch helper if needed for atomic raw patching

Likely tests:

- `tests/test_source_typing_perf_e2e.py`
- `tests/test_md_mode_switch_e2e.py`
- `tests/test_live_markdown_e2e.py`
- `tests/test_live_markdown.py` / `tests/test_working_copy_http.py`
- existing MD-T001/T006 regression suites

Dependency files:

- **do not add `@codemirror/merge` by default**
- existing `codemirror 6.0.2` dependency is sufficient for the chosen one-canonical-diff architecture
- package/lock changes are only justified if a specific required CodeMirror API is not already available from the locked dependency graph

## 16. Explicit non-goals for this DEV turn

Do not implement:

- MD-T008 Visual decoration redesign
- MD-T009 Visual exact-write strategy
- MD-T010 Preview hunk redesign
- full MD-T011 anchor/layout/paged work
- MD-T018 UX polish pass
- Crop T012–T014
- file watcher/event bus
- new Python diff engine
- CRDT/OT/rope editor
- custom text editor
- Pi/native terminal
- live deployment/restart

CodeMirror already supplies the editor data structure/viewport/history. Do not build a competing rope/piece-table.

## 17. Commit/slice discipline

This DEV turn may contain at most two coherent commits/slices corresponding to:

1. **MD-T007** — CodeMirror Source view + canonical hunk decorations/actions
2. **MD-T017** — exact patch-CAS persistence + integrated performance acceptance

If T007 exposes a blocking architecture contradiction with T006, stop after T007 and route REVIEW/PLAN rather than forcing T017.

Do not continue into Visual/Crop after T017 turns green.

## 18. Required verification

At minimum run:

### Build/static
- npm clean install from current lock if build deps are absent
- `npm run build:markdown`
- JS syntax/build checks
- vendor manifest/hash check
- `git diff --check`

### Canonical contracts
- `tests/test_md_diff_contract.py`
- `tests/test_markdown_draft_diff.py`
- `tests/test_markdown_roundtrip_corpus.py`
- `tests/test_live_markdown.py`
- `tests/test_working_copy_http.py`

### Browser behavior
Focused Source cases:
- add/change/delete same line and EOF
- gutter + deletion widget
- Accept/Undo
- Ctrl+S
- keyboard selection
- Undo/Redo
- Source -> Preview -> Source
- Source -> Visual minimum compatibility
- external edit
- two tabs / stale CAS
- delete/rename safety
- BOM/CRLF/mixed-EOL/no-final-newline
- CJK/non-BMP
- synthetic composition

### Performance
- updated MD-T000/T017 harness:
  - 900
  - 5,500
  - 500 KB
  - 5 MB
- retain raw JSON/logs under team `.plan`

### Full regression
Run the relevant full native suite if practical after build. If browser suites are opt-in/skipped, report exact skip counts rather than calling them PASS.

## 19. REVIEW after DEV

Route **REVIEW**.

REVIEW must independently challenge:

### Correctness
- transaction coordinate mapping
- CRLF/mixed-EOL insertion policy
- multi-change transaction
- BOM/non-BMP
- stale CAS
- conflict recovery
- no byte normalization outside edit

### Single ownership
- T006 remains canonical hunk truth
- CodeMirror only edits/renders
- no second merge semantics hidden in Source view
- LiveMarkdownStore remains file/CAS truth

### Performance
- 5,500 p95 <40 ms
- viewport-bounded DOM
- no full-backdrop rebuild
- no whole-doc network payload per key
- no long debounce
- no editor recreation on normal external update

### UX
- one Source surface
- inline/gutter diff
- deletion visibility
- selection/keyboard/Undo
- no bottom-only legacy diff list
- no focus/caret jump

### YAGNI
- no `@codemirror/merge` dependency unless justified
- no custom editor/data structure
- no generic patch/event framework beyond Source requirements

If accepted, next dependency slice should move to **MD-T008 + MD-T009** (Visual mapping/decorations + exact-write strategy) before Preview/anchor/Crop work.

## 20. Remaining overall gates

Even after T007/T017, not DONE:

- MD-T008–T018 remaining work
- native Japanese/Vietnamese IME integrated acceptance
- Spec 001 M-A11 low-load FJP performance
- Spec 001 M-A12 personal security-owner acceptance
- Foundation Linux/manual/owner residual gates
- final T015/T016 regression/review/integration/push/manual acceptance

No PAUSE condition is met.

**Turn 9 route = DEV.**

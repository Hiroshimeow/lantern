# PLAN Turn 8 — accept MD-T004/T005; fix one canonical byte/EOL-safe diff contract before Source integration

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 8 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn14_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE DEV** for **MD-T006 only** — harden the existing canonical JS diff engine and hunk application/merge contract so unchanged source bytes/EOL spelling survive Accept/Undo/concurrent merge. Do not begin MD-T007/T017 Source integration until this contract has independent REVIEW.

## 1. Repository truth

Fresh G6 verification:

- branch: `main`
- HEAD: **`1eeba4910d1e34e4045b514849b8625c9bb3234a`**
- commit: `fix(markdown): show missing file status in preview`
- `origin/main`: **`b2ffd886795840f0db570b8c07a913b406e68e80`**
- local main: **13 commits ahead / 0 behind**
- tracked content diff: clean
- staged diff: clean
- preserved unrelated `?? .pi/subagents.json`
- six generated vendor paths still appear modified only as the already-reviewed EOL/index/status noise; REVIEW Turn 14 confirmed no content diff. Do not reset/stash/clean/stage them merely to cosmetic-clean status.
- `.wt/lantern-bot`, detached profiling worktree, live :9999/:10099, CDPA and Pi/native-terminal remain outside this slice.

No PLAN product edits or service mutations occurred.

## 2. MD-T004 / MD-T005 accepted

REVIEW Turn 14 independently closed R13-1 and accepted the shared document/external-change slice.

### MD-T004 — ACCEPTED current shared document/CAS contract

Evidence now covers:

- real project `.md` is the live editable truth;
- `md_temp` is the accepted snapshot and stays immutable until Accept/Save;
- real-file write-through after short debounce;
- exact raw Accept/Save copies current real bytes into `md_temp`;
- stale CAS prevents silent overwrite;
- edit after Accept reopens a pending diff;
- browser Undo/Redo after Accept changes real file while accepted snapshot remains fixed;
- same-path browser concurrency does not silently lose updates;
- partial Accept modifies only accepted snapshot;
- partial Undo modifies only intended real-file hunk under current version checks.

Existing owner remains `LiveMarkdownStore`; no second persistence layer is justified.

### MD-T005 — ACCEPTED current polling/focus external-change contract

Fresh REVIEW evidence supports:

- external editor write is observed;
- same-path two-client non-overlap merge is protected;
- overlap retains local recovery while external disk bytes stay authoritative;
- own write does not create write ping-pong;
- hidden page suppresses normal polling;
- focus/visibility checks refresh;
- large no-op polling does not rebuild Source backdrop;
- external delete/rename fails safely and does not recreate stale path;
- missing-file warning is now actually visible in Preview;
- restoring same path clears stale missing/conflict UI.

**No dedicated filesystem observer is justified.** Preserve the existing focus/visibility + 2.5 s visible polling mechanism unless a new reproduced gap proves otherwise.

Do not reopen watcher research during T006.

## 3. Phase/dependency state

Accepted enough to progress:

- MD-T000 — Source performance characterization
- MD-T001 — exact-byte corpus
- MD-T002 — deterministic source mapping GO/NO-GO proof
- MD-T003 — CodeMirror unified merge POC GO_WITH_CONSTRAINTS
- MD-T004 — shared real-file/md_temp/CAS semantics
- MD-T005 — external-change/echo/concurrency contract

Next blocking dependency:

- **MD-T006 [MD-FR04] one canonical diff engine**

Production Source work **MD-T007/T017 stays behind T006 independent acceptance**.

## 4. Current canonical diff truth

The repository already has one browser-side engine:

`static/markdown_draft_diff.js`

It currently owns:

- `diffLines()`
- Myers line diff
- `merge3()`
- overlap/equivalent logic

Consumers in `static/markdown_visual_shell.js` use this same engine for:

- Source diff rendering;
- Preview diff rendering;
- Visual decorations/fallback;
- human/Pi/external merge;
- per-hunk Accept/Undo selection.

Therefore **do not create `lantern/md_diff.py` merely because the task text lists it as an option**. The existing JS module is already the natural single owner and runs where current view adapters need it.

## 5. Concrete reproduced T006 defect

Current engine begins with:

- `normalize(text).replace(/\r\n?/g, '\n')`
- `linesOf() = normalize(...).split('\n')`

Current per-hunk action in `markdown_visual_shell.js` independently repeats normalization and reconstructs documents with:

- `String(text).replace(/\r\n?/g, '\n').split('\n')`
- `.join('\n')`

Current `merge3()` likewise starts from normalized lines and returns `merged.join('\n')`.

This means logical line diffing is currently also the mutation mechanism, so source EOL spelling is lost.

Fresh PLAN read-only probe on current HEAD:

- baseline: `A\r\nB\nC`
- edited: `A\r\nBX\nC`
- intended one-line change: `B -> BX`
- current diff hunk correctly identifies line 2
- current hunk reconstruction produces:
  `A\nBX\nC`
- the untouched first separator changed from CRLF to LF.

Classification:

**T006 has a real byte/EOL-preservation defect.**

This directly conflicts with:
- MD-FR04 one canonical diff contract;
- MD-FR07 unchanged-byte fidelity;
- accepted MD-T001 mixed-EOL findings;
- task requirement that hunks preserve byte/EOL.

No speculative architecture is needed: fix this exact owner/contract.

## 6. DEV Turn 14 — MD-T006 only

### Primary goal

Upgrade the existing canonical JS diff engine so it can compare lines logically **without using normalized text as the reconstructed source**.

View adapters should render the engine result; hunk mutation/merge semantics must also come from the same canonical engine rather than reimplementing line normalization in `markdown_visual_shell.js`.

### Required new test

Create:

`tests/test_md_diff_contract.py`

It should exercise the real JS module through Node/browser as appropriate.

Keep existing `tests/test_markdown_draft_diff.py`; migrate or extend only where that reduces duplication. Do not delete useful old regression coverage just to match the task filename.

## 7. Required T006 contract

### A. One hunk representation, editor-independent

A hunk must carry enough evidence to support both rendering and exact application.

At minimum distinguish:

- kind: add / del / mod
- logical line ranges for rendering
- exact baseline source span
- exact current/draft source span
- exact replacement text/source slice
- version/revision association at the caller boundary

The exact representation is DEV's choice, but the contract must not require views to reconstruct text by `split/join`.

If using JavaScript string offsets:
- name them as decoded/UTF-16 source offsets, not raw UTF-8 byte offsets;
- preserve exact original CR/LF/CRLF characters in source slices;
- leave BOM preservation to the existing server snapshot/write metadata unless a raw-byte API is genuinely needed.

Do not duplicate the MD-T002 raw-byte mapper unnecessarily.

### B. Exact hunk application helper

The canonical engine should expose an operation equivalent to:

- apply this draft hunk to accepted/base text, or
- restore this base hunk into current text

using exact source spans/slices.

`markdown_visual_shell.js::actionHunk` should call that canonical helper instead of implementing its own normalization/split/join reconstruction.

View code should not become a second diff/mutation engine.

### C. Merge3 exactness

`merge3(base, ours, theirs)` must preserve unchanged source spelling.

Required cases:

1. mixed CRLF/LF base;
2. ours changes one line, theirs another;
3. untouched separators remain byte-identical;
4. no-final-newline remains absent;
5. BOM source file remains BOM-preserving through the existing save contract;
6. CJK/non-BMP unchanged text survives;
7. identical changes are not duplicated;
8. overlap remains conflict;
9. insertions/deletions at beginning/end/trailing-newline boundaries.

The merged **string** must retain exact line separator spelling from the relevant source regions rather than normalize the entire document.

### D. Revision/CAS consistency

The diff engine itself must stay pure; it should not own file I/O or CAS.

Hunk actions must still validate the exact current/saved revisions through existing APIs before applying.

Required acceptance:
- stale baseline/current version -> action rejected;
- no partial content is written on collision;
- external newer bytes remain authoritative;
- local recovery remains recoverable.

Do not move CAS responsibility out of `LiveMarkdownStore`.

## 8. Required test matrix

Use the accepted MD-T001 fixture corpus where possible. Do not create a competing corpus.

Minimum:

### Diff shape
- add
- delete
- modify
- multiple separated hunks
- adjacent hunks
- first line / last line
- trailing newline / no final newline

### EOL / bytes
- LF
- CRLF
- mixed CRLF/LF
- BOM + CRLF
- mixed EOL + no final newline
- CJK
- non-BMP emoji

For every exact-application case:
- hash/compare unchanged prefix and suffix;
- prove only intended source span changes.

### Merge
- non-overlap ours/theirs
- identical edit
- overlap conflict
- add/add same boundary
- deletion vs modification collision

### Integration
Real disposable Edge/HTTP for:
- Accept one hunk in a mixed-EOL document;
- Undo another hunk;
- verify real file and `md_temp` raw bytes separately;
- stale external write before action -> 409/refusal, no corruption.

## 9. Important persistence nuance

`LiveMarkdownStore` ultimately writes through `save_text_cas()`.

Current text persistence:
- preserves BOM based on existing file metadata;
- preserves CRLF for a uniformly CRLF file;
- for a mixed-EOL file, it encodes the exact supplied string.

Therefore the critical T006 requirement is:

> provide `save_text_cas` with an exact source-preserving string rather than a whole document normalized to LF.

Do **not** add a second raw-byte persistence API unless tests prove the existing API cannot satisfy the contract.

## 10. Scope / YAGNI guard

Expected product files:

- `static/markdown_draft_diff.js`
- `static/markdown_visual_shell.js` only for replacing duplicate hunk reconstruction with engine calls

Expected tests:

- `tests/test_md_diff_contract.py`
- possible focused additions to:
  - `tests/test_markdown_draft_diff.py`
  - `tests/test_live_markdown_e2e.py`

Not authorized:

- new Python diff engine while JS owner remains sufficient;
- new document store;
- new observer/watcher;
- CodeMirror product integration;
- `static/markdown_source_editor.js`;
- new merge dependency;
- Crop changes;
- Pi/native-terminal changes;
- broad cleanup/refactor of Visual/Preview.

Do not combine MD-T007/T017 in this DEV turn.

## 11. Complexity requirement

The current diff engine is ~193 lines and already central.

The target is a **small extension/replacement of its text model**, not a framework.

Reject:
- generic CRDT/OT;
- event sourcing;
- custom rope/piece-table solely for T006;
- second parser;
- backend diff microservice;
- editor-specific hunk objects per view.

The whole point of T006 is to reduce competing semantics, not add abstraction layers.

## 12. Verification before route

DEV must run:

1. `tests/test_md_diff_contract.py`
2. `tests/test_markdown_draft_diff.py`
3. focused `tests/test_live_markdown.py`
4. focused mixed-EOL Accept/Undo real Edge E2E
5. two-tab/external stale hunk collision E2E
6. MD-T001 exact-byte corpus
7. JS syntax check
8. `git diff --check`

If diff/action code changes execution timing substantially, rerun relevant live Markdown E2E, but **MD-T000 is not required merely for a pure diff-span change** unless Source render/per-key behavior is altered.

Commit only MD-T006.

Then route **REVIEW** for independent:
- byte/EOL correctness;
- collision/CAS safety;
- merge conflict semantics;
- single-owner/YAGNI review;
- regression/performance;
- view-adapter duplication check.

## 13. Next dependency after T006

Only after clean REVIEW/T006 acceptance:

- next product slice may start **MD-T007 + MD-T017** as a coherent Source integration pair, because the unified CodeMirror candidate and shared data/diff contracts will then all be accepted.

That later Source slice must preserve:
- normalized-editor -> authoritative source coordinate bridge;
- real `.md` as truth;
- `md_temp` accepted snapshot;
- no full-document persistence serialization per keypress;
- indexed/efficient mapping rather than copying the POC O(n)-per-change scanner;
- p95 <40 ms at 5,500 lines;
- viewport-bounded diff DOM;
- stale CAS;
- Undo/Redo;
- IME acceptance.

Do not start it now.

## 14. Remaining external/final gates

Still incomplete and not blockers for T006:

- Spec 001 M-A11 independent low-load FJP performance;
- Spec 001 M-A12 personal security-owner acceptance;
- Foundation Linux/manual/owner residual gates;
- native Japanese/Vietnamese IME integrated acceptance;
- remaining MD-T007–T018;
- final regression/integration/push/manual acceptance.

No DONE / PAUSE condition is met.

**Turn 8 route = DEV.**

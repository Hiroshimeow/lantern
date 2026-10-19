# PLAN Turn 7 — close Phase 0; advance to shared data/external-change contract without adding speculative watcher infrastructure

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 7 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn12_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE DEV** for exactly two dependency-correct Spec-003 tasks: **MD-T004 shared .md/md_temp/CAS/Accept semantics** and **MD-T005 external-file-change detection/echo/concurrency**. Existing store/polling behavior must be characterized and reused first; do **not** add a new filesystem observer unless a reproducible acceptance gap proves the current mechanism insufficient.

## 1. Repository truth re-verified

- G6 branch: `main`.
- Current HEAD: **`0eed7ed92dd758f64fbaecd8f958b568d29c9d32`** — `test(markdown): map normalized merge coordinates`.
- `origin/main`: **`b2ffd886795840f0db570b8c07a913b406e68e80`**.
- Local main is **9 commits ahead / 0 behind**.
- Current tracked content diff is clean:
  - `git diff --quiet` = clean;
  - `git diff --cached --quiet` = clean.
- `git status` shows six generated vendor paths as modified due already-reviewed stat/EOL/index noise; REVIEW Turn 12 verified raw content equals HEAD and no content diff is staged. Do **not** reset/stash/clean/stage these paths merely to cosmetically clean status.
- Preserve unrelated `?? .pi/subagents.json`.
- Preserve `.wt/lantern-bot`, detached profiling worktree, live :9999/:10099, CDPA and Pi/native-terminal ownership.

No PLAN source change, service restart, dependency installation or destructive Git operation occurred.

## 2. Phase-0 closure disposition

### MD-T000 — ACCEPTED characterization

Current Source product remains red:
- 5,500-line p95 materially above the fixed <40 ms target;
- full-backdrop rebuild reproduced;
- many DOM node mutations / Long Tasks;
- no real page reload/navigation;
- real `.md` write-through and `md_temp` invariants preserved.

This is the binding baseline for MD-T017.

### MD-T001 — ACCEPTED exact-byte corpus

Binding findings:
- Source preserves several byte-shape cases but **fails mixed-EOL local-edit fidelity**;
- Visual complex/table edits can reserialize untouched source bytes;
- `md_temp` remains immutable until Accept/Save.

These remain product-red inputs to later T006/T009.

### MD-T002 — ACCEPTED GO/NO-GO proof

REVIEW Turn 10/12 conclusion:
- top-level block exact mapping under exact revision/source identity = **GO**;
- nested table/list/inline exact identity = **NO-GO / unproved**;
- normalized/stale/ambiguous cases fail closed;
- no regex/Nth/text-search guessing.

Do not overstate this as arbitrary inline dirty-span proof.

### MD-T003 — ACCEPTED GO_WITH_CONSTRAINTS

REVIEW Turn 12 independently reran and accepted the CodeMirror 6 unified merge POC after the normalized-coordinate bridge fix.

Proven in isolated POC:
- real CodeMirror transaction coordinates captured;
- CRLF normalization boundary mapped back to authoritative source coordinates;
- exact raw UTF-8 patch preserves BOM, EOL spelling, CJK/non-BMP and no-final-newline;
- unified merge add/change/delete/bottom hunks;
- gutter/deletion affordance;
- selection/Undo/Redo;
- CRLF load + real edit;
- 500 KB and ~4.8 MB viability characterization;
- 5,500-line isolated p95 under 40 ms;
- bounded viewport DOM / no product-style full backdrop rebuild.

Still **not** production proof:
- no Lantern CAS/write-through integration;
- no native Windows Japanese/Vietnamese IME;
- no multi-change/multi-cursor raw persistence proof;
- inserted-newline byte policy not yet formalized;
- POC raw mapper scans from document start and must **not** be copied verbatim into large-file production code.

Therefore Phase 0 (MD-T000–T003) is now complete enough to drive implementation. Do not continue polishing the POC unless a later integrated defect specifically reopens it.

## 3. Why next = MD-T004 + MD-T005

Per task graph, Source replacement MD-T007/T017 must remain behind the shared document data/change contract.

Current repo already implements much of the intended semantics:

### Existing T004-capable owner

`lantern/live_markdown.py::LiveMarkdownStore` already owns:
- real project `.md` as the live source;
- `md_temp` as accepted snapshot;
- real-file CAS write with `expect_hash`;
- accepted-baseline CAS with `base_version`;
- Ctrl+S/Accept path that copies **exact raw real bytes** into `md_temp`;
- stale/baseline_changed 409 paths;
- partial Accept into `md_temp`;
- Restore All via CAS;
- direct same-real-path Pi edits.

Existing unit/HTTP/E2E already cover large portions of this.

### Existing T005-capable behavior

The current app already observes external file changes without a backend watcher:
- `LiveMarkdownStore.get()` re-reads the real file;
- browser `refreshDiskBaseline()` fetches current work state;
- refresh occurs on visibility/focus and every **2.5 s** while visible;
- external change while editor is open is already covered in `tests/test_live_markdown_e2e.py`;
- stale concurrent writes are rejected/merged rather than blindly overwriting.

Therefore **do not assume `lantern/markdown_observer.py` is required** merely because the task text names it as a possible module. The plan itself says observer only if need is proven. A new watchdog/polling subsystem would duplicate current ownership and increase race/echo complexity unless an acceptance test proves the current 2.5 s/focus mechanism inadequate.

This is the key anti-over-engineering constraint for the next DEV turn.

## 4. DEV Turn 12 — exactly TWO coherent subtasks

# Subtask 1 — MD-T004: freeze shared document/write/accept/CAS contract

Primary intent: turn existing semantics into complete acceptance coverage and make only the smallest production correction if a real gap appears.

### Required test targets

Use/extend:
- `tests/test_live_markdown.py`;
- `tests/test_working_copy_http.py`;
- `tests/test_live_markdown_e2e.py`.

Create a new test file only if existing ownership becomes materially clearer; do not duplicate fixtures for stylistic reasons.

### Required behaviors

1. **Real `.md` write-through**
   - Source edit reaches the real project file after current short debounce;
   - no Ctrl+S required to make the real file current.

2. **`md_temp` immutability**
   - remains exactly byte-identical until Accept/Save;
   - use raw bytes/hash, not newline-normalized strings.

3. **Ctrl+S / Accept current bytes**
   - copies the current real file bytes into `md_temp`;
   - preserves BOM/CRLF/mixed EOL/no-final-newline where current byte-safe path supports them;
   - does not rewrite the real file.

4. **Edit after Accept**
   - subsequent edit changes real `.md`;
   - `md_temp` stays at the accepted version;
   - diff becomes pending again.

5. **Browser Undo/Redo after Accept**
   - prove the actual current browser semantics required by Spec 003 AC3;
   - do not fake this as a backend-only restore operation;
   - if current textarea/Visual history behaves differently, capture the concrete defect before product change.

6. **CAS stale**
   - stale `expectHash` cannot overwrite a newer VS Code/other-browser write;
   - error reason/source is correctly surfaced;
   - preserved local browser draft/recovery is demonstrated for overlap conflicts.

7. **Two tabs / same path**
   - tab A and tab B start from same revision;
   - one writes;
   - stale write from the other never silently overwrites;
   - non-overlap auto-merge behavior, if currently relied upon, must be tested explicitly and not assumed.

8. **Partial Accept/Undo**
   - partial Accept changes only `md_temp`;
   - partial Undo changes only intended real-file hunk via current CAS;
   - other hunks remain.

9. **Exact-byte regression**
   - use the already accepted MD-T001 corpus where applicable;
   - do not add a second independent byte-fidelity corpus.

### Production change boundary

Allowed only if tests reproduce a concrete T004 defect:
- narrow change inside `lantern/live_markdown.py`, Markdown HTTP route, or current frontend state contract.

Not allowed:
- new document database;
- new event bus;
- new duplicate persistence service;
- CodeMirror Source integration;
- new diff engine;
- filesystem watcher;
- Pi/native-terminal changes.

If all required T004 behaviors are already correct, **the task may close primarily as tests/contract evidence**. Do not refactor working code just to “implement” an already-present requirement.

# Subtask 2 — MD-T005: external-change + echo/concurrency contract

Primary question: **Is existing 2.5 s/focus polling sufficient for the required UX and correctness, or is a dedicated observer justified?**

### First characterize current behavior

Use real disposable Edge + real file operations.

Required cases:

1. **VS Code-like external write while Lantern is open**
   - external write to current file;
   - visible page detects it within the current defined polling/focus bound;
   - Preview/Source/Visual state reflects current real bytes;
   - `md_temp` remains unchanged.

2. **External change while local editor has unsaved/unacked text**
   - no silent overwrite;
   - non-overlap merge only if exact current merge contract proves it;
   - overlap must remain local/recoverable and show conflict.

3. **Same-path two browser tabs**
   - one tab writes;
   - other tab observes or receives stale CAS;
   - no write ping-pong.

4. **Lantern self-write echo**
   - own write must not cause duplicate product writes or a render/write loop;
   - count `/api/work/write` requests and resulting state refreshes;
   - current 2.5 s poll seeing the same hash is a no-op.

5. **Delete current file externally**
   - page fails visibly/safely;
   - does not recreate stale content automatically;
   - local recovery text is not silently discarded.

6. **Rename/move current file externally**
   - current page must fail safely or explicitly indicate stale/missing path;
   - must not recreate old path merely due poll/write timer;
   - exact desired rename-following UX is **not assumed** unless already specified.

7. **Large file**
   - verify polling state/read path does not introduce unacceptable repeated heavy parse/editor rebuild;
   - measure request frequency and no-op behavior;
   - no new final threshold invented here.

8. **Focus/visibility**
   - hidden page should not continuously perform expensive refresh;
   - focus/visibility triggers immediate state check as current code intends.

### Observer decision gate

After characterization:

**Prefer NO new observer** if current polling/focus mechanism satisfies correctness and acceptable responsiveness. In that case close MD-T005 with tests + documented bounded latency.

A dedicated `lantern/markdown_observer.py` is justified only if tests prove a material gap that cannot be fixed cheaply in the current polling/state path, such as:
- required detection latency cannot be met;
- delete/rename safety cannot be achieved reliably by current checks;
- current polling creates unacceptable repeated large-file cost;
- echo suppression needs centralized origin/revision events beyond existing hashes.

If an observer is justified:
- route back to REVIEW/PLAN with the reproduced gap and proposed ownership before building a generic watcher subsystem;
- do **not** immediately add watchdog/native watcher in this same turn.

This preserves the Spec 003 text: observer **only if approved and needed**.

## 5. Important existing implementation facts to preserve

From current source:

- `LiveMarkdownStore.write()` checks accepted baseline and real current hash before CAS.
- `save()` re-reads raw real bytes and copies them atomically to `md_temp`; it does not write the real file.
- `accept_partial()` validates both saved and current versions before changing `md_temp`.
- `discard()` refuses to overwrite newer external real-file changes.
- Browser `flushWorkingCopy()`:
  - writes real `.md`;
  - on 409 fetches current state;
  - merge3 only when possible;
  - overlap conflicts retain local draft and do not overwrite.
- `refreshDiskBaseline()` is already invoked:
  - on visibility change;
  - on window focus;
  - every 2.5 seconds while visible.
- Existing E2E already proves a basic external VS Code edit becomes visible and can be undone per hunk.

Do not duplicate these mechanisms under new module names.

## 6. Known Phase-0 constraints carried into this slice

Even though T004/T005 are store/change tasks, preserve the future Source contract:

- CodeMirror normalized positions are not raw offsets.
- Real `.md` bytes are authoritative.
- `md_temp` is accepted snapshot only.
- Mixed-EOL insertion/newline byte policy still needs an explicit production decision before integrated CodeMirror persistence.
- Do not whole-document serialize CodeMirror on every keypress.
- Do not copy the POC's O(document-size)-per-change raw coordinate scan into production.
- Native IME remains later integrated acceptance.

Do not solve these early inside T004/T005 unless a store contract genuinely requires a narrowly scoped byte primitive.

## 7. Expected tracked scope

Likely:
- `tests/test_live_markdown.py`;
- `tests/test_working_copy_http.py`;
- `tests/test_live_markdown_e2e.py`;
- at most narrow existing-owner source fixes if a failing acceptance test requires them.

Not expected:
- `lantern/markdown_observer.py` without a proven gap + re-review;
- `static/markdown_source_editor.js`;
- `@codemirror/merge` product dependency;
- `lantern/md_diff.py`;
- Crop files;
- Pi/native terminal files.

Ignored raw logs belong under `.plan/lantern-markdown-main-20261018/`.

## 8. DEV verification requirements

1. Demonstrate RED only for actual missing behavior; do not rewrite existing green semantics to force a refactor.
2. Run focused unit + HTTP tests.
3. Run relevant real Edge external-change/two-tab/delete/rename scenarios on disposable ports/root.
4. Re-run MD-T001 corpus for byte invariants if any store/write path changes.
5. Run MD-T000 only if frontend timing/render behavior changes.
6. Run `git diff --check`.
7. Preserve stat-only vendor noise as-is; do not reset/stage it.
8. Preserve `.pi/subagents.json`, live services, CDPA and unrelated worktrees.
9. Commit at most the two coherent tasks.

Then route **REVIEW** for independent correctness/YAGNI/concurrency/UX/performance assessment.

## 9. REVIEW criteria after DEV

REVIEW must specifically ask:

- Did DEV duplicate existing CAS/state owners?
- Was a watcher added without proving polling insufficiency?
- Can two tabs or VS Code cause lost update?
- Can delete/rename recreate stale content?
- Does self-write cause feedback/POST loop?
- Is `md_temp` truly unchanged until accept?
- Are raw bytes preserved on accept?
- Does Undo after Accept behave as the spec says?
- Is large-file polling behavior acceptable?
- Are error states user-visible rather than silent?
- Is implementation leaner than adding a new event system?

If T004/T005 are accepted, next dependency slice is **MD-T006 canonical diff contract**, followed by bounded Source implementation work (T007/T017) rather than more Phase-0 research.

## 10. Overall remaining status

Completed enough to progress:
- MD-T000
- MD-T001
- MD-T002
- MD-T003

Now actionable:
- MD-T004
- MD-T005

Still remaining after this pair:
- MD-T006;
- MD-T007–T018 according to dependency graph;
- Spec 001 M-A11 low-load FJP performance;
- Spec 001 M-A12 personal owner/security acknowledgement;
- Foundation residual Linux/manual/owner gates;
- final integration/manual release acceptance.

No DONE or PAUSE condition is met.

**Turn 7 route = DEV.**

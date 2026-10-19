# REVIEW Turn 13 — MD-T004 / MD-T005 shared document + external-change contract

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 13 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `98056f7a55383441518b16b4dbe816490ca6abbc`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn12_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE DEV.**

Most of MD-T004 and MD-T005 is supported by fresh independent evidence and the decision **not** to add a new filesystem observer is correct/YAGNI-safe.

However, REVIEW reproduced one concrete end-user defect in the new missing-file handling:

> When a Markdown file is externally renamed/deleted while the page is in **Preview** mode, the controller sets the correct error text, but the global status element remains `hidden`. The existing E2E passes because it calls `inner_text()` on a hidden element rather than asserting visibility.

That violates the explicit MD-T005 requirement that delete/rename fail **visibly/safely**. Fix the visibility path and strengthen the E2E oracle. No new watcher, backend owner, or broader refactor is needed.

## Repository / actual slice truth

Loaded:
- `ponytail-review`
- `verification-before-completion`

Read:
- PLAN Turn 7;
- DEV Turn 12 handoff;
- full diff from REVIEW Turn 12 accepted HEAD `0eed7ed...` through current HEAD;
- current `static/markdown_visual_shell.js`;
- `tests/test_live_markdown.py`;
- `tests/test_live_markdown_e2e.py`;
- relevant Spec 003 MD-T004/T005 contracts.

Current HEAD chain since REVIEW Turn 12:

- `18896d2 test(markdown): lock live edit and external change contracts`
- `5afb9d0 test(markdown): cover missing-file recovery race`
- `98056f7 test(markdown): freeze live document change contract`

Full slice is **not test-only** despite the final commit being test-only. Compared with `0eed7ed...`, tracked changes are:

- `static/markdown_visual_shell.js` — 19-line production UI/state correction;
- `tests/test_live_markdown.py`;
- `tests/test_live_markdown_e2e.py`.

This discrepancy matters for review scope, but the production change is narrow and belongs to the existing frontend owner. No backend watcher or persistence subsystem was added.

Git:
- `git diff HEAD~1 HEAD --check`: exit 0;
- fresh `git diff --check`: exit 0;
- six known vendor paths remain status-only EOL/index noise;
- `.pi/subagents.json` preserved.

## Fresh independent verification

### Unit / HTTP contract

Command:

`C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_live_markdown.py tests/test_working_copy_http.py`

Fresh result:

- **11 passed**
- **2.60 s**
- exit 0

This independently supports:
- real-file owner semantics;
- md_temp accepted-snapshot behavior;
- stale CAS rejection;
- partial accept/discard contracts;
- exact-byte raw Accept including BOM/mixed-EOL/no-final-newline case.

### Focused real Edge concurrency / echo / polling

Fresh command ran:

- `test_accept_then_browser_undo_redo_keeps_md_temp_at_accepted_version`
- `test_two_browser_clients_nonoverlap_changes_auto_merge_without_lost_update`
- `test_external_overlap_during_local_write_retains_local_recovery_and_real_external_bytes`
- `test_self_write_echo_and_large_noop_poll_do_not_write_or_rebuild`

Fresh result:

- **4 tests OK**
- **24.362 s**
- exit 0

These independently support:

1. one browser Undo/Redo transaction after Accept changes the real file and leaves md_temp fixed;
2. non-overlap same-path two-client edits merge without lost update;
3. overlapping external write remains authoritative on disk while local browser text is retained/recoverable;
4. self-write produces no write ping-pong;
5. no-op large-file polling does not rebuild the observed Source backdrop;
6. hidden page suppresses regular polling;
7. focus/visibility refresh detects an external large-file change without write POST.

### Existing delete/rename E2E

Fresh command:

`LANTERN_E2E=1 ... unittest -v tests.test_live_markdown_e2e.LiveMarkdownE2E.test_external_delete_and_rename_fail_visible_without_recreating_old_path`

Result:

- **1 test OK**
- **11.625 s**
- exit 0

This test proves:
- conflict state becomes true;
- old path is not recreated;
- recovery content remains in DOM/editor;
- status element contains the right text.

It does **not** prove the status is actually visible.

## Concrete defect R13-1 — Preview missing-file error is hidden

### Contract

PLAN Turn 7 / MD-T005 requires external delete/rename to:

- fail visibly/safely;
- indicate missing/stale path;
- preserve recovery text;
- not recreate the old file.

The safety/data-preservation portions are working. The **visible** portion fails in Preview mode.

### Code evidence

`static/markdown_visual_shell.js`:

- global status element: `topStatus = document.querySelector('[data-md-status]')`;
- `status()` now chooses `view.status || topStatus`;
- missing-file catch at ~489–496 sets:
  - `view.conflict = true`;
  - `view.workState = 'missing'`;
  - status text `Project .md unavailable; local recovery text retained.`.

But `restoreButtons()` at ~795 sets:

`topStatus.hidden = !view.active`

Preview mode has `view.active === false`.

The missing-file catch updates the hidden element's text but never unhides it.

### Fresh independent browser reproduction

REVIEW started a disposable Lantern server/root on an ephemeral port, opened a Markdown file in Preview, externally renamed it, waited until `window.__lanternMdVisual.state.conflict === true`, then inspected `[data-md-status]`.

Fresh result:

`{'text': 'Project .md unavailable; local recovery text retained.', 'visible': False, 'hiddenAttr': '', 'mode': 'preview'}`

So the user receives no visible missing-file warning in Preview even though the DOM contains the correct message.

### Why the committed E2E false-greens

`tests/test_live_markdown_e2e.py::test_external_delete_and_rename_fail_visible_without_recreating_old_path` does:

`status = page.locator("[data-md-status]").inner_text().lower()`

Playwright `inner_text()` can read a hidden element. The test checks text content but never checks:

- `is_visible()`;
- absence of `hidden`;
- rendered status/alert visibility.

Therefore the test name says “fail_visible” but the oracle does not prove visibility.

## Required DEV correction

One small frontend/test correction only.

### 1. Make missing-file state visible in Preview

Use the existing global status owner; do not create a new banner subsystem.

Acceptable minimal behavior:

- when `refreshDiskBaseline()` catches 404/missing:
  - expose the existing `topStatus` even in Preview;
  - keep the error text and `data-kind=error`;
- when the file becomes valid/current again or the page returns to normal Preview:
  - clear/hide the missing-state global status appropriately so a stale error does not persist forever.

Do not make all ordinary Preview info messages permanently visible merely as a side effect.

### 2. Fix the E2E oracle

For both delete and rename Preview/Source cases as applicable, assert:

- status is actually visible to the user;
- error text is present;
- old path is still not recreated;
- recovery content remains;
- no product write POST recreates the missing path.

At minimum the Preview rename case must assert `locator.is_visible() == true`.

A recovery-to-existing-file check is useful if the implementation changes hidden-state lifecycle, but do not expand this into a new watcher feature.

## Accepted portions of MD-T004

### Real .md / md_temp owner

Fresh unit and Edge evidence supports the existing owner:

- edits write through to the real `.md`;
- Accept/Ctrl+S copies current real bytes into md_temp;
- real file is not rewritten by Accept;
- subsequent edits leave md_temp fixed;
- browser Undo/Redo after Accept leaves md_temp at the accepted revision.

### CAS / concurrency

Fresh Edge evidence supports:

- overlapping writes fail closed;
- local losing draft remains recoverable;
- external/current real bytes are not silently overwritten;
- non-overlap two-client edits can merge through current merge3 path;
- partial Accept/Undo behavior remains with the existing store owner.

No alternate persistence layer is justified.

## Accepted portions of MD-T005

### No new observer — ACCEPT

The current mechanism is sufficient for the tested correctness/latency scope:

- visible polling every 2.5 s;
- focus/visibility immediate refresh;
- no polling while hidden;
- same-hash no-op;
- no duplicate write feedback;
- external current-file changes become visible within the tested bound;
- delete/write races do not recreate deleted files;
- external overlap preserves real bytes and local recovery.

A new `lantern/markdown_observer.py`, watchdog, Windows watcher, or event bus would duplicate ownership without a demonstrated need.

### Large-file polling

Fresh focused E2E passes the current characterization:

- no write POST on unchanged poll;
- no observed Source backdrop child-list rebuild on unchanged poll;
- hidden interval has no work GET;
- refocus external change refreshes within the existing test's 2 s bound.

This is sufficient for T005 characterization. It is not the final MD-T017 integrated Source benchmark.

## UX / maintainability / module separation / scaling

### UX

One material UX defect remains: missing-file Preview warning is hidden. Other conflict paths tested retain recoverable local text and expose explicit overlap messages in active editors.

### Maintainability / ownership

The 19-line production change is in the existing shell/controller and reuses IndexedDB drafts + existing status element. This is the correct owner. No new observer or storage layer.

### Scalability

Polling remains bounded by visibility and same-hash no-op behavior. Large-file no-op DOM evidence is acceptable for this task. Final Source virtualization/performance remains MD-T017.

### Mature alternatives

Native filesystem watchers are not automatically “better” here. Given current correctness and bounded UI polling, adding watchdog/ReadDirectoryChangesW/inotify abstraction now would increase cross-platform race/echo complexity without acceptance value.

## Over-engineering / YAGNI

**Ponytail review:** Lean already apart from the missing visibility fix. No abstraction should be added.

The only unnecessary complexity risk would be reacting to this UI bug by building a new notification/watcher subsystem. Use the existing `topStatus` element and current state machine.

## Reporting discrepancy

DEV Turn 12 states:

> “No production source change was required.”

That is inaccurate for the complete Turn-12 slice. Commit `18896d2` changed `static/markdown_visual_shell.js` by 19 lines.

This is not itself a product defect, but future handoffs must report the **whole slice**, not only the last commit, so REVIEW can accurately audit production impact.

## Preservation

Confirmed not changed by this slice/review:

- real `.md` source-of-truth contract;
- md_temp accepted-snapshot semantics;
- Pi/native terminal;
- CodeMirror production integration;
- canonical diff engine MD-T006;
- Crop;
- CDPA;
- live :9999/:10099;
- unrelated vendor status noise;
- `.pi/subagents.json`.

## Next DEV slice

Only fix R13-1:

1. expose the existing missing-file global status in Preview without disturbing normal Preview chrome;
2. strengthen the existing delete/rename E2E to prove actual visibility and safe recovery behavior.

Do **not** start MD-T006 in the same turn. After this fix, route REVIEW. If independently accepted, PLAN can mark MD-T004/T005 complete and advance to MD-T006.

**Required route: DEV.**

# DEV Turn 12 — MD-T004 shared document/CAS contract + MD-T005 external-change contract

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: DEV turn 12  
Workspace: `E:\git-project\lantern`  
Plan: `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-plan_turn7_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Result

Executed exactly the two PLAN Turn 7 subtasks:

1. **MD-T004** — freeze the existing real-`.md` / `md_temp` / CAS / Accept contract.
2. **MD-T005** — characterize external-file change, echo, concurrency, delete/rename, polling and visibility/focus behavior.

No production source change was required. The existing `LiveMarkdownStore` + current browser 2.5 s/focus polling path satisfied the tested contract. No filesystem watcher/observer, event bus, new persistence owner, CodeMirror product dependency, Source replacement, Pi/native-terminal change, CDPA change, or live :9999/:10099 restart was added.

Accepted commit:

- `98056f7a55383441518b16b4dbe816490ca6abbc`
- `test(markdown): freeze live document change contract`

Tracked commit scope:

- `tests/test_live_markdown_e2e.py` only.

`package.json` / `package-lock.json`: unchanged.

## MD-T004 — contract evidence

### Existing store/API behavior verified

Focused unit + HTTP command:

`C:\Users\admin\miniconda3\python.exe -m pytest -q tests\test_live_markdown.py tests\test_working_copy_http.py`

Result:

- **11 passed in 2.68 s**
- exit 0.

This covers the current owner semantics including:

- browser/store write-through changes the real project Markdown;
- `md_temp` stays unchanged until Accept/Save;
- stale CAS refuses overwrite;
- Restore All requires exact current real version;
- direct Pi/LanternBot edits use the same real path;
- pending diff does not disable versioned section editing;
- exact raw Accept copies the current real bytes to `md_temp`;
- BOM/newline preservation;
- existing mixed-EOL/no-final-newline raw Accept regression.

No backend refactor was made because these behaviors were already present.

### Real Edge T004 acceptance

Fresh focused Edge run:

- `test_edit_source_real_written_before_accept_and_temp_only_after`
- `test_two_hunks_accept_one_undo_other_and_source_inline_rows`
- `test_two_browser_clients_cannot_blind_overwrite_same_line`
- `test_accept_then_browser_undo_redo_keeps_md_temp_at_accepted_version`
- `test_two_browser_clients_nonoverlap_changes_auto_merge_without_lost_update`

Result:

- **5 tests OK**
- **12.589 s**
- log: `.plan/lantern-markdown-main-20261018/dev_turn12_t004_final.log`.

Verified browser contract:

1. Source edit reaches the real `.md` before Ctrl+S.
2. Ctrl+S changes only the accepted baseline; the real file is already current.
3. Editing again after Accept changes the real file while `md_temp` remains byte-identical to the accepted version.
4. Browser Undo after Accept writes the undone content to the real file and leaves `md_temp` unchanged.
5. Browser Redo writes the redone content to the real file and leaves `md_temp` unchanged.
6. Same-line two-tab conflict cannot silently overwrite the first client.
7. The losing overlapping client retains its local Source text.
8. Non-overlapping two-client edits auto-merge into the real file without lost update.
9. Partial Accept updates only `md_temp`; partial Undo changes only the intended real-file hunk and preserves the other hunk.

### Undo/Redo test clarification

The pre-existing test used `page.keyboard.type(" MORE")`, which creates multiple browser textarea history entries and therefore required multiple Ctrl+Z/Ctrl+Y presses. That obscured the AC3 question.

Turn 12 changed only the test interaction to one `page.keyboard.insert_text(" MORE")` transaction and now asserts:

- one Ctrl+Z restores the accepted text;
- real file follows that undo;
- accepted `md_temp` does not move;
- one Ctrl+Y reapplies the edit;
- real file follows redo;
- accepted `md_temp` still does not move.

This is acceptance-test clarification, not a product behavior change.

## MD-T005 — external-change / echo / concurrency evidence

### Existing real Edge external-change suite

Focused T005 run executed these five existing acceptance tests:

- `test_external_poll_refreshes_source_and_visual_without_accepting_temp`
- `test_external_delete_and_rename_fail_visible_without_recreating_old_path`
- `test_delete_during_pending_local_write_retains_text_and_never_recreates_file`
- `test_external_overlap_during_local_write_retains_local_recovery_and_real_external_bytes`
- `test_self_write_echo_and_large_noop_poll_do_not_write_or_rebuild`

Result:

- **5 tests OK**
- **31.817 s**.

These establish:

### External write while open

- visible Source and Visual refresh to the current real bytes;
- accepted `md_temp` remains unchanged;
- the existing polling path detects normal external change within the tested bounded window;
- Preview external-change regression separately asserts detection <5.5 s.

### Local edit + concurrent external overlap

- overlapping external/VS Code write is not overwritten;
- external real bytes remain authoritative on disk;
- browser local text remains recoverable;
- UI enters conflict with an overlapping-change message.

### Same-path browser concurrency

T004 Edge coverage additionally proves:

- overlap => fail closed/local text retained/no lost update;
- non-overlap => current merge3 path combines both edits and persists exactly once.

### Self-write echo / no ping-pong

The existing self-write test proves:

- one browser edit causes one `POST /api/work/write`;
- subsequent poll seeing the same current hash does not produce another product write;
- no write feedback loop is created.

### Delete / rename safety

The existing tests prove:

- external delete and external rename set a visible missing/unavailable conflict state;
- current Source/Preview content remains available for recovery;
- old path is not recreated by polling;
- delete racing a pending browser write still does not recreate the deleted path;
- local browser recovery text remains intact.

### Large-file no-op polling

The large-file characterization proves:

- visible polling issues bounded `GET /api/work` requests;
- unchanged poll causes **0 product write POSTs**;
- unchanged poll causes **0 observed Source backdrop child-list mutations**;
- hidden-page interval produces **0 work GETs** during the tested 2.9 s hidden interval.

Turn 12 strengthened the same test with a real external change while hidden:

1. record accepted `md_temp` bytes;
2. hide page and confirm polling is quiet;
3. modify the large real file externally;
4. unhide + dispatch focus;
5. require Source to show the external text in **<2.0 s**;
6. require no `POST /api/work/write`;
7. require server `saved` to remain the old accepted content;
8. require server `work` to be the external real content;
9. require accepted `md_temp` bytes to remain unchanged.

Fresh post-commit focused Edge run:

- VS Code external Preview/diff/per-hunk Undo;
- Accept -> edit -> browser Undo/Redo;
- self-write echo + large visible/hidden/focus poll.

Result:

- **3 tests OK**
- **23.001 s**
- log: `.plan/lantern-markdown-main-20261018/dev_turn12_post_commit_e2e.log`.

## Observer decision

**NO new observer.**

The required correctness/UX cases were satisfied by the existing ownership:

- `LiveMarkdownStore.get()` re-reads authoritative real bytes;
- CAS rejects stale writes;
- browser polling is every 2.5 s only while visible;
- visibility/focus triggers an immediate state check;
- same-hash polling is a no-op;
- delete/rename fail safely;
- echo does not cause write ping-pong;
- large-file no-op polling did not rebuild the observed Source backdrop.

A separate `lantern/markdown_observer.py` or watchdog/native watcher would duplicate existing ownership without a reproduced acceptance gap.

## Full verification

### Full native suite

Command:

`C:\Users\admin\miniconda3\python.exe -m pytest -q`

Result:

- **212 passed**
- **121 skipped**
- **47 subtests passed**
- **74.36 s**
- log: `.plan/lantern-markdown-main-20261018/dev_turn12_full_pytest.log`.

The skips include opt-in browser/POC suites and are not reported as PASS; the relevant Edge cases above were run explicitly with `LANTERN_E2E=1`.

### Syntax / Git hygiene

Actually run:

- `python -m py_compile tests/test_live_markdown_e2e.py` — exit 0.
- `git diff --check` before commit — exit 0.
- staged `git diff --cached --check` — exit 0.
- `git diff HEAD^ HEAD --check` — exit 0.
- post-commit `git diff --quiet --` — exit 0.
- post-commit `git diff --cached --quiet` — exit 0.
- Turn 12 commit changes exactly `tests/test_live_markdown_e2e.py`.
- no package/lock diff.

## Working-tree truth

HEAD:

- `98056f7a55383441518b16b4dbe816490ca6abbc`

No actual tracked-content diff remains after the commit.

The six previously reviewed generated vendor paths still appear as `M` in `git status --short` because of the existing stat/EOL/index noise:

- `static/vendor/lantern-crepe.min.css`
- `static/vendor/lantern-crepe.min.js.LEGAL.txt`
- `static/vendor/lantern-image-crop.min.js`
- `static/vendor/lantern-image-crop.min.js.LEGAL.txt`
- `static/vendor/lantern-large-block.min.js`
- `static/vendor/lantern-md-segment-worker.min.js`

They were not staged, reset, cleaned, or committed.

Preserved unrelated:

- `?? .pi/`

## Not claimed / later gates

- No dedicated filesystem watcher was built.
- No production Source/CodeMirror integration was started.
- No MD-T006 diff-contract work was started.
- No MD-T017 integrated Source benchmark was run.
- Native IME remains later integrated acceptance.
- Phase-0 current Source performance/fidelity reds remain unchanged.
- Spec 001 M-A11/M-A12 and Foundation residual gates remain outside this Turn 12 slice.

## Route

**REVIEW** — MD-T004 and MD-T005 close primarily as acceptance/contract evidence over the existing lean owners. Independent review should challenge lost-update handling, delete/rename safety, echo/no-op behavior, polling cost, UI visibility, and the decision not to add a watcher.

# DEV Turn 13 — fix missing-file status visibility in Preview

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: DEV turn 13  
Workspace: `E:\git-project\lantern`  
Incoming REVIEW: `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn13_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Scope

Executed only REVIEW R13-1:

1. expose the existing missing-file global status while the page is in Preview;
2. strengthen the existing delete/rename Edge oracle to prove the warning is rendered and that the stale missing warning disappears after same-path recovery.

No MD-T006 work was started. No new watcher, banner subsystem, persistence owner, backend API, CodeMirror integration, Pi/native-terminal code, CDPA change, or live :9999/:10099 restart was introduced.

## Commit

- `1eeba4910d1e34e4045b514849b8625c9bb3234a`
- `fix(markdown): show missing file status in preview`

Tracked commit scope:

- `static/markdown_visual_shell.js`
- `tests/test_live_markdown_e2e.py`

`package.json` / `package-lock.json`: unchanged.

## TDD evidence

### RED

The existing delete/rename E2E was first strengthened to require:

- the existing `[data-md-status]` element to be actually visible while the file is missing;
- Preview rename recovery to restore the same path, clear conflict state, and hide the stale missing warning.

Fresh RED:

- `test_external_delete_and_rename_fail_visible_without_recreating_old_path`
- rename/Preview subtest failed at:
  `AssertionError: False is not true : project .md unavailable; local recovery text retained.`
- runtime: **10.552 s**
- log:
  `.plan/lantern-markdown-main-20261018/dev_turn13_missing_visibility_red.log`

This reproduced REVIEW Turn 13 exactly: correct error text existed in DOM but remained hidden in Preview.

### Intermediate lifecycle race found

The first implementation made the missing warning visible, but a combined focused run exposed a recovery-order race:

- after the renamed file was moved back to the original path,
- `view.conflict` could become false before the status element was hidden,
- causing the recovery visibility assertion to observe stale visible error chrome.

The final implementation synchronizes status visibility immediately after `adoptSavedBaseline(state)`, before asynchronous Preview/editor rendering.

## Implementation

A single helper now owns the existing global status visibility rule:

`syncStatusVisibility()`

Rule:

- active Source/Visual editor: existing global status remains visible;
- Preview + normal/current file: global status remains hidden;
- Preview + `workState === 'missing'`: existing global status is visible.

The helper reuses `topStatus`; no new notification component was added.

### Missing path

On 404 in `refreshDiskBaseline()`:

- `view.conflict = true`;
- `view.workState = 'missing'`;
- existing local-recovery draft behavior is preserved;
- status visibility is synchronized;
- existing error text remains:
  `Project .md unavailable; local recovery text retained.`

### Recovery

The previous same-version early return now excludes `workState === 'missing'`.

This matters when a renamed file is moved back unchanged: content hashes can be exactly the same as before the rename, but the controller still must leave missing state.

On successful recovery:

- `adoptSavedBaseline(state)` clears conflict and restores normal work state;
- status visibility is synchronized immediately;
- Preview hides the stale missing warning;
- active editors keep normal status chrome;
- normal Preview informational messages are not made permanently visible.

## Fresh final verification

### Post-commit focused real Edge

Command covered:

- `test_external_delete_and_rename_fail_visible_without_recreating_old_path`
- `test_external_poll_refreshes_source_and_visual_without_accepting_temp`
- `test_delete_during_pending_local_write_retains_text_and_never_recreates_file`
- `test_external_overlap_during_local_write_retains_local_recovery_and_real_external_bytes`

Result:

- **4 tests OK**
- **22.756 s**
- exit 0.

This verifies after the final commit:

- Source delete warning remains visible;
- Preview rename warning is now actually visible;
- missing path is not recreated by polling;
- recovery content remains;
- restoring the renamed file to the same path clears conflict and hides stale Preview error status;
- ordinary external Source/Visual refresh still works;
- delete during pending write still does not recreate the path;
- overlapping external write still preserves external real bytes and local browser recovery text.

### Syntax / hygiene

Actually run:

- `node --check static\markdown_visual_shell.js` — exit 0.
- `python -m py_compile tests\test_live_markdown_e2e.py` — exit 0.
- pre-commit `git diff --check` — exit 0.
- staged `git diff --cached --check` — exit 0.
- post-commit `git diff HEAD^ HEAD --check` — exit 0.
- Turn 13 commit changes exactly the two files listed above.
- `package.json` / `package-lock.json` commit diff: empty.
- post-commit `git diff --quiet --`: exit 0.
- post-commit `git diff --cached --quiet`: exit 0.

## Working-tree truth

HEAD:

- `1eeba4910d1e34e4045b514849b8625c9bb3234a`

No actual tracked-content diff remains after the commit.

The same six previously reviewed generated vendor files still appear `M` in `git status --short` as status/index noise and were not staged or committed:

- `static/vendor/lantern-crepe.min.css`
- `static/vendor/lantern-crepe.min.js.LEGAL.txt`
- `static/vendor/lantern-image-crop.min.js`
- `static/vendor/lantern-image-crop.min.js.LEGAL.txt`
- `static/vendor/lantern-large-block.min.js`
- `static/vendor/lantern-md-segment-worker.min.js`

Preserved unrelated:

- `?? .pi/`

## Not claimed

- Full repository suite was not rerun for this one bounded UI correction.
- No new observer/watcher was added.
- No MD-T006 work was started.
- Existing later Source/CodeMirror, IME, and integrated performance gates remain outside this turn.

## Route

**REVIEW** — R13-1 is reproduced RED, fixed in the existing global status owner, and the final post-commit focused Edge regression is green.

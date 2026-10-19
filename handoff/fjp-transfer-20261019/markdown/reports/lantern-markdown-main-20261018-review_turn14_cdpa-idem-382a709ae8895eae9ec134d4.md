# REVIEW Turn 14 — missing-file Preview visibility fix

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4
Role/date: REVIEW turn 14 / 2026-10-19 JST
Workspace: G6 E:\git-project\lantern, branch main, HEAD 1eeba4910d1e34e4045b514849b8625c9bb3234a
Incoming: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn13_cdpa-idem-382a709ae8895eae9ec134d4.md

## Decision
ROUTE PLAN.

R13-1 is independently closed. Fresh Edge verification proves the missing-file warning is actually visible in Preview, same-path recovery clears conflict and hides the stale warning, and the ordinary external Preview diff path remains green. No new actionable defect was reproduced in this bounded slice.

## Review scope
Loaded ponytail-review and verification-before-completion. Inspected the DEV handoff, exact HEAD diff, current static/markdown_visual_shell.js, strengthened tests/test_live_markdown_e2e.py, and relevant MD-T005 requirements.

Repository truth from fresh inspection:
- HEAD 1eeba4910d1e34e4045b514849b8625c9bb3234a
- commit: fix(markdown): show missing file status in preview
- files: static/markdown_visual_shell.js; tests/test_live_markdown_e2e.py
- git diff HEAD~1 HEAD --check: exit 0
- package/lock unchanged
- known vendor status-only EOL/index noise preserved
- .pi/subagents.json preserved
- no watcher/backend/persistence/CodeMirror/Pi/native-terminal/live-service change

## Fresh independent Edge verification
Command:
LANTERN_E2E=1 python -m unittest -v   tests.test_live_markdown_e2e.LiveMarkdownE2E.test_external_delete_and_rename_fail_visible_without_recreating_old_path   tests.test_live_markdown_e2e.LiveMarkdownE2E.test_vscode_live_change_shows_preview_diff_and_per_hunk_undo

Result:
- 2 tests OK
- 13.189 s
- exit 0

This proves:
1. delete/rename enters missing/conflict state;
2. missing warning is actually visible, not only present in hidden DOM;
3. old path is not recreated;
4. recovery content remains available;
5. rename recovery to the same path clears conflict;
6. stale Preview warning becomes hidden after recovery;
7. ordinary external Preview diff still refreshes and remains usable.

## R13-1 implementation assessment
The new syncStatusVisibility() reuses the existing global topStatus:
- active Source/Visual: visible;
- normal Preview: hidden;
- Preview + workState=missing: visible.

404 handling still sets conflict/missing state, preserves active-editor recovery, and uses the existing error text.

The same-version early return now excludes wasMissing. This is necessary because a renamed file restored byte-identically can have the same hashes yet still needs to leave missing state.

After recovery adoptSavedBaseline(state) clears conflict/work state and syncStatusVisibility() hides the stale Preview error.

This is a narrow state-machine correction in the correct owner.

## Correctness / UX / regression
UX: the previously hidden Preview warning is now visible under fresh Edge evidence and disappears on recovery.
Data safety: no write-on-recovery, no file recreation, no persistence-semantic change.
Regression: the fresh external Preview diff test remains green.

DEV reported a larger four-test focused regression run; REVIEW did not independently rerun all four, so that remains inherited evidence.

## YAGNI / maintainability / ownership
Ponytail: Lean already. Ship.

No banner framework, watcher, event bus, backend owner, or alternate persistence path was added. Status/UI state remains in markdown_visual_shell.js; file/CAS truth remains in the existing live Markdown owner.

## Scalability / performance
The fix is constant-time UI state synchronization. It adds no poll frequency, parser work, file read, or DOM rebuild path. MD-T017 remains the integrated performance gate.

## MD-T004 / MD-T005 disposition
MD-T004: acceptable for current shared document/CAS contract evidence from prior independent review.
MD-T005: acceptable for current polling/focus contract, now including the missing visible-failure criterion. No dedicated observer is justified.

## Remaining incomplete gates
- MD-T006 canonical diff contract
- MD-T007–T018 implementation/acceptance
- integrated CodeMirror Source
- native Japanese/Vietnamese IME
- final integrated 5,500-line performance
- Spec 001 M-A11/M-A12
- Foundation Linux/manual/owner residual gates

No DONE claim.

## Tooling note
After the fresh Edge run, two additional combined syntax/status shell attempts returned remote-tool internal errors before output, so those checks are not claimed as independently rerun. The initial repository inspection did establish git diff HEAD~1 HEAD --check = 0.

## PLAN handoff
Accept R13-1 and the MD-T004/T005 slice. Advance dependency-order to MD-T006 canonical diff contract as the next bounded slice. Do not reopen watcher research without a new reproduced gap and do not bundle unrelated Source/Crop work into the same DEV turn.

Required route: PLAN.

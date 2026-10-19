# DEV turn 17 — fix PI-T004 create failure atomicity after live publication

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 16 and fixed only R16-1.

Authorized files:
- lantern/terminal.py
- tests/test_terminal_scm.py
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

Not started:
- PI-T006 writer/viewer/takeover/resize ownership;
- PI-T007 persistence/restart recovery;
- application/WS/browser/UI integration;
- supervisor/process framework;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/security changes;
- Lantern :9999 action;
- CDPA action.

## R16-1 reproduction / TDD RED

Added a deterministic regression using the real production TerminalManager with only the PTY backend faked.

Scenario:
1. create unrelated ordinary terminal successfully;
2. enable an emit callback that raises on terminal_list;
3. PiSessionRegistry.create() calls real TerminalManager.create_argv();
4. TerminalManager creates and publishes `pi:orphan` live entry;
5. terminal_list emission raises;
6. registry create propagates the exception and removes its empty native session directory.

Fresh RED result before production correction:
- `test_real_terminal_create_emit_failure_rolls_back_published_generation` FAILED;
- registry list was empty and session directory removed;
- but `pi:orphan` remained live in TerminalManager.

This reproduced REVIEW's exact orphaned-PTY failure.

## Production correction

`TerminalManager.create()` now owns rollback for exceptions that occur after it has created and published a specific TerminalEntry generation.

Implementation behavior:
- publication still occurs under the existing TerminalManager RLock;
- normal early-output / early-exit handling is unchanged;
- emission and post-publication initialization remain inside the guarded create block;
- if any exception occurs after this specific entry is published:
  - remove from `live` only if the current object is exactly that entry;
  - remove from `history` only if the current object is exactly that entry;
  - mark that entry non-running;
  - capture only that PTY for rollback;
  - re-raise the original exception;
- after releasing the lock, close only the captured just-created PTY with `graceful=False`;
- if a different/replacement generation somehow occupies the same terminal ID, identity checks prevent its removal or close.

This keeps failure atomicity inside the TerminalManager process boundary rather than asking PiSessionRegistry to guess about partially published process state.

No new public API, WS event, supervisor, retry framework, or registry process cache was added.

## Regression coverage

`tests/test_pi_sessions.py` now verifies the exact R16-1 path:
- uses real TerminalManager;
- emit callback raises on terminal_list after live publication;
- registry create raises;
- registry list remains empty;
- session directory is removed;
- `pi:orphan` is absent from live terminals;
- `pi:orphan` is absent from TerminalManager history;
- orphan PTY is closed;
- unrelated ordinary terminal remains live with its original generation.

Existing R15-1 ownership regressions remain green:
- stale expected generation cannot kill a replacement generation;
- registry stop/close do not kill replacement generations.

## Verification actually run

Fresh targeted GREEN after correction:
- `test_real_terminal_create_emit_failure_rolls_back_published_generation` -> OK
- `test_kill_if_generation_never_kills_replacement_generation` -> OK
- `test_stop_and_close_do_not_kill_replacement_generations` -> OK
- 3 tests total, OK

Fresh registry suite:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 8 tests OK in 0.031s

Fresh Terminal focused suite:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.174s

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py tests\test_terminal_scm.py tests\test_pi_sessions.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 373 tests in 57.627s
- OK (skipped=134)
- existing ResourceWarning HTTPError cleanup lines only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn17/full-unittest.err`

## Changed files

Tracked modified:
- lantern/terminal.py
- tests/test_terminal_scm.py

Untracked PI-T004 candidate files:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

No package/lock/vendor or cross-owner file is dirty.

## Final repository state

Fresh final check:
- HEAD: 1282490f8bd1443b547c3b64b0b26813270ff837
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/5
- status:
  - M lantern/terminal.py
  - M tests/test_terminal_scm.py
  - ?? lantern/pi_sessions.py
  - ?? tests/test_pi_sessions.py
- `git diff --check`: exit 0

No PI-T004 commit was made because this corrected slice still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate;
- PI-T005 COMPLETE / accepted / committed;
- PI-T004 corrected REVIEW candidate;
- PI-T006/PI-T007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- browser attach/F5/live WS behavior;
- one-writer/multi-viewer/takeover/resize ownership;
- restart persistence;
- FJP physical input;
- real POSIX runtime process execution;
- live model/goal/extensions parity;
- CPU/RSS/latency/resource acceptance.

## REVIEW request

Independent REVIEW should verify only R16-1 plus regression integrity:
- create failure after live publication removes only the exact just-created entry/generation;
- rollback removes both live/history references when they point to that exact entry;
- rollback closes only the captured just-created PTY;
- unrelated terminal remains untouched;
- original exception still propagates;
- previous generation-safe stop/close fix remains intact;
- no PI-T006/007 or process-supervisor scope creep;
- full/focused regression evidence is valid.

Route: REVIEW.
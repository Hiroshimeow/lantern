# DEV turn 20 — fix PI-T006 attach-stop and writer/takeover races

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 19 and fixed only R19-1 and R19-2.

Changed only:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Did not start:
- PI-T007 persistence/restart/F5 lifecycle;
- application/runtime wiring;
- browser/UI work;
- session-create RPC;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/auth policy changes;
- Lantern :9999 actions;
- CDPA changes.

## R19-1 — attach could succeed after PTY exit

### TDD RED

Added deterministic regression:
`test_attach_rejects_exit_between_registry_lookup_and_replay_capture`.

Test behavior:
1. registry `get()` returns the session as running;
2. immediately triggers the real fake-PTY exit callback before attach enters replay capture;
3. then performs `pi_session_attach`.

Fresh RED before production fix:
- expected stale-session ValueError was not raised;
- attach incorrectly succeeded.

### Fix

Inside the existing terminal-locked attach boundary, after `replay_view()`, attach now rejects when either:
- PTY generation mismatches; or
- `meta.running` is false.

This preserves the existing atomic replay+route registration boundary and adds no lifecycle/restart behavior.

Fresh GREEN:
- targeted stopped-attach regression passed.

Acceptance assertions now prove:
- no Pi route attachment is installed;
- no writer ownership is granted;
- no `pi_session_replay` is sent;
- registry/TerminalManager authoritative status is stopped.

## R19-2 — stale old writer could actuate after takeover

### TDD RED

Added deterministic concurrency regression:
`test_takeover_between_writer_authorization_and_actuation_blocks_input_and_resize`.

The test wraps the real TerminalManager RLock with a signaling proxy so it can force this schedule without mocking the ownership contract:
1. old writer request starts;
2. old implementation validates writer/epoch before TerminalManager actuation lock;
3. request blocks at TerminalManager lock;
4. viewer performs real takeover and advances ownership epoch;
5. request resumes.

To isolate the exact writer-authorization/actuation boundary, the test supplies the already-known registry session view while exercising real WebSocketHub + dispatch + TerminalManager actuation.

Fresh RED before production fix:
- old writer completed without exception;
- stale request crossed the takeover boundary.

The same deterministic boundary is exercised for canonical resize ownership.

### Fix

Writer input/key/resize now use one consistent nested lock order:
1. acquire `TerminalManager.lock`;
2. re-resolve/revalidate registry session under that terminal boundary;
3. acquire `WebSocketHub.lock`;
4. validate attached session, PTY generation, ownership epoch, and current writer while hub lock remains held;
5. revalidate authoritative TerminalManager generation/running state;
6. perform input/key/resize before releasing the ownership boundary.

Lock order is therefore consistently:
`TerminalManager lock -> WebSocketHub lock`.

No inverse `hub -> terminal` nested path was added.

`WebSocketHub._pi_writer_target_locked()` contains the lock-free validation body for callers already holding hub lock. Existing `pi_writer_target()` remains a wrapper for ordinary direct use/tests.

Socket sends remain outside hub lock.

Fresh GREEN:
- stale input is rejected with `pi_session_stale_owner` semantics;
- stale resize is rejected;
- PTY receives zero stale bytes;
- PTY receives zero stale resize calls.

## Verification actually run

Targeted race GREEN:
- `test_attach_rejects_exit_between_registry_lookup_and_replay_capture` -> OK
- `test_takeover_between_writer_authorization_and_actuation_blocks_input_and_resize` -> OK
- 2 tests total, OK

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 9 tests OK in 0.044s

PI-T004 registry regression:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 9 tests OK in 0.030s

Ordinary Terminal regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.517s

LAN multi-peer/performance regression:
- `uv run python -m unittest -q tests.test_lan_multi_perf`
- 19 tests OK in 3.419s

Terminal auth regression:
- `uv run python -m unittest -q tests.test_terminal_auth`
- 12 tests OK in 2.722s

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.510s

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.010s
- no paid AI prompt

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0

## Full-suite evidence

First fresh full-suite run:
- `uv run python -m unittest discover -s tests -q`
- Ran 383 tests in 57.427s
- FAILED: 1 failure in `test_pi_working_copy_guard.PiWorkingCopyGuardTests.test_guard_blocks_saved_and_private_paths_but_allows_active_working_path`
- failure was outside this slice and concerned a working-copy guard expectation.

Per verification rules this first run is recorded as a real failure, not hidden.

Immediate isolated rerun of that exact failing test:
- 1 test OK in 0.169s.

One fresh full-suite rerun:
- Ran 383 tests in 62.474s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn20/full-unittest-rerun.err`

## Current repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate only:
  - M lantern/ws.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0

No PI-T006 commit was made because corrected source still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE structured spawn;
- PI-T004 COMPLETE / committed;
- PI-T006 corrected REVIEW candidate;
- PI-T007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- runtime application injection;
- real browser F5/live reconnect;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX runtime process execution;
- model/goal/custom-extension parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify only R19-1/R19-2 plus regression integrity:
- stopped PTY is rejected inside the terminal-locked attach replay boundary;
- no replay/route/writer is created after that race;
- writer authorization and PTY actuation are atomic relative to takeover/detach;
- lock order is consistently TerminalManager -> WebSocketHub;
- no hub -> terminal nested path/deadlock was introduced;
- input/key/resize all share the same atomic ownership check;
- stale input/resize cannot cross takeover;
- socket sends remain outside hub lock;
- ordinary Terminal, auth, replay, LAN and native Pi regressions remain intact;
- no PI-T007/UI/Markdown/LAN-policy scope drift.

Route: REVIEW.
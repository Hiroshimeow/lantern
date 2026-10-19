# DEV turn 16 — fix PI-T004 generation-atomic stop/close ownership race

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 15 and fixed only finding R15-1.

Authorized narrow production edit used:
- lantern/terminal.py — add generation-atomic conditional kill primitive
- lantern/pi_sessions.py — route registry stop/close through that primitive
- tests/test_terminal_scm.py — deterministic TerminalManager replacement-generation regression
- tests/test_pi_sessions.py — registry caller-boundary stale-generation regressions

No PI-T006 writer/viewer/takeover/resize policy, WS events, application wiring, restart persistence, browser/UI work, Markdown implementation, LAN/security work, Lantern :9999 action, or CDPA action was started.

## R15-1 reproduction / TDD RED

Before production changes, fresh focused run showed:
- TerminalManager had no kill_if_generation -> AttributeError;
- registry stop test expected conditional generation kill but observed none;
- registry close test expected conditional generation kills but observed none.

Result:
- 3 focused tests
- 1 error + 2 failures
- exact missing ownership primitive/caller usage reproduced.

## Production correction

### TerminalManager

Added `TerminalManager.kill_if_generation(term_id, expected_generation, *, emit_exit=True) -> bool`.

Semantics:
- acquires TerminalManager's existing lock;
- checks the currently live terminal by ID and exact generation under that same lock;
- if missing or generation-mismatched: returns false and does nothing;
- if matched: atomically removes that exact live entry and marks it non-running before releasing the lock;
- then closes only that captured PTY, emits the existing terminal_exit/list events, and returns true.

This makes generation check + destructive ownership decision atomic inside the TerminalManager owner. It does not add any writer/viewer/session policy.

### PiSessionRegistry

`stop()` and `close()` no longer:
- call `_terminal_status()`;
- then separately call ID-only `TerminalManager.kill()`.

They now call only:
- `terminal.kill_if_generation(session["terminalId"], session["generation"])`

Therefore a replacement PTY generation under the same terminal ID is not killable by stale registry ownership metadata.

## Deterministic regressions

`tests/test_terminal_scm.py` adds a real TerminalManager regression:
1. create terminal ID -> generation A;
2. kill A;
3. recreate same terminal ID -> generation B;
4. call kill_if_generation(ID, A);
5. assert false;
6. assert generation B remains live and its PTY remains open;
7. call kill_if_generation(ID, B);
8. assert true and B closes.

`tests/test_pi_sessions.py` updates the fake TerminalManager contract to expose `kill_if_generation()` and adds caller-boundary coverage:
- normal stop/close use conditional generation kills only;
- repeated stop stays idempotent;
- registry first observes both owned generations as running;
- terminal records are then deterministically replaced with new generations before requested stop/close;
- registry stop/close issue stale expected-generation requests;
- both replacement generations remain running;
- no ID-only kill occurs.

This directly locks the REVIEW race at both the owner primitive and registry caller boundary.

## Verification actually run

Fresh focused GREEN after implementation:
- `test_kill_if_generation_never_kills_replacement_generation` -> OK
- registry normal stop/close ownership tests -> OK
- 3 tests total, OK

Fresh final focused ownership run:
- TerminalManager replacement-generation regression -> OK
- PiSessionRegistry replacement-generation stop/close regression -> OK
- 2 tests, OK

Registry suite:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 7 tests OK in 0.028s

Terminal focused suite:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.169s

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py tests\test_terminal_scm.py tests\test_pi_sessions.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 372 tests in 49.833s
- OK (skipped=134)
- existing ResourceWarning HTTPError cleanup lines only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn16/full-unittest.err`

## Changed files

Tracked modified:
- lantern/terminal.py
- tests/test_terminal_scm.py

Untracked PI-T004 candidate files from turn 15, now corrected:
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

No PI-T004 commit was made because the corrected slice still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T002 COMPLETE narrow native PTY proof;
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE / committed;
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

Independent REVIEW should verify only R15-1 plus regression integrity:
- generation check and destructive removal are atomic under TerminalManager lock;
- stale expected generation cannot kill a replacement PTY;
- stop and close both use the same conditional primitive;
- registry no longer performs TOCTOU list-then-ID-kill ownership;
- ordinary Terminal kill behavior is unchanged;
- no PI-T006/session-writer scope creep;
- full/focused tests prove the acceptance boundary.

Route: REVIEW.
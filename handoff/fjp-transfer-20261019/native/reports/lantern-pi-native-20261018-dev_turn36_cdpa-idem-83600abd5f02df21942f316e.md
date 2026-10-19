# DEV turn 36 — recover PI-T006 contract source and complete R34-1 replay-before-live ordering

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Continued only the turn-35 recovery plus R34-1.

Directly affected source:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Existing unaccepted PI-T006 candidate files preserved:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

No PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA changes.

## Test-source recovery

The turn-35 accidental truncation was recovered from the preserved pre-truncation Python 3.14 bytecode artifact:
`.plan/lantern-pi-native-20261018/evidence-turn35/test_pi_ws_contract_pretruncate.cpython-314.pyc`.

Recovery method:
- used ejfkdev pycdc 0.6.0, which supports Python 3.14 bytecode;
- restored the full PI-T006 test class structure and all prior 27 test method names;
- repaired decompiler artifacts that were mechanically wrong, including tuple-created Peer instances and inverted/filter-comprehension conditions;
- replaced the older R31 concurrency test with the intended stronger-serialization version required by current R34-1 locking semantics;
- restored the new replay-before-live-output regression.

Current recovered test file:
- 27 test methods;
- 1,068 lines;
- 54,011 bytes;
- `py_compile`: PASS;
- `tests.test_pi_ws_contract`: 27 tests PASS.

Important provenance note:
- this is semantic source recovery from the preserved pre-truncation bytecode, not byte-for-byte recovery of the original untracked source text;
- independent REVIEW should inspect the recovered test source for readability/maintainability and acceptance fidelity before PI-T006 is accepted.

## R34-1 correction

`pi_session_attach` now keeps the existing `TerminalManager.lock` continuously across:
- exact replay snapshot capture;
- route publication via `hub.pi_attach()`;
- bounded replay preparation;
- final `_send_pi_replay()` queue enqueue.

This establishes one TerminalManager-owned replay/live-output serialization boundary:
- PTY output cannot append/emit between replay capture and replay enqueue;
- once replay is queued and the lock releases, later live output receives the next seq and routes after replay;
- no separate replay store, pending-output queue, or duplicate transcript owner was introduced.

Attach rollback remains token/session/generation-safe.

Ownership notice sends remain outside the TerminalManager boundary after successful replay enqueue.

Hub lock is not held during `peer.send()`.

## R34-1 regression

`test_attach_replay_precedes_live_output_after_capture_without_gap_or_duplicate` deterministically:
1. blocks attach on the peer replay/notice ordering lock after route publication;
2. starts PTY output after the replay snapshot boundary;
3. resumes attach;
4. asserts observed order is exactly replay then live output;
5. asserts replay seq 0 followed by output seq 1;
6. asserts `LIVE-AFTER-CAPTURE` appears exactly once.

Fresh RED was captured in turn 35:
- actual order before correction: `[pi_session_output, pi_session_replay]`.

Fresh GREEN this turn:
- full PI-T006 contract includes this test and passes 27/27.

## Exit ordering adjustment

The older turn-34 post-publication exit race test assumed PTY exit could complete before replay while attach was blocked only on the peer notice lock.

Under the stronger R34-1 TerminalManager serialization that assumption is intentionally no longer valid.

The regression now proves:
- PTY exit blocks on TerminalManager ownership while replay initialization is pending;
- replay is queued first;
- exit completes afterward;
- peer observes `pi_session_replay` before `pi_session_exit`;
- registry ends stopped.

This preserves the R33 safety property while matching the stronger no-gap R34 boundary.

## Verification actually run

Recovered PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- Ran 27 tests in 1.597s
- OK.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- Ran 40 tests in 6.578s
- OK.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- Ran 23 tests in 4.359s
- OK.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Enabled PI replay proof:
- first attempt: 1 error because upstream Node serializer probe exceeded its built-in 15s timeout;
- immediate fresh retry: `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- Ran 7 tests in 22.392s
- OK.
- The timeout was not claimed as PASS; both attempts are reported.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- Ran 1 test in 9.998s
- OK.
- no paid AI prompt.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 401 tests in 61.055s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn36/full-unittest.err`.

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0.

No PI-T006 commit was made because the recovered source and R34-1 correction still require independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE;
- PI-T004 COMPLETE / committed;
- PI-T006 corrected REVIEW candidate;
- PI-T007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- runtime application injection;
- real browser F5/live reconnect;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX runtime;
- model/goal/extensions parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify:
- R34-1 replay snapshot -> route publication -> replay enqueue is one TerminalManager-owned boundary;
- live Pi output cannot queue before initial replay and post-snapshot output is neither lost nor duplicated;
- replay seq/live seq remain continuous;
- PTY exit still orders after replay when replay wins TerminalManager ownership, and stale attach still fails when exit wins first;
- hub lock is not held across peer send;
- R29-R33 ownership/rollback/session isolation protections remain intact;
- recovered `tests/test_pi_ws_contract.py` is maintainable and semantically faithful despite bytecode-source recovery provenance;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
# DEV turn 34 — block stale attach replay after PTY exit

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 33 and fixed only R33-1.

Turn-34 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R33-1 TDD RED

Added deterministic regression:
`test_attach_rejects_exit_after_publish_before_replay_enqueue`.

Sequence:
1. connect peer and hold its existing per-peer Pi ownership/replay ordering lock;
2. wrap `hub.pi_attach()` only to signal once route publication/writer assignment has completed;
3. start `pi_session_attach` in a thread;
4. verify peer is published as route writer;
5. make the exact Pi PTY exit with code 9 while replay is still blocked before enqueue;
6. verify registry reports stopped;
7. release replay ordering lock;
8. require attach to raise stale-session, send no replay, token-safely roll back peer/writer state, and leave session stopped.

Fresh RED before production correction:
- attach returned without error;
- assertion failed because `errors` remained empty;
- this reproduced successful stale replay after the PTY had already exited.

## Production correction

`WebSocketHub._send_pi_replay()` now receives the authoritative `TerminalManager` plus the exact terminalId for the session.

While holding the existing per-peer Pi replay/ownership ordering lock it now:
1. rechecks terminal authorization;
2. acquires `TerminalManager.lock`;
3. reads `replay_view(terminal_id)`;
4. requires exact replay generation and `running == True`;
5. while TerminalManager lock is still held, revalidates hub attachment/session/generation under `hub.lock` and refreshes current role/ownership epoch;
6. releases hub lock;
7. enqueues the replay through existing `peer.send()` while TerminalManager lock remains held;
8. releases TerminalManager lock after enqueue.

This makes PTY liveness and replay enqueue one TerminalManager ownership boundary:
- if PTY exit wins the lock first, replay sees stopped state and fails;
- if replay wins first, its queue-only send is enqueued before exit can transition that generation to stopped.

Hub lock is still not held during `peer.send()`.

Existing attach exception handling then invokes the already accepted token/session/generation-safe rollback from turn 33 and re-raises the stale-session error.

No process restart, auto-promotion, third liveness owner, persistence, retry queue, or UI state was added.

## Preserving R31 replay/ownership ordering proof

The prior R31 regression originally paused by blocking inside the fake peer `send()` method.

Because the corrected R33 implementation intentionally keeps `TerminalManager.lock` through the queue-only replay enqueue, that artificial blocking point would also hold the PTY owner lock and prevent the concurrent takeover used by that test.

The test was therefore updated without weakening its acceptance condition:
- it now holds the same per-peer `_pi_notice_lock` before attach;
- waits until `pi_attach` has published A;
- lets B attach and take over while A replay is blocked before its final liveness/authority validation;
- releases A's per-peer lock;
- requires A's replay/ownership epochs to remain monotonic and final role/epoch to equal authoritative route state.

This continues to prove the intended R31 race while respecting the new final TerminalManager liveness boundary.

## Verification actually run

Targeted R33-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_attach_rejects_exit_after_publish_before_replay_enqueue`
- 1 test FAILED before production correction;
- failure: expected one stale attach error, observed zero.

Initial targeted GREEN run exposed the old R31 test's artificial blocking point holding TerminalManager lock; it failed because B became writer after A's fake send timeout. The R31 regression synchronization was moved to the per-peer replay ordering lock as described above.

Fresh targeted GREEN after correction:
- post-publication PTY-exit attach rejection -> OK
- attach replay/takeover ownership monotonicity -> OK
- auth-revocation rollback -> OK
- 3 tests OK in 0.018s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 26 tests OK in 1.657s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.737s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.179s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.822s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.057s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 400 tests in 62.307s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn34/full-unittest.err`

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current uncommitted PI-T006 candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0.

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
- real POSIX runtime;
- model/goal/extensions parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify R33-1 specifically:
- final replay enqueue is covered by exact TerminalManager terminalId/generation/running validation;
- PTY exit before that boundary makes attach fail stale and triggers exact-token rollback;
- replay cannot be queued after a matching stopped generation has already won TerminalManager ownership;
- if replay wins first, queue enqueue completes before exit can mark that generation stopped;
- hub lock is not held during peer send;
- per-peer replay/ownership ordering remains monotonic after takeover;
- turn-33 auth rollback and stale-token protections remain intact;
- Pi process is never restarted or auto-promoted;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
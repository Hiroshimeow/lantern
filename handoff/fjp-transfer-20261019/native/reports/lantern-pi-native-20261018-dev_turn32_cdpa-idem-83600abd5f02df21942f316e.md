# DEV turn 32 — serialize attach replay with ownership notices

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 31 and fixed only R31-1.

Turn-32 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R31-1 TDD RED

Added deterministic regression:
`test_attach_replay_cannot_regress_ownership_after_takeover`.

Sequence:
1. peer A begins `pi_session_attach` and becomes writer at epoch E1;
2. A's `pi_session_replay` send is paused before enqueue;
3. peer B attaches as viewer;
4. B performs takeover, advancing authoritative route to E2 and becoming writer;
5. A receives the fresh E2 ownership notice;
6. A's old attach replay resumes;
7. test requires A's ownership-bearing messages to remain monotonic and final role/epoch to equal authoritative route state.

Fresh RED before production correction:
- A observed ownership-bearing epochs `[2, 1]`;
- assertion failed because stale replay E1 followed fresh ownership E2.

## Production correction

Added narrow `WebSocketHub._send_pi_replay(peer, payload)` using the same per-peer `_pi_notice_lock` introduced for ownership notices.

Replay send flow:
1. acquire/get the peer's ownership-message lock;
2. check existing terminal authorization;
3. under `hub.lock`, revalidate:
   - route exists for replay sessionId;
   - route generation matches replay generation;
   - `pi_peer_session[peer]` still points to that session;
   - peer is still attached to route;
4. while still under hub lock, refresh replay `role` from current route writer and refresh `ownershipEpoch` from current route epoch;
5. release hub lock;
6. enqueue replay through existing `peer.send()` while still holding only the per-peer ownership-message lock.

`pi_session_attach` now sends its bounded replay through `_send_pi_replay()` instead of direct `peer.send()`.

This gives replay and ownership notices one per-peer enqueue ordering boundary.

Ordering guarantee:
- if replay obtains the peer lock first, replay queues before later takeover notice;
- if takeover notice obtains it first, replay waits and then refreshes to the current role/epoch before enqueue;
- replay cannot enqueue stale E1 after ownership E2 for the same peer.

Disconnect/detach or generation/session substitution before replay enqueue is rejected by the same route/session validation instead of sending stale authority.

Hub lock is not held during queue/socket send.

No new queue, retry system, persistence, UI state, or PI-T007 behavior was added.

## Verification actually run

Targeted R31-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_attach_replay_cannot_regress_ownership_after_takeover`
- 1 test FAILED before production correction;
- exact observed epochs: `[2, 1]` vs monotonic `[1, 2]`.

Targeted GREEN after correction:
- `test_attach_replay_cannot_regress_ownership_after_takeover` -> OK
- `test_ownership_notice_enqueue_order_cannot_regress_after_validation` -> OK
- `test_failed_writer_notice_cannot_regress_remaining_peer_epoch` -> OK
- 3 tests OK in 0.529s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 22 tests OK in 1.580s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 5.539s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.402s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 13.011s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.012s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 396 tests in 62.514s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn32/full-unittest.err`

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

Independent REVIEW should verify R31-1 specifically:
- `pi_session_replay` and `pi_session_ownership` share the same per-peer ordering lock;
- replay role/epoch are refreshed from authoritative route at enqueue time;
- stale E1 replay cannot follow E2 ownership notice;
- replay cannot send after detach/session switch/generation mismatch;
- hub lock is released before `peer.send()`;
- R29/R30 ownership-notice failure and enqueue ordering protections remain intact;
- prior PI-T006 attach/takeover/input/output/replay/generic-control isolation remains intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
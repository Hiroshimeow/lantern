# DEV turn 38 — prevent stale in-flight Pi output/exit after session switch

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 36 and fixed only R36-1.

Turn-38 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate work in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA changes.

## R36-1 TDD RED

Added deterministic output race regression:
`test_inflight_old_session_output_cannot_enqueue_after_switch_replay`.

Scenario:
1. switching peer and staying peer attach session A;
2. A output broadcast snapshots both peers while switching peer is still attached to A;
3. switching peer's old-event delivery is paused before enqueue;
4. switching peer completes attach to session B and receives B replay;
5. old A delivery resumes;
6. test requires no A output to be queued to the switched peer after B replay;
7. staying A peer must still receive A output exactly once.

Added matching exit race regression:
`test_inflight_old_session_exit_cannot_enqueue_after_switch_replay`.

It uses the same race shape for `pi_session_exit` and requires:
- switched peer receives no old A exit after B replay;
- staying A peer still receives exit code 23 exactly once.

Fresh RED before production correction:
- both regressions failed;
- switched peer received stale A output/exit after completing B attach.

## Production correction

Pi output/exit delivery in `WebSocketHub.broadcast()` now uses the existing per-peer `_pi_notice_lock` already shared by replay and ownership notices.

For each snapshotted Pi payload, immediately before queue enqueue it now:
1. obtains the peer's Pi ordering lock;
2. rechecks terminal authorization;
3. under `hub.lock`, verifies:
   - route still exists for payload sessionId;
   - route generation still equals payload generation;
   - `pi_peer_session[peer]` still equals payload sessionId;
   - peer is still in that route's peer set;
4. releases `hub.lock`;
5. calls existing `peer.send(pi_payload)` while still holding only the per-peer ordering lock.

This closes the stale-snapshot TOCTOU window:
- if old A event gets the peer ordering lock first, it queues before the B replay/switch initialization;
- if B replay/switch gets the lock first, the later A event revalidation sees the peer attached to B and drops the stale payload;
- no hub lock is held during `peer.send()`;
- other A peers remain unaffected.

The same narrow path covers both `pi_session_output` and `pi_session_exit`.

No new queue, transcript store, session model, retry mechanism, persistence, or protocol field was added.

## Verification actually run

Targeted RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_inflight_old_session_output_cannot_enqueue_after_switch_replay tests.test_pi_ws_contract.PiWsContractTests.test_inflight_old_session_exit_cannot_enqueue_after_switch_replay`
- both tests FAILED before production correction with stale old-session delivery.

Targeted GREEN:
- same command after correction;
- 2 tests OK in 0.014s.

Full PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- Ran 31 tests in 1.595s
- OK.

Related Pi/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- Ran 40 tests in 5.805s
- OK.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- Ran 23 tests in 4.487s
- OK.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Enabled PI replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- Ran 7 tests in 12.472s
- OK.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- Ran 1 test in 10.103s
- OK.
- no paid AI prompt.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 405 tests in 49.486s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn38/full-unittest.err`.

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- PI-T006 contract now has 31 test methods;
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

Independent REVIEW should verify R36-1 specifically:
- snapshotted A output/exit cannot queue after the peer has completed B replay/switch;
- per-peer ordering lock covers replay, ownership notices, and Pi output/exit enqueue ordering;
- authoritative session/generation/peer membership is revalidated immediately before enqueue;
- hub lock is not held over `peer.send()`;
- output already queued before switch may remain FIFO before B replay;
- staying A peers still receive A output/exit exactly once;
- B traffic remains unaffected;
- R22-R35 session/rollback/replay/ownership protections remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
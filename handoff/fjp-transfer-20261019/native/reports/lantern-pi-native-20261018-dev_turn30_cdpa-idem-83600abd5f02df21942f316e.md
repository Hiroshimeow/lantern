# DEV turn 30 — prevent stale ownership notices after failed writer delivery

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 29 and fixed only R29-1.

Turn-30 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R29-1 TDD RED

Added deterministic regression:
`test_failed_writer_notice_cannot_regress_remaining_peer_epoch`.

Sequence:
1. attach A as writer and B as viewer;
2. perform the real `_pi_takeover_locked()` so B becomes writer and ownership epoch advances to E2;
3. order the resulting valid notice batch deterministically with B's writer notice first and A's viewer notice second;
4. force B's ownership-notice send to raise `OSError("dead peer")`;
5. let existing `remove(B)` detach the failed writer and advance authoritative route epoch to E3;
6. verify A's final ownership state is E3 and no older E2 notice is delivered afterward.

Fresh RED before production correction:
- route epoch advanced to 3;
- A received the fresh epoch-3 viewer notice from failed-writer removal;
- then A received the stale epoch-2 notice from the original batch;
- assertion failed: final ownershipEpoch was 2 instead of 3.

## Production correction

`WebSocketHub._send_pi_notices()` now validates each queued ownership notice against current authoritative transient route state immediately before socket send.

Under the existing hub lock it requires:
- route still exists for payload sessionId;
- route generation still equals payload generation;
- route epoch still equals payload ownershipEpoch;
- target peer is still attached to that route.

If any condition is stale, the notice is skipped.

Socket send remains outside the hub lock.

On send failure the existing behavior remains:
- `remove(peer)` detaches the peer;
- writer removal increments ownership epoch;
- fresh current notices are generated/sent to remaining peers;
- Pi process is not killed;
- peer close is attempted.

After that synchronous removal path returns, the original stale notice batch continues iterating, but its older epoch no longer passes the authoritative route check. This prevents E3 -> E2 regression without adding retries, queues, persistence, or background delivery.

Viewer-only send failure behavior is preserved: if removal does not change ownership epoch, same-epoch notices for remaining attached peers remain eligible.

## Verification actually run

Targeted R29-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_failed_writer_notice_cannot_regress_remaining_peer_epoch`
- 1 test FAILED before production correction;
- exact mismatch: final ownershipEpoch 2 != authoritative route epoch 3.

Targeted R29-1 GREEN:
- same command after correction;
- 1 test OK in 0.009s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 20 tests OK in 1.095s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 7.613s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.607s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 14.158s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.016s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 394 tests in 58.399s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn30/full-unittest.err`

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

Independent REVIEW should verify R29-1 specifically:
- failed current-writer notice removal may advance ownership epoch but no older notice is delivered afterward;
- each ownership notice is suppressed if its session/generation/epoch/peer attachment is no longer authoritative;
- socket sends remain outside hub lock;
- writer removal still does not kill Pi and does not auto-promote a viewer;
- viewer-only failure does not unnecessarily invalidate same-epoch notices;
- prior attach/takeover/detach/input/output/replay/generic-control protections remain intact;
- no retries/background queues/persistence/UI/PI-T007 scope was added.

Route: REVIEW.
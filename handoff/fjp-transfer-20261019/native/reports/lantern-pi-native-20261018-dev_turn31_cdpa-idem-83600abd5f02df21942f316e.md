# DEV turn 31 — serialize ownership notice enqueue per peer

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 30 and fixed only R30-1.

Turn-31 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R30-1 TDD RED

Added deterministic regression:
`test_ownership_notice_enqueue_order_cannot_regress_after_validation`.

Sequence:
1. A starts as writer and B as viewer;
2. B takes over, producing epoch E2 notices;
3. the E2 notice for A enters `_send_pi_notices()` and passes authoritative route validation;
4. A's send path pauses before appending/enqueueing E2;
5. while E2 is paused, A takes over again, advancing the route to E3;
6. a fresh E3 notice is delivered;
7. the old E2 path resumes;
8. test requires A's observed ownership epochs to remain monotonic and end at E3.

Fresh RED before production correction:
- observed final ownership epoch was E2 after E3 had already been delivered;
- exact assertion failed: final epoch 2 != authoritative epoch 3.

## Production correction

### Per-peer ownership-notice enqueue serialization

`WebSocketPeer` now owns one `_pi_notice_lock` dedicated to ownership-notice enqueue ordering.

`WebSocketHub._send_pi_notices()` uses a per-peer notice lock so, for one peer:
- route validation;
- role/epoch eligibility;
- and `peer.send(payload)` enqueue

are serialized against other ownership-notice deliveries for that same peer.

For lightweight test peers that are not real `WebSocketPeer` instances, the hub lazily installs the same lock under `hub.lock`, ensuring concurrent send paths share one lock rather than racing lock creation.

### Ordering behavior

While holding the per-peer notice lock, the hub:
1. checks terminal authorization;
2. revalidates current route under `hub.lock`;
3. requires exact session generation;
4. requires exact current ownership epoch;
5. requires the peer still be attached;
6. releases `hub.lock`;
7. calls `peer.send(payload)` while still holding only the per-peer notice lock.

For production `WebSocketPeer`, `send()` serializes JSON and enqueues into its existing outbound queue; actual socket writes remain on the existing writer thread.

Therefore hub lock is never held over socket I/O.

Once an old E2 notice owns the peer notice lock, a concurrent E3 delivery waits. If E3 changes authoritative route state before E2 validates, E2 is skipped. If E2 has already validated and reaches enqueue first, E3 necessarily queues afterward. The reverse E3-then-E2 ordering is no longer possible for the same peer.

### Failed-peer behavior preserved

Existing R29-1 logic remains:
- if a notice send raises, `remove(peer)` performs detach cleanup;
- writer removal increments ownership epoch;
- remaining peers receive fresh authoritative notices;
- older batch entries are revalidated and skipped when stale;
- Pi process is not killed;
- no viewer auto-promotion occurs.

No retries, background notification framework, persisted ownership, new send queue, or UI logic was added.

## Verification actually run

Targeted R30-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_ownership_notice_enqueue_order_cannot_regress_after_validation`
- 1 test FAILED before production correction;
- exact mismatch: final epoch 2 != epoch 3.

Targeted race GREEN after correction:
- `test_ownership_notice_enqueue_order_cannot_regress_after_validation` -> OK
- `test_failed_writer_notice_cannot_regress_remaining_peer_epoch` -> OK
- 2 tests OK in 0.527s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 21 tests OK in 1.551s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.482s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 2.689s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.607s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.009s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 395 tests in 64.381s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn31/full-unittest.err`

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

Independent REVIEW should verify R30-1 specifically:
- ownership notice validation+enqueue is serialized per peer;
- E2 cannot be enqueued after E3 for the same peer/session;
- hub lock is not held during `peer.send()`;
- production `WebSocketPeer.send()` remains queue-only and socket writes stay on writer thread;
- failed-writer stale-batch protection from R29 remains intact;
- writer removal still does not kill Pi and does not auto-promote a viewer;
- no retries/background queue/persistence/UI/PI-T007 scope was added;
- prior PI-T006 session/input/output/replay/generic-control protections remain intact.

Route: REVIEW.
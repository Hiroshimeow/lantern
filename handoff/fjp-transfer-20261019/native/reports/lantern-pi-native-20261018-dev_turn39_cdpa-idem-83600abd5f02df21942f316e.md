# DEV turn 39 — serialize explicit detach/remove with Pi enqueue ordering

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 37 and fixed only R37-1.

Turn-39 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing PI-T006 candidate files:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

No PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA changes.

## R37-1 TDD RED

Added deterministic explicit-detach race:
`test_inflight_output_cannot_enqueue_after_explicit_detach_completes`.

The regression uses a test-only observed per-peer ordering lock and proves the required serialization boundary:
1. A Pi output reaches queue-enqueue send while holding the per-peer Pi ordering lock;
2. send is paused before append/enqueue;
3. another thread performs `pi_session_detach`;
4. before the fix, detach completed immediately instead of waiting;
5. after send resumes the stale output could therefore queue after detach completion.

Fresh RED result:
- expected first ordering event `waiter`;
- observed `done`;
- explicit detach was outside the Pi enqueue ordering boundary.

Added matching disconnect/remove race:
`test_inflight_exit_cannot_enqueue_after_disconnect_remove_completes`.

Fresh RED result:
- expected `waiter`;
- observed `done`;
- `hub.remove(peer)` likewise mutated attachment state outside the per-peer enqueue ordering boundary.

Both tests also preserve required behavior:
- staying A peer still receives the event;
- explicit detach leaves Pi process running;
- writer removal increments epoch / clears writer;
- no auto-promotion.

## Production correction

### Shared per-peer ordering boundary

`WebSocketPeer._pi_notice_lock` is now a `threading.RLock` rather than a plain Lock.

Reason:
- Pi replay, ownership notices, output/exit already serialize on this per-peer lock;
- `remove(peer)` can be invoked synchronously from a failed send while that same ordering boundary is already held;
- reentrancy avoids self-deadlock while preserving one queue-order boundary.

Lazy ordering locks installed for non-WebSocketPeer/test peers are also `RLock`.

### Explicit detach

`WebSocketHub.pi_detach()` now:
1. acquires/creates the peer's existing Pi ordering lock;
2. under that lock acquires `hub.lock`;
3. validates the peer is still attached to the requested session;
4. performs `_pi_detach_locked()`;
5. releases `hub.lock` and the per-peer ordering lock;
6. caller sends any ownership notices afterward through existing notice machinery.

Guarantee:
- if output/exit enqueue owns the per-peer lock first, it queues before detach can complete;
- if detach owns it first, later output/exit revalidation sees the peer detached and drops the stale payload.

### Disconnect/remove

`WebSocketHub.remove(peer)` now uses the same per-peer ordering lock around:
- peer-set removal;
- generic subscription clearing;
- Pi detach mutation.

Ownership notices remain sent after the mutation lock boundary through `_send_pi_notices()`.

Pi process is never killed by detach/remove.

No new queue, replay store, process owner, retry framework, persistence, or protocol field was added.

## Source-recovery incident during this turn

While applying the R37-1 lock change, I incorrectly used the bounded textual result of `read_text_file` as if it were the complete `lantern/ws.py` content and rewrote the file, truncating it.

This was a DEV-created source-loss incident inside an owned candidate file.

Immediate preservation/recovery actions:
- saved the truncated copy at `.plan/lantern-pi-native-20261018/evidence-turn39/ws_truncated_turn39.py`;
- saved HEAD baseline at `.plan/lantern-pi-native-20261018/evidence-turn39/ws_head.py`;
- reconstructed the PI-T006 `lantern/ws.py` candidate from:
  - HEAD baseline;
  - prior DEV/REVIEW contracts for turns 19-38;
  - the current 33-test PI-T006 contract;
  - the already accepted TerminalManager/PiSessionRegistry seams;
- retained the reconstruction dispatch fragment at `.plan/lantern-pi-native-20261018/evidence-turn39/dispatch_fragment.py`.

This is semantic reconstruction, not byte-for-byte restoration of the pre-incident uncommitted source.

Because of that provenance, independent REVIEW must inspect module separation/locking and source maintainability even though all fresh tests below pass.

## Verification actually run

R37-1 RED before production correction:
- `test_inflight_output_cannot_enqueue_after_explicit_detach_completes`: FAIL (`done` instead of `waiter`);
- `test_inflight_exit_cannot_enqueue_after_disconnect_remove_completes`: FAIL (`done` instead of `waiter`).

After reconstruction + correction:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- Ran 33 tests in 1.682s
- OK.

Fresh targeted R37-1 GREEN:
- explicit detach race -> OK;
- disconnect/remove race -> OK;
- 2 tests OK in 0.014s.

Related Pi/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- Ran 40 tests in 6.192s
- OK.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- Ran 23 tests in 4.436s
- OK.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0;
- `git diff --check` -> exit 0.

Enabled PI replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- Ran 7 tests in 13.363s
- OK.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- Ran 1 test in 10.058s
- OK.
- no paid AI prompt.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 407 tests in 58.645s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn39/full-unittest.err`.

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
- `lantern/ws.py`: 1037 lines after semantic reconstruction;
- PI-T006 contract: 33 test methods;
- `git diff --check`: exit 0.

No PI-T006 commit was made because reconstructed/corrected source still requires independent REVIEW/TEST acceptance.

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
- PI-T006 corrected REVIEW candidate, but not accepted;
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

Independent REVIEW should verify R37-1 and reconstruction provenance:
- explicit `pi_session_detach` participates in the same per-peer Pi ordering boundary as replay/ownership/output/exit enqueue;
- `hub.remove(peer)` participates in that same ordering boundary;
- RLock reentrancy is necessary/safe for synchronous send-failure -> remove cleanup and introduces no lock inversion;
- hub lock is not held over peer send/socket I/O;
- staying peers continue receiving output/exit exactly once;
- writer detach/remove retains epoch/no-auto-promotion semantics;
- Pi processes are not killed by detach/remove;
- reconstructed `lantern/ws.py` remains maintainable and semantically faithful to R19-R36 behavior;
- R22-R36 generic-control, replay, session switch, generation, rollback, ownership and stale-delivery protections remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
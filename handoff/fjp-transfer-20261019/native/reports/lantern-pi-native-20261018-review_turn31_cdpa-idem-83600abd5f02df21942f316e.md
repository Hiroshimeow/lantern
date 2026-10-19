# REVIEW turn 31 — R30 enqueue ordering fixed; attach replay can still regress ownership state

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 31  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R30-1 is resolved for ownership-change notices by per-peer enqueue serialization. A separate ownership-ordering defect remains: `pi_session_replay` also carries role/ownershipEpoch but bypasses that serialization, so takeover can enqueue a newer ownership notice before an older attach replay is finally enqueued.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 31 handoff.
- REVIEW turn 30 R30-1.
- PLAN turn 11 attach replay / writer-viewer / ownership-epoch contract.
- Current PI-T006 candidate source and tests.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate paths remain exactly:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## R30-1 — ownership notice validation-to-enqueue race: RESOLVED

`WebSocketPeer` now owns a dedicated per-peer `_pi_notice_lock`.

`WebSocketHub._send_pi_notices()` uses that lock across:
1. current route/generation/epoch/attachment validation;
2. the queue-only `peer.send(payload)` call.

For lightweight test peers, the hub installs the same lock under `hub.lock` so concurrent notice senders share one lock.

The hub lock itself is released before `peer.send()`.

Production `WebSocketPeer.send()` remains queue-only:
- JSON/frame encoding;
- bounded queue accounting;
- enqueue into the existing per-peer send queue.

Actual socket write/flush remains on the existing writer thread.

Therefore ownership notices for one peer cannot enqueue E3 and then E2: one notice owns the per-peer notice lock through its enqueue boundary.

## Fresh R30 verification

Fresh targeted tests:

- `test_ownership_notice_enqueue_order_cannot_regress_after_validation`: PASS.
- `test_failed_writer_notice_cannot_regress_remaining_peer_epoch`: PASS.

Result:
- 2 tests;
- all OK;
- 0.518 s;
- exit 0.

Fresh full PI-T006 contract:
- 21 tests;
- all OK;
- 1.587 s;
- exit 0.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 11.262 s;
- exit 0.

Syntax:
- `py_compile` for Terminal/Pi registry/WS and affected tests: exit 0.

`git diff --check`:
- exit 0.

The original turn-30 enqueue race is therefore independently reproduced as fixed.

## Finding R31-1 — attach replay can arrive after a newer ownership notice with stale role/epoch

**Location:** `lantern/ws.py`, `pi_session_attach` dispatch path after `hub.pi_attach()`.

**PLAN invariant**

PLAN turn 11 requires attach replay to return:
- current role writer/viewer;
- current transient ownership epoch.

It also requires all peers to receive ownership-change notifications sufficient to keep role/epoch current.

`pi_session_replay` is therefore an ownership-bearing message, not just terminal bytes.

**Current flow**
1. peer A attaches;
2. under terminal/hub coordination, A becomes writer at epoch E1;
3. dispatch leaves the ownership lock boundary;
4. before A's `pi_session_replay(role=writer, epoch=E1)` is enqueued, peer B attaches and performs takeover;
5. route advances to E2, B becomes writer, A becomes viewer;
6. B's takeover path sends A `pi_session_ownership(role=viewer, epoch=E2)` through the new serialized notice lock;
7. A's original attach dispatch then enqueues the stale replay carrying `role=writer, epoch=E1`.

Because attach replay does not use the per-peer ownership notice lock and does not refresh role/epoch before enqueue, the client can observe E2 then E1.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

Sequence:
1. A begins `pi_session_attach`.
2. A's `pi_session_replay` send is paused after A is already registered as writer but before the replay is appended/enqueued.
3. B attaches as viewer.
4. B performs `pi_session_takeover`.
5. A receives the fresh ownership notification.
6. A's old attach replay is released.

Fresh result:

`route_epoch 2 writer_is_b True`

A's observed ownership-bearing states:

`[('pi_session_ownership', 2, 'viewer'), ('pi_session_replay', 1, 'writer')]`

The proof assertion failed:

`stale attach replay regressed A ownership state after takeover`.

This is a concrete client-visible ownership regression.

## Why this is material

The new R30 serialization guarantees monotonic ordering only for `pi_session_ownership` notifications.

But `pi_session_replay` carries the same authority fields and is the attach response that initializes client writer/viewer state.

A stale replay after a newer ownership notification can leave the client believing:
- it is writer when it is actually viewer;
- ownership epoch is E1 when server authority is E2.

Server-side stale-owner checks still protect PTY input, but the public server contract is internally contradictory.

## Required correction

Serialize ownership-bearing attach replay with the same per-peer ownership ordering boundary.

Minimal acceptable shape:
1. use the same per-peer Pi notice lock before enqueueing `pi_session_replay`;
2. while holding that per-peer lock, revalidate under `hub.lock` that:
   - peer is still attached to the same session/generation;
   - current role/epoch are read from the authoritative route;
3. build/send the replay with that current role/epoch;
4. release hub lock before queue-only `peer.send()`.

This guarantees:
- if replay enqueue wins first, later takeover notice is newer and follows it;
- if takeover notice wins first, replay refreshes to the current E2 role/epoch rather than enqueueing stale E1 state;
- disconnect/detach before replay can also be rejected rather than sending stale authority.

Equivalent monotonic per-peer ownership-message serialization is acceptable.

Do not:
- hold hub lock over socket I/O;
- add a new queue/retry subsystem;
- add browser/UI state;
- add persistence/PI-T007.

Add deterministic regression matching the reproduction:
1. A attach captures E1 writer state;
2. pause before replay enqueue;
3. B takeover advances to E2 and notifies A;
4. resume A replay path;
5. A must never receive replay E1 after ownership E2;
6. final ownership-bearing state must match authoritative route role/epoch.

## Concurrency / lock-order review

The turn-31 per-peer notice lock is a valid narrow primitive.

For the correction, preserve:
- TerminalManager -> Hub order for process/route mutation;
- no Hub lock during queue/socket send;
- per-peer notice lock only for ordering ownership-bearing outbound messages.

TerminalManager and PiSessionRegistry do not require changes for R31-1.

## Complexity / ponytail review

Non-blocking dead code remains:
- `lantern/ws.py`: unread `route["active"]` fields and terminal-list update scan.
- `lantern/ws.py`: unused public `pi_takeover()` wrapper.
- `lantern/ws.py`: unused public `pi_writer_target()` wrapper.

**net: -16 lines possible.**

These are cleanup only; they do not repair R31-1.

## Other required review dimensions

- **Correctness:** R30-1 fixed; blocked by R31-1 stale attach replay authority.
- **Over-engineering:** per-peer ownership enqueue lock is justified and narrow.
- **Scope drift:** none detected.
- **UX:** R31-1 directly affects future writer/viewer UI correctness.
- **Maintainability/module separation:** transient role/epoch remains hub-owned; all outbound ownership-bearing messages must share one ordering rule.
- **Scalability:** one lock per live peer; no additional replay/session store.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** notice-to-notice ordering fixed; replay-to-notice ordering remains incomplete.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused suites are fresh green; no CPU/RSS/latency release claim.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate.
- PI-T005 COMPLETE.
- PI-T004 COMPLETE / committed.
- PI-T006: **NOT ACCEPTED due R31-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R31-1: make `pi_session_replay` participate in the same per-peer monotonic ownership ordering as ownership notices, refreshing role/epoch at enqueue time. Add the deterministic attach-replay-vs-takeover regression. Preserve all R22-R30 protections and do not start PI-T007/runtime/UI/persistence work.

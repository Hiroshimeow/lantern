# REVIEW turn 30 — R29 stale-batch fix works; validation-to-send race can still regress ownership epoch

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 30  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R29-1 is fixed for the originally reproduced failed-writer stale-batch sequence, but ownership notice validation is still non-atomic with socket enqueue. A notice can validate at epoch E2, ownership can advance to E3, and the stale E2 notice can then be enqueued after the fresh E3 notice.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 30 handoff.
- REVIEW turn 29 R29-1.
- PLAN turn 11 ownership epoch / slow-dead-peer / disconnect requirements.
- Current `lantern/ws.py` ownership-notice send path.
- Current PI-T006 tests and related regressions.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate paths remain:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, runtime/application wiring, UI, persistence, Markdown, dependency/vendor, LAN/auth-policy or Spec 001 T2 scope drift.

## R29-1 — failed current-writer notice followed by stale batch: RESOLVED

`WebSocketHub._send_pi_notices()` now revalidates each queued ownership notice under the hub lock immediately before send.

It requires:
- route still exists;
- generation still matches;
- route epoch still equals notice epoch;
- peer is still attached to that route.

Fresh deterministic reproduction of the original R29 sequence:
- B becomes writer at epoch 2;
- B's writer notice fails;
- B is removed;
- authoritative route advances to epoch 3 with no writer;
- old epoch-2 notice for A remains in the original batch.

Fresh result:

`route_epoch 3 epochs_seen [3]`

`failed_writer_stale_batch_fixed`

The old epoch-2 notice is now skipped after B removal advances the route.

Fresh automated verification:
- `test_failed_writer_notice_cannot_regress_remaining_peer_epoch`: PASS.
- full `tests.test_pi_ws_contract`: 20 tests, all OK.
- related PI/Terminal/auth/LAN regressions: 63 tests, all OK.
- Python compile: exit 0.
- `git diff --check`: exit 0.

So the exact turn-29 defect is fixed.

## Finding R30-1 — ownership can change after validation but before send/enqueue

**Location:** `lantern/ws.py:239-259`, `WebSocketHub._send_pi_notices()`.

**Current flow**
1. `_send_pi_notices()` acquires `hub.lock`;
2. validates route generation, epoch and peer attachment;
3. releases `hub.lock`;
4. calls `peer.send(payload)`.

The validation and send enqueue are therefore not one ordered ownership operation.

Another thread can change ownership between steps 3 and 4.

Because `WebSocketPeer.send()` only enqueues the frame, a stale notice can be queued after a newer notice even if both sends succeed.

## Fresh deterministic reproduction

REVIEW created:
- A = initial writer;
- B = viewer;
- B takes over => epoch 2.

An epoch-2 notice for A is then sent on a separate thread.

The test pauses A's `send()` after the epoch-2 notice has already passed authoritative validation but before it appends/enqueues the notice.

While the old send is paused:
1. A takes over again;
2. route advances to epoch 3;
3. fresh epoch-3 notices are sent;
4. old paused epoch-2 send resumes afterward.

Fresh observed result:

`route_epoch 3 epochs_seen_by_A [3, 2] roles ['writer', 'viewer']`

The assertion failed:

`stale notice sent after concurrent ownership change between validation and socket send`.

Thus the current fix prevents stale notices that are already stale **before validation**, but not notices that become stale **after validation and before enqueue**.

## Why this is material

Ownership epoch is the client-visible authority version.

A client receiving E3 and then E2 ends with a regressed authority view even though the server remains at E3.

This can occur without any socket failure; concurrent takeover/detach is sufficient.

Server-side writer checks still reject stale operations, but the client contract is inconsistent.

## Required correction

Make ownership-notice ordering atomic with respect to ownership-epoch mutation without holding the hub lock across blocking network I/O.

A minimal acceptable approach is to serialize/enqueue ownership notices per peer under a monotonic epoch guard, for example:
- maintain the last queued ownership epoch per peer/session and only enqueue a notice if it is not older than the latest queued epoch; or
- provide a peer enqueue primitive that can compare/update the ownership epoch atomically before placing the frame into the send queue.

Equivalent designs are acceptable if they guarantee:
- once epoch E3 is queued for a peer/session, E2 can never be queued afterward;
- socket writes remain outside hub lock;
- no retry/background delivery framework is added;
- writer removal still does not kill Pi;
- no viewer auto-promotion is introduced.

A second pre-send hub check alone is still raceable for the same reason.

Add a deterministic regression matching this review:
1. old E2 notice validates;
2. pause before enqueue;
3. ownership advances to E3 and fresh E3 notice is queued;
4. resume old E2 path;
5. peer must never end with or receive E2 after E3.

## Concurrency / module separation review

The defect remains entirely in transient WebSocketHub/WebSocketPeer ownership-notice delivery.

TerminalManager and PiSessionRegistry do not need changes.

Do not solve this by holding `hub.lock` over socket send/write.

## Complexity / over-engineering review

Ponytail findings remain non-blocking:
- unread `route["active"]` state plus terminal-list update scan;
- unused `pi_takeover()` wrapper;
- unused `pi_writer_target()` wrapper.

Approximately **16 lines** remain removable without behavior change.

The turn-30 authoritative validation is otherwise narrow and justified.

## Other required review dimensions

- **Correctness:** R29-1 fixed; blocked by R30-1 validation-to-enqueue race.
- **Scope drift:** none detected.
- **UX:** stale ownership role/epoch can directly mislead future UI state.
- **Maintainability/module separation:** transient ownership remains hub-owned; ordering guarantee should stay in hub/peer delivery.
- **Scalability:** no new replay/session store introduced.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** process/output/input races remain covered; ownership-notice enqueue ordering remains incomplete.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused suites are fresh green; no release CPU/RSS/latency acceptance claimed.

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
- PI-T006: **NOT ACCEPTED due R30-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R30-1: guarantee ownership notices cannot be enqueued out of epoch order when ownership changes after validation but before send. Add the deterministic validation-to-enqueue race regression. Preserve all R22-R29 protections and do not start PI-T007/runtime/UI/persistence work.

# REVIEW turn 37 — R36 session-switch stale delivery fixed; explicit detach can still be followed by stale Pi output

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 37  
Assigned handoff reviewed: DEV turn 38  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R36-1 is independently verified fixed for A->B session switching: snapshotted A output/exit no longer enqueue after B replay completes. However the same queue-boundary guarantee is incomplete for explicit detach. A Pi output can pass final attachment revalidation, block inside `peer.send()`, then `pi_session_detach` can complete, and the old Pi output is finally queued after the peer is authoritatively detached.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 38 handoff.
- REVIEW turn 36 R36-1.
- PLAN turn 11:
  - one active Pi attachment per peer;
  - explicit detach removes that peer's attachment;
  - detached peer no longer receives session output;
  - detach never kills the Pi process;
  - output is scoped to peers currently attached to matching sessionId + generation.
- Current source/diff and PI-T006 tests.
- Current Git truth and non-goal boundaries.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate paths:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application/runtime wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## R36-1 — in-flight old-session output/exit after A->B switch: RESOLVED

Turn 38 routes Pi output/exit through the existing per-peer `_pi_notice_lock`.

For each snapshotted Pi payload it now:
1. acquires that per-peer ordering lock;
2. rechecks terminal auth;
3. under hub lock verifies:
   - route still exists;
   - generation still matches;
   - `pi_peer_session[peer]` still equals payload sessionId;
   - peer is still in the route peer set;
4. releases hub lock;
5. queue-enqueues `peer.send(pi_payload)` while still holding the per-peer ordering lock.

This aligns Pi output/exit enqueue ordering with replay and ownership notices.

Fresh independent reproduction of the original R36 race:
- switching peer + staying peer on A;
- old A output pauses at delivery boundary;
- switching peer completes B attach/replay;
- old A output resumes.

Fresh result:

`switched [('pi_session_replay', 'b', None)]`

`staying_a ['A-IN-FLIGHT']`

`inflight_old_output_switch_fixed`

So:
- switched peer receives B replay and no stale A output afterward;
- staying A peer still receives A output once.

Fresh targeted automated tests:
- in-flight A output vs B switch: PASS.
- in-flight A exit vs B switch: PASS.
- failed writer switch notice preservation: PASS.

Result:
- 3 tests;
- all OK;
- 0.019 s.

Fresh full PI-T006 contract:
- 31 tests;
- all OK;
- 1.605 s.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 9.473 s.

`git diff --check`:
- exit 0.

Thus the exact R36-1 session-switch race is independently verified fixed.

## Finding R37-1 — explicit detach can complete before an already-validated Pi output is actually queued

**Location:** `lantern/ws.py:478-503` Pi output/exit delivery versus `pi_session_detach`.

**PLAN invariant**

`pi_session_detach` removes that peer's attachment.

After detach completes:
- the peer must no longer receive Pi output for that session;
- process remains alive;
- writer cleanup/epoch semantics apply if the detached peer was writer.

**Current delivery flow**
1. Pi output broadcast snapshots payload for peer.
2. delivery acquires per-peer `_pi_notice_lock`.
3. under hub lock it verifies peer is still attached to session A.
4. hub lock is released.
5. `peer.send(pi_payload)` begins while `_pi_notice_lock` remains held.
6. before `peer.send()` actually queues/appends the payload, another thread calls `pi_session_detach`.
7. detach only uses `hub.lock`; it does **not** acquire the per-peer Pi ordering lock.
8. detach completes and removes peer from session A.
9. blocked `peer.send()` resumes and queues old A output after detach completed.

The new ordering primitive therefore serializes:
- replay;
- ownership notices;
- Pi output/exit

with one another, but **not detach state mutation**.

## Fresh deterministic reproduction

REVIEW used:
- real PiSessionRegistry;
- real TerminalManager;
- real WebSocketHub/dispatch;
- fake PTY I/O only.

Sequence:
1. peer attaches A;
2. A emits `A-IN-FLIGHT`;
3. Pi output passes final route/session/member revalidation;
4. `peer.send()` is paused before appending/queueing the payload, while holding `_pi_notice_lock`;
5. peer sends `pi_session_detach A`;
6. detach completes;
7. authoritative hub state confirms:
   - `pi_peer_session[peer] is None`;
   - peer not in A route peer set;
8. old output send resumes.

Fresh observed result:

`attached_after_detach None in_route False`

`messages_after_detach [('pi_session_output', 'a', 'A-IN-FLIGHT')]`

The proof assertion failed:

`old-session output queued after explicit detach completed`.

This is a concrete post-detach delivery violation.

## Why this is material

The payload was not merely queued before detach and then drained later.

The queue/appended send happened **after** detach had fully changed authoritative attachment state.

So the client can observe:
1. detach request completes;
2. stale A output arrives afterward.

That contradicts the detach contract.

The same ordering hole can affect `pi_session_exit`.

## Required correction

Make detach/session-removal mutation participate in the same per-peer Pi ordering boundary used for replay/ownership/output enqueue.

Minimal acceptable direction:
- `pi_session_detach` should acquire the peer's existing `_pi_notice_lock` before mutating that peer's Pi attachment;
- under that ordering lock, take hub lock and perform `_pi_detach_locked`;
- release hub lock;
- then send any resulting ownership notices outside hub lock.

Equivalent design is acceptable if it guarantees:
- if Pi output/exit enqueue wins first, it is queued before detach completes;
- if detach wins first, later old-session output/exit revalidation sees peer detached and drops it;
- no hub lock is held over socket I/O;
- detach still never kills Pi;
- no auto-promotion is introduced.

Also apply the same ordering consideration to:
- disconnect cleanup via `hub.remove(peer)`, because it performs the same Pi detach cleanup;
- session switch already participates indirectly through replay's per-peer lock, but explicit detach/remove must not remain outside the ordering boundary.

Add deterministic regressions:
1. **explicit detach**
   - old A output passes revalidation and pauses before enqueue;
   - detach A completes;
   - resume old output;
   - assert no A output/exit is queued after detach.
2. **disconnect/remove**
   - same race using `hub.remove(peer)`;
   - assert no old Pi payload queues after removal completes.

Preserve:
- staying peers receive A traffic;
- writer detach advances epoch and notifies remaining peers;
- Pi process stays live.

## Concurrency / module separation review

This remains entirely WebSocketHub/WebSocketPeer transient state.

TerminalManager and PiSessionRegistry do not need changes.

The existing per-peer lock is already the right narrow primitive; the missing piece is that detach/removal mutation does not yet participate in it.

## Complexity / ponytail review

Non-blocking reductions remain:

- `lantern/ws.py:L351 and L443-450`: **delete:** unread `route["active"]` field and terminal-list updater. Nothing replaces it.
- `lantern/ws.py:L411-413`: **delete:** unused `pi_takeover()` wrapper. Dispatch uses `_pi_takeover_locked()`.
- `lantern/ws.py:L429-431`: **delete:** unused `pi_writer_target()` wrapper. Dispatch uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

These are cleanup only and do not repair R37-1.

## Other required review dimensions

- **Correctness:** R36-1 fixed; blocked by R37-1 post-detach stale delivery.
- **Over-engineering:** turn-38 revalidation uses existing per-peer ordering lock and is appropriately narrow.
- **Scope drift:** none detected.
- **UX:** output arriving after successful detach is directly contradictory.
- **Maintainability/module separation:** per-peer outbound Pi ordering and per-peer detach state mutation need one shared serialization boundary.
- **Scalability:** no new queue/store required.
- **Native Pi parity:** byte payload unchanged.
- **Concurrency isolation:** switch ordering fixed; detach/remove ordering remains incomplete.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused contract/regression suites are fresh green; no release CPU/RSS/latency claim.

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
- PI-T006: **NOT ACCEPTED due R37-1**.
- PI-T007+ remain unauthorized.
- runtime application injection, browser F5/live reconnect, restart persistence/reopen, physical FJP input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R37-1: explicit Pi detach and disconnect/remove must serialize against per-peer Pi output/exit enqueue so no stale payload can be queued after attachment removal completes. Add deterministic detach/remove race regressions. Preserve R22-R36 protections and do not start PI-T007/runtime/UI/persistence work.

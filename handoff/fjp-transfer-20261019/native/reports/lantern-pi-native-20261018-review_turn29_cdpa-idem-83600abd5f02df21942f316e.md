# REVIEW turn 29 — legacy replay filtering fixed; ownership notices can regress after failed writer send

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 29  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R28-1 is fixed: legacy fallback replay excludes Pi-owned retained output while preserving ordinary legacy tails. However a separate PI-T006 ownership-notice ordering defect is reproducible when sending an ownership update to a dead current writer fails: removing that writer advances the epoch again, but an older queued notice can still be sent afterward to remaining viewers, leaving them with stale ownership state.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 29 handoff.
- REVIEW turn 28 R28-1.
- PLAN turn 11 ownership-epoch / disconnect / slow-dead-peer requirements.
- Current source/tests:
  - `lantern/pi_sessions.py`
  - `lantern/terminal.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_ws_contract.py`
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current PI-T006 candidate paths remain:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application/runtime wiring, browser/UI, persistence, Markdown, dependency/vendor, LAN/auth-policy or Spec 001 T2 scope drift.

## R28-1 — legacy snapshot Pi replay leakage: RESOLVED

TerminalManager now provides:

`replay_excluding_control_owner(owner)`

under its existing RLock.

The helper reads the same live/history retained-output set as `replay()` but omits entries whose exact `TerminalEntry.control_owner` matches the requested owner.

`_legacy_snapshot_payload()` uses that helper for real TerminalManager instances and preserves the old `replay()` fallback for lightweight test doubles.

Fresh targeted verification:
- `test_legacy_snapshot_excludes_pi_retained_output_and_preserves_ordinary_tail`: PASS.
- `test_unattached_pi_generation_never_falls_through_to_generic_output_or_exit`: PASS.
- delayed old-generation output replacement test: PASS.
- delayed old-generation exit replacement test: PASS.

Fresh aggregate verification:
- PI-T006 contract: 19 tests, all OK.
- related PI/Terminal/auth/LAN regressions: 63 tests, all OK.
- Python compile: exit 0.
- `git diff --check`: exit 0.

So the exact turn-28 legacy replay defect is fixed.

## Independent legacy replay check

The corrected helper preserves:
- ordinary retained output;
- the existing 20,000-character legacy display cap;
- server-retained history;
- current metadata list visibility.

Pi retained bytes are omitted from the legacy snapshot output map.

No registry lookup or WebSocket route state is used as ownership truth.

## Finding R29-1 — failed writer ownership notice can be followed by an older stale notice

**Location:** `lantern/ws.py`, `WebSocketHub._send_pi_notices()`.

**Relevant PLAN requirements**
- ownership epoch increments whenever writer ownership changes;
- all attached peers receive ownership-change notifications sufficient to know their current role/epoch;
- `WebSocketHub.remove(peer)` on disconnect performs the same detach cleanup;
- REVIEW must scrutinize slow/dead peer behavior.

**Current flow**

`_send_pi_notices(notices)` iterates a snapshot list of ownership notices.

If sending a notice to the current writer fails:
1. `_send_pi_notices` catches the exception;
2. calls `self.remove(peer)`;
3. `remove()` detaches that writer;
4. detach advances ownership epoch again and sends a new ownership notice to remaining peers;
5. control returns to the original `_send_pi_notices` loop;
6. the loop may then send an older pre-detach notice from its original list to a remaining peer.

Because route peers are a set, the notice iteration order is not a stable contract. A valid ordering can therefore deliver:
- new epoch E3 from writer-removal cleanup;
- then stale older epoch E2 from the original takeover-notice list.

The remaining viewer ends with stale client-side ownership state.

## Fresh deterministic reproduction

REVIEW created one Pi route with:
- A = current writer;
- B = viewer.

Then B took over, producing epoch 2 ownership notices.

The notice list was exercised in a valid order with:
- B's writer notice first;
- A's viewer notice second.

B's send was forced to fail.

Observed after failure:
- B was removed;
- route writer became `None`;
- route epoch advanced to 3;
- A received epoch 3 viewer notice from disconnect cleanup;
- then A received stale epoch 2 viewer notice from the original notice list.

Fresh output:

`route_epoch 3 writer None`

`A_messages [... ownershipEpoch: 3 ..., ... ownershipEpoch: 2 ...]`

The assertion failed:

`remaining peer ended with stale ownership notice after failed writer send`.

This is a concrete PI-T006 dead-peer ordering defect.

## Why this is material

Ownership epoch is specifically the mechanism clients use to reject stale writer operations and understand current writer state.

A client that is told E3 and then E2 has a regressed view of authority even though the server remains at E3.

The server-side writer checks still reject stale operations, but the client contract becomes inconsistent and can drive incorrect UI/role behavior.

## Required correction

Ensure failed notice delivery cannot cause an older notice batch to continue after `remove(peer)` mutates ownership epoch.

Minimal acceptable directions:
- when a send failure triggers removal/detach and ownership mutation, stop processing the stale notice batch and regenerate/send current ownership state from the authoritative route; or
- version each notice batch and suppress any notice whose epoch is older than the route's current epoch at send time.

Preserve:
- socket sends outside hub lock;
- writer removal never kills Pi;
- no arbitrary viewer auto-promotion;
- current ownership-epoch semantics;
- all accepted attach/takeover/detach races.

Add a deterministic regression where:
1. writer B is first in a takeover notice batch;
2. B's ownership-notice send fails;
3. removal increments epoch;
4. remaining viewer A must end with only the current epoch as its final ownership state;
5. no older notice may be sent afterward.

Do not add retries, background queues, persisted ownership, PI-T007 lifecycle, or UI logic.

## Concurrency / module-separation review

The defect is confined to transient WebSocketHub ownership-notice delivery.

TerminalManager and PiSessionRegistry do not need changes.

No new lock hierarchy is required; socket sends should remain outside the hub lock.

## Complexity / over-engineering review

Current dead-code reductions remain non-blocking:
- unread `route["active"]` state and terminal-list scan;
- unused public `pi_takeover()` wrapper;
- unused public `pi_writer_target()` wrapper.

Approximately **16 lines** remain removable without behavior change.

The new legacy replay helper is justified by the real/fake TerminalManager compatibility boundary and is not over-engineering.

## Other required review dimensions

- **Correctness:** R28-1 fixed; blocked by R29-1 dead-peer ownership-notice regression.
- **Scope drift:** none detected.
- **UX:** stale role/epoch notice is directly relevant to future UI correctness but no UI implementation is present.
- **Maintainability/module separation:** transient ownership remains correctly hub-owned.
- **Scalability:** no new output/session store introduced.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** process/input/output races remain covered; ownership notification ordering under peer failure is incomplete.
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
- PI-T006: **NOT ACCEPTED due R29-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R29-1: prevent stale ownership notices from being delivered after a failed current-writer notice causes removal and a newer ownership epoch. Add the deterministic dead-writer notice-order regression. Preserve the accepted R22-R28 protections and do not start PI-T007/runtime/UI/persistence work.

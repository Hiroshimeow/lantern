# REVIEW turn 32 — R31 replay ordering fixed; auth revocation during attach leaves ghost writer attached

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 32  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R31-1 is fixed: attach replay and ownership notices now share the same per-peer ordering lock and replay role/epoch are refreshed from authoritative route state at enqueue time. However a concrete attach rollback defect remains if terminal authorization is revoked after `pi_attach` publishes the peer but before `_send_pi_replay` queues the replay. The attach request fails, yet the peer remains attached and may remain the route writer.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 32 handoff.
- REVIEW turn 31 R31-1.
- PLAN turn 11 attach/auth/ownership/disconnect requirements.
- Current PI-T006 candidate source/tests.
- Current Git state and scope.
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
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## R31-1 — attach replay ownership regression after takeover: RESOLVED

`WebSocketHub._send_pi_replay()` now uses the same per-peer `_pi_notice_lock` as ownership notices.

While holding that per-peer lock it:
1. verifies current terminal authorization;
2. under `hub.lock`, confirms:
   - route exists;
   - route generation matches replay generation;
   - `pi_peer_session[peer]` still points to the same session;
   - peer is still attached to the route;
3. refreshes replay `role` and `ownershipEpoch` from the authoritative route;
4. releases `hub.lock`;
5. calls queue-only `peer.send()`.

This gives ownership-bearing replay and ownership notices one enqueue-order boundary.

Fresh independent reproduction of the prior race:
- A attach is held before replay enqueue;
- B is attached and then becomes writer via takeover;
- route advances to epoch 2;
- A replay resumes.

Fresh result:

`mutated_epoch 2`

`states [('pi_session_replay', 2, 'viewer'), ('pi_session_ownership', 2, 'viewer')] authoritative 2 viewer`

`attach_replay_monotonic_ok`

So stale E1 writer replay no longer follows E2 viewer authority.

## Fresh automated verification

Targeted ownership-ordering tests:
- `test_attach_replay_cannot_regress_ownership_after_takeover`: PASS.
- `test_ownership_notice_enqueue_order_cannot_regress_after_validation`: PASS.
- `test_failed_writer_notice_cannot_regress_remaining_peer_epoch`: PASS.

Result:
- 3 tests;
- all OK;
- 0.526 s;
- exit 0.

Full PI-T006 contract:
- 22 tests;
- all OK;
- 1.553 s;
- exit 0.

Related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 11.230 s;
- exit 0.

Syntax:
- `py_compile` for affected Terminal/Pi/WS/test files: exit 0.

`git diff --check`:
- exit 0.

Thus the exact R31-1 ordering defect is independently verified fixed.

## Finding R32-1 — auth revocation after route publication leaves failed attach as ghost writer

**Location:** `lantern/ws.py`, `pi_session_attach` dispatch path and `WebSocketHub._send_pi_replay()`.

**Relevant PLAN requirements**
- existing terminal auth protects all Pi operations;
- unauthenticated peers cannot attach;
- first attached peer becomes writer;
- disconnect/detach releases writer ownership;
- one route writer must reflect an actually attached/usable peer.

**Current attach sequence**
1. dispatch entry checks `peer.can_terminal()` and it is true;
2. session/replay are validated;
3. `hub.pi_attach()` publishes the peer into:
   - `pi_peer_session`;
   - route `peers`;
   - route `writer` if first attacher;
4. attach returns role/epoch;
5. later `_send_pi_replay()` re-checks `peer.can_terminal()`;
6. if auth has expired/revoked meanwhile, it raises `PiSessionPermissionError("peer is not authorized")`;
7. dispatch fails, but no rollback detaches the peer.

So a request that did not successfully receive its attach replay can still remain the route writer.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

The peer's `can_terminal()` returned:
- true for dispatch's initial auth check;
- false on the later replay authorization check.

Fresh output:

`err PiSessionPermissionError: peer is not authorized`

`attached s writer_is_peer True epoch 1 messages []`

The proof assertion failed:

`revoked peer remained attached after replay authorization failure`.

The peer received no replay, the attach request failed, but server state still says:
- attached to session `s`;
- current writer;
- epoch 1.

## Why this is material

Terminal authorization is explicitly dynamic:
- current cookie/token expiry/revocation is checked on commands and broadcasts.

Therefore auth can legitimately change between the initial dispatch check and replay send.

A failed attach must not leave durable transient route authority behind.

Otherwise:
- an unauthorized peer can occupy writer ownership after its attach failed;
- later legitimate peers attach as viewers instead of first writer;
- no input may be possible without explicit takeover;
- route state disagrees with the externally observed failed attach result.

This is not a new auth policy issue; it is transactional cleanup of existing auth semantics.

## Required correction

Make `pi_session_attach` transactional with respect to replay-send failure after route publication.

Minimal acceptable behavior:
- if `_send_pi_replay()` raises after this attach published the peer, detach that peer from the same session before propagating the error;
- if the failed peer was writer, increment ownership epoch and notify remaining peers exactly as normal detach does;
- do not kill the Pi process;
- do not detach a newer/different attachment the peer may have switched to concurrently;
- do not roll back another peer's takeover.

A generation/session-safe rollback check is required.

Equivalent design:
- perform the final auth check before route publication and ensure no later auth-dependent failure exists before replay enqueue; but current design still needs to tolerate send/enqueue failure cleanup.

Add deterministic regression:
1. initial auth check succeeds;
2. attach publishes peer as first writer;
3. auth becomes invalid before replay send;
4. attach raises;
5. peer is absent from `pi_peer_session`;
6. peer absent from route peer set;
7. writer is none or a later authoritative owner, never the failed peer;
8. Pi process remains running.

Also test viewer failure if practical:
- failed viewer replay must not disturb current writer.

## Concurrency / rollback review

Rollback must be conditional on the same session attachment still being current.

Do not blindly call a detach that could remove:
- a later session switch;
- a newer generation attachment;
- another route state established after the failed attach began.

Use current `pi_peer_session` and route identity under `hub.lock` to decide whether rollback still applies.

## Complexity / ponytail review

Non-blocking complexity reductions remain:

- `lantern/ws.py`: unread `route["active"]` state plus terminal-list scan. Delete it; nothing replaces it.
- `lantern/ws.py`: unused `pi_takeover()` wrapper. Delete it; dispatch uses `_pi_takeover_locked()`.
- `lantern/ws.py`: unused `pi_writer_target()` wrapper. Delete it; dispatch uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

The new `_send_pi_replay()` helper is justified because replay now shares ownership ordering and authoritative refresh logic.

## Other required review dimensions

- **Correctness:** R31-1 fixed; blocked by R32-1 partial-attach rollback.
- **Over-engineering:** no new subsystem introduced.
- **Scope drift:** none detected.
- **UX:** ghost writer would make legitimate clients appear stuck as viewers after a failed attach.
- **Maintainability/module separation:** rollback belongs to transient hub attachment state; TerminalManager/PiSessionRegistry need no change.
- **Scalability:** no additional session/output store.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** replay/notice ordering fixed; attach failure rollback remains incomplete.
- **Auth/security:** existing auth is reused; defect is cleanup when authorization changes mid-attach.
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
- PI-T006: **NOT ACCEPTED due R32-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R32-1: a failed attach after route publication must conditionally roll back that same transient Pi attachment/writer state, while preserving the live Pi process and any newer authoritative route state. Add the deterministic auth-revocation-between-publish-and-replay regression. Preserve all R22-R31 protections and do not start PI-T007/runtime/UI/persistence work.

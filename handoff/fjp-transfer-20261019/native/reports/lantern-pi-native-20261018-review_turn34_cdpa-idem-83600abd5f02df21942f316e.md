# REVIEW turn 34 — R33 stale replay-after-exit fixed; live output can still overtake initial replay

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 34  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R33-1 is fixed: replay enqueue is now covered by exact TerminalManager generation/running validation and attach rolls back if the PTY exits first. However the attach boundary still allows live Pi output to be routed to the newly attached peer before its initial `pi_session_replay` is queued. This violates the PLAN requirement that replay capture + route registration be atomic before live output can race ahead.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 34 handoff.
- REVIEW turn 33 R33-1.
- PLAN turn 11 attach replay ordering requirement.
- Current PI-T006 source/tests.
- Current Git state/scope.
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
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## R33-1 — PTY exit after publish before replay enqueue: RESOLVED

`WebSocketHub._send_pi_replay()` now receives the authoritative TerminalManager and exact terminal ID.

While holding the per-peer Pi ownership/replay ordering lock it:
1. rechecks terminal auth;
2. enters `terminal.lock`;
3. verifies exact generation and `running`;
4. under the same TerminalManager boundary, revalidates current hub session/generation/attachment;
5. refreshes role/ownership epoch;
6. releases hub lock;
7. queue-enqueues replay while TerminalManager lock is still held.

Therefore:
- if exit wins TerminalManager lock first, replay sees stopped/stale and attach fails;
- if replay wins first, queue enqueue completes before that generation can be marked stopped;
- token-safe rollback handles failure.

Fresh targeted verification:
- post-publish PTY-exit attach rejection: PASS.
- replay/takeover ownership monotonicity: PASS.
- auth-revocation rollback: PASS.

Result:
- 3 tests;
- all OK;
- 0.021 s.

Fresh PI-T006 contract:
- 26 tests;
- all OK;
- 1.600 s.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 10.947 s.

Syntax:
- `py_compile`: exit 0.

`git diff --check`:
- exit 0.

So the exact turn-33 stale replay-after-exit defect is independently verified fixed.

## Finding R34-1 — live Pi output can be delivered before initial attach replay

**PLAN requirement**

PLAN turn 11 explicitly requires:

- atomically capture the underlying TerminalManager replay view and register the peer as attached **before live output can race ahead**.

That requirement is necessary because replay establishes:
- initial retained output;
- initial seq;
- UTF-8 replay boundaries;
- writer/viewer role;
- ownership epoch.

Live output must not precede that initialization message.

**Current flow**
1. under `terminal.lock`, capture replay view;
2. call `hub.pi_attach()`, publishing peer into route `peers`;
3. release `terminal.lock`;
4. perform bounded replay computation;
5. send any ownership notices;
6. later enter `_send_pi_replay()`;
7. acquire the per-peer replay/notice lock and TerminalManager lock;
8. enqueue replay.

Between steps 3 and 6, the peer is already route-visible to `WebSocketHub.broadcast()`.

A PTY output event can therefore route directly to that peer before replay is enqueued.

The final liveness lock added in turn 34 does not prevent this because the output can occur **before** `_send_pi_replay()` obtains its TerminalManager lock.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

The peer's existing per-peer Pi ordering lock was held so attach could:
- capture replay;
- publish the peer/writer route;
- then block before replay enqueue.

While replay remained blocked, the PTY emitted:

`LIVE-AFTER-CAPTURE`.

Fresh output before releasing replay:

`before_release [('pi_session_output', 1, 'LIVE-AFTER-CAPTURE')]`

After releasing replay:

`after_release [('pi_session_output', 1, 'LIVE-AFTER-CAPTURE', None), ('pi_session_replay', 0, None, '')]`

The proof assertion failed:

`live Pi output was queued before attach replay initialization`.

This is a direct violation of the PLAN attach race requirement.

## Why this is material

The client receives:
1. live output seq 1;
2. then replay seq 0.

Even if a future client tries to reconcile seq numbers, the protocol is backwards at initialization:
- live data arrives before the authoritative replay baseline;
- role/epoch initialization also arrives after live session traffic;
- a reconnect client may temporarily render/apply data against no replay state.

The existing replay continuity work relies on replay establishing the baseline before live continuation.

## Required correction

Make route visibility to live output contingent on replay enqueue ordering.

Minimal acceptable approaches include either:

1. **Pending attach state**
   - register peer in a transient pending state while replay is captured;
   - do not include pending peer in live-output routing;
   - enqueue replay;
   - then atomically mark attachment live before releasing the ordering boundary.

or

2. **One attach/output serialization boundary**
   - keep the TerminalManager output-emission boundary blocked from the moment replay snapshot is captured until replay is queue-enqueued and route is visible to output;
   - avoid holding hub lock over send;
   - preserve one consistent lock order.

Any equivalent design must guarantee:
- no `pi_session_output` for that attachment can be queued before its first `pi_session_replay`;
- no output bytes are lost between replay snapshot and activation;
- output produced after the replay snapshot is delivered exactly once after replay;
- attach failure still token-safely rolls back;
- PTY exit vs replay remains correctly ordered;
- takeover/ownership ordering remains monotonic.

Add a deterministic regression matching the reproduction:
1. pause attach after replay capture + route publication boundary but before replay enqueue;
2. emit PTY output;
3. resume attach;
4. assert peer message order is replay first, then output;
5. assert replay seq plus subsequent output seq are continuous;
6. assert output data is not duplicated or lost.

A stronger implementation may avoid publishing the peer into `route["peers"]` until replay is queued, but must still satisfy the original no-gap output requirement.

## Concurrency / module separation review

This is the remaining attach replay/live-output ordering boundary.

TerminalManager owns:
- output seq/replay stream;
- PTY liveness.

WebSocketHub owns:
- attachment visibility;
- peer routing.

The fix must coordinate those existing owners without introducing another replay store or output queue.

Do not hold the hub lock across socket I/O.

## Complexity / ponytail review

Non-blocking reductions remain:

- `lantern/ws.py`: unread `route["active"]` state and terminal-list update scan. Delete; nothing replaces it.
- `lantern/ws.py`: unused `pi_takeover()` wrapper. Delete; dispatch uses the locked helper.
- `lantern/ws.py`: unused `pi_writer_target()` wrapper. Delete; dispatch uses the locked helper.

**net: -16 lines possible.**

The turn-34 TerminalManager liveness validation is justified and not over-engineered.

## Other required review dimensions

- **Correctness:** R33-1 fixed; blocked by R34-1 live-output-before-replay race.
- **Over-engineering:** no new subsystem introduced.
- **Scope drift:** none detected.
- **UX:** live bytes before initialization would produce incorrect reconnect/render ordering.
- **Maintainability/module separation:** replay baseline and live continuation need one explicit activation boundary.
- **Scalability:** no additional retained-output store should be added.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** PTY exit ordering fixed; replay-vs-live-output ordering still incomplete.
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
- PI-T006: **NOT ACCEPTED due R34-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R34-1: initial `pi_session_replay` must queue before any live `pi_session_output` becomes deliverable to that newly attached peer, without losing or duplicating output produced after replay capture. Add the deterministic replay-before-live-output regression. Preserve all R22-R33 protections and do not start PI-T007/runtime/UI/persistence work.

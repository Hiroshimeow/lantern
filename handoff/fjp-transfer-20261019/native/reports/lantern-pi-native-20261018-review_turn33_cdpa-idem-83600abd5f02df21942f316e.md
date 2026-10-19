# REVIEW turn 33 — R32 rollback fixed; attach can still send replay after PTY exit

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 33  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R32-1 is fixed: replay/auth failure now conditionally rolls back only the exact published attachment token and preserves newer attachments/current writers. However a separate attach liveness race remains: after `pi_attach` publishes the peer, the PTY can exit before `_send_pi_replay`; the peer then receives `pi_session_exit` followed by a successful stale `pi_session_replay` for the stopped generation, and remains attached/writer.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 33 handoff.
- REVIEW turn 32 R32-1.
- PLAN turn 11 attach/liveness/replay/ownership requirements.
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

## R32-1 — failed attach rollback after replay/auth failure: RESOLVED

Turn 33 adds transient per-attachment identity in `WebSocketHub`:

`pi_peer_attach_token: dict[peer, object]`.

A newly published attachment receives a unique token. Idempotent reattach to the same current session/generation reuses the same token.

`pi_rollback_attach(peer, session_id, generation, attach_token)` detaches only when:
- peer is still attached to that session;
- current token is exactly the failed attach token;
- route generation still matches;
- peer is still in the route peer set.

Rollback uses the existing detach semantics:
- failed writer is cleared;
- ownership epoch advances;
- remaining peers receive fresh notices;
- failed viewer removal leaves current writer/epoch unchanged;
- Pi process is not killed.

Fresh targeted verification:
- failed first-writer auth replay rollback: PASS.
- failed viewer auth replay rollback without writer disturbance: PASS.
- stale old attach token cannot remove newer same-session attachment: PASS.
- attach replay/takeover ordering: PASS.
- failed-writer notice ordering: PASS.

Result:
- 5 tests;
- all OK;
- 0.026 s;
- exit 0.

Fresh full PI-T006 contract:
- 25 tests;
- all OK;
- 1.567 s;
- exit 0.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 11.192 s;
- exit 0.

Syntax:
- `py_compile`: exit 0.

`git diff --check`:
- exit 0.

Independent idempotent-attach probe also confirmed:
- ownership epoch unchanged;
- same attach token retained;
- writer unchanged;
- second replay returned as expected.

## Finding R33-1 — attach can succeed with replay after the PTY already exited

**Location:** `lantern/ws.py`, `pi_session_attach` flow between `hub.pi_attach()` and `hub._send_pi_replay()`.

**PLAN invariant**

PLAN turn 11 requires attach to:
- reject stopped/not-running sessions;
- reject stale generation;
- return replay for the currently attached live Pi session;
- establish a consistent writer/viewer attachment.

The existing pre-publication exit race is already covered by:

`test_attach_rejects_exit_between_registry_lookup_and_replay_capture`.

But there is a second liveness window after route publication.

**Current sequence**
1. registry/session view says running;
2. under `terminal.lock`, replay view confirms matching live generation;
3. `hub.pi_attach()` publishes peer and writer state;
4. terminal lock is released;
5. before `_send_pi_replay()` queues replay, PTY exits;
6. TerminalManager removes the live generation and emits `pi_session_exit`;
7. PiSessionRegistry reports session stopped;
8. `_send_pi_replay()` only revalidates hub route/session/generation/peer attachment and auth;
9. it does **not** revalidate TerminalManager liveness;
10. stale replay is sent successfully after the exit.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

The per-peer ownership-message lock was held so attach could:
- publish the peer/writer route;
- then block before replay enqueue.

While replay was blocked:
- the exact Pi PTY exited with code 9.

Then replay enqueue was released.

Fresh output:

`errs []`

Messages observed by the peer, in order:

`('pi_session_exit', 9, ...)`

then

`('pi_session_replay', ..., ownershipEpoch=1, role='writer')`

Registry truth after the sequence:

`registry_running False`

So the attach request completed successfully and delivered a replay **after** the same generation had already exited.

The peer also remains attached/writer unless later explicitly detached.

## Why this is material

A successful attach replay is the client’s initialization of:
- session liveness;
- terminal output state;
- writer/viewer role;
- ownership epoch.

Delivering:
1. exit; then
2. successful replay claiming writer role

for an already-stopped generation produces an internally contradictory protocol state.

It also leaves transient writer ownership attached to a dead generation.

This is the post-publication analogue of the earlier pre-replay-capture exit race.

## Required correction

Make replay-send success conditional on the same PTY generation still being live at the enqueue boundary.

Minimal acceptable direction:
- before enqueueing `pi_session_replay`, under the existing TerminalManager ownership boundary, revalidate exact terminal ID + generation + running state;
- if stopped/stale, fail attach and invoke the existing token-safe rollback;
- do not send replay after a matching `pi_session_exit` has already made that generation dead.

Preserve:
- per-peer replay/ownership ordering lock;
- token-safe rollback;
- no hub lock across queue/socket send;
- no process restart;
- no auto-promotion.

Because `_send_pi_replay()` currently only has hub state, the clean implementation may pass a liveness callback/snapshot from dispatch or perform the final liveness check in dispatch immediately before entering the per-peer replay enqueue boundary. Whatever design is chosen, avoid introducing a new process-state owner.

Add deterministic regression:
1. attach publishes peer as writer;
2. block replay before enqueue;
3. PTY exits;
4. release replay path;
5. attach must raise stale/not-running error;
6. no `pi_session_replay` is sent after exit;
7. failed peer is rolled back from route/writer state;
8. Pi session remains stopped, not restarted.

## Concurrency / module separation review

TerminalManager remains the authority for PTY generation/liveness.

WebSocketHub remains the authority for transient peer/writer attachment.

The correction must coordinate those two existing owners without introducing a third state source.

Preserve established lock ordering and avoid hub-lock-held socket sends.

## Complexity / ponytail review

Non-blocking reductions remain:

- `lantern/ws.py`: unread `route["active"]` state and terminal-list scan.
- `lantern/ws.py`: unused `pi_takeover()` wrapper.
- `lantern/ws.py`: unused `pi_writer_target()` wrapper.

**net: -16 lines possible.**

The new attach-token map is justified by exact rollback identity and is not speculative.

## Other required review dimensions

- **Correctness:** R32-1 fixed; blocked by R33-1 post-publication exit/replay race.
- **Over-engineering:** tokenized rollback is narrowly justified.
- **Scope drift:** none detected.
- **UX:** exit followed by stale writer replay would misinitialize future UI.
- **Maintainability/module separation:** liveness must remain TerminalManager-owned; attachment remains hub-owned.
- **Scalability:** one transient token per attached peer only.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** rollback identity fixed; final liveness-to-replay atomicity remains incomplete.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused suites are fresh green; no release CPU/RSS/latency claim.

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
- PI-T006: **NOT ACCEPTED due R33-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R33-1: prevent a published attach from successfully enqueueing replay after the exact PTY generation has exited; fail and token-safely roll back the attachment instead. Add the deterministic exit-between-publication-and-replay regression. Preserve all R22-R32 protections and do not start PI-T007/runtime/UI/persistence work.

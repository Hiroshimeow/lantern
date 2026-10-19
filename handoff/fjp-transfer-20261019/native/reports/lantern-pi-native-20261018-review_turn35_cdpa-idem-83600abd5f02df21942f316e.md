# REVIEW turn 35 — R34 replay/live serialization fixed; failed session switch drops old-route ownership notice

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 35  
Assigned handoff reviewed: DEV turn 36 (following DEV turn 35 recovery incident)  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R34-1 is independently verified fixed: replay snapshot, route publication and replay queue enqueue now share one TerminalManager-owned boundary, so live output cannot overtake initial replay. However a concrete session-switch failure defect remains: if a peer is detached from old session A while attaching session B and B's replay/auth step fails, the ownership notice generated for A's remaining viewers is discarded.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 36 handoff, including DEV turn 35 source-recovery incident.
- REVIEW turn 34 R34-1.
- PLAN turn 11 one-active-Pi-attachment, session switch, detach, ownership epoch and replay/live-output ordering requirements.
- Current diffs and repository truth.
- Recovered `tests/test_pi_ws_contract.py`.
- Preserved pre-truncation Python 3.14 bytecode artifact.
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
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## Turn-35 test-source recovery assessment

DEV turn 35 accidentally truncated the untracked PI-T006 contract test source and preserved the pre-truncation Python 3.14 pyc.

DEV turn 36 reconstructed source from that bytecode and repaired decompiler artifacts.

Independent REVIEW checks:
- preserved pyc class exposes **27 test methods**;
- current recovered source exposes **27 test methods**;
- method-name sets are identical;
- a substantial subset of recovered methods is bytecode-equivalent to the preserved artifact;
- intentionally changed R34/R31 concurrency tests are expected to differ because the locking contract changed;
- current recovered source compiles;
- all 27 current PI-T006 tests run and pass fresh.

The recovered test source is stylistically compressed in places because of decompilation, but it is readable enough to review and execute. The recovery provenance remains important evidence; it is not itself a blocking correctness defect in the current candidate.

The preserved pyc test class was also attempted directly against the current implementation. That old suite timed out, which is expected because old concurrency tests encode synchronization points invalidated by the stronger R34 serialization. REVIEW does not treat that timeout as acceptance evidence.

## R34-1 — replay must precede live output: RESOLVED

Current `pi_session_attach` holds `TerminalManager.lock` continuously across:
1. exact replay snapshot capture;
2. route publication via `hub.pi_attach()`;
3. bounded replay calculation;
4. final `_send_pi_replay()` queue enqueue.

`_send_pi_replay()` re-enters the TerminalManager RLock, checks exact generation/running, refreshes route role/epoch under hub lock, releases hub lock, and queue-enqueues replay before TerminalManager lock can be released.

This provides the required no-gap boundary:
- PTY output cannot append/increment seq between replay snapshot and replay enqueue;
- once replay is queued, later output becomes the next seq and routes afterward;
- no separate pending-output buffer/transcript owner was added.

Fresh targeted tests:
- `test_attach_replay_precedes_live_output_after_capture_without_gap_or_duplicate`: PASS.
- `test_attach_serializes_replay_before_exit_after_publish`: PASS.
- `test_attach_replay_cannot_regress_ownership_after_takeover`: PASS.
- `test_attach_auth_revocation_rolls_back_published_writer`: PASS.

Result:
- 4 tests;
- all OK;
- 0.030 s.

Fresh full PI-T006 contract:
- 27 tests;
- all OK;
- 1.626 s.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 10.245 s.

Syntax:
- `py_compile`: exit 0.

`git diff --check`:
- exit 0.

The exact R34 replay-before-live-output defect is therefore independently verified fixed.

## Finding R35-1 — failed switch from session A to B loses A ownership-change notice

**Location:** `lantern/ws.py`, `pi_session_attach` error path around lines 748-788 and `WebSocketHub.pi_attach()`.

**PLAN invariants**
- one active Pi attachment per peer;
- attaching another session detaches the peer from the old session;
- if old-session writer detaches, old session writer becomes none and ownership epoch advances;
- remaining old-session peers must receive ownership-change notification;
- failure on the new attach must not leave ownership state silently changed from clients' perspective.

**Current flow**

When a peer currently attached to session A attaches session B:

1. `hub.pi_attach(peer, B, ...)` sees current session A.
2. It calls `_pi_detach_locked(peer)` for A.
3. If peer was A's writer:
   - A writer becomes none;
   - A epoch increments;
   - ownership notices for A's remaining viewers are accumulated in local `notices`.
4. The peer is then attached to B.
5. If B's final replay/auth enqueue fails, attach catches the exception.
6. It token-safely rolls the failed B attachment back and stores `rollback_notices`.
7. Outside TerminalManager lock the error path sends **only `rollback_notices`**.
8. The earlier `notices` from detaching A are discarded.

Server state for A is correct, but A's remaining viewers never learn the writer/epoch change.

## Fresh deterministic reproduction

REVIEW used:
- real PiSessionRegistry;
- real TerminalManager;
- real WebSocketHub/dispatch;
- fake PTY I/O only.

Setup:
1. peer W attaches A as writer;
2. peer V attaches A as viewer;
3. V's existing messages are cleared;
4. W begins switching to B;
5. dispatch-level terminal auth succeeds;
6. final replay auth check fails.

Fresh observed result:

`err PiSessionPermissionError: peer is not authorized`

Authoritative A route:

`A_writer None A_epoch 2 A_peers 1`

Rolled-back B route:

`B_writer None B_peers 0`

Viewer V received:

`viewer_old_session_notices []`

The proof assertion failed:

`failed session switch dropped old-session ownership notice`.

This is reproducible on current source.

## Why this is material

The server correctly increments A's epoch and clears its writer, but the remaining A viewer retains stale client state:
- it still believes W is writer;
- it still has the old epoch.

That contradicts the ownership-notification contract and can leave the remaining peer unable to reason correctly about takeover/current ownership.

The token-safe rollback for B is correct; the defect is that A's already-committed detach notification is lost when B's attach later fails.

## Required correction

Preserve and send ownership notices for all attachment-state mutations that actually remain committed, even when the new attach fails.

Minimal correction:
- on attach failure, send both:
  - notices produced by detaching/switching away from the old session; and
  - notices produced by rolling back the failed new attachment;
- use existing per-peer monotonic ownership notice machinery;
- do not resend stale notices if their route epoch no longer matches;
- do not restore the old session attachment automatically unless PLAN explicitly requires transactional switch rollback (it does not);
- do not kill either Pi process.

A clean implementation can combine the notice lists and let `_send_pi_notices()` perform authoritative epoch/attachment filtering.

Add deterministic regression:
1. W writer + V viewer on A;
2. W switches to B;
3. B replay/auth fails after A detach and B publication;
4. B attachment is rolled back;
5. A remains with writer none and incremented epoch;
6. V receives current A ownership notice with that epoch;
7. neither A nor B process is killed;
8. W is not left attached to B.

Also preserve the viewer-switch case:
- if the switching peer was only an A viewer, no A writer epoch change/notice should be invented.

## Concurrency / module separation review

This fix stays entirely in WebSocketHub transient ownership state and dispatch notice delivery.

No TerminalManager/PiSessionRegistry model change is needed.

The new R34 lock boundary is not implicated except that attach failure handling occurs after the TerminalManager-owned replay attempt.

## Complexity / ponytail review

Current non-blocking reductions remain:

- `lantern/ws.py:L340/L351 and terminal-list update block`: **delete:** unread `route["active"]` state and its updater. Nothing replaces it.
- `lantern/ws.py:L400-402`: **delete:** unused `pi_takeover()` wrapper. Dispatch uses `_pi_takeover_locked()`.
- `lantern/ws.py:L418-420`: **delete:** unused `pi_writer_target()` wrapper. Dispatch uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

Recovered test formatting could be prettified later, but wholesale rewrite would add risk and is not warranted before correctness acceptance.

## Other required review dimensions

- **Correctness:** R34-1 fixed; blocked by R35-1 dropped old-session ownership notification.
- **Over-engineering:** stronger TerminalManager serialization is narrow and reuses existing owner/lock.
- **Scope drift:** none detected.
- **UX:** stale old-session writer/epoch state is directly client-visible.
- **Maintainability/module separation:** old-session detach is a committed hub mutation and its notice must survive failure of the subsequent new-session attach.
- **Scalability:** no added transcript/store/queue.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** replay/live output and replay/exit ordering are fixed; failed session-switch notification delivery remains incomplete.
- **Auth/security:** dynamic auth rollback remains correct for the failed new attachment.
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
- PI-T006: **NOT ACCEPTED due R35-1**.
- PI-T007+ remain unauthorized.
- runtime application injection, browser F5/live reconnect, restart persistence/reopen, physical FJP input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R35-1: a failed A->B session switch must still deliver any authoritative ownership notices caused by the committed detach from A, while token-safely rolling back B. Add the deterministic failed-switch old-route notification regression. Preserve R22-R34 protections and do not start PI-T007/runtime/UI/persistence work.

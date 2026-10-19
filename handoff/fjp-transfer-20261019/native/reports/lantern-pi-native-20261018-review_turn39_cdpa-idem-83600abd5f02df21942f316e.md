# REVIEW turn 39 — R38 per-peer replay dedupe fixed; writer can incorrectly self-takeover

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 39  
Assigned handoff reviewed: DEV turn 40  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R38-1 is independently verified fixed: replay-covered delayed output is suppressed per attachment, while peers with an earlier replay baseline still receive the delayed event once. However the reconstructed PI-T006 source currently accepts `pi_session_takeover` from the already-current writer as a successful no-op. PLAN requires takeover to be viewer-only. This is a concrete protocol regression not covered by the current 35-test contract.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 40 handoff.
- REVIEW turn 38 R38-1.
- PLAN turn 11 explicit takeover contract.
- Current reconstructed `lantern/ws.py` after the turn-39 source-loss incident.
- Current PI-T006 tests and related PI/Terminal/auth/LAN regressions.
- Current Git truth and scope/non-goal boundaries.
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

## R38-1 — delayed output already represented in replay: RESOLVED

Turn 40 adds transient WebSocketHub delivery state:

`pi_peer_delivery[peer]`

with only:
- sessionId;
- PTY generation;
- current attach token;
- scalar lastSeq.

No transcript/history bytes are duplicated.

### Replay baseline

After `peer.send(pi_session_replay)` succeeds, while still inside the existing per-peer Pi ordering boundary, the hub records:
- the current attachment identity;
- replay seq as `lastSeq`.

If the peer has already switched/detached, the baseline is not installed for the stale attachment.

### Live output

Immediately before Pi output enqueue, the hub checks:
- exact route session;
- exact generation;
- peer membership;
- current attach token;
- current per-peer delivery state.

For `pi_session_output`:
- seq <= lastSeq is suppressed;
- seq > lastSeq is queued;
- after successful enqueue, lastSeq advances monotonically only if the same attachment is still authoritative.

Detach/remove/session switch clears the delivery marker through `_pi_detach_locked()`.

### Fresh R38 verification

Fresh targeted tests:

- `test_pre_attach_delayed_output_in_replay_is_not_delivered_twice`: PASS.
- `test_delayed_output_uses_per_peer_replay_baseline`: PASS.

Result:
- 2 tests;
- all OK;
- 0.012 s;
- exit 0.

Fresh full PI-T006 contract:

`uv run python -m unittest -q tests.test_pi_ws_contract`

Result:
- 35 tests;
- all OK;
- 1.675 s;
- exit 0.

Fresh related PI / Terminal / auth / LAN regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 63 tests;
- all OK;
- 9.814 s;
- exit 0.

Syntax:
- `py_compile`: exit 0.

`git diff --check`:
- exit 0.

So the exact R38 duplicate replay/live-output defect is independently verified fixed.

## Finding R39-1 — current writer is incorrectly allowed to call takeover

**Location:** `lantern/ws.py:402-418`, `WebSocketHub._pi_takeover_locked()`.

**PLAN contract**

PLAN turn 11 explicitly states `pi_session_takeover`:
- requires the peer already be attached **as a viewer**;
- requires matching PTY generation;
- promotes requester to writer;
- prior writer becomes viewer;
- increments ownership epoch;
- does not send input/resize/restart.

A peer that is already writer therefore does not satisfy the operation precondition and must be rejected.

**Current implementation**

Current reconstructed source does:

`if route.get("writer") is peer:`
`    return route["epoch"], []`

So the current writer's takeover request is accepted as a no-op instead of rejected.

This differs from the accepted pre-reconstruction behavior described and reviewed earlier in PI-T006, where takeover was viewer-only.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

Sequence:
1. peer attaches as first writer;
2. confirm route writer is that peer and epoch is 1;
3. same peer sends `pi_session_takeover` for the same session/generation.

Fresh result:

`takeover_error None`

`epoch_before 1 epoch_after 1 writer_same True`

The proof assertion failed:

`current writer takeover was accepted instead of viewer-only rejection`.

So current source violates the explicit takeover contract.

## Why this is material

This is not merely a stylistic preference.

The operation has a defined role precondition:
- viewers may explicitly request transfer;
- writers already own authority and are not valid takeover requesters.

Accepting invalid self-takeover:
- weakens the server protocol contract;
- makes invalid client state silently succeed;
- masks client bugs;
- diverges from the previously reviewed PI-T006 semantics;
- is especially concerning because `lantern/ws.py` was semantically reconstructed after accidental truncation.

Current green tests do not cover this viewer-only negative case.

## Required correction

Restore viewer-only takeover behavior.

Minimal correction in `_pi_takeover_locked()`:
- if requester is already current writer, raise `PiSessionPermissionError` with the existing stable not-writer/viewer precondition error semantics, e.g. the previously used `"takeover requires a viewer"`;
- do not change epoch;
- do not send ownership notices;
- do not touch the PTY.

Add a deterministic regression:
1. first peer attaches as writer;
2. same peer sends `pi_session_takeover`;
3. operation raises PermissionError;
4. writer remains unchanged;
5. ownership epoch remains unchanged;
6. no ownership notification is emitted;
7. PTY remains untouched.

Preserve:
- viewer takeover succeeds;
- viewer takeover increments epoch;
- prior writer becomes viewer;
- stale generation takeover fails;
- exit-before-takeover liveness race remains fixed;
- takeover/input race protections remain fixed.

No TerminalManager or PiSessionRegistry change is needed.

## Source-reconstruction note

The turn-39 DEV handoff explicitly states `lantern/ws.py` was semantically reconstructed after accidental truncation.

R39-1 is exactly the kind of protocol-semantic drift that reconstruction can introduce while broad positive-path tests remain green.

Therefore this finding is based on current source + current PLAN + fresh production-path reproduction, not on provenance alone.

## Concurrency / module separation review

R39-1 is entirely a WebSocketHub role/precondition defect.

No lock topology change is required.

Keep existing:
- TerminalManager -> Hub order where nested;
- per-peer Pi ordering lock for replay/notices/output/detach;
- no hub lock over socket I/O.

## Complexity / ponytail review

Current non-blocking reductions in reconstructed `lantern/ws.py`:

- `lantern/ws.py:L353,L366,L462-471`: **delete:** unread `route["active"]` state and terminal-list updater. Nothing replaces it.
- `lantern/ws.py:L420-422`: **delete:** unused public `pi_takeover()` wrapper. Dispatch uses `_pi_takeover_locked()`.
- `lantern/ws.py:L444-450`: **delete:** unused public `pi_writer_target()` wrapper. Dispatch uses `_pi_writer_target_locked()`.

**net: -22 lines possible.**

These are non-blocking cleanup findings and must not be mixed with the R39 correctness fix unless independently reverified.

## Other required review dimensions

- **Correctness:** R38-1 fixed; blocked by R39-1 takeover precondition regression.
- **Over-engineering:** per-peer scalar delivery baseline is justified; no duplicate transcript store added.
- **Scope drift:** none detected.
- **UX:** silent self-takeover can hide incorrect client ownership state.
- **Maintainability/module separation:** takeover role validation belongs in hub transient ownership state.
- **Scalability:** one scalar continuity record per attached peer is acceptable.
- **Native Pi parity:** PTY bytes remain byte-transparent.
- **Concurrency isolation:** replay/delayed-output dedupe is now per attachment and ordering-aware.
- **Auth/security:** no new auth policy or token surface.
- **Regression/performance:** focused suites are fresh green, but the missing writer-self-takeover negative case proves current suite is incomplete for PLAN acceptance.

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
- PI-T006: **NOT ACCEPTED due R39-1**.
- PI-T007+ remain unauthorized.
- runtime application injection, browser F5/live reconnect, restart persistence/reopen, physical FJP input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Restore the PLAN-required viewer-only takeover precondition, add the current-writer negative regression, and preserve the accepted R22-R38 behavior. Do not start PI-T007/runtime/UI/persistence work.

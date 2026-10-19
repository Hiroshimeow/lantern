# REVIEW turn 20 — verify R19 race fixes; takeover still races PTY exit

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 20  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R19-1 and R19-2 are fixed, but a related takeover/liveness race remains: a viewer can become writer after the Pi PTY has already exited because takeover validates registry liveness before, not atomically with, the hub ownership change.

No implementation edits made by REVIEW.

## Inputs independently checked

- REVIEW turn 19 R19-1/R19-2.
- DEV turn 20 handoff.
- PLAN turn 11 PI-T006 ownership/takeover contract.
- Current diff:
  - `lantern/ws.py`
  - `tests/test_pi_ws_contract.py`
- Existing TerminalManager exit/list publication behavior.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current PI-T006 candidate is exactly:
  - `M lantern/ws.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application wiring, frontend/UI, Markdown, dependency/vendor, LAN policy, session-create RPC, or Spec 001 T2 work was introduced.

## R19-1 — attach after PTY exit: RESOLVED

The attach path now:
1. resolves the registry session;
2. enters `terminal.lock`;
3. captures `replay_view()`;
4. rejects if generation mismatches **or `meta.running` is false**;
5. only then registers the hub route.

Fresh regression:

`test_attach_rejects_exit_between_registry_lookup_and_replay_capture`

PASS.

The test forces the PTY exit between registry lookup and replay capture and proves:
- stale-session error;
- no peer route installed;
- no replay sent;
- authoritative registry view is stopped.

This closes R19-1.

## R19-2 — stale old-writer actuation after takeover: RESOLVED

Writer input/key/resize now use the same nested order as attach:

`TerminalManager.lock -> WebSocketHub.lock`.

Inside that ownership boundary the implementation:
- re-resolves registry session;
- validates route attachment/generation/epoch/current writer under hub lock;
- revalidates authoritative TerminalManager generation/running;
- performs input/key/resize before releasing the ownership boundary.

Fresh deterministic regression:

`test_takeover_between_writer_authorization_and_actuation_blocks_input_and_resize`

PASS.

The test forces takeover while the old writer is waiting to actuate and verifies:
- stale input is rejected;
- stale resize is rejected;
- zero stale PTY writes;
- zero stale resize calls.

This closes R19-2.

## Fresh REVIEW verification

`uv run python -m unittest -v tests.test_pi_ws_contract`

Result:
- 9 tests;
- all 9 OK;
- 0.043 s;
- exit 0.

Related fresh regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 40 tests;
- all OK;
- 5.891 s;
- exit 0.

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py`: exit 0.
- `git diff --check`: exit 0.

These pass but do not cover the takeover/liveness race below.

## Finding R20-1 — takeover can succeed after the Pi PTY exits

**Location:** `lantern/ws.py`, `pi_session_takeover` path.

**PLAN invariant:** takeover is authority transfer for an attached **live** Pi session with matching PTY generation. Stopped/stale sessions must not gain or advance writer ownership.

**Current flow:**
1. `_pi_session_view(pi, sessionId, generation)` validates registry view as running.
2. No TerminalManager lock is held.
3. Before `hub.pi_takeover()`, the PTY may exit.
4. TerminalManager marks that generation stopped and emits terminal exit/list.
5. `hub.pi_takeover()` still promotes the viewer and increments ownership epoch because it checks only route attachment/generation, not authoritative PTY liveness.

The route may already be marked `active=False`, but writer ownership still changes and a `pi_session_ownership` notification is sent for a dead session.

### Fresh deterministic reproduction

REVIEW attached writer A and viewer B to one real registry/TerminalManager session, then wrapped only `registry.get()` so that:
- it first returns the session as running;
- immediately invokes the real PTY exit callback with code 9;
- then the actual `pi_session_takeover` continues.

Observed:

`err None`

`active False`

`writer_is_b True`

`epoch 2`

B received:

`pi_session_ownership { role: "writer", ownershipEpoch: 2 }`

The assertion that takeover must fail after PTY exit failed.

This is a concrete liveness/ownership race inside PI-T006, not PI-T007 lifecycle work.

## Required correction

Make takeover authoritative-liveness validation atomic with ownership transfer.

Use the same lock order already established:

**TerminalManager lock -> WebSocketHub lock**.

Minimal shape:
1. enter `terminal.lock`;
2. resolve/revalidate sessionId + expected generation + running state against TerminalManager;
3. while still holding terminal lock, enter hub lock and perform takeover only if the route is still attached to that exact generation;
4. release locks;
5. send ownership notices outside hub lock.

Do not:
- restart Pi;
- auto-reattach;
- persist ownership;
- add PI-T007 behavior.

Add a deterministic regression that exits the PTY after the initial registry view but before takeover ownership mutation and proves:
- takeover raises stale/stopped-session error;
- writer remains unchanged or no writer if exit cleanup already released it;
- ownership epoch does not advance due takeover;
- no new `pi_session_ownership` writer notification is sent for the stopped session.

## Lock-order review

The corrected input/key/resize path and attach path now consistently use:

`terminal.lock -> hub.lock`.

Takeover currently uses no terminal lock. Bringing takeover into the same order is the narrowest fix and reduces the number of ownership paths with different synchronization rules.

Socket sends should remain outside hub lock.

## Complexity / YAGNI

Ponytail review found no unnecessary abstraction worth removing. The new `_pi_writer_target_locked()` exists for callers already holding hub lock and is justified by the required atomic writer path.

**Lean already. Ship.**

## Other review dimensions

- **Correctness:** R19-1/R19-2 fixed; blocked by R20-1.
- **Scope drift:** none.
- **UX:** no browser UI in this slice, correctly.
- **Maintainability/module separation:** route state remains in hub; process liveness remains in TerminalManager. Cross-owner operations must share one lock order.
- **Scalability:** no duplicate output/history buffers.
- **Native Pi parity:** transport remains byte-transparent; physical/browser parity stays unmeasured.
- **Concurrency isolation:** improved, but takeover liveness is still non-atomic.
- **Auth/security:** existing terminal auth reused; no new token/LAN/argv/env exposure.
- **Regression/performance:** focused contract/regression suites are green; no CPU/RSS/latency claim.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate.
- PI-T005 COMPLETE.
- PI-T004 COMPLETE / committed.
- PI-T006: **not accepted** due R20-1.
- PI-T007+ remain not authorized.
- application wiring, browser F5/live reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix R20-1 only: make takeover liveness/generation validation atomic with ownership transfer using the established TerminalManager->Hub lock order, and add the deterministic exit-between-view-and-takeover regression. Do not start PI-T007 or any runtime/UI/persistence work.

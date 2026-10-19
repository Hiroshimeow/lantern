# REVIEW turn 40 — route-repair handoff did not address R39 viewer-only takeover defect

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 40  
Assigned handoff reviewed: DEV turn 41  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. DEV turn 41 explicitly performed route-response repair only and made no source/test changes. The blocking R39-1 defect from REVIEW turn 39 remains reproducible in the current workspace: an already-current writer can call `pi_session_takeover` successfully even though PLAN requires takeover to be viewer-only.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 41 handoff.
- REVIEW turn 39.
- PLAN turn 11 explicit takeover contract.
- Current `lantern/ws.py` takeover implementation.
- Current repository status/diff.
- Fresh current PI-T006 and related regression tests.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh checks:
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
- DEV turn 41 reports no source/test edits, and current Git truth is consistent with the previously reviewed candidate.
- no PI-T007, runtime/UI/persistence, Markdown implementation, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift detected.

## Prior R38 correction remains covered by current suite

Fresh current PI-T006 suite:

`uv run python -m unittest -q tests.test_pi_ws_contract`

Result:
- 35 tests;
- all OK;
- 1.692 s;
- exit 0.

Fresh related PI/Terminal/auth/LAN regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 63 tests;
- all OK;
- 12.137 s;
- exit 0.

These green suites still do not include the viewer-only negative takeover case below.

## R39-1 — STILL OPEN: current writer self-takeover is accepted

**PLAN contract**

PLAN turn 11 states:

`pi_session_takeover`
- requires the peer already be attached **as a viewer**;
- requires matching PTY generation;
- promotes requester to writer;
- prior writer becomes viewer;
- increments ownership epoch.

Therefore an already-current writer is not a valid takeover requester.

**Current source**

`WebSocketHub._pi_takeover_locked()` currently contains:

`if route.get("writer") is peer:`
`    return route["epoch"], []`

That accepts current-writer takeover as a successful no-op.

## Fresh deterministic reproduction

REVIEW again exercised the production dispatch path using:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY only.

Sequence:
1. attach one peer as first writer;
2. record epoch 1;
3. same peer calls `pi_session_takeover`.

Fresh result:

`error None`

`epoch_before 1 epoch_after 1 writer_same True`

The proof assertion failed:

`current writer takeover unexpectedly accepted`.

So R39-1 remains present in current source after DEV turn 41.

## Required correction

Restore the explicit viewer-only precondition.

Minimal correction:
- if requester is already current writer, raise `PiSessionPermissionError`;
- keep writer unchanged;
- keep epoch unchanged;
- emit no ownership notices;
- touch no PTY state.

Add deterministic regression:
1. first peer attaches as writer;
2. same peer sends `pi_session_takeover`;
3. request raises PermissionError;
4. writer identity unchanged;
5. epoch unchanged;
6. no ownership notification;
7. PTY untouched.

Preserve:
- viewer takeover success;
- epoch increment on real viewer takeover;
- prior writer demotion to viewer;
- stale generation rejection;
- exit/takeover and writer-actuation race protections;
- R22-R38 fixes.

## Complexity / ponytail review

Non-blocking reductions remain in `lantern/ws.py`:

- `L353,L366,L462-471`: delete unread `route["active"]` state and terminal-list updater. Nothing replaces it.
- `L420-422`: delete unused public `pi_takeover()` wrapper. Dispatch uses `_pi_takeover_locked()`.
- `L444-450`: delete unused public `pi_writer_target()` wrapper. Dispatch uses `_pi_writer_target_locked()`.

**net: -22 lines possible.**

Do not combine these cleanup changes with the correctness repair unless independently reverified.

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
- PI-T006: **NOT ACCEPTED due open R39-1**.
- PI-T007+ remain unauthorized.
- runtime application injection, browser F5/live reconnect, restart persistence/reopen, physical FJP input, real POSIX runtime, model/goal/extensions parity, and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** DEV turn 41 was only a routing repair; the prior concrete takeover defect remains. Fix R39-1 and add the viewer-only negative regression before another REVIEW/TEST handoff.

# REVIEW turn 25 — R24 exit generation fix works; old-generation output can still be dropped before hub delivery

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 25  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R24-1 is resolved for exit events: terminal_exit now carries PTY generation and old-generation Pi exits survive same-ID replacement. However an analogous generation-scoping race still exists for terminal_output: output emitted by the old Pi generation can be dropped if the same terminal ID is replaced before WebSocketHub receives that output event.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 25 handoff.
- REVIEW turn 24 R24-1.
- Current diffs in:
  - `lantern/terminal.py`
  - `lantern/pi_sessions.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_ws_contract.py`
- PLAN turn 11 output/exit scoping requirements.
- Current TerminalManager output/exit event ordering.
- Current WebSocketHub route generation/active handling.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current PI-T006 candidate paths:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application/runtime wiring, frontend/UI, Markdown, dependency/vendor, LAN/auth-policy, or Spec 001 T2 work was introduced.

## R24-1 — generation-scoped terminal exit routing: RESOLVED

TerminalManager now adds `generation` to live-generation exit events for:
- natural PTY exit;
- explicit `kill()`;
- `kill_if_generation()`.

WebSocketHub now requires exact:
- terminal ID; and
- generation

before converting a terminal exit to `pi_session_exit`.

For exit events, route `active` is intentionally not required, so a delayed old-generation exit still reaches peers even if a replacement generation already caused the route to become inactive.

Fresh targeted REVIEW verification:
- `test_old_generation_exit_survives_terminal_id_replacement_before_broadcast`: PASS.
- `test_replacement_generation_rejects_old_attachment_without_touching_new_pty`: PASS.

Fresh full PI-T006 contract:
- 15 tests;
- all OK;
- 1.060 s.

Related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 10.278 s.

`git diff --check`: exit 0.

So the exact R24 exit defect is fixed.

## Finding R25-1 — old-generation terminal_output can be dropped if same-ID replacement occurs before hub delivery

**Locations**
- `lantern/terminal.py:_queue_output()`
- `lantern/ws.py:WebSocketHub.broadcast()` terminal-output routing

**PLAN invariant**

PLAN turn 11 requires:
- only peers attached to the exact sessionId + PTY generation receive Pi output;
- seq/data are preserved;
- replacement generation must not receive or mask stale-generation traffic.

The output event already carries generation:

`terminal_output {terminalId, generation, seq, data}`.

But WebSocketHub currently routes terminal_output only when:
- terminal ID matches;
- generation matches;
- **route.active is true**.

`route.active` is recomputed from the latest `terminal_list` state by terminal ID + generation.

## Current race

TerminalManager output flow is:
1. under TerminalManager lock, append old-generation data and increment seq;
2. release lock;
3. emit `terminal_output` to the hub.

Between steps 2 and 3, another thread can:
1. remove old generation;
2. create a replacement under the same terminal ID;
3. replacement terminal-list updates the route to `active=False`.

When the already-created old-generation `terminal_output` finally reaches the hub:
- terminal ID matches route;
- generation matches route;
- but `active=False`;
- hub drops the old-generation output.

That loses bytes which were already accepted into the old generation's retained stream.

## Fresh deterministic reproduction

REVIEW used:
- real PiSessionRegistry;
- real TerminalManager;
- real WebSocketHub/dispatch;
- fake PTY only.

Sequence:
1. create and attach Pi session `sess`;
2. old Pi PTY emits `FINAL-BYTES`;
3. after TerminalManager creates the old-generation terminal_output event but before hub receives it:
   - old generation is removed without emitting an exit;
   - a new ordinary terminal is created under the same internal terminal ID;
4. the delayed old terminal_output is then delivered to WebSocketHub.

Fresh result:

`pi_output_events []`

replacement remains live with a different generation.

route:
- `active=False`;
- route generation remains the old Pi generation.

The proof assertion failed:

`attached Pi peer missed old-generation output that was emitted before replacement`.

## Why this is material

The output event already has exact generation identity. Once the event exists, `route.active` should not be used to infer whether that event belongs to the attached old generation.

A later terminal-list state should not retroactively invalidate a generation-tagged output event that was emitted by the old process before replacement.

This is the output analogue of R24-1.

## Required correction

Route `terminal_output` by exact:

`terminalId + generation`

without additionally requiring current `route.active` for an already-generation-tagged event.

Keep `route.active` for:
- attach/liveness/status bookkeeping;
- deciding whether the route currently maps to a live PTY.

But do not use current active state to suppress an event whose own generation already proves it belongs to the attached route.

Add deterministic regression:
- attach old Pi generation;
- delay its terminal_output after TerminalManager emitted it;
- replace the same terminal ID with a different generation before hub receives the delayed event;
- assert old attached peer receives exactly the old-generation output with original seq/data;
- assert wrong-session peer receives none;
- assert replacement remains live and receives no mislabeled output.

Also preserve:
- replacement-generation output must not be sent to old Pi route;
- ordinary terminal subscription behavior;
- no duplicate generic + Pi delivery.

## Concurrency / module-separation review

No new lock or state owner is needed.

TerminalManager already stamps output with generation. WebSocketHub should trust that event identity for routing.

This is a routing predicate correction only.

## Complexity / YAGNI

Turn-25 exit-generation change is appropriately narrow.

Non-blocking dead code remains:
- unused `WebSocketHub.pi_takeover()` wrapper;
- unused `WebSocketHub.pi_writer_target()` wrapper.

`net: -6 lines possible.`

No other complexity finding is material.

## Other review dimensions

- **Correctness:** R24-1 fixed; blocked by R25-1.
- **Scope drift:** none.
- **UX:** no browser/UI claim.
- **Maintainability/module separation:** generation-tagged process events should be routed from event identity, not mutable later liveness state.
- **Scalability:** no additional history/output store required.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** generic control and exit races are fixed; delayed output vs replacement remains.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused contract/regression suites are fresh green; no release performance claim.

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
- PI-T006: **not accepted** due R25-1.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R25-1: generation-tagged terminal_output must survive same-ID replacement between TerminalManager emission and hub delivery. Add the deterministic delayed-output replacement regression and preserve all accepted R22-R24 protections. Do not start PI-T007 or runtime/UI/persistence work.

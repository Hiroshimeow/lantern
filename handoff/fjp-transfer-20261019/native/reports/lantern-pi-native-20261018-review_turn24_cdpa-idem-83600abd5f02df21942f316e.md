# REVIEW turn 24 — R23 generic-control atomicity fixed; Pi exit scoping still races terminal-ID replacement

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 24  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R23-1 is resolved: generic Terminal ownership validation and actuation now occur under the same TerminalManager RLock. However a separate PI-T006 generation-scoping race remains in `terminal_exit` delivery: if the terminal ID is replaced before the old generation's exit event reaches WebSocketHub, attached Pi peers can miss the required scoped exit event entirely.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 24 handoff.
- REVIEW turn 23 R23-1.
- Current diffs in:
  - `lantern/terminal.py`
  - `lantern/pi_sessions.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_pi_ws_contract.py`
- PLAN turn 11 PI-T006 output/exit scoping and stale-generation requirements.
- Existing TerminalManager exit event shape and WebSocketHub route-generation handling.
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
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application/runtime wiring, frontend/UI, Markdown, dependency/vendor, LAN/auth-policy, or Spec 001 T2 work was introduced.

## R23-1 — generic ownership check vs actuation: RESOLVED

Generic `terminal_create/run/input/key/resize/kill` dispatch now:
1. derives terminal ID;
2. enters `terminal.lock`;
3. validates `_guard_generic_terminal_control()`;
4. performs the actual TerminalManager operation before releasing that same RLock.

This binds authorization to the same live-generation ownership boundary as actuation.

Socket replies for create/run are sent only after the TerminalManager lock is released.

No WebSocketHub lock was added to the generic path, so the established Pi lock order is unchanged.

## Fresh R23 verification

Fresh targeted suite:
- `test_generic_control_authorization_is_atomic_with_actuation`: PASS.
- `test_generic_controls_are_blocked_during_pi_create_publication_window`: PASS.
- `test_generic_terminal_controls_still_work_for_ordinary_and_replacement_generations`: PASS.

Result:
- 3 tests;
- all OK;
- exit 0.

Full PI-T006 contract:
- `tests.test_pi_ws_contract`: 14 tests;
- all OK;
- 1.044 s.

Related registry/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 9.008 s.

`git diff --check`: exit 0.

So:
- Pi-create publication ownership stays protected;
- ordinary->Pi replacement cannot be reached by stale generic authorization;
- ordinary replacement generations remain controllable.

## Finding R24-1 — old Pi generation exit can be lost if terminal ID is replaced before exit broadcast

**Locations**
- `lantern/terminal.py:_handle_exit()`
- `lantern/ws.py:WebSocketHub.broadcast()` terminal-exit routing

**PLAN invariant**

PLAN turn 11 requires:

- attached peers receive a scoped Pi session exit/status event on terminal exit;
- no peer for another session receives it;
- generation is part of Pi session identity;
- replacement process must remain untouched by stale-generation activity.

**Current event shape**

`TerminalManager._handle_exit()` emits:

`{"type":"terminal_exit","terminalId": entry.id,"exitCode": code}`

It does **not** include the exiting generation.

WebSocketHub routes `terminal_exit` by terminal ID and current route activity, but cannot prove the event belongs to the route's generation.

This becomes observable if the same terminal ID is replaced before the old exit event reaches the hub.

## Fresh deterministic reproduction

REVIEW used:
- real PiSessionRegistry;
- real TerminalManager;
- real WebSocketHub/dispatch;
- fake PTY only.

Sequence:
1. create/attach Pi session `sess`;
2. old Pi PTY invokes its real exit callback with code 7;
3. after TerminalManager removes old generation but **before** WebSocketHub receives that exit event, the test creates a new ordinary terminal with the same internal terminal ID `pi:sess`;
4. normal hub broadcast continues.

Fresh result:

`pi_exit_events []`

`replacement_live [('7b0dfcc3819b45a09318b29a8f1e1f2e', True)]`

`route_active False`

The attached Pi peer received **no** `pi_session_exit` for the old generation.

The proof assertion failed:

`attached Pi peer missed old-generation exit when terminal ID was replaced before exit broadcast`

This is a real PI-T006 generation-scoping defect.

## Why this happens

The terminal-list emission for the replacement generation updates the Pi route's `active` state before the stale old-generation exit is broadcast.

Because `terminal_exit` lacks generation:
- hub cannot identify the event as belonging to the attached old Pi generation;
- current route activity/terminal-ID state is insufficient;
- the required old-generation scoped exit event is dropped.

Using terminal ID alone is not enough under generation reuse.

## Required correction

Carry generation on `terminal_exit` and route Pi exit notifications by exact:

`terminalId + generation`.

Minimal shape:
- `TerminalManager._handle_exit()` includes `generation: entry.generation`;
- explicit kill/conditional-kill exit events also include the killed entry's generation;
- WebSocketHub emits `pi_session_exit` only when both terminal ID and generation match the route;
- replacement generations remain untouched and must not receive/mask the stale generation's exit.

Preserve ordinary Terminal exit behavior/compatibility.

Add a deterministic regression matching the reproduction:
- attach old Pi generation;
- exit it;
- create a replacement generation under the same internal terminal ID before hub sees old exit;
- assert attached peer still receives exactly one `pi_session_exit` for the old generation;
- assert replacement remains live and unaffected;
- assert no wrong-session peer receives the exit.

Do not add persistence/restart/UI behavior.

## Concurrency / module-separation review

This fix belongs at the existing process-event boundary:
- TerminalManager already owns generation identity;
- WebSocketHub already owns Pi session routing.

No new registry, queue, or locking abstraction is needed.

## Complexity / YAGNI

The turn-24 atomic generic-control change is appropriately small.

Non-blocking dead code remains:
- unused `WebSocketHub.pi_takeover()` wrapper;
- unused `WebSocketHub.pi_writer_target()` wrapper.

`net: -6 lines possible.`

This is not material to acceptance.

## Other review dimensions

- **Correctness:** R23-1 fixed; blocked by R24-1.
- **Scope drift:** none detected.
- **UX:** no browser/UI claim.
- **Maintainability/module separation:** generation identity must travel with terminal lifecycle events; routing by current terminal ID alone is insufficient.
- **Scalability:** no extra output/history store needed.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** generic process-control races are fixed; exit/replacement generation race remains.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused PI/Terminal/auth/LAN suites are fresh green; no release performance claim.

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
- PI-T006: **not accepted** due R24-1.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R24-1: make terminal exit generation-scoped end-to-end and add the replacement-between-exit-and-broadcast regression. Preserve the accepted R22/R23 generic-control fixes. Do not start PI-T007 or runtime/UI/persistence work.

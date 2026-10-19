# REVIEW turn 27 — T11 attached-session scoping fixed; route-less Pi generations still leak generic exit/output

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 27  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. TEST T11-1 is fixed for Pi generations that already have a WebSocketHub Pi route, and generic live/retained replay is correctly blocked by TerminalManager ownership. But Pi output/exit suppression is still keyed only to existing `hub.pi_routes`. A Pi session that has never been Pi-attached has no route, so generic `terminal_exit` still reaches every terminal-authorized peer; a legacy peer also receives raw generic `terminal_output`. This is a concrete session-scoping defect.

No implementation edits made by REVIEW.

## Inputs independently checked

- TEST turn 11 T11-1.
- DEV turn 27 handoff.
- REVIEW turn 26 accepted race/scoping boundaries.
- PLAN turn 11 PI-T006 output/exit isolation and ordinary Terminal compatibility contract.
- Current candidate:
  - `lantern/pi_sessions.py`
  - `lantern/terminal.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_ws_contract.py`
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- worktree remains exactly:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, live Lantern :9999, or CDPA scope drift.

## What DEV turn 27 fixed correctly

### Generic subscribe/replay authorization

`terminal_subscribe` now calls the existing Pi-owner guard before:
- replay capture;
- generic subscription registration.

For this read/replay path, `TerminalManager.control_owner(..., include_history=True)` checks:
1. current live entry first;
2. retained history when no live entry exists.

This means both:
- live Pi-owned generation replay; and
- retained stopped Pi history

are denied through generic Terminal subscribe.

Fresh independent retained-history probe:
- create Pi session with no Pi WebSocket attach;
- emit retained output;
- exit session;
- attempt generic `terminal_subscribe`.

Observed:

`PiSessionPermissionError: Pi terminal control requires Pi session writer ownership`

Probe result:

`retained_pi_history_guard_ok`.

So generic replay itself is correctly closed even when no Pi route exists.

### Attached-route generic output/exit suppression

When a `terminal_output` or `terminal_exit` event matches an existing Pi route by exact:
- terminalId;
- PTY generation,

WebSocketHub now:
- delivers one scoped `pi_session_output` / `pi_session_exit` to route peers;
- marks the event Pi-scoped;
- prevents all other peers from receiving the generic Terminal form.

This fixes the exact TEST turn-11 reproduction where:
- A is Pi-attached to session A;
- B is Pi-attached only to B;
- an unattached authenticated peer exists;
- B/unattached cannot subscribe to A;
- B/unattached do not receive A generic output/exit;
- A receives exactly the scoped Pi event;
- ordinary Terminal subscribe/replay/output/exit remains available.

Fresh existing regression:

`test_pi_generation_cannot_escape_through_generic_subscribe_output_or_exit`

Result:
- 1 test;
- OK;
- 0.007 s.

Full current PI-T006 contract:
- 17 tests;
- all OK;
- 1.045 s.

Related registry / Terminal / auth / LAN regressions:
- 63 tests;
- all OK;
- 10.614 s.

Syntax and `git diff --check` both exit 0.

These green tests do not exercise a Pi generation before its first Pi attach.

## Finding R27-1 — generic Pi exit/output leakage when no Pi route has ever been created

**Location:** `lantern/ws.py:350-406`, `WebSocketHub.broadcast()`.

**Required invariant**

PLAN turn 11 requires Pi output/exit to be scoped to peers attached to the matching `sessionId + PTY generation`.

TEST turn 11 further clarified the acceptance boundary:
- generic Terminal replay/output/exit must not disclose a Pi-owned generation to nonattached Pi peers;
- this must not depend on hiding the internal terminal ID.

DEV turn 27 protects generic replay from TerminalManager ownership, but generic event suppression depends on:

`hub.pi_routes`

rather than the process-owned `control_owner="pi"` identity.

**Current behavior**

A Pi session exists and its TerminalEntry is already tagged:
- `control_owner == "pi"`.

But `WebSocketHub.pi_routes` is created only by `pi_session_attach`.

If the Pi session has never been attached:
- no route exists;
- `pi_scoped_event` remains false;
- `terminal_exit` falls through to ordinary generic broadcast;
- terminal-authorized v2 peers receive the generic exit;
- legacy peers receive both raw generic output and exit.

This creates a route-existence gap in the intended Pi scoping boundary.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub`;
- fake PTY I/O only.

No peer called `pi_session_attach`.

Sequence:
1. create Pi session `noattach`;
2. confirm `noattach not in hub.pi_routes`;
3. connect one terminal-authorized v2 peer and one terminal-authorized legacy peer;
4. Pi PTY emits `SECRET`;
5. Pi PTY exits with code 17.

Fresh observed output:

`v2_exit [{'type': 'terminal_exit', 'terminalId': 'pi:noattach', 'generation': '<pi-generation>', 'exitCode': 17}]`

`legacy_output [{'type': 'terminal_output', 'terminalId': 'pi:noattach', 'generation': '<pi-generation>', 'seq': 1, 'data': 'SECRET'}]`

`legacy_exit [{'type': 'terminal_exit', 'terminalId': 'pi:noattach', 'generation': '<pi-generation>', 'exitCode': 17}]`

The independent assertion failed:

`unattached v2 peer received generic Pi exit before any Pi route existed`.

This is reproducible with current source.

## Why this is material

The process is already unambiguously Pi-owned at the TerminalManager boundary before any browser attaches.

Pi attachment state should determine who receives the scoped Pi payload, but it must not determine whether a Pi-owned process is treated as ordinary Terminal traffic.

Otherwise:
- zero attached Pi peers means generic exit leakage;
- legacy authorized peers can receive Pi raw output despite having no Pi attachment;
- the scoping guarantee changes based on whether some other browser happened to attach first.

That is not a stable one-session routing contract.

## Required correction

Make Pi event classification independent of whether a Pi route already exists.

Minimal acceptable direction:
- carry a non-public/internal process-owner marker on TerminalManager `terminal_output` / `terminal_exit` events from the exact TerminalEntry generation; and
- in WebSocketHub:
  - if owner is Pi, never deliver generic output/exit;
  - if an exact Pi route exists, deliver the scoped Pi payload only to its attached peers;
  - if no route exists, deliver the event to no peer;
  - keep ordinary Terminal events unchanged.

Equivalent generation-bound classification is acceptable, but do not use terminal-ID prefix as authorization truth.

Do not expose the internal owner marker to clients.

Add deterministic regression:
1. create a Pi session;
2. do **not** Pi-attach any peer;
3. connect terminal-authorized v2 and legacy peers;
4. emit Pi output and exit;
5. assert neither receives generic Pi output/exit;
6. then separately prove ordinary terminal output/exit remains unchanged.

Also preserve:
- live/retained generic subscribe denial for Pi generations;
- TEST T11 attached-route scoping;
- delayed old-generation R24/R25 output/exit delivery to old attached peers after same-ID replacement;
- replacement-generation isolation.

## Concurrency / module-separation review

No new registry/hub lifecycle coupling is required.

TerminalManager already owns:
- exact PTY generation;
- `control_owner`;
- output/exit event creation.

Therefore process classification should travel with the event identity rather than be inferred from later route state.

WebSocketHub should continue to own only:
- peer attachment;
- writer/viewer ownership;
- conversion to Pi-scoped client events.

This avoids introducing PI-T007 persistence or a second session/process truth source.

## Complexity / over-engineering review

Current pre-existing dead code remains removable and is non-blocking relative to R27-1:

- `lantern/ws.py:L288`: delete: unread `route["active"]` initial field. Nothing replaces it.
- `lantern/ws.py:L299`: delete: unread replacement-route `active=True`. Nothing replaces it.
- `lantern/ws.py:L355-362`: delete: terminal-list scan whose only effect is updating unread `route["active"]`. Nothing replaces it.
- `lantern/ws.py:L328-330`: delete: unused `pi_takeover()` wrapper. Locked dispatch path uses `_pi_takeover_locked()`.
- `lantern/ws.py:L346-348`: delete: unused `pi_writer_target()` wrapper. Locked dispatch path uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

These are cleanup only; they do not repair R27-1.

## Other required review dimensions

- **Correctness:** attached-route T11 scoping and generic replay denial are fixed; R27-1 remains blocking.
- **Scope drift:** none detected.
- **UX:** no browser/UI acceptance inferred.
- **Maintainability/module separation:** process-owner classification must come from TerminalManager, not browser-route existence.
- **Scalability:** no new replay/output store is needed.
- **Native Pi parity:** unchanged; raw bytes are not parsed or transformed.
- **Concurrency isolation:** prior publication/generic-control/attach/takeover/writer/output/exit replacement races remain covered; route-less event classification is the remaining defect.
- **Auth/security:** this is Pi session-scoping, not a new authentication bypass.
- **Regression/performance:** focused suites are fresh green; no release CPU/RSS/latency acceptance is claimed.

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
- PI-T006: **NOT ACCEPTED due R27-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R27-1: classify generation-tagged Pi output/exit from TerminalManager ownership even before the first Pi route exists, suppress generic delivery in that state, and add the route-less v2/legacy regression. Preserve T11 attached-route scoping, retained-history replay denial, R22-R25 race protections, and ordinary Terminal behavior. Do not start PI-T007 or runtime/UI/persistence work.

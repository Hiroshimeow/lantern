# REVIEW turn 28 — route-less live events fixed; legacy fallback snapshot still exposes Pi replay output

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 28  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R27-1 is fixed for live generation-tagged output/exit: TerminalManager now stamps an internal owner marker and WebSocketHub suppresses generic Pi-owned events even when no Pi route exists. However the legacy fallback snapshot still reads `TerminalManager.replay()` directly and includes Pi-owned retained output. A legacy terminal-authorized peer can therefore receive Pi session replay bytes without any Pi attachment.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 28 handoff.
- REVIEW turn 27 R27-1.
- PLAN turn 11 PI-T006 output/session isolation and legacy-path compatibility contract.
- Current candidate source/tests:
  - `lantern/pi_sessions.py`
  - `lantern/terminal.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_ws_contract.py`
- Current legacy fallback path `_legacy_snapshot_payload()` / `legacy_fallback()`.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- worktree candidate remains exactly:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, live Lantern :9999, or CDPA scope drift.

## R27-1 — route-less live output/exit classification: RESOLVED

TerminalManager now stamps generation-tagged process events with an internal-only:

`_controlOwner: entry.control_owner`.

This is added to:
- `terminal_output`;
- natural `terminal_exit`;
- explicit kill exit;
- generation-conditional kill exit.

WebSocketHub classifies:

`message["_controlOwner"] == "pi"`

as Pi-scoped even when no `pi_routes` entry exists.

For such events:
- exact matching Pi route peers receive one scoped `pi_session_output` / `pi_session_exit`;
- all other peers skip generic `terminal_output` / `terminal_exit`;
- if no Pi route exists, no peer receives the event.

Before any ordinary generic send, `_controlOwner` is stripped from the client payload.

This is the correct process-owner classification boundary for live events and does not depend on terminal-ID prefix or route existence.

The new route-less regression covers v2 and legacy peers for live output/exit and is green.

## Fresh existing verification

Fresh current tests run by REVIEW:

`uv run python -m unittest -q tests.test_pi_ws_contract`
- 18 tests;
- all OK.

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_terminal_auth tests.test_lan_multi_perf`
- 63 tests;
- all OK.

Syntax:
- `py_compile` for Terminal/Pi registry/WS and affected tests: exit 0.

`git diff --check`:
- exit 0.

These green tests do not exercise the legacy initial snapshot path.

## Finding R28-1 — legacy fallback snapshot still exposes Pi-owned retained output

**Locations**
- `lantern/ws.py:429-437` — `_legacy_snapshot_payload(terminal)`.
- `lantern/ws.py:480-494` — delayed `legacy_fallback()`.

**Required invariant**

PLAN turn 11 requires:
- Pi output never leaks across sessions;
- unaffiliated peers must not receive Pi session output;
- ordinary legacy Terminal behavior remains unchanged for ordinary terminals.

The prior TEST/REVIEW findings established that knowing the internal terminal ID is not authorization to read Pi bytes.

**Current legacy path**

`_legacy_snapshot_payload()` does:

`output = dict(terminal.replay())`

and sends every retained terminal tail to a legacy peer.

`TerminalManager.replay()` currently returns output for all live/history entries with output and does not filter `control_owner == "pi"`.

Therefore the legacy fallback bypasses:
- generic `terminal_subscribe` Pi-owner guard;
- WebSocketHub live-event Pi classification;
- Pi attach/session scoping.

This happens even if the Pi session has never had a Pi WebSocket route.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub`;
- fake PTY I/O only.

Sequence:
1. create Pi session `legacy`;
2. emit retained Pi output `PI-SECRET-SNAPSHOT`;
3. create ordinary terminal and emit `ORDINARY-SNAPSHOT`;
4. call the production `_legacy_snapshot_payload(terminal)`.

Fresh observed payload:

`snapshot_output {'pi:legacy': 'PI-SECRET-SNAPSHOT', 'ordinary': 'ORDINARY-SNAPSHOT'}`

`snapshot_terminals ['pi:legacy', 'ordinary']`

The assertion failed:

`legacy snapshot exposed Pi-owned replay output`.

So a legacy fallback client can receive Pi retained bytes without `pi_session_attach`.

## Why this is material

Turn 28 closes live generic output/exit, but replay confidentiality is still inconsistent across protocol versions:

- v2 generic `terminal_subscribe`: Pi live/history replay denied;
- live v2/legacy broadcast events: Pi-owned generic delivery suppressed;
- legacy fallback snapshot: Pi retained replay still exposed.

A protocol-version fallback must not become an alternate Pi replay channel.

PLAN explicitly allows generic terminal-list hiding of Pi sessions to remain deferred, so the terminal metadata ID may still appear in the legacy snapshot's `terminals` list. The blocking defect is retained **output bytes**, not list visibility.

## Required correction

Filter Pi-owned entries out of legacy replay output while preserving ordinary legacy Terminal output.

Minimal direction:
- add a narrow TerminalManager replay helper/filter capable of excluding entries whose `control_owner == "pi"`; or
- build the legacy output tail from TerminalManager-owned entries under the existing lock while excluding Pi-owned generations.

Do not:
- hide all Pi terminal metadata as the primary fix;
- change ordinary legacy terminal tails;
- add new auth/LAN policy;
- add registry lookup as a second process-owner truth source;
- start PI-T007.

Add deterministic regression:
1. create route-less Pi session with retained output;
2. create ordinary terminal with retained output;
3. run legacy fallback snapshot;
4. assert ordinary retained output is present and unchanged;
5. assert Pi retained output is absent;
6. preserve existing ordinary truncation behavior.

Also preserve:
- route-less live Pi output/exit suppression;
- attached Pi scoped output/exit;
- delayed old-generation R24/R25 delivery;
- retained Pi v2 generic-subscribe denial.

## Concurrency / module-separation review

No new lock topology is needed.

TerminalManager already owns:
- retained output;
- generation;
- control owner.

Legacy replay filtering should remain at that ownership boundary or use a read helper provided by it.

## Complexity / over-engineering review

Pre-existing dead code remains non-blocking:

- `lantern/ws.py:L288`: delete: unread `route["active"]` initial field.
- `lantern/ws.py:L299`: delete: unread replacement `active=True`.
- `lantern/ws.py:L360-367`: delete: terminal-list scan whose only effect is updating unread `route["active"]`.
- `lantern/ws.py:L328-330`: delete: unused `pi_takeover()` wrapper.
- `lantern/ws.py:L346-348`: delete: unused `pi_writer_target()` wrapper.

**net: -16 lines possible.**

These are cleanup only and do not repair R28-1.

## Other required review dimensions

- **Correctness:** R27-1 fixed for live events; blocked by R28-1 legacy replay leakage.
- **Scope drift:** none detected.
- **UX:** no browser/UI acceptance inferred.
- **Maintainability/module separation:** process-owner filtering belongs with TerminalManager retained-output ownership.
- **Scalability:** no additional replay store is required.
- **Native Pi parity:** unchanged; bytes are not parsed/transformed.
- **Concurrency isolation:** prior create/ownership/attach/takeover/output/exit races remain covered; legacy snapshot bypass is protocol-path isolation, not a new lock race.
- **Auth/security:** same terminal auth gate remains; this is Pi session-scoping, not a new authentication mechanism.
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
- PI-T006: **NOT ACCEPTED due R28-1**.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R28-1: prevent Pi-owned retained output from entering the legacy fallback snapshot while preserving ordinary legacy replay/truncation behavior. Add the deterministic mixed Pi/ordinary legacy snapshot regression. Preserve all R22-R27 protections and do not start PI-T007/runtime/UI/persistence work.

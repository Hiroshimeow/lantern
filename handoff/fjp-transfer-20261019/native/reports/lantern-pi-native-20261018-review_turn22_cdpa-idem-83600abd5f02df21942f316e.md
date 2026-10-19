# REVIEW turn 22 — generic Terminal guard still has Pi-create publication race

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 22  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. TEST T10-1 is fixed for already-published registry sessions and stale replacement generations, but a concrete creation-window bypass remains: a Pi PTY can be live in TerminalManager before PiSessionRegistry publishes its session metadata, and generic terminal_input is then allowed into that live Pi process.

No implementation edits made by REVIEW.

## Inputs independently checked

- TEST turn 10 T10-1.
- DEV turn 22 handoff.
- Current `lantern/ws.py` generic-control guard.
- Current `tests/test_pi_ws_contract.py` generic-control regressions.
- `PiSessionRegistry.create()` publication order.
- `TerminalManager.create_argv()` live-entry publication order.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate:
  - `M lantern/ws.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, app/runtime wiring, frontend/UI, Markdown, dependency/vendor, LAN/auth-policy or Spec 001 T2 scope drift.

## What DEV turn 22 fixed correctly

The new `_guard_generic_terminal_control(pi, terminal, terminal_id)` blocks generic:

- `terminal_create`
- `terminal_run`
- `terminal_input`
- `terminal_key`
- `terminal_resize`
- `terminal_kill`

when the current live TerminalManager generation exactly matches a running PiSessionRegistry record for the same terminal ID.

The generation match is important and correct: stale registry metadata for an old Pi generation does not permanently reserve the terminal ID if a later ordinary terminal reuses it with a new generation.

Fresh existing tests:
- `tests.test_pi_ws_contract`: 12 tests, all OK, 0.062 s.
- related registry/auth/LAN set: 40 tests, all OK, 5.750 s.
- `py_compile`: exit 0.
- `git diff --check`: exit 0.

These tests do not cover the publication race below.

## Finding R22-1 — generic control bypass during PiSessionRegistry create publication window

**Locations**
- `lantern/pi_sessions.py:96-125` — TerminalManager process creation completes before `self._sessions[session_id] = session`.
- `lantern/ws.py:587-607` — generic-control guard recognizes Pi ownership only by scanning already-published registry sessions.

**Required invariant**

PI-T006 single-writer/process-control ownership must hold across the reachable generic Terminal control surface for every live Pi-owned PTY, not only after registry metadata publication.

**Current order**

`PiSessionRegistry.create()` currently:
1. validates and creates the native session directory;
2. calls `TerminalManager.create_argv()`;
3. TerminalManager publishes the live `pi:<sessionId>` PTY;
4. `create_argv()` returns;
5. only afterward does PiSessionRegistry insert the session into `self._sessions`.

During the interval between steps 3 and 5:
- TerminalManager reports a live Pi PTY;
- PiSessionRegistry `list()` is still empty for that session;
- `_guard_generic_terminal_control()` sees no matching running Pi session and allows generic terminal control.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub` and production `dispatch`;
- fake PTY I/O only.

The test wrapped `TerminalManager.create_argv()` so that it paused **after** the live PTY was published but **before** `PiSessionRegistry.create()` stored the session record.

Verified during the pause:
- `reg.list() == []`;
- TerminalManager contains live `pi:race`.

Then an authenticated peer sent:

`terminal_input {terminalId:"pi:race", data:"BYPASS_DURING_CREATE"}`.

Fresh result:

`dispatch_error None`

`writes_before_registry_publish ['BYPASS_DURING_CREATE']`

After release, registry publication completed and reported the same Pi session running.

The proof assertion failed because generic input reached the live Pi before registry publication.

This is a real process-control ownership bypass, not merely metadata visibility.

## Required correction

Make Pi ownership discoverable atomically with live PTY publication, or make the generic guard recognize live Pi ownership from a TerminalManager-owned marker that exists before generic control becomes possible.

Acceptable minimal directions include:

- pass a server-internal ownership/classification marker into `TerminalManager.create_argv()` and store it on the live `TerminalEntry`, so generic control can reject Pi-owned generations directly at the process owner boundary; or
- an equivalent narrow atomic registration mechanism that makes the Pi generation protected before the live PTY is externally controllable.

Do **not** rely on terminal-ID prefixes alone as authorization truth.

Do **not**:
- hide terminal IDs as the primary fix;
- add a new auth/LAN policy;
- add PI-T007 persistence;
- add app/runtime UI wiring;
- redesign ordinary Terminal ownership.

Add a deterministic regression that pauses Pi creation after TerminalManager live publication but before registry publication and proves generic input/key/resize/kill/run/create cannot touch that live Pi generation.

Also preserve the stale-replacement-generation compatibility test.

## Concurrency / lock review

The new guard takes `terminal.lock` and calls `pi.list()`, whose status derivation re-enters the same TerminalManager RLock. That does not introduce a new hub->terminal cycle.

The defect is not deadlock; it is publication ordering / ownership visibility.

## Complexity / YAGNI

Ponytail review: the guard itself is narrow and justified. No new abstraction should be added beyond the minimum ownership marker/atomic publication needed to close R22-1.

The two unused six-line wrappers previously noted in turn 21 remain non-blocking cleanup only:
- unused `pi_takeover()` wrapper;
- unused `pi_writer_target()` wrapper.

`net: -6 lines possible.`

## Other review dimensions

- **Correctness:** blocked by R22-1.
- **Scope drift:** none detected.
- **UX:** no browser/UI claim.
- **Maintainability/module separation:** ownership truth should live where the PTY generation is owned, not depend on later registry publication timing.
- **Scalability:** no extra output/history storage is needed.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** existing attach/takeover/writer race fixes remain intact, but create-publication isolation is incomplete.
- **Auth/security:** this is writer/process-control authorization, not an auth bypass.
- **Regression/performance:** focused suites are fresh green; no release performance claim.

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
- PI-T006: **not accepted** due R22-1.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R22-1: make live Pi generation ownership visible atomically with TerminalManager publication so generic terminal controls cannot enter during registry create. Add the deterministic publication-window regression and preserve ordinary/replacement-generation compatibility. Do not start PI-T007 or runtime/UI/persistence work.

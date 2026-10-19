# REVIEW turn 23 — R22 publication fix works, but generic guard/actuation is still TOCTOU

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 23  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R22-1 is resolved: Pi ownership is now installed atomically with TerminalManager live-entry publication. However the generic Terminal guard releases TerminalManager.lock before the requested generic operation executes, so a terminal can change from ordinary to Pi-owned after authorization and before input/resize/kill/create/run actuation. A stale generic request can therefore still control the replacement Pi generation.

No implementation edits made by REVIEW.

## Inputs independently checked

- REVIEW turn 22 R22-1.
- DEV turn 23 handoff.
- Current diffs in:
  - `lantern/terminal.py`
  - `lantern/pi_sessions.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_pi_ws_contract.py`
- Current TerminalManager lock / live-generation semantics.
- Current generic WS dispatch control path.
- Current branch/base/status.
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
- no PI-T007, app/runtime wiring, frontend/UI, Markdown, dependency/vendor, LAN/auth-policy, or Spec 001 T2 work was introduced.

## R22-1 — Pi-create publication window: RESOLVED

The new TerminalEntry field:

`control_owner: Optional[str]`

is installed on the exact live entry at the same publication point as the PTY generation.

`PiSessionRegistry.create()` passes:

`control_owner="pi"`

through the accepted structured-spawn seam.

The generic Terminal control guard now asks the process owner directly:

`terminal.control_owner(term_id)`

instead of inferring Pi ownership from later registry publication.

This removes the previous interval where:
- TerminalManager already had a live Pi PTY;
- PiSessionRegistry had not yet published its session;
- generic Terminal operations were still allowed.

The new publication-window regression covers all six generic controls:
- terminal_input
- terminal_key
- terminal_resize
- terminal_kill
- terminal_run
- terminal_create

and is green.

The owner marker is not exposed through:
- TerminalManager list/info/replay metadata;
- Pi registry public views;
- WS payloads.

Stale registry metadata also no longer controls the guard; a later ordinary replacement generation defaults to `control_owner=None`.

## Fresh existing verification

Fresh commands run by REVIEW:

`uv run python -m unittest -q tests.test_pi_ws_contract`
- 13 tests;
- all OK.

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm`
- 32 tests;
- all OK.

`py_compile` for Terminal/Pi registry/WS and affected tests:
- exit 0.

`git diff --check`:
- exit 0.

These green tests do not cover the guard-to-actuation race below.

## Finding R23-1 — generic ownership check and generic actuation are not atomic

**Location**
- `lantern/ws.py`: `_guard_generic_terminal_control()` and the generic `terminal_create/run/input/key/resize/kill` dispatch branches immediately after it.

**Invariant**
Once a generic Terminal request is authorized against a specific live generation, it must not be allowed to actuate a later Pi-owned generation that replaces that target before the operation executes.

This is the same class of stale-authorization problem already fixed for Pi writer epoch operations in R19.

**Current flow**
1. generic request enters dispatch;
2. `_guard_generic_terminal_control()` acquires `terminal.lock`;
3. guard observes current entry as ordinary (`control_owner != "pi"`);
4. guard releases `terminal.lock`;
5. another thread can kill/replace the same terminal ID with a new Pi-owned generation;
6. generic branch calls `terminal.input/key/resize/kill/create/run`, which reacquires the TerminalManager lock internally;
7. operation applies to the new Pi generation.

The ownership decision and destructive/input actuation therefore refer to different possible generations.

## Fresh deterministic reproduction

REVIEW used:
- real TerminalManager;
- real WebSocketHub + production dispatch;
- fake PTY I/O only.

Setup:
1. create ordinary terminal `race`;
2. generic peer sends `terminal_input`;
3. during the guard's owner lookup, after the ordinary owner value is obtained but before guard returns, replace `race` with a new live Pi-owned generation;
4. allow dispatch to continue.

Fresh output:

`err None`

`owner_now pi`

`old_closed True new_writes ['STALE_GENERIC']`

The generic request was authorized against the old ordinary generation and then wrote into the replacement Pi generation.

The proof assertion failed exactly because the stale generic authorization crossed the generation/ownership change.

## Required correction

Make generic ownership validation and generic actuation atomic under the same TerminalManager ownership boundary.

Minimal direction:
- for generic `terminal_input/key/resize/kill`, hold `terminal.lock` across:
  1. current-entry owner check;
  2. current-entry/generation liveness;
  3. the actual TerminalManager operation.
- for generic `terminal_create/run`, hold the same TerminalManager lock across:
  1. existing target owner check;
  2. any replacement/kill/create sequence.

Because TerminalManager uses an RLock, its existing methods can be called while the outer lock is held.

Equivalent generation-bound APIs are acceptable if they guarantee the same atomicity.

Add deterministic regressions that:
- authorize against an ordinary generation;
- replace it with a Pi-owned generation before actuation would otherwise happen;
- prove stale generic input/resize/kill cannot reach the Pi replacement.

At minimum input must be covered; preferably include a destructive operation because create/run/kill can replace or terminate the protected process.

Preserve:
- ordinary Terminal behavior;
- later ordinary replacement-generation compatibility;
- Pi-create publication-window protection.

Do not:
- add PI-T007;
- hide terminal IDs as authorization;
- add auth/LAN policy;
- add a second process registry.

## Concurrency / lock-order review

This correction should remain TerminalManager-lock-only for generic operations. It does not require WebSocketHub lock and therefore should not add a new hub->terminal cycle.

The existing Pi scoped operations continue to use the established:

`TerminalManager -> WebSocketHub`

order.

## Complexity / YAGNI

The new `control_owner` marker is justified and materially simplifies ownership truth compared with registry scanning.

No new abstraction is needed to fix R23-1; the generic dispatch can hold the existing TerminalManager RLock around check + operation.

The two previously noted unused wrappers remain non-blocking dead code:
- `pi_takeover()`;
- `pi_writer_target()`.

`net: -6 lines possible.`

## Other review dimensions

- **Correctness:** R22-1 fixed; blocked by R23-1.
- **Scope drift:** none detected.
- **UX:** no browser/UI claim.
- **Maintainability/module separation:** process-control ownership belongs in TerminalManager and is now marked there; authorization must remain bound to the same generation through actuation.
- **Scalability:** no additional output/history store introduced.
- **Native Pi parity:** unchanged.
- **Concurrency isolation:** publication visibility fixed; guard/actuation generation isolation remains incomplete.
- **Auth/security:** this is writer/process-control authorization, not authentication.
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
- PI-T006: **not accepted** due R23-1.
- PI-T007+ remain unauthorized.
- runtime application wiring, browser F5/live reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R23-1: make generic process-control owner validation atomic with the operation against the same TerminalManager generation. Add the deterministic ordinary-to-Pi replacement race regression and preserve the R22 publication-window and stale-ordinary-replacement tests. Do not start PI-T007 or runtime/UI/persistence work.

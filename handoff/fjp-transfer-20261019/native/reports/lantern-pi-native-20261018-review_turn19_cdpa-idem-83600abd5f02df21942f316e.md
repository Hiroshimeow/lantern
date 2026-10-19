# REVIEW turn 19 — PI-T006 scoped WS attach / one-writer ownership

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 19  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. The PI-T006 contract suite is green, but two concurrency defects are independently reproducible: attach can succeed after the PTY has already exited, and a stale old writer can still send input after takeover if ownership changes between authorization and the TerminalManager write.

No implementation edits were made by REVIEW.

## Inputs independently checked

- PLAN turn 11 PI-T006 contract.
- TEST turn 9 PI-T004 acceptance.
- DEV turn 19 handoff.
- Actual PI-T006 diff:
  - `lantern/ws.py`
  - `tests/test_pi_ws_contract.py`
- Existing TerminalManager replay/input/key/resize locking.
- Existing WebSocketHub peer removal/send behavior.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- accepted PI-T004 is committed as `71bc8de feat(pi): add native session registry`.
- current PI-T006 candidate is exactly:
  - `M lantern/ws.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check` passes.
- no application/runtime wiring, frontend/chatbot, Markdown, dependency/vendor, LAN-policy, PI-T007 persistence/restart, or Spec 001 T2 implementation is present.

The PI-T006 slice remains server-contract-only as PLAN required.

## What is correct in the current PI-T006 candidate

The architecture is appropriately scoped:
- durable native process/session metadata remains in `PiSessionRegistry`;
- transient peer attachment/writer state lives in `WebSocketHub`;
- no output transcript/ANSI/model/slash catalog is duplicated;
- no client-controlled argv/env/create-session RPC is introduced;
- Pi operations reuse the existing terminal auth decision;
- public Pi events use `sessionId + generation`, not internal terminal ID;
- ordinary Terminal replay truncation math is reused through one `_bounded_replay()` helper;
- first attach becomes writer, later attach viewer;
- explicit takeover changes writer/epoch;
- detach/disconnect does not intentionally kill the Pi process;
- no arbitrary viewer auto-promotion;
- output scoping and ordinary generic-output suppression are implemented;
- no socket send is performed while the hub lock is held.

Ponytail complexity review: **Lean already. Ship.** The extra route state is justified by the requested transient ownership contract; no meaningful code deletion is available without removing required behavior.

## Fresh existing-suite verification

Fresh PI-T006 contract suite:

`uv run python -m unittest -v tests.test_pi_ws_contract`

Result:
- 7 tests;
- all 7 OK;
- 0.034 s;
- exit 0.

Fresh related regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 40 tests;
- all OK;
- 5.693 s;
- exit 0.

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py`: exit 0.
- `git diff --check`: exit 0.

These green tests do not cover the two races below.

## Finding R19-1 — attach can succeed after the Pi PTY has already exited

**Location:** `lantern/ws.py` PI attach path around `_pi_session_view()`, `terminal.replay_view()`, and `hub.pi_attach()`.

**PLAN invariant:** attach must:
1. reject unknown/stopped/not-running sessions;
2. atomically capture replay + route registration before output can cross the boundary.

**Current race:**
1. `_pi_session_view()` calls registry `get()` and observes the session as running.
2. Before the later `with terminal.lock:` block, the PTY exits.
3. TerminalManager moves the exact generation into history with `running=False`.
4. `terminal.replay_view()` still succeeds for history.
5. attach checks only `meta.generation == expected`, not `meta.running`.
6. `hub.pi_attach()` registers the peer and returns a writer replay for a stopped process.

### Fresh deterministic reproduction

REVIEW instrumented only the registry `get()` timing:
- registry view was returned as running;
- then the fake PTY invoked its real TerminalManager exit callback with code 7 before attach entered the terminal-lock/replay phase.

Observed:

`err None`

`replay_count 1`

replay:
- type `pi_session_replay`;
- role `writer`;
- ownershipEpoch 1.

Authoritative TerminalManager list simultaneously showed:
- same terminal ID/generation;
- `running=False`.

The proof assertion that stopped attach must fail therefore failed.

### Required correction

Inside the terminal-locked attach phase, after `replay_view()`, reject when either:
- generation mismatches; or
- `meta.running` is false.

Add a deterministic regression that exits the PTY between registry lookup and replay capture and proves:
- no route attachment is installed;
- no writer ownership is granted;
- no `pi_session_replay` is sent;
- stable `pi_session_stale`/equivalent stopped-session error is returned.

Do not add lifecycle persistence or auto-restart.

## Finding R19-2 — stale old-writer input can cross a takeover boundary

**Location:** `lantern/ws.py` writer operations:
- `hub.pi_writer_target(...)`;
- later separate `with terminal.lock:` block;
- `terminal.input/key/resize`.

**PLAN invariant:** ownership epoch exists specifically so stale queued messages from a previous owner are rejected after takeover/detach. A request is valid only while the peer is still current writer for the exact epoch.

**Current race:**
1. old writer A calls `pi_session_input` with epoch E;
2. `pi_writer_target()` validates A under hub lock and returns terminal ID;
3. hub lock is released;
4. viewer B performs takeover, changing writer and epoch E -> E2;
5. A resumes, acquires TerminalManager lock;
6. TerminalManager generation is still valid;
7. A's already-authorized stale input is written to PTY.

No ownership/epoch revalidation occurs at the actuation point.

### Fresh deterministic reproduction

REVIEW paused A immediately after `pi_writer_target()` returned, then performed a real `pi_session_takeover` by B before releasing A.

Observed:

- old epoch = 1;
- new epoch = 2;
- PTY writes = `['OLD']`;
- no exception for A.

The proof assertion that no stale old-writer input crosses takeover failed.

This is exactly the stale-queued-message failure PI-T006's ownership epoch is intended to prevent.

### Required correction

Make writer authorization and terminal actuation atomic with respect to takeover/detach.

The lock ordering already chosen for attach is:

**TerminalManager lock -> WebSocketHub lock**.

Use the same order for input/key/resize:
1. acquire `terminal.lock`;
2. validate current hub writer/session/generation/epoch while still holding terminal lock;
3. revalidate TerminalManager generation/running;
4. perform input/key/resize before releasing the ownership boundary.

Do not introduce the inverse nested order anywhere.

Equivalent atomic coordination is acceptable, but a second check after the fact is not enough because bytes/resize may already have reached the PTY.

Add deterministic regressions for at least:
- takeover between old-writer request start and actuation => zero stale input;
- preferably the same boundary for resize because writer also owns canonical geometry.

## Lock-order / deadlock review

Current attach already nests:

`terminal.lock -> hub.lock`.

Terminal output callbacks ultimately broadcast after their internal TerminalManager update; writer operations currently avoid nesting but lose atomic ownership as shown above.

A corrected writer path should use the same documented `terminal -> hub` order as attach. Avoid adding any `hub -> terminal` nested path.

Takeover/detach may continue to use hub lock only.

Socket sends must remain outside hub lock.

## Other review dimensions

- **Correctness:** blocked by R19-1 and R19-2.
- **Over-engineering/YAGNI:** no unnecessary framework identified; fix should remain local to attach/writer atomicity.
- **Scope drift:** none into PI-T007, UI, application wiring, Markdown, LAN policy or IME work.
- **UX:** no browser UI yet, correctly. Server ownership semantics must be race-safe before UI binds to them.
- **Maintainability/module separation:** route state in hub and process state in TerminalManager is a sound split; cross-owner operations need one consistent atomic lock order.
- **Scalability:** per-session peer sets are bounded only by connected peers and reuse existing queue/backpressure. No extra output buffers exist.
- **Native Pi parity:** transport passes bytes unchanged and does not intercept native Pi commands; physical/browser parity remains unmeasured.
- **Concurrency isolation:** **not accepted** due both races.
- **Auth/security:** same terminal auth gate is reused; no new remote argv/env or token model exists.
- **Regression/performance:** existing contract/regression tests are green; no CPU/RSS/latency claim is made.

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
- PI-T006: **not accepted** due R19-1 and R19-2.
- PI-T007+ remain not authorized.
- runtime application wiring, browser F5/reconnect, FJP physical input, real POSIX runtime, model/goal/extensions parity, and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only the PI-T006 concurrency boundaries:
1. reject stopped PTY state inside the terminal-locked attach replay boundary;
2. make writer epoch/role validation atomic with input/key/resize actuation using one consistent lock order.

Add deterministic race regressions. Do not start PI-T007, application wiring, frontend/UI, session-create RPC, persistence, Markdown, or LAN-policy work.

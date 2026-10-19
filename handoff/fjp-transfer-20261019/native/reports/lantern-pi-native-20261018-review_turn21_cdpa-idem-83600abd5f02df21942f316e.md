# REVIEW turn 21 — verify takeover/liveness atomicity for PI-T006

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 21  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **clean correctness review; ROUTE TEST** for independent PI-T006 acceptance. R20-1 is resolved, R19-1/R19-2 remain resolved, and no new material reproducible defect was found.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 21 handoff.
- REVIEW turn 20 R20-1.
- PLAN turn 11 PI-T006 attach/writer/takeover/lock-order contract.
- Actual current diff:
  - `lantern/ws.py`
  - `tests/test_pi_ws_contract.py`
- Existing TerminalManager lock/exit/replay/input behavior.
- Current WebSocketHub attachment/ownership state and call sites.
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate remains exactly:
  - `M lantern/ws.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no application/runtime wiring, frontend/UI, Markdown, dependency/vendor, LAN-policy, PI-T007 lifecycle/persistence, session-create RPC, or Spec 001 T2 work is present.

## R20-1 — takeover after PTY exit: RESOLVED

The `pi_session_takeover` dispatch path now uses the same cross-owner lock order as attach and writer actuation:

`TerminalManager.lock -> WebSocketHub.lock`.

Under the TerminalManager lock it:
1. resolves/revalidates the registry session and expected PTY generation;
2. captures `terminal.replay_view()`;
3. rejects generation mismatch or `meta.running == false`;
4. only then enters the hub lock and mutates ownership through `_pi_takeover_locked()`.

Ownership notices are sent after both locks are released.

Because TerminalManager exit handling needs the same TerminalManager lock, the PTY cannot transition to stopped between the authoritative liveness check and the hub ownership mutation.

## Fresh deterministic R20-1 reproduction

REVIEW independently recreated the exact prior race:
- writer A and viewer B attached;
- registry `get()` returned the session as running;
- the real fake-PTY exit callback fired immediately before takeover continued;
- B then attempted `pi_session_takeover`.

Fresh result:

- error: `PiSessionError: stale session generation`;
- route active: false;
- writer unchanged: true;
- ownership epoch unchanged at 1;
- no new writer ownership notice for B.

Probe result:

`independent_takeover_exit_race_ok`

This directly closes the turn-20 failure.

## R19-1 / R19-2 preservation

Fresh targeted three-race suite:

- `test_takeover_rejects_exit_between_registry_view_and_ownership_change`: PASS.
- `test_attach_rejects_exit_between_registry_lookup_and_replay_capture`: PASS.
- `test_takeover_between_writer_authorization_and_actuation_blocks_input_and_resize`: PASS.

Result:
- 3 tests;
- all 3 OK;
- 0.015 s;
- exit 0.

Thus:
- attach cannot register a stopped PTY;
- stale old-writer input cannot cross takeover;
- stale old-writer resize cannot cross takeover;
- takeover cannot promote a viewer after PTY exit.

## Lock-order review

Current nested cross-owner paths are consistent:

- attach: TerminalManager -> Hub;
- takeover: TerminalManager -> Hub;
- writer input/key/resize: TerminalManager -> Hub.

Hub-only paths such as detach/remove do not call TerminalManager while holding the hub lock.

TerminalManager output/exit/list emission either follows the same terminal->hub direction or emits after releasing terminal state as already established.

No new hub->terminal nested path was found.

Socket ownership notices remain outside the hub lock.

## Fresh REVIEW verification

Full PI-T006 contract:

`uv run python -m unittest -q tests.test_pi_ws_contract`

Result:
- 10 tests;
- all OK;
- 0.042 s;
- exit 0.

Related regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 40 tests;
- all OK;
- 5.976 s;
- exit 0.

Syntax / diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py`: exit 0.
- `git diff --check`: exit 0.

DEV also reports a fresh 384-test full-suite PASS. REVIEW did not repeat the whole suite in this turn because the corrected surface is limited to the takeover synchronization boundary and the PI-T006 contract plus related registry/auth/LAN regressions were freshly executed here. Independent TEST still owns material acceptance.

## Correctness / ownership assessment

The PI-T006 candidate now provides the scoped contract PLAN requested:
- sessionId + PTY-generation attach identity;
- no public Pi terminalId identity;
- replay continuity reuse;
- first-attacher writer, additional viewers;
- one writer/resize owner;
- explicit takeover with monotonically advancing ownership epoch;
- stale queued old-owner actuation rejected;
- detach/disconnect releases writer without killing Pi;
- stopped-session attach/takeover rejected;
- session switching and two-session output isolation;
- no duplicate generic terminal output to Pi-attached peers;
- existing terminal auth reuse;
- ordinary Terminal ownership behavior unchanged.

No browser/runtime lifecycle or persistence acceptance is inferred.

## Complexity / YAGNI

Two tiny hub wrappers are currently unused by repository callers:

- `lantern/ws.py:328-330`: `pi_takeover()` wraps `_pi_takeover_locked()`, but dispatch uses the locked helper directly.
- `lantern/ws.py:346-348`: `pi_writer_target()` wraps `_pi_writer_target_locked()`, but no repository caller uses the wrapper.

Ponytail finding:
- `ws.py:L328-330: delete: unused takeover wrapper. Use _pi_takeover_locked only at the synchronized dispatch boundary.`
- `ws.py:L346-348: delete: unused writer-target wrapper. Use _pi_writer_target_locked only at the synchronized dispatch boundary.`
- `net: -6 lines possible.`

This is non-blocking dead-code cleanup, not a material acceptance defect. Keeping these wrappers does not change current behavior, but PLAN/DEV may remove them before commit if desired.

## Other required review dimensions

- **Over-engineering:** aside from the six unused wrapper lines above, the transient route/epoch state is required by PI-T006.
- **Scope drift:** none.
- **UX:** no browser/UI implementation in this slice, correctly.
- **Maintainability/module separation:** process liveness remains TerminalManager-owned; transient peer/writer ownership remains Hub-owned.
- **Scalability:** no duplicate transcript/output buffer; per-session route state is limited to connected-peer references and small ownership metadata.
- **Native Pi parity:** byte stream remains unparsed/unchanged; physical/browser parity remains NOT_MEASURED.
- **Concurrency isolation:** required attach/takeover/old-writer races are now covered and fresh green.
- **Auth/security:** existing Terminal auth is reused; no remote argv/env, new token, whitelist, or LAN policy added.
- **Regression/performance:** focused PI/registry/auth/LAN regressions are fresh green; CPU/RSS/latency/release resource acceptance remains NOT_MEASURED.

## Findings

No concrete reproducible implementation defect remains in DEV turn 21.

PI-T006 is a clean REVIEW acceptance candidate, subject to independent TEST. The only remaining review note is six lines of non-blocking unused wrappers.

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
- PI-T006: **PASS candidate pending independent TEST**.
- PI-T007+ remain not authorized until TEST acceptance.
- runtime application wiring, browser F5/live reconnect, restart persistence, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE TEST.** Independent TEST should reproduce:
- stopped-session attach and takeover rejection;
- takeover-vs-old-writer input/resize race rejection;
- ownership epoch behavior;
- output/session isolation and no duplicate generic delivery;
- auth reuse and ordinary Terminal compatibility;
- focused/full regressions as appropriate.

Do not unlock PI-T007/runtime/UI/persistence until TEST acceptance.

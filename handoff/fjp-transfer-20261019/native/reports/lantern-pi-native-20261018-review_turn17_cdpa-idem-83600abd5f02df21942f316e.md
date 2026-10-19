# REVIEW turn 17 — verify PI-T004 create rollback atomicity

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 17  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `1282490f8bd1443b547c3b64b0b26813270ff837`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **clean implementation review; ROUTE TEST** for independent PI-T004 acceptance. R16-1 is resolved and the prior generation-safe ownership fix remains intact. No implementation edits made by REVIEW.

## Inputs independently checked

- REVIEW turn 16 R16-1.
- DEV turn 17 handoff.
- Current diff in:
  - `lantern/terminal.py`
  - `lantern/pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_sessions.py`
- Existing TerminalManager create/publish/history/kill behavior.
- PI-T005 native spawn regression and PI-T003 replay regression.
- Current branch/base/status.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 1282490f8bd1443b547c3b64b0b26813270ff837`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/5`.
- dirty paths remain exactly:
  - `M lantern/terminal.py`
  - `M tests/test_terminal_scm.py`
  - `?? lantern/pi_sessions.py`
  - `?? tests/test_pi_sessions.py`
- `git diff --check`: exit 0.
- no WS/frontend/application/Markdown/dependency/vendor/LAN-security path is dirty.
- no PI-T006/007 work, application wiring, browser attach, writer/viewer/takeover policy, persistence, live Lantern :9999 action, or CDPA action was introduced.

## R16-1 — create failure after live publication: RESOLVED

`TerminalManager.create()` now owns rollback for exceptions after a specific newly-created `TerminalEntry` has been published.

On the guarded path:
1. PTY is created.
2. the new entry is published to `live`;
3. early output/early exit handling and list emission run;
4. if any exception occurs after publication:
   - `live[term_id]` is removed only if it is still the exact same entry object;
   - `history[term_id]` is removed only if it is still the exact same entry object;
   - that entry is marked non-running;
   - only that captured PTY is closed with `graceful=False`;
   - the original exception is re-raised.

This keeps rollback at the TerminalManager process-ownership boundary and avoids registry-side guesses about partially published state.

## Fresh reproduction of the original failure path

REVIEW reran the exact deterministic regression:

`test_real_terminal_create_emit_failure_rolls_back_published_generation`

Result: PASS.

The test uses:
- real production TerminalManager;
- fake PTY backend only;
- an emit callback that raises on `terminal_list` after the new Pi terminal is live.

It verifies:
- registry create raises;
- registry list remains empty;
- native session directory is removed;
- `pi:orphan` is absent from live terminals;
- `pi:orphan` is absent from TerminalManager history;
- orphan PTY is closed;
- unrelated ordinary terminal remains live with its original generation.

This directly resolves R16-1.

## Replacement-generation safety during rollback

REVIEW also ran an additional deterministic real-TerminalManager probe that deliberately replaces the same terminal ID with a new generation from inside the failing list-emission path before the original create unwinds.

Observed:
- old generation's PTY closed;
- replacement generation remained live;
- replacement PTY remained open;
- live generation exactly matched the replacement generation.

Result:

`generation_safe_create_rollback_ok`

So the rollback identity checks do not remove or close a later replacement generation.

## R15-1 preservation — generation-atomic stop/close remains fixed

Fresh targeted run:
- `test_stop_and_close_do_not_kill_replacement_generations`: PASS.
- `test_kill_if_generation_never_kills_replacement_generation`: PASS.

`PiSessionRegistry.stop()` and `close()` still route through `kill_if_generation()`; no list-then-ID-kill TOCTOU pattern has returned.

## Fresh REVIEW verification

Targeted ownership/atomicity set:

`uv run python -m unittest -v tests.test_pi_sessions.PiSessionRegistryTests.test_real_terminal_create_emit_failure_rolls_back_published_generation tests.test_pi_sessions.PiSessionRegistryTests.test_stop_and_close_do_not_kill_replacement_generations tests.test_terminal_scm.TerminalParityTests.test_kill_if_generation_never_kills_replacement_generation`

Result:
- 3 tests;
- all 3 OK;
- exit 0.

Full PI-T004 registry suite:
- `tests.test_pi_sessions`: 8 tests, OK, 0.031 s.

Focused Terminal suite:
- `test_terminal_scm.py`: 23 tests, OK, 4.399 s.

Syntax/diff:
- `py_compile` for Terminal/registry/tests: exit 0.
- `git diff --check`: exit 0.

Native Pi structured-seam regression:
- `LANTERN_PI_TUI_E2E=1 ... tests.test_pi_tui_e2e`
- 1 test, OK, 9.993 s.

PI-T003 replay-continuity regression:
- `LANTERN_PI_REPLAY_E2E=1 ... tests.test_pi_reconnect_e2e`
- 7 tests, OK, 11.249 s.

DEV also reports a fresh 373-test repository suite PASS. REVIEW did not repeat that entire suite because the corrected code is isolated to the create rollback path and the directly affected registry, Terminal, native Pi and replay paths were freshly exercised here.

## Review dimensions

- **Correctness:** R16-1 is independently reproduced as fixed. Exact-entry live/history rollback, PTY cleanup, original-exception propagation, unrelated-terminal preservation and replacement-generation safety are verified.
- **Over-engineering / YAGNI:** no supervisor, transaction framework, process wrapper, retry layer or duplicate state owner was introduced. The rollback is local to the existing create owner. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none into PI-T006/007, browser/WS ownership, persistence, Markdown, LAN/security or Spec 001 T2.
- **Maintainability/module separation:** process publication/rollback stays in TerminalManager; registry remains metadata-only.
- **Scalability:** no new persistent/session-history mechanism.
- **Native Pi parity:** structured native Pi spawn regression remains green; no new parity claim.
- **Concurrency isolation:** both stop/close and failed-create ownership are now generation-safe in the tested races.
- **Regression/performance:** focused affected suites are fresh green; CPU/RSS/latency remain NOT_MEASURED.
- **Security:** no new remote process-control surface.

## Findings

No concrete reproducible implementation defect remains in DEV turn 17.

PI-T004 is now a clean acceptance candidate:
- opaque session identity;
- immutable context metadata;
- exact native session argv/session directory;
- same-document and cross-document independence;
- TerminalManager as sole PTY/status owner;
- generation-safe stop/close;
- failure-atomic create rollback;
- cleanup isolation from unrelated terminals;
- no premature attach/writer/persistence framework.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate.
- PI-T005 COMPLETE / accepted / committed.
- PI-T004: **PASS candidate pending independent TEST**.
- PI-T006/PI-T007+ remain not authorized until TEST acceptance.
- browser/FJP/real POSIX/resource/release items remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE TEST.** Independent TEST should reproduce the PI-T004 registry contract, generation-safe stop/close, create rollback after post-publication failure, unrelated-terminal isolation, exact argv/session-dir construction and focused regressions before PLAN authorizes PI-T006.

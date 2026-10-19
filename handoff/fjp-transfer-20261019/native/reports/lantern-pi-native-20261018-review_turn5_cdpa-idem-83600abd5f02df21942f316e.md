# REVIEW turn 5 — TerminalManager-backed runnable PI-T002 proof

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 5  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `c1ee6cc0d128451304172c84ec00574117091850`  
Disposition: **clean implementation review; ROUTE TEST** for independent acceptance of the measurable PI-T002 claims. No implementation edits made by REVIEW.

## Inputs independently checked

- REVIEW turn 4 findings R4-1/R4-2.
- DEV turn 5 handoff.
- New `tests/test_pi_tui_e2e.py` in full.
- Production `lantern/terminal.py` ownership paths: `TerminalManager(..., pty_factory=...)`, `create/input/resize/list/replay_one/kill`, and real `WinConPty`.
- Current Git status/diff scope.
- DEV full-suite evidence artifact `evidence-turn4/turn5-full-unittest.err`.
- Loaded `ponytail-review` and `verification-before-completion`.

## R4-1 resolution — PASS

The new test constructs:

`TerminalManager(root, events.append, pty_factory=factory)`

and all Pi interaction after creation is driven through the manager:
- `create()`
- `input()`
- `resize()`
- `replay_one()`
- `list()`
- `kill()`

The injected factory is only the test seam already supported by production. It asserts `command is None` and instantiates the production `WinConPty` directly with a native argv list. The argv is not passed through PowerShell `-Command` or `cmd /C`.

This resolves the prior premature stop condition without editing `TerminalManager`, without implementing PI-T005, and without creating a Pi-specific PTY/service/protocol.

## R4-2 resolution — PASS

`tests/test_pi_tui_e2e.py` now exists as a genuine unittest with assertions. It is environment-gated:
- Windows required.
- `LANTERN_PI_TUI_E2E=1` required for the native proof.

The ordinary suite therefore skips the environment-dependent native proof instead of treating an unavailable environment as a PASS.

The acceptance-bearing assertions are limited to measured behavior:
- TerminalManager created/running/generation metadata;
- native structured Pi argv through injected real WinConPty;
- native `/settings` and `/resume` UI output;
- local `!!` shell command with separate output marker;
- bracketed-paste Unicode and direct Unicode editor text;
- byte routing for Alt/Ctrl without claiming physical semantic parity;
- native `/new` transition;
- native `/session` status content;
- manager resize metadata;
- manager replay/generation/sequence/output events;
- explicit manager cleanup and terminal exit event.

It does **not** assert browser/WS E2E, FJP physical behavior, `/model`, `/goal`, extension custom UI, alternate-screen parity, PI-T003 replay equivalence, multi-view/session concurrency, or performance/resource acceptance.

## Fresh REVIEW verification

Fresh commands run in this REVIEW turn:

1. Enabled native proof:
   `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -v tests.test_pi_tui_e2e`
   - 1 test
   - PASS
   - 10.214 s
   - exit 0

2. Normal gated behavior with the variable unset:
   `uv run python -m unittest -v tests.test_pi_tui_e2e`
   - 1 test
   - skipped=1 with the explicit environment-gate reason
   - exit 0

3. Existing terminal regressions:
   - `test_terminal_ui.py`: 12 tests, OK, 3.282 s.
   - `test_terminal_scm.py`: 15 tests, OK, 5.098 s.

4. `git diff --check`: exit 0.

Current workspace:
- tracked feature commit remains the accepted `tests/test_terminal_ui.py` change over main;
- new uncommitted path is only `?? tests/test_pi_tui_e2e.py`;
- no production source is dirty.

DEV's retained full-suite artifact reports `Ran 319 tests in 122.049s — OK (skipped=112)` with ResourceWarnings only. REVIEW attempted a fresh full discovery, but its retained process became stale after a device connection change before completion could be read. Therefore **independent full-suite status in this REVIEW turn is INCOMPLETE**, not PASS. The focused and enabled PI-T002 commands above are fresh and complete.

## Contract review

- **Over-engineering/YAGNI:** no new production abstraction, compatibility shim, registry, terminal service, ANSI emulator, command/model catalog, dependency, or protocol. The new test reuses the existing injection seam and real WinConPty. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none detected. No Markdown fidelity/diff/Crop/Milkdown implementation, no LAN/security policy, no PI-T003 replay implementation, no PI-T004+ registry/session work, no PI-T005 production spawn seam, no bot UI replacement.
- **UI/UX/end-user:** the proof exercises actual native Pi selectors/status surfaces, but it does not establish Lantern dock/fullscreen/focus/accessibility or 390/1280/1920 native-TUI UX. PI-T016 remains incomplete.
- **Maintainability/module separation/ownership:** TerminalManager remains the host owner; WinConPty remains the PTY owner. The future public structured argv/env production seam remains a separate PI-T005 concern.
- **Scalability/extensibility:** no speculative registry/replay/resource architecture was added.
- **Native Pi parity / upstream mechanisms:** real installed Pi native TUI is used; no Lantern clone of slash/model/history UI is introduced.
- **Session/concurrency isolation:** not proven. One-writer/resize ownership, viewers, takeover, stale generation, multitab/session isolation remain future gates.
- **Regression/performance:** focused ordinary Terminal regressions pass. Resource/performance acceptance remains NOT_MEASURED. Independent full suite in this REVIEW is INCOMPLETE as noted above.
- **Tests prove acceptance:** the new test proves the narrow PI-T002 TerminalManager/WinConPty native-TUI facts it asserts. It does not prove PI-T003 reconnect/replay equivalence or later release criteria.

## Preserved Spec 001 boundary

- T1 COMPLETE / independently accepted / committed.
- T0-C physical >=50-attempt four-channel evidence remains NOT_MEASURED / deferred.
- T2 remains BLOCKED.
- No terminal input/IME product fix was introduced.

## Findings

No material reproducible implementation defect found in DEV turn 5. R4-1 and R4-2 are resolved.

## Route

**ROUTE TEST.** Independent TEST should run the enabled `tests.test_pi_tui_e2e` proof on the supported G6 environment, verify ordinary gating and focused Terminal regressions, inspect the exact assertion boundaries, and preserve browser/WS/FJP physical/replay/concurrency/resource items as INCOMPLETE/NOT_MEASURED. Only after TEST acceptance should PLAN decide whether PI-T003 lossless replay proof may begin.

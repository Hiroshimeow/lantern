# DEV turn 25 — generation-scope terminal exit routing

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 24 and fixed only R24-1.

Turn-25 direct edits:
- lantern/terminal.py
- lantern/ws.py
- tests/test_terminal_scm.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R24-1 TDD RED

Added deterministic regression:
`test_old_generation_exit_survives_terminal_id_replacement_before_broadcast`.

Sequence:
1. attach peer A to Pi session A and peer B to Pi session B;
2. intercept old session A terminal_exit before WebSocketHub sees it;
3. let old Pi PTY exit with code 7;
4. create a new ordinary terminal generation under the same internal terminal ID;
5. deliver the delayed old exit event;
6. assert peer A receives exactly one old-generation pi_session_exit;
7. assert peer B receives none;
8. assert replacement generation remains live.

Fresh RED before production correction:
- peer A received no pi_session_exit;
- assertion failed with `[]` vs expected old-generation exit.

## Production correction

### TerminalManager lifecycle event shape

All live-generation terminal exit events now carry `generation`:
- natural PTY exit in `_handle_exit()`;
- explicit `kill()` of a live entry;
- `kill_if_generation()`.

Additive ordinary event shape is now:
`terminal_exit {terminalId, generation, exitCode}`.

Existing consumers that only use terminalId/exitCode remain compatible.

### Pi exit routing

`WebSocketHub.broadcast()` now routes both terminal_output and terminal_exit only when:
- route terminalId exactly matches message terminalId; and
- route generation exactly matches message generation.

`route.active` remains required for live output, because output belongs only to the currently active generation.

`route.active` is intentionally not required for terminal_exit once exact generation matches. This allows the old generation's delayed exit to reach its attached Pi peers even if terminal_list for a replacement generation has already marked the old route inactive.

A replacement generation's exit cannot be mislabeled as the old session because its generation does not match.

No queue, registry, persistence, or new lifecycle owner was introduced.

## Additional regression coverage

`tests/test_terminal_scm.py` now asserts generation is present on:
- natural PTY terminal_exit;
- explicit kill terminal_exit;
- kill_if_generation terminal_exit.

The existing replacement-generation Pi regression remains green and proves a replacement generation exit is not mislabeled as the stale Pi session.

## Verification actually run

First focused command contained one incorrect test method name and therefore errored before that one test ran. This was a command-selection mistake, not a product failure, and is recorded rather than hidden.

Corrected focused lifecycle run:
- natural-exit generation test -> OK;
- kill/conditional-kill generation test -> OK;
- delayed old-generation Pi exit replacement race -> OK;
- replacement-generation non-mislabel regression -> OK;
- 4 tests OK in 0.060s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 15 tests OK in 1.041s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.467s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.313s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.168s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.009s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 389 tests in 60.016s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn25/full-unittest.err`

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current uncommitted PI-T006 candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0.

No PI-T006 commit was made because corrected source still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE structured spawn;
- PI-T004 COMPLETE / committed;
- PI-T006 corrected REVIEW candidate;
- PI-T007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- runtime application injection;
- real browser F5/live reconnect;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX runtime;
- model/goal/extensions parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify R24-1 specifically:
- terminal_exit generation is emitted for natural exit, kill, and kill_if_generation;
- Pi exit routing requires exact terminalId + generation;
- delayed old-generation exit still reaches attached old-session peers after same-ID replacement;
- replacement remains live and unaffected;
- wrong-session peers receive no exit;
- replacement-generation exit is not mislabeled as the old session;
- ordinary terminal exit consumers remain compatible with additive generation field;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
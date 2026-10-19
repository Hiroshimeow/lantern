# DEV turn 22 — block generic Terminal control bypass of Pi writer ownership

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read TEST turn 10 and fixed only T10-1.

Changed only:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## T10-1 reproduction / TDD RED

Added two deterministic regressions against real:
- PiSessionRegistry;
- TerminalManager;
- WebSocketHub;
- dispatch.

Only PTY I/O is fake.

`test_generic_terminal_controls_cannot_bypass_pi_writer_or_destroy_session` covers a live Pi-owned terminal.

Before production correction, fresh RED showed all six generic operations bypassing the Pi ownership boundary:
- terminal_input;
- terminal_key;
- terminal_resize;
- terminal_kill;
- terminal_run;
- terminal_create.

Observed RED details:
- all six expected PermissionError assertions failed;
- generic input reached the Pi PTY as `BYPASS`;
- generic key reached the PTY as encoded Enter `\r`;
- destructive generic operations remained reachable.

`test_generic_terminal_controls_still_work_for_ordinary_and_replacement_generations` was GREEN before the fix, establishing the ordinary-Terminal compatibility baseline.

## Production correction

Added one narrow server-boundary helper in `lantern/ws.py`:
`_guard_generic_terminal_control(pi, terminal, terminal_id)`.

It runs only for generic process-control operations:
- terminal_create;
- terminal_run;
- terminal_input;
- terminal_key;
- terminal_resize;
- terminal_kill.

Behavior:
1. if no PiSessionRegistry was injected, existing generic Terminal behavior is unchanged;
2. acquire the existing TerminalManager RLock;
3. resolve current authoritative terminal metadata via `replay_view()`;
4. if the terminal does not exist or is not running, do not block;
5. compare current terminalId + current PTY generation against PiSessionRegistry list state;
6. only when the live current generation is owned by a Pi session, reject generic control with `PiSessionPermissionError(pi_session_control_required, ...)`.

This keeps process-control authorization at the server boundary rather than relying on hiding terminal IDs.

### Why generation matching is required

A stopped Pi session may leave a stale registry record for its old terminalId/generation.

The guard blocks only when:
- current live TerminalManager generation;
- Pi registry terminalId;
- Pi registry stored generation

all match.

Therefore a later ordinary replacement terminal that reuses the same terminal ID with a new generation is not incorrectly captured by stale Pi ownership metadata.

### Locking

The guard uses TerminalManager's existing RLock and does not acquire WebSocketHub lock.

PiSessionRegistry.list() derives status from TerminalManager and re-enters the same RLock, so this keeps the established process-owner boundary without introducing a new hub/terminal lock ordering path.

No generic protocol or terminal list format was changed.

## Acceptance proof

Fresh targeted GREEN after correction:
- `test_generic_terminal_controls_cannot_bypass_pi_writer_or_destroy_session` -> OK
- `test_generic_terminal_controls_still_work_for_ordinary_and_replacement_generations` -> OK
- 2 tests total, OK

The first regression proves for a live Pi-owned PTY:
- viewer generic terminal_input is rejected;
- viewer generic terminal_key is rejected;
- unattached authenticated peer generic terminal_resize is rejected;
- generic terminal_kill is rejected;
- generic terminal_run targeting the same live ID is rejected;
- generic terminal_create targeting the same live ID is rejected;
- no PTY input bytes were written;
- no resize occurred;
- PTY was not closed;
- Pi registry still reports the same generation running.

The second regression proves:
- ordinary terminal_create/input/resize/kill remain unchanged;
- after the old Pi generation is stopped and the same internal terminal ID is reused by a new ordinary generation, generic input/resize are allowed;
- stale Pi registry generation metadata therefore does not permanently reserve an internal terminal ID.

## Verification actually run

Targeted T10-1 RED/ GREEN:
- RED: live-Pi control test failed for all six generic operations; ordinary/replacement compatibility test passed;
- GREEN: both targeted tests passed, 2/2.

PI-T006 contract after fix:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 12 tests OK in 0.055s

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.225s

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 2.937s

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.212s

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.001s
- no paid AI prompt

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 386 tests in 52.408s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn22/full-unittest.err`

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate:
  - M lantern/ws.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0
- tests/test_pi_ws_contract.py SHA256: f4f649a89ba5292af58402e08fbdb42b9e3e1a79bacf4e01b07444cd038b352a

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
- runtime application injection of PiSessionRegistry;
- real browser F5/live reconnect;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX runtime;
- model/goal/extensions parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify T10-1 specifically:
- generic terminal_input/key/resize cannot bypass Pi writer ownership;
- generic terminal_kill/run/create cannot destroy or replace a live Pi-owned PTY;
- ordinary Terminal control remains unchanged;
- stale Pi registry metadata does not block a replacement generation;
- guard is generation-aware and process-owner scoped;
- lock behavior does not add hub->terminal or new deadlock paths;
- no terminal ID hiding/security-policy workaround was substituted for authorization;
- prior PI-T006 attach/takeover race fixes remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
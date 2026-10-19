# DEV turn 23 — close PI-T006 Pi-create publication window

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 22 and fixed only R22-1.

Changed only:
- lantern/terminal.py
- lantern/pi_sessions.py
- lantern/ws.py
- tests/test_pi_sessions.py
- tests/test_pi_ws_contract.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R22-1 reproduction / TDD RED

Added deterministic regression:
`test_generic_controls_are_blocked_during_pi_create_publication_window`.

The test uses real:
- PiSessionRegistry;
- TerminalManager;
- WebSocketHub;
- production dispatch;

with fake PTY I/O only.

For each generic control operation, the test pauses `PiSessionRegistry.create()` after `TerminalManager.create_argv()` has already published the live `pi:race` PTY but before the registry inserts its session record.

While paused it proves:
- `registry.list() == []`;
- TerminalManager reports live `pi:race`;
- the Pi process is therefore in the exact review publication window.

Fresh RED before production correction:
- terminal_input: no PermissionError;
- terminal_key: no PermissionError;
- terminal_resize: no PermissionError;
- terminal_kill: no PermissionError;
- terminal_run: no PermissionError;
- terminal_create: no PermissionError.

Result: 1 test with 6 failing subtests.

## Production correction

### TerminalManager ownership marker

Added one server-internal field to `TerminalEntry`:
- `control_owner: Optional[str]`

Added keyword-only `control_owner` passthrough to:
- `TerminalManager.create()`;
- `TerminalManager.create_argv()`.

The marker is stored on the exact live TerminalEntry at the same moment that generation is published into `TerminalManager.live`.

Added `TerminalManager.control_owner(term_id)` which returns the current running entry's owner under the existing TerminalManager RLock.

The owner marker is intentionally absent from `_info()`, `list()`, `replay_view()` metadata, WS payloads, and Pi session views.

### Pi registry

`PiSessionRegistry.create()` now calls the accepted structured spawn seam with:
- `control_owner="pi"`.

Therefore Pi process ownership exists at TerminalManager live-entry publication, before registry metadata publication.

### Generic Terminal guard

`_guard_generic_terminal_control()` no longer infers ownership by scanning `PiSessionRegistry.list()`.

It now asks the TerminalManager process owner directly:
- if current running entry has `control_owner == "pi"`, reject generic process control;
- otherwise preserve ordinary Terminal behavior.

The guard remains applied only to:
- terminal_create;
- terminal_run;
- terminal_input;
- terminal_key;
- terminal_resize;
- terminal_kill.

This closes the publication window without relying on terminal-ID prefixes, hiding IDs, new auth policy, persistence, or a second process registry.

## Generation / replacement behavior

`control_owner` belongs to a specific TerminalEntry generation.

When the old Pi generation is stopped and an ordinary terminal later reuses the same terminal ID:
- the new TerminalEntry has `control_owner=None` by default;
- generic Terminal input/resize remain allowed;
- stale PiSessionRegistry metadata cannot reserve the replacement generation.

Existing stale-replacement compatibility regression remains green.

## Test contract updates

`tests/test_pi_sessions.py` fake TerminalManager now accepts/records the internal `control_owner` keyword so registry unit tests continue to exercise the exact structured-spawn contract.

The registry test now asserts:
- Pi create passes `control_owner == "pi"` internally;
- returned session metadata does not expose a `controlOwner` field.

## Verification actually run

Fresh targeted publication-window GREEN after production correction:
- publication-window regression;
- existing live-Pi generic-control block regression;
- ordinary/replacement-generation compatibility regression;
- 3 tests OK in 0.052s.

PI registry + PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract tests.test_pi_sessions`
- 22 tests OK in 0.132s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.335s.

Terminal auth + LAN multi-peer/performance regression:
- `uv run python -m unittest -q tests.test_terminal_auth tests.test_lan_multi_perf`
- 31 tests OK in 6.460s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.140s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.108s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 387 tests in 61.911s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn23/full-unittest.err`

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
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0.

No commit was made because the corrected PI-T006 slice still requires independent REVIEW/TEST acceptance.

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

Independent REVIEW should verify R22-1 specifically:
- Pi ownership marker is installed atomically with TerminalManager live-entry publication;
- generic terminal_input/key/resize/kill/run/create cannot enter during the registry publication window;
- authorization truth no longer depends on later registry publication;
- marker is server-internal and not leaked through TerminalManager metadata or WS/session payloads;
- ordinary terminals and ordinary replacement generations remain controllable;
- no terminal-ID-prefix authorization shortcut was used;
- no extra process/history/session service was introduced;
- prior PI-T006 attach/takeover/writer race fixes remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
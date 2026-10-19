# DEV turn 14 — PI-T005 structured native spawn seam

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope executed

Read PLAN turn 9 and AGENTS.md. Loaded executing-plans, test-driven-development, verification-before-completion, and ponytail.

Executed only the authorized PI-T005 slice after preserving the independently accepted PI-T003 continuity work.

Explicitly not started:
- PI-T004 registry;
- PI-T006 writer/viewer/takeover protocol;
- PI-T007 lifecycle;
- Pi-specific WS protocol;
- browser argv/env exposure;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/security policy;
- live Lantern :9999 actions;
- CDPA changes.

## Housekeeping — accepted PI-T003 continuity slice

Incoming dirty paths matched PLAN exactly:
- lantern/terminal.py
- lantern/ws.py
- static/terminal_scm.js
- tests/test_pi_reconnect_e2e.py
- tests/test_terminal_scm.py
- tests/test_terminal_ui.py

`git diff --check` was clean.

Selectively staged only those six paths and committed:
- aa9282d feat(terminal): expose replay continuity watermark

Then rebased cleanly onto current local main without stash/reset/clean/merge.

Post-rebase accepted continuity commit became:
- 4a03fa9d15803d0adfdd2a28124012d6439e9cb7 HEAD after rebase
- main 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/4

Feature diff after rebase contains only owned Terminal/Pi runtime/test paths; no Markdown-owner path is in the feature diff.

## PI-T005 implementation

Changed only:
- lantern/terminal.py
- tests/test_terminal_scm.py
- tests/test_pi_tui_e2e.py

No WS/frontend/application/chatbot file changed in this slice.

### API shape

Added generic server-internal `TerminalManager.create_argv(...)` and keyword-only `argv` / `env` support on `create()`.

Behavior:
- structured argv is passed as an exact list of strings;
- empty argv is rejected;
- a bare string/bytes value is rejected as not being an argv sequence;
- non-string argv entries are rejected;
- command string + structured argv is rejected before spawn;
- structured env without argv is rejected;
- env keys/values must be strings;
- cwd still uses existing root containment/normalization;
- ordinary `create()` and `run_command()` keep their legacy shell behavior and factory signature.

### Native PTY ownership

Added one shared `_build_pty_env()` helper in `lantern/terminal.py`.

It:
- copies `os.environ` into a fresh child dict;
- preserves inherited environment;
- applies existing TERM=xterm-256color and LANG=en_US.UTF-8 defaults when absent;
- applies caller overlay after defaults, so an explicit override wins;
- validates string keys/values;
- never mutates `os.environ`.

Both WinConPty and PosixPty use the same helper and receive the same optional env-overlay contract.

`TerminalManager._spawn_native()` now either:
- resolves the existing interactive shell / shell-command wrapping exactly as before; or
- uses the provided structured argv directly with no shell wrapping.

No new process framework, Pi-only PTY manager, dependency, transcript/history store, metadata serialization, or browser-facing process API was added.

### Metadata/security boundary

Structured argv/env are not added to terminal metadata or events.

`terminal_create` / `terminal_run` WebSocket contracts were not changed and cannot supply argv/env.

## TDD evidence

Initial RED was observed before production implementation:
- `create_argv` missing -> AttributeError;
- `_build_pty_env` missing -> ImportError;
- structured spawn tests failed as expected;
- ordinary legacy factory test already passed, establishing the backward-compatibility baseline.

After implementation, focused structured-spawn tests passed.

New acceptance coverage in tests/test_terminal_scm.py proves:
- exact argv preservation with spaces, Japanese text, embedded quotes, `&`, `;`, and single quote;
- no shell command is supplied on structured path;
- cwd resolves inside configured root;
- argv/env are not present in returned metadata;
- empty argv / string-as-argv / command+argv / outside cwd are rejected before factory invocation;
- inherited env survives;
- PTY defaults exist when parent env is empty;
- explicit TERM override and Unicode env values remain exact;
- child env mutation does not mutate parent `os.environ`;
- non-string env values are rejected;
- both WinConPty and PosixPty dispatch branches receive the same argv/env contract;
- ordinary shell create/run_command keeps the legacy injected factory signature.

## Production Pi seam proof

`tests/test_pi_tui_e2e.py` no longer injects a special Pi `pty_factory` closure.

It now:
- constructs the already characterized installed Pi 1.3.0 node + CLI argv;
- keeps `--offline`, `--approve`, `--no-mcp`, session-dir/session-id, regular TUI mode;
- creates a normal TerminalManager with its production `_spawn_native` owner;
- calls `manager.create_argv(...)` with exact structured argv and a harmless server-owned env overlay;
- asserts the manager owns its normal production PTY factory;
- asserts argv/env are not exposed in returned metadata;
- asserts no `-Command`, `/C`, or `-lc` wrapper is present;
- retains local native `/settings`, `/resume`, shell command, Unicode input, `/new`, `/session`, resize, sequence, cleanup assertions;
- sends no paid AI prompt.

Fresh G6 native run:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.211s

Gate-off run:
- 1 test discovered, skipped=1, exit 0

Real POSIX PTY process execution is NOT_MEASURED in this Windows turn. The shared construction/dispatch contract for PosixPty is unit-covered; no claim of real POSIX runtime parity is made.

## Verification actually run

Focused structured-spawn RED/GREEN command after implementation:
- 4 focused tests OK

Final focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 22 tests OK in 4.793s

Native Pi production-seam proof:
- 1 test OK in 10.211s

Ordinary gate-off Pi proof:
- 1 skipped, exit 0

Combined ordinary Terminal/UI/LAN regression:
- `uv run python -m unittest -q tests.test_terminal_scm tests.test_terminal_ui tests.test_lan_multi_perf`
- 54 tests OK in 12.332s

PI-T003 replay regression after TerminalManager changes:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 14.029s

Syntax/diff checks:
- `uv run python -m py_compile lantern\terminal.py tests\test_terminal_scm.py tests\test_pi_tui_e2e.py` -> exit 0
- `node --check static\terminal_scm.js` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 364 tests in 62.351s
- OK, skipped=134
- existing ResourceWarning HTTPError cleanup lines only
- evidence: .plan/lantern-pi-native-20261018/evidence-turn14/full-unittest.err

## Final repository state

Fresh status:
- HEAD: 4a03fa9d15803d0adfdd2a28124012d6439e9cb7
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/4

Only current uncommitted PI-T005 candidate paths:
- lantern/terminal.py
- tests/test_pi_tui_e2e.py
- tests/test_terminal_scm.py

No package/lock/vendor file is dirty.

No PI-T005 production commit was made because this slice still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T002 COMPLETE for narrow native TerminalManager/WinConPty proof;
- PI-T003 COMPLETE for Phase-0 bounded same-geometry continuity gate;
- PI-T005 implementation is now a REVIEW candidate;
- PI-T004 remains not started and must wait for PI-T005 acceptance;
- PI-T006/007+ remain not authorized;
- browser F5/live reconnect, FJP physical IME/AltGr/image paste, live model/goal/extensions parity, and resource acceptance remain INCOMPLETE/NOT_MEASURED.

## REVIEW request

Independent REVIEW must explicitly check:
- exact argv preservation and absence of shell wrapping;
- argv/command mutual exclusion and validation;
- env overlay/default/inheritance semantics and parent-env immutability;
- no argv/env secret exposure in metadata/events/logging;
- same WinConPty/PosixPty ownership contract;
- server-internal-only boundary and no new WS attack surface;
- ordinary Terminal shell behavior and legacy factory compatibility;
- native Pi e2e truly uses `TerminalManager.create_argv()` with production `_spawn_native`, not injected Pi PTY ownership;
- YAGNI / no generic process-framework overreach;
- future PI-T004 suitability without pre-implementing registry/session policy;
- cross-platform evidence honesty;
- no Markdown/LAN/security scope drift;
- full regression evidence.

Route: REVIEW.
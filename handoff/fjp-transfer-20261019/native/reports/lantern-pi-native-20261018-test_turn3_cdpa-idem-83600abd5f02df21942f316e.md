# TEST turn 3 — independent verification of TerminalManager-backed PI-T002 proof

Task: `cdpa-idem-83600abd5f02df21942f316e`  
Role: TEST, turn 3, hop 21  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn5_cdpa-idem-83600abd5f02df21942f316e.md`  
Disposition: **PASS for the narrow measurable PI-T002 TerminalManager/WinConPty native-TUI proof; ROUTE PLAN.** No reproducible implementation defect found. This is not PI-T003 replay acceptance, FJP physical/browser parity, session/concurrency acceptance, or release completion.

## Execution identity and repository truth

Repository checks were executed on device `desktop-b5e4iue-87cea2af`, hostname `DESKTOP-B5E4IUE`, Windows x64, account `desktop-b5e4iue\admin`, with working directory `E:\git-project\lantern\.wt\lantern-bot`.

Fresh environment observations:
- `node --version` => `v22.22.2`
- `uv --version` => `uv 0.11.8 (0e961dd9a 2026-04-27 x86_64-pc-windows-msvc)`
- `pi --version` => `1.3.0`
- bare `python --version` is unavailable on PATH; this is not the project runtime.
- `uv run python --version` => `Python 3.14.1`

Fresh Git observations:
- `HEAD=c1ee6cc0d128451304172c84ec00574117091850`
- local `main=ffe3decb4469cff36bb98f8afd6ba8e9e89af089`
- `main...HEAD = 0 1`
- branch `feat/lantern-bot...origin/feat/lantern-bot [ahead 3]`
- only uncommitted path: `?? tests/test_pi_tui_e2e.py`
- committed feature diff against main remains only `M tests/test_terminal_ui.py`
- no production source is dirty.

Loaded verification skill: `verification-before-completion`. No browser/server restart, paid AI prompt, merge/rebase/reset/stash/clean, Lantern `:9999` action, or CDPA modification/reload was performed.

## Source/ownership inspection

Observation procedure:
- Read `tests/test_pi_tui_e2e.py` in full.
- Ran:
  `rg -n "class TerminalManager|def __init__|pty_factory|def create|def input|def resize|def replay_one|def kill|class WinConPty" lantern\terminal.py`

Expected:
- Proof must run through production `TerminalManager` ownership with the existing `pty_factory` seam and production `WinConPty`.
- No production structured-spawn API, Pi-specific PTY service/protocol, ANSI emulator, command catalog, session registry, or replay implementation may be introduced.

Actual:
- `TerminalManager.__init__` accepts `pty_factory` and `create()` delegates PTY creation through it.
- The test creates `TerminalManager(root, events.append, pty_factory=factory)`.
- The factory asserts `command is None`, records a structured native Pi argv, and constructs production `WinConPty(argv, ...)`.
- All interaction after creation is through manager methods: `create`, `input`, `resize`, `replay_one`, `list`, and `kill`.
- Test argv explicitly excludes shell wrappers `-Command` and `/C`.
- Test assertions are limited to native Pi/local TUI facts, manager metadata/events, and cleanup. It does not assert browser/WS/FJP physical/reconnect/concurrency/release facts.

Status: **PASS** for ownership/scope of this proof.

## Exact independent verification

### 1. Enabled native PI-T002 proof

Command:
`$env:LANTERN_PI_TUI_E2E='1'; uv run python -m unittest -v tests.test_pi_tui_e2e; $code=$LASTEXITCODE; Remove-Item Env:LANTERN_PI_TUI_E2E -ErrorAction SilentlyContinue; exit $code`

Expected:
- Environment-gated test executes rather than skips.
- Real installed Pi TUI starts through TerminalManager + WinConPty.
- All acceptance-bearing assertions in the test pass.

Actual:
- `test_terminal_manager_hosts_native_pi_tui_without_shell_wrapping ... ok`
- `Ran 1 test in 10.076s`
- `OK`
- exit code 0; no timeout.

The passing assertions cover only what the test actually checks:
- manager create/running/generation/initial geometry;
- exact structured argv ownership and absence of shell wrapping;
- native `/settings` UI containing expected settings rows;
- native `/resume` selector;
- local `!!echo PI_NATIVE_SHELL_PROOF` command plus separate native shell output;
- bracketed-paste Unicode text and direct Unicode editor text retained;
- Alt/Ctrl bytes routed without claiming physical key semantics;
- native `/new` transition;
- native `/session` status surface;
- resize metadata 100x32 -> 120x40;
- replay carries same generation, nonzero sequence, and retained output;
- emitted `terminal_output` events have matching generation and unique monotonic sequence values;
- explicit kill empties manager list and emits `terminal_exit`.

Status: **PASS — narrow runnable PI-T002 proof**.

### 2. Ordinary-suite environment gate

Command:
`Remove-Item Env:LANTERN_PI_TUI_E2E -ErrorAction SilentlyContinue; uv run python -m unittest -v tests.test_pi_tui_e2e`

Expected:
- Native machine-dependent proof is not silently treated as ordinary-suite PASS.
- Test is explicitly skipped when the opt-in variable is absent.

Actual:
- test skipped with reason `set LANTERN_PI_TUI_E2E=1 to run native Pi TUI proof`
- `Ran 1 test in 0.000s`
- `OK (skipped=1)`
- exit 0.

Status: **PASS** for correct gating behavior. The skipped native proof itself is not counted as a native PASS in this command.

### 3. Focused ordinary Terminal regressions

Commands:
- `uv run python -m unittest discover -s tests -p test_terminal_ui.py -q`
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`

Expected:
- Existing ordinary Terminal/SCM focused coverage remains green.

Actual:
- terminal UI: `Ran 12 tests in 2.341s`, `OK`, exit 0.
- terminal SCM: `Ran 15 tests in 4.786s`, `OK`, exit 0.

Status: **PASS** for focused regression boundary.

### 4. Syntax and diff hygiene

Commands:
- `uv run python -m py_compile tests\test_pi_tui_e2e.py`
- `git diff --check`

Actual:
- both exit 0 with no error output.

Status: **PASS**.

### 5. Post-test workspace preservation

Command:
`git status --short --branch; git diff --name-status; git ls-files --others --exclude-standard; git diff --name-status main..HEAD; git rev-list --left-right --count main...HEAD`

Actual:
- worktree still has only `?? tests/test_pi_tui_e2e.py`;
- no tracked working-tree modifications;
- main-to-HEAD committed diff is still only `M tests/test_terminal_ui.py`;
- `main...HEAD = 0 1`.

Status: **PASS** for scope preservation.

## Strict classifications

- **PI-T002 measurable proof in this slice: PASS.** Real installed Pi 1.3.0 native TUI ran under production `WinConPty` hosted by `TerminalManager`, with native selectors/session UI/local shell/Unicode input bytes/resize/replay-tail metadata and cleanup assertions passing.
- **PI-T002 broader task/release parity: INCOMPLETE.** This test does not establish browser xterm -> WS -> manager E2E, FJP physical IME/AltGr/image paste, `/model`, `/goal`, custom extension UI, alternate-screen/cursor-state equivalence, or a full 12-action FJP parity matrix.
- **PI-T003 lossless reconnect/replay equivalence: INCOMPLETE / NOT_MEASURED.** The test only confirms current manager tail replay returns retained bytes with generation/sequence; it does not prove cell/style/cursor/mode equivalence, alternate screen, broken ANSI boundaries, F5 behavior, or different viewer widths. The PI-T003 stop gate remains intact.
- **Session/concurrency isolation: INCOMPLETE.** One-writer/resize ownership, viewers, takeover, stale generation, multitab/session isolation, and cross-session containment are not tested here.
- **Performance/resource acceptance: NOT_MEASURED.** No CPU/RSS/latency benchmark was run.
- **Independent full repository unittest suite: INCOMPLETE in this TEST turn.** DEV retained a prior full-suite artifact, but TEST did not rerun the full suite because the assigned REVIEW handoff required the enabled PI-T002 proof, gating, and focused Terminal regressions as the smallest sufficient independent checks. No broader PASS is inferred.
- **Spec 001 T0-C: NOT_MEASURED / deferred.** No physical >=50-attempt four-channel UniKey evidence was gathered. T2 remains BLOCKED. No IME product fix was introduced.

## Route

**ROUTE PLAN.** No material PI-T002 proof defect is reproducible. PLAN may decide whether to authorize the next dependency-ordered PI-T003 lossless replay proof, while preserving the stop condition that no registry/WS/UI implementation proceeds unless replay/screen-state equivalence is actually demonstrated.

The only write by TEST is this required Git-ignored report.

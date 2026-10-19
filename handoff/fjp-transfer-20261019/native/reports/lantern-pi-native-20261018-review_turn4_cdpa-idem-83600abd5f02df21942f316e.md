# REVIEW turn 4 — FJP PI-T001 baseline + PI-T002 native PTY proof

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 4  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `c1ee6cc0d128451304172c84ec00574117091850`  
Disposition: **ROUTE DEV**. FJP PI-T001 characterization is materially sound, and the direct WinConPty POC is useful partial evidence, but PI-T002 stopped too early and did not satisfy the PLAN-required existing TerminalManager proof/test path.

## Independent sources checked

- `AGENTS.md`, PLAN turn 4, DEV turn 4, Spec 004 tasks/plan contract carried from prior turns.
- Current Git truth and feature diff.
- `lantern/terminal.py` `WinConPty`, `TerminalManager.__init__`, `_spawn_native`, `create`, and existing `pty_factory` injection.
- Existing `tests/test_terminal_scm.py` use of `TerminalManager(..., pty_factory=factory)`.
- Turn-4 artifacts:
  - `evidence-turn4/pi-t001-fjp-pi-t002-poc.md`
  - `pi_t002_probe.py`
  - `pi-t002-g6-winconpty-raw.txt`
  - `pi-t002-g6-winconpty.json`
  - `render_xterm.py`
  - `read_xterm_snapshot.js`
  - `pi-t002-xterm-snapshot.json`
- Actual FJP CLI/package/settings/package versions and installed Pi 1.3.0 slash/TUI docs/source.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / regression truth

Fresh REVIEW checks:
- `HEAD = c1ee6cc0d128451304172c84ec00574117091850`.
- local `main = ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0/1`.
- tracked worktree clean; feature diff remains only `M tests/test_terminal_ui.py`, the previously accepted Spec 001 T1 guard.
- `git diff --check`: exit 0.
- `test_terminal_ui.py`: 12 tests, OK, exit 0, 2.150 s.
- `test_terminal_scm.py`: 15 tests, OK, exit 0, 4.321 s.
- No full repository suite, CPU/RSS/latency benchmark, replay test, browser live-WS Pi E2E, or physical IME test was run by REVIEW; those remain INCOMPLETE/NOT_MEASURED.

Spec 001 preservation remains correct:
- T1 COMPLETE/accepted/committed.
- T0-C NOT_MEASURED/deferred.
- T2 BLOCKED.
- No IME/terminal product fix, input filtering/reordering/delay, vendored xterm change, Markdown implementation change, LAN/security policy, reset/stash/clean/merge/push, live :9999 restart, or CDPA modification occurred.

## PI-T001 FJP baseline review — supported

Fresh FJP read-only commands on device `lppduongnh66-1-7337f19f` independently confirmed:
- hostname `LPP00374779A`, account `fsoft.fpt.vn\duongnh66`;
- `pi --version = 1.3.0`;
- package `@earendil-works/pi-coding-agent@1.3.0`;
- configured packages: `pi-usage`, `pi-mcp-adapter`, `@tintinweb/pi-subagents`, `@tintinweb/pi-tasks`, `pi-lens`;
- exact installed versions: 0.3.0, 3.3.0, 0.19.0, 0.9.0, 4.3.0 respectively;
- user settings keys are only `packages,lastChangelogVersion`;
- standard user extension/skill/theme directories are absent;
- target G6 worktree path is absent on FJP;
- installed built-in slash source includes settings/model/fork/new/resume/hotkeys and no built-in help entry;
- installed TUI docs expose `ctx.ui.select/confirm/input/editor` and `ctx.ui.setWidget`;
- keybinding docs expose `app.clipboard.pasteImage` with `alt+v` on Windows/WSL.

The evidence correctly keeps live `/model` picker, `/goal`, custom extension UI, physical Ctrl/Alt/IME/image-paste, and PI-SC01/PI-T014 acceptance INCOMPLETE/NOT_MEASURED. No unsupported `/help` or `/goal` PASS claim was found.

## PI-T002 direct WinConPty evidence — valid but partial

The disposable harness really imports production `lantern.terminal.WinConPty` and passes a structured native argv list to installed Pi 1.3.0. It does not shell-quote Pi through `-Command`/`cmd /C`.

Artifacts support the narrow claims:
- settings output contains the 33-item native selector and selector guidance;
- resume output contains `Resume Session (Current Folder)`;
- raw output contains both the displayed `$ echo PI_NATIVE_SHELL_PROOF` command and a separate rendered `PI_NATIVE_SHELL_PROOF` output line, supporting actual local shell execution rather than mere input echo;
- Unicode/bracketed-paste editor text is present;
- `✓ New session started` is present;
- `/session` statistics/status output is present;
- the harness calls 100x32 -> 120x40 resize and records no exception;
- no saved session file is claimed;
- exit code 2 is recorded instead of relabeled clean.

The post-capture renderer does load the repository's vendored `static/vendor/xterm.js` and produces a non-null normal-buffer/cursor snapshot. DEV correctly classifies this as **render/consumability evidence only**. It is not live browser->WS->PTY proof, style/cell equivalence, alternate-screen proof, or PI-T003 replay proof. Also, the renderer replays the whole capture at 120x40 rather than reproducing the original 100x32 then resize sequence, so the snapshot must continue to be treated only as a synthetic render state, not as the actual final live terminal state. DEV's current wording already preserves that limitation, so this is not a separate defect.

## Finding R4-1 — PI-T002 stop condition is premature; existing TerminalManager test injection can launch the structured Pi argv without product changes

**Location/boundary:** DEV turn 4 section "TerminalManager stop condition discovered"; `lantern/terminal.py:342,351,424`; existing `tests/test_terminal_scm.py:116-125`.

**Violated contract/invariant:** The governing lane requires Pi to reuse **TerminalManager/WS/xterm ownership**, and the earlier PI-T002 proof plan explicitly called for `TerminalManager(pty_factory=...)` test injection before adding the production structured-argv seam. PLAN turn 4 also says to prefer test injection/isolated harness first and stop only if the available API makes the proof impossible without product expansion.

**Evidence:**  
`TerminalManager.__init__` accepts `pty_factory` and assigns it directly as the spawn owner. `create()` calls:

`self.pty_factory(term_id, safe_cwd, cols, rows, on_data, on_exit, command)`.

Existing repository tests already inject factories through this seam. A PI-T002 harness can therefore construct `TerminalManager(root, emit, pty_factory=<closure>)` where the closure instantiates the real production `WinConPty(pi_argv, str(cwd), cols, rows, on_data, on_exit)`. That uses a structured native argv without editing `TerminalManager.create` or starting PI-T005.

The DEV statement that PI-T002 must stop because TerminalManager cannot launch structured argv conflates the **future production public spawn API** with the **already available test-injection seam**. The public production seam is indeed missing and belongs to PI-T005, but it does not block the remaining PI-T002 proof.

**Required correction:** Continue the same PI-T002 subtask using existing `TerminalManager(pty_factory=...)` injection with real `WinConPty`. Drive Pi through `TerminalManager.create/input/resize/kill`, capture manager-emitted output/generation/list/replay metadata as appropriate, and keep the native argv inside the injected factory. Do not change production `terminal.py`, do not pass Pi through shell command strings, and do not start PI-T005.

## Finding R4-2 — required runnable PI-T002 test is missing

**Location/boundary:** `tests/test_pi_tui_e2e.py` is absent; DEV created only ignored `.plan/evidence-turn4/pi_t002_probe.py` and renderer helpers.

**Violated contract/invariant:** PLAN turn 4 requires: "Create or extend `tests/test_pi_tui_e2e.py` only with genuine runnable assertions." The overall workflow requires tests to prove acceptance rather than one-off narrative artifacts.

**Evidence:** Fresh repository check returns `MISSING` for `tests/test_pi_tui_e2e.py`; existing Pi tests are only legacy `test_pi_chat.py`, `test_pi_chat_ws.py`, and `test_pi_working_copy_guard.py`. The current proof script writes evidence and prints results but has no unittest/pytest assertions and is not part of the runnable suite.

**Required correction:** Add the smallest genuine PI-T002 E2E test file using the TerminalManager injection above. It should assert only the measurable native-TUI facts actually proven and skip/mark unavailable environment-dependent portions honestly. Do not encode FJP/browser/physical/PI-T003 claims as passing assertions. Evidence-only helpers may remain private, but the acceptance-bearing claims need a runnable test.

## Required review dimensions

- **Over-engineering/YAGNI:** direct WinConPty and vendored-xterm reuse are appropriately minimal; no duplicate ANSI emulator/protocol/service/catalog exists. The correction should reuse the existing `pty_factory` seam rather than introduce a new abstraction. Ponytail target: no production lines required for this PI-T002 correction.
- **Scope drift:** none detected into Markdown fidelity/diff/Crop/Milkdown, LAN/security, session registry, WS ownership implementation, replay, or UI replacement.
- **UI/UX/end-user:** native settings/resume/session TUI output demonstrates real Pi UI shape, but no live Lantern viewport/focus/accessibility evidence exists. Do not promote this to PI-T016.
- **Maintainability/module ownership:** direct `WinConPty` proves the low-level mechanism; PI-T002 still needs TerminalManager to remain the actual host owner in the proof. The future production structured-argv seam remains PI-T005.
- **Scalability/extensibility:** no registry/supervisor/resource architecture was prematurely added.
- **Native Pi parity/upstream:** FJP/G6 version-specific source facts are sound; provider/model/custom extension/goal/physical interaction parity remains incomplete.
- **Session/concurrency isolation:** not tested and must remain INCOMPLETE; do not infer one-writer/multiview semantics from this POC.
- **Regression/performance:** ordinary terminal focused tests are green; full regression and performance/resource acceptance remain unmeasured.
- **Tests prove acceptance:** not yet. This is the second material issue: PI-T002 measurable claims currently live only in ignored evidence scripts/artifacts.

## Route

**ROUTE DEV.** Correct R4-1 and R4-2 within the existing PI-T002 subtask only. No production source seam, PI-T003 replay work, PI-T004+ session architecture, Markdown changes, or LAN/security behavior is authorized. After the TerminalManager-backed runnable PI-T002 test/evidence exists, return to independent REVIEW, then independent TEST for the measurable claims before PLAN decides whether PI-T003 may start.

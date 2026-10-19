# DEV turn 4 — FJP PI-T001 baseline + PI-T002 native WinConPty proof

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
HEAD: c1ee6cc0d128451304172c84ec00574117091850
Disposition: REVIEW

> Turn-5 correction after independent REVIEW R4-1/R4-2: the statement below that PI-T002 had to stop before TerminalManager ownership proof was premature. `TerminalManager(pty_factory=...)` already provides the legal test-injection seam; turn 5 adds `tests/test_pi_tui_e2e.py` using that seam with real `WinConPty` and no production TerminalManager change. The future public structured-argv spawn API remains PI-T005.

## Contract followed

Read PLAN turn 4 and Spec 004 spec/plan/tasks. Loaded executing-plans, test-driven-development, ponytail, and verification-before-completion. This turn was limited to exactly two substantive items:
1. PI-T001 exact FJP baseline update.
2. PI-T002 evidence-first native PTY parity POC.

No PI-T003 replay work, PI-T004+ session architecture, production structured-spawn seam, WS ownership, UI replacement, Markdown implementation, LAN/security policy, or Spec 001 terminal fix was started.

## PI-T001 — exact FJP baseline

FJP command execution is currently available. Direct measurements on device lppduongnh66-1-7337f19f:
- hostname LPP00374779A
- account fsoft.fpt.vn\duongnh66
- pi --version = 1.3.0
- package = @earendil-works/pi-coding-agent@1.3.0
- package path = C:\Users\DuongNH66\AppData\Roaming\npm\node_modules\@earendil-works\pi-coding-agent\package.json

Configured user packages and installed versions:
- pi-usage@0.3.0
- pi-mcp-adapter@3.3.0
- @tintinweb/pi-subagents@0.19.0
- @tintinweb/pi-tasks@0.9.0
- pi-lens@4.3.0

Read-only settings inspection:
- ~/.pi/agent/settings.json keys: packages,lastChangelogVersion
- no user extensions/skills/themes declarations observed
- user extension/skill/theme directories returned no entries
- target path E:\git-project\lantern\.wt\lantern-bot is absent on FJP, so project-local .pi/settings.json for this exact worktree cannot be measured there

Installed 1.3.0 source/docs:
- built-in slash surface confirms /settings, /model, /new, /resume, /fork, /hotkeys
- no built-in /help entry; targeted source check returns HELP_ABSENT
- CLI help exposes --session, --session-id, --session-dir, --continue, --resume, --fork, --tui-mode fullscreen|regular, provider/model/tools/extensions/skills/themes controls
- TUI docs expose ctx.ui.select/confirm/input/editor and ctx.ui.setWidget
- keybinding docs define Ctrl/Alt handling and app.clipboard.pasteImage (alt+v on Windows/WSL)
- usage docs state image paste/drag support for compatible terminals
- configured package code scan returned GOAL_REGISTRATION_ABSENT_IN_CONFIGURED_PACKAGE_CODE; /goal live availability therefore remains NOT_MEASURED, not PASS

Stale turn-2 evidence artifact was updated to remove the obsolete "FJP broker unavailable" basis and point to the new turn-4 evidence. Historical turn reports were not rewritten as if their then-current observations never happened.

Primary evidence:
.plan/lantern-pi-native-20261018/evidence-turn4/pi-t001-fjp-pi-t002-poc.md

PI-T001 classification:
- exact FJP CLI/package/config/source baseline: measured
- live /model picker, /goal, custom extension UI, physical keyboard/IME/image-paste: INCOMPLETE/NOT_MEASURED
- PI-SC01 and PI-T014 are not satisfied

## PI-T002 — native PTY parity POC

### Production mechanism reused

The evidence harness imports and directly uses production lantern.terminal.WinConPty. It launches actual installed Pi 1.3.0 with a structured native argv list:
- node executable
- installed Pi dist/bundle/cli.js
- --offline --approve --no-mcp
- disposable --session-dir
- opaque UUID --session-id
- --tui-mode regular

CWD and session directory are disposable %TEMP% paths. No new PTY factory, terminal protocol, ANSI emulator, HTML transcript, model catalog, or command catalog was created.

Why G6 for the PTY POC:
- G6 owns the feature worktree and its uv environment already includes pywinpty.
- FJP Pi 1.3.0 is installed, but the target worktree is absent and available Python 3.12 reports ModuleNotFoundError: winpty.
- No package was installed on FJP merely to make the probe run.

### Clean ConPTY probe evidence

The clean second probe waited 8 seconds for startup and intentionally omitted provider/model selection.

Observed through WinConPty:
- /settings rendered the native 33-item settings selector and selector help
- /resume rendered "Resume Session (Current Folder)" with picker controls
- !!echo PI_NATIVE_SHELL_PROOF exercised local shell execution and marker bytes appeared in output
- bracketed-paste sequence ESC[200~...ESC[201~ containing "PASTE 日本語 tiếng Việt 😀" rendered in the native editor
- direct Unicode editor input "Unicode 日本語 tiếng Việt 😀" rendered intact
- Alt-word bytes and Ctrl+C were delivered without TUI crash; semantic shortcut parity is not claimed from bytes alone
- /new rendered "✓ New session started"
- /session rendered native session/statistics/status UI
- resize 100x32 -> 120x40 completed without exception
- WinConPty.close(graceful=True) ended the probe; exit callback reported code 2, recorded as-is
- no session file was created in this no-message run; persistence is not claimed

Evidence artifacts:
- .plan/.../evidence-turn4/pi_t002_probe.py
- .plan/.../evidence-turn4/pi-t002-g6-winconpty-raw.txt
- .plan/.../evidence-turn4/pi-t002-g6-winconpty.json

A first exploratory probe was discarded for /model acceptance because /model was entered before startup had settled and the TUI showed Working. Provider/billing side effects of that race are NOT_MEASURED. The clean probe did not use /model and no model-picker PASS is claimed.

### Existing xterm screen/cursor evidence

No hand-written ANSI parser was used. The clean captured ConPTY stream was replayed into the repository's exact vendored static/vendor/xterm.js in headless Edge.

Snapshot:
- buffer type normal
- cursor x=0, y=35
- buffer length 334
- baseY=294
- viewportY=294
- visible buffer contains native /session statistics/footer

Artifacts:
- render_xterm.py
- pi-t002-xterm-render.html
- read_xterm_snapshot.js
- pi-t002-xterm-snapshot.json

This proves the captured native Pi byte stream is consumable by the existing xterm implementation and yields a concrete screen/cursor state. It does NOT prove live browser/xterm -> Lantern WS -> PTY input routing, exact cell/style parity against a reference terminal, alternate-screen parity, or replay.

### TerminalManager stop condition discovered

Repository truth:
- TerminalManager.create(..., command: Optional[str]) exposes only a shell command string.
- TerminalManager._spawn_native wraps command using shell -lc, cmd /C, or PowerShell -Command.
- There is no public structured argv/cwd/env spawn seam through TerminalManager.

Therefore:
- native Pi through the existing production WinConPty mechanism is proven on G6;
- production Pi launch through TerminalManager with safe structured argv is NOT proven and cannot be added in this turn without starting the PI-T005 seam that PLAN explicitly withheld;
- passing Pi as a shell command string would weaken the stated structured-argv/no-quoting contract and was not done.

This is a PLAN turn-4 stop condition. No production source change was made.

## PI-T002 classification

PARTIAL PROOF / STOP BEFORE PRODUCT IMPLEMENTATION.

Measured:
- real Pi 1.3.0 interactive TUI through production WinConPty on Windows
- native settings/resume/session UIs
- local shell execution
- Unicode and bracketed paste into Pi editor
- /new session transition
- resize
- captured stream rendered by current vendored xterm with concrete buffer/cursor state

INCOMPLETE / NOT_MEASURED:
- FJP WinConPty through Lantern environment
- live browser/xterm -> existing WS -> TerminalManager -> Pi end-to-end path
- clean /model picker
- /goal live availability
- custom extension select/widget UI
- physical Ctrl/Alt/IME/UniKey/emoji/image paste
- normal vs alternate-screen cell/style parity
- PI-T003 reconnect/replay/two-viewer geometry
- session/concurrency ownership
- CPU/RSS/latency/resource acceptance

## Spec 001 preservation

- T1 remains COMPLETE / independently accepted / committed.
- T0-C physical >=50-attempt four-channel evidence remains NOT_MEASURED / deferred.
- T2 terminal product fix remains BLOCKED.
- No xterm input filtering, terminal PTY behavior, vendored xterm source, or backend transport behavior was changed.

## Tracked source state and verification

No tracked product/test file changed in turn 4. .plan evidence only.

Fresh checks actually run after evidence work:
- uv run python -m unittest discover -s tests -p test_terminal_ui.py -q
  - 12 tests, OK
- uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
  - 15 tests, OK
- git diff --check
  - exit 0
- git status --short --branch
  - branch feat/lantern-bot...origin/feat/lantern-bot [ahead 3], no tracked dirty path
- git rev-parse HEAD
  - c1ee6cc0d128451304172c84ec00574117091850
- git rev-list --left-right --count main...HEAD
  - 0 1

No full repository suite ran. A Playwright ordinary-terminal E2E attempt on G6 was not completed because the device broker timed out before returning a result; it is not claimed PASS.

## REVIEW request

Independent REVIEW must explicitly evaluate:
- exactness of the FJP 1.3.0 characterization and /help-/goal nonclaims
- whether direct WinConPty use is an acceptable PI-T002 partial proof while TerminalManager remains command-string-only
- whether the post-capture vendored-xterm snapshot is correctly classified as render evidence rather than live E2E
- over-engineering/YAGNI: evidence-only harness vs unnecessary production seam
- scope drift: no Markdown, LAN/security, replay, registry, WS, or UI implementation
- UX/native parity implications of real settings/resume/session TUI
- maintainability/module ownership and the structured-argv seam boundary
- session/concurrency isolation remains unaccepted
- regression/performance evidence is partial and honestly classified
- whether PI-T002 is strong enough to proceed, or PLAN must explicitly authorize the narrow TerminalManager structured-argv seam before any further proof

Route: REVIEW.

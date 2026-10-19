# PI-T001 FJP baseline + PI-T002 native PTY POC — DEV turn 4

Task: cdpa-idem-83600abd5f02df21942f316e
Date: 2026-10-18

## PI-T001 — exact FJP version/config/source baseline

Host measured directly:
- device: FJP `lppduongnh66-1-7337f19f`
- hostname: `LPP00374779A`
- account: `fsoft.fpt.vn\duongnh66`
- Pi: `@earendil-works/pi-coding-agent@1.3.0`
- package path: `C:\Users\DuongNH66\AppData\Roaming\npm\node_modules\@earendil-works\pi-coding-agent\package.json`
- `pi --version`: `1.3.0`

Configured user packages and exact installed versions:
- `pi-usage@0.3.0`
- `pi-mcp-adapter@3.3.0`
- `@tintinweb/pi-subagents@0.19.0`
- `@tintinweb/pi-tasks@0.9.0`
- `pi-lens@4.3.0`

User `~/.pi/agent/settings.json` top-level keys observed without printing secrets:
- `packages`
- `lastChangelogVersion`

No user `extensions`, `skills`, or `themes` declarations were present in that settings object. The standard user extension/skill/theme directories returned no files/directories in the read-only inspection.

Target worktree path `E:\git-project\lantern\.wt\lantern-bot` is absent on FJP, so project-local `.pi/settings.json` for this exact worktree cannot be measured on FJP. Do not infer target-worktree project configuration from G6.

### Version-specific native surface matrix

| Surface | FJP 1.3.0 evidence | Classification |
|---|---|---|
| `/settings` | Installed `docs/slash-commands.md` lists it; built-in source includes settings | source-confirmed |
| `/model` | Installed docs/source list it; CLI has provider/model/model-set flags | source-confirmed; live picker not exercised on FJP |
| `/new` | Installed docs/source list it | source-confirmed |
| `/resume` | Installed docs/source list it; CLI `--resume` exists | source-confirmed |
| `/fork` | Installed docs/source list it; CLI `--fork` exists | source-confirmed |
| help | CLI `pi --help` works; built-in slash list has `/hotkeys`, not `/help`; targeted source check returned `HELP_ABSENT` | exact version mismatch recorded; no Lantern shim |
| `/goal` | Not built-in. Configured user packages were scanned for direct `registerCommand("goal")`/single-quote equivalent outside nested dependencies; result `GOAL_REGISTRATION_ABSENT_IN_CONFIGURED_PACKAGE_CODE`. No user extension dir and target project config is absent on FJP. | live availability still NOT_MEASURED; no positive claim |
| shell/tools | CLI advertises read/bash/powershell/edit/write/grep/find/ls built-ins; native usage docs define `!` and `!!` shell execution | source-confirmed; actual local shell exercised later in G6 ConPTY POC |
| skills | CLI supports `--skill` and discovery controls; no FJP user skill declaration/dir content observed | framework source-confirmed; installed custom skill parity NOT_MEASURED |
| extensions | CLI supports extension discovery and explicit `--extension`; five configured packages above are present | source/config-confirmed |
| custom picker/editor UI | installed TUI docs expose `ctx.ui.select()`, `confirm()`, `input()`, `editor()`, and `ctx.ui.setWidget()` | source-confirmed; live custom extension UI NOT_MEASURED |
| Ctrl/Alt | installed keybindings docs define ctrl/alt modifiers and native editor/select/session bindings | source-confirmed; physical behavior NOT_MEASURED |
| clipboard image | installed keybindings docs define `app.clipboard.pasteImage`: `ctrl+v` generally, `alt+v` on Windows/WSL; usage docs say paste image/drag into compatible terminal | source-confirmed; physical image paste NOT_MEASURED |
| TUI mode/session flags | `pi --help` confirms `--session`, `--session-id`, `--session-dir`, `--continue`, `--resume`, `--fork`, and `--tui-mode fullscreen|regular` | CLI-confirmed |

No paid AI prompt was intentionally sent during FJP PI-T001 characterization. A retained-process attempt to type `/settings` did not produce inspectable TUI output because that broker session was not a terminal/screen harness; it is not counted as interactive parity evidence.

PI-T001 FJP classification after this turn: **PARTIALLY MEASURED / exact CLI-package-config-source baseline complete; interactive parity remains INCOMPLETE**.

## PI-T002 — evidence-first native PTY POC

### Mechanism

POC ran on G6 because the feature worktree and its locked Python environment are present there and `uv run python` has `pywinpty`. FJP has Pi 1.3.0 but the target worktree is absent and its available Python 3.12 does not have `winpty`; no package installation was performed.

The POC imports and directly uses the production `lantern.terminal.WinConPty` class. It launches the installed Pi 1.3.0 CLI as a **native argv list**:
- Node executable
- installed Pi `dist/bundle/cli.js`
- `--offline --approve --no-mcp`
- disposable `--session-dir`
- opaque UUID `--session-id`
- `--tui-mode regular`

CWD and session directory are disposable `%TEMP%` paths. No Lantern `:9999` process was touched. No product source, WS protocol, terminal protocol, ANSI parser, transcript, or command/model catalog was added.

Evidence files:
- `pi_t002_probe.py` — disposable proof harness
- `pi-t002-g6-winconpty-raw.txt` — exact ConPTY output stream
- `pi-t002-g6-winconpty.json` — bounded per-step snapshots/metadata
- `pi-t002-xterm-render.html`, `render_xterm.py`, `read_xterm_snapshot.js` — evidence-only current-xterm renderer
- `pi-t002-xterm-snapshot.json` — vendored xterm buffer/cursor snapshot

### Native interactions directly observed through WinConPty

Second clean probe waited 8 seconds for startup and deliberately omitted provider/model selection:
- `/settings` rendered the real settings selector with 33 entries and selector help text.
- `/resume` rendered `Resume Session (Current Folder)` with sort/name/path controls.
- `!!echo PI_NATIVE_SHELL_PROOF` executed the local native shell surface; the marker occurs in the ConPTY stream.
- Bracketed paste bytes `ESC[200~ ... ESC[201~` containing `PASTE 日本語 tiếng Việt 😀` rendered in the Pi editor.
- Direct Unicode editor input `Unicode 日本語 tiếng Việt 😀` rendered intact.
- Alt-word input (`ESC f`) and Ctrl+C were delivered without crashing the TUI; semantic keybinding parity is not claimed from raw bytes alone.
- `/new` rendered `✓ New session started`.
- `/session` rendered native session statistics/status with zero messages/tool calls.
- PTY resize 100x32 -> 120x40 completed without exception.
- `WinConPty.close(graceful=True)` terminated the probe; exit callback reported code 2. This is recorded, not reclassified as a clean Pi quit.
- The second no-message run produced no saved session file, so durable session persistence is **not** claimed.

A first exploratory probe was discarded for picker acceptance because `/model` was entered before startup had fully settled and the TUI showed `Working`; provider/billing side effects of that race are NOT_MEASURED. No `/model` command was used in the clean second probe and no model-picker PASS is claimed.

### Mature xterm rendering evidence

To avoid inventing an ANSI parser, the captured clean ConPTY stream was replayed into the repository's exact vendored `static/vendor/xterm.js` inside headless Edge. The resulting xterm snapshot reports:
- active buffer type: `normal`
- cursor: x=0, y=35
- buffer length: 334
- baseY=294
- viewportY=294
- visible buffer includes native `/session` statistics and the Pi status/footer.

This proves the captured native Pi byte stream is consumable by the existing xterm implementation and produces a concrete screen/cursor state. It does **not** prove live browser->WS->PTY input routing, exact style/cell parity against a reference terminal, alternate-screen parity, or reconnect/replay. Those remain for later gates.

### TerminalManager ownership proof and remaining production API gap

Repository inspection shows:
- `TerminalManager.create(..., command: Optional[str])` exposes only a shell-command string for its default production spawn path.
- `TerminalManager.__init__` already exposes `pty_factory` injection, and `create()` delegates terminal ownership to that factory with `term_id/cwd/cols/rows/on_data/on_exit/command`.
- The PI-T002 runnable test uses this existing seam to instantiate the real production `WinConPty(pi_argv, ...)` with structured native argv, then drives Pi through `TerminalManager.create/input/resize/replay_one/kill`.
- No production `terminal.py` change is needed for the proof.

The **future public production structured argv/env spawn seam** is still missing and remains PI-T005 work. PI-T002 does not solve or start that product API; it only proves that TerminalManager can remain the host owner while its existing test-injection seam launches real native Pi safely.

### Runnable TerminalManager-backed proof

`tests/test_pi_tui_e2e.py` is the acceptance-bearing runnable proof for the measurable PI-T002 claims. It is gated by `LANTERN_PI_TUI_E2E=1` and Windows so ordinary environments skip instead of fabricating a pass. The test creates `TerminalManager(..., pty_factory=closure)`, launches real `WinConPty` with the structured Pi argv, and asserts manager-owned lifecycle/output generation/sequence, native settings/resume/session UI, local shell output, Unicode + bracketed paste, `/new`, resize metadata, replay tail, and explicit kill cleanup. It does not assert browser/WS/reconnect/FJP-physical claims.

### PI-T002 classification

**PARTIAL PROOF / STOP BEFORE PRODUCT IMPLEMENTATION.**

Measured:
- actual Pi 1.3.0 interactive TUI through production WinConPty on Windows;
- real local settings/resume/session UI;
- local shell command surface;
- Unicode and bracketed-paste editor bytes;
- native session transition `/new`;
- resize;
- captured stream rendered by existing xterm to a concrete screen/cursor state.

NOT_MEASURED / INCOMPLETE:
- FJP WinConPty execution through Lantern's environment;
- live browser/xterm -> existing Lantern WS -> TerminalManager -> Pi end-to-end path;
- `/model` picker parity in the clean POC;
- `/goal` live availability;
- custom extension selector/widget UI;
- physical Ctrl/Alt/IME/UniKey/emoji/image-paste;
- normal vs alternate screen cell/style parity;
- lossless reconnect/replay and two-viewer geometry (PI-T003);
- session/concurrency ownership (PI-T004+);
- CPU/RSS/latency/resource acceptance.

No product change is made because the next required production seam belongs to a later authorized slice.

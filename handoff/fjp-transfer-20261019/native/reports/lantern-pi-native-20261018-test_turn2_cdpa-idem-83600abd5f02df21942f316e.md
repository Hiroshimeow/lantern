# TEST turn 2 — independent PI-T000/T001 characterization verification

Task: `cdpa-idem-83600abd5f02df21942f316e`  
Role: TEST, turn 2, hop 15  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Incoming PLAN: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-plan_turn3_cdpa-idem-83600abd5f02df21942f316e.md`  
Decision: **PARTIAL PASS with material evidence-state change; ROUTE PLAN.** PI-T000 G6 legacy UX characterization is independently supported. PI-T001 G6 1.3.0 characterization is independently supported. However, the retained evidence/PLAN claim that FJP PI-T001 remains NOT_MEASURED because the FJP shell broker cannot execute is now stale: during this TEST turn the FJP device executed `pi --version`, `pi --help`, and `pi list` successfully. This is a PLAN/evidence update, not an implementation defect. No product/test source was edited.

## Identity and repository state

Execution device for repository checks: G6 `desktop-b5e4iue-87cea2af`, hostname `DESKTOP-B5E4IUE`, Windows x64.  
Feature worktree: `E:\git-project\lantern\.wt\lantern-bot`.

Fresh commands:
- `git status --short --branch`
- `git diff --check`
- `git diff --name-status main..HEAD`
- `git rev-parse HEAD`
- `git rev-parse main`
- `git rev-list --left-right --count main...HEAD`

Actual:
- branch `feat/lantern-bot`, ahead of origin by 3;
- tracked worktree clean;
- `git diff --check` exit 0;
- feature diff against local main is only `M tests/test_terminal_ui.py`;
- `HEAD=c1ee6cc0d128451304172c84ec00574117091850`;
- `main=ffe3decb4469cff36bb98f8afd6ba8e9e89af089`;
- `main...HEAD = 0 1`.

Status: **PASS** for evidence-only slice scope preservation. No new Terminal/WS/Pi/UI/Markdown implementation source is present.

## PI-T000 — G6 legacy UX characterization

Durable evidence inspected:
- `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-g6-edge-390x844.png`: PNG, 34,074 bytes, metadata width/height exactly **390x844**.
- `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-g6-edge-1280x900.png`: PNG, 38,175 bytes, metadata width/height exactly **1280x900**.
- `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-g6-edge-1920x1080.png`: PNG, 42,040 bytes, metadata width/height exactly **1920x1080**.
- `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-t001-baseline.md`.

Visual inspection of all three screenshots confirms they show the existing **legacy HTML LanternBot chatbot** with bubbles/provider-model toolbar/compose UI, not a native Pi xterm/TUI. At 390px it appears as a bottom sheet over the editor; at desktop widths it is a fixed right-side overlay.

Fresh source checks:
- `static/chatbot.css:4`: `.lantern-chat-drawer ... width:min(440px,92vw)`.
- `static/chatbot.css:43` and `:58`: `@media(max-width:700px)`.
- `static/chatbot.css:44`: narrow layout `height:min(72dvh,680px)`.
- `static/chatbot.css:55`: chat-open Markdown content right-padding rule; repository editor source uses `.editor/.editarea`, so the source editor itself does not gain the desktop drawer reservation.
- `static/chatbot.js:69-77`: provider/model selects are owned by the HTML bot.
- `static/chatbot.js:205,223,231`: separate transcript/sessionStorage snapshot ownership exists.
- `static/chatbot.js:503-509`: opening chat adds the open state and focuses `#lanternChatInput` after 80 ms.
- `static/chatbot.js:109`: hint says Ctrl/Cmd+Enter.
- `static/chatbot.js:130-135`: unmodified Enter sends; Ctrl/Meta/Alt/Shift+Enter returns without sending.

Expected: corrected evidence accurately characterizes G6 legacy UI only and does not claim native Pi/FJP/IME/accessibility acceptance.  
Actual: source and screenshots match the corrected evidence, including the **<=700px** breakpoint and compose-hint mismatch. No native Pi dock/expand/fullscreen control is present in this legacy shell.  
Status: **PASS — PI-T000 G6 characterization only.**

FJP browser viewport/focus/IME/accessibility/end-user acceptance was not executed in this turn and remains **NOT_MEASURED** for PI-T000.

## PI-T001 — G6 provisional Pi 1.3.0 characterization

Fresh G6 commands:
- `pi --version`
- `pi --help`
- `pi list`
- `npm root -g`
- installed package `package.json` read-only inspection
- installed `dist/core/slash-commands.js` read-only inspection
- installed `dist/core/extensions/types.d.ts` targeted read-only inspection
- `~/.pi/agent/settings.json` keys/packages/extensions read-only inspection
- global `pi-goal-x` package presence/readme/package metadata read-only inspection

Actual:
- Pi version **1.3.0**.
- Package `@earendil-works/pi-coding-agent` version **1.3.0**.
- CLI includes `--continue`, `--resume`, `--session`, `--session-id`, `--fork`, `--session-dir`, `--models`, tool/extension/skill/theme controls, `--offline`, and `--tui-mode fullscreen|regular`.
- `pi list` matches the recorded G6 configured package inventory.
- settings keys and `extensions=-builtin:mcp` match the retained evidence; user skill directory `image-creation` exists; project `.pi/settings.json` does not.
- installed built-in slash-command source contains `settings`, `model`, `fork`, `new`, `resume` and **no `help` entry**.
- installed extension type definitions contain:
  - `session_start` with reason `startup|reload|new|resume|fork` and `previousSessionFile?`;
  - `session_before_switch` with `targetSessionFile?`;
  - `session_before_fork`;
  - `session_shutdown` with reason `quit|reload|new|resume|fork` and `targetSessionFile?`.
- global `pi-goal-x` version 0.31.2 is installed and documents `/goal`, but it is **not** in the observed G6 `pi list` configured package list; therefore the evidence correctly does not promote installation alone to live worktree availability.

Expected: G6 facts remain provisional characterization and do not justify Lantern shims/catalogs/session architecture.  
Actual: retained corrected G6 PI-T001 statements are independently supported.  
Status: **PASS — G6 provisional PI-T001 characterization.**

## Material FJP state change discovered by TEST

PLAN turn 3 and retained evidence state that FJP PI-T001 is NOT_MEASURED because the FJP broker failed before command execution with `spawn C:\windows\system32\cmd.exe ENOENT`.

Fresh TEST observation on FJP device `lppduongnh66-1-7337f19f`, hostname `LPP00374779A`, account `fsoft.fpt.vn\duongnh66`:

1. `pi --version` from `C:\` => **1.3.0**, exit 0.
2. `echo %COMPUTERNAME% & whoami & pi --version & pi --help & pi list & npm root -g` => exit 0.
3. FJP `pi --help` exposes the same native session/TUI family, plus FJP-specific extension flags from installed extensions.
4. FJP `pi list` reports configured packages including `pi-usage`, `pi-mcp-adapter`, `@tintinweb/pi-subagents`, `@tintinweb/pi-tasks`, and `pi-lens`.
5. FJP `pi.cmd` points at `@earendil-works/pi-coding-agent\dist\bundle\cli.js`; direct package/source inspection confirms package name/version **@earendil-works/pi-coding-agent 1.3.0** and built-ins `settings`, `model`, `fork`, `new`, `resume`; no `help` entry was returned by the targeted source check.

Therefore:
- The old reason for classifying FJP PI-T001 as NOT_MEASURED — **broker execution unavailable** — is no longer true.
- FJP PI-T001 is now **PARTIALLY MEASURED** for CLI/package/configured-package/source facts actually observed in this TEST turn.
- FJP interactive TUI behavior, physical keyboard/IME, Edge viewport UX, live `/help` behavior in a different Pi version, extension UI parity, `/goal`, paid-provider/model interaction, and native PTY/replay acceptance were **not executed** and remain **NOT_MEASURED/INCOMPLETE**.
- This environmental change does not authorize PI-T002/T003 implementation by TEST and does not justify a Lantern compatibility shim or command catalog.

This is a **PLAN/evidence contract update**, not a reproducible product implementation defect. The retained PI-T001 evidence is stale only in its FJP-availability classification.

## Other acceptance boundaries

- Spec 001 T1: prior accepted/committed evidence remains untouched; not rerun because no source drift affected it.
- Spec 001 T0-C: **NOT_MEASURED / deferred**. No physical UniKey 50+ run/four-channel evidence was performed.
- Spec 001 T2: **BLOCKED**.
- PI-T002/T003 native PTY/replay proof: **INCOMPLETE**, not started here.
- PI-T004 onward: not accepted or inferred.
- No full repository suite, browser automation, PTY screen equivalence, session concurrency, F5 replay, resource benchmark, accessibility acceptance, or release parity was run.

## Route

**ROUTE PLAN.** PI-T000 G6 characterization and PI-T001 G6 provisional characterization pass independent TEST. The FJP execution prerequisite changed during this TEST turn, so PLAN must update the evidence/classification and decide the smallest next legal characterization/proof slice using the now-accessible FJP read-only/runtime surface. Do not route DEV: no implementation failure was reproduced. Do not treat the newly available FJP CLI reads as native Pi parity or release acceptance.

No implementation/test source, git history, live Lantern :9999 process, or CDPA state was modified. The only write by TEST is this required Git-ignored report.

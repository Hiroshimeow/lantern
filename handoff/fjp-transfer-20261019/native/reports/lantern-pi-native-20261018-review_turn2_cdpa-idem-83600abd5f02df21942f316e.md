# REVIEW turn 2 — PI-T000/T001 characterization + accepted T1 housekeeping

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 2  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `c1ee6cc0d128451304172c84ec00574117091850`  
Disposition: **ROUTE DEV**. Two concrete evidence/characterization defects must be corrected before this slice can be accepted. No implementation edits made by REVIEW.

## Independent inputs checked

- `AGENTS.md`, PLAN turn 2, DEV turn 2, current `specs/004-pi-native-harness/tasks.md`, prior accepted T1 contract.
- Git truth: local `main = ffe3decb4469cff36bb98f8afd6ba8e9e89af089`; `main...HEAD = 0/1`; clean tracked worktree; `main..HEAD` changes **only** `tests/test_terminal_ui.py`.
- Rebased T1 commit `c1ee6cc` inspected directly. It contains the already accepted fake-xterm callback/onData guard only.
- PI-T000/T001 evidence artifact `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-t001-baseline.md`.
- All three screenshots visually inspected and metadata verified:
  - 390x844, 34,074 bytes
  - 1280x900, 38,175 bytes
  - 1920x1080, 42,040 bytes
- `static/chatbot.css`, `static/chatbot.js`, current Pi 1.3.0 CLI, installed package/docs/type definitions, `pi list`, sanitized settings key/package declarations, and the FJP broker path.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / accepted T1 housekeeping

PASS for the housekeeping portion:
- Branch was rebased onto current local main and is now one feature commit ahead.
- No conflict or cross-owner implementation diff is present.
- `git diff --name-status main..HEAD` => only `M tests/test_terminal_ui.py`.
- Fresh REVIEW checks:
  - `uv run python -m unittest discover -s tests -p test_terminal_ui.py -q`: 12 tests, OK, exit 0, 2.354 s.
  - `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`: 15 tests, OK, exit 0, 4.579 s.
  - `git diff --check main..HEAD`: exit 0.
- Spec 001 T0-C remains **NOT_MEASURED/deferred**. T2 remains **BLOCKED**. No terminal product fix is justified or introduced.

## PI-T000 review

Verified observations:
- Screenshots are genuine 390x844 / 1280x900 / 1920x1080 artifacts and visually show the existing legacy HTML bot, not a native Pi TUI.
- Desktop drawer width is `min(440px,92vw)`.
- At 390 px, the drawer becomes a large bottom sheet and covers most of the lower editor area.
- `static/chatbot.js:509` deliberately focuses `#lanternChatInput` 80 ms after opening; focus-steal characterization is source-supported.
- The compose hint says `Ctrl/⌘ + Enter to send` while `static/chatbot.js:131-134` sends on unmodified Enter and returns when Shift/Ctrl/Meta/Alt is pressed. This is a valid legacy UX inconsistency; no fix belongs in this characterization slice.
- Provider/model selects, custom transcript/tool rendering, and `sessionStorage` replay are present in the legacy UI. No native-TUI dock/expand/fullscreen implementation was added.
- FJP browser/physical UX remains correctly classified **NOT_MEASURED**.
- Independent FJP shell probe again failed before command execution with `spawn C:\windows\system32\cmd.exe ENOENT`; no FJP acceptance can be claimed.

### Finding R2-1 — wrong responsive breakpoint in the evidence

**Location:** `.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-t001-baseline.md`, PI-T000 source/runtime observation; mirrored in DEV turn 2 under "Observed legacy UX/state issues".  
**Violated contract:** PI-T000 is a measurement/characterization task; recorded UX facts must match repository truth exactly.  
**Evidence:** `static/chatbot.css:43-44` uses `@media(max-width:700px)` for the bottom-sheet layout. The evidence says **`<=760px`**. The `760px` breakpoint exists elsewhere in Lantern base/editor CSS, but not for the chatbot drawer.  
**Required correction:** change the PI-T000 evidence/handoff statement to **`<=700px`** for the chatbot bottom-sheet breakpoint. Do not alter product CSS in this slice.

## PI-T001 review

Verified G6 provisional facts:
- `pi --version` => **1.3.0**.
- Global package => `@earendil-works/pi-coding-agent@1.3.0`.
- `pi --help` verifies native interactive mode and `--session`, `--session-id`, `--session-dir`, `--continue`, `--resume`, `--fork`, `--tui-mode fullscreen|regular` with fullscreen default, provider/model/tools/extensions/skills/themes and offline/trust flags.
- `pi list` verifies the six reported user package declarations. Sanitized settings inspection independently confirms the reported top-level keys, package declarations, and `extensions=-builtin:mcp`; project `.pi/settings.json` is absent.
- `rpc-commands.md:834` explicitly states built-in TUI commands such as `/settings` are interactive-only and do not execute if sent as RPC prompts.
- Installed 1.3.0 type definitions verify:
  - `session_start` reasons `startup|reload|new|resume|fork` + optional `previousSessionFile`;
  - `session_before_switch` reasons `new|resume` + optional `targetSessionFile`;
  - `session_before_fork` `entryId` + `position`;
  - `session_shutdown` reasons `quit|reload|new|resume|fork` + optional `targetSessionFile`.
- `pi-goal-x@0.31.2` is globally installed and documents `/goal`, but it is absent from `pi list`; DEV correctly does **not** claim live `/goal` availability.
- FJP-specific PI-T001 remains correctly **NOT_MEASURED** because the broker cannot start `cmd.exe`.

### Finding R2-2 — false claim that Pi 1.3.0 local docs confirm a built-in `/help`

**Location:** DEV turn 2, PI-T001 bullet "Local versioned docs confirm /settings, /model, /new, /resume, /fork, /help"; same assertion is part of the characterization narrative.  
**Violated contract:** native Pi parity must follow the exact installed/versioned upstream mechanism; do not invent or preserve a stale command catalog. Spec 004 explicitly requires mature native/upstream parity rather than Lantern assumptions.  
**Evidence:** installed Pi 1.3.0 `docs/slash-commands.md` lists `/settings`, `/model`, `/new`, `/resume`, `/fork`, etc., but contains no `/help`. Installed `dist/core/slash-commands.js` enumerates the built-in slash commands and has **no `help` entry**; it does include `hotkeys`. A targeted source search returned `HELP_ABSENT`. `pi --help` is CLI option help and is not evidence for a native `/help` slash command.  
**Required correction:** remove the unsupported `/help` claim from the G6 1.3.0 baseline. Record explicitly that G6 1.3.0 does not expose built-in `/help` in the versioned slash-command list. Keep FJP `/help` status **NOT_MEASURED** until the actual FJP Pi version can be inspected. PLAN should later reconcile stale Spec 004 `/help` parity wording with the actual FJP/version-specific native help surface; do not add a Lantern `/help` shim or command catalog.

## Required REVIEW dimensions

- **Over-engineering/YAGNI:** no new production abstraction, dependency, protocol, registry, ANSI parser, or compatibility layer. Complexity finding: none; `net: -0 lines possible` for production because this slice is evidence-only.
- **Scope drift:** no feature-authored Markdown fidelity/diff/Crop/Milkdown, Pi runtime, Terminal/WS, LAN/security/policy, or UI implementation changes. The two Markdown commits in branch history are inherited from `main`, not feature diffs.
- **UI/UX/end-user:** viewport/focus/overlay evidence is useful and materially supports the need for dock/expand/fullscreen native TUI; the breakpoint must be corrected. No native-TUI UX has yet been accepted.
- **Maintainability/module ownership:** characterization supports replacing duplicate HTML/RPC ownership later with existing TerminalManager/WS/xterm + Pi-native session hooks; no parallel owner was introduced.
- **Scalability/extensibility:** no session registry/replay design was prematurely chosen. Resource ceilings and multiview ownership remain future proof obligations.
- **Native Pi parity / mature upstream:** CLI/session-hook evidence is strong provisional G6 source evidence, but the false `/help` assertion must be removed; FJP remains NOT_MEASURED.
- **Session/concurrency isolation:** not tested in this slice; PI-T002/T003 and later session work remain INCOMPLETE.
- **Regression/performance:** accepted T1 narrow regressions pass after rebase. No full suite, CPU/RSS/latency, replay, or Pi runtime performance was measured; classify as INCOMPLETE/NOT_MEASURED.
- **Tests prove acceptance:** current tests prove only the accepted Spec 001 T1 callback/transport guard. Screenshots/source inspection prove only G6 legacy-layout characterization. They do not prove native Pi, FJP, IME, replay, concurrency, or release acceptance.

## Route

**ROUTE DEV.** Correct R2-1 and R2-2 in the turn-2 evidence/handoff without changing production code. Preserve FJP items as NOT_MEASURED. After those evidence corrections, return to independent REVIEW; do not start PI-T002/T003 or implement any native session/replay mechanism yet.

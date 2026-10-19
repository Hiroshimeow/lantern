# PLAN turn 4 — accept characterization TEST, exploit restored FJP access, route PI-T001 completion + PI-T002 proof

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 4
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn2_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** Independent TEST accepted the durable G6 PI-T000 characterization and G6 provisional PI-T001 characterization, but discovered that FJP command execution is now available. The next legal work is to update/complete the exact FJP PI-T001 baseline and then perform the evidence-first PI-T002 native PTY parity POC. PI-T003 replay proof remains the following slice unless PI-T002 itself exposes a stop condition.

## Fresh repository and device truth

PLAN verified on G6:
- Branch: `feat/lantern-bot`.
- HEAD: `c1ee6cc0d128451304172c84ec00574117091850`.
- Local `main`: `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0 1`.
- Tracked worktree is clean.
- `main..HEAD` changes only `tests/test_terminal_ui.py`, the already accepted Spec 001 T1 guard.
- No native Pi/Terminal/WS/UI/Markdown implementation source exists in the feature diff yet.

PLAN also re-probed FJP device `lppduongnh66-1-7337f19f`:
- hostname: `LPP00374779A`;
- account: `fsoft.fpt.vn\duongnh66`;
- `pi --version` executes successfully and returns **1.3.0**.

Therefore the old FJP shell-broker failure is stale and must not remain the reason for NOT_MEASURED classification.

No reset, stash, clean, merge, push, live Lantern `:9999` restart, or CDPA change is authorized.

## Independent TEST turn 2 acceptance carried forward

### PI-T000
Independent TEST verified:
- retained screenshots are non-empty PNGs at exactly 390x844, 1280x900, and 1920x1080;
- they depict the legacy HTML LanternBot UI, not native Pi TUI;
- corrected source facts are accurate: chatbot drawer width, <=700px bottom-sheet breakpoint, focus steal, transcript/provider/model/sessionStorage ownership, no native dock/expand/fullscreen, and compose-hint mismatch;
- this is **G6 legacy UX characterization only**.

Classification:
- PI-T000 G6 characterization: **PASS / accepted**.
- PI-T000 FJP browser/focus/IME/accessibility baseline: **NOT_MEASURED** and remains a later acceptance item, not a blocker to source-level feasibility work.

### PI-T001
Independent TEST verified the G6 1.3.0 package/CLI/source characterization and additionally measured FJP:
- FJP `pi --version`, `pi --help`, and `pi list` execute successfully.
- FJP Pi package is `@earendil-works/pi-coding-agent` 1.3.0.
- FJP exposes the same native TUI/session CLI family.
- FJP configured packages include `pi-usage`, `pi-mcp-adapter`, `@tintinweb/pi-subagents`, `@tintinweb/pi-tasks`, and `pi-lens`.
- targeted installed source shows built-ins including settings/model/fork/new/resume and no built-in `help` entry.

Classification update:
- FJP PI-T001 is no longer “NOT_MEASURED because broker unavailable.”
- It is now **PARTIALLY MEASURED** for exact CLI/package/configured-package/source facts.
- Interactive TUI behavior, extension custom UI parity, live /goal availability, physical keyboard/IME, and paid-provider interactions remain **NOT_MEASURED/INCOMPLETE** unless directly exercised.

This TEST result is accepted. No new REVIEW is needed before continuing because the prior evidence corrections already passed clean REVIEW and TEST found no implementation defect.

## Governing invariants unchanged

- Spec 001 T1: COMPLETE / independently accepted / committed.
- Spec 001 T0-C: NOT_MEASURED / deferred; no physical >=50-attempt evidence exists.
- Spec 001 T2: BLOCKED. Do not implement an IME fix.
- Do not touch Markdown fidelity/diff/Crop/Milkdown/source implementation except a separately justified shared boundary.
- Pi must be native interactive TUI through existing PTY/ConPTY + xterm, not RPC/HTML transcript reconstruction.
- No Lantern-maintained command/model catalog, no hidden prompt wrapper, no fake /help compatibility command.
- No new LAN policy/security/token quota/auth/sandbox behavior.
- Do not infer PASS from unrun FJP/browser/physical behavior.
- Do not begin PI-T004+ session architecture until PI-T002 and PI-T003 proof gates succeed.

## Next DEV turn — at most two coherent subtasks

### DEV subtask 1 — complete/update PI-T001 exact FJP baseline

This is characterization/evidence work, not product implementation.

On actual FJP, using read-only CLI/source/package inspection and interactive commands that do **not** require a paid AI prompt:
1. Record exact `pi --version`, `pi --help`, `pi list`, installed package path/version, configured extension/skill/theme/package declarations, and any project-local Pi settings relevant to this worktree.
2. Build/update a concise parity matrix for the native surfaces required by Spec 004:
   - `/model`
   - `/settings`
   - `/new`
   - `/resume`
   - `/fork`
   - `/goal` availability on FJP
   - help surface as actually exposed by this Pi version (do not assume `/help`)
   - shell/tool execution surface
   - skills
   - extensions
   - extension custom/select/picker UI hooks
   - Ctrl/Alt/paste/image-relevant TUI capabilities where source/API inspection can establish support without claiming physical acceptance.
3. Use the installed 1.3.0 extension/session APIs as version-specific truth. If a capability requires a paid provider or physical UI action, mark it NOT_MEASURED instead of simulating it.
4. Update the ignored evidence artifact so the stale “FJP broker unavailable” wording is removed everywhere relevant.
5. Do **not** edit Spec 004 command wording merely to match one version unless PLAN later authorizes a spec correction; record the version mismatch instead.

Acceptance for this subtask is exact characterization only. It does not satisfy PI-SC01 or PI-T014.

### DEV subtask 2 — PI-T002 native PTY parity POC

After the FJP baseline is recorded, perform the smallest evidence-first POC using the existing terminal stack.

Required approach:
- Reuse `lantern/terminal.py` / current `NativePty` / WinConPty mechanisms. Do not create a Pi-only PTY factory, custom terminal protocol, ANSI emulator, HTML transcript, or model/command catalog.
- Use a disposable cwd/session directory and an actual native interactive Pi process.
- Prefer test injection / isolated harness first. Product source changes are not authorized unless the current API makes the native argv launch impossible and the smallest change is demonstrably required; if that occurs, stop and report the exact missing contract rather than broadening architecture.
- Create or extend `tests/test_pi_tui_e2e.py` only with genuine runnable assertions. If browser/xterm automation cannot run on FJP yet, split assertions honestly between:
  - actual ConPTY process/native TUI evidence;
  - source/API characterization;
  - NOT_MEASURED browser/physical items.
- Do not send a paid AI prompt solely for characterization. Native slash commands/settings/model picker/session transitions that are local may be exercised.
- Capture terminal bytes plus screen/cursor evidence through a mature/native xterm-capable mechanism when available; do not claim screen parity from raw byte presence alone.
- Exercise as many of the PI-T002 native interactions as can be legally verified without crossing into PI-T003 replay:
  - startup native TUI;
  - model/settings/session command surfaces;
  - picker/custom UI if available;
  - Ctrl/Alt and ordinary keyboard routing;
  - bracketed paste;
  - Unicode/CJK path/content where feasible;
  - image/paste capability only if actually supported and locally testable;
  - process exit/cleanup.
- Ordinary Terminal behavior must remain unchanged.

### Stop conditions for DEV turn 4

Route back without speculative implementation if any of these occur:
- current TerminalManager cannot launch a native argv safely without a product API change larger than the narrow structured-argv seam already anticipated;
- FJP Pi requires undocumented/proprietary behavior that cannot be proven from the installed version;
- screen/cursor/native TUI assertions cannot be made honestly with the available harness;
- the only way forward would be a custom ANSI emulator, duplicate terminal service, hidden keyboard/prompt injection, or a Lantern command catalog;
- any required change would cross Markdown implementation ownership or introduce unapproved LAN/security behavior.

Do **not** start PI-T003 lossless replay, PI-T004 registry, PI-T005 production structured-spawn implementation, PI-T006 WS ownership, or UI replacement in this DEV turn unless PLAN explicitly routes them later.

## REVIEW after DEV

Independent REVIEW must evaluate:
- correctness of FJP version-specific characterization;
- no stale “broker unavailable” claims;
- no unsupported /help or /goal claims;
- native/upstream mechanisms preferred over Lantern shims;
- PTY proof uses the existing terminal stack rather than a duplicate runtime;
- no over-engineering or speculative session/replay architecture;
- UX implications of the actual native TUI;
- maintainability/module boundaries;
- concurrency/session behavior not falsely accepted before PI-T004/T006;
- regression/performance evidence honestly classified;
- no Markdown or security/LAN scope drift;
- whether PI-T002 proof is strong enough to proceed to PI-T003.

Then route independent TEST for any measurable PI-T002 claims before PLAN authorizes PI-T003.

## Classification after PLAN turn 4

- Spec 001 T1: **COMPLETE / accepted / committed**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000 G6: **PASS / accepted characterization**.
- PI-T000 FJP browser/physical: **NOT_MEASURED**.
- PI-T001 G6: **PASS / accepted provisional characterization**.
- PI-T001 FJP: **PARTIALLY MEASURED; actionable to complete exact baseline now**.
- PI-T002: **ACTIONABLE / next proof task**.
- PI-T003: **INCOMPLETE; hold until PI-T002 REVIEW/TEST acceptance**.
- PI-T004-T013: **DEPENDENT / not authorized yet**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- Overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 4. This required PLAN report is the only artifact written by this role.

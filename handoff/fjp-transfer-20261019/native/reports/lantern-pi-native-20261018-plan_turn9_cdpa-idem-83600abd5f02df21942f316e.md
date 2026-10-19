# PLAN turn 9 — close PI-T003 phase-0 gate; route PI-T005 structured native spawn seam

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 9
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn6_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** PI-T003 now has clean independent REVIEW and TEST acceptance for the bounded same-geometry public replay-continuity proof gate. Preserve and commit that accepted slice, rebase the latest unrelated Markdown main change, then implement **PI-T005 only**: a generic server-internal structured argv/cwd/env spawn seam through the existing TerminalManager/native PTY ownership. Do not start PI-T004 registry in the same turn.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- branch: `feat/lantern-bot`;
- HEAD: `69214a799c4708b785136462fa2ce126df88d186`;
- current local `main`: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`;
- `main...HEAD = 1 3`;
- merge base: `44b65ff5aac4bffa015385bbed3d0ce8643484c9`;
- current uncommitted continuity slice changes exactly:
  - `lantern/terminal.py`;
  - `lantern/ws.py`;
  - `static/terminal_scm.js`;
  - `tests/test_pi_reconnect_e2e.py`;
  - `tests/test_terminal_scm.py`;
  - `tests/test_terminal_ui.py`;
- no other tracked path is dirty.

The only current main-only commit is:

`4b32a79 feat(markdown): integrate CodeMirror Source editor`

Its paths are Markdown-owner only:
- `static/markdown_anchor_bridge.js`;
- `static/markdown_visual_shell.css`;
- `static/markdown_visual_shell.js`;
- `static/vendor/lantern-crepe.manifest.json`;
- `static/vendor/lantern-source-editor.min.js`;
- `tests/test_source_codemirror_e2e.py`;
- `tools/build_markdown.mjs`;
- `tools/source_markdown_entry.js`.

It does not overlap Terminal/Pi ownership.

Feature committed paths from the current merge base are the three accepted test files:
- `tests/test_terminal_ui.py`;
- `tests/test_pi_tui_e2e.py`;
- `tests/test_pi_reconnect_e2e.py`.

## PI-T003 phase-0 gate: ACCEPTED / COMPLETE for dependency progression

REVIEW turn 13 found the continuity implementation clean and within the PLAN-authorized generic terminal-v2 seam. TEST turn 6 independently reproduced the acceptance.

Independent TEST facts:

- enabled `tests.test_pi_reconnect_e2e`: **7/7 executed, all OK**;
- `test_terminal_scm.py`: **17 OK**;
- `test_terminal_ui.py`: **13 OK**;
- LAN multi-client focused regression: **19 OK**;
- full ordinary suite: **357 tests OK, 132 skipped**;
- Python/Node syntax and `git diff --check`: PASS.

The accepted continuity implementation:
- retains one bounded terminal output buffer;
- tracks UTF-8 retained start and stream end positions;
- exposes `replayStartUtf8` / `replayEndUtf8` for the actual public replay payload;
- accounts for both manager retention and the later WS display cap;
- uses browser `TextEncoder` semantics;
- preserves old `replay_one()` compatibility and ordinary terminal reset+write behavior;
- introduces no unbounded history, duplicate transcript, snapshot persistence, Pi-specific WS protocol, session registry, writer/takeover logic, or custom ANSI state engine.

Accepted proof boundary:
- bounded raw-tail-only replay remains non-lossless;
- server-headless serializer -> vendored browser remains a failed representation;
- exact vendored-client native-Pi snapshot round-trip at 120x40 is exact under the full cell/style/cursor/buffer/mode/geometry oracle;
- exact snapshot + complete ordered Unicode-bearing public delta is exact;
- manager-retention and WS-display-cap gaps are detectable and rejected before partial restore;
- snapshot-at-start and snapshot-at-end boundaries are handled safely;
- no input resend is proven in the deterministic boundary fixture;
- different-width equivalence remains false.

Therefore **PI-T003 is COMPLETE as the Phase-0 replay feasibility gate** needed to unlock the session foundation.

This does **not** promote broader release evidence:
- actual browser F5/live reconnect remains NOT_MEASURED;
- snapshot persistence has not been implemented;
- viewers at arbitrary independent PTY widths are not supported by the proof;
- physical FJP IME/AltGr/image paste remains NOT_MEASURED;
- live model/goal/custom extension parity remains incomplete;
- resource/CPU/RSS/latency acceptance remains NOT_MEASURED.

The geometry result becomes a foundation invariant: future shared-session design has one canonical PTY/resize owner. Read-only viewers may have different browser viewport pixels, but they must not independently reflow/resize the same PTY state without explicit ownership transfer.

## Preserved Spec 001 boundary

- T1: **COMPLETE / independently accepted / committed**.
- T0-C physical >=50-attempt four-channel evidence: **NOT_MEASURED / deferred**.
- T2 terminal product fix: **BLOCKED**.
- No UniKey-specific filtering, delay, reordering, input rewrite, or terminal product fix is authorized.

## Dependency decision

The next foundation tasks are PI-T004–T007, but implementation order remains:

**PI-T005 structured native spawn seam -> PI-T004 session registry -> PI-T006 scoped WS ownership -> PI-T007 lifecycle.**

PI-T005 must precede PI-T004 because the registry must launch native Pi with exact structured argv/cwd/env rather than shell command strings or a Pi-specific PTY factory.

To preserve small independently reviewed slices, **this DEV turn is PI-T005 only**. PI-T004 remains the next slice after REVIEW/TEST accept PI-T005.

## DEV housekeeping — commit accepted continuity slice, then rebase

Before PI-T005 edits:

1. Reconfirm the six-file continuity diff is exactly the independently accepted TEST turn-6 candidate.
2. Run `git diff --check`.
3. Selectively stage only those six accepted files; never `git add -A`.
4. Commit with a narrow terminal replay-continuity message.
5. Confirm tracked worktree clean.
6. Rebase `feat/lantern-bot` onto current local `main`.
7. Do not stash/reset/clean/merge.
8. If any rebase conflict occurs, especially in Markdown-owner files, abort safely and route PLAN. Do not resolve cross-owner conflicts by guesswork.
9. After clean rebase, verify:
   - `main...HEAD = 0 4`;
   - the feature diff contains only owned Terminal/Pi test/runtime paths;
   - no Markdown-owner path appears in the feature diff.

If main advances again before PI-T005 source editing, re-check its merge-base paths. Rebase again only if the new changes remain outside this lane.

The accepted continuity slice does not need its full acceptance suite repeated merely to commit it. A focused smoke plus `git diff --check` after rebase is sufficient unless the rebase changes relevant source.

## Next substantive task — PI-T005 only

### Objective

Add the smallest **generic, server-internal structured native-process spawn API** to `TerminalManager` so a future PiSessionRegistry can launch installed Pi directly through existing WinConPty/PosixPty without:
- shell command strings;
- PowerShell `-Command`;
- `cmd /C`;
- shell quoting;
- a Pi-only PTY factory;
- a second terminal protocol.

This is an internal spawn seam, not a browser/WS feature.

### Allowed implementation paths

Primary:
- `lantern/terminal.py`;
- `tests/test_terminal_scm.py`;
- `tests/test_pi_tui_e2e.py`.

Only add another focused test file if it clearly improves isolation. Do not edit application/chatbot/WS/frontend for PI-T005.

### API requirements

DEV may choose the smallest maintainable public-in-Python shape, such as:
- keyword-only `argv` / `env` on `TerminalManager.create()`; or
- a dedicated generic `create_argv(...)`/equivalent method.

REVIEW should judge the concrete shape, but the behavior is fixed:

1. Structured `argv` is a list/sequence of exact argument strings and is passed to the native PTY without shell re-parsing.
2. Existing interactive-shell `create()` behavior remains unchanged for ordinary Terminal.
3. Existing `run_command()` shell-string behavior remains unchanged.
4. Supplying both structured argv and shell command is rejected explicitly.
5. CWD still goes through the existing configured-root containment check.
6. Optional environment is an overlay on the child environment, not a replacement of Lantern's own process environment.
7. PTY defaults such as `TERM=xterm-256color` and `LANG=en_US.UTF-8` remain available, while an explicit structured-spawn override may replace a default intentionally.
8. The caller's env mapping must not mutate `os.environ`.
9. WinConPty and PosixPty receive the same generic env contract.
10. Do not expose env values in terminal metadata/events/logs.
11. Do not serialize argv/env to ordinary terminal clients unless an existing safe field already requires it.
12. New structured spawn is **server-internal only** in this slice.

### Critical security/scope boundary

Do **not** add `argv` or `env` fields to the existing browser `terminal_create` / `terminal_run` WebSocket API.

Remote/client-controlled arbitrary process argv/env is not required for native Pi and would be a new security surface. PI-T005 only prepares an internal Python API that the later server-owned Pi registry can call.

Do not add LAN policy, whitelist/blacklist, auth, token/call limits, or sandbox behavior.

### Backward compatibility

Existing test factories currently accept the legacy shape ending in `command=None`. Preserve ordinary test and production callers without forcing unrelated refactors.

If the implementation extends the injected factory interface:
- old factories must still work for ordinary shell terminals; or
- update only the narrow owned test helpers with a simple compatibility adapter.

Do not replace TerminalManager with a generic process framework.

### Native PTY environment contract

Both `WinConPty` and `PosixPty` currently build an internal environment copy.

Implement the structured env overlay at this lowest common ownership point or an equally small shared helper.

Required:
- child gets a fresh environment dict;
- standard PTY defaults are applied;
- structured env overlay is applied predictably;
- no parent env mutation;
- values are strings;
- no secrets are printed by tests.

No new dependency.

## Required TDD/acceptance cases for PI-T005

### 1. Exact argv, no shell wrapping

Use arguments containing:
- spaces;
- Unicode;
- quotes;
- `&`, `;' or other shell metacharacters.

Assert the native spawn boundary receives the exact list elements unchanged.

Assert no added:
- `-Command`;
- `/C`;
- `-lc`;
- shell quoting layer.

### 2. Shell behavior preserved

Existing ordinary terminal:
- no command -> current interactive shell;
- `run_command` / command string -> current platform shell wrapping.

No behavioral regression.

### 3. Mutual exclusion

Structured argv + command string together must fail clearly before process spawn.

Empty argv must fail clearly.

### 4. CWD containment

Structured spawn must still reject a cwd outside configured root and normalize a valid inside-root cwd exactly as existing terminal creation does.

### 5. Env overlay

Prove:
- inherited env survives;
- TERM/LANG defaults are set when absent;
- explicit overlay values reach child/native spawn;
- explicit overlay may override a default intentionally;
- Unicode env value remains exact;
- parent `os.environ` is unchanged.

### 6. Platform ownership

Unit-level tests must establish the same structured argv/env contract for both native backends without creating a second backend.

On G6, actual Windows ConPTY is the runnable native acceptance environment. If a real POSIX runtime is unavailable in this turn, test the shared platform-independent construction/dispatch path and keep real POSIX process execution **NOT_MEASURED**, not PASS.

### 7. Existing factory seam

Existing `pty_factory` injection and ordinary Terminal tests must remain usable.

### 8. Production Pi seam proof

Update the already accepted gated `tests/test_pi_tui_e2e.py` so its native Pi launch uses the **new production structured-spawn API**, not the special `pty_factory` closure used only for PI-T002 proof.

On G6:
- use the already characterized installed Pi 1.3.0 node + CLI bundle argv;
- use a disposable cwd/session-dir;
- keep `--offline`;
- no paid AI prompt;
- verify exact argv ownership/no shell wrapper;
- retain the local native settings/resume/session/new/shell/Unicode/resize/cleanup assertions that are stable;
- no browser/WS/FJP physical claim.

This is the key acceptance that PI-T005 is a real production seam, not merely a unit-test abstraction.

## Stop conditions

Return to REVIEW/PLAN without broadening if:
- structured argv cannot be added without changing the public browser terminal API;
- environment support would require exposing secrets or a new remote policy surface;
- the only implementation would create a Pi-specific PTY manager;
- ordinary terminal shell behavior would need a large rewrite;
- a platform limitation requires shell-wrapping Pi again;
- changes would cross Markdown implementation ownership.

Do not begin PI-T004 as a workaround.

## Explicitly forbidden this DEV turn

Do not start:
- `lantern/pi_sessions.py`;
- PiSessionRegistry;
- session ID/path/context policy;
- writer/viewer/takeover logic;
- Pi-specific WS events;
- reconnect snapshot persistence;
- restart lifecycle/supervisor;
- chatbot UI replacement;
- model/command catalog;
- Markdown implementation changes;
- Spec 001 T2 IME fix;
- LAN/security/auth/policy features.

Never restart or attach to live Lantern `:9999`; never modify/reload CDPA.

## Required REVIEW after PI-T005

Independent REVIEW must explicitly evaluate:

- exact argv preservation and absence of shell wrapping;
- command/argv mutual exclusion;
- env overlay semantics and parent-env immutability;
- no env/secret exposure in metadata/events;
- WinConPty/PosixPty module ownership;
- server-internal-only boundary; no new WS attack surface;
- ordinary terminal backwards compatibility;
- existing factory/test compatibility;
- production Pi e2e uses the new seam rather than test injection;
- YAGNI / no process-framework over-abstraction;
- maintainability and future PI-T004 suitability;
- cross-platform evidence honesty;
- no Markdown/LAN/security scope drift;
- focused/full regression evidence.

If REVIEW is clean, route independent TEST. Only after TEST acceptance should PLAN authorize PI-T004.

## Classification after PLAN turn 9

- Spec 001 T1: **COMPLETE**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: accepted characterization; FJP browser/physical incomplete.
- PI-T001: FJP/G6 baseline materially characterized; live release parity incomplete.
- PI-T002: **COMPLETE for narrow native TerminalManager/WinConPty proof**.
- PI-T003: **COMPLETE for Phase-0 bounded same-geometry replay feasibility/continuity gate**; browser F5/live/release evidence remains later acceptance.
- PI-T005: **ACTIONABLE NOW / next implementation slice**.
- PI-T004: **NEXT after PI-T005 acceptance**.
- PI-T006/PI-T007: **DEPENDENT / not authorized yet**.
- PI-T008-T013: **DEPENDENT / not authorized yet**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 9. This required PLAN report is the only artifact written by PLAN.

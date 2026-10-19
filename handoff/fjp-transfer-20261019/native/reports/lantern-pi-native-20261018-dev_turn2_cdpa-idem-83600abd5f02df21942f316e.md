# DEV turn 2 — accepted T1 commit/rebase + PI-T000/T001 characterization
Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Skills / contract used
Loaded executing-plans, test-driven-development, ponytail, and verification-before-completion. Re-read AGENTS.md and PLAN turn 2. No new production behavior was authorized in this slice.

## A. Accepted Spec 001 T1 housekeeping
Incoming state:
- HEAD b2ffd886795840f0db570b8c07a913b406e68e80
- local main ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- main...HEAD = 2/0
- only tracked diff: tests/test_terminal_ui.py
- git diff --check: clean

Actions:
1. Selectively staged only tests/test_terminal_ui.py.
2. Committed accepted guard as:
   - pre-rebase commit: 30712bf test(terminal): guard native xterm IME forwarding
3. Rebased feat/lantern-bot onto local main. No conflict occurred; no reset/stash/clean/merge/push.
4. Rebased commit is now:
   - c1ee6cc0d128451304172c84ec00574117091850 test(terminal): guard native xterm IME forwarding
5. Current base relationship:
   - main = ffe3decb4469cff36bb98f8afd6ba8e9e89af089
   - main...HEAD = 0/1

Fresh post-rebase checks actually run:
- uv run python -m unittest discover -s tests -p test_terminal_ui.py -q -> 12 OK
- uv run python -m unittest discover -s tests -p test_terminal_scm.py -q -> 15 OK
- git diff --check -> exit 0
No repeat review/test was invented; PLAN turn 2 explicitly carries independent T1 acceptance forward.

Spec 001 state:
- T1 COMPLETE/accepted/committed.
- T0-C physical >=50-attempt four-channel evidence: NOT_MEASURED / deferred.
- T2 terminal product fix: BLOCKED.
- No terminal product source, vendored xterm, PTY, WS, Markdown, or UI implementation was changed.

## B. PI-T000 UX baseline characterization
Evidence artifact:
.plan/lantern-pi-native-20261018/evidence-turn2/pi-t000-t001-baseline.md

Screenshots copied into ignored evidence directory:
- evidence-turn2/pi-t000-g6-edge-390x844.png (34,074 bytes)
- evidence-turn2/pi-t000-g6-edge-1280x900.png (38,175 bytes)
- evidence-turn2/pi-t000-g6-edge-1920x1080.png (42,040 bytes)

Method:
- G6 / Edge 155.0.4283.45.
- Disposable Lantern instance only, root under %TEMP%, bound to 127.0.0.1:18089.
- Sample source page: /sample.md?edit=1.
- Existing rebased chatbot.js/css used unchanged.
- Exact viewport forced through Edge DevTools emulation; launcher clicked through DevTools; screenshots captured from the actual page.
- Disposable server was terminated. Initial session termination left the child listener alive; verified the listener process on 18089 and terminated that specific disposable child only. Final probe reports 18089 closed.
- User Lantern :9999 was never restarted or attached.

Measured runtime geometry:
- 390x844: chat drawer x=0 y=236.33 w=390 h=607.67; editarea remains x=0 y=59 w=390 h=784; drawer overlays lower ~72% of editor; focus moves to lanternChatInput.
- 1280x900: drawer x=840 y=0 w=440 h=900; editarea remains full 1280px wide; right 440px is overlaid; focus moves to chat input.
- 1920x1080: drawer x=1480 y=0 w=440 h=1080; editarea remains full 1920px wide; right 440px is overlaid; focus moves to chat input.

Observed legacy UX/state issues, characterization only:
- Desktop drawer uses fixed 440px target width; <=700px becomes a bottom sheet at up to 72dvh.
- Source editor does not reserve drawer width, so right-side caret/content can be hidden on desktop.
- Opening chat steals editor focus into the chat textarea.
- Legacy HTML bot owns provider/model selects, transcript/tool rendering and sessionStorage replay, i.e. duplicate UI/state that Spec 004 plans to remove only after native parity proof.
- No expand/fullscreen native-TUI workspace controls exist in the legacy shell.
- Existing compose hint says Ctrl/Cmd+Enter to send, but code sends on plain Enter and returns for modified Enter. No fix was authorized or made.
- 390px source remains visible only above the bottom sheet; the bot covers most of the edit area.

FJP UX/browser/physical IME baseline: NOT_MEASURED. FJP device shell still fails before command execution with:
spawn C:\windows\system32\cmd.exe ENOENT
No FJP screenshot, physical keyboard, focus, timing, or Pi acceptance is claimed.

## C. PI-T001 native Pi CLI/config characterization
FJP-specific PI-T001: NOT_MEASURED due the same broker failure above.

G6 provisional reference only:
- pi --version = 1.3.0
- installed package = @earendil-works/pi-coding-agent 1.3.0
- CLI help confirms interactive native TUI and --session, --session-id, --session-dir, --continue, --resume, --fork, --tui-mode fullscreen|regular (fullscreen default), provider/model/model-set flags, tools, extensions, skills, themes, --offline, and trust flags.
- pi list reports user packages: @tintinweb/pi-subagents, pi-mcp-adapter, @juicesharp/rpiv-todo, pi-web relay package, pi-web-ui, and zero-mem.
- Sanitized user settings inventory recorded key names only and package/resource declarations; no secrets were printed. Built-in MCP is explicitly disabled with extensions="-builtin:mcp"; one user skill directory image-creation is present; no project .pi/settings.json exists here.
- Local versioned docs confirm /settings, /model, /new, /resume, /fork and native TUI extension APIs. The installed 1.3.0 built-in slash-command list does not expose /help; FJP /help status remains NOT_MEASURED until the actual FJP Pi version can be inspected. RPC docs explicitly state built-in TUI commands such as /settings are not handled as RPC prompt commands.
- Local 1.3.0 type definitions expose native session transition hooks:
  - session_start reason startup|reload|new|resume|fork + previousSessionFile
  - session_before_switch reason new|resume + targetSessionFile
  - session_before_fork entryId/position
  - session_shutdown reason quit|reload|new|resume|fork + targetSessionFile
These are candidates for later PI-T002/T003 proof, not accepted architecture yet.
- pi-goal-x is globally installed and documents /goal, but it was not present in the observed Pi user package declarations for this worktree. Therefore actual /goal availability in a live Pi session is NOT asserted.
- No AI prompt or paid provider request was sent.

## Changed tracked files
No tracked production or test files are dirty after the accepted T1 commit/rebase. Current git status:
## feat/lantern-bot...origin/feat/lantern-bot [ahead 3]
The ignored .plan evidence/report files are the only new characterization artifacts.

## Remaining risks / required independent checks
REVIEW must explicitly assess:
- YAGNI/over-engineering: evidence-only approach stayed out of premature native Pi implementation; no duplicate terminal mechanism added.
- Scope drift: no Markdown fidelity/diff/Crop/Milkdown edits, no LAN/security/policy, no production Pi/Terminal/WS/UI source changes.
- UI/UX: verify screenshot geometry and focus conclusions; confirm the recorded overlap and keyboard-hint mismatch are accurate legacy observations, not implementation requests.
- Maintainability/module ownership: evidence points toward reusing TerminalManager/WS/xterm and native Pi hooks, with no parallel transcript/history/model catalog.
- Scalability/extensibility: no session registry or replay representation has been chosen before proof.
- Native Pi parity / mature upstream: G6 docs/types are provisional; FJP remains NOT_MEASURED.
- Session/concurrency isolation: not yet tested; PI-T002/T003 remain next proof slice only after review/test acceptance.
- Regression/performance: only the post-rebase terminal UI/SCM narrow checks ran in this turn; no full suite, resource measurement, or native Pi runtime performance was run.
- Acceptance proof: PI-T000 is partially measured on G6; PI-T001 FJP acceptance is NOT_MEASURED. Missing evidence must remain INCOMPLETE/NOT_MEASURED.

## Routing
Route to independent REVIEW. Do not begin PI-T002/T003 until REVIEW then TEST accept the measurable T000/T001 evidence and PLAN returns the next slice.

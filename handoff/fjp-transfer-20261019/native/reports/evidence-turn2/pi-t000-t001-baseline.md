# PI-T000 / PI-T001 characterization — DEV turn 2

Task: cdpa-idem-83600abd5f02df21942f316e
Date: 2026-10-18
Workspace: E:\git-project\lantern\.wt\lantern-bot

## PI-T000 — UX baseline (G6 disposable Edge, not FJP acceptance)

Environment:
- Host: G6 / DESKTOP-B5E4IUE.
- Edge: 155.0.4283.45.
- Disposable Lantern process: localhost 127.0.0.1:18089 with a TEMP-root sample.md fixture. The user's :9999 Lantern was not restarted or attached.
- Exact viewport was forced through Edge DevTools emulation before capture.
- Existing chatbot.js/css from the rebased branch were used unchanged. The launcher was clicked through DevTools; no product source was edited.
- Screenshots:
  - pi-t000-g6-edge-390x844.png
  - pi-t000-g6-edge-1280x900.png
  - pi-t000-g6-edge-1920x1080.png

Measured geometry with chat open:
- 390x844: drawer x=0, y=236.33, w=390, h=607.67; source textarea remains x=0, y=59, w=390, h=784. The drawer overlays the lower ~72% of the editor. Focus moves to lanternChatInput.
- 1280x900: drawer x=840, y=0, w=440, h=900; source textarea remains full 1280 px wide. The 440 px drawer overlays the editor's right side rather than reserving editor width. Focus moves to lanternChatInput.
- 1920x1080: drawer x=1480, y=0, w=440, h=1080; source textarea remains full 1920 px wide. The drawer overlays the editor's right side. Focus moves to lanternChatInput.

Source/runtime observations:
- static/chatbot.css fixes desktop width to min(440px,92vw); <=700px becomes a bottom sheet at min(72dvh,680px).
- .content receives right padding while chat is open, but this source editor page uses .editor/.editarea, so the editor itself is not narrowed; runtime rectangles above confirm overlap.
- Existing open behavior deliberately focuses the chat input after 80 ms, displacing editor focus/caret.
- Existing HTML bot owns its own provider/model selects, transcript/tool rows, sessionStorage snapshot replay, and compose area. This is exactly the duplicate UI/state model Spec 004 intends to replace after native parity proof.
- No expand/fullscreen native-Pi workspace control exists in this legacy shell.
- The compose hint says Ctrl/Cmd + Enter to send, while the input handler sends on unmodified Enter and returns for Ctrl/Meta/Alt/Shift+Enter. This is an existing legacy UX inconsistency; no fix is authorized in T000.
- At 390 px, source remains visible only in the top portion while the bottom-sheet chat covers most of the edit area; at desktop sizes the rightmost editor content/caret can be physically hidden beneath the drawer.
- These images are characterization of the legacy HTML bot, not proof of native Pi UX.

FJP browser/physical keyboard baseline remains NOT_MEASURED. Shell execution was restored and exact FJP CLI/package/source characterization was completed later in turn 4; see `../evidence-turn4/pi-t001-fjp-pi-t002-poc.md`. No FJP Edge screenshot, physical IME, focus, or end-user timing is claimed.

## PI-T001 — native Pi CLI/config baseline

FJP CLI/package/source baseline is superseded by the direct turn-4 measurement in `../evidence-turn4/pi-t001-fjp-pi-t002-poc.md`; do not use the earlier broker-failure classification.

G6 provisional comparison only:
- pi --version: 1.3.0.
- Package: @earendil-works/pi-coding-agent 1.3.0.
- Interactive TUI CLI supports --session, --session-id, --session-dir, --continue, --resume, --fork, --tui-mode fullscreen|regular (fullscreen default), --provider, --model, --models, tools, extensions, skills, themes, --offline, and project trust flags.
- pi list reports configured user packages: npm:@tintinweb/pi-subagents, npm:pi-mcp-adapter, npm:@juicesharp/rpiv-todo, a pi-web relay package, npm:pi-web-ui, and git:github.com/skorotkiewicz/zero-mem.
- User settings keys observed without reading secrets: lastChangelogVersion, theme, defaultProvider, defaultModel, defaultThinkingLevel, modelThinkingLevels, showHardwareCursor, defaultProjectTrust, packages, hideThinkingBlock, extensions, deviceId. Built-in MCP is explicitly disabled with extensions="-builtin:mcp". One user skill directory named image-creation is present. No project .pi/settings.json exists in this worktree.
- Local G6 1.3.0 docs confirm interactive-only built-ins including /settings and /model; /new starts a session, /resume opens the saved-session picker, and /fork branches from an earlier user message. Direct FJP 1.3.0 source inspection in turn 4 likewise shows no built-in /help entry. RPC documentation explicitly says built-in TUI commands such as /settings are not included/handled by RPC.
- Local extension docs expose native TUI APIs such as ctx.ui.select()/confirm()/input()/editor() and ctx.ui.setWidget(), reinforcing that native interactive mode is required for extension UI parity.
- Versioned extension type definitions expose session_start with reason startup|reload|new|resume|fork and previousSessionFile; session_before_switch, session_before_fork; and session_shutdown with reason quit|reload|new|resume|fork and targetSessionFile. This is a concrete native hook candidate for observing session transitions; it still requires PTY/runtime proof before architecture relies on it.
- A globally installed pi-goal-x package documents /goal and related custom interactive commands on G6, but it is not declared in the observed G6 Pi user package list for this worktree. Therefore /goal availability in an actual Pi session is NOT asserted from installation alone.
- No AI prompt was sent and no paid provider call was made for this characterization.

## Disposition

PI-T000: PARTIALLY MEASURED on G6 with 390/1280/1920 screenshots and runtime geometry; FJP/browser/physical UX remains NOT_MEASURED.
PI-T001: G6 1.3.0 CLI/docs/config characterization remains provisional reference; FJP exact CLI/package/config/source facts were later PARTIALLY MEASURED in turn 4, while interactive/physical acceptance remains INCOMPLETE.
No production source change is justified by these findings in this slice.

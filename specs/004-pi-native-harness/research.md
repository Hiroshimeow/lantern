# Research — Native Pi TUI Harness (read-only)
## FJP source observation
- `pi --help` on FJP confirms interactive default, `--session`, `--session-id`, `--session-dir`, `--tui-mode regular`, `--models`, `--tools`, `--no-extensions`, `--no-mcp`. Extension-specific CLI flags also present; Lantern should defer model/commands to Pi.
- Existing `lantern/terminal.py`: WinConPty uses pywinpty; `lantern/ws.py` carries TerminalManager PTY data with subscriptions and replay; `static/terminal_scm.js` uses xterm.js, fit addon and reconnect handling. These are mature local components to reuse, not replace.
- Existing `lantern/pi_chat.py` uses a singleton RPC session and global state. `static/chatbot.js` builds custom transcript; A/B tabs share stream/model/newchat/stop state. This is not session-per-user/task isolation.
- Pi extensions support custom interactive TUI; RPC mode degrades some extension UI methods. Official/current version-specific Pi docs should be checked again before implementation: https://app.unpkg.com/%40mariozechner/pi-coding-agent%400.68.0/files/docs/extensions.md and rpc.md.
- Native session files are Pi-owned; parsing JSONL for a second 'chat' is not justified in first release.
- FJP has project/global Pi extensions and commands; the parity gate must include at least one custom UI extension and /goal; not just /help.

## Distinctions
- sessionId is opaque durable identity, not equal to tab or file path. contextRef is metadata. Two independent conversations for same file must be possible; two tabs can deliberately attach one Pi session.
- Reload/F5: existing process should continue and output replay; host restart may terminate process, but Pi history can be reopened from Pi-native saved session. In-flight survival across restart needs separate supervisor design and user approval.
- Replay of arbitrary tail bytes can start mid-ANSI escape and corrupt screen; tests must prove screen/cursor/modes parity before choosing snapshot/serialize mechanism. Do not implement hand-written ANSI parser without upstream evidence.
- xterm data/input must remain native, preserving IME/AltGr/bracketed paste/image paste, default shortcuts and Pi theme.
- LAN tool/model/token quotas via prompt or CLI --models do NOT enforce billing/tool boundary. User explicitly defers security implementation; reserve spawn configuration decisions only. Any LAN Pi exposure beyond current behavior requires separate spec/approval.

## Debate
Sonnet 5.5 FJP M365 conversation: https://m365.cloud.microsoft/chat/conversation/181fd168-316e-4e07-bd5d-e99097960384. Round 1 rejected RPC HTML parity; Round 2 agreed baseline pure native Pi TUI, optional future context extension only; Round 3 refines opaque session ID and no premature headless mirror. Claims are research, not runtime test results.

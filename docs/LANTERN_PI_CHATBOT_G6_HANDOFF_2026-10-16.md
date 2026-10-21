# Lantern Native Pi Chatbot — G6 implementation handoff

Date: 2026-10-16 JST
Authoritative implementation host for this increment: G6
Repo: `E:\git-project\lantern`

## Current Git state

Implemented chatbot code baseline, verified and pushed:

```text
chatbot code baseline = 426b8edc3a72702e51b561dd7cd96e29ec55745c
review range = 4deb159..426b8ed

426b8ed fix(chat): flush Markdown drafts before Pi prompts
da62dd0 fix(chat): resume Pi sessions by session file
439806c feat(chat): add shared Lantern chatbot drawer
7e6d6ed feat(chat): expose Pi session over Lantern websocket
d7e6327 feat(chat): add persistent native Pi RPC manager
4deb159 fix(markdown): stabilize wide-table actions across rerenders
```

G6 live Lantern `9999` is HTTP 200. The currently loaded Python backend corresponds to the same backend code as `da62dd0`; `426b8ed` only changes the static chatbot JS/tests and is served directly from disk.

## Product goal

Add a native Pi chatbot to Lantern without degrading existing file manager,
Markdown Preview / Visual / Source, table controls, crop, or Terminal.

Required behavior:

1. Keep one Pi conversation until the user presses **New chat**.
2. Offer a compact set of 4–5 usable Pi models.
3. Capture the user's current Lantern location on every prompt.
4. For Markdown, include current mode, mapped line, and selected text.
5. Pi may directly read/edit files using its native tools.
6. Chatbot lock state is exactly the Terminal access state for MVP.
7. Eventually display AI edits as VS Code-like transient diffs:
   - added/new content: green;
   - modified: yellow/green;
   - removed old text: faded red + strikethrough.
8. Do not add a separate write-approval/security system in this MVP.

## Implemented architecture

```text
Browser
  │
  ├── existing /ws?v=2
  │       ├── Terminal messages
  │       └── Chat messages
  │
  ▼
Lantern Python server
  │
  ├── existing TerminalAccess / terminal cookie gate
  ├── existing WebSocketHub
  └── PiChatManager
         │
         │ JSONL stdin/stdout
         ▼
     native Pi 1.2.0
     --mode rpc
```

### Important design nuance for Opus review

The current base **does not put Pi RPC inside `TerminalManager` / ConPTY**.

It reuses:
- the same Terminal lock/auth predicate;
- the same `/ws` transport;
- the same Lantern server lifecycle.

But `PiChatManager` owns a pipe-based RPC subprocess separately.

Reason:
- existing `TerminalManager` is a PTY/ConPTY abstraction for human terminal
  text/ANSI;
- Pi RPC is structured JSONL over stdin/stdout;
- forcing RPC through PTY would require parsing terminal echo/ANSI and would
  make tool events/diffs/model switching less reliable;
- generalizing TerminalManager before proving the chatbot would be a much larger
  refactor and could degrade the stable terminal.

Opus should explicitly review whether:
A. keep `PiChatManager` as a sibling to TerminalManager (recommended current
   direction), or
B. introduce a generic process-session parent abstraction shared by both later.

Do **not** convert working RPC to a raw TUI parser merely to make it look like a
normal terminal session.

## Native Pi facts verified on G6

```text
Pi version: 1.2.0
npm wrapper: C:\Users\admin\AppData\Roaming\npm\pi.cmd
actual runtime: node.exe + @earendil-works/pi-coding-agent/dist/bundle/cli.js
```

Production manager launches the Node CLI directly when that npm layout exists.
This avoids Windows `cmd.exe` quoting errors.

Base arguments:

```text
--mode rpc
--session-dir ~/.lantern/pi-sessions
--name LanternChat
--append-system-prompt <Lantern embedded prompt>
--no-extensions
--no-mcp
```

`--no-extensions --no-mcp` is deliberate for MVP:
an installed mcp-adapter emitted interactive `extension_ui_request` events in
RPC mode. Native Pi skills remain available.

### Model list currently exposed

The manager queries `get_available_models` and prefers these real available
models:

```text
cliproxy-2080/gpt-6.1-sol
cliproxy-2080/gpt-6-astra
cliproxy-2080/claude-opus-5-5-high
cliproxy-2080/claude-sonnet-5-5-high
cliproxy-2080/gemini-3.1-pro-low
```

Do not assume these are permanently available; inventory remains dynamic.

## Implemented files

### `lantern/pi_chat.py`

Owns:
- native Pi process;
- JSONL request/response correlation;
- Pi event broadcast;
- `get_state`;
- `get_messages`;
- model inventory and `set_model`;
- `new_session`;
- `abort`;
- context normalization;
- session persistence/recovery;
- process cleanup.

Windows npm wrapper is bypassed in favor of:
`node.exe <pi-cli.js>` when resolvable.

Session recovery:
- persist Pi's **actual `sessionFile`** from `get_state`;
- restart using `--session <jsonl>`;
- do not use `--session-id` for recovery.

Pi does not create a JSONL file for a completely empty session. Therefore an
empty, unused session can get a new ID after Lantern restart. Once the
conversation has at least one message, the JSONL exists and the conversation is
resumed with the exact same session ID/history. No conversation is lost.

### `lantern/ws.py`

Added:
- `chat_sync`
- `chat_prompt`
- `chat_abort`
- `chat_new`
- `chat_set_model`

Every `chat_*` action uses the exact same `peer.can_terminal()` gate as
`terminal_*`.

Chat broadcasts are hidden from locked peers.

### `lan_drive.py`

Creates one lazy `PiChatManager`, passes it into existing WebSocket upgrade,
and closes it during normal server shutdown.

The Pi process is **not started at normal page load**.

### `static/chatbot.js` / `static/chatbot.css`

Shared drawer used by:
- main file manager;
- Markdown preview/editor.

Capabilities:
- lazy connect when Chat is opened;
- streaming assistant text;
- compact tool activity;
- model selector;
- New chat;
- Stop/abort;
- reconnect/history;
- current-context chip;
- desktop right drawer;
- mobile bottom sheet.

### Context behavior

Main file manager priority:
1. file currently open in media viewer;
2. exactly one selected file/folder;
3. current folder.

Markdown:
- relative file path;
- Preview / Visual / Source;
- mapped line;
- selected text when available.

It reuses `LanternAnchorBridge`; there is no second Markdown location system.

Backend resolves relative path under the configured Lantern root and rejects
escape attempts.

### Dirty Markdown correctness

Before `chat_prompt`:
- if Source/Visual is dirty, chatbot calls the existing
  `__lanternMdVisual.save()`;
- it waits for disk save;
- if the draft remains dirty or enters conflict, the Pi prompt is not sent.

This prevents Pi from reading/editing a stale disk revision.

## Live acceptance evidence on G6

### Real Pi message

Through the actual browser drawer and real provider:

```text
model: cliproxy-2080/gpt-6.1-sol
user: Reply exactly LANTERN_CHAT_OK. Do not use tools.
assistant: LANTERN_CHAT_OK
UI final status: Ready
```

### Context

File manager:

```text
kind=file
path=__lantern_chat_probe_.../note.txt
folder=__lantern_chat_probe_...
```

Markdown selection:

```text
kind=markdown
path=__lantern_chat_probe_.../doc.md
markdownMode=preview
line=103
selectedText="Unique paragraph 50."
```

### Session

Verified:
- navigating file manager -> Markdown keeps the same Pi session ID;
- **New chat** changes Pi session ID;
- after a real message is written to the session JSONL, restarting Lantern
  resumes the exact same session ID and message history.

Verified resumed session:

```text
sessionId = 01a14248-58af-73fa-ab21-4523a903e2cc
sessionName = LanternChat
messageCount = 3
```

### Dirty Markdown

Live Source acceptance:

```text
before: dirty=true
after flush: dirty=false
disk contains NEW_UNSAVED_MARKER
```

No model call was required for this flush test.

## Test evidence

Focused regression before final fixes:

```text
84 tests: PASS
```

Pi/chat unit + WebSocket tests after session fix:

```text
14 tests: PASS
```

Chat/UI/Pi tests after draft flush:

```text
18 tests: PASS
```

Plugin/Markdown/chat static regression after draft flush:

```text
32 tests: PASS
```

Full suite on G6:

```text
230 tests discovered
79 skipped
1 ERROR: tests.test_security temporary-directory cleanup WinError 32
```

That single error is **not introduced by chatbot**. The same isolated
`test_security` fails identically on a detached `4deb159` baseline worktree
on this G6 Windows environment. It is a pre-existing/environment-specific
directory-handle cleanup issue.

## Intentionally not implemented yet

### 1. AI diff decoration inside Markdown

Still pending:
- consume Pi `edit` result `details.diff / details.patch / firstChangedLine`;
- snapshot old content for `write`;
- normalize hunks;
- render:
  - Preview line highlights;
  - Visual external overlay (never insert into ProseMirror);
  - Source gutter/overlay;
  - removed old text ghost red + strikethrough.

This is the next major increment and should get real Opus review before
implementation because it touches three editor surfaces.

### 2. Raw Pi terminal view

Current chatbot uses structured RPC only.

There is no "open this exact Pi RPC process as a normal human terminal" because
RPC output is JSON and not Pi TUI.

If product wants a manual Pi terminal too, recommended options to debate:
- keep RPC chatbot + separate ordinary `pi` terminal session;
- or later introduce a generic process-session abstraction shared by PTY and RPC.

Do not mix TUI input and RPC protocol on one process.

### 3. Generic shell-mutation diff detection

For v1 the Pi system prompt tells the agent to prefer native `edit`/`write`
for file mutation. Generic detection of files mutated by arbitrary shell
commands is not implemented.

## Opus review task when FJP is online

On FJP:

1. Pull current `origin/main`.
2. Verify HEAD and clean status. Do not reset concurrent WIP.
3. Inspect native FJP Pi:
   ```powershell
   Get-Command pi | Format-List *
   where.exe pi
   pi --version
   pi --help
   pi --list-models
   ```
4. Read this document and inspect every chatbot commit.
5. Independently challenge:
   - sibling `PiChatManager` vs generalized TerminalSession;
   - RPC process recovery;
   - lock coupling;
   - browser reconnect;
   - Markdown dirty-save ordering;
   - model filtering.
6. Run focused tests and full regression on FJP.
7. Produce a patch proposal for the **AI diff overlay increment**.
8. Prefer KISS. Do not rewrite working Terminal/Markdown architecture merely to
   unify abstractions.
9. Stop before a large refactor if evidence does not justify it.

## Suggested next checkpoint after review

```text
feat(chat): surface structured Pi edit diffs
feat(markdown): overlay Pi edits without mutating editor content
```

Acceptance must prove that diff decorations never serialize into Markdown and
do not break Preview <-> Visual <-> Source location mapping.

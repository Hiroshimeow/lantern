# PLAN turn 10 — accept PI-T005; route minimal PI-T004 native Pi session registry

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 10
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn7_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** PI-T005 has clean independent REVIEW and TEST acceptance. Preserve/commit that accepted three-file slice, then implement **PI-T004 only**: a small server-internal PiSessionRegistry that creates and owns independent native Pi PTYs through the accepted TerminalManager structured-spawn seam. Do not start PI-T006 WS writer/viewer ownership, PI-T007 restart recovery, or browser/UI integration in this turn.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- branch: `feat/lantern-bot`;
- HEAD: `4a03fa9d15803d0adfdd2a28124012d6439e9cb7`;
- local `main`: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`;
- `main...HEAD = 0 4`;
- merge base is current main;
- current PI-T005 candidate changes exactly:
  - `lantern/terminal.py`;
  - `tests/test_terminal_scm.py`;
  - `tests/test_pi_tui_e2e.py`;
- no other tracked path is dirty;
- `lantern/pi_sessions.py` does not exist;
- `tests/test_pi_sessions.py` does not exist.

No current main drift exists. No rebase is needed before committing PI-T005 unless main advances again.

The legacy `LanternBotManager` RPC implementation still exists and is still wired by `application.py`. That is expected until the native replacement is complete. PI-T004 must not modify or partially rewire that legacy bot in this slice.

## PI-T005: ACCEPTED / COMPLETE

Independent REVIEW turn 14 and TEST turn 7 both accepted the structured native spawn seam.

Accepted behavior:

- `TerminalManager.create_argv()` / structured `argv` path launches native processes without shell re-parsing.
- Exact argv containing spaces, Unicode, quotes and shell metacharacters remains element-for-element unchanged.
- No PowerShell `-Command`, cmd `/C`, or POSIX `-lc` wrapper is inserted for structured spawn.
- Ordinary interactive shell `create()` behavior remains unchanged.
- Existing `run_command()` shell-string behavior remains unchanged.
- command + argv, empty/malformed argv, env-without-argv, and non-string env entries are rejected.
- CWD still uses the configured-root containment check.
- shared native PTY environment construction:
  - copies parent environment;
  - preserves inherited values;
  - applies TERM/LANG defaults;
  - applies explicit string overlay last;
  - does not mutate `os.environ`;
  - is shared by WinConPty and PosixPty.
- argv/env are not exposed in terminal metadata, WS, browser messages, or logs.
- browser clients gained no arbitrary argv/env spawn surface.
- existing injected ordinary-terminal factory compatibility remains intact.
- real G6 Pi 1.3.0 launches through the production TerminalManager structured seam with no test-only Pi factory and no paid AI prompt.

Independent TEST evidence:

- native Pi production seam: **1/1 PASS**;
- terminal SCM focused: **22 PASS**;
- terminal UI + LAN focused: **32 PASS**;
- PI-T003 replay continuity regression: **7 PASS**;
- Python compile / `git diff --check`: PASS.

Real POSIX child execution remains NOT_MEASURED on this Windows turn; common backend construction/dispatch is covered. This does not block PI-T004.

Classification: **PI-T005 COMPLETE**.

## Preserved earlier gates

### Spec 001

- T1: **COMPLETE / accepted / committed**.
- T0-C physical >=50-attempt four-channel UniKey evidence: **NOT_MEASURED / deferred**.
- T2 product fix: **BLOCKED**.
- No terminal/IME product fix is authorized.

### Spec 004 Phase 0

- PI-T000 G6 characterization accepted; FJP browser/physical UX remains incomplete.
- PI-T001 baseline materially characterized; live release parity remains incomplete.
- PI-T002 narrow native Pi/TerminalManager/WinConPty proof accepted.
- PI-T003 bounded same-geometry exact-client replay feasibility/continuity gate accepted.
- actual browser F5/live reconnect and release-level physical/resource evidence remain later acceptance items.

## Dependency decision

The next task is **PI-T004 Durable PiSessionRegistry**.

Do not combine PI-T004 with PI-T006. The registry must first prove independent session/process/context ownership in ordinary Python/module tests before WebSocket clients are allowed to attach, claim writer role, resize, or take over.

This turn is one substantive task.

## DEV housekeeping — commit accepted PI-T005 first

Before creating registry files:

1. Reconfirm the current three-file PI-T005 diff is unchanged from TEST turn 7.
2. Run `git diff --check`.
3. Selectively stage only:
   - `lantern/terminal.py`;
   - `tests/test_terminal_scm.py`;
   - `tests/test_pi_tui_e2e.py`.
4. Commit with a narrow structured-native-spawn message.
5. Confirm tracked worktree clean.
6. Re-check current local main.
7. If main has advanced:
   - inspect merge-base/main-only paths first;
   - rebase only when they remain outside Terminal/Pi ownership;
   - abort and route PLAN on any conflict;
   - never stash/reset/clean or guess through Markdown-owner conflicts.

No repeat full acceptance cycle is needed merely to commit unchanged PI-T005. A focused smoke after any rebase is sufficient.

## PI-T004 objective

Create `lantern/pi_sessions.py` and `tests/test_pi_sessions.py` implementing the smallest server-internal registry that owns native Pi process/session identity above TerminalManager.

The registry must establish these facts before WS/UI work:

1. every Lantern Pi session has an opaque generated `sessionId`;
2. `sessionId` is independent of file path, tab ID, document kind, title, or cwd;
3. one registry session maps to one TerminalManager terminal/PTy generation;
4. each session has its own Pi-native session directory/identity;
5. two sessions for the same document are independent;
6. two sessions for different documents are independent;
7. session context metadata is fixed at creation and is not silently retargeted by later file/tab navigation;
8. registry process launch uses **only** TerminalManager's accepted structured-spawn seam;
9. no browser/WS attach or writer policy is introduced yet.

## Allowed paths

Primary allowed implementation:
- new `lantern/pi_sessions.py`;
- new `tests/test_pi_sessions.py`.

Narrow edits to `lantern/terminal.py` are **not expected** after PI-T005 and require a concrete registry-blocking defect. If one appears, stop and route REVIEW/PLAN rather than casually expanding the spawn seam.

Do not edit:
- `lantern/application.py`;
- `lantern/ws.py`;
- `static/chatbot.js`;
- `static/chatbot.css`;
- `static/terminal_scm.js`;
- `lantern/pi_chat.py`;
- Markdown implementation files.

No application wiring is required in PI-T004. Keeping the new registry server-internal and independently testable avoids temporarily running or exposing two competing bot transports.

## Registry construction contract

Use dependency injection rather than rediscovering or hardcoding the installed Pi implementation inside the registry.

Recommended small constructor shape:

`PiSessionRegistry(root, state_dir, terminal, pi_argv, *, env=None, id_factory=None)`

Equivalent lean shapes are acceptable.

Requirements:

- `root`: configured Lantern project root used for context/cwd validation.
- `state_dir`: server-owned writable state root for Pi-native per-session directories; tests use temp dirs.
- `terminal`: the existing `TerminalManager` owner.
- `pi_argv`: server-owned base argv sequence for the installed native Pi entry point.
  - Do not infer it from browser input.
  - Do not hardcode a model/provider/command catalog.
  - Do not depend on legacy `LanternBotManager`.
- optional env is a server-owned structured overlay passed through TerminalManager.
- optional `id_factory` exists only if needed for deterministic tests; production default must be cryptographically/UUID opaque enough to avoid path/tab derivation.

The registry should not install packages or mutate global Pi config.

## Session creation contract

A create call should accept the smallest useful server-owned creation fields:

- cwd;
- contextRef metadata;
- initial cols/rows;
- optional human title.

Do **not** accept arbitrary Pi argv from a browser/user-facing transport in this slice.

For each create:

1. Generate an opaque unique `sessionId`.
2. Derive an internal terminal ID from the opaque ID only, e.g. `pi:<sessionId>`.
   - do not derive terminal ID from path/tab/document title.
3. Create a unique server-owned native session directory for that session.
4. Build native Pi argv by appending only version-proven native session flags to the injected base argv:
   - `--session-id <sessionId>`;
   - `--session-dir <sessionDir>`;
   - `--tui-mode regular`.
5. Do **not** add provider/model/tools/extension restrictions by default.
6. Do **not** add `--offline` in production registry behavior merely because the e2e characterization used it.
7. Call `TerminalManager.create_argv()` with the exact structured list, cwd, env and geometry.
8. Store immutable creation metadata and the returned PTY generation.
9. Return a sanitized session view that does not expose env secrets or the full internal argv.

If the installed/versioned Pi contract changes later, the registry should only need its base argv/config dependency updated; it must not own a duplicate slash/model catalog.

## Pi-native session directory

PI-T004 must create a real distinct directory per Lantern session under the injected `state_dir`.

Requirements:

- directory identity is based on opaque session ID, not document path;
- two sessions for one file use different directories;
- directory path is stable for the life of that registry session;
- registry metadata may expose the server-side sessionDir to internal callers/tests if needed, but browser exposure is a later design choice;
- do not parse or rewrite Pi's own session-history format.

**Restart persistence is not accepted by PI-T004.** PI-T007 will define which metadata is persisted/reloaded and how an existing Pi history file is reopened. Do not invent a registry JSON database now.

## ContextRef contract

Treat `contextRef` as immutable session creation metadata only.

Minimum behavior:

- defensive-copy caller input so later mutation of the caller's dict does not retarget the session;
- return defensive copies/sanitized immutable views so consumers cannot mutate registry state accidentally;
- allow two sessions with identical contextRef;
- allow two sessions with different contextRefs;
- no implicit “active document” lookup after creation;
- no method in this turn that silently changes contextRef.

Do not inject context into the TUI with hidden keystrokes or XML prompts.

PI-T011 will later establish the native context channel used by Pi itself.

## Status / generation contract

The registry should expose enough server-internal metadata for PI-T006 to build on without implementing attach ownership now.

At minimum a session view should contain:
- `sessionId`;
- internal terminal ID or a server-internal equivalent;
- PTY `generation` from TerminalManager;
- cwd;
- contextRef;
- running/exited status;
- cols/rows;
- native session directory;
- a registry/session incarnation or attach-generation field only if it has clear semantics.

Avoid speculative counters.

If the task text's “attach generations” cannot be given meaningful semantics before PI-T006, prefer the existing TerminalManager PTY generation as the stale-session identity and document that browser attachment-generation/ownership starts in PI-T006. Do not create a counter nobody uses.

## Registry operations allowed now

Keep the API small:

- create;
- get;
- list;
- explicit stop;
- close/cleanup for registry-owned sessions.

Optional rename is unnecessary unless a test proves it is needed.

Not allowed yet:
- browser/client attach;
- detach;
- writer/viewer roles;
- takeover;
- resize ownership;
- acknowledged sequence per viewer;
- WS subscriptions;
- F5 behavior;
- restart reopen;
- supervisor.

`stop(sessionId)` is explicit user/server intent and may kill the underlying terminal.

`close()` may clean up registry-owned live sessions for tests/server shutdown semantics, but do not wire it into `Application.close()` yet.

## Required PI-T004 tests

### 1. Opaque identity

Create a session for a document/path with recognizable text.

Assert:
- generated session ID does not equal path/tab/title;
- terminal ID derives only from opaque session ID;
- native session directory derives from opaque session ID;
- no file/path slug is used as identity.

Use deterministic `id_factory` in unit tests where useful; production default must remain opaque.

### 2. Two sessions, same document

Create A and B with identical:
- cwd;
- contextRef.

Assert:
- A.sessionId != B.sessionId;
- terminal IDs differ;
- PTY generations differ;
- session directories differ;
- stopping/mutating process state for A does not stop or retarget B;
- contextRef values may be equal but are independent stored copies.

This is a core PI-T004 acceptance.

### 3. Two documents

Create A for document A and B for document B.

Assert:
- contextRef/cwd remain bound to their creation values;
- querying/listing B never mutates A;
- there is no global “current document” field that retargets both.

If both documents use the same cwd, independence must still hold.

### 4. Exact native argv

With a fake/spy TerminalManager or injected spawn boundary, assert registry passes:
- injected base argv unchanged first;
- native `--session-id`;
- correct unique `--session-dir`;
- `--tui-mode regular`;
- no shell command string;
- no XML prompt;
- no provider/model restriction unless already present in injected server-owned base argv.

### 5. Context immutability

After create:
- mutate the original input dict/nested selection object;
- returned session state stays unchanged.
- mutate a returned context copy;
- later `get()` remains unchanged.

Use deep copying, not a shallow top-level copy.

### 6. CWD validation

Registry delegates actual cwd containment to TerminalManager and surfaces a clear failure without leaving a half-created registry entry/session directory that appears active.

A failed create must not remain in `list()`.

Reasonable empty session directory cleanup on failed spawn is preferred; if retained for diagnostic reasons, it must not be reported as a valid session.

### 7. Stop isolation

Stop A explicitly:
- underlying A terminal is killed/stopped;
- B remains running;
- registry view for B unchanged.

Define whether stopped A remains listable as exited history or is removed; choose one simple consistent behavior and test it. Do not conflate stop with browser detach.

### 8. Terminal exit observation

If the underlying TerminalManager reports/contains an exited terminal, registry `get/list` must not continue claiming `running=true`.

Use existing TerminalManager metadata; do not create a second process-status source.

### 9. Cleanup

`close()` affects only registry-owned terminal IDs, not unrelated ordinary Terminal sessions.

This ownership isolation is required.

### 10. No duplicate state protocol

Tests/source inspection should show registry stores metadata only; PTY output/replay remains entirely in TerminalManager. No output transcript, ANSI buffer, model list, slash list, or HTML history belongs in PiSessionRegistry.

## Native Pi runnable evidence

PI-T004 does not need another paid/native Pi interaction suite merely to prove metadata identity.

If practical, add one small gated integration assertion using installed Pi and the accepted structured seam to show two registry sessions can be created with separate native session IDs/directories without sending AI prompts. This is useful but not required if it would make the slice machine-flaky.

Do not claim FJP/browser/physical parity from unit registry tests.

## Failure atomicity / cleanup

DEV must explicitly handle:

- generated ID collision: retry or fail before spawn; never overwrite an existing session;
- native session directory creation failure: no registry entry;
- TerminalManager spawn failure: no live registry entry;
- close/stop idempotence where reasonable;
- no killing terminals the registry did not create.

Do not add a general persistence database or supervisor to solve these cases.

## Security / LAN boundary

PI-T004 is internal server state only.

Do not:
- expose create/list/stop to WS;
- accept remote env/argv;
- add LAN policy;
- change auth;
- add quotas/token limits/sandboxing.

Those are either PI-T006 routing concerns or explicitly deferred requirements.

## Legacy bot coexistence

Do not modify `LanternBotManager`, legacy chat tests or chatbot JS in this slice.

The old RPC bot and new native registry may coexist in source temporarily, but PI-T004 is not wired into application/browser runtime yet. This avoids duplicate live bot ownership during an intermediate commit.

PI-T012 removes legacy runtime only after native replacement parity passes.

## Required REVIEW after DEV

Independent REVIEW must assess:

- identity is opaque and independent of path/tab;
- same-document and different-document session isolation;
- no mutable global context retargeting;
- exact native session argv/session-dir construction;
- use of TerminalManager structured spawn only;
- no duplicate PTY/output/replay/history ownership;
- status follows TerminalManager instead of a second truth source;
- stop/close ownership isolation;
- cleanup/failure atomicity;
- YAGNI / no premature attach/writer/persistence framework;
- module boundaries and maintainability;
- scalability implications of one PTY per session and state-dir growth without inventing cleanup policy;
- no WS/browser/security/Markdown scope drift;
- acceptance tests are meaningful rather than mocks that merely restate implementation.

If clean, route independent TEST. Only after TEST acceptance should PLAN authorize PI-T006 scoped WS one-writer/viewer ownership.

## Classification after PLAN turn 10

- Spec 001 T1: **COMPLETE**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: accepted characterization; FJP browser/physical incomplete.
- PI-T001: materially characterized; release parity incomplete.
- PI-T002: **COMPLETE narrow native PTY proof**.
- PI-T003: **COMPLETE Phase-0 bounded same-geometry replay continuity gate**.
- PI-T005: **COMPLETE / independently accepted**.
- PI-T004: **ACTIONABLE NOW**.
- PI-T006: **NEXT after PI-T004 acceptance**.
- PI-T007: **DEPENDENT after scoped ownership**.
- PI-T008-T013: **DEPENDENT / not authorized yet**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 10. This required PLAN report is the only artifact written by PLAN.

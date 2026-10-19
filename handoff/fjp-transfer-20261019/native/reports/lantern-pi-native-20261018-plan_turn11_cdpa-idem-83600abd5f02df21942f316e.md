# PLAN turn 11 — accept PI-T004; route PI-T006 scoped Pi WS attach and one-writer ownership

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 11
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn9_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** PI-T004 has clean independent REVIEW and TEST acceptance after the T8-1 correction. Preserve/commit that accepted four-file registry slice, then implement **PI-T006 only**: sessionId-scoped WebSocket attach/output plus exactly one input+resize writer with explicit takeover. Do not start PI-T007 restart lifecycle or browser bot UI replacement.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- branch: `feat/lantern-bot`;
- HEAD: `1282490f8bd1443b547c3b64b0b26813270ff837`;
- local `main`: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`;
- `main...HEAD = 0 5`;
- merge base is current main;
- current accepted PI-T004 candidate paths are exactly:
  - `M lantern/terminal.py`;
  - `M tests/test_terminal_scm.py`;
  - `?? lantern/pi_sessions.py`;
  - `?? tests/test_pi_sessions.py`;
- no application, WS, browser, Markdown, dependency/vendor, LAN/security or unrelated path is dirty.

No current main drift exists.

## PI-T004: ACCEPTED / COMPLETE

Independent REVIEW turn 18 and TEST turn 9 accepted the server-internal registry boundary.

Accepted facts include:

- opaque session identity independent of path/tab/title;
- one registry session maps to one TerminalManager terminal generation;
- unique native Pi session directory per registry session;
- exact server-owned native argv using `--session-id`, `--session-dir`, `--tui-mode regular`;
- TerminalManager remains the only PTY/output/process-status owner;
- same-document sessions are independent;
- different-document sessions are independent;
- contextRef is deep-copied at creation and cannot be silently retargeted;
- returned context views do not mutate stored state;
- unsupported/deepcopy-failing context input fails **before** identity allocation, directory creation or spawn;
- spawn/post-publication failure rolls back the exact created generation;
- stop/close use generation-safe terminal kill and do not kill a replacement generation;
- close/stop do not affect unrelated ordinary Terminal sessions;
- no output transcript, ANSI state, model/slash catalog, persistence DB, browser attach state or restart supervisor exists in the registry.

Independent TEST turn 9 freshly verified:

- PI-T004 registry suite: **9/9 PASS**;
- targeted failure/ownership cases: **4/4 PASS**;
- Terminal focused suite: **23 PASS**;
- native Pi structured-spawn regression: **1 PASS**;
- PI-T003 replay regression: **7 PASS**;
- full ordinary repository suite: **374 tests OK, 134 skipped**;
- syntax and `git diff --check`: PASS.

Classification: **PI-T004 COMPLETE**.

## Preserved earlier classifications

### Spec 001

- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- No IME product fix.

### Spec 004

- PI-T002 COMPLETE narrow native PTY proof.
- PI-T003 COMPLETE Phase-0 bounded same-geometry replay-continuity gate.
- PI-T005 COMPLETE structured native spawn seam.
- PI-T004 COMPLETE server-internal session registry.
- Browser F5/live reconnect, FJP physical input, release resource/performance, model/goal/custom-extension parity remain later INCOMPLETE/NOT_MEASURED items.

## Dependency decision

Next: **PI-T006 Scoped WS and one writer**.

PI-T006 must be accepted before PI-T007 lifecycle because reconnect/detach semantics need a stable attach/writer contract first.

This DEV turn is PI-T006 only.

## DEV housekeeping — commit accepted PI-T004 first

Before WS edits:

1. Reconfirm the four current PI-T004 paths match TEST turn 9.
2. Run `git diff --check`.
3. Selectively stage only those four files; never `git add -A`.
4. Commit with a narrow Pi session-registry message.
5. Confirm clean tracked worktree.
6. Re-check current local main.
7. If main has advanced, inspect merge-base paths before rebase.
8. Rebase only if new main work remains outside Terminal/Pi ownership; abort on conflict.
9. Never reset/stash/clean/merge or resolve Markdown-owner conflicts by guesswork.

No need to repeat the entire PI-T004 acceptance just to commit unchanged accepted work.

## Current WS truth that PI-T006 must preserve

Existing terminal v2 already provides useful generic mechanisms:

- each peer has a terminal subscription set;
- terminal output is broadcast only to subscribed v2 peers;
- two peers may independently subscribe to the same ordinary terminal;
- switching one peer's subscription does not retarget another peer;
- terminal replay captures metadata/output/seq/UTF-8 continuity under the TerminalManager lock;
- ordinary terminal input/key/resize currently have **no per-peer writer ownership**: any authenticated peer knowing a terminal ID may send them;
- legacy terminal behavior must remain unchanged.

PI-T006 must not redesign ordinary Terminal ownership. Apply writer/viewer policy only to **Pi session WebSocket operations**.

## Architecture decision for PI-T006

Keep durable process/session identity in `PiSessionRegistry`.

Keep transient browser connection ownership in `WebSocketHub`.

Do **not** persist peer/client writer state in PiSessionRegistry.

Rationale:

- peer lifetime belongs to WebSocketHub;
- disconnect cleanup already belongs to WebSocketHub.remove();
- writer ownership is transient browser attachment state, not Pi native session history;
- PI-T007 can later preserve process/session across reload without needing to persist old WebSocket peers;
- registry remains YAGNI metadata/process ownership rather than becoming a client-state database.

## Allowed implementation paths

Primary:

- `lantern/ws.py`;
- `lantern/pi_sessions.py` only if a tiny read-only helper is required to resolve session -> terminal generation cleanly;
- new `tests/test_pi_ws_contract.py`.

Focused existing regression files may be updated only where needed:
- `tests/test_lan_multi_perf.py`;
- `tests/test_terminal_auth.py`;
- `tests/test_terminal_scm.py`.

Do **not** edit in this slice:
- `lantern/application.py`;
- `lantern/http/server.py`;
- `static/chatbot.js`;
- `static/chatbot.css`;
- `static/terminal_scm.js`;
- `lantern/pi_chat.py`;
- Markdown implementation.

Runtime application wiring is intentionally deferred. PI-T006 is a server transport contract proven through injected registry/manager objects first. PI-T008 can wire the native bot host after the session foundation is accepted.

## PI WebSocket operation surface

Use a small Pi-specific session protocol; do not expose the registry's internal terminal ID as the client identity.

Recommended operations:

- `pi_session_attach`
- `pi_session_detach`
- `pi_session_takeover`
- `pi_session_input`
- `pi_session_key`
- `pi_session_resize`

Equivalent concise names are acceptable if consistent.

Do not add create/new-session browser operations yet; PI-T010/UI will own that product flow.

No remote argv/env fields.

## Existing terminal auth must protect Pi operations

Current auth checks protect `terminal_*` and legacy `chat_*`.

New Pi session WS operations must reuse the **same existing terminal access decision**.

Do not create:
- a new auth mode;
- a LAN policy;
- a new password/token;
- a whitelist;
- a sandbox.

Unauthenticated peers must not learn Pi session metadata/output.

This is reuse of existing auth, not new security policy.

## Attach contract

`pi_session_attach` client request must contain:

- `sessionId`;
- expected PTY `generation`.

Generation is mandatory so stale tabs cannot attach to a replacement process by session ID alone.

Server behavior:

1. Resolve the session through `PiSessionRegistry.get(sessionId)`.
2. Reject if unknown/stopped/not running.
3. Reject if expected generation != registry/TerminalManager generation.
4. Atomically capture the underlying TerminalManager replay view and register the peer as attached before live output can race ahead.
5. Do not return/expose the internal terminal ID.
6. Return a `pi_session_replay` or equivalent payload containing:
   - sessionId;
   - generation;
   - output;
   - seq;
   - replayStartUtf8/replayEndUtf8;
   - truncated display flag;
   - current role: writer/viewer;
   - current transient ownership epoch/generation.
7. Reuse the accepted replay continuity math; do not add another replay implementation.

### First writer rule

For a session with no currently attached writer:

- the first attaching peer becomes writer/resize owner.

Additional peers:

- attach as viewers.

No automatic writer stealing.

A peer attaching twice is idempotent.

## One active Pi attachment per peer

For this slice, bound complexity the same way ordinary terminal v2 does:

- one active Pi session attachment per WebSocket peer.

Attaching a different Pi session:
- detaches that peer from the old Pi session;
- must not kill either Pi process;
- must not affect other peers.

This is sufficient for browser-tab-per-connection behavior and prevents idle output accumulation.

Do not build a many-session multiplexed peer protocol now.

## Transient ownership epoch

Each attached Pi session route should maintain a monotonically increasing **ownership epoch** (or equivalent transient writer generation).

This is distinct from TerminalManager PTY generation.

Purpose:

- stale queued writer messages from a previous owner must be rejectable after takeover or writer detach.

Required semantics:

- starts from a defined value when the WS route first exists;
- increments when writer ownership changes;
- input/key/resize request must carry:
  - sessionId;
  - PTY generation;
  - ownership epoch.
- request is accepted only when:
  - peer is attached to that session;
  - peer is current writer;
  - PTY generation matches;
  - ownership epoch matches current route.

Do not use timestamps.

## Explicit takeover

`pi_session_takeover`:

- requires the peer already be attached as a viewer;
- requires matching PTY generation;
- promotes requester to writer;
- prior writer becomes viewer;
- increments ownership epoch;
- does not send terminal input;
- does not resize automatically;
- does not restart Pi.

All attached peers should receive a small ownership-change notification sufficient to update their role/epoch.

Do not expose remote IP or auth token as an owner identifier.

Role is enough: each peer knows whether **it** is writer.

## Detach and disconnect

`pi_session_detach`:

- removes only that peer's attachment;
- never kills the Pi process;
- never removes registry session metadata;
- if viewer: no writer change;
- if writer: writer becomes none and ownership epoch increments;
- do not auto-promote an arbitrary viewer.

When `WebSocketHub.remove(peer)` runs on socket disconnect:

- perform the same Pi detach cleanup;
- do not kill Pi.

This is an important prerequisite for PI-T007/F5 but is not yet a claim that browser F5 restoration works end-to-end.

## Output scoping

When TerminalManager emits `terminal_output` for a terminal belonging to an attached Pi session:

- only peers attached to that **sessionId + PTY generation** receive the Pi output event;
- do not broadcast A raw data to B;
- client-facing Pi output should use sessionId/generation, not require internal terminalId;
- keep seq and data unchanged;
- do not parse ANSI/TUI content.

Recommended client event:
- `pi_session_output {sessionId, generation, seq, data}`.

On terminal exit:
- attached peers should receive a scoped Pi session exit/status event;
- no peer for another session receives it.

Ordinary terminal broadcast/subscription behavior remains unchanged.

## Avoid duplicate delivery

A Pi-attached peer should not receive the same Pi byte stream through both:
- generic `terminal_output`;
- Pi session output.

The PI attach mechanism should not require the peer to generic-subscribe to the internal terminal ID.

Do not expose Pi internal terminal IDs through the new protocol.

Generic Terminal list hiding of Pi sessions is **not** required in this transport-only slice because the registry is not application-wired yet. That runtime/UI integration concern belongs to PI-T008. However the new Pi protocol itself must never use terminalId as its public identity.

## Input/key contract

`pi_session_input` and `pi_session_key`:

- writer-only;
- attached-session-only;
- matching PTY generation;
- matching ownership epoch;
- use existing TerminalManager.input()/key() on the registry-owned terminal internally;
- viewers receive a deterministic permission/role error;
- stale writer epoch receives a deterministic stale-owner error;
- wrong generation receives a stale-session error;
- no input duplication;
- no hidden prompt wrapping or slash-command interception.

Do not inspect or transform native Pi bytes.

## Resize contract

`pi_session_resize` obeys the exact same ownership checks as input.

Only current writer may resize the canonical PTY.

Viewers never resize the PTY based on their own viewport.

This preserves the PI-T003 geometry invariant.

Takeover alone must not resize; the new writer's next explicit resize owns the canonical size.

## Session isolation requirements

Tests must prove:

- A output never reaches a peer attached only to B;
- B input cannot target A by substituting A sessionId unless that peer is attached and writer for A;
- wrong PTY generation is rejected;
- stale ownership epoch is rejected;
- viewer input/key/resize is rejected;
- explicit takeover transfers authority exactly once;
- old writer becomes viewer and cannot continue input/resize;
- process remains alive across peer detach/disconnect;
- two independent sessions can both have their own writers simultaneously.

## Required test file

Create `tests/test_pi_ws_contract.py`.

Use real:
- `PiSessionRegistry`;
- `TerminalManager`;
- `WebSocketHub`;
- `dispatch`.

Use fake PTYs for deterministic transport tests.

Do not mock the contract into tautology.

## Required PI-T006 tests

### 1. First attach writer, second attach viewer

Pre-create one registry session.

Attach peer A:
- replay returned;
- A role writer;
- epoch E.

Attach peer B:
- replay returned;
- B role viewer;
- same PTY generation;
- same current epoch.

### 2. Both viewers receive output

Emit PTY output after both attach.

Assert:
- A and B each receive exactly one scoped Pi output;
- same sessionId/generation/seq/data;
- no internal terminalId required;
- unrelated peer receives none.

### 3. Writer input/key only

A sends input and key with generation + E:
- exact bytes reach PTY once.

B sends same:
- rejected;
- zero new PTY input.

### 4. Writer resize only

A resize changes PTY once.

B resize:
- rejected;
- canonical terminal geometry unchanged.

### 5. Explicit takeover

B requests takeover:
- B writer;
- A viewer;
- epoch changes E -> E2;
- both peers notified.

A using old E:
- rejected.

A using E2:
- still rejected because viewer.

B using E2:
- accepted.

### 6. Stale PTY generation

Simulate/replace terminal generation while old attachment exists.

Any old attach/input/resize/takeover message using old PTY generation:
- rejected;
- replacement process untouched.

Do not kill replacement generation.

### 7. Detach does not kill

Detach current writer:
- writer becomes none;
- epoch advances;
- session/process remains running;
- remaining viewers continue receiving output.

A remaining viewer must use explicit takeover to become writer.

### 8. Socket removal does not kill

Call `hub.remove(peer)` for attached writer.

Assert:
- ownership released;
- process remains;
- other session/viewer state unaffected.

### 9. Session switch on one peer

Peer A attached to session 1 then attaches session 2.

Assert:
- A no longer receives session 1 output;
- peer B still attached to session 1 continues receiving;
- neither session is killed;
- A can become writer of session 2 if it has no writer.

### 10. A/B isolation

Create session A and session B.

Attach different peers/writers.

Assert output/input/resize/ownership events are completely isolated.

### 11. Replay continuity

Attach replay must preserve:
- seq;
- replayStartUtf8;
- replayEndUtf8;
- truncation;
- PTY generation.

Use existing accepted TerminalManager replay view rather than recomputing.

### 12. Auth reuse

Peer with `can_terminal() == False`:
- cannot attach;
- cannot receive Pi session metadata/output;
- cannot input/takeover/resize.

No new auth mechanism.

### 13. Ordinary Terminal regression

Existing:
- terminal_subscribe;
- terminal_input/key/resize;
- output scoping;
- legacy terminal path

remain behaviorally unchanged.

## Error contract

Extend terminal-style error response only as much as needed for deterministic client behavior.

Useful stable codes may include:
- `pi_session_not_found`;
- `pi_session_stale`;
- `pi_session_not_attached`;
- `pi_session_not_writer`;
- `pi_session_stale_owner`.

Do not build a large error taxonomy.

Error payload must not leak:
- internal terminal ID;
- env;
- argv;
- auth token;
- filesystem secrets beyond already-approved session metadata.

## Concurrency / lock order

REVIEW must scrutinize lock ordering.

Preferred rule:

- TerminalManager lock owns replay/process metadata;
- WebSocketHub lock owns peer attachment/writer state;
- PiSessionRegistry lock, if any, owns registry metadata.

Avoid nested lock cycles.

For attach replay race, preserve the existing safe pattern:
- atomically capture terminal replay and register routing before output emission can pass the boundary;
- if two locks are required, use one documented consistent ordering everywhere.

Do not hold hub lock during socket send.

## No browser implementation yet

Do not modify frontend to consume the new protocol this turn.

PI-T006 acceptance is server contract only.

This avoids simultaneously debugging protocol ownership and UI lifecycle.

PI-T008/PI-T010 will bind the native xterm pane to these events later.

## No PI-T007 yet

Do not implement:
- saved attachment selection;
- F5 auto-reattach;
- Lantern restart reopen;
- Pi history discovery;
- interrupted-turn recovery;
- supervisor/process persistence.

Detach merely not killing the current live process is PI-T006. Cross-Lantern-restart behavior is PI-T007.

## No session creation WS yet

Do not expose a browser create/new-session RPC in PI-T006.

Tests may pre-create registry sessions server-internally.

Session creation UI/protocol can be added with PI-T010 after native host wiring, unless a later PLAN explicitly moves the minimal create endpoint earlier.

This keeps current task focused on isolation/ownership.

## Required regressions

After PI-T006 implementation run at minimum:

- `tests.test_pi_ws_contract`;
- `tests.test_pi_sessions`;
- `test_terminal_scm.py`;
- `tests.test_lan_multi_perf`;
- `tests.test_terminal_auth`;
- enabled PI-T003 replay proof;
- enabled native Pi TUI proof where environment permits;
- Python syntax;
- `git diff --check`.

Full ordinary suite should run before REVIEW handoff because WS dispatch is shared infrastructure.

## Required REVIEW after DEV

Independent REVIEW must evaluate:

- sessionId/generation scoping correctness;
- one writer + one resize owner;
- explicit takeover and stale-epoch rejection;
- detach/disconnect never kills Pi;
- two-session isolation;
- output never leaks across sessions;
- no duplicate generic/Pi output;
- auth reuse without policy expansion;
- ordinary Terminal compatibility;
- replay continuity reuse rather than duplicate logic;
- lock ordering/races;
- slow/dead peer behavior;
- YAGNI and transient ownership placement in hub rather than registry persistence;
- maintainability/module separation;
- scalability of per-session peer sets;
- native Pi parity nonclaims;
- no PI-T007/UI/Markdown/LAN scope drift;
- acceptance test quality.

If clean, route independent TEST.

Only after TEST acceptance should PLAN authorize PI-T007 lifecycle/restart.

## Classification after PLAN turn 11

- Spec 001 T1: COMPLETE.
- Spec 001 T0-C: NOT_MEASURED / deferred.
- Spec 001 T2: BLOCKED.
- PI-T002: COMPLETE narrow native PTY proof.
- PI-T003: COMPLETE Phase-0 replay gate.
- PI-T005: COMPLETE structured spawn.
- PI-T004: **COMPLETE / independently accepted**.
- PI-T006: **ACTIONABLE NOW**.
- PI-T007: **NEXT after PI-T006 acceptance**.
- PI-T008-T013: DEPENDENT / not authorized yet.
- PI-T014/T015/T016: INCOMPLETE / NOT_MEASURED where applicable.
- overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 11. This required PLAN report is the only artifact written by PLAN.

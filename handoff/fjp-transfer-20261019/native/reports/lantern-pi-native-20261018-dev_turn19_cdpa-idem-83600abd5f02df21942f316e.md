# DEV turn 19 — preserve PI-T004; implement PI-T006 scoped Pi WS attach + one-writer ownership

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Contract followed

Read PLAN turn 11 and executed only its authorized slice:
1. preserve/commit independently accepted PI-T004 registry work;
2. implement PI-T006 server transport contract only.

Explicitly not started:
- PI-T007 restart/F5 lifecycle persistence;
- application/runtime wiring;
- browser bot UI/xterm integration;
- session creation RPC;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/auth policy changes;
- Lantern :9999 restart/action;
- CDPA changes.

## Housekeeping — PI-T004 accepted slice

Incoming accepted paths matched PLAN exactly:
- M lantern/terminal.py
- M tests/test_terminal_scm.py
- ?? lantern/pi_sessions.py
- ?? tests/test_pi_sessions.py

`git diff --check` was clean.

Selectively staged only those four files and committed:
- `71bc8de feat(pi): add native session registry`

Local main had not advanced, so no rebase was required.

Post-commit base:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6

## PI-T006 implementation

Current uncommitted candidate files:
- lantern/ws.py
- tests/test_pi_ws_contract.py

No PiSessionRegistry, TerminalManager, application, frontend, chatbot, Markdown, package/lock/vendor or security-policy source was changed for PI-T006.

### Transient ownership placement

WebSocketHub now owns only transient Pi browser-route state:
- one route per sessionId;
- sessionId -> internal terminalId/generation association;
- attached peer set;
- current writer peer or none;
- monotonically increasing ownership epoch;
- active/stale route marker.

PiSessionRegistry remains native process/session metadata only.

No output/history/transcript/ANSI/model/slash-command duplication was added.

### Pi-specific WS operations

`dispatch(..., pi=registry)` now accepts:
- pi_session_attach
- pi_session_detach
- pi_session_takeover
- pi_session_input
- pi_session_key
- pi_session_resize

Runtime application wiring is intentionally absent per PLAN turn 11; existing `upgrade()` call sites do not yet inject PiSessionRegistry.

No create/new-session RPC was added.

### Auth reuse

Pi operations reuse the same existing `peer.can_terminal()` decision as terminal/chat operations.

Unauthenticated peers fail before registry lookup/metadata access.

No new auth mode/token/password/whitelist/LAN policy exists.

`_terminal_error_reply()` now emits `pi_session_error` for Pi operations with stable compact codes when available:
- pi_session_not_found
- pi_session_stale
- pi_session_not_attached
- pi_session_not_writer
- pi_session_stale_owner

Auth rejection continues to use existing `terminal_auth_required` policy and does not expose internal terminalId for Pi requests.

### Attach/replay contract

Attach requires:
- public sessionId;
- expected PTY generation.

Server flow:
1. resolves registry session;
2. rejects unknown/stopped/stale generation;
3. acquires TerminalManager lock;
4. captures existing replay_view seq/output/UTF-8 interval;
5. registers Pi route/peer in WebSocketHub before terminal output can pass the replay boundary;
6. releases TerminalManager lock;
7. sends bounded replay outside locks.

`pi_session_replay` contains only:
- sessionId;
- generation;
- output;
- seq;
- replayStartUtf8;
- replayEndUtf8;
- truncated;
- role;
- ownershipEpoch.

No internal terminalId is exposed.

Ordinary terminal_subscribe now calls the same `_bounded_replay()` helper, so Pi replay cap math and accepted generic replay cap math are one implementation.

### One writer / resize owner

Rules implemented:
- first attach for a route becomes writer;
- later attaches are viewers;
- repeated attach by the same peer is idempotent and does not change epoch;
- one active Pi session attachment per peer;
- switching sessions detaches only that peer from the old route and never kills either process;
- no arbitrary viewer auto-promotion;
- writer detach/disconnect releases ownership and increments epoch;
- later writer assignment increments epoch;
- explicit viewer takeover increments epoch and demotes previous writer to viewer;
- takeover itself sends no input and performs no resize.

Writer-only input/key/resize require all of:
- peer attached to session;
- exact PTY generation;
- exact current ownership epoch;
- peer is current writer.

Stale epoch is checked before writer role so queued messages from the old writer deterministically fail as stale-owner.

### Generation/process safety

Before input/key/resize:
- registry generation/running state is checked;
- WebSocket route generation is checked;
- under TerminalManager's existing RLock, replay_view verifies current live generation again;
- actual TerminalManager input/key/resize is executed under that same re-entrant lock.

This prevents an old attachment from targeting a replacement PTY with the same internal terminal ID.

No new TerminalManager process primitive was required.

### Output and exit scoping

WebSocketHub translates attached Pi terminal output to:
- `pi_session_output {sessionId,generation,seq,data}`

Only peers attached to that exact Pi route receive it.

A Pi-attached peer does not receive the same bytes through generic `terminal_output` even if generic broadcast is processing the same event.

Unauthenticated/revoked peers are filtered again at send time using existing `can_terminal()`.

`terminal_list` generation state marks stale Pi routes inactive. This is used so a replacement terminal generation reusing the same internal ID cannot have its later terminal_exit mislabeled as the old Pi session.

Scoped exit event:
- `pi_session_exit {sessionId,generation,exitCode}`

No internal terminalId is exposed.

### Lock ordering / socket send behavior

Attach uses one documented nested order:
- TerminalManager lock -> WebSocketHub lock

Terminal output emission occurs after TerminalManager releases its lock, then WebSocketHub snapshots routing under its own lock.

Input/key/resize obtain transient route target under hub lock, release it, then acquire TerminalManager lock; no hub lock is held while acquiring terminal lock.

No socket send occurs while hub lock is held.

Existing peer send queue/backpressure behavior remains the send mechanism. Send failure removes the peer and performs the same Pi detach ownership cleanup; no new buffering path exists.

## TDD evidence

Initial RED:
- new `tests.test_pi_ws_contract` ran 6 tests;
- all errored because `dispatch()` did not accept `pi=` / Pi protocol did not exist.

After implementation, contract tests went GREEN.

A first GREEN run found one test expectation mismatch for `pi_session_key`: existing TerminalManager.key correctly encodes Enter to `\r` and writes through PTY input rather than calling a PTY key method. Test was corrected to assert existing TerminalManager behavior; production code was not changed for that mismatch.

Final contract suite now has 7 tests.

## PI-T006 acceptance coverage

`tests/test_pi_ws_contract.py` uses real:
- PiSessionRegistry;
- TerminalManager;
- WebSocketHub;
- dispatch.

Only PTY process I/O is fake/deterministic.

Coverage includes:
- first attach writer / second attach viewer;
- same-peer attach idempotence;
- replay seq/start/end/truncation/generation reuse;
- no terminalId in Pi replay/output;
- both writer/viewer receive one scoped output;
- unrelated peer receives no Pi output;
- no duplicate generic terminal_output for Pi-attached peer;
- exact writer input/key bytes once;
- writer-only resize;
- viewer input/key/resize rejection;
- explicit takeover;
- old epoch rejection;
- old writer remains viewer after takeover;
- new writer input acceptance;
- writer detach does not kill process;
- disconnect via hub.remove does not kill process;
- no arbitrary viewer auto-promotion;
- session switch detaches only switching peer;
- session A/B output isolation;
- two sessions have independent writers simultaneously;
- cross-session input substitution rejection;
- wrong PTY generation rejection;
- stale ownership epoch rejection;
- auth rejection before Pi metadata/output access;
- replacement PTY generation remains untouched by stale old-session input;
- replacement-generation exit is not mislabeled as old Pi session.

## Verification actually run after final code

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 7 tests OK in 0.034s

PI-T004 registry regression:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 9 tests OK in 0.033s

Ordinary terminal regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.193s

LAN multi-peer/performance regression:
- `uv run python -m unittest -q tests.test_lan_multi_perf`
- 19 tests OK in 4.436s

Terminal auth regression:
- `uv run python -m unittest -q tests.test_terminal_auth`
- 12 tests OK in 2.754s

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.987s

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.008s
- no paid AI prompt

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full ordinary repository suite after final route-active/exit scoping correction:
- `uv run python -m unittest discover -s tests -q`
- Ran 381 tests in 57.413s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn19/full-unittest-final2.err`

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate:
  - M lantern/ws.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0

No PI-T006 commit was made because independent REVIEW/TEST acceptance is still required.

## Preserved classifications / nonclaims

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T002 COMPLETE narrow native PTY proof;
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE structured spawn;
- PI-T004 COMPLETE and committed this turn;
- PI-T006 is now a REVIEW candidate only;
- PI-T007+ not started.

Still INCOMPLETE / NOT_MEASURED:
- runtime application injection of PiSessionRegistry into WebSocket upgrade;
- real browser consumption/F5 reattach;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX process execution;
- model/goal/custom-extension parity;
- CPU/RSS/latency/resource release acceptance.

## REVIEW request

Independent REVIEW must explicitly check:
- sessionId + PTY generation scoping;
- one writer / one resize owner semantics;
- ownership epoch monotonicity and stale-message rejection;
- detach/disconnect process survival;
- explicit takeover and no auto-promotion;
- A/B output/input/resize isolation;
- replacement-generation safety;
- no duplicate generic/Pi output;
- auth reuse and error payload non-leakage;
- ordinary Terminal compatibility;
- replay continuity helper reuse;
- lock ordering and attach replay race;
- send/backpressure behavior;
- YAGNI: transient route state in hub only, no persistence/process framework;
- no PI-T007/UI/Markdown/LAN policy scope drift;
- tests actually prove acceptance.

Route: REVIEW.
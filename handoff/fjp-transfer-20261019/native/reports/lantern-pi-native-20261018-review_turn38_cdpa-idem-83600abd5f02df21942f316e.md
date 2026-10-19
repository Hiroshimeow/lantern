# REVIEW turn 38 — R37 detach/remove ordering fixed; delayed pre-attach output is replayed and then delivered again

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 38  
Assigned handoff reviewed: DEV turn 39  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R37-1 is independently verified fixed: explicit detach and disconnect/remove now participate in the same per-peer Pi ordering boundary as replay, ownership notices, and output/exit enqueue. However a replay-continuity duplication race remains: output can be appended to TerminalManager before attach, included in the attach replay snapshot, but its delayed `terminal_output` broadcast can arrive after route registration and be delivered again as live `pi_session_output` with the same seq/data.

No implementation edits made by REVIEW.

## Inputs independently checked

- DEV turn 39 handoff, including the turn-39 `lantern/ws.py` source-loss/reconstruction incident.
- REVIEW turn 37 R37-1.
- PLAN turn 11 attach/replay continuity contract:
  - replay snapshot + attach must form one no-gap handoff;
  - replay continuity fields reuse TerminalManager seq/UTF-8 view;
  - live continuation must not duplicate already-replayed output.
- Current reconstructed `lantern/ws.py`.
- Current PI-T006 test source and related Terminal/Pi/auth/LAN regressions.
- Current Git truth and non-goal boundaries.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- current candidate paths remain:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, application/runtime wiring, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, Lantern :9999, or CDPA scope drift.

## Turn-39 reconstruction review

DEV explicitly reports that `lantern/ws.py` was truncated during turn 39 and semantically reconstructed rather than byte-for-byte restored.

Fresh structural inspection:
- reconstructed file is 1037 lines;
- HEAD baseline is 446 lines;
- diff is large because PI-T006 candidate work is uncommitted and accumulated in this file;
- the reconstructed module still preserves the expected ordinary WS/chat/SCM sections plus Pi-specific transport additions;
- no obviously missing dispatch branch or top-level helper was found in the reviewed regions;
- current source compiles and current tests execute.

The reconstruction incident materially raises the need for independent behavior verification, but the blocking finding below is a concrete protocol defect, not provenance alone.

## R37-1 — explicit detach/remove must serialize against Pi enqueue: RESOLVED

Current `WebSocketPeer._pi_notice_lock` is an `RLock`.

`WebSocketHub._pi_order_lock(peer)` returns/creates the same per-peer ordering lock for production and test peers.

The lock is now shared by:
- ownership notices;
- attach replay;
- Pi output/exit enqueue;
- explicit `pi_detach`;
- disconnect/remove attachment mutation.

Fresh current behavior and automated regressions verify:
- explicit detach waits if an output enqueue already owns the per-peer ordering boundary;
- remove waits if an exit enqueue already owns it;
- if detach/remove wins first, later Pi event revalidation sees the peer detached and drops the payload;
- process is not killed;
- staying peers still receive the event.

Fresh targeted tests:
- `test_inflight_output_cannot_enqueue_after_explicit_detach_completes`: PASS.
- `test_inflight_exit_cannot_enqueue_after_disconnect_remove_completes`: PASS.
- attach replay/live-output regression: PASS.
- replay continuity field regression: PASS.

Result:
- 4 tests;
- all OK;
- 0.026 s.

Fresh full PI-T006 contract:
- 33 tests;
- all OK;
- 1.664 s.

Fresh related PI/Terminal/auth/LAN regressions:
- 63 tests;
- all OK;
- 11.246 s.

Syntax:
- `py_compile`: exit 0.

`git diff --check`:
- exit 0.

So the exact R37 detach/remove ordering defect is independently verified fixed.

## Finding R38-1 — delayed pre-attach terminal_output is duplicated after replay

**Locations**
- `lantern/terminal.py:_queue_output()`
- `lantern/ws.py:pi_session_attach`
- `lantern/ws.py:WebSocketHub.broadcast()`

**Required invariant**

Attach replay is the baseline for live continuation.

If replay returns seq N, a peer must not subsequently receive a live `pi_session_output` event whose seq is <= N for data already included in that replay.

Otherwise the same terminal bytes are applied twice.

**Current TerminalManager order**

`_queue_output(entry, data)`:
1. takes TerminalManager lock;
2. appends data to retained output;
3. increments `entry.seq`;
4. releases the lock;
5. only then calls `self.emit(terminal_output)`.

This means retained replay state can advance before the corresponding output event reaches WebSocketHub.

**Current attach/broadcast interaction**

A delayed output event can therefore be in this state:
- already present in `TerminalManager.replay_view()`;
- seq already included in attach replay;
- not yet seen by WebSocketHub.

If attach occurs while that event is delayed:
1. attach captures replay including the bytes and seq;
2. peer becomes route-attached;
3. replay is enqueued;
4. delayed old `terminal_output` finally reaches hub;
5. route/session/generation membership all match;
6. hub delivers the same seq/data again as live `pi_session_output`.

Current Pi route state does not track the replay seq baseline needed to suppress already-replayed delayed events.

## Fresh deterministic reproduction

REVIEW used:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

The terminal emitter was paused only after TerminalManager had already:
- appended `PRE-ATTACH`;
- incremented seq to 1;
- constructed the generation-tagged terminal_output event.

While that event was paused before hub delivery, peer attached.

Fresh replay:

`replay_seq 1 replay_output 'PRE-ATTACH'`

Then delayed terminal_output was released.

Fresh live event:

`live_events [(1, 'PRE-ATTACH')]`

The proof assertion failed:

`already-replayed output was delivered again after attach`.

So the peer receives the same output:
- once in replay seq 1;
- once again as live output seq 1.

## Why this is material

This is a duplicate byte-stream defect in the core PI-T006 reconnect/attach contract.

It is distinct from R34:
- R34 covered output generated **after** replay capture racing ahead of replay;
- R38 covers output generated **before** replay capture but whose WS event delivery is delayed until after attach.

Both directions must be correct for a lossless replay/live handoff.

Seq already provides the exact boundary needed to identify this case.

## Required correction

Track the attach replay baseline per Pi attachment/route and suppress delayed output events already covered by that baseline.

Minimal acceptable direction:
- when attach replay is published, record a per-peer or per-route delivered replay seq for the exact sessionId + generation;
- before delivering `pi_session_output`, if event seq <= that attachment's replay baseline / last delivered seq, drop it;
- after live delivery, advance the attachment's delivered seq monotonically.

Equivalent generation-scoped continuity tracking is acceptable.

Requirements:
- no duplicate event for seq already represented in replay;
- no loss of event seq > replay seq;
- same-generation ordering remains monotonic;
- session switch/detach removes or replaces the old continuity state;
- replacement generation starts a fresh continuity baseline;
- staying peers with different attach times each use their own correct baseline if necessary.

Be careful with route-wide seq state:
- peers can attach at different times;
- a later viewer may have a higher replay seq than an earlier attached peer;
- therefore a single route-wide baseline can incorrectly suppress output needed by an earlier peer.
Per-peer attachment continuity state is the safer model unless another exact design proves equivalent.

Do not introduce:
- another retained transcript;
- browser-side dedupe as the primary fix;
- persistence/PI-T007;
- new protocol fields unless truly necessary.

Add deterministic regression matching the reproduction:
1. terminal output is appended/seq-incremented before attach;
2. delay only its hub delivery;
3. attach peer and confirm replay contains data at seq N;
4. release delayed terminal_output seq N;
5. assert no duplicate live Pi output reaches that peer;
6. emit fresh output seq N+1 and assert it does reach peer exactly once.

Also add a two-peer timing case if implementation uses per-peer state:
- peer A attached before seq N;
- peer B attaches after seq N is retained but before delayed event delivery;
- delayed seq N should still reach A if A has not already received it;
- delayed seq N must be suppressed for B because B replay included it.

That two-peer case prevents an incorrect route-wide suppression fix.

## Concurrency / module separation review

TerminalManager remains the owner of:
- retained byte stream;
- seq;
- generation.

WebSocketHub remains the owner of:
- peer attachment;
- per-peer outbound delivery continuity.

No new process registry or transcript store is required.

A small per-peer delivered-seq marker tied to attach token/session/generation is consistent with existing transient hub ownership.

## Complexity / ponytail review

Non-blocking reductions remain in reconstructed `lantern/ws.py`:

- `route["active"]` state plus terminal-list updater: **delete**; no current reader depends on it.
- public `pi_takeover()` wrapper: **delete**; dispatch uses `_pi_takeover_locked()`.
- public `pi_writer_target()` wrapper: **delete**; dispatch uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

Given the recent source reconstruction, avoid broad cleanup in the same turn as the continuity fix unless separately verified.

## Other required review dimensions

- **Correctness:** R37-1 fixed; blocked by R38-1 duplicate replay/live output.
- **Over-engineering:** turn-39 RLock/order helper is justified by shared enqueue/detach serialization.
- **Scope drift:** none detected.
- **UX:** duplicate terminal bytes can visibly duplicate text and corrupt terminal state.
- **Maintainability/module separation:** per-peer delivery continuity belongs in transient hub state, not PiSessionRegistry persistence.
- **Scalability:** only scalar seq state per attachment is needed.
- **Native Pi parity:** raw PTY bytes remain unchanged.
- **Concurrency isolation:** detach/remove ordering fixed; replay-vs-delayed-event continuity remains incomplete.
- **Auth/security:** no auth regression found.
- **Regression/performance:** focused contract/regression suites are fresh green; no release CPU/RSS/latency claim.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate.
- PI-T005 COMPLETE.
- PI-T004 COMPLETE / committed.
- PI-T006: **NOT ACCEPTED due R38-1**.
- PI-T007+ remain unauthorized.
- runtime application injection, browser F5/live reconnect, restart persistence/reopen, physical FJP input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix only R38-1: a delayed generation-tagged terminal_output already represented in a peer's attach replay must not be delivered again as live Pi output. Add the deterministic delayed-pre-attach-output regression and protect differing per-peer replay baselines. Preserve R22-R37 protections and do not start PI-T007/runtime/UI/persistence work.

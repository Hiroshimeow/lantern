# REVIEW turn 13 — generic UTF-8 replay watermark + PI-T003 public continuity proof

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 13  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `69214a799c4708b785136462fa2ce126df88d186`  
Main reviewed: `44b65ff5aac4bffa015385bbed3d0ce8643484c9`  
Disposition: **clean implementation review; ROUTE TEST** for independent acceptance of the continuity-watermark slice and PI-T003 PASS candidate. No implementation edits made by REVIEW.

## Inputs independently checked

- PLAN turn 8 in full, including:
  - explicit UTF-8 stream-position contract;
  - manager retention and WS display-cap arithmetic;
  - exact-client snapshot/delta proof requirements;
  - stop conditions and forbidden PI-T004/005/006 scope.
- DEV turn 13 handoff.
- Actual six-file implementation/test diff:
  - `lantern/terminal.py`
  - `lantern/ws.py`
  - `static/terminal_scm.js`
  - `tests/test_terminal_scm.py`
  - `tests/test_terminal_ui.py`
  - `tests/test_pi_reconnect_e2e.py`
- Current branch/base/status.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / freshness truth

Fresh REVIEW checks:
- branch `feat/lantern-bot`;
- `HEAD = 69214a799c4708b785136462fa2ce126df88d186`;
- `main = 44b65ff5aac4bffa015385bbed3d0ce8643484c9`;
- `main...HEAD = 0/3`;
- accepted commits are:
  - `aef4698 test(terminal): guard native xterm IME forwarding`
  - `20b535d test(pi): prove native TUI via TerminalManager`
  - `69214a7 test(pi): prove replay continuity boundaries`
- current implementation slice is intentionally uncommitted and changes exactly six owned files listed above;
- no Markdown-owner file, dependency file, vendor file, LAN/security file, or unrelated production path is dirty;
- `git diff --check` passes.

The rebase housekeeping is consistent with PLAN turn 8. No feature diff contains main's Markdown-owner work.

## Subtask 1 — TerminalManager UTF-8 continuity watermark

### Correctness

`TerminalEntry` replaces the old ambiguous character counter with explicit:
- `retained_start_utf8`;
- `stream_end_utf8`.

No duplicate history or second output buffer was introduced.

`_append_retained()` now:
1. appends to the same existing bounded `entry.output`;
2. advances `stream_end_utf8` by `len(data.encode("utf-8"))`;
3. if the existing character retention drops a prefix, advances `retained_start_utf8` by the UTF-8 byte length of exactly that removed prefix.

This preserves current visible retention semantics while making the retained interval explicit and cross-runtime.

`replay_view()` captures under the existing manager lock:
- meta;
- retained output;
- seq;
- retained-start UTF-8 position;
- stream-end UTF-8 position.

`replay_one()` remains backward-compatible as the original 3-tuple wrapper.

New terminal generations naturally begin at 0/0 because the explicit fields are dataclass defaults and new entries are constructed fresh.

### Atomicity / race review

The WS subscription path already holds `terminal.lock` while capturing replay state and registering the hub subscription. `TerminalManager.lock` is reentrant, so calling `replay_view()` inside that block preserves the existing atomic snapshot+subscription boundary.

Live output that races after subscription still receives later sequence numbers and is buffered/merged by the existing client sequence machinery.

No correctness defect found in the lock/sequence interaction.

## Subtask 1 — WebSocket public interval

`terminal_subscribe` now sends:
- `replayStartUtf8`;
- `replayEndUtf8`;

alongside existing output, seq, meta and display `truncated`.

If the existing WS display cap removes another character prefix:
- the output string is sliced exactly as before;
- the UTF-8 byte length of the omitted prefix is added to the public start;
- public end remains the manager stream end.

Therefore the public interval describes the **actual replay string sent to the browser**, not merely the manager-retained tail.

This correctly distinguishes:
- manager-retention loss;
- additional WS display-cap loss;
- current top-level `truncated` display semantics.

No unbounded history or additional replay store was added.

## Subtask 1 — browser boundary

The browser addition is minimal:
- `utf8Length()` uses `TextEncoder`;
- `isReplayContinuous(snapshot,start,end)` accepts only safe integer positions inside the public interval;
- replay messages record start/end bookkeeping;
- ordered live output advances the known stream end using UTF-8 bytes;
- reconnect, unsubscribe and generation replacement clear continuity bookkeeping.

Ordinary replay rendering remains reset+write as before for clients with no snapshot consumer.

The implementation does **not** add:
- Pi snapshot persistence;
- F5/sessionStorage restore;
- session picker;
- writer/takeover ownership;
- multitab policy;
- custom ANSI state;
- Pi-specific WS events.

This is within the PLAN-authorized generic terminal-v2 seam.

A small exported helper through the existing test API is justified because PLAN explicitly allowed a testable continuity helper before the real snapshot consumer exists.

## Independent UTF-8 arithmetic cross-check

REVIEW ran an additional disposable combined test over:
- ASCII;
- Japanese;
- emoji;
- Vietnamese;
- combining-mark text;
- multiple manager retention sizes;
- multiple WS display-cap sizes.

For every case it independently asserted:

`replayEndUtf8 - replayStartUtf8 == len(actual_output.encode("utf-8"))`

and:

`replayEndUtf8 == len(full_stream.encode("utf-8"))`.

Result: `combined_unicode_watermark_ok`.

This independently verifies that manager retention + WS display-cap arithmetic remains aligned across mixed Unicode samples.

## Subtask 2 — PI-T003 proof through public contract

The updated proof keeps historical negatives intact:
- bounded raw-tail replay is still explicitly non-lossless;
- server-headless real-Pi serializer -> exact browser remains non-equivalent;
- different-width replay remains unsupported.

The positive exact-client proof remains byte-faithful and same-geometry:
- accepted native Pi capture;
- exact vendored browser xterm;
- upstream serializer;
- exact vendored restore target;
- 120x40;
- corrected 6,130 UTF-8 byte snapshot metric.

### Short-detach public proof

The new proof obtains snapshot position S from a real public `terminal_replay.replayEndUtf8`, not from private manager state.

Then it:
- unsubscribes;
- writes one user input once;
- emits nine post-snapshot chunks with split ANSI, styles, cursor movement, DEC 1049 enter/exit, bracketed-paste mode, Japanese and emoji;
- resubscribes through the real public WS contract;
- validates S lies inside the public interval;
- extracts exactly the UTF-8 bytes after S;
- verifies the exact expected ordered delta;
- verifies exact retained-start boundary acceptance;
- verifies snapshot-at-end yields a valid empty delta;
- verifies PTY input was not resent;
- reruns the exact vendored-client full-state oracle using the same nine chunks.

This satisfies PLAN's short-detach, Unicode-boundary, exact-boundary and no-new-output cases.

### Forced manager-retention gap

The proof first learns S from a public replay, then forces bounded manager retention to remove older bytes.

Observed public replay:
- output `DEFGHIJK`;
- `replayStartUtf8 = 7`;
- `replayEndUtf8 = 15`;
- snapshot S = 4.

Because S < start, the helper rejects restoration before partial output is applied.

This is the exact previously blocking case.

### Forced WS display-cap gap

With manager retention complete but WS cap forced to 5 characters:
- output `GHIJK`;
- `replayStartUtf8 = 10`;
- `replayEndUtf8 = 15`;
- `truncated = true`;
- snapshot S = 4.

Again S < start and restoration is rejected before partial delta use.

This proves the public watermark handles both retention layers without relying on seq alone.

## Fresh REVIEW verification

Fresh enabled PI-T003 proof:

`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`

Result:
- 7 tests;
- all 7 OK;
- 12.965 s;
- exit 0.

Fresh focused terminal regressions:
- `test_terminal_scm.py`: 17 tests, OK, 4.990 s.
- `test_terminal_ui.py`: 13 tests, OK, 2.359 s.

Fresh LAN/multi-client regressions:
- `tests.test_lan_multi_perf`: 19 tests, OK, 3.193 s.

Syntax/static checks:
- `node --check static/terminal_scm.js`: exit 0.
- `git diff --check`: exit 0.

Fresh full repository suite:
`uv run python -m unittest discover -s tests -q`

Result:
- 357 tests;
- OK;
- skipped=132;
- 58.423 s;
- exit 0.

Existing ResourceWarning lines for temporary HTTPError cleanup remain warnings only.

## Review dimensions

- **Correctness:** UTF-8 interval math, atomic replay capture, sequence ordering, manager trim, WS-cap trim, short detach, exact boundaries and stale-gap rejection are all independently verified.
- **Over-engineering / YAGNI:** no duplicate history, no state engine, no new service, no registry, no speculative Pi protocol. Ponytail result: **Lean already. Ship.**
- **Scope drift:** no Markdown fidelity/diff/Crop/Milkdown implementation, LAN/security changes, Spec 001 T2 IME fix, PI-T004 registry, PI-T005 spawn seam, PI-T006 writer/takeover/multiview protocol, or bot UI replacement.
- **UX:** continuity is now safe at the generic replay boundary, but actual browser F5/restoration UX remains NOT_MEASURED. Same-geometry requirement remains explicit.
- **Maintainability/module separation:** retention ownership stays in TerminalManager; replay payload ownership stays in WS dispatch; xterm remains renderer/state parser; browser gets only generic continuity bookkeeping.
- **Scalability/resource:** existing bounded retention remains bounded; no extra replay history exists. CPU/RSS/latency and long-session resource acceptance remain NOT_MEASURED.
- **Native Pi parity:** accepted native Pi stream remains in the exact-client proof. FJP physical UniKey/IME/AltGr/image paste and live model/goal/custom-extension parity remain incomplete.
- **Concurrency isolation:** this slice proves sequence/no-resend/replay continuity only. One-writer/multi-viewer/takeover/resize-owner policy remains PI-T004/006-era work and is not claimed.
- **Regression/performance:** focused terminal, LAN/multi-client and complete 357-test suite are fresh green. No performance-release claim is made.
- **Upstream/native alternatives:** exact vendored xterm + upstream serializer remains the mature mechanism; no Lantern ANSI clone was introduced.

## Findings

No concrete reproducible implementation defect found in DEV turn 13.

The previous PI-T003 retained-delta blocker is materially addressed by a generic bounded UTF-8 replay continuity watermark:
- complete intervals can be restored;
- manager-retention gaps are detected;
- WS-cap gaps are detected;
- stale snapshots are rejected rather than silently partially restored.

This is a valid **PI-T003 PASS candidate**, but independent TEST is still required before PLAN may classify PI-T003 PASS or unlock PI-T004+.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T002 accepted.
- PI-T003: **PASS candidate pending independent TEST**.
- PI-T004-T013 remain BLOCKED pending that independent acceptance.
- browser F5/live reconnect, physical FJP input, multi-view ownership, arbitrary-width restore and resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE TEST.** TEST should independently reproduce:
- UTF-8 start/end arithmetic under manager retention and WS display cap;
- exact-client same-geometry short-detach restoration through the public contract;
- safe rejection of manager-retention and display-cap gaps;
- no-input-resend and ordinary terminal compatibility;
- focused/full regressions as appropriate.

Do not promote browser F5, physical FJP, PI-T004/005/006 or resource acceptance to PASS.

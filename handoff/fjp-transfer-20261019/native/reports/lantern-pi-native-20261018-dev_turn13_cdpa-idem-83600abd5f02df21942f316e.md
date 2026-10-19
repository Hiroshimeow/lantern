# DEV turn 13 — generic UTF-8 replay watermark + PI-T003 public continuity proof

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Contract followed

Read PLAN turn 8 and executed only the authorized linked slice:
1. housekeeping: preserve/commit accepted PI-T003 proof and rebase current main;
2. Subtask 1: generic terminal-v2 UTF-8 replay continuity watermark;
3. Subtask 2: complete PI-T003 proof through that public contract.

No PI-T004/005/006 session/writer protocol, no Pi-specific WS event, no replay history duplication, no unbounded log, no permanent xterm addon/vendor dependency, no Markdown implementation, no Spec 001 T2 IME fix, no LAN/security change, no live Lantern :9999 action, and no CDPA action.

## Housekeeping / accepted proof preservation

Incoming accepted replay proof SHA256:
- dd396bed28f9a0587034a52963ab5cf2e8aa865e6c2383e88200538434f7b853

Fresh accepted proof smoke before commit:
- LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 6 tests OK in 17.347s

Selectively staged only tests/test_pi_reconnect_e2e.py and committed:
- original pre-rebase commit: 2e3b39b test(pi): prove replay continuity boundaries

Main-only changes were confirmed Markdown-owner files, with no Terminal/Pi/WS conflict.

First rebase onto then-current main completed without conflict.

Main advanced again during implementation, still only in unrelated Markdown-owner files. PLAN required one more freshness rebase before the production commit. Because stash/reset/clean are forbidden, DEV:
- saved only this slice's six-file diff as ignored .plan evidence;
- restored only those six owned worktree files to HEAD;
- rebased cleanly onto current main;
- converted the saved patch from PowerShell UTF-16/CRLF to UTF-8/LF after git apply rejected its encoding;
- reapplied the exact saved diff.

No source was reconstructed by hand during this recovery. The final rebased accepted commits are:
- aef4698 test(terminal): guard native xterm IME forwarding
- 20b535d test(pi): prove native TUI via TerminalManager
- 69214a7 test(pi): prove replay continuity boundaries

Current base relationship:
- HEAD 69214a799c4708b785136462fa2ce126df88d186
- main 44b65ff5aac4bffa015385bbed3d0ce8643484c9
- main...HEAD = 0/3

## Subtask 1 — generic terminal replay continuity watermark

### TDD RED

Added focused tests before production edits.

Initial RED results:
- TerminalManager had no replay_view -> AttributeError
- terminal_replay had no replayStartUtf8 -> KeyError
- browser client exported no utf8Length/isReplayContinuous -> TypeError

These failures matched the missing continuity contract.

### TerminalManager change

Changed lantern/terminal.py only in the existing TerminalManager owner:
- replaced unused/ambiguous character output_offset with explicit:
  - retained_start_utf8
  - stream_end_utf8
- _append_retained now advances stream_end_utf8 by len(data.encode('utf-8'));
- when existing max_output character retention drops a prefix, retained_start_utf8 advances by the UTF-8 byte length of that exact removed prefix;
- existing bounded entry.output behavior is unchanged;
- no second history/log was added;
- new replay_view() captures meta/output/seq/start/end under the existing RLock;
- replay_one() remains backward-compatible and still returns its original 3-tuple;
- a new TerminalEntry/generation starts both positions at zero.

### WebSocket change

Changed lantern/ws.py only in the existing terminal_subscribe owner:
- terminal_subscribe now gets the atomic replay_view;
- if the existing WS display cap removes another prefix, replayStartUtf8 advances by that omitted prefix's UTF-8 byte count;
- replayEndUtf8 remains the manager stream end;
- terminal_replay now adds top-level:
  - replayStartUtf8
  - replayEndUtf8
- existing output, seq, meta and display truncated semantics are preserved;
- existing clients may ignore the additive fields.

### Browser boundary

Changed static/terminal_scm.js minimally:
- utf8Length() uses TextEncoder;
- isReplayContinuous(snapshot,start,end) accepts only a safe UTF-8 byte boundary inside [start,end];
- terminal_replay records replayStartUtf8 and streamUtf8;
- ordered live terminal_output advances streamUtf8 by TextEncoder byte length;
- reconnect/unsubscribe/generation change clears continuity bookkeeping;
- no Pi snapshot persistence, F5 storage, session picker, writer ownership, takeover or multitab protocol was added;
- helper functions are exported only through existing __lanternTerminalScm for focused testing/future snapshot consumer.

### Focused acceptance cases

tests/test_terminal_scm.py now proves:
- ASCII retention start/end: max_output=16 retains suffix at UTF-8 [6,22);
- Unicode + partial emitted-chunk retention with escaped Japanese/emoji;
- Python UTF-8 offsets, not code-point/UTF-16 counts;
- replay_one backward compatibility;
- generation reset to 0/0;
- WS no-cap public interval;
- WS display-cap public interval includes the additional omitted prefix.

tests/test_terminal_ui.py proves:
- TextEncoder byte count for A + Japanese + emoji;
- stale-before-start and after-end snapshots reject;
- S == replayStartUtf8 accepts;
- S == replayEndUtf8 accepts;
- terminal_replay records public offsets;
- Unicode live output advances streamUtf8 by UTF-8 bytes;
- generation replacement clears bookkeeping;
- ordinary writes remain unchanged.

## Subtask 2 — PI-T003 proof through public contract

tests/test_pi_reconnect_e2e.py preserves all prior diagnostic facts and now uses the public terminal_subscribe payload as the continuity authority.

Historical/diagnostic facts preserved:
- bounded raw-tail reset+write is NOT LOSSLESS;
- real-Pi server-headless serializer -> exact vendored browser remains non-equivalent;
- exact vendored-client 120x40 snapshot -> exact vendored-client remains equal;
- corrected snapshot metrics remain 6,130 UTF-8 bytes / 5,708 UTF-16 code units;
- different-width equivalence remains unsupported/false.

New exact short-detach public proof:
- accepted byte-faithful real Pi native capture is emitted through TerminalManager;
- snapshot position S is obtained from an actual public terminal_replay replayEndUtf8, not private manager fields;
- capture contains Unicode and S equals the exact raw UTF-8 byte length;
- client unsubscribes/detaches;
- one user input is written once;
- nine ordered post-snapshot chunks are emitted, including:
  - split escape sequence;
  - styles;
  - cursor movement;
  - alternate-screen enter/write/style/exit;
  - bracketed-paste mode;
  - Japanese + emoji;
- a new public terminal_replay is consumed;
- bytes after S are extracted only if S lies in the public [replayStartUtf8,replayEndUtf8] interval;
- extracted delta exactly equals the emitted ordered delta;
- S == replayStartUtf8 accepts;
- S == replayEndUtf8 yields valid empty delta;
- PTY input remains exactly one write; replay does not resend it;
- the exact vendored-client snapshot plus the same nine chunks remains full-oracle equal.

Forced manager-retention gap:
- public S is first learned from terminal_replay after 'SNAP';
- later retained history cuts inside subsequent output;
- next public replay reports replayStartUtf8=7, replayEndUtf8=15, output='DEFGHIJK', truncated=false;
- S=4 is older than start=7;
- proof rejects before applying partial output.

Forced WS display-cap gap:
- manager retention is complete;
- public S is learned before the later output;
- WS display cap=5 returns output='GHIJK', replayStartUtf8=10, replayEndUtf8=15, truncated=true;
- S=4 is older than start=10;
- proof rejects before applying partial output.

This directly addresses the prior blocker: seq alone is not used to claim continuity, and a partial emitted chunk can be detected by the byte watermark.

## Verification actually run

Final focused runs after the second freshness rebase and patch reapplication:
- test_terminal_scm.py: 17 tests OK in 4.678s
- test_terminal_ui.py: 13 tests OK in 2.307s
- LANTERN_PI_REPLAY_E2E=1 tests.test_pi_reconnect_e2e: 7 tests OK in 17.133s
- tests.test_lan_multi_perf: 19 tests OK in 2.912s
- node --check static/terminal_scm.js: exit 0
- git diff --check: exit 0

Fresh full repository suite:
- uv run python -m unittest discover -s tests -q
- Ran 357 tests in 81.754s
- OK (skipped=132)
- existing ResourceWarning HTTPError cleanup lines only
- evidence: .plan/lantern-pi-native-20261018/evidence-turn13/full-unittest.err

## Changed files

Production:
- lantern/terminal.py
- lantern/ws.py
- static/terminal_scm.js

Tests/proof:
- tests/test_terminal_scm.py
- tests/test_terminal_ui.py
- tests/test_pi_reconnect_e2e.py

Ignored rebase/full-suite evidence:
- .plan/lantern-pi-native-20261018/evidence-turn13/*

No Markdown-owner file or repository dependency/vendor file is dirty.

## Current repository state

- HEAD: 69214a799c4708b785136462fa2ce126df88d186
- main: 44b65ff5aac4bffa015385bbed3d0ce8643484c9
- main...HEAD = 0/3
- accepted committed feature diff relative to main remains only:
  - tests/test_terminal_ui.py
  - tests/test_pi_tui_e2e.py
  - tests/test_pi_reconnect_e2e.py
- current six-file continuity implementation/proof diff is intentionally uncommitted pending independent REVIEW/TEST.
- current tests/test_pi_reconnect_e2e.py SHA256: 826536dcb1a9270aeb61b2615f8886c0065d63bbf666a552deb9fc188d715032

## Classification / remaining boundaries

DEV evidence now supports a PI-T003 PASS candidate for the authorized public continuity seam:
- exact-client same-geometry snapshot restore: measured;
- complete short-detach delta: measured;
- manager retention gap: detected safely;
- WS display-cap gap: detected safely;
- exact-boundary and no-new-output cases: measured;
- Unicode byte boundary: measured;
- no input resend: measured.

Independent REVIEW and TEST are still required before PLAN may classify PI-T003 PASS.

Still NOT_MEASURED / INCOMPLETE:
- actual browser F5 against disposable live Lantern WS;
- FJP physical UniKey/IME/AltGr/image paste;
- live /model, /goal, custom extension parity;
- PI-T004+ session registry/writer/multiview ownership;
- arbitrary-width snapshot restore;
- cursor visibility beyond tested public oracle;
- CPU/RSS/latency/resource release acceptance.

Spec 001 remains:
- T1 COMPLETE / accepted / committed;
- T0-C physical >=50-attempt evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

## REVIEW request

Independent REVIEW must explicitly assess:
- UTF-8 unit correctness across Python/browser;
- atomic replay interval capture;
- manager retention and WS display-cap arithmetic;
- partial-chunk detection;
- browser helper/bookkeeping YAGNI and ordinary terminal compatibility;
- exact-client proof uses public WS contract for S/interval rather than private manager offsets;
- stale snapshots are rejected before partial render;
- no duplicate history/snapshot service or PI-T004/006 scope creep;
- module ownership, scalability/resource impact, native Pi parity boundaries, geometry/UX limitations, concurrency nonclaims, and regression evidence.

No production commit was made because this new implementation slice has not yet received independent acceptance.

Route: REVIEW.
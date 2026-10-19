# PLAN turn 8 — authorize minimal terminal replay continuity watermark to finish PI-T003

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 8
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn12_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** Independent TEST turn 5 reproduced the functional PI-T003 facts, DEV corrected its one snapshot-size evidence defect, and REVIEW turn 12 independently accepted that correction with no functional classification change. The remaining blocker is now narrow and actionable: expose enough continuity metadata in the existing bounded TerminalManager/terminal-replay contract to detect retained-output gaps safely, then rerun the exact-client PI-T003 proof through that public contract.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- branch: `feat/lantern-bot`;
- HEAD: `18a8743003c19a719f000166c42c66197e6e80f7`;
- local main: `1eeba4910d1e34e4045b514849b8625c9bb3234a`;
- `main...HEAD = 4 2`;
- merge base: `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`;
- current worktree candidate: only `?? tests/test_pi_reconnect_e2e.py`;
- feature-only committed files from the merge base:
  - `tests/test_terminal_ui.py`;
  - `tests/test_pi_tui_e2e.py`;
- main-only changes are Markdown-owner files:
  - `static/markdown_visual_shell.js`;
  - `tests/test_live_markdown.py`;
  - `tests/test_live_markdown_e2e.py`;
- no production Terminal/WS/Pi/UI source is dirty;
- repository dependency/vendor files remain unchanged.

Main movement is unrelated to this lane but must be incorporated before new production source edits. Preserve the untracked replay proof exactly through freshness housekeeping.

## Durable acceptance carried forward

### Spec 001

- T1: **COMPLETE / independently accepted / committed**.
- T0-C physical >=50-attempt four-channel UniKey evidence: **NOT_MEASURED / deferred**.
- T2 product fix: **BLOCKED**.
- No IME/keyboard product change is authorized.

### PI-T002

The native Pi TerminalManager/WinConPty proof is accepted and committed. It remains a narrow proof, not browser/FJP physical/release acceptance.

### PI-T003 — independently reproduced functional facts

TEST turn 5 independently reran the six acceptance categories and confirmed:

- bounded raw-tail reset+write: **NOT LOSSLESS**;
- real-Pi server-headless serializer -> exact vendored browser: **non-equivalent / failed representation**;
- byte-faithful exact vendored-browser snapshot -> exact vendored-browser restore at 120x40: **equal=true** under the full cell/style/cursor/buffer/mode/geometry oracle;
- exact-client snapshot + complete ordered eight-chunk post-snapshot delta: **equal=true**;
- deterministic manager replay boundary: sequence ordering preserved and input not resent;
- public `terminal_replay` after internal TerminalManager retention loss: **unsafe / gap not detectable**.

TEST independently inspected production and confirmed the blocker:
- `TerminalEntry.output_offset` advances internally when bounded retained output drops leading characters;
- `_info()` / `replay_one()` hide that position;
- `terminal_subscribe` can further slice output to the WS display cap;
- public replay contains output/seq/top-level display `truncated` but no actual retained-stream start position;
- `static/terminal_scm.js` therefore cannot distinguish a complete post-snapshot delta from a suffix missing older retained bytes.

TEST's only finding was a proof metric label: JavaScript `.length` was called bytes. DEV turn 12 corrected it to:
- exact snapshot UTF-8 bytes: **6,130**;
- exact snapshot UTF-16 code units: **5,708**.

REVIEW turn 12 independently reproduced those metrics and reran all six PI-T003 tests successfully. No functional replay classification changed.

Therefore the proof itself no longer needs another correction cycle before the continuity implementation.

## Architecture decision: smallest permitted continuity contract

PLAN authorizes a generic terminal-v2 continuity watermark only. This is prerequisite completion of PI-T003, **not** PI-T006 writer/session protocol work.

### Required semantics

Use an explicit monotonic **UTF-8 byte stream position** for retained PTY output.

Rationale:
- Pi/xterm output is Unicode-bearing;
- Python `len(str)` counts code points while JavaScript `.length` counts UTF-16 code units;
- current evidence already proved these metrics can diverge;
- UTF-8 byte positions are unambiguous across Python and browser `TextEncoder` and correspond to actual serialized transport content.

For each terminal generation, the server must be able to expose the exact UTF-8 stream position of:
- the first byte of the replay string actually sent to the client;
- the end position immediately after the replay string.

Names are implementation-detail choices, but use one clear pair consistently, e.g. `replayStartUtf8` / `replayEndUtf8`. Do not overload the existing display `truncated` boolean.

### TerminalManager requirements

Smallest change in `lantern/terminal.py`:

1. Keep existing bounded `entry.output`; do not add a second history.
2. Track cumulative UTF-8 output position and retained start position for the current generation.
3. When trimming by current `max_output` character limit:
   - calculate the UTF-8 byte length of the exact removed prefix;
   - advance retained-start by that byte length;
   - preserve existing visible retention behavior.
4. Appending output advances stream-end by `len(data.encode("utf-8"))`.
5. Expose an atomic replay view containing:
   - existing meta/output/seq;
   - retained start UTF-8 offset;
   - stream end UTF-8 offset.
6. New terminal generation starts its stream positions at zero.
7. Do not repurpose `output_offset` ambiguously. Either replace/internalize it with explicitly named UTF-8 fields while preserving any tests/contracts, or retain the old character offset internally and add explicit UTF-8 counters. REVIEW should reject confusing dual semantics.

The replay data and offsets must be captured under the same lock.

### WebSocket replay requirements

Smallest change in `lantern/ws.py`:

1. Existing `terminal_subscribe` remains the owner of replay payload construction.
2. If the WS display cap slices the retained output again, compute the UTF-8 byte length of that additional omitted prefix.
3. Public `terminal_replay` must expose the start/end offsets for the **actual output string included in that payload**, not merely the underlying manager tail.
4. Preserve existing `seq`, generation and display `truncated` behavior.
5. A snapshot at byte position S is continuous only if S lies within the available public interval and the bytes after S can be taken exactly; if S < replayStartUtf8, a gap exists and restore must be rejected as stale/incomplete.
6. Do not claim `seq` alone solves continuity; retention may cut inside an emitted chunk.
7. Do not add unbounded output retention or a second log.

No new Pi-specific WS event is required for this seam.

### Browser/client boundary

Only the minimum generic bookkeeping needed for continuity is permitted in `static/terminal_scm.js`.

- Preserve ordinary terminal replay behavior for clients that have no snapshot.
- Record/validate UTF-8 stream positions from `terminal_replay`.
- Live `terminal_output.data` may advance the local stream position by `TextEncoder().encode(data).length`; generation/seq rules remain authoritative for event ordering.
- If a future/restored snapshot position is older than public `replayStartUtf8`, the client must refuse partial snapshot+delta restoration rather than silently render it.
- Do not implement Pi session snapshots, F5 storage, sessionStorage transcript, writer ownership, takeover, or multitab behavior in this slice.
- If product browser code does not yet have a snapshot consumer, a small exported/testable continuity helper is enough; do not build speculative Pi UI around it.

Backward compatibility:
- existing ordinary terminal behavior must remain unchanged;
- legacy WebSocket clients must not break if they ignore new fields.

## Next DEV turn — maximum two linked subtasks

### Housekeeping — preserve accepted replay proof and rebase current main

Before production edits:

1. Record the current hash of `tests/test_pi_reconnect_e2e.py`.
2. Selectively stage **only** that proof file and commit it with a narrow replay-proof/test message. It has functional independent TEST acceptance and the metric correction has clean independent REVIEW.
3. Confirm clean tracked worktree.
4. Rebase `feat/lantern-bot` onto current local `main` without stash/reset/clean.
5. If any conflict occurs, or main changes this lane's Terminal/Pi files before rebase completes, abort safely and route PLAN. Do not resolve Markdown-owner conflicts by guesswork.
6. After rebase verify:
   - `main...HEAD = 0 3`;
   - feature-only diffs are the three accepted test files;
   - no Markdown-owner file appears in the feature diff.

If main advances again only in unrelated Markdown-owner files before the production commit, rebase once more under the same rule.

### Subtask 1 — implement generic replay continuity watermark

Allowed production/test paths:
- `lantern/terminal.py`;
- `lantern/ws.py`;
- minimally `static/terminal_scm.js`;
- focused `tests/test_terminal_scm.py`, existing WS contract tests if present, and/or the smallest new focused terminal-v2 test.

Required TDD cases before/with implementation:

1. ASCII retention:
   - emitted total > max_output;
   - public replay start/end exactly bound the sent suffix.
2. Unicode retention:
   - include ASCII + Japanese/Vietnamese/emoji;
   - prove Python UTF-8 positions equal browser/TextEncoder semantics, not code-point/UTF-16 counts.
3. Partial emitted-chunk trim:
   - retention cuts inside one previously emitted `terminal_output.data`;
   - seq remains latest but start offset advances, proving why seq alone is insufficient.
4. WS display cap:
   - manager tail itself is complete;
   - WS cap removes an additional prefix;
   - public replay start offset includes both omissions and top-level display `truncated=true`.
5. No-cap replay:
   - top-level display `truncated=false`;
   - start/end still accurate.
6. Generation reset:
   - a newly created generation starts byte positions at zero.
7. Ordinary terminal regression:
   - clients ignoring offsets still receive the same output/seq and render as before.

Do not introduce an offset field whose unit is unstated.

### Subtask 2 — complete PI-T003 proof through the new public contract

Update `tests/test_pi_reconnect_e2e.py` and ignored evidence only after subtask 1 works.

Required proof:

1. Keep the negative raw-tail and server-headless representations as historical/diagnostic negative facts.
2. Keep exact-client 120x40 real-Pi snapshot round-trip and 6,130-byte sample metric.
3. Associate the reference snapshot with an exact UTF-8 stream position S.
4. Short-detach case:
   - public replay interval contains S;
   - apply only bytes/output after S exactly once;
   - reconstruction remains full-oracle equal;
   - no input resend.
5. Forced manager-retention gap:
   - public replay start > S;
   - proof detects gap before applying output;
   - restoration is rejected/marked stale, never silently partial.
6. Forced WS display-cap gap:
   - same safe rejection if display cap pushes public replay start beyond S.
7. Exact-boundary case:
   - S == replayStartUtf8 is accepted.
8. No-new-output case:
   - S == replayEndUtf8 produces empty delta and remains valid.
9. Unicode boundary:
   - snapshot/replay boundary after a Unicode-bearing chunk proves byte positions remain aligned and no multi-byte character is split by the application logic.
10. Same geometry remains required; different-width equivalence remains false/not supported.

Browser F5 itself may remain NOT_MEASURED for this proof slice; the public continuity contract below F5 must be exact.

## Stop conditions

Route back without expanding scope if:
- reliable UTF-8 continuity requires retaining a second/unbounded history;
- current output representation cannot map the snapshot boundary without custom ANSI/private xterm state mutation;
- browser/client needs a Pi-specific session protocol merely to consume the generic offsets;
- a required change crosses Markdown implementation ownership;
- ordinary terminal compatibility would need a broad rewrite;
- LAN/security behavior would need to change.

Do not weaken PI-T003 acceptance to avoid the stop.

## Explicitly forbidden in this DEV turn

Do not start:
- PI-T004 PiSessionRegistry;
- PI-T005 structured argv/cwd/env production spawn seam;
- PI-T006 writer/resize ownership, takeover, Pi-specific attach protocol or multi-view isolation;
- PI-T007 restart lifecycle;
- PI-T008+ bot UI/session picker/context replacement;
- permanent xterm addon dependency/vendor change;
- client/server terminal snapshot persistence;
- duplicate transcript/history/unbounded raw log;
- custom ANSI/state engine;
- Markdown fidelity/diff/Crop/Milkdown/source changes;
- Spec 001 T2 IME fix;
- new LAN/security/auth/policy controls.

Never restart/attach to live Lantern `:9999`; never reset/stash/clean; never modify/reload CDPA.

## Required REVIEW after DEV

Independent REVIEW must explicitly assess:
- offset unit correctness and Unicode semantics;
- atomicity of replay start/end with output/seq;
- manager retention plus WS display-cap math;
- partial-chunk retention;
- ordinary terminal backward compatibility;
- whether browser bookkeeping is minimal/YAGNI;
- no duplicate terminal history or snapshot service;
- no PI-T004/006 scope creep;
- exact-client replay proof uses the public contract rather than private manager fields;
- stale snapshot is rejected before partial render;
- module ownership, scalability/resource impact, UX/geometry limitations, concurrency nonclaims, native Pi parity boundaries and regressions.

If clean, route independent TEST. Only after independent TEST proves both safe gap detection and exact short-detach restoration may PLAN classify PI-T003 PASS and unlock the next session-foundation slice.

## Current classifications

- Spec 001 T1: **COMPLETE**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: accepted G6 characterization; FJP browser/physical incomplete.
- PI-T001: baseline materially characterized; live release parity incomplete.
- PI-T002: accepted narrow native TerminalManager/WinConPty proof.
- PI-T003: **PARTIAL / BLOCKED; continuity watermark implementation now authorized**.
- PI-T004-T013: **BLOCKED pending PI-T003 independent acceptance**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 8. This required PLAN report is the only artifact written by PLAN.

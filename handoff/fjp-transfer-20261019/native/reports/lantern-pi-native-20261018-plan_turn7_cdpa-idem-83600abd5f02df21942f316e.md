# PLAN turn 7 — accept clean replay review, require independent TEST before minimal continuity-contract DEV

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 7
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn11_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE TEST.** REVIEW turn 11 is clean and resolves the proof defects. PI-T003 is still PARTIAL/BLOCKED because the public terminal replay contract cannot signal retained-output loss. The new exact-client positive result and the public-gap negative result are material acceptance facts and must be independently reproduced before PLAN authorizes the smallest production continuity seam.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- branch: `feat/lantern-bot`;
- HEAD: `18a8743003c19a719f000166c42c66197e6e80f7`;
- local main: `5afb9d095e3fbbd124c700cdfa6eb9719eaf73b7`;
- `main...HEAD = 2 2`;
- merge base remains `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`;
- the only worktree candidate is `?? tests/test_pi_reconnect_e2e.py`;
- no production Terminal/WS/Pi/UI/Markdown source is dirty.

The two current main-only commits are Markdown-owner work:
- `18896d2 test(markdown): lock live edit and external change contracts`;
- `5afb9d0 test(markdown): cover missing-file recovery race`.

They do not introduce a competing replay proof or Pi/session implementation. TEST must not rebase, merge, reset, stash or clean this branch; freshness is a later DEV housekeeping step after acceptance.

## REVIEW turn 11 accepted findings

REVIEW independently verified the corrected PI-T003 proof:

### Byte-faithful real Pi capture

The proof now reads the accepted native Pi capture as bytes and strictly decodes UTF-8. It records a successful byte-identical decode/re-encode round trip and no longer relies on Python universal-newline normalization.

Current accepted facts:
- capture size: 25,168 bytes;
- CRLF pairs: 173;
- exact-client reference and reconstruction geometry: 120x40;
- exact-client cursor: 0,35 on both;
- base/viewport: 16/16 on both;
- exact-client snapshot: 5,708 bytes;
- full cells/styles/cursor/buffer/modes/geometry oracle: equal=true.

### Exact-client short-detach representation

For the tested byte-faithful real-Pi state:
- exact vendored-browser xterm -> upstream serializer -> exact vendored-browser xterm is equivalent at the same canonical geometry;
- exact-client snapshot + eight complete ordered post-snapshot output chunks also reconstructs exactly;
- alternate-screen exit, cursor, styles/modes and sequence ordering in the deterministic proof remain covered;
- no input replay is observed in the manager boundary fixture.

This is a materially successful replay representation and is distinct from the already failed server-headless serializer representation.

### Public retained-output gap

The proof now exercises the real public path:
- `WebSocketHub`;
- `TerminalManager(max_output=8)`;
- `terminal_subscribe`;
- actual emitted `terminal_replay`.

After internal retention drops leading output, the browser-visible replay contains only the surviving suffix while:
- `seq` advances normally;
- top-level `truncated` remains false because that flag covers only the later WS display cap;
- no retained-stream start/offset/gap marker is exposed.

Therefore a client holding an exact-client snapshot can silently receive an incomplete post-snapshot delta and cannot determine from the public contract that restoration is unsafe.

This is the remaining PI-T003 blocker.

## PI-T003 classification after clean REVIEW

- bounded raw tail reset+write: **FAIL / not lossless**;
- server-headless xterm -> serializer -> exact browser: **FAIL / STOP representation**;
- exact browser snapshot -> exact browser restore, same geometry: **PASS for tested real-Pi state**;
- exact browser snapshot + complete ordered post-S delta: **PASS for tested short-detach case**;
- different-width equivalence: **FALSE / geometry-scoped**;
- no-input-resend deterministic fixture: **PASS narrowly**;
- current public retained-output gap detection: **FAIL / unsafe**;
- browser F5/live reconnect: **NOT_MEASURED**;
- full PI-T003: **PARTIAL / BLOCKED, not PASS**.

PI-T004/005/006 and later session/UI work remain blocked.

## PLAN architecture disposition

The remaining gap does **not** justify:
- an unbounded terminal log;
- a duplicate transcript/history store;
- a custom ANSI/state engine;
- weakening exact state equality;
- starting PiSessionRegistry, writer ownership, takeover, multiview or other PI-T004/006 behavior.

A narrow continuity seam is technically available in the existing TerminalManager/terminal-replay ownership and is the only production change PLAN is prepared to consider after independent TEST:

1. TerminalManager already tracks `TerminalEntry.output_offset`, the amount removed from the beginning of its bounded retained output.
2. `replay_one()` currently hides that retention position and returns only meta/output/seq.
3. `terminal_subscribe` may further slice the retained output to `_MAX_ACTIVE_REPLAY_CHARS`, also without exposing the actual start position of the replay string.
4. A future client snapshot can be safe only if it can associate the snapshot with a monotonic stream position and compare that position to the actual start/end of the subsequent replay tail.
5. If the replay starts after the snapshot position, the client must reject the snapshot as stale/unrecoverable rather than render a partial delta.

This may be solved by a **small generic terminal-v2 continuity watermark**, reusing existing bounded retention. It is not authorization for the broader PI-T006 session/writer protocol.

The exact field names and offset units are not frozen in this PLAN turn. A future DEV slice must choose a cross-Python/JavaScript representation with explicit Unicode semantics and tests; it must account for both TerminalManager retention and the WS display cap. Sequence alone is insufficient because retention can cut inside one emitted chunk.

No production change is authorized until TEST independently confirms the current proof facts below.

## Independent TEST turn assignment

TEST must independently reproduce the current `tests/test_pi_reconnect_e2e.py` acceptance boundary without editing implementation.

### 1. Verify exact candidate identity and scope

Confirm:
- candidate file exists and is non-empty;
- candidate hash matches the reviewed file unless an explainable no-op/report-only change occurred;
- no production source/dependency file is dirty;
- main drift remains unrelated to this feature lane;
- no custom ANSI parser, private xterm buffer mutation, permanent addon dependency, registry/session protocol or duplicate history store exists.

### 2. Run enabled PI-T003 proof

Run the gated proof with `LANTERN_PI_REPLAY_E2E=1`.

Independently verify all current categories rather than treating “suite green” as one undifferentiated PASS:

- bounded raw-tail replay is explicitly characterized as non-lossless;
- server-headless real-Pi representation is explicitly characterized as non-equivalent;
- byte-faithful exact-client real-Pi snapshot round-trip is equivalent under the full oracle;
- exact-client snapshot + complete ordered short delta is equivalent under the full oracle;
- deterministic manager sequence/no-input-resend assertion passes;
- public WS retained-output-gap test proves the replay payload cannot signal the internal gap.

The proof suite may be green because negative representations are now asserted as expected negative facts. TEST must report those classifications explicitly.

### 3. Independently inspect the public blocker

Verify production truth, not only the test implementation:
- `TerminalEntry.output_offset` advances when retention drops leading characters;
- `TerminalManager._info()` / `replay_one()` do not expose that value;
- `terminal_subscribe` emits output/seq/truncated but no internal retention start watermark;
- current `truncated` is tied to `_MAX_ACTIVE_REPLAY_CHARS`, not the earlier manager loss;
- `static/terminal_scm.js` cannot distinguish a complete post-snapshot delta from an internally truncated one.

If any existing public field already solves that gap, TEST must fail the blocker claim and route PLAN with the evidence.

### 4. Focused regression / preservation

At minimum run:
- `test_terminal_scm.py`;
- `test_terminal_ui.py`;
- syntax check for the replay proof;
- `git diff --check`;
- workspace status.

Do not repeat expensive full-suite/browser work unless current drift invalidates prior evidence. No live Lantern `:9999`, CDPA, paid AI prompt, rebase/merge/push/reset/stash/clean.

## TEST acceptance result expected

### If independently reproduced

Route PLAN with:
- exact-client short-detach replay = measured PASS at same geometry;
- public retention-gap detectability = measured FAIL;
- PI-T003 remains PARTIAL/BLOCKED;
- no product implementation defect in the proof.

PLAN will then be allowed to route a narrowly scoped DEV slice for **continuity metadata only**, plus the replay proof using that metadata. That future slice must undergo independent REVIEW and TEST before PI-T003 can become PASS.

### If not reproduced

Route PLAN with the exact discrepancy. Do not route downstream session work.

## Future DEV boundary if TEST confirms the blocker

This is recorded now so the architecture decision is durable; it is **not** the current route.

PLAN will permit at most two linked subtasks:

1. **Generic replay continuity watermark**
   - smallest additions to `lantern/terminal.py`, `lantern/ws.py`, focused terminal tests, and only the minimum browser bookkeeping needed to consume/validate the watermark;
   - reuse bounded output; no extra terminal history;
   - explicitly distinguish manager retention loss from WS display-cap truncation;
   - preserve legacy/ordinary Terminal behavior;
   - reject stale/incomplete restore instead of silently showing partial state;
   - Unicode/offset semantics must be cross-runtime and tested.

2. **PI-T003 proof through that public contract**
   - exact-client snapshot associated with a known stream position;
   - short-detach replay reconstructs exactly;
   - forced retention gap is detected and snapshot restore is refused/falls back safely, never silently partial;
   - no input resend;
   - same geometry requirement remains explicit;
   - actual browser F5 can remain NOT_MEASURED until the later live acceptance if the public contract is genuinely proven below it.

This limited continuity work is a prerequisite completion of PI-T003, not permission to implement Pi session registry, writer/takeover, multitab isolation, restart lifecycle or UI replacement.

## Preserved classifications

Spec 001:
- T1: **COMPLETE / accepted / committed**.
- T0-C: **NOT_MEASURED / deferred**.
- T2: **BLOCKED**.
- no IME product fix.

Spec 004:
- PI-T000 G6 characterization accepted; FJP browser/physical UX incomplete.
- PI-T001 baseline materially characterized; live release parity incomplete.
- PI-T002 narrow native TerminalManager/WinConPty proof accepted/committed.
- PI-T003: **PARTIAL / BLOCKED pending independent TEST and continuity gap solution**.
- PI-T004-T013: **BLOCKED pending PI-T003**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 7. This report is the only PLAN artifact written.

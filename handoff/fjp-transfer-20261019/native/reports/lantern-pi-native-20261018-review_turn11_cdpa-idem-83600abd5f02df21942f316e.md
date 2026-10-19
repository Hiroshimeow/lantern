# REVIEW turn 11 — verify byte-faithful PI-T003 proof and public WS retention-gap blocker

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 11  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `18a8743003c19a719f000166c42c66197e6e80f7`  
Current local main: `5afb9d095e3fbbd124c700cdfa6eb9719eaf73b7`  
Disposition: **clean proof review; ROUTE PLAN**. R10-1 and R10-2 are resolved. No new reproducible implementation defect was found. PI-T003 remains **PARTIAL / BLOCKED** because current public replay metadata cannot safely detect a retained-output gap after an exact-client snapshot. PI-T004/005/006 must not start under the current contract.

## Inputs independently checked

- PLAN turn 6 exact-client candidate and gap decision rules.
- REVIEW turn 10 findings R10-1/R10-2.
- DEV turn 11 handoff.
- Current `tests/test_pi_reconnect_e2e.py`.
- Turn-11 regenerated evidence:
  `.plan/lantern-pi-native-20261018/evidence-turn11/pi-t003-byte-faithful-and-ws-gap.json`.
- Production `TerminalManager` retention and `replay_one()` behavior.
- Production `terminal_subscribe -> terminal_replay` WebSocket dispatch.
- Browser replay handling in `static/terminal_scm.js`.
- Current Git state and concurrently advanced main.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository truth / preservation

Fresh REVIEW checks:
- `HEAD = 18a8743003c19a719f000166c42c66197e6e80f7`.
- local `main = 5afb9d095e3fbbd124c700cdfa6eb9719eaf73b7`.
- `main...HEAD = 2/2`.
- only worktree candidate is `?? tests/test_pi_reconnect_e2e.py`.
- candidate SHA256 remains `a1fd3f7a1ee6edc5344d5e1361bc25b6b03fe16e0ae41b96e5920960df716298`.
- `git diff --check`: exit 0.
- no production Terminal/WS/Pi/UI source is dirty.

Current main advanced after DEV's earlier rebase by exactly two Markdown-owner commits:
- `18896d2 test(markdown): lock live edit and external change contracts`
  - modifies `static/markdown_visual_shell.js`, `tests/test_live_markdown.py`, `tests/test_live_markdown_e2e.py`.
- `5afb9d0 test(markdown): cover missing-file recovery race`
  - modifies `tests/test_live_markdown_e2e.py`.

Main does not contain `tests/test_pi_reconnect_e2e.py` or `tests/test_pi_tui_e2e.py`; it does contain the older shared `tests/test_terminal_ui.py`. DEV correctly did not rebase the still-unaccepted PI-T003 proof again after unrelated main movement.

No reset/stash/clean/merge/push, live Lantern :9999 restart, CDPA action, dependency change, Markdown implementation by this feature lane, LAN/security change, custom ANSI engine, duplicate terminal history store, PI-T004/005/006 implementation, or Spec 001 T2 fix was introduced.

## R10-1 — byte-faithful accepted Pi capture: RESOLVED

Both real-Pi helpers now use:

`raw_bytes = raw_path.read_bytes()`  
`raw = raw_bytes.decode("utf-8")`

and assert:

`captureByteExact = raw.encode("utf-8") == raw_bytes`.

This removes Python universal-newline translation and uses strict UTF-8.

Turn-11 evidence records:
- capture bytes: 25,168;
- CRLF pairs: 173;
- CR bytes: 364;
- LF bytes: 173;
- strict UTF-8 round-trip: true.

The byte-faithful outcomes now match the independent REVIEW turn-10 control rather than the earlier normalized-input artifact:
- headless representation:
  - reference cursor 0,35;
  - base/view 16/16;
  - reconstruction cursor 3,35;
  - base/view 20/20;
  - equal=false.
- exact-client representation:
  - geometry 120x40;
  - ref/recon cursor 0,35;
  - ref/recon base/view 16/16;
  - snapshot size 5,708 bytes;
  - full oracle equal=true.
- exact-client + eight ordered post-snapshot chunks:
  - ref/recon cursor 10,1;
  - base/view 16/16;
  - normal buffer after DEC 1049 exit;
  - modes equal;
  - full oracle equal=true.

The prior normalized-stream 294/294 base/view and 14,223-byte artifact are no longer treated as acceptance evidence.

## R10-2 — actual public WS replay gap: RESOLVED

The previous private-manager-only test was replaced by:

`test_public_ws_replay_cannot_signal_internal_retention_gap`.

It now drives the real public path:
- `WebSocketHub`;
- `TerminalManager(max_output=8)`;
- `dispatch(peer, {"type":"terminal_subscribe", ...}, manager, None, hub)`;
- emitted `terminal_replay` payload.

Scenario:
- seq 1: `SNAP`;
- seq 2: `ABCDEFGHIJK`;
- manager retention drops leading bytes because max_output=8.

The runnable assertion verifies the actual client-visible replay payload:
- `seq == 2`;
- `output == "DEFGHIJK"`;
- top-level `truncated is False`;
- `meta.outputOffset` absent;
- `meta.oldestSeq` absent;
- `meta.truncated` absent.

This correctly distinguishes the existing WS/display-cap `truncated` flag from internal TerminalManager retention loss. The browser-visible protocol can therefore silently provide an incomplete post-snapshot delta with no usable gap signal.

This is the exact PLAN turn-6 blocker, now proven at the public boundary rather than inferred from private state.

## Fresh REVIEW verification

Fresh enabled command:

`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`

Result:
- 6 tests;
- all 6 OK;
- 9.663 s;
- exit 0.

The six tests currently establish:
1. bounded raw-tail replay is not lossless;
2. synthetic same-geometry serializer diagnostics remain narrow;
3. real-Pi server-headless -> exact-client representation remains non-equivalent;
4. byte-faithful real-Pi exact-client snapshot + short ordered delta is equivalent at 120x40;
5. public WS replay cannot signal internal retention loss;
6. manager output sequencing/no-input-resend remains ordered across a replay boundary.

Fresh focused ordinary regressions:
- `test_terminal_scm.py`: 15 tests, OK, 4.836 s.
- `test_terminal_ui.py`: 12 tests, OK, 2.168 s.
- `git diff --check`: exit 0.

DEV turn 11 also reports a fresh 332-test full suite PASS. REVIEW does not need to re-run that full suite again to resolve R10-1/R10-2 because the proof and focused terminal paths were freshly re-executed here; the full-suite result remains corroborating DEV evidence rather than the basis of this disposition.

## PI-T003 acceptance decision

The evidence now supports the following exact classification:

- existing bounded raw-tail reset+write: **NOT LOSSLESS**;
- server-headless xterm state -> serialize -> exact browser: **FAIL / STOP representation**;
- exact vendored-browser snapshot -> exact vendored-browser restore at canonical geometry: **PASS for tested byte-faithful real-Pi state**;
- exact-client snapshot + complete ordered post-S delta: **PASS for tested short-detach deterministic case**;
- no input resend in the deterministic manager boundary proof: **PASS for that narrow fixture**;
- different-width equivalence: **FALSE / geometry-scoped**;
- current public WS replay after retained-output loss: **unsafe / cannot detect gap**;
- long-detach recovery under current public replay contract: **BLOCKED**;
- full PI-T003: **PARTIAL, not PASS**.

PLAN turn 6 explicitly requires retained-delta gap behavior to be safe and non-silent before PI-T003 can pass. That condition is not met.

The remaining issue is not a defect in DEV turn 11's proof. It is a product/protocol architecture blocker exposed by the proof. REVIEW must not route DEV to silently implement PI-T006-era protocol changes when PLAN explicitly prohibited them in this proof slice.

## Required review dimensions

- **Correctness:** R10-1/R10-2 are directly verified. Exact-client short-detach proof and public gap failure are both reproducible.
- **Over-engineering/YAGNI:** no production abstraction, permanent dependency, custom parser/state engine, duplicate history mechanism, or replay service was added. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none into Markdown fidelity/diff/Crop/Milkdown implementation, LAN/security, Spec 001 T2, PI-T004+, PI-T005, PI-T006, registry/session foundation, or bot UI.
- **UX/end-user:** same-geometry short reconnect representation is feasible; arbitrary-width viewers remain unsupported, and live browser F5 behavior is still NOT_MEASURED.
- **Maintainability/module separation:** the exact browser xterm remains the terminal-state parser; upstream serializer is reused rather than cloned. The remaining blocker belongs to replay-gap/public protocol design, not terminal rendering.
- **Scalability/resource:** no unbounded history was proposed. Snapshot frequency, artifact size distribution, CPU/RSS/latency and long-lived-session resource ceilings remain NOT_MEASURED.
- **Native Pi parity:** the accepted byte-faithful native Pi stream is used. FJP physical IME/UniKey/AltGr/image paste and live /model-/goal-/extension parity remain incomplete/NOT_MEASURED.
- **Session/concurrency isolation:** current tests prove sequence bookkeeping and no input replay only. One-writer/multi-viewer ownership, takeover, resize ownership and multi-session isolation remain unaccepted.
- **Regression/performance:** focused Terminal regressions are green; no new production runtime path was introduced.
- **Upstream/native alternative:** exact-client upstream serialization is materially better than the failed headless representation but cannot by itself solve missing post-snapshot bytes.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T000 G6 characterization accepted; FJP browser/physical UX incomplete.
- PI-T001 FJP/G6 baseline materially characterized; live release parity incomplete.
- PI-T002 narrow native TerminalManager/WinConPty proof accepted/committed.
- PI-T003 PARTIAL / BLOCKED as above.
- PI-T004-T013 remain blocked by PI-T003.
- PI-T014/T015/T016 remain INCOMPLETE / NOT_MEASURED where applicable.
- overall objective NOT DONE.

## Findings

No concrete reproducible DEV implementation defect remains in turn 11. R10-1 and R10-2 are resolved. The remaining blocker is architectural and already mandated by PLAN's PI-T003 stop gate.

## Route

**ROUTE PLAN.** PLAN must decide the permitted architecture/stop disposition for the retained-delta gap. It must not promote PI-T003 to PASS, and it must not authorize PI-T004/005/006 under the current public replay contract unless the gap-safety contract is explicitly solved in an allowed future slice. Preserve the uncommitted proof, unrelated main Markdown work, and all NOT_MEASURED boundaries.

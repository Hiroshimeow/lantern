# REVIEW turn 6 — PI-T003 lossless replay proof gate

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 6  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`  
Disposition: **ROUTE DEV**. The raw-tail falsification and upstream serializer feasibility evidence are useful, but two PLAN-mandated replay stress cases are not actually proven. PI-T003 cannot be accepted as a PASS candidate yet.

## Independent inputs checked

- PLAN turn 5 contract and DEV turn 6 handoff.
- New `tests/test_pi_reconnect_e2e.py` in full.
- Ignored feasibility helper `.plan/lantern-pi-native-20261018/evidence-turn6/replay_probe.js` and retained `replay_probe.json`.
- Current browser replay implementation in `static/terminal_scm.js`, especially `replayWrite()`, `terminal_replay`, `terminal_output`, generation/seq handling, subscribe/unsubscribe behavior.
- Current `TerminalManager.replay_one()`, output sequencing, input, resize and lifecycle behavior.
- Temporary feasibility packages under `%TEMP%\lantern-pi-replay-proof\node_modules`.
- Current Git status/diff scope and the committed PI-T002 proof.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository truth / preservation

Fresh REVIEW observations:
- `HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- local `main = ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0/2`.
- committed turn-6 housekeeping commit `9d39a0f` changes only `tests/test_pi_tui_e2e.py`.
- current uncommitted path is only `?? tests/test_pi_reconnect_e2e.py`.
- no production Terminal/WS/Pi/UI/Markdown source is dirty.
- `package.json` has no working-tree diff; the accidental npm-init metadata edit was restored.
- `git diff --check` exit 0.

Spec 001 boundaries remain intact:
- T1 COMPLETE/accepted/committed.
- T0-C physical >=50-attempt four-channel evidence remains NOT_MEASURED/deferred.
- T2 remains BLOCKED.
- no terminal/IME product fix was introduced.

No reset/stash/clean/merge/push, live Lantern :9999 restart, CDPA change, Markdown fidelity/diff/Crop/Milkdown implementation, LAN/security/policy work, PI-T004+ registry/session implementation, PI-T005 production argv seam, or PI-T006 WS ownership implementation was introduced.

## Fresh REVIEW verification

Commands run independently:

1. Enabled PI-T003 proof:
   `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`
   - 3 tests, all OK
   - 4.675 s
   - exit 0

2. Ordinary gated run with the variable unset:
   `uv run python -m unittest -v tests.test_pi_reconnect_e2e`
   - 3 tests, skipped=3 with explicit gate reason
   - exit 0

3. Focused ordinary Terminal regression:
   `test_terminal_scm.py`
   - 15 tests, OK
   - 5.555 s
   - exit 0

4. `git diff --check`: exit 0.

These prove the test as currently written passes; they do **not** prove omitted PLAN acceptance cases.

## What the current PI-T003 proof does establish

### Raw-tail falsification

The exact vendored `static/vendor/xterm.js` is loaded in headless Edge and the oracle compares:
- visible cells and cell widths;
- foreground/background values and modes;
- bold/italic/underline/inverse/dim/blink/invisible/strikethrough;
- cursor x/y;
- active normal/alternate buffer type;
- base/viewport positions;
- exposed terminal modes;
- geometry.

Current retained-stream behavior is correctly classified:
- full split escape stream: equivalent;
- tested active alternate-buffer stream: equivalent;
- tested style/cursor stream: equivalent;
- tested public modes: equivalent;
- tested same-final-geometry resize stream: equivalent;
- bounded tail: **not equivalent**;
- different-width replay: **not equivalent**.

This supports the conclusion that today's bounded raw-tail `TerminalManager.replay_one()` + browser `term.reset(); term.write(output)` is not lossless.

### Upstream serializer feasibility

Temporary packages are outside the repository:
- `xterm-headless@5.3.0`;
- `xterm-addon-serialize@0.11.0`;
- serialize addon's peer range is `xterm=^5.0.0`.

No repository dependency file was changed. No custom ANSI parser/state engine was introduced.

The feasibility proof shows same-geometry equivalence for the tested:
- active alternate-buffer state;
- style/cursor/erase state;
- bracketed-paste/application-cursor modes;
- resize-to-final-geometry state.

Different-width reconstruction is correctly falsified. The classification as a **geometry-scoped candidate** is appropriate and does not justify arbitrary-width reuse.

### TerminalManager transport accounting

The deterministic fixture proves:
- one input write occurs exactly once;
- three output chunks receive seq 1/2/3 in one generation;
- `replay_one()` returns the accumulated bytes at seq 3;
- replay itself does not resend input;
- resize is manager/PTy-owned.

This is useful transport evidence but does not yet cover the required detach/output-race case below.

## Finding R6-1 — alternate-screen exit behavior is not tested

**Location:**  
- `.plan/.../evidence-turn6/replay_probe.js:59` raw alternate case  
- `.plan/.../evidence-turn6/replay_probe.js:66` serialized alternate case  
- `tests/test_pi_reconnect_e2e.py:166-169`

**Violated PLAN contract:** PLAN turn 5 explicitly requires deterministic **"alternate-screen enter/write/cursor/exit behavior"**. REVIEW must verify buffer/state equivalence, not merely that one active alternate-buffer snapshot serializes.

**Evidence:** Both alternate cases are:
`normal\x1b[?1049h` then `ALT\x1b[2;5H@`.

They enter alternate screen and leave the terminal **still in alternate buffer**. Neither sends `\x1b[?1049l`, returns to normal buffer, nor checks that the pre-alt normal-buffer state/cursor is restored equivalently after exit.

The unittest only asserts `serializeAlt.ref.type == "alternate"`; no exited-alt case exists.

**Required correction:** Add a deterministic raw and serialized case that:
1. establishes meaningful normal-buffer text/cursor state;
2. enters 1049 alternate screen;
3. writes/moves cursor/styles there;
4. exits 1049 alternate screen;
5. compares the reconstructed final normal-buffer cells/styles/cursor/modes at the same geometry.

Preserve the existing active-alt case as well; both active-alt and exit-alt matter. Do not weaken the oracle to text-only comparison.

## Finding R6-2 — detach while output is still arriving is not exercised

**Location:** `tests/test_pi_reconnect_e2e.py:177-203`, especially emits at lines 191-193 and replay at line 194.

**Violated PLAN contract:** PLAN turn 5 explicitly requires:
**"detach while output is still arriving, with ordered generation/sequence accounting and no duplicated input."**
The intended future snapshot contract also requires a sequence boundary plus ordered post-snapshot output.

**Evidence:** The current test:
1. writes one user input;
2. emits all three output chunks synchronously;
3. calls `replay_one()` only after output has stopped;
4. asserts seq 1/2/3 and no resend;
5. performs resize/kill.

No output is emitted after the replay/snapshot boundary, and there is no concurrent/in-flight output around detach/replay. Therefore it does not prove that post-snapshot output is preserved exactly once and remains correctly ordered relative to the replay boundary.

**Required correction:** Extend the deterministic manager proof so that output exists on both sides of a replay/detach boundary. At minimum:
- emit initial chunks and capture `replay_one()` with boundary seq N;
- emit one or more later chunks after that boundary;
- verify subsequent `terminal_output` sequence numbers continue N+1... under the same generation;
- verify the later bytes are not lost or duplicated and the original user input is still present exactly once in PTY writes;
- preferably exercise a controlled thread/event so one output arrival races with or follows the detach/replay boundary deterministically.

This remains transport-level proof; do not implement PI-T006 or claim one-writer/multi-viewer policy.

## Non-blocking observations

- Cursor visibility remains explicitly NOT_MEASURED because the tested public xterm buffer API does not expose it through the current oracle. This is acceptable if PLAN/TEST retain that limitation.
- The committed test depends on an ignored helper and temporary external packages for the serializer feasibility case. PLAN explicitly allowed ignored evidence helpers and temporary out-of-repo packages for this proof turn, so this is not a turn-6 defect. Before any long-lived regression test is relied on in a clean checkout, PLAN should decide whether to make the feasibility fixture self-contained or keep it as gated local evidence.
- Actual browser F5, live Lantern WS reconnect, real Pi server-side serialization, FJP physical IME/AltGr/image paste, custom extension/model/goal parity, arbitrary-width equivalence, session concurrency and performance/resource acceptance remain INCOMPLETE/NOT_MEASURED exactly as DEV states.

## Required review dimensions

- **Over-engineering/YAGNI:** no custom parser/state engine, permanent Node service, duplicate history store, registry, protocol, or command catalog. Temporary upstream packages are appropriate for feasibility. Ponytail result for production code: **Lean already. Ship.**
- **Scope drift:** none detected into forbidden Markdown, security/LAN, PI-T004+, PI-T005, PI-T006, or UI implementation.
- **UI/UX/end-user:** geometry dependence is now directly evidenced and is material for future viewer UX; arbitrary-width viewers cannot reuse one serializer artifact as equivalent.
- **Maintainability/module ownership:** current raw-tail replay remains owned by TerminalManager/browser xterm; future serializer state ownership is only a candidate, not implemented.
- **Scalability/extensibility:** geometry-scoped snapshots imply real cost/state implications and must be designed later; this proof correctly does not implement them.
- **Native Pi parity/upstream:** mature xterm serialization is used rather than a Lantern emulator. Real Pi/FJP/browser parity remains incomplete.
- **Session/concurrency isolation:** still unaccepted. The manager fixture proves sequence bookkeeping only.
- **Regression/performance:** focused Terminal SCM regression passes; full turn-6 suite and resource benchmarks were not run by REVIEW and remain INCOMPLETE/NOT_MEASURED.
- **Tests prove acceptance:** the current tests prove raw-tail falsification and a promising serializer candidate, but they do not yet prove two mandatory PI-T003 stress cases.

## Route

**ROUTE DEV.** Add the missing alternate-screen exit equivalence case and the post-boundary/in-flight output ordering case within the existing PI-T003 proof only. Do not start PI-T004/005/006 or any production replay/session implementation. After those required cases pass, return to independent REVIEW; if clean, independent TEST should reproduce the PI-T003 PASS/STOP result before PLAN authorizes any later architecture.

# REVIEW turn 8 — verify exact xterm 6 correction; PI-T003 still missing the real-Pi/client replay leg

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 8  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`  
Disposition: **ROUTE DEV**. R7-1 is resolved: the serializer feasibility run now uses the scoped xterm 6.0.0 family and passes the existing synthetic oracle. However PI-T003 still does not execute the PLAN-required real Pi native-state replay case, and the positive serializer proof reconstructs headless-to-headless rather than into Lantern's exact vendored browser xterm. The PASS candidate is therefore not yet sufficient.

## Independent inputs checked

- PLAN turn 5 PI-T003 contract.
- REVIEW turn 7 finding R7-1.
- DEV turn 8 handoff.
- Current `tests/test_pi_reconnect_e2e.py`.
- Current ignored `evidence-turn6/replay_probe.js` and serializer evidence.
- Exact vendored runtime identity recorded by accepted Spec 001 source evidence: `@xterm/xterm@6.0.0`.
- Spec 004 mature replay requirement and PI-T003 task boundary.
- Temporary package metadata under `%TEMP%\lantern-pi-replay-proof6`.
- Current Git state and the externally advanced local `main`.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / ownership truth

Fresh REVIEW observations:
- `HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- local `main = 1e3b77cda8d1d7e31019ccc79c38a6f63516817b`.
- `main...HEAD = 1/2`.
- current uncommitted tracked-candidate path is only `?? tests/test_pi_reconnect_e2e.py`.
- no production Terminal/WS/Pi/UI/Markdown source is dirty.
- `package.json`, `uv.lock`, and `package-lock.json` have no worktree diff.
- `git diff --check`: exit 0.

The new local-main commit `1e3b77c fix(markdown): bound Mermaid print and render work` is Markdown/Mermaid-owner work. Its Spec 001 edits are in Mermaid performance/print sections; it does not change the previously accepted `@xterm/xterm@6.0.0` terminal identity or the PI-T003 contract. DEV correctly reported the drift and did not rebase an unaccepted proof.

Spec 001 remains preserved:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no terminal/IME product fix.

No reset/stash/clean/merge/push, live Lantern :9999 restart, CDPA action, Markdown implementation, LAN/security work, PI-T004/005/006 implementation, registry, WS ownership protocol, bot UI replacement, custom ANSI parser, or production replay service was introduced.

## R7-1 exact-version correction — RESOLVED

The temporary feasibility environment is now the scoped xterm 6 family:
- `@xterm/headless@6.0.0`
- `@xterm/addon-serialize@0.14.0`

Fresh package inspection independently returned exactly those versions. The helper imports the scoped package names, and the unittest fails closed unless helper-reported versions equal:

`{"headless":"6.0.0","serialize":"0.14.0"}`.

Fresh direct helper run with `NODE_PATH` pointing only at `%TEMP%\lantern-pi-replay-proof6\node_modules`:
- `serializeAlt`: equal=True, alternate 20x6, cursor 5,1.
- `serializeAltExit`: equal=True, normal 20x6, cursor 4,1.
- `serializeStyle`: equal=True, normal 20x6, cursor 4,1.
- `serializeModes`: equal=True, normal 20x6, cursor 4,0.
- `serializeResize`: equal=True, normal 16x6, cursor 4,2.
- `serializeWidth`: equal=False; ref 12x6 cursor 3,2 vs reconstructed 20x6 cursor 3,1.

The jsdom canvas `getContext()` warning is still emitted, but the helper exits 0 and this proof makes no canvas/image-render claim. The same-geometry / cross-width classification is unchanged and honest.

## R6-1 / R6-2 preservation — verified

The active-alt and exited-alt cases remain in both the exact-vendored raw probe and serializer probe. The exited-alt case still establishes normal state, enters DEC 1049, writes/moves/styles in alternate, exits, and compares final normal-buffer state.

The deterministic manager proof still uses the controlled output boundary:
- seq 1/2 before replay boundary;
- replay returns exact bytes through seq 2;
- seq 3/4 arrive after boundary;
- second replay returns exact bytes through seq 4;
- generation stays stable;
- user input appears exactly once in PTY writes;
- post-boundary output is neither lost nor duplicated.

No PI-T006 writer/viewer policy is inferred.

## Fresh REVIEW verification

Enabled PI-T003 proof:
`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`
- 3 tests, OK
- 6.848 s
- exit 0

Ordinary gated execution:
`uv run python -m unittest -v tests.test_pi_reconnect_e2e`
- 3 tests, skipped=3 with explicit environment gate
- exit 0

Focused Terminal regression:
`uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 15 tests, OK
- 5.216 s
- exit 0

Syntax:
`uv run python -m py_compile tests\test_pi_reconnect_e2e.py`
- exit 0

Full repository discovery was also run fresh by REVIEW:
`uv run python -m unittest discover -s tests -q`
- **322 tests**
- **OK (skipped=115)**
- 63.004 s
- exit 0
- only the already-known ResourceWarning lines for implicitly cleaned HTTPError objects appeared.

So the prior turn-7 transient concurrency-suite failure is not reproduced in this REVIEW turn.

## Finding R8-1 — PI-T003 never exercises a real Pi native TUI stream

**Location:** `tests/test_pi_reconnect_e2e.py` and `evidence-turn6/replay_probe.js`.

**PLAN contract:** PLAN turn 5 explicitly requires:
> Use real Pi local/native UI states where legally available without paid-provider requests (for example native selectors/status) and a deterministic terminal fixture for terminal-state edge cases that Pi cannot reliably trigger locally.

**Evidence:** A targeted search of the entire PI-T003 test/helper finds no `WinConPty`, installed Pi CLI, PI-T002 capture, `/settings`, `/session`, or any real Pi native stream. The test consists of:
- synthetic ANSI/xterm streams; and
- a deterministic fake `NativePty` for sequence-boundary accounting.

Real installed Pi is legally available on G6 and was already exercised/captured in accepted PI-T002, so this item is not legitimately NOT_MEASURED.

**Required correction:** Add the smallest real-Pi replay case without a paid AI prompt. Reuse an accepted local native Pi state such as `/settings` or `/session` (a retained PI-T002 native stream is acceptable if its provenance is asserted), and subject that actual stream/state to the PI-T003 replay oracle. Keep deterministic synthetic cases for terminal edge conditions.

Do not broaden into browser F5, session registry, WS implementation, provider prompts, or physical FJP acceptance.

## Finding R8-2 — positive serializer reconstruction is headless-to-headless, not into Lantern's exact vendored browser xterm

**Location:** `.plan/.../evidence-turn6/replay_probe.js: serializedReplay()`.

**PLAN contract:** PLAN turn 5 says to use the repository's **exact vendored xterm build for screen comparison**, while evaluating headless+serialize as the mature server-side candidate. Lantern's actual client remains `static/vendor/xterm.js`.

**Evidence:** `serializedReplay()` creates:
1. a reference `new Terminal(...)` from `@xterm/headless`;
2. serializes it with `@xterm/addon-serialize`;
3. reconstructs into another `new Terminal(...)` from `@xterm/headless`;
4. compares those two headless snapshots.

The exact vendored `static/vendor/xterm.js` is used only by the separate raw-tail falsification path. No positive serializer artifact is replayed into the actual vendored browser terminal, so version alignment alone does not prove the cross-stack state artifact Lantern would need.

**Required correction:** Extend the proof so a 6.0.0 headless serializer artifact is written into the **exact vendored browser xterm** at the same geometry and compared with the full vendored-xterm reference oracle. The most efficient correction can combine R8-1 and R8-2: feed the same real Pi native stream into both the canonical headless state owner and the vendored-browser reference, serialize the headless state, restore that artifact into a fresh vendored xterm, then compare cells/styles/cursor/buffer/modes/geometry. Preserve the cross-width FAIL and cursor-visibility NOT_MEASURED limitations.

If this exact cross-stack real-Pi reconstruction is not equivalent, PI-T003 must be FAIL/STOP; do not fall back to synthetic headless-to-headless equivalence.

## Required review dimensions

- **Over-engineering/YAGNI:** no unnecessary production abstraction exists. The correction should remain proof-only and reuse the exact vendored xterm plus upstream scoped serializer. Ponytail result for production: **Lean already. Ship.**
- **Scope drift:** none detected into Markdown implementation, LAN/security, PI-T004+, PI-T005, PI-T006, registry, WS ownership, or bot UI.
- **UX/end-user:** different-width equivalence remains disproven; future snapshot state is geometry-scoped.
- **Maintainability/module ownership:** no duplicate terminal owner exists; headless serialization is still only a candidate for a future canonical state owner.
- **Scalability/extensibility:** snapshot/geometry costs remain future design work, not implemented here.
- **Native/upstream alternatives:** scoped xterm 6 correction is good, but native Pi + exact client interoperability is still the missing proof.
- **Session/concurrency isolation:** R6-2 proves only sequence-boundary/no-resend bookkeeping; one-writer/multiview semantics remain INCOMPLETE.
- **Regression/performance:** full Python suite is fresh green; CPU/RSS/latency/resource acceptance remains NOT_MEASURED.
- **Acceptance honesty:** browser F5/live WS reconnect, physical FJP input, cursor visibility, arbitrary-width equivalence, and PI-T004+ remain INCOMPLETE/NOT_MEASURED.

## Route

**ROUTE DEV.** R7-1 itself is fixed, but PI-T003 still lacks the PLAN-required real Pi native-state case and the actual headless-serializer -> exact vendored-browser reconstruction. Add those proof legs only; do not start PI-T004/005/006 or production replay/session work. Return to REVIEW with either exact cross-stack equivalence at canonical geometry or an honest FAIL/STOP.

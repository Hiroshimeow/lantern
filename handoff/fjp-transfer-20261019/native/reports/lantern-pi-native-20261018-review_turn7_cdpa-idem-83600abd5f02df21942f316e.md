# REVIEW turn 7 — verify R6-1/R6-2, re-check PI-T003 serializer candidate

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 7  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`  
Disposition: **ROUTE DEV**. R6-1 and R6-2 are resolved, but the upstream serializer candidate is being tested against xterm 5.x while Lantern's vendored runtime is authoritative xterm 6.0.0. That version mismatch is material to the PI-T003 pass gate.

## Independent inputs checked

- REVIEW turn 6 and DEV turn 7 handoffs.
- Current `tests/test_pi_reconnect_e2e.py`.
- Updated `.plan/lantern-pi-native-20261018/evidence-turn6/replay_probe.js` and `replay_probe.json`.
- Current `static/terminal_scm.js` replay/reset/seq/generation path.
- Repository source truth in `specs/001-terminal-ime-markdown-export/{spec,plan}.md` for the exact vendored xterm identity.
- Spec 004 mature replay reference in `specs/004-pi-native-harness/plan.md`.
- npm metadata for the temporary unscoped and current scoped xterm packages.
- Current Git scope/status.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / preservation truth

Fresh REVIEW observations:
- `HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- local `main = ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0/2`.
- current uncommitted path remains only `?? tests/test_pi_reconnect_e2e.py`.
- no production Terminal/WS/Pi/UI/Markdown source is dirty.
- `package.json` is clean; the earlier temporary npm-init mutation is not present.
- `git diff --check` exit 0.
- no reset/stash/clean/merge/push, live Lantern :9999 restart, CDPA action, Markdown fidelity/diff/Crop/Milkdown implementation, LAN/security/policy work, PI-T004+, PI-T005 or PI-T006 implementation was introduced.

Spec 001 preservation remains correct:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt four-channel evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no terminal/IME product fix was introduced.

## R6-1 — alternate-screen exit coverage: RESOLVED

Updated raw vendored-xterm case:
- creates styled normal-buffer state;
- enters DEC 1049 alternate screen;
- writes/moves cursor/styles in alternate;
- exits with `ESC[?1049l`;
- compares the final state with the existing full oracle.

Updated serializer case does the same.

Fresh artifact inspection:
- `altExit equal=True`, ref/reconstructed buffer type `normal`, cursor `4,1`.
- `serializeAltExit equal=True`, ref/reconstructed buffer type `normal`, cursor `4,1`.

The test retains the original active-alternate case as well as the exited-alternate case. Equality still includes cells/width, fg/bg + color modes, style flags, cursor x/y, buffer type, base/viewport, public modes and geometry. This satisfies the requested R6-1 correction.

## R6-2 — output crossing replay boundary: RESOLVED

The manager fixture now uses controlled `threading.Event` coordination:
1. one user input is written once;
2. producer emits seq 1/2 then signals the boundary and waits;
3. main test calls `replay_one()` and asserts exact retained output at seq 2;
4. producer is released and emits seq 3/4;
5. second replay asserts exact full output through seq 4;
6. emitted event data are exactly `["A", ESC[31, "mRED...reset", "POST"]`;
7. all event generations remain the original generation;
8. PTY writes remain exactly `["ONE-USER-INPUT"]`;
9. resize remains manager/PTy-owned.

This is the requested post-boundary ordering/no-resend transport proof. It does not overclaim PI-T006 writer/viewer policy.

## Fresh REVIEW verification

Enabled proof:
`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`
- 3 tests, OK
- 6.833 s
- exit 0

Ordinary gated run:
`uv run python -m unittest -v tests.test_pi_reconnect_e2e`
- 3 tests, skipped=3 with explicit gate
- exit 0

Focused ordinary terminal regression:
`test_terminal_scm.py`
- 15 tests, OK
- 4.840 s
- exit 0

`uv run python -m py_compile tests\test_pi_reconnect_e2e.py`: exit 0.  
`git diff --check`: exit 0.

DEV reported one full-suite concurrency failure outside this lane and an immediate isolated PASS. REVIEW independently reran that exact isolated test:
`tests.test_lan_multi_perf.LanPreviewConcurrencyTests.test_per_server_heavy_preview_slots_cover_separate_clients`
- 1 test, OK
- 0.117 s
- exit 0.

The full repository suite remains **not green for turn 7** because the prior full discovery had one failure and REVIEW did not rerun the entire suite. Do not promote it to PASS.

## Finding R7-1 — serializer proof uses the wrong xterm major/version family

**Location/boundary**
- `tests/test_pi_reconnect_e2e.py:8`, `_upstream_results()` around lines 100-120.
- `.plan/.../evidence-turn6/replay_probe.js` imports `xterm-headless` and `xterm-addon-serialize`.
- DEV turn 6/7 calls these packages “version-compatible”.

**Violated contract/invariant**
PI-T003 must evaluate a mature replay mechanism that is compatible with Lantern's **exact vendored xterm stack**. PLAN turn 5 says to use the repository's exact vendored build for screen comparison and evaluate the version-compatible upstream headless/serialization mechanism. Spec 004 names the mature scoped packages `@xterm/headless` + `@xterm/addon-serialize`.

**Independent evidence**
Repository source truth explicitly records the vendored asset as upstream:
- `specs/001-terminal-ime-markdown-export/spec.md:62` => `@xterm/xterm@6.0.0`.
- `specs/001-terminal-ime-markdown-export/plan.md:24` => same authoritative 6.0.0 identity.

The current feasibility environment instead uses:
- `xterm-headless@5.3.0`
- `xterm-addon-serialize@0.11.0`

Fresh npm metadata:
- unscoped `xterm-headless` latest = **5.3.0**
- unscoped `xterm-addon-serialize` latest = **0.11.0**
- the installed 0.11.0 addon declares peer `xterm=^5.0.0`
- scoped `@xterm/headless` current = **6.0.0**
- scoped `@xterm/addon-serialize` current = **0.14.0**
- `@xterm/xterm` current = **6.0.0**

Therefore the candidate equivalence results are for the legacy xterm 5.x family, not the authoritative Lantern 6.0.0 family. The raw-tail falsification still uses the exact vendored browser xterm and remains valid, but the positive serializer PASS candidate is not yet version-matched to Lantern.

**Required correction**
Repeat the upstream serializer feasibility with the **6.0.0 scoped xterm family**, using temporary out-of-repository packages only:
- `@xterm/headless@6.0.0`
- a matching `@xterm/addon-serialize` release for xterm 6.0.0 (current registry release is 0.14.0; verify it directly rather than assuming)
- update the helper imports/test availability checks accordingly.

Re-run the complete same-geometry oracle cases:
- active alternate;
- exited alternate normal-buffer restoration;
- styles/cursor/erase;
- tested terminal modes;
- resize;
- different-width falsification.

Do not modify repository `package.json`, lockfiles, vendored xterm, or production dependencies. If xterm 6 scoped serialization fails any required case, PI-T003 must become FAIL/STOP rather than falling back to the 5.x result.

## Required review dimensions

- **Over-engineering/YAGNI:** no custom ANSI/state parser, permanent Node service, duplicate transcript/history store, registry, protocol or compatibility shim. The correction should only swap the temporary feasibility packages/helper imports to the exact upstream 6.x family. Production code remains lean.
- **Scope drift:** none detected into forbidden Markdown implementation, LAN/security, PI-T004+, PI-T005, PI-T006 or bot UI implementation.
- **UI/UX/end-user:** different-width replay remains correctly falsified, so any future snapshot is geometry-scoped; arbitrary viewer widths are not accepted.
- **Maintainability/module ownership:** current raw-tail ownership remains TerminalManager/browser xterm. Serializer state ownership is only a future candidate, not implemented.
- **Scalability/extensibility:** geometry-scoped snapshot cost/state remains a later architecture concern; no premature implementation is present.
- **Native/upstream parity:** this is the blocking review issue. The mature mechanism is correct in concept, but the positive proof currently targets xterm 5.x while Lantern runs xterm 6.0.0.
- **Session/concurrency isolation:** not accepted; R6-2 only proves sequence boundary/no-resend bookkeeping.
- **Regression/performance:** focused terminal regression passes. Full suite is not currently a turn-7 PASS; CPU/RSS/latency remain NOT_MEASURED.
- **Tests prove acceptance:** R6-1/R6-2 tests are now adequate, and raw-tail failure is proven. The serializer PASS candidate is still unproven for Lantern's actual xterm major.

## Route

**ROUTE DEV.** Keep R6-1/R6-2 unchanged, replace the temporary legacy xterm 5.x serializer feasibility with the exact scoped xterm 6.0.0 family, and rerun the same state oracle. Do not start PI-T004/005/006 or production replay/session work. Return to REVIEW with either a version-matched PASS candidate or an honest FAIL/STOP.

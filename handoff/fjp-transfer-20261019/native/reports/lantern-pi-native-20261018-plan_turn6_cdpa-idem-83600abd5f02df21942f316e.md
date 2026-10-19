# PLAN turn 6 — PI-T003 headless representation STOP; test exact-client upstream snapshot before final blocker disposition

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 6
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn4_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** TEST independently reproduced the PI-T003 failure for the current server-side headless-xterm serializer representation. That representation remains STOP and must not be used for PI-T004/005/006. One materially different mature-upstream PI-T003 candidate remains legally actionable: serialize from the exact vendored browser xterm itself, then prove snapshot + post-snapshot delta reconstruction. This is still PI-T003 proof work only.

## Fresh repository truth

Verified on G6 `desktop-b5e4iue-87cea2af`:

- Branch: `feat/lantern-bot`.
- HEAD: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- Current local `main`: `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`.
- Merge base: `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 7 2`.
- Feature-only committed files from the merge base are exactly:
  - `tests/test_terminal_ui.py`;
  - `tests/test_pi_tui_e2e.py`.
- Main-only files from the merge base are Markdown/Mermaid owner work (spec 001 Markdown sections, plugin/preview/editor characterization/assets/tests); main has not introduced a competing `tests/test_pi_reconnect_e2e.py`.
- Current worktree has only `?? tests/test_pi_reconnect_e2e.py`.
- No production Terminal/WS/Pi/UI/Markdown source is dirty.
- `package.json`, lockfiles and repository dependencies were not changed by the replay proof.

A previous intermediate interpretation of `git diff HEAD..main` was corrected: deletions shown there mean the feature-only tests are absent from main, not that main edited those lane files.

## TEST turn 4 result accepted

Independent TEST reproduced the required enabled PI-T003 proof against:
- accepted real Pi 1.3.0 WinConPty capture;
- temporary `@xterm/headless@6.0.0`;
- temporary `@xterm/addon-serialize@0.14.0`;
- repository exact `static/vendor/xterm.js`.

Enabled result:
- 4 tests run;
- 3 diagnostic/synthetic tests pass;
- real-Pi exact cross-stack test fails;
- process exit 1 by the acceptance equality assertion.

The exact failure is material:
- same nominal geometry 120x40;
- reference vendored-browser cursor = (0,35);
- reconstruction cursor = (3,35);
- base/viewport also differ;
- exposed modes match;
- preserving exact Windows newline content does not restore equality.

Therefore these classifications are durable:

- **Existing bounded raw-tail reset+write:** NOT LOSSLESS.
- **Server-side `@xterm/headless` -> serialize -> vendored browser:** **PI-T003 FAIL/STOP**.
- **Synthetic same-geometry serializer success:** diagnostic only; cannot override real-Pi failure.
- **Different-width replay:** not equivalent / geometry-sensitive.
- **Browser F5/live WS reconnect:** NOT_MEASURED.
- **PI-T004/005/006 and later session/UI implementation:** BLOCKED under this failed replay representation.

No correctness defect in the proof test itself was found by REVIEW or TEST.

## Why one PI-T003 candidate remains actionable

The failed path serializes a terminal state created by `@xterm/headless` and restores it into the browser build. It does **not** test a snapshot produced by the exact browser xterm instance that Lantern actually renders.

The temporary upstream `@xterm/addon-serialize@0.14.0` package is already present outside the repository and exposes a standalone ES module whose `SerializeAddon.activate(terminal)` works against a terminal instance; the module does not require maintaining a Lantern ANSI parser. This makes an exact-client proof possible without:
- modifying repository dependency files;
- inventing a terminal state engine;
- creating a permanent Node/browser service;
- implementing session/WS ownership;
- weakening the state-equality oracle.

This is a genuinely different representation: **exact client xterm snapshot + ordered server delta**, not server-headless snapshot.

Testing it is consistent with the governing instruction to exhaust mature/native mechanisms before declaring the replay requirement externally blocked.

## Next DEV turn — PI-T003 continuation only

At most two coherent proof subtasks are authorized. No production feature implementation.

### Housekeeping before proof: rebase safely onto current main

Before editing the replay proof:
1. Reconfirm merge-base/main-only paths and that `tests/test_pi_reconnect_e2e.py` is absent from main.
2. Preserve the untracked proof file exactly; record its hash before rebase.
3. Run `git rebase main` without stash/reset/clean. Main-only changes are outside this lane based on the verified merge-base diff.
4. If rebase reports any conflict, overwrite risk, or touches Markdown-owner content beyond automatic replay of the two feature test commits, **abort the rebase and route PLAN**. Do not resolve cross-owner conflicts by guesswork.
5. After a clean rebase, verify:
   - branch is `0/2` relative to main;
   - feature diff remains the two accepted test files only;
   - untracked replay proof is byte-identical to its pre-rebase hash.

This is repository freshness housekeeping, not a substantive task.

### Subtask 1 — exact vendored-browser serializer round-trip

Keep the already verified failed headless representation as a **negative characterization**, not as the new acceptance candidate.

Adjust the runnable proof so:
- the existing real-Pi headless-serializer case records/asserts its known non-equivalence explicitly (for example, a test whose acceptance is that `equal == false` for this candidate);
- evidence retains the prior REVIEW/TEST hashes/results and does not rewrite history as if it ever passed.

Add a new positive acceptance case using the exact vendored browser xterm for both snapshot source and restore target:

1. Use a disposable local/headless-Edge proof harness only; never use live Lantern `:9999`.
2. Load the repository exact `static/vendor/xterm.js`.
3. Load temporary upstream `@xterm/addon-serialize@0.14.0` from a disposable server/temp root; do not copy it into the repository or alter package/lock/vendor files.
4. Create the reference vendored xterm at the required geometry.
5. Feed the accepted real Pi native stream into that exact reference terminal.
6. Attach upstream `SerializeAddon` to **that same browser terminal** and serialize with sufficient scrollback and modes/alt-buffer included.
7. Create a second exact vendored xterm at identical geometry and write only that snapshot artifact.
8. Compare the full established oracle:
   - cells/chars/width;
   - fg/bg/color modes;
   - style flags;
   - cursor x/y and visibility where exposed;
   - active buffer;
   - base/viewport/history extent;
   - exposed terminal modes;
   - geometry.

No visible-text-only equivalence is acceptable.

If exact-client round-trip fails, stop immediately. Preserve the failing runnable assertion and evidence; do not attempt custom cursor escapes, manual cell JSON restore, xterm private-buffer mutation, or a Lantern serializer patch.

### Subtask 2 — snapshot + ordered delta boundary, only if subtask 1 passes

If and only if the exact-client snapshot round-trip is exact, prove the reconnect representation rather than assuming it:

- Establish a snapshot at sequence S from the exact client xterm.
- Retain only server-side PTY output **after S** using the existing ordered generation/sequence semantics.
- Produce additional deterministic output after the snapshot. Prefer real Pi local/native UI commands that require no paid provider; deterministic terminal fixture output is acceptable for terminal-state edge cases.
- Restore a new exact vendored xterm from:
  1. the client-generated upstream snapshot;
  2. then post-S raw output exactly once in sequence order.
- Compare against the continuously connected reference terminal with the same full oracle.
- Prove input is not replayed/resubmitted.
- Prove chunk-boundary splits do not change the result.
- Reconfirm alternate-screen/style/cursor/mode behavior.
- Test same owner geometry as the positive case.
- Keep the already-established different-width result explicit: snapshot is geometry-scoped unless a mature mechanism proves otherwise. Do not fake arbitrary-width equivalence.

#### Required truncation/gap result

The current TerminalManager output retention is bounded. The proof must not hide that.

Simulate/measure a post-snapshot delta gap that exceeds retained output:
- if the server cannot reconstruct every byte after snapshot sequence S, the proof must detect a gap and classify the snapshot unusable;
- silent partial restore is a failure;
- do not solve the gap by adding an unbounded terminal log, duplicate transcript/history store, or new production persistence in this turn.

If exact client snapshot + bounded delta has no lossless fallback for a detached session that outlives the retained delta, report that as the remaining PI-T003 blocker even if short-detach reconstruction passes.

## PI-T003 decision rules for this turn

### Candidate PASS is allowed only if all are true

- exact browser-generated upstream snapshot round-trips the real Pi state under the full oracle;
- snapshot + ordered post-S delta reconstructs exactly for deterministic detach/output cases;
- no input is resent;
- alt-buffer/cursor/styles/modes/chunk boundaries are covered;
- geometry ownership is explicit;
- retained-delta gap behavior is safe and non-silent;
- no custom ANSI/state engine or duplicate history mechanism is introduced.

A short-detach-only success with no acceptable long-detach/gap disposition is **not** full PI-T003 PASS; classify it PARTIAL and return to REVIEW/PLAN.

### STOP

If exact-browser serializer itself fails, or the only way to cover delta gaps is a custom state engine/unbounded duplicate terminal history, preserve the evidence and stop PI-T003. Do not route into session foundation.

## Explicitly forbidden

Do not implement or start:
- PI-T004 PiSessionRegistry;
- PI-T005 production argv/cwd/env spawn seam;
- PI-T006 WS attach/writer/resize/replay protocol;
- PI-T007 lifecycle/restart;
- PI-T008+ UI/session/context replacement;
- production xterm snapshot protocol;
- permanent addon vendoring/dependency change;
- custom ANSI parser/state JSON restore;
- duplicate transcript/history/raw-log persistence;
- Markdown fidelity/diff/Crop/Milkdown/source work;
- Spec 001 T2 IME fix;
- LAN/security/auth/policy changes.

Never restart/attach to live Lantern `:9999`; never reset/stash/clean; never modify/reload CDPA.

## Required REVIEW / TEST after DEV

Independent REVIEW must decide whether:
- the exact-client candidate is genuinely distinct from the already failed headless representation;
- the oracle remains strict and complete;
- no private xterm/internal-state mutation or hand-authored terminal restore logic crept in;
- delta sequence/gap semantics are correct;
- long-detach/resource implications are honest;
- YAGNI, module ownership, scalability, ordinary Terminal regression, UX/geometry, and native Pi parity boundaries remain intact.

If REVIEW finds a valid candidate, route TEST for independent reproduction. If REVIEW confirms another STOP, route PLAN rather than DEV downstream.

Independent TEST must reproduce the positive or failing exact-client result itself; no unrun F5/FJP/physical evidence may be promoted to PASS.

## Current classifications

- Spec 001 T1: **COMPLETE / accepted / committed**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: G6 characterization accepted; FJP browser/physical UX incomplete.
- PI-T001: exact FJP baseline materially supported; live release parity incomplete.
- PI-T002: **PASS for narrow native TerminalManager/WinConPty proof**.
- PI-T003 raw-tail representation: **FAIL**.
- PI-T003 server-headless serializer representation: **FAIL/STOP**, independently reproduced.
- PI-T003 exact-client upstream snapshot representation: **ACTIONABLE / not yet measured**.
- PI-T004-T013: **BLOCKED pending PI-T003**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- Overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 6. This required PLAN report is the only artifact written by PLAN.

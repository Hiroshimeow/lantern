# DEV turn 10 — exact-client PI-T003 snapshot passes short-detach; bounded-delta gap remains blocker

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Contract / scope followed

Read PLAN turn 6 and AGENTS.md. Loaded executing-plans, test-driven-development, verification-before-completion, and ponytail.

This turn stayed inside PI-T003 proof work only:
- required freshness rebase onto current main;
- Subtask 1 exact vendored-browser snapshot source/restore;
- Subtask 2 snapshot + ordered delta proof and bounded-retention gap characterization.

No PI-T004/005/006 implementation, production replay/session protocol, registry, WS ownership, UI replacement, permanent addon dependency/vendor change, custom ANSI/state engine, duplicate transcript/history store, Markdown implementation, Spec 001 T2 IME fix, LAN/security work, live Lantern :9999 action, or CDPA action was started.

## Freshness housekeeping / rebase

Pre-rebase truth:
- HEAD 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
- main 0eed7ed92dd758f64fbaecd8f958b568d29c9d32
- merge base ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- main...HEAD = 7/2
- untracked proof file only: tests/test_pi_reconnect_e2e.py
- main does not contain tests/test_pi_reconnect_e2e.py
- feature-only committed paths from merge base:
  - tests/test_terminal_ui.py
  - tests/test_pi_tui_e2e.py
- main-only paths are Markdown/Mermaid-owner files plus related tests/assets; no competing replay proof.

Pre-rebase SHA256 of tests/test_pi_reconnect_e2e.py:
dbc88f8b19dae5fd018fa083e5a6519732162832e231f8c3b6443b4b05837d15

Action:
- ran git rebase main
- no conflict
- no reset/stash/clean/merge/push
- no manual cross-owner resolution

Post-rebase:
- HEAD 18a8743003c19a719f000166c42c66197e6e80f7
- main 0eed7ed92dd758f64fbaecd8f958b568d29c9d32
- main...HEAD = 0/2
- rebased accepted commits:
  - 78a5b16 test(terminal): guard native xterm IME forwarding
  - 18a8743 test(pi): prove native TUI via TerminalManager
- feature diff relative to main remains exactly:
  - tests/test_terminal_ui.py
  - tests/test_pi_tui_e2e.py
- untracked replay proof SHA256 remained exactly dbc88f8b19dae5fd018fa083e5a6519732162832e231f8c3b6443b4b05837d15 immediately after rebase.

## Changed candidate

Uncommitted/untracked:
- tests/test_pi_reconnect_e2e.py

Ignored evidence:
- .plan/lantern-pi-native-20261018/evidence-turn10/pi-t003-candidates.json
- .plan/lantern-pi-native-20261018/evidence-turn10/full-unittest.{out,err,pid}

No production source or repository dependency file is dirty.

## Subtask 1 — exact vendored-browser snapshot round-trip

### Preserve failed headless representation

The prior real-Pi server-headless representation was converted from a positive assertion into an explicit negative characterization:
- @xterm/headless@6.0.0 + @xterm/addon-serialize@0.14.0
- accepted real Pi native WinConPty stream as input
- restore into exact static/vendor/xterm.js
- expected result: equal=false

Fresh evidence still reproduces:
- ref cursor 0,35; base/view 294/294
- reconstructed cursor 3,35; base/view 20/20
- exposed modes match
- equal=false

This history is preserved; it is not rewritten as a former PASS.

### New exact-client candidate

The new positive candidate is materially different:
1. load exact repository static/vendor/xterm.js in disposable headless Edge;
2. load temporary upstream @xterm/addon-serialize@0.14.0 directly into that same browser environment from %TEMP%\lantern-pi-replay-proof6;
3. create exact vendored reference terminal at canonical 120x40;
4. feed accepted real Pi native stream into that exact terminal;
5. attach SerializeAddon to that exact reference terminal;
6. serialize with scrollback=8000;
7. create a second exact vendored terminal at 120x40;
8. write only the browser-generated snapshot artifact;
9. compare the full established browser oracle.

No addon file was copied into the repository and no package/lock/vendor file was modified.

### Real Pi provenance asserted

The proof reuses accepted PI-T002 artifacts:
- evidence-turn4/pi-t002-g6-winconpty-raw.txt
- evidence-turn4/pi-t002-g6-winconpty.json

Assertions verify:
- argv contains --offline;
- argv targets installed @earendil-works/pi-coding-agent;
- stream contains real native Pi UI markers:
  - Auto-resize images
  - Resume Session (Current Folder)
  - New session started
  - Messages
  - Status:

No paid AI prompt was sent in this turn.

### TDD evidence

RED 1:
- added test_real_pi_exact_client_snapshot_round_trips with an unimplemented helper
- targeted run failed with explicit assertion:
  "exact vendored-browser snapshot candidate not implemented"

GREEN:
- implemented only the disposable proof harness
- targeted exact-client round-trip passed

Fresh exact-client result:
- serialize addon version: 0.14.0
- snapshot size: 14,223 bytes
- browser equal=true
- ref/recon geometry: 120x40
- ref/recon buffer: normal
- ref/recon cursor: 0,35
- ref/recon base/view: 294/294
- exposed modes equal
- full cells/styles/cursor/buffer/base/view/modes/geometry oracle equal

This establishes exact-client snapshot round-trip for the accepted real Pi stream at canonical geometry.

## Subtask 2 — snapshot + ordered delta and retention gap

### Snapshot + ordered delta

After Subtask 1 passed, the exact-client browser harness was extended.

TDD RED 2:
- test was extended to require a delta result;
- run failed with KeyError 'delta' before the browser harness produced one.

GREEN:
- after taking the browser-generated snapshot at canonical state, the continuously connected reference and fresh reconstructed terminal receive the same ordered post-snapshot chunks exactly once.

Delta intentionally includes:
- multiple chunks;
- an escape sequence split across chunk boundaries;
- styled text;
- explicit cursor movement;
- DEC 1049 alternate-screen enter/write/style/cursor/exit;
- bracketed-paste mode set;
- normal-screen continuation.

Fresh result:
- 8 ordered chunks
- equal=true
- ref/recon geometry 120x40
- ref/recon normal buffer after alt exit
- ref/recon cursor 10,1
- ref/recon base/view 294/294
- modes equal
- full oracle equal

The existing deterministic TerminalManager fixture remains and proves:
- one user input is written once;
- seq 1/2 precede replay boundary;
- seq 3/4 arrive after boundary;
- second replay retains ordered bytes through seq 4;
- generation stays stable;
- no input resend;
- resize remains manager/PTy-owned.

### Required bounded-retention gap result

The proof also characterizes the current public replay surface with:
- TerminalManager(max_output=8)
- snapshot boundary S=1
- post-boundary output chunk at seq=2 larger than retained capacity

Observed:
- replay_one() returns seq=2
- retained output is silently truncated to the last 8 characters: DEFGHIJK
- returned terminal metadata contains no:
  - outputOffset
  - oldestSeq
  - truncated marker

The internal TerminalEntry tracks output_offset, but replay_one() does not expose a public boundary marker that lets a detached client determine whether all bytes after snapshot sequence S are still retained.

Therefore the required long-detach/gap safety gate is **not satisfied**. A client can reconstruct exact short-detach state only while the complete post-S delta is available; current public replay metadata cannot safely distinguish that case from truncated retained output.

No production protocol was added to solve this because PLAN turn 6 explicitly forbids PI-T006/production snapshot protocol and unbounded duplicate history.

## PI-T003 disposition from DEV

- Current bounded raw-tail reset+write: NOT LOSSLESS.
- Server-headless serializer -> exact browser: FAIL/STOP representation.
- Exact vendored-browser snapshot -> exact vendored-browser restore at canonical geometry: PASS for tested real Pi state.
- Exact-client snapshot + complete ordered post-S delta: PASS for tested short-detach deterministic case.
- Different-width equivalence: remains false / geometry-scoped.
- Bounded post-snapshot delta gap detection with current public replay metadata: FAIL / BLOCKER.
- Full PI-T003: **PARTIAL, not PASS**.

Per PLAN decision rule, short-detach success without an acceptable long-detach/gap disposition is not sufficient to proceed into PI-T004/005/006.

## Verification actually run

### Enabled PI-T003 proof
Command:
LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e

Result:
- 6 tests
- OK
- 11.649s
- exit 0

Covers:
1. bounded raw-tail falsification / exact vendored synthetic state oracle
2. deterministic seq-boundary/no-input-resend manager proof
3. exact-client real-Pi snapshot + delta round-trip
4. preserved real-Pi headless-serializer mismatch
5. scoped xterm 6 synthetic serializer diagnostics
6. bounded-retention gap/no-public-marker characterization

### Ordinary gated replay test
With LANTERN_PI_REPLAY_E2E unset:
- 6 tests
- OK
- skipped=6
- exit 0

### Focused ordinary Terminal regressions
- test_terminal_scm.py: 15 tests, OK, 5.458s
- test_terminal_ui.py: 12 tests, OK, 3.066s

### Syntax / whitespace / repository
- uv run python -m py_compile tests\test_pi_reconnect_e2e.py -> exit 0
- git diff --check -> exit 0
- explicit trailing-whitespace scan of untracked test -> []
- package.json / uv.lock / package-lock.json worktree diff -> none

### Fresh full repository suite after rebase/proof
uv run python -m unittest discover -s tests -q
- 332 tests
- OK
- skipped=122
- 58.773s
- evidence stderr:
  .plan/lantern-pi-native-20261018/evidence-turn10/full-unittest.err
- existing ResourceWarning lines for implicit HTTPError cleanup appeared; no unittest failure

## Final repository state

Fresh:
- git status: only ?? tests/test_pi_reconnect_e2e.py
- HEAD 18a8743003c19a719f000166c42c66197e6e80f7
- main 0eed7ed92dd758f64fbaecd8f958b568d29c9d32
- main...HEAD = 0/2
- committed feature diff relative to main:
  - tests/test_pi_tui_e2e.py
  - tests/test_terminal_ui.py
- no production dirty path
- no PI-T003 commit made because full acceptance remains blocked by the retention-gap contract.

## Preserved NOT_MEASURED / INCOMPLETE boundaries

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt four-channel evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no terminal/IME product fix.

Spec 004:
- PI-T002 accepted/committed.
- PI-T003 exact-client short-detach representation is now proven, but full task remains PARTIAL due unsafe undetectable bounded-delta gap.
- browser F5/live Lantern WS reconnect: NOT_MEASURED.
- FJP physical IME/UniKey/AltGr/image paste: NOT_MEASURED.
- live /model, /goal, custom extension parity: incomplete.
- cursor visibility beyond exposed tested API: NOT_MEASURED.
- one-writer/multi-viewer/session isolation: not accepted.
- CPU/RSS/latency/resource acceptance: NOT_MEASURED.
- PI-T004/005/006+: not started.

## REVIEW request

Independent REVIEW must explicitly check:
- exact-client candidate truly serializes from the same exact vendored browser xterm that consumed real Pi output;
- no private xterm mutation/custom restore engine was used;
- full oracle remains strict;
- ordered delta/chunk/alt/style/cursor/mode proof is valid;
- existing manager test proves no input resend but not PI-T006 policy;
- bounded-retention gap characterization is correct and cannot silently be called PASS;
- no unbounded duplicate terminal history or production protocol was introduced;
- YAGNI/module ownership/scalability/geometry/native parity boundaries remain intact;
- fresh full suite and ordinary Terminal regressions are valid after rebase.

Expected disposition: PI-T003 PARTIAL with a remaining public replay-gap blocker; REVIEW should decide whether to route PLAN per turn-6 decision rules.

Route: REVIEW.

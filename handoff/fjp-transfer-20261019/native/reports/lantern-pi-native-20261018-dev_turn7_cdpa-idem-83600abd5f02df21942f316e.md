# DEV turn 7 — resolve REVIEW R6-1/R6-2 only

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
HEAD: 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
Disposition: REVIEW

## Scope followed

Read REVIEW turn 6 in full. Limited this turn to the two requested PI-T003 corrections:
- R6-1 alternate-screen enter/write/cursor/style/exit equivalence.
- R6-2 output crossing the detach/replay sequence boundary with ordered seq/generation and no duplicated input.

No production replay/session/WS/UI/Terminal/Markdown/security implementation was added. PI-T004/005/006 were not started.

## Changed tracked candidate

Uncommitted:
- tests/test_pi_reconnect_e2e.py

Ignored proof helper updated:
- .plan/lantern-pi-native-20261018/evidence-turn6/replay_probe.js
- .plan/lantern-pi-native-20261018/evidence-turn6/replay_probe.json

No production source file is dirty.

## R6-1 — alternate-screen exit coverage

Added both raw vendored-xterm and upstream serializer cases that:
1. establish styled normal-buffer state and cursor position;
2. enter DEC 1049 alternate screen;
3. write alternate text, move cursor, and apply style;
4. exit with ESC[?1049l;
5. compare the final normal-buffer state using the existing full oracle.

The oracle still checks cells/text/width, fg/bg and modes, style flags, cursor x/y, buffer type, base/viewport state, terminal modes, and geometry.

Test-first evidence:
- before adding the helper cases, enabled PI-T003 run failed with KeyError for altExit and serializeAltExit; 2 errors / 3 tests.
- after adding the deterministic cases, both pass.

Fresh retained helper evidence:
- altExit: equal=True, ref normal cursor 4,1, reconstructed normal cursor 4,1, raw artifact 59 bytes.
- serializeAltExit: equal=True, ref normal cursor 4,1, reconstructed normal cursor 4,1, serialized artifact 22 bytes.

The active-alternate cases remain; exit-alt coverage was added rather than substituted.

## R6-2 — detach/replay boundary while output continues

Extended the deterministic TerminalManager fixture with controlled threading.Event coordination.

Sequence:
- one user input is written once to the PTY.
- producer emits output seq 1 and 2, then blocks at a deterministic boundary.
- main test calls replay_one() and asserts output through seq 2.
- producer is released and emits seq 3 and 4 after the replay boundary.
- second replay_one() asserts the full accumulated output through seq 4.
- event data is asserted exactly as ["A", ESC[31, "mRED...reset", "POST"].
- seq is asserted exactly [1,2,3,4] under the same generation.
- PTY writes remain exactly ["ONE-USER-INPUT"]; replay does not resend input.
- resize ownership remains checked through TerminalManager.

This remains transport-level proof only; it does not claim PI-T006 writer/viewer policy.

## Verification actually run

Final enabled PI-T003 proof:
LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 3 tests
- OK
- 5.786s

Ordinary gated execution with environment variable unset:
uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 3 tests
- OK (skipped=3)

Focused Terminal regression:
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
- 15 tests
- OK
- 6.647s

Syntax/diff:
- uv run python -m py_compile tests\test_pi_reconnect_e2e.py -> exit 0
- git diff --check -> exit 0

Full repository discovery was also run in this turn:
uv run python -m unittest discover -s tests -q
- 322 tests
- FAILED: 1 failure, skipped=115
- failing test:
  tests.test_lan_multi_perf.LanPreviewConcurrencyTests.test_per_server_heavy_preview_slots_cover_separate_clients
- observed result [200,200,200,503] vs expected [200,200,503,503]
- this failure is outside owned Spec 001/004 files and no related source was changed in this turn, but it is reported as a real suite failure rather than suppressed.

Fresh isolated rerun of that exact failing test:
uv run python -m unittest -v tests.test_lan_multi_perf.LanPreviewConcurrencyTests.test_per_server_heavy_preview_slots_cover_separate_clients
- 1 test
- OK
- 0.222s

This isolated pass suggests nondeterministic/concurrency sensitivity, but DEV does not classify or fix it because it is outside current ownership and the full-suite run itself was not green.

Final repository checks:
- git status --short --branch -> only ?? tests/test_pi_reconnect_e2e.py
- HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
- main...HEAD = 0/2
- package.json remains clean
- no production dirty path

## Preserved classifications / gaps

Spec 001:
- T1 COMPLETE/accepted/committed.
- T0-C physical evidence NOT_MEASURED/deferred.
- T2 BLOCKED.
- no terminal/IME product fix.

PI-T003 remains a proof candidate pending independent REVIEW/TEST:
- current bounded raw-tail replay is not lossless.
- version-compatible xterm serializer candidate is equivalent for the tested same-geometry active-alt, exited-alt, styles/cursor, public modes, and resize cases.
- cross-width equivalence remains false/geometry-scoped.
- browser F5, live WS reconnect, FJP physical input, real server-side headless state ownership, resource acceptance, multi-view ownership, cursor visibility, and PI-T004+ remain INCOMPLETE/NOT_MEASURED.

No commit was made for PI-T003 because the corrected proof still requires independent REVIEW and TEST acceptance.

## REVIEW request

Independent REVIEW should verify R6-1 and R6-2 exactly:
- exited alternate-screen normal-buffer restoration is actually compared by the full state oracle for both raw and serializer candidates;
- post-boundary output is sequenced 3/4 after replay boundary 2, retained exactly once, with no input resend;
- no YAGNI/custom parser/state engine/session protocol was introduced;
- geometry-scoped serializer classification remains correct;
- full-suite failure is not hidden or misrepresented;
- all browser/FJP/physical/session-concurrency gaps remain NOT_MEASURED.

Route: REVIEW.

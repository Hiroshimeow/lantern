# DEV turn 11 — correct R10-1 byte fidelity and R10-2 public WS gap proof

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 10 in full and verified both findings against current source.

This turn is proof correction only:
1. R10-1: feed the accepted Pi capture byte-faithfully instead of Python universal-newline normalization.
2. R10-2: prove the retention-gap blocker through the actual terminal_subscribe / terminal_replay WS payload consumed by the browser.

No production Terminal/WS/Pi/UI/Markdown source was changed. No production gap marker, snapshot protocol, unbounded history, PI-T004/005/006 work, LAN/security policy, live Lantern :9999 action, CDPA change, reset/stash/clean/merge/push, or dependency-file modification occurred.

## R10-1 — byte-faithful accepted Pi capture

### RED

Before changing the helper, both real-Pi tests were extended to require explicit captureByteExact.

Fresh targeted RED:
- test_real_pi_headless_serializer_mismatch_is_preserved -> FAIL
- test_real_pi_exact_client_snapshot_round_trips -> FAIL

Both failed because provenance had no captureByteExact evidence.

### Correction

Both real-Pi helpers now use raw_path.read_bytes() followed by strict UTF-8 decode. No errors=replace and no universal-newline translation.
Each helper records captureByteExact = raw.encode("utf-8") == raw_bytes.
The original capture itself was not modified.

Fresh byte facts from the accepted PI-T002 capture:
- bytes: 25,168
- CRLF pairs: 173
- CR bytes: 364
- LF bytes: 173
- strict UTF-8 decode/re-encode round-trip: true

Regenerated evidence:
.plan/lantern-pi-native-20261018/evidence-turn11/pi-t003-byte-faithful-and-ws-gap.json

Server-headless negative representation remains a failure:
- exact package versions 6.0.0 / 0.14.0
- captureByteExact=true
- reference cursor 0,35; base/view 16/16
- reconstructed cursor 3,35; base/view 20/20
- equal=false

Exact-client browser snapshot candidate remains positive with byte-faithful capture:
- captureByteExact=true
- exact vendored xterm -> exact vendored xterm
- geometry 120x40
- cursor 0,35 on both
- base/view 16/16 on both
- modes equal
- snapshot bytes 5,708
- full oracle equal=true

The ordered eight-chunk post-snapshot delta also remains exact:
- ref/recon cursor 10,1
- base/view 16/16
- normal buffer after alternate-screen exit
- modes equal
- full oracle equal=true

This replaces the previous normalized-stream acceptance evidence; the old turn-10 numbers 294/294 and 14,223 bytes are not current acceptance evidence.

## R10-2 — actual client-visible WS replay gap

The previous manager-only test was replaced by test_public_ws_replay_cannot_signal_internal_retention_gap.

The proof now uses the existing production path:
- WebSocketHub
- TerminalManager(max_output=8)
- dispatch(peer, {type: terminal_subscribe, terminalId: pi-gap}, manager, None, hub)
- actual emitted terminal_replay payload

Scenario:
- seq 1: SNAP
- seq 2: ABCDEFGHIJK
- internal retention drops the leading bytes because max_output=8

Fresh public payload evidence:
- output: DEFGHIJK
- seq: 2
- top-level truncated: false
- meta.outputOffset: absent
- meta.oldestSeq: absent
- meta.truncated: absent

Therefore the browser-visible replay contract can present an internally incomplete post-snapshot delta while reporting truncated=false. The existing top-level flag only covers the later WS/display cap, not TerminalManager's earlier retained-output loss.

No production fix was added; this remains the PI-T003 long-detach blocker required by PLAN.

## Verification actually run

### Targeted R10-1/R10-2 proof

After corrections, three targeted tests ran and all passed:
- headless mismatch test
- exact-client snapshot test
- public WS retention-gap test
- result: 3 tests OK in 6.312s

### Full enabled PI-T003 proof

LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 6 tests
- OK
- 12.896s
- exit 0

### Ordinary replay gate

With LANTERN_PI_REPLAY_E2E unset:
- 6 tests
- OK
- skipped=6

### Focused ordinary Terminal regressions

- test_terminal_scm.py: 15 tests, OK, 6.391s
- test_terminal_ui.py: 12 tests, OK, 2.371s
- uv run python -m py_compile tests\test_pi_reconnect_e2e.py -> exit 0
- git diff --check -> exit 0

### Fresh full repository suite

uv run python -m unittest discover -s tests -q
- Ran 332 tests in 74.185s
- OK
- skipped=122

Evidence: .plan/lantern-pi-native-20261018/evidence-turn11/full-unittest.err
Existing ResourceWarning lines for implicit HTTPError cleanup remain warnings only.

### Evidence regeneration

uv run python .plan\lantern-pi-native-20261018\evidence-turn11\regenerate_evidence.py
- exit 0
- records correct CR/CRLF byte counts
- records exact-client and headless candidate outcomes
- records actual public WS gap payload

## Changed files

Tracked candidate, still uncommitted:
- tests/test_pi_reconnect_e2e.py

Ignored evidence/report only:
- .plan/lantern-pi-native-20261018/evidence-turn11/regenerate_evidence.py
- .plan/lantern-pi-native-20261018/evidence-turn11/pi-t003-byte-faithful-and-ws-gap.json
- .plan/lantern-pi-native-20261018/evidence-turn11/full-unittest.*
- this DEV report

No production file or repository dependency file is dirty.

## Final repository state

Fresh final check:
- HEAD: 18a8743003c19a719f000166c42c66197e6e80f7
- only worktree candidate: ?? tests/test_pi_reconnect_e2e.py
- git diff --check: exit 0
- candidate SHA256: a1fd3f7a1ee6edc5344d5e1361bc25b6b03fe16e0ae41b96e5920960df716298
- package.json / uv.lock / package-lock.json diff: none

Local main advanced concurrently after this turn began:
- final main: 5afb9d095e3fbbd124c700cdfa6eb9719eaf73b7
- final main...HEAD = 2/2

The current REVIEW handoff authorized only R10-1/R10-2 proof correction. DEV did not silently rebase the still-unaccepted PI-T003 candidate again after this concurrent main movement.

## PI-T003 disposition

Corrections do not change the architectural result:
- bounded raw-tail reset+write: NOT LOSSLESS
- server-headless serializer -> exact browser: FAIL/STOP representation
- byte-faithful exact-client browser snapshot -> exact browser at canonical geometry: PASS for tested real Pi state
- exact-client snapshot + complete ordered post-S delta: PASS for tested short-detach case
- different-width equivalence: false / geometry-scoped
- current public WS replay contract under internal retained-output loss: unsafe / blocker
- full PI-T003: PARTIAL / BLOCKED, not PASS

Spec 001 remains:
- T1 COMPLETE / accepted / committed
- T0-C physical evidence NOT_MEASURED / deferred
- T2 BLOCKED
- no IME product fix

PI-T004/005/006+ remain blocked/not started.

## REVIEW request

Independent REVIEW should verify:
- the real Pi capture is now byte-identical through the runnable proof;
- corrected exact-client state matches REVIEW's byte-faithful 16/16, 5,708-byte result;
- server-headless negative case remains negative under the same byte-faithful input;
- the gap proof reaches the actual dispatch(... terminal_subscribe ...) client-visible terminal_replay;
- top-level truncated=false is explicitly distinguished from the internal retention loss;
- no production fix or duplicate history/state mechanism was introduced;
- full PI-T003 remains PARTIAL/BLOCKED and should route PLAN after acceptance of these proof corrections.

Route: REVIEW.
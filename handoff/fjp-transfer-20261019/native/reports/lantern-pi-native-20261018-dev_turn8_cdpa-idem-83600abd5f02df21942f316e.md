# DEV turn 8 — correct R7-1 with exact scoped xterm 6.0.0 serializer proof

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
HEAD: 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
Disposition: REVIEW

## Scope followed

Read REVIEW turn 7 in full. Limited this turn to R7-1 only:
- preserve all accepted raw-tail falsification and R6-1/R6-2 stress cases;
- replace the temporary legacy xterm 5.x serializer feasibility environment with the exact scoped xterm 6.0.0 family;
- rerun the same oracle.

No PI-T004/005/006 implementation, production replay/session service, WS change, UI work, Terminal product change, Markdown implementation, dependency-file change, LAN/security policy, or Spec 001 IME fix was added.

## Exact upstream package correction

Fresh registry/install evidence:
- @xterm/headless@6.0.0 installed under %TEMP%\lantern-pi-replay-proof6
- @xterm/addon-serialize@0.14.0 installed under the same disposable temp directory
- @xterm/xterm@6.0.0 registry version verified
- node package inspection returned:
  - headless = 6.0.0
  - addon-serialize = 0.14.0

No repository package.json, uv.lock, package-lock.json, or vendored xterm file was changed.

Updated ignored helper imports:
- require('@xterm/headless')
- require('@xterm/addon-serialize')

Updated tests/test_pi_reconnect_e2e.py:
- test documentation now names @xterm/headless@6.0.0 + @xterm/addon-serialize@0.14.0
- temporary module path now points to %TEMP%\lantern-pi-replay-proof6\node_modules
- availability check targets scoped @xterm directories
- serializer test now asserts the helper-reported versions exactly equal:
  {"headless": "6.0.0", "serialize": "0.14.0"}

The helper now emits those exact package versions in its result so a stale/wrong package family cannot silently satisfy the serializer acceptance test.

## Version-matched xterm 6.0.0 serializer results

Fresh direct helper run with NODE_PATH pointing only at the scoped xterm 6 temp environment:

- serializeAlt:
  - equal=True
  - ref alternate 20x6 cursor 5,1
  - reconstructed alternate 20x6 cursor 5,1
  - serialized artifact 31 bytes

- serializeAltExit:
  - equal=True
  - ref normal 20x6 cursor 4,1
  - reconstructed normal 20x6 cursor 4,1
  - serialized artifact 22 bytes

- serializeStyle:
  - equal=True
  - ref normal 20x6 cursor 4,1
  - reconstructed normal 20x6 cursor 4,1
  - 23 bytes

- serializeModes:
  - equal=True
  - ref/reconstructed normal 20x6 cursor 4,0
  - tested public modes remain equivalent
  - 25 bytes

- serializeResize:
  - equal=True
  - ref/reconstructed normal 16x6 cursor 4,2
  - 26 bytes

- serializeWidth:
  - equal=False
  - ref 12x6 cursor 3,2
  - reconstructed 20x6 cursor 3,1
  - geometry-scoped limitation remains proven

The helper emitted a jsdom canvas "Not implemented: HTMLCanvasElement.getContext" warning while exiting 0. The tested headless buffer/serializer state comparisons completed successfully; no canvas/image-render acceptance is inferred from this run.

PI-T003 serializer candidate classification remains:
- PASS candidate for the tested same-geometry xterm 6.0.0 state cases.
- FAIL for arbitrary-width equivalence.
- current raw bounded-tail replay remains not lossless.
- this is feasibility evidence only; no production snapshot owner was implemented.

## Fresh verification

Enabled PI-T003 proof after the exact-version assertion was added:
LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 3 tests
- OK
- 6.150s

The same test still covers:
- exact vendored browser xterm raw-tail falsification
- active alternate screen
- alternate enter/write/style/cursor/exit restoration
- style/cursor/erase
- modes
- resize
- different-width falsification
- deterministic output crossing replay boundary with seq/generation continuity and no input resend
- exact scoped serializer package versions

Ordinary gated execution:
uv run python -m unittest -v tests.test_pi_reconnect_e2e
- 3 tests
- skipped=3 with explicit environment gate
- exit 0

Focused terminal regression:
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
- 15 tests
- OK
- 5.420s

Syntax/diff:
- uv run python -m py_compile tests\test_pi_reconnect_e2e.py -> exit 0
- git diff --check -> exit 0

Fresh full repository suite after final exact-version assertion:
uv run python -m unittest discover -s tests -q
- Ran 322 tests in 84.203s
- OK (skipped=115)
- stderr retained at:
  .plan/lantern-pi-native-20261018/evidence-turn6/turn8-final-full-unittest.err
- same existing ResourceWarning lines for implicit HTTPError cleanup appeared; no unittest failure

## Repository state / preservation

Final status:
- only untracked tracked-candidate path:
  ?? tests/test_pi_reconnect_e2e.py
- no production source dirty path
- package.json / uv.lock / package-lock.json diff: none
- HEAD remains 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
- no PI-T003 commit made pending independent acceptance

Local main advanced externally during this turn:
- main = 1e3b77cda8d1d7e31019ccc79c38a6f63516817b
- main...HEAD = 1/2

The current REVIEW handoff authorized only the R7-1 proof correction, not housekeeping/rebase of an unaccepted PI-T003 candidate, so DEV did not rebase or otherwise alter branch history. No reset/stash/clean/merge/push was used.

## Preserved incomplete / NOT_MEASURED boundaries

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt four-channel evidence remains NOT_MEASURED / deferred.
- T2 remains BLOCKED.
- no Terminal/IME product fix.

Spec 004 / PI:
- browser F5 against a live disposable Lantern WS server: NOT_MEASURED
- live browser xterm -> WS -> TerminalManager -> Pi reconnect: NOT_MEASURED
- production server-side headless xterm snapshot owner: not implemented
- FJP physical IME/UniKey/AltGr/image paste: NOT_MEASURED
- live /model, /goal, custom extension parity: incomplete
- one-writer/multi-viewer/session ownership: not accepted
- arbitrary-width snapshot equivalence: disproven
- cursor visibility beyond exposed tested API: NOT_MEASURED
- CPU/RSS/latency/resource acceptance: NOT_MEASURED
- PI-T004/005/006+: not started

## REVIEW request

Independent REVIEW should verify:
- R7-1 is resolved with the exact scoped xterm 6.0.0 family;
- the test now fails closed on stale/wrong serializer package versions;
- all prior R6-1/R6-2 cases remain unchanged and passing;
- same-geometry equivalence / cross-width failure is still correctly classified;
- temporary packages remain outside the repository dependency graph;
- no custom parser/state engine, replay service, registry, protocol, transcript/history store, or production abstraction was added;
- local main drift is reported but not silently rebased into the unaccepted proof;
- browser/FJP/physical/session-concurrency/resource gaps remain honestly NOT_MEASURED/INCOMPLETE.

No commit was made for PI-T003 because independent REVIEW/TEST acceptance is still required.

Route: REVIEW.

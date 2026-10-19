# DEV turn 9 — real Pi cross-stack replay proof => PI-T003 FAIL/STOP

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
HEAD: 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
Disposition: REVIEW

## Scope followed

Read REVIEW turn 8 in full. Limited this turn to the two linked PI-T003 proof gaps:
- R8-1: exercise a real native Pi stream.
- R8-2: restore the scoped xterm 6 headless serializer artifact into Lantern's exact vendored browser xterm and compare the full oracle.

No PI-T004/005/006 work, production replay/session/WS code, registry, bot UI, Terminal product change, Markdown implementation, dependency-file change, LAN/security policy, or Spec 001 IME fix was started.

## Real Pi provenance used

Reused the already accepted PI-T002 capture:
- .plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty-raw.txt
- .plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty.json

Provenance assertions in the new runnable proof verify:
- argv contains --offline
- argv points to installed @earendil-works/pi-coding-agent
- retained stream contains real native Pi UI markers:
  - Auto-resize images
  - Resume Session (Current Folder)
  - New session started
  - Messages
  - Status:

No paid AI prompt was sent in this turn.

## Test-first evidence

Added a new gated acceptance case in tests/test_pi_reconnect_e2e.py:
test_real_pi_native_stream_serializes_into_exact_vendored_xterm

Initial RED before implementation:
- 1 test
- FAIL
- explicit "real Pi -> headless serializer -> vendored xterm proof not implemented"

Then implemented the smallest proof-only path.

## Cross-stack proof mechanism

The proof:
1. reads the accepted real Pi WinConPty stream;
2. feeds it at canonical 120x40 geometry into temporary @xterm/headless@6.0.0;
3. serializes with temporary @xterm/addon-serialize@0.14.0 using scrollback=8000;
4. loads the repository's exact static/vendor/xterm.js in disposable headless Edge;
5. creates two exact vendored browser terminals at 120x40:
   - reference: writes the original real Pi raw stream;
   - reconstruction: writes the headless serializer artifact;
6. compares the same full browser oracle:
   - cells/chars and cell width
   - fg/bg values and color modes
   - style flags
   - cursor x/y
   - active buffer type
   - base/viewport
   - exposed terminal modes
   - geometry.

The temporary scoped xterm packages remain outside the repository under %TEMP%\lantern-pi-replay-proof6.

The serializer documentation/source was checked after the failure:
- serialize({scrollback:N}) serializes up to N available scrollback rows;
- the proof already requests 8000 rows, so this is not a missing-option misuse.

## Required real-Pi cross-stack result

The required acceptance case FAILS.

Fresh artifact:
.plan/lantern-pi-native-20261018/evidence-turn9/pi-t003-real-pi-cross-stack.json

Exact package versions:
- headless: 6.0.0
- serialize: 0.14.0

Provenance:
- offline=true
- nativePiCli=true
- nativeUiMarkers=true

Exact vendored-browser comparison:
- equal=false

Reference from original real Pi raw stream:
- geometry 120x40
- buffer normal
- cursor x=0 y=35
- base=294
- viewport=294
- bracketedPasteMode=true
- sendFocusMode=true
- other recorded modes match the reconstruction

Reconstruction from headless serializer artifact:
- geometry 120x40
- buffer normal
- cursor x=3 y=35
- base=20
- viewport=20
- recorded modes match the reference

Therefore the serializer artifact does not reproduce the exact vendored-browser terminal state for the real Pi capture, even at the same canonical geometry.

Per REVIEW turn 8's explicit rule:
- PI-T003 is **FAIL/STOP**
- do not fall back to synthetic headless-to-headless success
- do not promote the mature serializer candidate as lossless for Lantern's real Pi stream.

## Existing synthetic/transport evidence preserved

The earlier synthetic tests still establish:
- bounded raw-tail replay is not lossless;
- different-width reconstruction is not equivalent;
- active-alt and exited-alt synthetic states can serialize/reconstruct in tested synthetic cases;
- tested style/cursor/modes/resize synthetic cases pass;
- output can cross a deterministic replay boundary with seq continuity and no duplicated input.

Those results remain useful diagnostics only. They do not override the real-Pi cross-stack failure.

## Verification actually run

Enabled PI-T003 suite after the real-Pi proof was implemented:
LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e

Result:
- 4 tests total
- 3 PASS
- 1 FAIL
- failing test: test_real_pi_native_stream_serializes_into_exact_vendored_xterm
- failure is the required equal=false cross-stack result
- enabled suite exit code 1

Ordinary gated execution with LANTERN_PI_REPLAY_E2E unset:
- 4 tests
- OK
- skipped=4

Focused ordinary Terminal regression:
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
- 15 tests
- OK
- 4.770s

Syntax/diff:
- uv run python -m py_compile tests\test_pi_reconnect_e2e.py -> exit 0
- git diff --check -> exit 0

Fresh ordinary full repository suite with replay gate unset:
uv run python -m unittest discover -s tests -q
- 323 tests
- OK
- skipped=116
- 57.045s
- retained stderr:
  .plan/lantern-pi-native-20261018/evidence-turn9/full-unittest.err
- existing ResourceWarning HTTPError cleanup lines remain warnings only.

## Repository state

Fresh final state:
- branch feat/lantern-bot...origin/feat/lantern-bot [ahead 4]
- only untracked candidate: tests/test_pi_reconnect_e2e.py
- no production source dirty path
- package.json / uv.lock / package-lock.json diff: none
- HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863
- main = 1e3b77cda8d1d7e31019ccc79c38a6f63516817b
- main...HEAD = 1/2

No commit was made because PI-T003 acceptance fails and requires PLAN/REVIEW disposition.

## Preserved boundaries / NOT_MEASURED

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt four-channel evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no Terminal/IME product fix.

Spec 004:
- PI-T002 remains accepted/committed.
- PI-T003 current raw-tail replay remains not lossless.
- PI-T003 scoped serializer candidate now FAILS the required real-Pi -> exact vendored-browser equivalence gate.
- browser F5/live WS reconnect remains NOT_MEASURED.
- FJP physical IME/UniKey/AltGr/image paste remains NOT_MEASURED.
- live /model, /goal, custom extension parity remains incomplete.
- session writer/viewer ownership and PI-T004+ remain unimplemented.
- arbitrary-width equivalence remains disproven.
- cursor visibility beyond exposed tested state remains NOT_MEASURED.
- CPU/RSS/latency/resource acceptance remains NOT_MEASURED.

## REVIEW request

Independent REVIEW should verify:
- accepted PI-T002 provenance is actually used;
- scoped xterm 6.0.0 headless serializer is restored into exact static/vendor/xterm.js;
- the browser oracle compares full state, not text only;
- the equal=false result and cursor/base/viewport mismatch reproduce;
- serializer scrollback option was not accidentally omitted;
- PI-T003 is correctly classified FAIL/STOP instead of being hidden by synthetic success;
- no PI-T004/005/006 or production workaround was started.

Route: REVIEW.

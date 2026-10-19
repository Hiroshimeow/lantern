# DEV turn 5 — correct REVIEW R4-1/R4-2 with TerminalManager-backed runnable PI-T002 proof

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Known HEAD before this turn: c1ee6cc0d128451304172c84ec00574117091850
Disposition: REVIEW

## Review findings verified

Read REVIEW turn 4 in full and re-inspected TerminalManager/WinConPty plus the existing pty_factory injection pattern.

R4-1 is technically valid:
- TerminalManager.__init__ accepts pty_factory.
- TerminalManager.create delegates spawn ownership to that factory.
- A factory closure can instantiate the real production WinConPty with structured Pi argv.
- Therefore the future public production argv/env spawn API is still absent, but that PI-T005 product seam does not block the PI-T002 proof.

R4-2 is technically valid:
- tests/test_pi_tui_e2e.py did not exist.
- The prior ignored probe was evidence, not an acceptance-bearing runnable test.

No production code change was required.

## Tracked change

Added:
- tests/test_pi_tui_e2e.py

No production source file was edited.

The test is explicitly gated:
- Windows only.
- LANTERN_PI_TUI_E2E=1 required.
- Ordinary suite execution therefore skips the native environment-dependent proof rather than fabricating a pass.

## TerminalManager-backed proof

The test constructs:
TerminalManager(root, events.append, pty_factory=factory)

The injected factory:
- asserts command is None, so Pi is not passed through the manager's shell command-string path;
- instantiates production WinConPty with a structured argv list for installed Pi 1.3.0;
- uses disposable cwd and session-dir;
- launches with --offline --approve --no-mcp --session-dir --session-id --tui-mode regular.

All runtime interaction is then driven through TerminalManager owners:
- create()
- input()
- resize()
- replay_one()
- list()
- kill()

Assertions are deliberately limited to measurable PI-T002 behavior:
- manager-created terminal is running and has generation metadata;
- no -Command or /C shell wrapper appears in Pi argv;
- native /settings selector renders and includes settings rows;
- native /resume selector renders;
- !!echo PI_NATIVE_SHELL_PROOF produces both displayed local command and separate shell output marker;
- bracketed paste containing Japanese/Vietnamese/emoji is retained;
- direct Unicode editor text is retained;
- Alt bytes and Ctrl+C are routed without claiming semantic physical-key parity;
- /new reports native new-session transition;
- /session renders native Messages/Tools/Status content;
- manager resize updates 100x32 -> 120x40 metadata;
- replay_one preserves generation, nonzero seq, and retained output;
- emitted terminal_output events carry the manager generation and unique monotonic seq values;
- explicit manager.kill cleans up the terminal and emits terminal_exit.

Not asserted:
- live browser/xterm -> WS -> TerminalManager path;
- PI-T003 reconnect/replay semantics;
- /model provider picker;
- /goal;
- custom extension UI;
- physical IME/UniKey/AltGr/image paste;
- alternate-screen parity;
- multi-view/session concurrency;
- resource acceptance.

## Characterization-test iteration

Initial enabled test run:
LANTERN_PI_TUI_E2E=1 uv run python -m unittest -v tests.test_pi_tui_e2e

Result: FAIL after 18.542s at /resume.

Evidence showed /resume had been typed into the still-open /settings search field immediately after Escape. This was a test synchronization defect, not a product defect. The test was corrected only by adding a 0.5s settle after exiting settings and resume selectors. No production behavior was changed.

Second enabled run:
- 1 test
- OK
- 10.318s

This is a characterization test of existing behavior rather than a new production behavior TDD cycle; the failure was retained as evidence that the first test sequence was invalid.

## Durable evidence correction

Updated:
- .plan/lantern-pi-native-20261018/evidence-turn4/pi-t001-fjp-pi-t002-poc.md
- .plan/lantern-pi-native-20261018/lantern-pi-native-20261018-dev_turn4_cdpa-idem-83600abd5f02df21942f316e.md

The durable evidence now states:
- TerminalManager ownership proof is possible through existing pty_factory injection.
- The runnable test uses TerminalManager with real WinConPty and structured native Pi argv.
- The future public production structured argv/env seam remains PI-T005 and was not started.
- Prior turn-4 stop-condition wording is explicitly marked as superseded by R4-1/R4-2 correction.

## Verification actually run

### Native PI-T002 proof
Command:
$env:LANTERN_PI_TUI_E2E='1'; uv run python -m unittest -v tests.test_pi_tui_e2e

Result:
- 1 test
- OK
- 10.318s

### Normal-suite gate behavior
Command:
uv run python -m unittest -v tests.test_pi_tui_e2e
with LANTERN_PI_TUI_E2E unset

Result:
- 1 test
- OK
- skipped=1 with explicit environment-gate reason

### Focused normal Terminal regressions
- uv run python -m unittest discover -s tests -p test_terminal_ui.py -q
  - 12 tests, OK
- uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
  - 15 tests, OK

### Syntax/diff checks
- uv run python -m py_compile tests\test_pi_tui_e2e.py
  - exit 0
- git diff --check
  - exit 0 on the completed successful check before the long full-suite attempt

### Full repository unittest discovery
Because direct long shell calls exceeded the device request window, the full suite was launched with output redirected to ignored evidence files:
- .plan/lantern-pi-native-20261018/evidence-turn4/turn5-full-unittest.out
- .plan/lantern-pi-native-20261018/evidence-turn4/turn5-full-unittest.err

Fresh completion evidence in stderr:
- Ran 319 tests in 122.049s
- OK (skipped=112)

The full run also emitted ResourceWarning lines for implicitly cleaned-up HTTPError objects with 404, 400, 403 Origin mismatch, and 409. These were warnings, not unittest failures; they are preserved in the evidence file rather than omitted.

A later combined verification command and later quick git-status commands hit the device broker timeout and returned no result, so they are not claimed as successful checks. The last successful tracked-state observation in this turn showed:
- branch feat/lantern-bot...origin/feat/lantern-bot [ahead 3]
- only new tracked-worktree path: ?? tests/test_pi_tui_e2e.py
- no production source dirty path

No commit was made because this correction has not yet been independently accepted.

## Scope/invariants preserved

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical >=50-attempt evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- No IME fix or terminal production input change.

Spec 004:
- PI-T001 FJP exact CLI/package/config/source baseline remains valid.
- PI-T002 now has a TerminalManager-owned real WinConPty runnable proof.
- PI-T002 remains partial: browser/WS/FJP physical/native parity acceptance is not promoted.
- PI-T003 was not started.
- PI-T004+ registry/session/WS ownership was not started.
- PI-T005 public structured-spawn product seam was not started.
- No legacy HTML UI replacement or transcript work was started.

No Markdown fidelity/diff/Crop/Milkdown implementation, LAN/security policy, dependency installation, reset/stash/clean/merge/push, live Lantern :9999 restart, or CDPA modification/reload occurred.

## REVIEW request

Independent REVIEW must explicitly check:
- R4-1 is resolved by existing TerminalManager pty_factory ownership, without production seam expansion;
- R4-2 is resolved by a genuine runnable tests/test_pi_tui_e2e.py;
- test assertions match only measured native behavior and do not overclaim physical/browser/reconnect/session-concurrency acceptance;
- YAGNI/over-engineering: no new production abstraction, ANSI parser, terminal service, protocol, catalog, registry, or compatibility shim;
- scope drift: no Markdown, LAN/security, PI-T003+, or UI implementation;
- UX/native parity: native selectors/session UI are real Pi surfaces but PI-T016 remains incomplete;
- maintainability/module ownership: TerminalManager remains host owner and WinConPty remains PTY owner;
- scalability/extensibility/session isolation remain future gates, not inferred here;
- regression/performance: full unittest suite is green but resource/performance acceptance remains NOT_MEASURED;
- whether the proof is sufficient to route independent TEST before PLAN decides PI-T003.

Route: REVIEW.

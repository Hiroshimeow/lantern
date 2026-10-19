# DEV turn 18 — fix T8-1 contextRef pre-spawn failure atomicity

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read TEST turn 8 and fixed only T8-1.

Authorized files touched:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

Existing PI-T004 candidate changes in lantern/terminal.py and tests/test_terminal_scm.py were preserved unchanged this turn.

Not started:
- PI-T006/007;
- WS/frontend/application wiring;
- persistence/supervisor work;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/security changes;
- Lantern :9999 action;
- CDPA action.

## T8-1 reproduction / TDD RED

Added `test_context_snapshot_failure_happens_before_session_dir_or_spawn` using a standard read-only `MappingProxyType({"path":"file.md"})` context.

Fresh RED before production correction:
- test raised TypeError as expected from deepcopy(mappingproxy);
- but FakeTerminalManager recorded one created `pi:ctxFail` terminal;
- therefore the failure still occurred after native spawn ownership began.

Exact RED result: 1 test, FAIL.

## Production correction

`PiSessionRegistry.create()` now performs `context_snapshot = deepcopy(context_ref)` before:
- generating/claiming the session directory;
- checking/creating terminal ownership;
- calling TerminalManager.create_argv().

The later session record stores this already-created `context_snapshot` instead of deep-copying the caller object after successful spawn.

Resulting ownership rule:
- if context snapshot/validation raises, no session directory exists and no PTY spawn is attempted;
- successful contexts retain the existing defensive-copy behavior;
- the original TypeError is preserved;
- no new cleanup framework or generation rollback path was added because pre-spawn validation is the smaller root-cause fix.

## Verification actually run

Fresh targeted GREEN:
- `uv run python -m unittest -v tests.test_pi_sessions.PiSessionRegistryTests.test_context_snapshot_failure_happens_before_session_dir_or_spawn`
- 1 test OK in 0.004s

Registry suite:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 9 tests OK in 0.033s

Terminal regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.428s

Syntax/diff:
- `uv run python -m py_compile lantern\pi_sessions.py tests\test_pi_sessions.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 374 tests in 55.403s
- OK (skipped=134)
- existing ResourceWarning HTTPError cleanup lines only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn18/full-unittest.err`

## Changed files

Turn-18 direct changes:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

Preserved unaccepted PI-T004 candidate paths from prior turns:
- M lantern/terminal.py
- M tests/test_terminal_scm.py
- ?? lantern/pi_sessions.py
- ?? tests/test_pi_sessions.py

No package/lock/vendor, Markdown-owner, WS/browser/application, or unrelated path is dirty.

## Final repository state

Fresh final check:
- HEAD: 1282490f8bd1443b547c3b64b0b26813270ff837
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/5
- `git diff --check`: exit 0

No PI-T004 commit was made because the corrected registry slice still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate;
- PI-T005 COMPLETE / accepted / committed;
- PI-T004 corrected REVIEW candidate;
- PI-T006/007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- browser attach/F5/live WS behavior;
- writer/viewer/takeover/resize ownership;
- restart persistence;
- FJP physical input;
- real POSIX runtime process execution;
- live model/goal/extensions parity;
- CPU/RSS/latency/resource acceptance.

## REVIEW request

Independent REVIEW should verify T8-1 specifically:
- unsupported/deepcopy-failing context mappings fail before session directory or PTY creation;
- supported contexts still receive defensive nested copies;
- no registry/session/terminal ownership remains on snapshot failure;
- existing TerminalManager post-publication rollback and generation-safe stop/close remain intact;
- no PI-T006/007 or process-framework scope creep;
- focused/full regression evidence is valid.

Route: REVIEW.
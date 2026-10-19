# DEV turn 35 — R34-1 implementation started; test source recovery required

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: DEV

## Scope followed

Read REVIEW turn 34 and worked only R34-1.

Production change in progress:
- lantern/ws.py

Test work in progress:
- tests/test_pi_ws_contract.py

No PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA changes were started.

## R34-1 TDD RED

Added deterministic regression for replay/live-output ordering:
`test_attach_replay_precedes_live_output_after_capture_without_gap_or_duplicate`.

Fresh RED before production correction:
- observed message order was `[pi_session_output, pi_session_replay]`;
- expected `[pi_session_replay, pi_session_output]`;
- confirms live output can overtake attach replay after replay capture and route publication.

## Production correction in progress

`pi_session_attach` was changed so the same existing `TerminalManager.lock` remains held from:
- replay snapshot capture;
- route publication via `hub.pi_attach()`;
- bounded replay construction;
- final `_send_pi_replay()` queue enqueue.

This is the minimal serialization direction allowed by REVIEW turn 34:
- TerminalManager remains the sole PTY/output/liveness owner;
- WebSocketHub remains the transient attachment owner;
- output cannot mutate/emit while replay initialization is still waiting to enqueue;
- hub lock remains released during `peer.send()`;
- no new replay store or pending-output queue was introduced.

Fresh targeted evidence before the recovery incident:
- replay-before-live-output regression became GREEN;
- serialized replay-before-exit regression became GREEN.

## IMPORTANT — INCOMPLETE source recovery

While updating the older R31 concurrency regression to reflect the stronger TerminalManager serialization boundary, I used `read_text_file` output as if it contained the full untracked test file and then rewrote `tests/test_pi_ws_contract.py` from that bounded read.

That truncated the untracked file from its prior full source to 308 lines / 11,418 bytes.

This is a DEV-created source-loss incident, not an upstream/repository conflict. I am not claiming PI-T006 acceptance while it is unresolved.

Preservation evidence immediately captured:
- pre-truncation Python 3.14 bytecode copied to:
  `.plan/lantern-pi-native-20261018/evidence-turn35/test_pi_ws_contract_pretruncate.cpython-314.pyc`
- preserved pyc size: 104,330 bytes
- preserved pyc timestamp: 2026-10-19 06:48:30 local

Recovery attempts actually run:
- uncompyle6: unsupported Python 3.14;
- depyf: cannot decompile this Python 3.14 module;
- byteripper: produced syntactically invalid/semantically unreliable output;
- pycrefine: produced syntactically invalid/semantically unreliable output;
- ejfkdev pycdc 0.6.0: produced syntactically valid source but semantic reconstruction is not exact (e.g. independent Peer constructions reconstructed as chained assignments), so it is not safe to overwrite the test source with that output.

Recovery artifacts retained under:
`.plan/lantern-pi-native-20261018/evidence-turn35/`.

## Checks actually run this turn

Before the accidental truncation:
- R34-1 new regression RED: FAIL with output-before-replay ordering, as expected.
- after production serialization change, targeted replay-before-live-output regression: PASS.
- serialized replay-before-exit regression: PASS.

After the truncation:
- no full PI-T006 suite or full repository suite is claimed;
- current test source is incomplete and therefore acceptance verification is invalid;
- `git diff --check` currently exits 0.

## Current repository state

Fresh final state check:
- branch: feat/lantern-bot
- current candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- current `tests/test_pi_ws_contract.py`: 308 lines, 11,418 bytes
- preserved pre-truncation pyc: 104,330 bytes
- `git diff --check`: exit 0

No commit was made.

## Required next DEV action

Restore `tests/test_pi_ws_contract.py` source without discarding the accepted prior PI-T006 test coverage, then rerun:
- targeted R34-1 replay/live-output race;
- R33 exit/replay ordering;
- R31 replay/ownership monotonicity;
- full `tests.test_pi_ws_contract`;
- related Pi/Terminal/auth/LAN regressions;
- enabled PI replay/TUI proofs;
- full repository suite.

Only after exact source recovery and fresh green evidence should this slice route to REVIEW.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE;
- PI-T004 COMPLETE / committed;
- PI-T006 INCOMPLETE this turn because test source recovery is required;
- PI-T007+ not authorized and not started.

Route: DEV.
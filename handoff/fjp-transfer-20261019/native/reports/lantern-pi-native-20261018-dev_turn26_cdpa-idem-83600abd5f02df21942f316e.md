# DEV turn 26 — preserve generation-tagged Pi output across same-ID replacement

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 25 and fixed only R25-1.

Turn-26 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R25-1 TDD RED

Added deterministic regression:
`test_old_generation_output_survives_terminal_id_replacement_before_broadcast`.

Sequence:
1. attach peer A to Pi session A and peer B to Pi session B;
2. intercept old session A terminal_output after TerminalManager has already stamped terminalId + generation + seq + data but before WebSocketHub sees it;
3. old Pi PTY emits `FINAL-BYTES`;
4. remove old generation without emitting a Pi exit for the test setup;
5. create a new ordinary terminal generation under the same internal terminal ID;
6. deliver the delayed old terminal_output;
7. assert peer A receives exactly one old-generation pi_session_output with original seq/data;
8. assert peer B receives none;
9. emit replacement-generation output and assert it is not mislabeled as old Pi output;
10. assert replacement remains live.

Fresh RED before production correction:
- peer A received no pi_session_output;
- assertion failed with `[]` vs the expected old-generation output event.

## Production correction

`WebSocketHub.broadcast()` already required exact:
- terminalId match; and
- generation match

for terminal_output/terminal_exit routing.

The only incorrect predicate was the additional mutable `route.active` gate for terminal_output.

Turn-26 fix removes only that active-state suppression for generation-tagged terminal_output.

Now once a TerminalManager output event exists, WebSocketHub routes it solely by the event's exact terminalId + generation identity.

This means a later terminal_list for a replacement generation cannot retroactively invalidate already-emitted old-generation bytes.

`route.active` bookkeeping itself is preserved unchanged for current-route status/liveness state; no new state owner, queue, lock, replay store, or lifecycle mechanism was added.

Replacement-generation output still cannot reach the old Pi route because its generation differs.

## Acceptance behavior

Fresh targeted GREEN:
- delayed old-generation output survives same-ID replacement;
- delayed old-generation exit still survives same-ID replacement;
- replacement-generation output/exit are not mislabeled as old Pi session events;
- 3 tests OK in 0.018s.

## Verification actually run

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 16 tests OK in 1.059s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.343s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.391s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.318s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.011s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 390 tests in 53.900s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn26/full-unittest.err`

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current uncommitted PI-T006 candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0.

No PI-T006 commit was made because corrected source still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate;
- PI-T005 COMPLETE structured spawn;
- PI-T004 COMPLETE / committed;
- PI-T006 corrected REVIEW candidate;
- PI-T007+ not authorized and not started.

Still INCOMPLETE / NOT_MEASURED:
- runtime application injection;
- real browser F5/live reconnect;
- restart persistence/reopen;
- physical FJP UniKey/IME/AltGr/image paste;
- real POSIX runtime;
- model/goal/extensions parity;
- CPU/RSS/latency/resource-release acceptance.

## REVIEW request

Independent REVIEW should verify R25-1 specifically:
- terminal_output routing uses exact terminalId + generation identity;
- mutable later route.active state no longer suppresses an already-generation-tagged old output event;
- old-generation seq/data survive same-ID replacement before hub delivery;
- wrong-session peers receive no old output;
- replacement-generation output is not mislabeled as old Pi output;
- ordinary Terminal subscription/output behavior remains intact;
- no new lock/state/history mechanism was introduced;
- R22-R24 publication/control/exit protections remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
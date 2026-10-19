# DEV turn 37 — preserve old-session ownership notice when switch-to-new-session attach fails

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 35 and fixed only R35-1.

Turn-37 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate work in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

No PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA changes.

## R35-1 TDD RED

Added deterministic regression:
`test_failed_writer_switch_preserves_old_session_ownership_notice`.

Scenario:
1. W attaches session A as writer;
2. V attaches session A as viewer;
3. V's prior messages are cleared;
4. W attempts to switch to session B;
5. dispatch-level terminal auth succeeds;
6. final replay auth for B fails;
7. B attachment rolls back;
8. A detach remains committed;
9. test requires V to receive exactly the current A ownership notice with writer none / incremented epoch;
10. neither A nor B Pi process is killed.

Fresh RED before production correction:
- authoritative A route had writer none and epoch advanced;
- B was correctly rolled back;
- V received no A ownership notice;
- exact assertion: `[]` vs one expected `pi_session_ownership` event.

Also added preservation regression:
`test_failed_viewer_switch_does_not_invent_old_session_ownership_notice`.

It proves that if the switching peer was only an A viewer:
- A writer remains unchanged;
- A epoch does not change;
- no synthetic A ownership notice is emitted;
- B rollback succeeds;
- both Pi processes remain live.

That test was GREEN before the production correction, confirming the defect was specific to committed writer-detach notifications.

## Production correction

Current `hub.pi_attach()` already returns `notices` for committed mutations that happened while switching away from the previous session.

Current failure handling already returns `rollback_notices` for the failed new-session attachment.

The defect was only the error path sending `rollback_notices` and discarding the earlier committed old-session `notices`.

Minimal correction:
- on attach replay/auth failure, send `[*notices, *rollback_notices]` through the existing `_send_pi_notices()` machinery;
- re-raise the original attach error unchanged.

This preserves existing authoritative filtering:
- stale session/generation/epoch notices are skipped;
- notices only go to peers still attached to that route;
- per-peer ownership enqueue ordering remains serialized;
- no old session is automatically reattached;
- no new state owner, queue, retry system, or persistence mechanism was added.

Both Pi processes remain untouched by the failed switch.

## Verification actually run

Targeted RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_failed_writer_switch_preserves_old_session_ownership_notice tests.test_pi_ws_contract.PiWsContractTests.test_failed_viewer_switch_does_not_invent_old_session_ownership_notice`
- writer-switch test FAILED as expected with missing A notice;
- viewer-switch preservation test already passed.

Targeted GREEN after correction:
- same command;
- 2 tests OK in 0.012s.

Full PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- Ran 29 tests in 1.604s
- OK.

Related Pi/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- Ran 40 tests in 6.536s
- OK.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- Ran 23 tests in 4.178s
- OK.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Enabled PI replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- Ran 7 tests in 12.284s
- OK.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- Ran 1 test in 10.002s
- OK.
- no paid AI prompt.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 403 tests in 52.309s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn37/full-unittest.err`.

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- recovered PI-T006 contract now has 29 test methods;
- `git diff --check`: exit 0.

No PI-T006 commit was made because the corrected source still requires independent REVIEW/TEST acceptance.

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

Independent REVIEW should verify R35-1 specifically:
- failed A->B switch preserves ownership notices from the committed detach from A;
- B rollback notices are also preserved;
- old-session and rollback notice lists are sent through existing authoritative epoch/session filtering;
- writer switch leaves A writer none with incremented epoch and informs remaining A viewers;
- viewer switch does not invent an A epoch change or ownership notice;
- neither Pi process is killed;
- failed switching peer is not left attached to B;
- R22-R34 replay/output/session/rollback/ownership ordering protections remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
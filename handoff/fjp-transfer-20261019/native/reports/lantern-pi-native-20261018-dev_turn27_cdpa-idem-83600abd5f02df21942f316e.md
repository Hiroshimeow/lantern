# DEV turn 27 — close generic Terminal replay/output/exit scoping bypass for Pi generations

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read TEST turn 11 and fixed only T11-1.

Turn-27 direct edits:
- lantern/terminal.py
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## T11-1 TDD RED

Added deterministic regression:
`test_pi_generation_cannot_escape_through_generic_subscribe_output_or_exit`.

The test uses real:
- PiSessionRegistry;
- TerminalManager;
- WebSocketHub;
- production dispatch;

with fake PTY I/O only.

Scenario:
1. peer A attaches to Pi session A;
2. peer B attaches only to Pi session B;
3. a separate authenticated peer remains unattached to Pi;
4. A emits private output and A's attached peer receives it correctly;
5. B and unattached peer attempt generic `terminal_subscribe` against A internal terminal ID;
6. A emits more output and exits;
7. test asserts only A's attached Pi peer receives A scoped output/exit;
8. test separately creates an ordinary terminal and proves generic subscribe/replay/output/exit remains unchanged.

Fresh RED before production correction:
- both B and unattached peer could generic-subscribe to A; expected PermissionError was not raised;
- cross-session generic output remained visible;
- one test produced three failures matching TEST turn 11.

## Production correction

### Generic subscribe authorization

`terminal_subscribe` now reuses the existing `_guard_generic_terminal_control()` process-owner fence before replay capture or hub subscription.

The check runs inside the existing TerminalManager RLock, before:
- `replay_view()`;
- `hub.subscribe()`.

For subscribe only, the guard asks TerminalManager ownership with `include_history=True`, so stopped retained Pi history cannot be replayed through the generic Terminal path.

`TerminalManager.control_owner()` therefore gained one keyword-only `include_history=False` option:
- default behavior is unchanged for generic process controls;
- when requested for replay authorization it checks current live entry first, then retained history.

A later ordinary replacement generation remains allowed because TerminalManager create already replaces/pops stale history and the live ordinary entry has no Pi owner marker.

### Output/exit delivery scoping

`WebSocketHub.broadcast()` now records when a `terminal_output` or `terminal_exit` event matches an existing Pi route by exact:
- terminalId; and
- generation.

Matching attached peers still receive exactly the Pi-specific payload:
- `pi_session_output`; or
- `pi_session_exit`.

For the same exact Pi-scoped event, all other peers now skip the generic `terminal_output` / `terminal_exit` delivery path, even if they know the internal terminal ID or have a generic subscription.

This preserves the accepted R25 behavior because delayed old-generation output/exit still matches the retained old Pi route by exact generation and is delivered to its attached old-session peers.

Replacement-generation traffic does not match the old route generation and therefore cannot be mislabeled as old Pi traffic.

No new state owner, output store, auth policy, or terminal-ID hiding mechanism was added.

## Ordinary Terminal compatibility

The new regression explicitly proves a normal ordinary terminal still supports:
- terminal_create;
- terminal_subscribe + terminal_replay;
- generic terminal_output;
- generic terminal_exit.

Existing ordinary replacement-generation tests also remain green.

## Verification actually run

Targeted T11-1 RED:
- 1 test run;
- failed with 3 assertions before production correction;
- failures were missing subscribe rejection and cross-session generic delivery.

Targeted T11-1 GREEN:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_pi_generation_cannot_escape_through_generic_subscribe_output_or_exit`
- 1 test OK in 0.008s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 17 tests OK in 1.035s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 5.428s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.142s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.032s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 9.999s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 391 tests in 51.108s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn27/full-unittest.err`

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

Independent REVIEW should verify T11-1 specifically:
- generic terminal_subscribe cannot replay a live or retained Pi-owned generation;
- B attached only to session B cannot receive A generic replay/output/exit;
- unattached authenticated peers cannot receive A generic replay/output/exit;
- A attached peers still receive exactly one scoped Pi output/exit event;
- delayed old-generation R25 output/exit remains deliverable to old attached route peers;
- replacement-generation events remain isolated;
- ordinary terminal subscribe/output/exit remains unchanged;
- authorization does not depend on hiding internal terminal IDs;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
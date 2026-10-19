# DEV turn 24 — make generic Terminal ownership check atomic with actuation

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 23 and fixed only R23-1.

Changed only:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/terminal.py
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R23-1 reproduction / TDD RED

Added deterministic regression:
`test_generic_control_authorization_is_atomic_with_actuation`.

The test covers all six guarded generic operations:
- terminal_input;
- terminal_key;
- terminal_resize;
- terminal_kill;
- terminal_run;
- terminal_create.

For each operation:
1. create ordinary terminal `race`;
2. generic dispatch enters ownership check;
3. after ordinary ownership is observed, a replacement thread kills that generation and creates a Pi-owned replacement under the same terminal ID;
4. generic dispatch continues.

Fresh RED before production correction:
- input wrote `STALE` into the Pi replacement;
- key wrote encoded Enter into the Pi replacement;
- resize resized the Pi replacement;
- kill killed the Pi replacement;
- run replaced/killed the Pi replacement;
- create returned/observed the Pi replacement generation.

Result: 1 test with all 6 subtests failing exactly at stale-authorization crossing.

## Production correction

Generic process-control dispatch now holds `TerminalManager.lock` across both:
1. `_guard_generic_terminal_control()` ownership validation; and
2. the actual TerminalManager operation.

Operations covered under the single existing RLock boundary:
- terminal_create;
- terminal_run;
- terminal_input;
- terminal_key;
- terminal_resize;
- terminal_kill.

Because TerminalManager already uses `threading.RLock`, the existing methods safely re-enter the same lock.

Socket response for terminal_create/terminal_run is sent only after releasing the TerminalManager lock.

No WebSocketHub lock is acquired by this generic path, so the established Pi lock order is unchanged and no hub->terminal cycle is added.

Removed the now-unreachable duplicate terminal_kill branch below the unified generic-control block.

## Acceptance behavior

Fresh targeted GREEN after correction:
- `test_generic_control_authorization_is_atomic_with_actuation`
- 1 test OK in 0.982s.

The regression proves that an ordinary->Pi replacement cannot be reached by a stale generic request once the request has begun authorization.

Existing PI-T006 protections remain covered:
- Pi-create publication-window ownership marker;
- live Pi generic-control block;
- stale ordinary replacement-generation compatibility;
- attach/exit race;
- takeover/liveness race;
- writer/takeover stale input/resize race;
- auth and session isolation.

## Verification actually run

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 14 tests OK in 1.022s.

Registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.186s.

Ordinary Terminal regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 2.854s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.247s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 9.998s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 388 tests in 59.445s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn24/full-unittest.err`

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

Independent REVIEW should verify R23-1 specifically:
- generic owner validation and actuation are atomic under the same TerminalManager RLock;
- stale ordinary authorization cannot reach a Pi replacement generation;
- create/run/kill destructive operations are covered, not only input;
- socket sends occur outside the TerminalManager lock;
- no WebSocketHub lock is added to generic path;
- ordinary Terminal behavior and later ordinary replacement generations remain intact;
- R22 publication-window protection remains intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
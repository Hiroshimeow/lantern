# DEV turn 29 — filter Pi-owned retained output from legacy fallback snapshot

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 28 and fixed only R28-1.

Turn-29 direct edits:
- lantern/terminal.py
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R28-1 TDD RED

Added deterministic regression:
`test_legacy_snapshot_excludes_pi_retained_output_and_preserves_ordinary_tail`.

The test creates:
- route-less Pi session A and emits retained `PI-SECRET-SNAPSHOT`;
- ordinary terminal and emits >20,000 chars ending with `ORDINARY-TAIL`;
- production `_legacy_snapshot_payload(terminal)`.

Required assertions:
- Pi terminal ID absent from legacy snapshot `output` map;
- ordinary terminal present;
- ordinary retained tail equals the existing last-20,000-char behavior;
- truncation flag remains true;
- Pi terminal metadata remains visible in `terminals` list because list hiding is outside this fix.

Fresh RED before production correction:
- Pi terminal ID was present in snapshot output with `PI-SECRET-SNAPSHOT`.

## Production correction

### TerminalManager retained-output filter

Preserved existing public `TerminalManager.replay()` behavior unchanged.

Added one narrow owner-aware read helper:
`replay_excluding_control_owner(owner)`.

It:
- executes under TerminalManager's existing RLock;
- reads the same live + history retained-output owners as `replay()`;
- excludes only entries whose exact TerminalEntry `control_owner` matches the requested owner;
- does not mutate retained history;
- does not consult PiSessionRegistry or WebSocket route state.

### Legacy snapshot

`_legacy_snapshot_payload()` now prefers:
`terminal.replay_excluding_control_owner("pi")`

and falls back to the old `terminal.replay()` only for minimal test/fake terminal objects that do not implement the new owner-aware helper.

This keeps real production classification at TerminalManager retained-output ownership while preserving the existing lightweight LAN snapshot performance test fixture.

Ordinary snapshot truncation remains unchanged:
- same 20,000-char display cap;
- same `truncated` detection;
- no modification to server-retained output.

Pi terminal metadata list visibility remains unchanged by design.

## Verification actually run

Targeted R28-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_legacy_snapshot_excludes_pi_retained_output_and_preserves_ordinary_tail`
- 1 test FAILED before production correction because Pi retained output was present.

First GREEN aggregation exposed a compatibility regression in the existing lightweight LAN test fixture:
- `test_legacy_reconnect_snapshot_is_bounded_without_deleting_server_history` errored because its SimpleNamespace `replay` lambda did not accept the new keyword argument.

Correction:
- restored `TerminalManager.replay()` original no-argument contract;
- moved filtering to new `replay_excluding_control_owner()` helper;
- legacy snapshot uses the helper when available and old replay fallback for non-TerminalManager test doubles.

Fresh targeted GREEN after compatibility correction:
- R28-1 mixed Pi/ordinary snapshot regression -> OK;
- existing legacy truncation fixture -> OK;
- 2 tests OK in 0.025s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 19 tests OK in 1.036s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 5.496s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.510s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.391s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 10.015s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 393 tests in 60.729s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn29/full-unittest.err`

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

Independent REVIEW should verify R28-1 specifically:
- legacy fallback retained output excludes TerminalEntry generations owned by Pi;
- filtering truth comes from TerminalManager retained-output ownership, not registry/route state;
- ordinary legacy replay and 20,000-char truncation remain unchanged;
- retained server history is not mutated;
- Pi terminal metadata list visibility remains unchanged;
- route-less live-event suppression and attached-route scoping remain intact;
- delayed old-generation output/exit and replacement isolation remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
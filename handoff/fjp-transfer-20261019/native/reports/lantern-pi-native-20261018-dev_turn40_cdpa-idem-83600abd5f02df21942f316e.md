# DEV turn 40 — verify existing R38-1 per-peer replay/live continuity candidate

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 38 and inspected only R38-1 replay/live continuity.

No source edit was made in this turn.

At turn start, repository truth already contained an unaccepted R38-1 candidate in:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Those changes were not described by DEV turn 39, so I treated them as pre-existing dirty work and preserved them rather than rewriting or attributing them to this turn.

Existing PI-T006 candidate paths remain:
- lantern/pi_sessions.py
- lantern/terminal.py
- lantern/ws.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py
- tests/test_pi_ws_contract.py

No PI-T007, runtime/application wiring, browser/UI, persistence, Markdown implementation, Spec 001 T2, LAN/auth-policy, Lantern :9999, or CDPA work.

## Current R38-1 candidate inspected

`WebSocketHub` already contains per-peer transient continuity state:
- `pi_peer_delivery[peer]`
- exact sessionId
- exact generation
- exact attach token
- `lastSeq`

`_send_pi_replay()` currently:
1. serializes on the existing per-peer Pi ordering lock;
2. validates auth + session/generation/attachment under existing TerminalManager/WebSocketHub boundaries;
3. enqueues replay;
4. while still inside the per-peer ordering boundary, records the replay seq as that attachment's `lastSeq` together with the current attach token.

`broadcast()` currently revalidates Pi output immediately before enqueue and, for `pi_session_output`:
- requires continuity state for the same sessionId;
- requires same generation;
- requires same attach token;
- drops event seq <= `lastSeq`;
- after successful enqueue, advances `lastSeq` monotonically.

`_pi_detach_locked()` removes the peer continuity state together with peer session / attach token.

This is per-peer rather than route-wide, so peers attaching at different replay baselines can receive different correct outcomes.

No duplicate retained transcript or browser-side dedupe is introduced.

## Existing deterministic R38 regressions found

Current test source already contains both requested shapes:

`test_delayed_pre_attach_output_in_replay_is_not_delivered_twice`:
- terminal output advances retained output + seq;
- hub delivery is paused;
- peer attaches and replay contains seq 1 + PRE-ATTACH;
- delayed seq 1 is released;
- no live duplicate seq 1 is accepted;
- fresh seq 2 arrives exactly once.

`test_delayed_output_uses_each_peers_own_replay_baseline`:
- early peer attaches at seq 0;
- seq 1 retained output is paused before hub delivery;
- late peer attaches and replays seq 1;
- delayed seq 1 is then released;
- early peer receives seq 1 once;
- late peer suppresses seq 1 because its replay already included it;
- both peers receive fresh seq 2 once.

Two additional equivalent R38 regressions are also present:
- `test_pre_attach_delayed_output_in_replay_is_not_delivered_twice`
- `test_delayed_output_uses_per_peer_replay_baseline`

I did not remove them in this turn because REVIEW explicitly requested avoiding broad cleanup while the reconstructed PI-T006 source remains unaccepted.

## Verification actually run

Fresh targeted R38 proof:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_pre_attach_delayed_output_in_replay_is_not_delivered_twice tests.test_pi_ws_contract.PiWsContractTests.test_delayed_output_uses_per_peer_replay_baseline tests.test_pi_ws_contract.PiWsContractTests.test_delayed_pre_attach_output_in_replay_is_not_delivered_twice tests.test_pi_ws_contract.PiWsContractTests.test_delayed_output_uses_each_peers_own_replay_baseline`
- Ran 4 tests in 0.026s
- OK.

Fresh full PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- Ran 37 tests in 1.621s
- OK.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- Ran 40 tests in 6.851s
- OK.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- Ran 23 tests in 4.247s
- OK.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Enabled PI replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- Ran 7 tests in 12.379s
- OK.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- Ran 1 test in 10.008s
- OK.
- no paid AI prompt.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 411 tests in 66.498s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn40/full-unittest.err`.

## Final repository state

Fresh final check:
- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- branch remains ahead of origin feature branch by 21 commits;
- current candidate paths:
  - M lantern/pi_sessions.py
  - M lantern/terminal.py
  - M lantern/ws.py
  - M tests/test_pi_sessions.py
  - M tests/test_terminal_scm.py
  - ?? tests/test_pi_ws_contract.py
- PI-T006 contract currently has 37 test methods;
- `git diff --check`: exit 0.

No commit was made because PI-T006 remains unaccepted and the R38 candidate requires independent correctness review.

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
- PI-T006 R38-1 candidate present and freshly verified, but not accepted;
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

Independent REVIEW should inspect the pre-existing R38 candidate and verify:
- replay seq becomes the per-peer attachment baseline only for the exact session/generation/attach token;
- delayed event seq <= replay/last-delivered seq is dropped only for that peer;
- an earlier peer with a lower baseline still receives the same delayed seq when needed;
- live seq advances monotonically after successful enqueue;
- session switch/detach clears old continuity state;
- replacement generation gets a fresh attachment token/baseline;
- per-peer ordering lock prevents replay/baseline publication races;
- R22-R37 attach, generation, rollback, ownership, stale-delivery and detach/remove protections remain intact;
- duplicate test coverage is non-blocking cleanup only and should not trigger broad refactor before acceptance;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
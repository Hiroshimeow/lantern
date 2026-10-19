# DEV turn 28 — route-less Pi output/exit classification from TerminalManager ownership

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 27 and fixed only R27-1.

Turn-28 direct edits:
- lantern/terminal.py
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R27-1 TDD RED

Added deterministic regression:
`test_unattached_pi_generation_never_falls_through_to_generic_output_or_exit`.

The test creates a Pi session but never calls `pi_session_attach` for that session, then connects:
- one authorized v2 peer;
- one authorized legacy peer;
- one additional authorized ordinary peer.

It emits Pi output and exit and requires:
- no peer receives generic terminal_output/terminal_exit for the Pi generation;
- no peer receives Pi-scoped output/exit because no Pi route has attached peers;
- ordinary Terminal output/exit behavior remains unchanged in a separate ordinary terminal case.

Fresh RED before production correction:
- the test failed because route-less Pi output/exit still appeared through generic Terminal routing.

## Production correction

### TerminalManager event classification

TerminalManager already owns exact TerminalEntry generation and `control_owner`.

Generation-tagged process events now carry one internal-only marker:
- `_controlOwner: entry.control_owner`

Added to:
- terminal_output;
- natural terminal_exit;
- explicit kill terminal_exit;
- kill_if_generation terminal_exit.

This marker is created from the exact TerminalEntry that produced the event, so classification does not depend on later WebSocket route existence, terminal ID prefix, or registry lookup.

### WebSocketHub route-less suppression

`WebSocketHub.broadcast()` now classifies a process event as Pi-scoped immediately when:
- `message['_controlOwner'] == 'pi'`.

Existing exact terminalId+generation Pi route matching still builds `pi_session_output` / `pi_session_exit` payloads for attached matching peers.

For a Pi-owned event:
- matching Pi-route peers receive the scoped Pi payload;
- all other peers skip generic terminal_output/terminal_exit;
- if no Pi route exists, no peer receives the event.

This closes the route-existence gap reported by REVIEW turn 27.

### Internal marker non-exposure

Before any ordinary generic broadcast, WebSocketHub copies the event and removes `_controlOwner`.

Therefore:
- Pi owner classification is server-internal;
- ordinary Terminal clients do not see `_controlOwner`;
- existing public terminal output/exit fields remain unchanged apart from the already accepted generation field.

## Preserved behavior

Existing attached-route scoping remains intact:
- exact terminalId + generation route peers get one Pi-scoped event;
- nonattached peers get no generic duplicate.

Existing delayed old-generation behavior remains intact because the delayed event carries its original generation and owner marker:
- old attached route peers still receive delayed old-generation output/exit after same-ID replacement;
- replacement-generation output/exit cannot be mislabeled as the old Pi session.

Generic live/retained Pi replay denial from turn 27 remains unchanged.

Ordinary Terminal behavior remains unchanged:
- v2 peers still receive ordinary generic terminal_exit;
- legacy peers still receive ordinary generic terminal_output and terminal_exit.

No new state owner, registry coupling, replay store, auth policy, terminal-ID prefix check, or persistence mechanism was introduced.

## Verification actually run

Targeted R27-1 RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_unattached_pi_generation_never_falls_through_to_generic_output_or_exit`
- 1 test FAILED before production correction, reproducing generic route-less Pi leakage.

Targeted R27-1 GREEN:
- same command after correction;
- 1 test OK in 0.008s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 18 tests OK in 1.041s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.511s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 2.531s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 11.353s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 9.949s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 392 tests in 51.965s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn28/full-unittest.err`

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

Independent REVIEW should verify R27-1 specifically:
- Pi output/exit classification comes from the exact TerminalEntry owner marker, not Pi route existence;
- route-less Pi generations deliver no generic output/exit to v2 or legacy peers;
- attached matching Pi routes still receive exactly one scoped output/exit;
- `_controlOwner` is never exposed to clients;
- ordinary Terminal output/exit remains unchanged;
- delayed old-generation R24/R25 output/exit still reaches old attached peers after same-ID replacement;
- replacement generation isolation remains intact;
- no new process/session state owner or PI-T007/persistence behavior was introduced.

Route: REVIEW.
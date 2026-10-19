# DEV turn 21 — fix PI-T006 takeover/liveness race

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 20 and fixed only R20-1.

Changed only:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, session-create RPC, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R20-1 reproduction / TDD RED

Added deterministic regression:
`test_takeover_rejects_exit_between_registry_view_and_ownership_change`.

Test schedule:
1. attach writer and viewer to one live Pi session;
2. wrap registry.get() so it first returns the session as running;
3. immediately invoke the real PTY exit callback before takeover ownership mutation;
4. perform `pi_session_takeover` from the viewer.

Fresh RED before production correction:
- takeover raised no error;
- viewer could become writer after PTY exit.

Exact result: 1 test, FAIL.

## Production correction

Takeover now uses the same cross-owner lock order already established for attach and writer actuation:
`TerminalManager.lock -> WebSocketHub.lock`.

Flow:
1. acquire `terminal.lock`;
2. resolve/revalidate registry sessionId + expected generation;
3. capture `terminal.replay_view(session["terminalId"])` while still under terminal lock;
4. reject if generation mismatches or `meta.running` is false;
5. acquire `hub.lock` while terminal lock is still held;
6. perform takeover mutation only through `_pi_takeover_locked()`;
7. release locks;
8. send ownership notices outside hub lock.

Added `_pi_takeover_locked()` as the lock-free validation/mutation body for callers already holding hub lock. Existing `pi_takeover()` remains a wrapper for direct callers.

No inverse hub->terminal nested lock path was introduced. No restart, auto-reattach, persistence, or PI-T007 behavior was added.

## Acceptance proof

Fresh targeted GREEN:
- `test_takeover_rejects_exit_between_registry_view_and_ownership_change` -> OK

The regression proves:
- takeover raises stale-session after exit;
- viewer is not promoted;
- ownership epoch does not advance due the rejected takeover;
- no new writer ownership notification is sent for the stopped session;
- authoritative registry/TerminalManager state is stopped.

Prior race fixes remain covered by the same contract suite:
- attach-after-exit rejection;
- stale old-writer input after takeover rejection;
- stale resize after takeover rejection.

## Verification actually run

Targeted R20-1:
- 1 test OK in 0.008s

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 10 tests OK in 0.061s

Related regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 5.889s

Syntax/diff:
- `uv run python -m py_compile lantern\ws.py tests\test_pi_ws_contract.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 384 tests in 52.128s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn21/full-unittest.err`

## Final repository state

- HEAD: 71bc8de3e6b82e94078b899c54ba01cfb71ff64b
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/6
- current PI-T006 candidate:
  - M lantern/ws.py
  - ?? tests/test_pi_ws_contract.py
- `git diff --check`: exit 0

No PI-T006 commit was made because corrected source still requires independent REVIEW/TEST acceptance.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C NOT_MEASURED / deferred;
- T2 BLOCKED;
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE;
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

Independent REVIEW should verify R20-1 specifically:
- takeover liveness/generation validation is atomic with ownership mutation;
- lock order is consistently TerminalManager -> WebSocketHub;
- no hub -> terminal deadlock path was added;
- stopped session cannot gain writer ownership or epoch advance;
- ownership notices remain outside hub lock;
- prior attach/writer race fixes remain intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
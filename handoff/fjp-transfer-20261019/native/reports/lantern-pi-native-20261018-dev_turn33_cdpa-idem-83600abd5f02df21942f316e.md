# DEV turn 33 — transactional attach rollback after replay authorization failure

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read REVIEW turn 32 and fixed only R32-1.

Turn-33 direct edits:
- lantern/ws.py
- tests/test_pi_ws_contract.py

Preserved existing unaccepted PI-T006 candidate changes in:
- lantern/pi_sessions.py
- lantern/terminal.py
- tests/test_pi_sessions.py
- tests/test_terminal_scm.py

Did not start PI-T007, runtime/application wiring, browser/UI work, persistence, Markdown implementation, Spec 001 T2, LAN/auth policy changes, Lantern :9999 actions, or CDPA changes.

## R32-1 TDD RED

Added deterministic regression:
`test_attach_auth_revocation_rolls_back_published_writer`.

Sequence:
1. peer is connected;
2. first `can_terminal()` call succeeds at dispatch entry;
3. Pi attach publishes peer into transient route state and makes it first writer;
4. second `can_terminal()` call in `_send_pi_replay()` fails;
5. attach raises;
6. test requires peer removed from `pi_peer_session` and route peer set, writer cleared, no replay delivered, and Pi process still running.

Fresh RED before production correction:
- attach raised as expected;
- peer remained present in `pi_peer_session` as session `sessA`;
- failed peer therefore remained a ghost attachment/writer.

## Production correction

### Generation/session-safe rollback

Added `WebSocketHub.pi_rollback_attach(peer, session_id, generation, attach_token)`.

Rollback runs under `hub.lock` and only detaches when all of these still match the failed attach:
- current `pi_peer_session[peer]` equals the failed sessionId;
- route still exists;
- route generation equals the failed generation;
- peer is still in that route's peer set;
- peer's current attach token is exactly the token created by that attach.

If any check differs, rollback is a no-op.

### Per-attachment identity

Added transient `pi_peer_attach_token` map in WebSocketHub.

Each newly published attachment gets a unique in-memory object token.

`pi_attach()` now returns that token with role/epoch/notices.

Idempotent repeated attach to the same already-current session returns the existing token rather than creating a new attachment identity.

`_pi_detach_locked()` removes the token together with `pi_peer_session`.

This is intentionally transient hub state only; no persistence, protocol field, browser state, or session-registry field was added.

### Attach error handling

`pi_session_attach` now wraps only the replay-send phase after route publication.

If `_send_pi_replay()` raises:
1. call token/session/generation-safe `pi_rollback_attach()`;
2. send any fresh ownership notices returned by normal detach semantics;
3. re-raise the original attach/replay failure.

If the failed peer was still writer, normal detach semantics clear writer and advance ownership epoch.

If another peer already became authoritative writer, removing the failed peer as viewer does not disturb that writer.

Pi process is never killed by rollback.

## Additional concurrency proof

Added `test_failed_attach_rollback_does_not_remove_newer_same_session_attachment`.

It proves an older failed-attach token cannot detach a later attachment by the same peer to the same session and PTY generation:
- attach token T1 created;
- peer detaches;
- newer same-session attachment creates T2;
- rollback using stale T1 returns no notices and leaves T2 attached/writer.

This closes the REVIEW requirement that rollback must not blindly remove a newer/different attachment.

Also added `test_attach_auth_revocation_rolls_back_viewer_without_disturbing_writer`:
- existing writer remains writer;
- viewer's failed replay/auth attach is removed;
- ownership epoch remains unchanged;
- Pi process remains live.

## Verification actually run

Targeted writer rollback RED:
- `uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_attach_auth_revocation_rolls_back_published_writer`
- 1 test FAILED before production correction because failed peer remained in `pi_peer_session`.

Targeted rollback GREEN:
- writer auth-revocation rollback -> OK
- viewer auth-revocation rollback without writer disturbance -> OK
- stale old attach token cannot remove newer same-session attachment -> OK
- 3 tests OK in 0.019s.

PI-T006 contract:
- `uv run python -m unittest -q tests.test_pi_ws_contract`
- 25 tests OK in 1.600s.

Related registry/auth/LAN regressions:
- `uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf`
- 40 tests OK in 6.663s.

Ordinary Terminal focused regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 23 tests OK in 4.248s.

Enabled PI-T003 replay proof:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 12.556s.

Enabled native Pi TUI proof:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 9.953s.
- no paid AI prompt.

Syntax/diff:
- `uv run python -m py_compile lantern\terminal.py lantern\pi_sessions.py lantern\ws.py tests\test_pi_sessions.py tests\test_pi_ws_contract.py tests\test_terminal_scm.py` -> exit 0
- `git diff --check` -> exit 0.

Fresh full repository suite:
- `uv run python -m unittest discover -s tests -q`
- Ran 399 tests in 56.755s
- OK (skipped=134)
- existing HTTPError cleanup ResourceWarnings plus one closed-socket ResourceWarning only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn33/full-unittest.err`

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

Independent REVIEW should verify R32-1 specifically:
- replay/auth failure after route publication conditionally rolls back only that exact attach token/session/generation;
- failed first writer is absent from route state and writer is cleared/epoch advanced by normal detach semantics;
- failed viewer rollback does not disturb current writer or epoch;
- stale rollback cannot detach a newer same-session/same-generation attachment;
- rollback never kills the Pi process;
- any rollback ownership notices use existing monotonic per-peer notice ordering;
- R29-R31 ownership notification/replay ordering remains intact;
- no PI-T007/UI/persistence/Markdown/LAN-policy scope drift.

Route: REVIEW.
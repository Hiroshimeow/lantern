# REVIEW turn 26 — verify delayed old-generation Pi output survives same-ID replacement

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 26  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `71bc8de3e6b82e94078b899c54ba01cfb71ff64b`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **clean correctness review; ROUTE TEST** for independent PI-T006 acceptance. R25-1 is resolved, prior R22-R24 protections remain intact, and no new material reproducible correctness defect was found.

No implementation edits were made by REVIEW.

## Inputs independently checked

- DEV turn 26 handoff.
- REVIEW turn 25 R25-1.
- PLAN turn 11 PI-T006 output/exit scoping and concurrency contract.
- Current candidate source/tests:
  - `lantern/pi_sessions.py`
  - `lantern/terminal.py`
  - `lantern/ws.py`
  - `tests/test_pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_ws_contract.py`
- Current Git state/scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 71bc8de3e6b82e94078b899c54ba01cfb71ff64b`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/6`.
- worktree candidate remains exactly:
  - `M lantern/pi_sessions.py`
  - `M lantern/terminal.py`
  - `M lantern/ws.py`
  - `M tests/test_pi_sessions.py`
  - `M tests/test_terminal_scm.py`
  - `?? tests/test_pi_ws_contract.py`
- `git diff --check`: exit 0.
- no PI-T007, app/runtime injection, browser/UI, persistence, Markdown implementation, dependency/vendor, LAN/auth-policy, Spec 001 T2, live Lantern :9999 action, or CDPA action was introduced.

## R25-1 — delayed generation-tagged output after replacement: RESOLVED

The only turn-26 production change is the routing predicate in `WebSocketHub.broadcast()`.

For both `terminal_output` and `terminal_exit`, Pi routing now requires exact:
- internal terminal ID; and
- PTY generation.

The prior additional mutable `route.active` suppression is no longer used for `terminal_output`.

This is the correct event-identity boundary:
- once TerminalManager has emitted a generation-tagged output event, a later `terminal_list` caused by same-ID replacement cannot retroactively invalidate those already-produced bytes;
- replacement-generation output still cannot be mislabeled as the old Pi session because its generation differs;
- seq/data are forwarded unchanged;
- no extra queue, replay buffer, lifecycle owner, lock, or state store was introduced.

## Fresh deterministic reproduction of the original race

REVIEW independently recreated the exact turn-25 failure with:
- real `PiSessionRegistry`;
- real `TerminalManager`;
- real `WebSocketHub/dispatch`;
- fake PTY I/O only.

Sequence:
1. attach Pi session `sess`;
2. old generation emits `FINAL-BYTES`;
3. after TerminalManager stamps the old `terminal_output` but before hub delivery:
   - old generation is removed;
   - a new ordinary generation is created under the same terminal ID;
4. delayed old output reaches WebSocketHub.

Fresh result:

`pi_output_events [{'type': 'pi_session_output', 'sessionId': 'sess', 'generation': '<old>', 'seq': 1, 'data': 'FINAL-BYTES'}]`

replacement remains live with a different generation.

Probe result:

`pi_output_scoping_replacement_race_ok`

This directly closes R25-1.

## R24 exit-generation protection remains intact

Fresh targeted tests:
- `test_old_generation_output_survives_terminal_id_replacement_before_broadcast`: PASS.
- `test_old_generation_exit_survives_terminal_id_replacement_before_broadcast`: PASS.
- `test_replacement_generation_rejects_old_attachment_without_touching_new_pty`: PASS.

Result:
- 3 tests;
- all 3 OK;
- 0.018 s;
- exit 0.

Thus:
- old-generation output survives same-ID replacement;
- old-generation exit survives same-ID replacement;
- replacement-generation events are not relabeled as old Pi-session events;
- replacement process remains unaffected.

## Fresh PI-T006 / related verification

Full PI-T006 contract:

`uv run python -m unittest -q tests.test_pi_ws_contract`

Result:
- 16 tests;
- all OK;
- 1.109 s;
- exit 0.

Related registry / Terminal / auth / LAN regressions:

`uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_terminal_auth tests.test_lan_multi_perf`

Result:
- 63 tests;
- all OK;
- 10.624 s;
- exit 0.

Syntax/diff:
- `py_compile` for Terminal/Pi registry/WS and affected tests: exit 0.
- `git diff --check`: exit 0.

## Fresh full repository verification

REVIEW also ran:

`uv run python -m unittest discover -s tests -q`

with native/replay opt-in environment gates unset.

Result:
- **390 tests**
- **OK**
- **skipped=134**
- **50.739 s**
- exit 0.

Existing HTTPError cleanup warnings plus the already-seen closed-socket ResourceWarning remain warnings, not test failures.

Skipped native/browser/physical cases remain skipped evidence, not PASS evidence.

## PI-T006 correctness assessment

The current candidate now satisfies the scoped server transport/ownership contract under reviewed evidence:

- attach identity is `sessionId + generation`;
- first attacher is writer, later peers are viewers;
- writer input/key/resize uses ownership epoch;
- takeover advances epoch and stale old-writer operations are rejected atomically;
- attach/takeover reject stopped/replaced generations;
- detach/disconnect releases ownership without killing the Pi process;
- session switching and A/B routing remain isolated;
- replay continuity reuses TerminalManager seq/UTF-8 boundaries;
- generic Terminal process control cannot enter Pi-owned generations during publication or later replacement races;
- delayed old-generation output and exit remain correctly scoped by event generation;
- replacement generation remains untouched;
- Pi-attached peers do not receive duplicate generic + Pi delivery for the matching event;
- ordinary Terminal subscription/control regressions remain green;
- existing terminal auth is reused.

No runtime browser/F5/persistence acceptance is inferred.

## Concurrency / lock-order review

Cross-owner mutation paths remain consistent with the established order:

`TerminalManager lock -> WebSocketHub lock`.

The turn-26 output correction adds no lock and therefore introduces no new deadlock edge.

Generation-tagged output/exit routing is based on immutable event identity rather than later mutable process state, which removes the replacement-order race without expanding synchronization scope.

## Complexity / over-engineering review

No new complexity was introduced by turn 26 itself; it removes one routing condition.

There is now some pre-existing dead state that can be removed before commit without changing behavior:

- `lantern/ws.py:L288`: delete: `route["active"] = True` initial field. Nothing reads route active now.
- `lantern/ws.py:L299`: delete: replacement-route `active=True`. Nothing reads route active now.
- `lantern/ws.py:L355-362`: delete: terminal-list generation scan whose only effect is updating unread `route["active"]`. Nothing replaces it.
- `lantern/ws.py:L328-330`: delete: unused `pi_takeover()` wrapper. Synchronized dispatch uses `_pi_takeover_locked()`.
- `lantern/ws.py:L346-348`: delete: unused `pi_writer_target()` wrapper. Synchronized dispatch uses `_pi_writer_target_locked()`.

**net: -16 lines possible.**

This is non-blocking maintainability cleanup; none of these lines changes the reviewed PI-T006 behavior.

## Other required review dimensions

- **Correctness:** no material reproducible defect found after R25-1 correction.
- **Scope drift:** none detected.
- **UX:** no browser/UI implementation in this slice, correctly.
- **Maintainability/module separation:** TerminalManager owns process generation/events; WebSocketHub owns transient peer/writer routing; registry remains session metadata owner.
- **Scalability:** no duplicate transcript/output store, queue, or persistence layer.
- **Native Pi parity:** server transport remains byte-transparent; physical/browser parity remains NOT_MEASURED.
- **Concurrency isolation:** publication, generic-control, attach, takeover, writer-actuation, output and exit replacement races now have deterministic coverage.
- **Upstream/native alternatives:** no custom terminal/state protocol added; existing TerminalManager/WebSocket primitives are reused.
- **Auth/security:** terminal auth remains the only gate; no new token, whitelist, remote argv/env, or LAN policy.
- **Regression/performance:** complete ordinary repository suite is fresh green. CPU/RSS/latency/release resource acceptance remains NOT_MEASURED.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C physical evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay continuity gate.
- PI-T005 COMPLETE.
- PI-T004 COMPLETE / committed.
- PI-T006: **clean REVIEW PASS candidate pending independent TEST**.
- PI-T007+ remain not authorized until PI-T006 independent TEST acceptance.
- runtime application wiring, browser F5/live reconnect, restart persistence/reopen, FJP physical input, real POSIX runtime, model/goal/extensions parity and release resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Findings

No concrete reproducible correctness defect remains in DEV turn 26.

The only findings are non-blocking dead-code reductions totaling approximately 16 lines.

## Route

**ROUTE TEST.** Independent TEST should reproduce:
- delayed old-generation output/exit delivery across same-ID replacement;
- replacement-generation isolation;
- attach/takeover/writer epoch race protections;
- Pi-create and generic-control ownership protections;
- output/session isolation and no duplicate delivery;
- auth reuse and ordinary Terminal compatibility;
- focused/full regressions as appropriate.

Do not unlock PI-T007/runtime/UI/persistence until independent TEST accepts PI-T006.

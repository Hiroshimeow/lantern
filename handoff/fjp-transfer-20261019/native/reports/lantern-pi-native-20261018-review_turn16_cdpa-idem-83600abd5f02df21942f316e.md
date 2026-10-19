# REVIEW turn 16 — verify generation-atomic ownership fix; create failure remains non-atomic

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 16  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `1282490f8bd1443b547c3b64b0b26813270ff837`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. R15-1 is fixed, but a separate reproducible PI-T004 failure-atomicity defect remains: a `TerminalManager.create_argv()` exception can occur after the terminal has already been published live, leaving an unowned PTY while the registry removes its session directory and records no session.

No implementation edits made by REVIEW.

## Inputs checked

- REVIEW turn 15 finding R15-1.
- DEV turn 16 handoff.
- Current changes:
  - `lantern/terminal.py`
  - `lantern/pi_sessions.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_sessions.py`
- Existing `TerminalManager.create()`, `kill()`, event/list publication, and new `kill_if_generation()`.
- Current branch/base/status.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 1282490f8bd1443b547c3b64b0b26813270ff837`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/5`.
- dirty paths remain exactly:
  - `M lantern/terminal.py`
  - `M tests/test_terminal_scm.py`
  - `?? lantern/pi_sessions.py`
  - `?? tests/test_pi_sessions.py`
- `git diff --check` passes.
- no WS/frontend/application/Markdown/dependency/vendor/LAN-security path changed.
- no PI-T006/007 work, browser attach, writer/takeover protocol, persistence, live :9999 action, or CDPA action was introduced.

## R15-1 — generation-atomic stop/close ownership: RESOLVED

The new `TerminalManager.kill_if_generation(term_id, expected_generation)`:
- takes the existing TerminalManager lock;
- verifies the live entry and expected generation while holding that lock;
- removes exactly that live entry before releasing the lock;
- then closes only the captured PTY;
- returns false without action when generation mismatches.

`PiSessionRegistry.stop()` and `close()` now call only this conditional primitive and no longer perform list/status observation followed by ID-only kill.

Fresh REVIEW tests:
- `test_stop_and_close_do_not_kill_replacement_generations`: PASS.
- `test_kill_if_generation_never_kills_replacement_generation`: PASS.
- 2/2 focused race tests PASS.
- full `tests.test_pi_sessions`: 7 PASS.
- `test_terminal_scm.py`: 23 PASS.
- `git diff --check`: PASS.

The original replacement-generation kill race from REVIEW turn 15 is therefore resolved.

## Finding R16-1 — registry create is not failure-atomic when TerminalManager fails after publishing the live entry

**Location**
- `lantern/pi_sessions.py:95-110` create exception handling.
- `lantern/terminal.py:493-502` live-entry publication / list event emission.

**Required invariant**
PLAN turn 10 requires:
- TerminalManager spawn failure leaves no live registry entry;
- create failure is atomic;
- registry must not leave half-created active state;
- cleanup must not kill terminals the registry did not create.

DEV turn 15 explicitly relied on the assumption that `TerminalManager.create_argv()` never publishes a live terminal before raising.

That assumption is false for exceptions after PTY creation/publication.

**Production behavior**
`TerminalManager.create()` currently:
1. creates the PTY;
2. creates `TerminalEntry`;
3. assigns `self.live[term_id] = entry`;
4. emits `terminal_list`;
5. returns metadata.

If the event callback raises at step 4, `create_argv()` propagates the exception even though the live terminal is already installed.

`PiSessionRegistry.create()` catches any exception, removes the new session directory if empty, and re-raises. It does not retain the generation/entry and cannot clean the terminal.

Result: registry has no session record, session directory is removed, but a live `pi:<sessionId>` PTY remains owned by nobody.

## Fresh deterministic reproduction

REVIEW used:
- real production `TerminalManager`;
- existing fake PTY backend only;
- an emit callback that raises on `terminal_list`.

Observed output:

`create_error emit failed`

`registry_sessions []`

`terminal_list [{'id': 'pi:orphan', ..., 'running': True, 'generation': '214cde968e3a47d99c0b1d78189a3b75'}]`

`session_dir_exists False`

The assertion that no live terminal remain after failed registry create failed.

This is a concrete failure-atomicity defect, not a speculative later PI-T006 concern.

## Required correction

Fix only the PI-T004 create atomicity boundary.

Preferred minimal direction:
- make `TerminalManager.create/create_argv` itself atomic with respect to exceptions after live-entry publication, rolling back the exact just-created generation before propagating the exception; or
- provide an equivalent narrow creation primitive that either returns a fully-published terminal or leaves no live/history terminal.

The cleanup must be generation-safe and must not kill a replacement generation.

Add a regression using a real TerminalManager whose emit/list callback raises after live publication and assert:
- registry create raises;
- registry list remains empty;
- session directory is removed when empty;
- no live/history terminal for that session remains;
- no unrelated terminal is touched.

Do not add PI-T006 writer/viewer policy, WS APIs, persistence, supervisor, application wiring, or broad process abstractions.

## Required review dimensions

- **Correctness:** R15-1 is resolved; R16-1 blocks PI-T004 acceptance.
- **Over-engineering/YAGNI:** current conditional-kill primitive is justified and narrow. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none.
- **Maintainability/module separation:** generation-safe destructive ownership belongs in TerminalManager. Create rollback should likewise be owned at the TerminalManager process boundary rather than guessed by registry metadata.
- **Scalability:** no new state/history framework introduced.
- **Native Pi parity:** unchanged; registry still uses accepted structured native spawn.
- **Concurrency isolation:** replacement-generation stop/close race fixed. Create failure atomicity remains broken.
- **Regression/performance:** focused registry/terminal tests are fresh green, but they do not cover this newly reproduced exception-after-publication path.
- **Security:** no remote/WS process surface introduced.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate.
- PI-T005 COMPLETE / accepted / committed.
- PI-T004: still not accepted due R16-1 failure atomicity.
- PI-T006/PI-T007+ remain not authorized.
- browser/FJP/real POSIX/resource/release items remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix R16-1 only: make structured terminal creation failure-atomic across exceptions after live publication, with generation-safe rollback and a deterministic regression. Do not start PI-T006/007 or application/WS/UI work.

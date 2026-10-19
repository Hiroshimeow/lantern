# REVIEW turn 18 — verify T8-1 context snapshot pre-spawn failure atomicity

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 18  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `1282490f8bd1443b547c3b64b0b26813270ff837`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **clean implementation review; ROUTE TEST** for independent PI-T004 re-acceptance. T8-1 is resolved and the previously fixed R15-1/R16-1 ownership/rollback boundaries remain intact. No implementation edits made by REVIEW.

## Inputs independently checked

- TEST turn 8 T8-1.
- DEV turn 18 handoff.
- Current PI-T004 implementation and tests:
  - `lantern/pi_sessions.py`
  - `tests/test_pi_sessions.py`
- Preserved prior PI-T004/TerminalManager corrections:
  - `lantern/terminal.py`
  - `tests/test_terminal_scm.py`
- Current Git state and full repository regression.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 1282490f8bd1443b547c3b64b0b26813270ff837`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/5`.
- current dirty paths remain exactly:
  - `M lantern/terminal.py`
  - `M tests/test_terminal_scm.py`
  - `?? lantern/pi_sessions.py`
  - `?? tests/test_pi_sessions.py`
- `git diff --check`: exit 0.
- no WS/frontend/application/Markdown/dependency/vendor/LAN-security path is dirty.
- no PI-T006/007, persistence, browser attach, writer/viewer/takeover, restart recovery, live Lantern :9999, or CDPA work was introduced.

## T8-1 — contextRef defensive-copy failure after spawn: RESOLVED

`PiSessionRegistry.create()` now performs:

`context_snapshot = deepcopy(context_ref)`

before:
- session ID allocation/collision work;
- native session-directory creation;
- TerminalManager collision checks that depend on the generated ID;
- `TerminalManager.create_argv()`.

The successful session record stores that already-created snapshot rather than performing a second caller-object copy after PTY spawn.

Therefore a context snapshot exception occurs before any registry-owned filesystem or PTY/process ownership starts.

The original TypeError is not wrapped or relabeled.

## Fresh targeted verification

Fresh four-test set:
- `test_context_snapshot_failure_happens_before_session_dir_or_spawn`: PASS.
- `test_real_terminal_create_emit_failure_rolls_back_published_generation`: PASS.
- `test_stop_and_close_do_not_kill_replacement_generations`: PASS.
- `test_kill_if_generation_never_kills_replacement_generation`: PASS.

Result:
- 4 tests;
- all OK;
- exit 0.

Full PI-T004 registry suite:
- 9 tests;
- all OK;
- 0.031 s;
- exit 0.

Focused Terminal suite:
- 23 tests;
- all OK;
- 2.623 s;
- exit 0.

Syntax/diff:
- `py_compile` for Terminal/registry/tests: exit 0.
- `git diff --check`: exit 0.

## Independent real-TerminalManager T8-1 probe

REVIEW reproduced the original TEST input with:
- real production `TerminalManager`;
- fake PTY backend only;
- `MappingProxyType({"path":"file.md"})`.

Observed:

`type_error cannot pickle 'mappingproxy' object`

`spawned [] sessions [] terminals [] dir_exists False`

Result:

`real_manager_context_failure_pre_spawn_ok`

So the unsupported/deepcopy-failing mapping now:
- preserves the original TypeError;
- causes zero PTY factory calls;
- leaves registry empty;
- leaves TerminalManager empty;
- creates no per-session state directory.

This directly closes T8-1 at the real manager boundary, not only through the fake registry manager.

## Supported context behavior remains intact

The existing registry suite continues to prove:
- nested supported context data is defensively copied at create;
- mutating the caller object after create does not retarget stored metadata;
- mutating returned views does not mutate stored metadata;
- same-document sessions remain independent;
- different-document contexts remain independently bound.

No context-retarget API or mutable global active-document state was added.

## Prior failure-atomicity / generation ownership fixes remain intact

R16-1:
- a post-publication TerminalManager exception rolls back the exact created entry;
- live/history references to that exact entry are removed;
- the created PTY is closed;
- unrelated terminals remain untouched.

R15-1:
- stop/close use generation-conditional kill;
- stale registry generation cannot kill a replacement generation.

Both boundaries are freshly covered by the targeted tests above.

## Fresh full repository suite

REVIEW ran:

`uv run python -m unittest discover -s tests -q`

with replay/native gated environment variables unset.

Result:
- **374 tests**
- **OK**
- **skipped=134**
- **52.545 s**
- exit 0.

Only the existing HTTPError ResourceWarning cleanup lines appeared. The worktree after the full run remained exactly the four expected PI-T004 candidate paths.

Skipped native/browser/physical tests remain skipped evidence, not PASS evidence.

## Review dimensions

- **Correctness:** T8-1 is independently reproduced as fixed; supported context copies, post-publication rollback and generation-safe stop/close remain green.
- **Over-engineering / YAGNI:** the correction is one pre-spawn snapshot and reuse of that snapshot. No cleanup framework, supervisor, retry layer, or duplicate process owner was added. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none into PI-T006/007, application/WS/browser, persistence, Markdown, LAN/security or Spec 001 T2.
- **Maintainability/module separation:** caller-data validation/snapshot occurs before process ownership; TerminalManager retains process rollback ownership; registry remains metadata-only.
- **Scalability:** no new persistent store or cleanup policy.
- **Native Pi parity:** registry still uses the already accepted structured native spawn seam; no new parity claim is made.
- **Concurrency isolation:** generation-safe destructive ownership remains intact; no writer/viewer/takeover claim is made.
- **Regression/performance:** complete ordinary repository suite is fresh green. CPU/RSS/latency/resource acceptance remains NOT_MEASURED.
- **Security:** no new remote process-control or argv/env surface.

## Findings

No concrete reproducible implementation defect remains in DEV turn 18.

PI-T004 is again a clean acceptance candidate:
- opaque identity;
- immutable defensive context snapshot;
- same/different-document session independence;
- exact native Pi session argv/session directory;
- TerminalManager-only PTY/status ownership;
- generation-safe stop/close;
- exact-entry create rollback;
- context snapshot failure before filesystem/process ownership;
- unrelated-terminal isolation;
- no premature PI-T006/007 architecture.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE Phase-0 replay gate.
- PI-T005 COMPLETE / accepted / committed.
- PI-T004: **PASS candidate pending independent TEST**.
- PI-T006/PI-T007+ remain not authorized until TEST acceptance.
- browser/FJP/real POSIX/resource/release items remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE TEST.** Independent TEST should re-run the corrected PI-T004 acceptance boundary, including the read-only context snapshot failure before spawn, post-publication TerminalManager rollback, replacement-generation protection, same/different-document isolation, exact native session argv/session-dir construction, and ordinary regressions. Do not unlock PI-T006/007 until that independent acceptance completes.

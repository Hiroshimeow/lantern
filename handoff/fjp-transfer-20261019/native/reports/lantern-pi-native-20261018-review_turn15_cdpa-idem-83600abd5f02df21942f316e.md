# REVIEW turn 15 — PI-T004 native Pi session registry

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 15  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `1282490f8bd1443b547c3b64b0b26813270ff837`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **ROUTE DEV**. The registry is otherwise narrow and contract-aligned, but stop/close ownership is not generation-atomic. A reproducible race lets a registry stop kill a replacement PTY generation that the registry did not create.

No implementation edits made by REVIEW.

## Inputs independently checked

- PLAN turn 10 PI-T004 contract in full.
- TEST turn 7 PI-T005 acceptance.
- DEV turn 15 handoff.
- New implementation:
  - `lantern/pi_sessions.py`
  - `tests/test_pi_sessions.py`
- Existing production `TerminalManager` generation/list/kill behavior.
- Current branch/base/status and accepted PI-T005 commit.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW checks:
- `HEAD = 1282490f8bd1443b547c3b64b0b26813270ff837`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/5`.
- accepted PI-T005 commit `1282490 feat(terminal): add structured native spawn` changes only:
  - `lantern/terminal.py`
  - `tests/test_pi_tui_e2e.py`
  - `tests/test_terminal_scm.py`
- current PI-T004 worktree candidate is only:
  - `?? lantern/pi_sessions.py`
  - `?? tests/test_pi_sessions.py`
- no application/WS/frontend/chatbot/Markdown/dependency/vendor/LAN-security path is dirty.
- `git diff --check` passes.

No PI-T006 writer/viewer/takeover/resize ownership, PI-T007 persistence/restart recovery, application wiring, browser attach, Pi-specific WS event, legacy bot removal, Spec 001 T2 IME fix, live Lantern :9999 action, CDPA action, reset/stash/clean/merge, or cross-owner implementation is present.

## PI-T004 behavior that REVIEW found correct

### Opaque identity / native session directory

Production default identity is `uuid4().hex`.

Registry terminal identity is derived only as:

`pi:<sessionId>`

and the Pi-native directory is:

`state_dir / sessionId`.

No path, tab ID, document title, cwd, context path, or filename slug participates in identity.

Session IDs are restricted to ASCII letters/digits/`-`/`_`, so the derived session directory cannot path-traverse.

### Exact Pi argv and structured-spawn ownership

The registry owns no process backend. It calls only the accepted:

`TerminalManager.create_argv(...)`

and appends exactly:
- `--session-id <sessionId>`
- `--session-dir <sessionDir>`
- `--tui-mode regular`

to the injected server-owned base argv.

It does not add:
- `--offline`;
- provider/model restrictions;
- hidden prompt/XML context;
- shell command strings;
- browser-controlled argv/env.

Returned views do not expose argv or env.

### Context immutability

`contextRef` is deep-copied into session metadata and deep-copied again on each view.

Focused tests mutate:
- the original nested caller context;
- a returned nested context view;

and later `get()` retains the creation-time value.

No retarget/update API or global active-document field is introduced.

### Same-document / different-document isolation

The tests prove two sessions with identical cwd/context receive distinct:
- session IDs;
- terminal IDs;
- PTY generations;
- native session directories.

Stopping A leaves B running.

Separate document context metadata stays independently bound and a mutated returned view does not alter either stored session.

### Metadata ownership

The registry stores only session metadata:
- opaque ID;
- terminal ID;
- generation;
- cwd;
- contextRef;
- cols/rows;
- session directory;
- title.

It stores no:
- terminal output;
- replay buffer;
- ANSI/xterm state;
- transcript;
- model list;
- slash-command list;
- attachment/writer state.

`running`, exit code and current geometry are derived from `TerminalManager.list()`, with terminal ID **and generation** matching required for status observation.

This avoids a second process-status truth source.

### Failure handling

Verified source behavior:
- generated/session-dir collision fails before spawn;
- existing terminal ID collision fails before spawn;
- session directory is created before native spawn;
- if `create_argv()` fails, the fresh empty session directory is removed where possible;
- no registry entry is inserted on failed spawn;
- cwd containment failure therefore leaves no listed session;
- no speculative kill is issued for a terminal that was never registered.

This matches the intended failure-atomic shape for ordinary create failures.

### YAGNI / module separation

No registry JSON database, restart persistence, supervisor, attach counter, writer role, resize ownership, session picker, extra process abstraction, or duplicate terminal history exists.

Ponytail complexity result: **Lean already. Ship.** No meaningful line deletion is justified within the authorized PI-T004 API.

## Fresh REVIEW verification

### Focused PI-T004

`uv run python -m unittest -v tests.test_pi_sessions`

Result:
- 6 tests;
- all 6 OK;
- 0.023 s;
- exit 0.

### PI-T005 / ordinary Terminal regression

`uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`

Result:
- 22 tests;
- OK;
- 2.526 s;
- exit 0.

### Syntax / diff

- `uv run python -m py_compile lantern\pi_sessions.py tests\test_pi_sessions.py`: exit 0.
- `git diff --check`: exit 0.

### Additional real-TerminalManager registry integration probe

REVIEW also constructed `PiSessionRegistry` over the real production `TerminalManager` with only the PTY process itself faked.

The probe independently verified:
- two registry sessions create through real `TerminalManager.create_argv`;
- exact native session flags are passed;
- generations differ;
- stopping one session leaves the other live;
- an unrelated ordinary terminal remains live after `stop()` and `close()`.

Result:

`real_terminal_registry_integration_ok`

This establishes that the unit fake is not merely restating the registry interface for the normal non-racing path.

## Finding R15-1 — generation ownership check and kill are TOCTOU, so stop/close can kill an unowned replacement generation

**Location:** `lantern/pi_sessions.py:136-149` (`stop()` and `close()`).

**Required invariant:** PLAN turn 10 requires:
- registry ownership to be identified by terminal ID **and stored PTY generation**;
- `stop()` / `close()` to affect only registry-owned terminal generations;
- no killing terminals the registry did not create.

The governing REVIEW directive also explicitly requires concurrency-isolation review.

**Current implementation:**

`stop()` does:
1. `_terminal_status(session)`, which calls `TerminalManager.list()` and confirms the stored generation;
2. releases that observation;
3. later calls `TerminalManager.kill(terminalId)` by ID only.

`close()` uses the same two-step pattern.

The generation check and destructive action are therefore not atomic.

### Fresh reproducible race against the real TerminalManager

REVIEW used the actual production `TerminalManager` with only its PTY backend replaced by the existing fake PTY, then deterministically paused `PiSessionRegistry.stop()` after it observed generation A.

While stop was paused:
1. the original `pi:raceA` generation A was removed;
2. a new terminal with the same terminal ID was created, producing generation B;
3. stop was resumed.

Fresh output:

- original generation: `0014b86d452c419797de330bc5df0f45`
- replacement generation: `8b8f480c2287485983e1431c5e210ca4`
- `replacement_survives False`

The proof assertion failed exactly because registry `stop()` called `kill("pi:raceA")` after generation B replaced generation A.

Thus a registry action can kill a terminal generation it does not own.

This is not a hypothetical browser-writer policy issue. It is an ownership primitive defect in the PI-T004 registry itself, and PI-T006 is expected to rely on this generation identity.

### Required correction

Make “check expected generation + kill” one TerminalManager-owned atomic operation.

The smallest acceptable shape is an internal conditional-kill seam such as:

`kill_if_generation(term_id, expected_generation)`

implemented under TerminalManager's existing lock, returning whether the expected generation was actually killed.

Equivalent generation-atomic ownership handling is acceptable, but do not:
- add writer/viewer/takeover policy;
- add WS events;
- add session attach logic;
- add a registry-wide process framework.

Both `stop()` and `close()` must use the same atomic ownership primitive.

Add a deterministic regression that replaces a terminal ID with a different generation between observation and requested stop/cleanup and proves the replacement generation survives.

PLAN turn 10 explicitly allowed a narrow `lantern/terminal.py` edit only when a concrete registry-blocking defect is found; this REVIEW provides that reproducible defect.

## Other required review dimensions

- **Over-engineering:** none found beyond the correctness issue above.
- **Scope drift:** none.
- **UX:** no browser/UI behavior exists in this slice, correctly.
- **Maintainability:** metadata ownership is clean; the destructive ownership action needs to move to an atomic TerminalManager primitive rather than duplicating terminal internals in the registry.
- **Scalability:** one native PTY and one native session directory per registry session is explicit. Registry metadata/state-dir growth has no invented cleanup policy, as required.
- **Native Pi parity:** registry uses the already accepted structured native spawn seam; another paid/native interaction run is not required for this metadata slice.
- **Concurrency isolation:** **blocked by R15-1**. Observation-only generation matching is good; destructive ownership is not atomic.
- **Regression/performance:** focused registry/Terminal tests are green. CPU/RSS/latency and release resource ceilings remain NOT_MEASURED.
- **Security:** registry remains server-internal; no WS create/list/stop surface, remote argv/env, LAN policy or auth change exists.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T003 COMPLETE for the accepted Phase-0 replay gate.
- PI-T005 COMPLETE / independently accepted / committed.
- PI-T004: implementation candidate has one blocking ownership-race defect R15-1.
- PI-T006/PI-T007 and later tasks remain not authorized.
- FJP physical input, browser F5/live release behavior, real POSIX process parity and resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Fix R15-1 only: make registry stop/close conditional on the expected PTY generation atomically and add the deterministic replacement-generation regression. Do not start PI-T006, application wiring, WS ownership, restart persistence, or UI work.

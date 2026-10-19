[Reading 1 lines from start (total: 1 lines, 0 remaining)]

# DEV turn 15 — preserve PI-T005; implement PI-T004 native Pi session registry

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope followed

Read PLAN turn 10 and executed only its authorized work:
1. preserve/commit the independently accepted PI-T005 structured native spawn seam;
2. implement PI-T004 only as a server-internal PiSessionRegistry with focused tests.

Not started:
- PI-T006 WS attach/writer/viewer/takeover/resize ownership;
- PI-T007 persistence/restart recovery;
- browser/UI integration;
- application wiring;
- legacy LanternBotManager removal/change;
- Pi-specific WS events;
- transcript/ANSI/model/slash-command duplication;
- Markdown implementation;
- Spec 001 T2 IME fix;
- LAN/security/auth/quota work;
- live Lantern :9999 actions;
- CDPA changes.

## Housekeeping — PI-T005 accepted slice

Incoming dirty paths matched PLAN exactly:
- lantern/terminal.py
- tests/test_terminal_scm.py
- tests/test_pi_tui_e2e.py

Fresh `git diff --check` was clean.

Selectively staged only those three paths and committed:
- `1282490 feat(terminal): add structured native spawn`

Current local main did not advance, so no further rebase was required.

Post-commit base:
- HEAD: 1282490f8bd1443b547c3b64b0b26813270ff837
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/5

## PI-T004 implementation

New uncommitted candidate files only:
- lantern/pi_sessions.py
- tests/test_pi_sessions.py

No existing production module was modified for PI-T004.

### Registry ownership model

`PiSessionRegistry` is server-internal and constructed with:
- project root;
- server-owned state directory;
- existing TerminalManager instance;
- server-owned base Pi argv;
- optional server-owned env overlay;
- optional id_factory for deterministic tests.

Production default session identity uses `uuid4().hex`.

Registry state is metadata only. It does not store:
- PTY output;
- replay history;
- ANSI/xterm state;
- prompt transcript;
- model catalog;
- slash-command catalog;
- browser attachment state.

TerminalManager remains the only PTY/process/output/replay owner.

### Session creation behavior

Each create:
- generates an opaque sessionId;
- derives terminalId only as `pi:<sessionId>`;
- creates a unique native Pi session directory under state_dir named by sessionId;
- constructs exact structured argv as injected base argv plus:
  - `--session-id <sessionId>`;
  - `--session-dir <sessionDir>`;
  - `--tui-mode regular`;
- does not add `--offline`, model/provider/tool restrictions, XML prompts, or hidden keystrokes;
- calls only `TerminalManager.create_argv()`;
- passes optional server-owned env through that accepted seam;
- stores returned PTY generation and immutable creation metadata;
- returns a sanitized view without argv/env.

ContextRef is deep-copied on create and deep-copied on every returned view, so caller mutations cannot retarget the registry session.

### Identity / lifecycle behavior

- Session identity is independent of path/tab/title/cwd.
- Two sessions for the same document/context remain distinct by sessionId, terminalId, PTY generation and native session directory.
- Different document contexts remain independently bound to creation metadata.
- `get()` and `list()` derive current running/exit state from TerminalManager.list(), not a registry process-status cache.
- PTY generation must match the stored generation before registry treats a terminal as its current process.
- `stop()` keeps stopped session metadata listable but only kills the matching registry-owned live terminal.
- repeated `stop()` is idempotent with respect to kill calls.
- `close()` only kills matching live terminal generations owned by this registry and never calls TerminalManager.kill_all().
- unrelated ordinary terminals are untouched.

### Failure atomicity

- invalid/generated session IDs are rejected before spawn;
- registry/session-directory collision is rejected before spawn;
- an existing TerminalManager terminal ID collision is rejected before spawn;
- native session directory is created before spawn and removed if TerminalManager.create_argv() fails;
- failed cwd containment/spawn does not add a registry session;
- failed create does not issue a speculative kill for a terminal that never existed.

Ruling: on create_argv exception, registry removes only its freshly-created empty session directory and does not call terminal.kill. TerminalManager.create_argv does not publish a live entry before its spawn boundary succeeds, and speculative kill could target a terminal the registry never created. Cost if this assumption changes later: TerminalManager would need an explicit atomic spawn/rollback contract rather than registry guessing.

## TDD evidence

Initial RED:
- `tests.test_pi_sessions` failed to import because `lantern.pi_sessions` did not exist.

After first implementation, focused tests found a real cleanup defect:
- outside-cwd failure recorded a kill for `pi:outside` even though no terminal had been created.

Fix:
- removed speculative terminal.kill from create failure cleanup.

Second RED for lifecycle idempotence:
- repeated stop produced duplicate kill calls.

Fix:
- stop/close now kill only matching TerminalManager entries whose current status is running.

## PI-T004 acceptance tests

`tests/test_pi_sessions.py` has 6 focused tests covering:
- opaque identity and path/title independence;
- exact Pi argv/session-id/session-dir/tui-mode construction;
- no production `--offline` injection;
- argv/env sanitization from returned views;
- nested contextRef defensive copies;
- same-document two-session independence;
- stop isolation and idempotence;
- different-document creation-context immutability;
- spawn failure atomicity and session-dir cleanup;
- generated-ID collision rejection without overwrite;
- cwd containment failure without registry entry;
- close ownership isolation from ordinary terminals;
- running/exit status following TerminalManager rather than registry cache.

## Verification actually run

Final PI-T004 focused:
- `uv run python -m unittest -q tests.test_pi_sessions`
- 6 tests OK in 0.026s

PI-T005 / ordinary terminal regression:
- `uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`
- 22 tests OK in 2.565s

Native Pi production structured seam regression:
- `LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`
- 1 test OK in 9.994s
- no paid AI prompt

PI-T003 replay continuity regression:
- `LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`
- 7 tests OK in 10.235s

Syntax/diff:
- `uv run python -m py_compile lantern\pi_sessions.py tests\test_pi_sessions.py` -> exit 0
- `git diff --check` -> exit 0

Fresh full repository suite after final idempotence fix:
- `uv run python -m unittest discover -s tests -q`
- Ran 370 tests in 45.743s
- OK, skipped=134
- existing ResourceWarning HTTPError cleanup lines only
- evidence: `.plan/lantern-pi-native-20261018/evidence-turn15/full-unittest-final.err`

## Final repository state

Fresh status:
- HEAD: 1282490f8bd1443b547c3b64b0b26813270ff837
- main: 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b
- main...HEAD = 0/5
- only uncommitted candidate paths:
  - `?? lantern/pi_sessions.py`
  - `?? tests/test_pi_sessions.py`
- package/lock files unchanged;
- no Markdown-owner path dirty.

No PI-T004 commit was made because this new registry slice still requires independent REVIEW/TEST.

## NOT_MEASURED / deferred boundaries

Spec 001:
- T1 COMPLETE / accepted / committed;
- T0-C physical >=50-attempt four-channel evidence NOT_MEASURED / deferred;
- T2 BLOCKED;
- no terminal/IME product fix.

Spec 004:
- PI-T002 accepted narrow native PTY proof;
- PI-T003 accepted Phase-0 bounded same-geometry replay continuity gate;
- PI-T005 accepted/committed structured native spawn seam;
- PI-T004 is now a REVIEW candidate only;
- PI-T006/PI-T007+ not started.

Still NOT_MEASURED / INCOMPLETE:
- browser attach/F5/live WS behavior;
- one-writer/multi-viewer/takeover/resize ownership;
- restart persistence/reopen;
- real two-registry-session installed-Pi process integration (optional for this slice; unit contract only);
- real POSIX runtime process execution;
- FJP physical UniKey/IME/AltGr/image paste;
- live model/goal/extensions parity;
- CPU/RSS/latency/resource acceptance.

## REVIEW request

Independent REVIEW must explicitly assess:
- opaque session identity independent of path/tab/title/cwd;
- same-document and different-document isolation;
- deep context immutability;
- exact native Pi argv/session-dir construction through TerminalManager.create_argv only;
- no duplicate PTY/output/replay/history ownership;
- status truth comes from TerminalManager generation/state;
- stop/close ownership isolation and idempotence;
- collision/spawn/cwd failure atomicity;
- YAGNI: no premature WS attach/writer/persistence/supervisor framework;
- one-PTY-per-session scalability implications without inventing cleanup policy;
- no application/legacy bot/WS/browser/security/Markdown scope drift;
- focused/full regression evidence.

Route: REVIEW.
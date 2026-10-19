# REVIEW turn 14 — PI-T005 structured native spawn seam

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 14  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `4a03fa9d15803d0adfdd2a28124012d6439e9cb7`  
Main reviewed: `4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`  
Disposition: **clean implementation review; ROUTE TEST** for independent PI-T005 acceptance. No implementation edits made by REVIEW.

## Inputs independently checked

- PLAN turn 9 PI-T005 contract in full.
- TEST turn 6 acceptance of PI-T003 continuity.
- DEV turn 14 handoff.
- Actual current diff in:
  - `lantern/terminal.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_tui_e2e.py`
- Current branch/base/status and scope.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / preservation truth

Fresh REVIEW checks:
- `HEAD = 4a03fa9d15803d0adfdd2a28124012d6439e9cb7`.
- `main = 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b`.
- `main...HEAD = 0/4`.
- current uncommitted PI-T005 candidate changes exactly:
  - `lantern/terminal.py`
  - `tests/test_terminal_scm.py`
  - `tests/test_pi_tui_e2e.py`
- no WS/frontend/application/chatbot, Markdown-owner, dependency, vendor, LAN/security, or unrelated path is dirty.
- `git diff --check` passes.

The previously accepted PI-T003 continuity slice is now committed/rebased in branch history. No current PI-T005 diff crosses that accepted ownership boundary.

No reset/stash/clean/merge, live Lantern :9999 action, CDPA action, PI-T004 registry, PI-T006 writer/takeover protocol, PI-T007 lifecycle, Pi-specific WS event, browser argv/env exposure, Spec 001 T2 IME fix, or Markdown implementation is present in this slice.

## PI-T005 API shape

The implementation adds a generic server-internal structured spawn seam without changing the browser/WS API.

`TerminalManager.create()` now accepts keyword-only:
- `argv`
- `env`

and `create_argv()` is a narrow convenience entry point over that same implementation.

Validation is performed before PTY spawn:
- command + argv: rejected;
- empty argv: rejected;
- bare string/bytes argv: rejected;
- non-string argv entries: rejected;
- env without argv: rejected;
- non-string env key/value: rejected;
- cwd still passes through the existing configured-root containment path.

Structured argv is copied to a list and passed to the native PTY path unchanged. It is not shell-quoted or serialized into a command string.

Ordinary interactive shell creation and `run_command()` remain on the existing shell-resolution/wrapping path.

## Exact argv / no shell wrapping

`TerminalManager._spawn_native()` has two paths:

1. legacy shell path:
   - current `resolve_shell()`;
   - existing bash/posix `-lc`, cmd `/D /S /C`, or PowerShell `-NoProfile -Command` behavior for ordinary command strings;

2. structured argv path:
   - `spawn_argv = list(argv)`;
   - no shell resolution or wrapper is inserted.

Focused tests include spaces, Japanese text, embedded quotes, `&`, `;`, and apostrophes and assert the exact element list reaches the injected spawn boundary unchanged.

The real G6 Pi proof uses `create_argv()` through the normal production `TerminalManager._spawn_native` owner rather than the prior test-only Pi PTY closure.

No shell wrapper is present in the Pi argv.

## Environment contract

A single shared `_build_pty_env()` now owns the child environment construction for both `WinConPty` and `PosixPty`.

It:
- makes a fresh `os.environ.copy()`;
- preserves inherited variables;
- retains existing `TERM=xterm-256color` and `LANG=en_US.UTF-8` defaults when absent;
- applies the explicit structured overlay last, so caller overrides win intentionally;
- validates string keys/values;
- does not mutate `os.environ`.

Both native backends take the same optional overlay parameter.

Tests independently establish:
- defaults when the parent env is empty;
- inherited values survive;
- explicit TERM override wins;
- Unicode overlay remains exact;
- child-dict mutation does not affect parent env;
- WinConPty and PosixPty dispatch receive the same argv/env contract.

Real POSIX PTY execution remains correctly NOT_MEASURED on this Windows-only review; only the shared dispatch/construction contract is unit-covered.

## Metadata / security boundary

No argv/env field is added to:
- terminal metadata;
- terminal list events;
- replay/output events;
- browser terminal_create / terminal_run messages.

The existing WS dispatch was not modified.

This keeps structured process creation server-internal and does not create a new remote arbitrary-process/env attack surface.

No env values are logged or asserted through metadata.

## Existing factory compatibility

Ordinary `create()` with no structured argv/env still calls injected `pty_factory` using the legacy positional signature ending in `command`.

`run_command()` also preserves that legacy test/factory contract.

Only structured-spawn calls require the extended keyword arguments, which is appropriate for the new server-internal seam.

No second PTY manager or process framework was introduced.

## Production Pi seam proof

The gated native Pi test now:
- constructs the previously characterized installed Pi 1.3.0 native argv;
- keeps offline/no-paid-prompt operation;
- uses a normal `TerminalManager` with its production spawn owner;
- calls `create_argv()`;
- uses a harmless server-owned environment overlay;
- verifies argv/env are absent from returned metadata;
- retains native settings/resume/local-shell/Unicode/new/session/resize/cleanup assertions.

Fresh REVIEW execution:

`LANTERN_PI_TUI_E2E=1 uv run python -m unittest -q tests.test_pi_tui_e2e`

Result:
- 1 test;
- OK;
- 10.264 s;
- exit 0.

This is direct evidence that the structured seam launches the real installed native Pi through production TerminalManager/WinConPty ownership on G6.

## Fresh REVIEW regression verification

Focused structured/terminal suite:

`uv run python -m unittest discover -s tests -p test_terminal_scm.py -q`

Result:
- 22 tests;
- OK;
- 4.275 s;
- exit 0.

PI-T003 regression after TerminalManager changes:

`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -q tests.test_pi_reconnect_e2e`

Result:
- 7 tests;
- OK;
- 12.666 s;
- exit 0.

Ordinary UI + LAN/multi-client regression:

`uv run python -m unittest -q tests.test_terminal_ui tests.test_lan_multi_perf`

Result:
- 32 tests;
- OK;
- 5.935 s;
- exit 0.

Syntax / diff:
- `uv run python -m py_compile lantern\terminal.py tests\test_terminal_scm.py tests\test_pi_tui_e2e.py`: exit 0.
- `git diff --check`: exit 0.

The first combined verification command exceeded the device-tool timeout after already showing the 22-test Terminal suite and 1-test native Pi proof complete and green; REVIEW reran the remaining commands separately to obtain complete exit statuses. No claim relies on the timed-out wrapper.

DEV also reports a full 364-test suite PASS. REVIEW did not repeat that expensive full suite because the production slice is isolated to the native spawn seam and the relevant focused, Pi-native, replay-continuity, UI/LAN, syntax and diff checks were freshly completed here.

## Required review dimensions

- **Correctness:** exact structured argv, cwd containment, mutual exclusion, env overlay, backend dispatch and production Pi launch are supported by fresh evidence.
- **Over-engineering / YAGNI:** no generic process framework, registry, policy layer, second PTY owner, duplicate history or dependency was introduced. `create_argv()` is a thin convenience over the single `create()` implementation and is justified as the explicit future registry entry point. Ponytail result: **Lean already. Ship.**
- **Scope drift:** none into PI-T004/006/007, browser process controls, Markdown implementation, LAN/security, or Spec 001 T2.
- **UX:** no browser-facing behavior changed in PI-T005.
- **Maintainability/module separation:** environment construction is centralized once at the common PTY ownership layer; platform-specific PTYs remain their existing owners.
- **Scalability/extensibility:** future registry can launch native Pi without shell parsing while ordinary terminals remain unchanged; no speculative registry/session model is present.
- **Native Pi parity:** G6 real native Pi execution through the production seam is measured. Real POSIX runtime and FJP physical interaction remain NOT_MEASURED.
- **Concurrency isolation:** unchanged; PI-T005 does not claim writer/viewer/takeover or resize-owner semantics.
- **Security boundary:** argv/env stay server-internal; no WS remote spawn surface was added.
- **Regression/performance:** relevant focused regressions are fresh green. CPU/RSS/latency/resource acceptance remains NOT_MEASURED.

## Findings

No concrete reproducible implementation defect found in DEV turn 14.

PI-T005 is a clean **acceptance candidate**:
- structured argv reaches native PTY without shell re-parsing;
- structured env overlays the child only;
- ordinary shell behavior and injected factory compatibility remain intact;
- real G6 native Pi uses the production seam;
- no remote/browser attack surface is added.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T002 COMPLETE for narrow native TerminalManager/WinConPty proof.
- PI-T003 COMPLETE for Phase-0 bounded same-geometry replay feasibility/continuity gate; browser F5/live/release acceptance remains later.
- PI-T005: **PASS candidate pending independent TEST**.
- PI-T004 remains next only after PI-T005 independent acceptance.
- PI-T006/PI-T007 and later work remain not authorized in this review.
- physical FJP, real POSIX runtime, resource/performance acceptance and broader release parity remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Route

**ROUTE TEST.** Independent TEST should reproduce the structured argv/env contract, ordinary shell/factory compatibility, real G6 Pi production-seam launch, metadata/WS non-exposure, and focused regressions before PLAN authorizes PI-T004.

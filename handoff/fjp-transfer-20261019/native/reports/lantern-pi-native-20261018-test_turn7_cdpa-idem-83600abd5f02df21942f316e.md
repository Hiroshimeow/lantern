# TEST turn 7 — PI-T005 independent structured native spawn acceptance

Task: cdpa-idem-83600abd5f02df21942f316e. Handoff: review_turn14. Workspace: E:\git-project\lantern\.wt\lantern-bot. Role TEST. **ROUTE PLAN.** Narrow PI-T005 PASS candidate independently reproduced. No implementation edit.

## Identity and preservation
Device desktop-b5e4iue-87cea2af, DESKTOP-B5E4IUE, Microsoft Windows NT 10.0.26100.0; broker-resolved working directory E:\git-project\lantern\.wt\lantern-bot. uv 0.11.8; Node v22.22.2; Python 3.14.1. Device date 2026-10-19 02:54–02:56 +09:00. Branch feat/lantern-bot, HEAD 4a03fa9d15803d0adfdd2a28124012d6439e9cb7, main 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b, merge base main, main...HEAD = 0 left/4 right.
Only M lantern/terminal.py, M tests/test_terminal_scm.py, M tests/test_pi_tui_e2e.py; no WS/browser, dependency/vendor, Markdown, registry/session, auth/LAN or unrelated dirty changes. git diff --check exit 0. No resets/stashes/cleans, merges/rebases, commits/pushes, live Lantern :9999 or CDPA action.

Environment/identity commands executed in verified working directory (PowerShell):
    Get-Location; hostname; [System.Environment]::OSVersion.VersionString; Get-Date -Format o
    uv --version; node --version; uv run python --version
    git branch --show-current; git rev-parse HEAD; git rev-parse main; git merge-base main HEAD
    git rev-list --left-right --count main...HEAD; git status --short; git diff --check
    git diff --name-only; git diff --stat; git log --oneline HEAD..main; git log --oneline main..HEAD
    git diff -- lantern/terminal.py; git diff -- tests/test_pi_tui_e2e.py
Expected allowed three files and preserved branch; actual exactly these files, +256/-31, no unexpected paths, diff check exit 0.

## Actual native Pi production seam
Command:
    $env:LANTERN_PI_TUI_E2E='1'
    uv run python -m unittest -v tests.test_pi_tui_e2e
    $code=$LASTEXITCODE; Write-Output ('PI_T005_NATIVE_E2E_EXIT='+$code); exit $code
Expected enabled real WinConPty/native installed Pi offline through production TerminalManager structured create_argv; no custom PTY factory, shell wrapper or paid prompt; retained native settings/resume/new/Unicode/shell/resize/cleanup. Actual test_terminal_manager_hosts_native_pi_tui_without_shell_wrapping OK; **1/1 run, 0 skipped, 10.057s, exit 0**.
Inspected exact native test diff: previous special pty_factory removed; manager uses default bound production factory; invokes create_argv with structured native Pi argv and harmless server-owned environment overlay; asserts argv/env not in returned metadata and no -Command, /C, -lc wrapper.

## Production and contract inspection
Read implementation diff: TerminalManager.create gained keyword-only argv/env; create_argv delegates to same owner; validates no command+argv, nonempty sequence of strings, string-valued env, env only with argv, and safe rooted cwd before spawning. _spawn_native passes argv list unchanged to platform PTY; ordinary shell path continues resolve_shell and existing command wrappers. Existing factories invoked with legacy positional signature for ordinary shells; structured calls use extended kwargs. A single shared _build_pty_env copies os.environ, applies TERM and LANG defaults and then explicit overlay. Both WinConPty and PosixPty receive same generic overlay contract. No metadata/WS/browser env or argv exposure; no Pi-specific service or protocol.
Focused test source contains metacharacter/Unicode exact argv, env/default/inheritance/parent immutability, malformed argv/env, cwd containment, backend dispatch, ordinary factory/command compatibility. Actual native POSIX runtime NOT_MEASURED on Windows.

## Focused regressions and syntax
Commands:
    Remove-Item Env:LANTERN_PI_TUI_E2E -ErrorAction SilentlyContinue
    uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
    uv run python -m unittest -q tests.test_terminal_ui tests.test_lan_multi_perf
    uv run python -m py_compile lantern/terminal.py tests/test_terminal_scm.py tests/test_pi_tui_e2e.py
    git diff --check
Expected all green. Actual SCM **22 OK, 3.956s exit 0**; UI/LAN **32 OK, 5.584s exit 0**; compile exit 0; diff check exit 0.
Continuity regression command:
    $env:LANTERN_PI_REPLAY_E2E='1'; uv run python -m unittest -q tests.test_pi_reconnect_e2e
    $code=$LASTEXITCODE; Write-Output ('REPLAY_EXIT='+$code); exit $code
Expected seven enabled PI-T003 proof cases. Actual **7 OK, 10.618s, exit 0**.
Full repository suite was NOT independently run this turn; DEV's reported 364-suite success is prior-role evidence, not TEST PASS.

## Acceptance
PI-T005 PASS candidate narrowly for server-internal structured argv/cwd/env native spawn on G6 plus common cross-platform dispatch unit tests; old shell/factory behavior preserved and no new remote argv/env surface. No reproducible implementation defect found. Real POSIX child execution, physical FJP IME/UniKey/AltGr/image paste, browser F5/live replay, writer/viewer isolation, model/goal/extension parity and resource/CPU/RSS/latency NOT_MEASURED or INCOMPLETE. Spec 001 T1 accepted, T0-C >=50-attempt gate NOT_MEASURED/deferred, T2 BLOCKED; no IME fix. PI-T004 not implemented; PI-T006+ dependent; overall goal NOT DONE.
**ROUTE PLAN** for PI-T005 disposition and authorized next dependency slice. Preserve unrelated work.
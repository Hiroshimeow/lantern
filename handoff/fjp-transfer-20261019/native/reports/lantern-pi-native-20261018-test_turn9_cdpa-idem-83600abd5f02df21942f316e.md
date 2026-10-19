# TEST turn 9 — PI-T004 reacceptance after T8-1 correction

Task: cdpa-idem-83600abd5f02df21942f316e
Role: TEST turn 9
Incoming: .plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn18_cdpa-idem-83600abd5f02df21942f316e.md
Workspace: E:\git-project\lantern\.wt\lantern-bot

**Disposition: ROUTE PLAN.** PI-T004 passes the independently tested *server-internal registry* boundary, including the former T8-1 pre-spawn failure. No implementation defect reproduced. This is a PASS candidate for PLAN, not F5/live/browser/release acceptance.

## Device, source, scope and preservation

Verified owned device desktop-b5e4iue-87cea2af (DESKTOP-B5E4IUE, Microsoft Windows NT 10.0.26100.0), device-broker-resolved working directory E:\git-project\lantern\.wt\lantern-bot. uv 0.11.8; Node v22.22.2; Python 3.14.1. Observed local time 2026-10-19T03:44:15.5048141+09:00 to 2026-10-19T03:46:19.9810455+09:00.

Branch feat/lantern-bot, HEAD 1282490f8bd1443b547c3b64b0b26813270ff837, main/merge-base 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b, main...HEAD = 0 left/5 right.

Worktree remained exactly M lantern/terminal.py; M tests/test_terminal_scm.py; ?? lantern/pi_sessions.py; ?? tests/test_pi_sessions.py. No Markdown, application, WS/browser, security/LAN, dependency/vendor or other implementation path dirty. No reset/stash/clean, rebase/merge/push/commit, live Lantern :9999 restart/attach, CDPA interaction or production source edit by TEST.

Source SHA256 (certutil -hashfile): lantern/pi_sessions.py = 165ea22b26be53a24c3115e7fc950a83fcec49ba010790903d9913999abd6641; tests/test_pi_sessions.py = 8f8187e8391e3ff72197a67f778d24d4efc7474238c59ae07b1101df8564b1f6; lantern/terminal.py = 0f35f4176c74eeceb45f64c7e37efa786ba09f133baaf19dedc96e44cb66cff3; tests/test_terminal_scm.py = 40103419716fdb21c9cf82285fd3f5fdb60832c96dc1533ae0e9a213b92e514c.

Executed PowerShell identity/source commands in verified directory:

    Get-Location; hostname; [System.Environment]::OSVersion.VersionString
    Get-Date -Format o; uv --version; node --version; uv run python --version
    git branch --show-current; git rev-parse HEAD; git rev-parse main
    git merge-base main HEAD; git rev-list --left-right --count main...HEAD
    git status --short; git diff --name-only; git diff --stat; git diff --check
    git log --oneline main..HEAD; Get-Content lantern/pi_sessions.py
    Select-String -Path tests/test_pi_sessions.py -Pattern 'def test_context_snapshot_failure_happens_before_session_dir_or_spawn' -Context 0,50
    certutil -hashfile lantern/pi_sessions.py SHA256
    certutil -hashfile tests/test_pi_sessions.py SHA256
    certutil -hashfile lantern/terminal.py SHA256
    certutil -hashfile tests/test_terminal_scm.py SHA256

Expected only four PI-T004 paths and unchanged accepted feature history. Actual exactly those paths; git diff --check exit 0. Untracked modules independently compiled and executed.

## Direct T8-1 reproduction — corrected

Inspection confirms lantern/pi_sessions.py line 75 runs context_snapshot = deepcopy(context_ref) BEFORE id_factory, directory creation and TerminalManager.create_argv at line 97. The session record stores that snapshot at line 118, avoiding a second caller-object copy after spawn.

TEST independently executed a disposable Python stdin probe with **real TerminalManager and fake PTY only**, plus an unrelated ordinary live terminal. It attempted two unsupported defensive-copy inputs: MappingProxyType({'path':'file.md'}) (original T8-1), and a nested MappingProxyType inside a normal dict. In both, deepcopy throws original TypeError, but the failure must precede registry-owned PTY, directory, identity allocation and leave the unrelated terminal unchanged.

The exact shell invocation used was:

    $py = @'
    [one-shot Python source; real TerminalManager, fake Pty, two MappingProxyType cases]
    '@
    $py | uv run python -
    $rc=$LASTEXITCODE
    Write-Output ('INDEPENDENT_T8_1_PRESPAWN_EXIT='+$rc)
    exit $rc

Core asserted conditions were:
    len(ids)==0
    len(spawned)==1              # solely pre-existing ordinary terminal
    reg.list()==[]
    not (state/'blocked').exists()
    list(manager.live)==['ordinary']
    manager.live['ordinary'].generation==ordinary['generation']
    not spawned[0][1].closed

Expected safe rejection/unchanged state. Actual **INDEPENDENT_T8_1_PRESPAWN_EXIT=0**:
    {"failed_session_directory_exists":false,"identity_factory_calls":0,"mappingproxy_errors":["cannot pickle 'mappingproxy' object","cannot pickle 'mappingproxy' object"],"ordinary_generation_unchanged":true,"ordinary_pty_alive":true,"registry_size":0,"spawn_count_including_ordinary":1}

This exit 0 is positive *safe-rejection* evidence, not a claim that MappingProxyType copying succeeded. The T8-1 orphaned PTY/dir is no longer reproducible. The original TypeError is preserved and no server-owned session identity allocation occurred.

## Fresh independent happy-path ownership probe

A separate ephemeral Python stdin script, again using production TerminalManager and fake PTYs, created one ordinary terminal plus three registry sessions (two for the same document, one for another). Exact native structured argv with --session-id, --session-dir and --tui-mode regular was verified along with injected env, no shell command, distinct session IDs/generations/directories, deep context-copy isolation, stop of only A, stale stop after replacing C's terminal generation, twice-safe close and unrelated terminal survival.

Invocation used the same exact PowerShell pattern:

    $py = @'
    [real TerminalManager three-session identity, argv, context and ownership assertions]
    '@
    $py | uv run python -
    $rc=$LASTEXITCODE
    Write-Output ('INDEPENDENT_REAL_MANAGER_REGISTRY_EXIT='+$rc)
    exit $rc

Expected all assertions true. Actual **exit 0**:
    {"sessions":3,"exact_argv_and_env":true,"deep_context_isolation":true,"stop_isolated":true,"stale_replacement_preserved":true,"ordinary_terminal_preserved":true,"close_twice_safe":true}

These are synthetic PTYs; actual simultaneous multi-native-Pi resource/concurrency evidence remains NOT_MEASURED.

## Test commands and measured outcomes

All run on the verified G6 device in the exact workspace.

A. Registry suite:

    uv run python -m unittest -v tests.test_pi_sessions
    $rc=$LASTEXITCODE; Write-Output ('REGISTRY_SUITE_EXIT='+$rc); exit $rc

Expected 9 actual tests. Actual **9 run, 9 OK, 0 skipped, 0.062s, exit 0**. Includes T8-1 regression, exact argv/context, same/different document sessions, cwd/collision/spawn failure, status, exact-entry post-publication rollback and stale-generation stop/close.

B. Targeted four ownership/failure cases:

    uv run python -m unittest -v tests.test_pi_sessions.PiSessionRegistryTests.test_context_snapshot_failure_happens_before_session_dir_or_spawn tests.test_pi_sessions.PiSessionRegistryTests.test_real_terminal_create_emit_failure_rolls_back_published_generation tests.test_pi_sessions.PiSessionRegistryTests.test_stop_and_close_do_not_kill_replacement_generations tests.test_terminal_scm.TerminalParityTests.test_kill_if_generation_never_kills_replacement_generation
    $rc=$LASTEXITCODE; Write-Output ('TARGET_FOUR_EXIT='+$rc); exit $rc

Expected 4/4. Actual **4 run, 4 OK, 0.018s, exit 0**. T8-1, R16-1 and R15-1 remain green.

C. Terminal syntax/regression:

    uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
    uv run python -m py_compile lantern/terminal.py lantern/pi_sessions.py tests/test_terminal_scm.py tests/test_pi_sessions.py
    git diff --check

Expected all exit 0. Actual **23 terminal tests OK, 4.561s**, py_compile exit 0, git diff --check exit 0.

D. Native Pi structured-spawn regression, explicit gate enabled:

    $env:LANTERN_PI_TUI_E2E='1'
    uv run python -m unittest -v tests.test_pi_tui_e2e
    $rc=$LASTEXITCODE; Write-Output ('NATIVE_PI_E2E_EXIT='+$rc); exit $rc

Actual **1 run, 1 OK, 0 skips, 10.005s, exit 0**; production G6 WinConPty native Pi without paid prompt. This does not imply PI-T004 production concurrent Pi instance acceptance.

E. PI-T003 replay boundary, explicit gate enabled:

    $env:LANTERN_PI_REPLAY_E2E='1'
    uv run python -m unittest -v tests.test_pi_reconnect_e2e
    $rc=$LASTEXITCODE; Write-Output ('PI_T003_REPLAY_EXIT='+$rc); exit $rc

Actual **7 run, 7 OK, 0 skips, 11.031s, exit 0**, preserving historical negative replay representations.

F. Fresh complete ordinary suite, retained device process:

    Remove-Item Env:LANTERN_PI_TUI_E2E -ErrorAction SilentlyContinue
    Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
    uv run python -m unittest discover -s tests -q
    $rc=$LASTEXITCODE; Write-Output ('FULL_SUITE_EXIT='+$rc); exit $rc

Actual **374 tests, OK, skipped=134, 54.816s, exit 0**. Existing ResourceWarning temporary HTTPError cleanup messages only; 134 skipped checks do NOT count as PASS. Gated suites D/E were executed separately above.

## Acceptance and route

PI-T004 is independently **PASS as a narrow server-internal registry candidate**: opaque session ID/terminal generation and native directory, exact server-owned argv/env, immutable context snapshot, same/different-document isolation, TerminalManager as PTY and status owner, safe failure before spawn for unsupported mapping, rollback of post-publication failure, generation-safe stop/close, and isolation from ordinary terminals. No new registry database/transcript, application wiring, client attach/writer protocol or persistence. No reproducible implementation defect found.

Spec 001 T1 previously accepted; T0-C >=50 physical four-channel evidence NOT_MEASURED/deferred; T2 BLOCKED and no IME product fix. PI-T003 Phase-0 and PI-T005 previously accepted and freshly regressed. PI-T006/007+ not authorized by TEST. Browser F5/live reconnect, writer-viewer takeover and resize owner, persistence/restart, FJP physical UniKey/IME/AltGr/image paste, real POSIX, live model/goal/extensions parity, CPU/RSS/latency release criteria remain **INCOMPLETE or NOT_MEASURED**, not PASS.

Overall objective NOT DONE. **ROUTE PLAN** for PI-T004 disposition and dependency-ordered next slice; preserve four-file candidate and all unrelated work.
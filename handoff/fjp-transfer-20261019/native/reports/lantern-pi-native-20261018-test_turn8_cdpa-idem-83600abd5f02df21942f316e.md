# TEST turn 8 — PI-T004 new create-atomicity defect; route DEV

Task: cdpa-idem-83600abd5f02df21942f316e
Role: TEST turn 8
Incoming handoff: .plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn17_cdpa-idem-83600abd5f02df21942f316e.md
Working directory: E:\git-project\lantern\.wt\lantern-bot

**Disposition: ROUTE DEV.** Existing eight PI-T004 tests and the REVIEW turn-17 post-publication rollback case independently PASS, but a new reproducible create-failure atomicity defect remains in lantern/pi_sessions.py. PI-T004 overall acceptance is **INCOMPLETE / FAIL at the failure-atomicity boundary**, not PASS. No implementation code was edited by TEST.

## Environment / code identity / preservation

Verified owned device desktop-b5e4iue-87cea2af (hostname DESKTOP-B5E4IUE), Windows Microsoft Windows NT 10.0.26100.0, authenticated device-broker working directory resolved exactly to E:\git-project\lantern\.wt\lantern-bot. Tools: uv 0.11.8, node v22.22.2, Python 3.14.1. Observed local device timestamps: 2026-10-19T03:29:16.3369739+09:00 through 2026-10-19T03:33:04.2532598+09:00.

Git branch feat/lantern-bot; HEAD 1282490f8bd1443b547c3b64b0b26813270ff837; local main / merge base 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b; main...HEAD = 0 left / 5 right. Worktree remains exactly:
- M lantern/terminal.py
- M tests/test_terminal_scm.py
- ?? lantern/pi_sessions.py
- ?? tests/test_pi_sessions.py

No Markdown-owner, WS, browser, application/chatbot, vendor/lock/dependency, LAN/security or other tracked path changed. No restart/attach to live Lantern :9999; no CDPA action; no reset/stash/clean/rebase/merge/push; no implementation edit.

Fresh file SHA256 via certutil -hashfile:
- lantern/pi_sessions.py: fd0b51c03877619b80c15b84a850ab260646b7152a942b6f37a862f7269b8554
- tests/test_pi_sessions.py: a922ee314a98d59a405f76490c9e185fd6c5b183d43a39cf06544b9a91ea2301
- lantern/terminal.py: 0f35f4176c74eeceb45f64c7e37efa786ba09f133baaf19dedc96e44cb66cff3

Environment/source checks executed in this verified directory:
    Get-Location; hostname; [System.Environment]::OSVersion.VersionString; Get-Date -Format o
    uv --version; node --version; uv run python --version
    git branch --show-current; git rev-parse HEAD; git rev-parse main
    git merge-base main HEAD; git rev-list --left-right --count main...HEAD
    git status --short; git diff --name-only; git diff --stat; git diff --check
    git log --oneline HEAD..main; git log --oneline main..HEAD
    Get-Content lantern/pi_sessions.py
    Get-Content tests/test_pi_sessions.py
    git diff -- lantern/terminal.py
    certutil -hashfile lantern/pi_sessions.py SHA256
    certutil -hashfile tests/test_pi_sessions.py SHA256
    certutil -hashfile lantern/terminal.py SHA256

Expected unchanged review candidate and only four authorized paths; actual as above. git diff --check exit 0 (only tracked diffs; untracked registry/tests separately compiled and executed).

## Executed ordinary acceptance and regression checks

All commands run on DESKTOP-B5E4IUE with working_directory E:\git-project\lantern\.wt\lantern-bot.

1. Registry unit suite:
    uv run python -m unittest -v tests.test_pi_sessions
    $code=$LASTEXITCODE; Write-Output ('PI_T004_REGISTRY_EXIT='+$code); exit $code

Expected eight cases executed, no skips. Actual: **8 run, 8 OK, 0 skips, 0.041s, exit 0**. Cases include opaque identity and exact native session argv, context defensive copies, same/different document independence, collision and cwd handling, stop/close generation isolation, TerminalManager exit status, and the reviewed post-publication list-emission rollback.

2. Targeted real TerminalManager ownership:
    uv run python -m unittest -v tests.test_pi_sessions.PiSessionRegistryTests.test_real_terminal_create_emit_failure_rolls_back_published_generation tests.test_pi_sessions.PiSessionRegistryTests.test_stop_and_close_do_not_kill_replacement_generations tests.test_terminal_scm.TerminalParityTests.test_kill_if_generation_never_kills_replacement_generation
    $code=$LASTEXITCODE; Write-Output ('OWNERSHIP_3_EXIT='+$code); exit $code

Expected 3/3. Actual: **3 run, 3 OK, 0.014s, exit 0**. This proves REVIEW R16-1 is resolved in its covered injection path; it does NOT cover all exceptions after successful TerminalManager.create_argv.

3. Terminal regression, syntax and tracked diff:
    uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
    uv run python -m py_compile lantern/terminal.py lantern/pi_sessions.py tests/test_terminal_scm.py tests/test_pi_sessions.py
    git diff --check

Expected all succeed. Actual: Terminal suite **23 run, 23 OK, 4.649s, exit 0**; py_compile exit 0; git diff --check exit 0.

4. Real native Pi structured-spawn regression:
    $env:LANTERN_PI_TUI_E2E='1'
    uv run python -m unittest -v tests.test_pi_tui_e2e
    $code=$LASTEXITCODE; Write-Output ('NATIVE_PI_EXIT='+$code); exit $code

Actual: **1 run, 1 OK, 0 skips, 10.214s, exit 0**. Native WinConPty/Pi evidence only, no provider request or physical FJP parity claim.

5. PI-T003 replay continuity regression:
    $env:LANTERN_PI_REPLAY_E2E='1'
    uv run python -m unittest -v tests.test_pi_reconnect_e2e
    $code=$LASTEXITCODE; Write-Output ('PI_T003_REPLAY_EXIT='+$code); exit $code

Actual: **7 run, 7 OK, 0 skips, 14.702s, exit 0**. Historical negative representations remain asserted negative; successful bounded same-geometry continuity remains narrowly accepted.

6. Complete ordinary repo discovery, run via device retained-process:
    Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
    Remove-Item Env:LANTERN_PI_TUI_E2E -ErrorAction SilentlyContinue
    uv run python -m unittest discover -s tests -q
    $rc=$LASTEXITCODE; Write-Output ('FULL_UNITTEST_EXIT='+$rc); exit $rc

Actual retained-process completion: **373 tests, OK, skipped=134, 71.725s, exit 0**; ResourceWarning HTTPError cleanup warnings only. Skipped=134 is not PASS evidence for gated native/browser/physical checks.

## Independent boundary probes beyond existing tests

A. Disposable true TerminalManager + fake PTY session-ownership probe, executed as a PowerShell here-string piped to uv run python - (no repository files written). It created an unrelated ordinary terminal and a PiSessionRegistry with server-owned argv/env, created three Pi sessions (two same-document, one different-document), asserted exact argv including --session-id, --session-dir, --tui-mode regular and distinct IDs/generations/session directories. Nested caller/returned context mutations did not change the stored copy. Simulated Pi A exit code 7 and verified TerminalManager-derived status, Pi B stayed live, replaced Pi C's terminal generation and verified stale registry stop/close could not kill replacement. Ordinary terminal survived. Closing twice remained safe. Expected and actual:
    {"argv_exact":true,"close_idempotent":true,"context_independent":true,"different_document":1,"exit_observed":true,"ordinary_preserved":true,"replacement_preserved":true,"same_document":2,"sessions":3}
    INDEPENDENT_REGISTRY_OWNER_EXIT=0

B. Independent after-publication exception and replacement-generation probe, also real TerminalManager with only a fake PTY. Emission of terminal_list raised RuntimeError after publish, then a second variant replaced the same terminal ID with another generation before the original create unwound. Expected cleanup exact old PTY/generation and directory, preserve unrelated/replacement terminal. Actual:
    {"post_publish_failure":"PROPAGATED","orphan_live":false,"orphan_history":false,"failed_session_dir":false,"orphan_pty_closed":true,"replacement_generation_survived":true,"unrelated_terminal_survived":true}
    INDEPENDENT_ROLLBACK_REPLACEMENT_EXIT=0

These positives confirm R16-1/R15-1 fixes, but are not sufficient to accept registry failure atomicity given the following counterexample.

## T8-1 — NEW reproducible orphan after contextRef defensive-copy failure

The registry advertises context_ref: Mapping[str, Any], and PLAN turn 10 mandates both defensive context copying and no half-created registry/process/session directory on failed create. A standard Python read-only MappingProxyType around ordinary string JSON-compatible fields satisfies the accepted Mapping interface, but deepcopy(mappingproxy) raises TypeError.

Inspection of lantern/pi_sessions.py create shows **contextRef: deepcopy(context_ref) occurs after self.terminal.create_argv(...) succeeds**. Only the create_argv call is inside the catch/rollback for session_dir. Thus an exception during post-spawn context deepcopy propagates while the native terminal remains live and the session dir remains, even though registry records no session.

Exact independent reproduction, one-shot Python stdin in the verified workspace (no tracked/untracked file writes):

    $py = @'
    import json,tempfile
    from pathlib import Path
    from types import MappingProxyType
    from lantern.terminal import TerminalManager
    from lantern.pi_sessions import PiSessionRegistry
    class Pty:
        def __init__(self,on_data,on_exit): self.closed=False
        def write(self,data): pass
        def resize(self,cols,rows): pass
        def close(self,graceful=True): self.closed=True
    with tempfile.TemporaryDirectory(prefix='lantern-t8-context-failure-') as td:
        root=Path(td)/'root';state=Path(td)/'state';root.mkdir();spawned={}
        def factory(tid,cwd,cols,rows,on_data,on_exit,command=None,**kw):
            p=Pty(on_data,on_exit);spawned[tid]=p;return p
        manager=TerminalManager(root,lambda event:None,pty_factory=factory)
        reg=PiSessionRegistry(root,state,manager,['node','pi.js'],id_factory=lambda:'ctxFail')
        err=None
        try: reg.create(cwd=root,context_ref=MappingProxyType({'path':'file.md'}))
        except Exception as ex: err=type(ex).__name__+': '+str(ex)
        live='pi:ctxFail' in manager.live
        out={'input':'MappingProxyType[str, str]','error':err,
             'registry_sessions':len(reg.list()),'terminal_live_after_failure':live,
             'session_dir_exists_after_failure':(state/'ctxFail').is_dir(),
             'pty_closed_after_failure':spawned.get('pi:ctxFail').closed if 'pi:ctxFail' in spawned else None}
        print(json.dumps(out))
        if live: manager.kill('pi:ctxFail',emit_exit=False)
        assert err and live and (state/'ctxFail').is_dir()
        print('BUG_REPRODUCED_CONTEXT_COPY_POST_SPAWN_ORPHAN')
    '@
    $py | uv run python -
    $code=$LASTEXITCODE; Write-Output ('CONTEXT_FAILURE_PROBE_EXIT='+$code); exit $code

Expected contract: accept and defensively copy the read-only Mapping, OR reject its unsupported shape before spawning, OR safely roll back only its own newly created PTY generation and native session directory on any post-spawn exception. Registry must not lose the ability to manage a live PTY.

Actual (probe exit 0 means the ASSERTIONS OF THE BUG succeeded, not that acceptance passed):
    {"input":"MappingProxyType[str, str]","error":"TypeError: cannot pickle 'mappingproxy' object","registry_sessions":0,"terminal_live_after_failure":true,"session_dir_exists_after_failure":true,"pty_closed_after_failure":false}
    BUG_REPRODUCED_CONTEXT_COPY_POST_SPAWN_ORPHAN
    CONTEXT_FAILURE_PROBE_EXIT=0

The probe terminated its temporary orphaned fake PTY before leaving the disposable temporary directory; no Lantern :9999 or other terminal was touched. This is a deterministic product defect, not a flaky native-Pi test. It is specifically **not** REVIEW's already fixed TerminalManager.create emit-failure path. The context mapping holds only a normal string path; failure comes from defensively copying a valid Mapping implementation too late.

Required DEV correction: make context snapshot/validation failure safe **before** PTY spawn where possible, or use an exact-generation conditional rollback after post-spawn registry failures; preserve original exception and unrelated/replacement generations. Add a focused failing-then-green regression for read-only Mapping or another natural context deep-copy failure, and keep the existing 8 positive tests and all existing scope boundaries. No PI-T006/007, WS/frontend, persistence, Markdown or extra process framework is justified. Independent REVIEW/TEST must reaccept PI-T004 after correction.

## Final classification

- PI-T004: **NOT ACCEPTED**; specifically T8-1 violates create failure atomicity despite existing positive tests being green.
- PI-T005: previously accepted; native Pi regression newly confirmed 1/1.
- PI-T003: previously accepted Phase-0; replay regression newly confirmed 7/7.
- Spec 001 T1: previously accepted. T0-C physical >=50-attempt four-channel evidence NOT_MEASURED/deferred; T2 BLOCKED; no IME fix.
- PI-T006/007, attach/writer-viewer/resize arbitration, browser F5/live session persistence, FJP physical IME/AltGr/image paste, real POSIX process behavior, model/goal/custom-extension parity, CPU/RSS/latency/resource release evidence: **INCOMPLETE / NOT_MEASURED**.
- Full objective NOT DONE; no unrelated work touched.

**ROUTE DEV**, specifically for reproducible T8-1 post-spawn contextRef defensive-copy orphan. Do not route DONE or unlock PI-T006 until PI-T004 passes independent acceptance.
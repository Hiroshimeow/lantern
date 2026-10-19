# TEST turn 10 — PI-T006 generic Terminal bypass of single-writer ownership

Task: cdpa-idem-83600abd5f02df21942f316e
Role: TEST turn 10
Incoming: .plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn21_cdpa-idem-83600abd5f02df21942f316e.md
Workspace: E:\git-project\lantern\.wt\lantern-bot

**Disposition: ROUTE DEV. PI-T006 NOT ACCEPTED.** An independent production-dispatch probe reproducibly shows that a Pi viewer denied by pi_session_input can still send the same input using generic terminal_input and the internal terminal ID. A separate unattached authenticated peer can resize the canonical Pi PTY through generic terminal_resize. The new single-writer/resize ownership policy is bypassed. No implementation edits were made by TEST.

## Environment / source identity / scope

Device desktop-b5e4iue-87cea2af, hostname DESKTOP-B5E4IUE, Windows NT 10.0.26100.0; verified device-broker working directory E:\git-project\lantern\.wt\lantern-bot. Observed device time 2026-10-19T04:30:55.1974530+09:00; uv 0.11.8, Node v22.22.2, Python 3.14.1. Branch feat/lantern-bot, HEAD 71bc8de3e6b82e94078b899c54ba01cfb71ff64b, main/merge-base 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b, main...HEAD 0 left / 6 right.

Candidate status exactly M lantern/ws.py and ?? tests/test_pi_ws_contract.py; git diff --check exit 0. No new Markdown, application, frontend, vendor/dependency, auth policy, session persistence or other implementation paths dirty. TEST did not reset/stash/clean/rebase/merge, edit implementation, restart/attach live Lantern :9999 or touch CDPA.

Commands used for identity and source inspection:
    Get-Location; hostname; [System.Environment]::OSVersion.VersionString; Get-Date -Format o
    uv --version; node --version; uv run python --version
    git branch --show-current; git rev-parse HEAD; git rev-parse main
    git merge-base main HEAD; git rev-list --left-right --count main...HEAD
    git status --short; git diff --name-only; git diff --check; git diff --stat
    git log --oneline main..HEAD
    git diff -- lantern/ws.py
    Get-Content lantern/ws.py
    Get-Content tests/test_pi_ws_contract.py

## TEST finding T10-1: direct generic terminal commands bypass Pi writer ownership

Expected PI-T006 one-writer semantics: a viewer cannot input/key/resize the shared canonical Pi PTY, and an unattached peer cannot resize it. There must be one authoritative writer/resize owner across the reachable WS transport surface.

Production code:
- pi_session_input/key/resize check attachment, generation and ownershipEpoch via hub._pi_writer_target_locked while holding TerminalManager.lock -> hub.lock.
- Existing terminal_sync exposes TerminalManager.list(), including Pi internal terminal IDs (PLAN correctly did not require hiding list entries in this slice).
- Existing terminal_input and terminal_resize dispatch branches accept terminalId and call TerminalManager.input()/resize() directly without excluding Pi-owned terminal IDs or enforcing Pi writer ownership.
- The runtime already has authenticated generic Terminal protocol, so these are reachable operations using the same terminal access credential; the new Pi protocol's writer policy does not cover them.

Independent repro (no source edits; disposable fake PTYs, actual PiSessionRegistry + TerminalManager + WebSocketHub + dispatch; used test fixture only for construction):

    $py = @'
    import json
    from tests.test_pi_ws_contract import PiWsContractTests, Peer
    t=PiWsContractTests('test_first_attach_writer_second_viewer_replay_and_output_scope')
    t.setUp()
    try:
        a=Peer(); b=Peer(); rogue=Peer()
        role_a=t.attach(a,t.a); role_b=t.attach(b,t.a); t.hub.add(rogue)
        pty=t.spawned[t.a['terminalId']]
        denied=[]
        for typ,data in [('pi_session_input','FORBIDDEN'),('pi_session_resize',None)]:
            request={'type':typ,'sessionId':t.a['sessionId'],'generation':t.a['generation'],'ownershipEpoch':role_b['ownershipEpoch'],'data':data,'cols':131,'rows':41}
            try:t.op(b,request)
            except PermissionError as err: denied.append(type(err).__name__)
        assert len(denied)==2 and pty.writes==[] and pty.resizes==[]
        t.op(b,{'type':'terminal_sync'})
        sync=b.messages[-1]
        assert sync['type']=='terminal_list' and any(s['id']==t.a['terminalId'] for s in sync['terminals'])
        t.op(b,{'type':'terminal_input','terminalId':t.a['terminalId'],'data':'BYPASS_VIEWER'})
        t.op(rogue,{'type':'terminal_resize','terminalId':t.a['terminalId'],'cols':135,'rows':43})
        assert pty.writes==['BYPASS_VIEWER'] and pty.resizes==[(135,43)]
        assert t.hub.pi_routes[t.a['sessionId']]['writer'] is a
        print(json.dumps({'pi_viewer_denied':denied,'ordinary_terminal_sync_exposes_pi_terminal_id':True,'generic_viewer_input_reached_pi':pty.writes,'generic_unattached_resize_reached_pi':pty.resizes,'writer_still':role_a['role'],'epoch':role_a['ownershipEpoch']},sort_keys=True))
    finally:t.tearDown()
    '@
    $py | uv run python -
    Write-Output ('GENERIC_PI_WRITER_BYPASS_PROBE_EXIT='+$LASTEXITCODE)

Actual: process exit 0, i.e. the assertions that reproduce the bug passed:

    {"epoch":1,"generic_unattached_resize_reached_pi":[[135,43]],"generic_viewer_input_reached_pi":["BYPASS_VIEWER"],"ordinary_terminal_sync_exposes_pi_terminal_id":true,"pi_viewer_denied":["PiSessionPermissionError","PiSessionPermissionError"],"writer_still":"writer"}
    GENERIC_PI_WRITER_BYPASS_PROBE_EXIT=0

This is not an auth bypass (these are authenticated peers); it is a **writer-authorization bypass**. No arbitrary session ID guessing is necessary: terminal_sync exposes the terminalId. Hiding the terminalId only is not a complete authorization defense because process-control authorization belongs at the server boundary.

**Required DEV resolution:** keep ordinary Terminal behavior compatible, but reject generic terminal_input/key/resize (and review generic terminal_kill/run/create with matching live Pi IDs for destructive ownership bypass) for terminal IDs registered as native Pi processes, or design another narrow central guard that consistently prevents generic ops from circumventing scoped writer/resize semantics. Preserve existing Terminal auth; do not add broad LAN/security controls, a new process service, application wiring or PI-T007. Add a deterministic regression proving generic operations cannot write/resize/kill a Pi session while ordinary Terminal operations remain unchanged; include reviewer consideration of stale/replacement generations and lock order. Do not weaken the one-writer acceptance rule.

## Other checks genuinely executed

1. PI-T006 focused contract:
    uv run python -m unittest -v tests.test_pi_ws_contract
    $rc=$LASTEXITCODE; Write-Output ('PI_WS_CONTRACT_EXIT='+$rc); exit $rc

Expected 10 tests. Actual **10 run, 10 OK, 0 skips, 0.068s, exit 0**; these do not cover the generic Terminal bypass.

2. Related registry/auth/LAN regressions:
    uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_auth tests.test_lan_multi_perf
    uv run python -m py_compile lantern/ws.py tests/test_pi_ws_contract.py
    git diff --check

Expected all green. Actual **40 tests OK, 6.616s, exit 0**; py_compile exit 0; git diff --check exit 0. Existing test messages about terminal password YAML changes are from test fixtures; TEST did not restart Lantern.

3. Complete ordinary suite independently run via retained device process:
    uv run python -m unittest discover -s tests -q

Expected green with gated native tests skipped. Actual **384 tests, OK, skipped=134, 54.263s, retained process exit 0**. Existing HTTPError and one closed-socket ResourceWarning occurred. All skips remain NOT_MEASURED, not PASS.

4. REVIEW's three concurrency race tests (attach exit, takeover exit, stale old writer after takeover) are included in the 10/10 focused contract and green, supporting narrow R19/R20 corrections. No new physical browser/remote multi-peer test was run; do not infer live-release parity or performance from unit suites.

## Status and route

PI-T006 **FAIL / BLOCKED at the material writer-ownership boundary**, despite its existing tests being green. R19-1, R19-2, R20-1 race regressions remain covered, but generic terminal_* actuation bypass is reproducible. This is a concrete implementation defect: **ROUTE DEV**, not PLAN and never DONE.

PI-T004 server-internal registry, PI-T005 structured native spawn, PI-T003 Phase-0 replay were previously accepted; their related tests are fresh green here. Spec 001 T1 previously accepted. T0-C physical >=50 attempts across four channels NOT_MEASURED/deferred; T2 BLOCKED, no IME fix. PI-T007 and downstream UI/lifecycle still unauthorized. Browser F5/live reconnect, FJP physical input, actual multi-native-Pi process concurrency/resource, POSIX runtime, model/goal/extensions parity, CPU/RSS/latency remain NOT_MEASURED/INCOMPLETE. Overall objective NOT DONE.

**ROUTE DEV** for T10-1; preserve all unrelated work and do not modify live Lantern 9999 or CDPA.
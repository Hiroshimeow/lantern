# TEST turn 11 — PI-T006 session-scoping bypass via generic Terminal replay/output/exit

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: TEST turn 11  
Incoming handoff: .plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn26_cdpa-idem-83600abd5f02df21942f316e.md  
Workspace: E:\git-project\lantern\.wt\lantern-bot

**Disposition: ROUTE DEV. PI-T006 NOT ACCEPTED.** REVIEW R25-1 (delayed old-generation output) and preceding writer/ownership/generic-control fixes are green, but an independent test using production TerminalManager + PiSessionRegistry + WebSocketHub + dispatch reproduces a material **cross-session output/exit scoping defect**. A peer attached only to Pi session B can use the permitted generic Terminal subscription to obtain session A replay and future output, and even an unattached peer receives A's generic terminal_exit event. No source implementation was edited by TEST.

## Verified identity / preservation

- Owned device: desktop-b5e4iue-87cea2af, hostname DESKTOP-B5E4IUE, Microsoft Windows NT 10.0.26100.0, PowerShell; device broker resolved working directory exactly E:\git-project\lantern\.wt\lantern-bot.
- Observed date/time: 2026-10-19T05:23:14.5709008+09:00 to 2026-10-19T05:25:31.3276814+09:00. uv 0.11.8; node v22.22.2; Python 3.14.1.
- Branch feat/lantern-bot, HEAD 71bc8de3e6b82e94078b899c54ba01cfb71ff64b; main and merge base 4b32a79c34040a0ca8eb6ae0e9f2b2505d06656b; main...HEAD = 0 left / 6 right.
- Worktree unchanged from REVIEW turn 26: M lantern/pi_sessions.py; M lantern/terminal.py; M lantern/ws.py; M tests/test_pi_sessions.py; M tests/test_terminal_scm.py; ?? tests/test_pi_ws_contract.py. No Markdown-owned, app/browser, dependency/vendor, LAN policy or unrelated file changes. git diff --check exit 0 (untracked proof separately compiled and run). Git LF-to-CRLF advisory warnings only, no reset/stash/clean/rebase/merge/commit/push. No live Lantern :9999 restart/attach or CDPA mutation. No paid-provider/native prompt.
- SHA256 via Windows certutil -hashfile: lantern/ws.py 86e93d34ef8914e72fe211a7b1e25c48bd6c555372c76c4510f06389784655a9; tests/test_pi_ws_contract.py 63dac886c3cef2c2e6f9dc2c5ee1883a45190a843688f5fe6894e6ce4f78a65c; lantern/terminal.py e2bf5f51bd5b73bb73b617325298632d7be1d305829f5d15605a7724ce0ddc33; lantern/pi_sessions.py 741d78e9bfa4c68bccd935f23dec1eecb560c10d21f08e3ba2dfd4656dcd10c0.

Environment/diff commands independently executed in the exact verified directory:

    Get-Location; hostname; [System.Environment]::OSVersion.VersionString
    Get-Date -Format o; uv --version; node --version; uv run python --version
    git branch --show-current; git rev-parse HEAD; git rev-parse main
    git merge-base main HEAD; git rev-list --left-right --count main...HEAD
    git status --short; git diff --name-only; git diff --stat; git diff --check
    git log --oneline main..HEAD
    git diff -- lantern/pi_sessions.py lantern/terminal.py
    git diff -- lantern/ws.py
    git diff -- tests/test_pi_sessions.py tests/test_terminal_scm.py
    certutil -hashfile lantern/ws.py SHA256
    certutil -hashfile tests/test_pi_ws_contract.py SHA256
    certutil -hashfile lantern/terminal.py SHA256
    certutil -hashfile lantern/pi_sessions.py SHA256

Expected: exact reviewed six-file candidate without unrelated modifications. Actual as listed, git diff --check exit 0.

## T11-1 — cross-session generic Terminal read and exit routing escapes Pi attachment scope

PLAN turn 11 explicitly requires only peers attached to **the matching sessionId + generation** to receive the Pi session output; A must not send raw TUI bytes to a peer attached only to B; on Pi terminal exit, **no peer for another session receives it**. Internal terminal IDs being visible in the legacy terminal_list is expressly deferred and does not authorize cross-session Pi replay/output/exit under this contract.

Static production-path finding:

- pi_session_attach correctly registers one session per peer and hub.broadcast() delivers pi_session_output/pi_session_exit to matching Pi route peers by exact terminalId+generation.
- However dispatch terminal_subscribe (lantern/ws.py) accepts *any* terminal ID, including one whose TerminalEntry.control_owner == "pi". Unlike generic terminal_input/key/resize/create/run/kill, generic terminal_subscribe has no Pi owner guard.
- terminal_subscribe calls TerminalManager.replay_view and sends terminal_replay containing Pi's internal terminalId, metadata, exact history and stream offsets, and generic subscription registration.
- hub.broadcast() sends generic terminal_output to an unrelated v2 peer subscribed to that internal ID if it has no matching Pi-route payload.
- hub.broadcast() sends generic terminal_exit to **all** terminal-authorized peers with no subscription test; peers of other Pi sessions and unattached peers receive the Pi terminalId, generation and exit code. Only matching-route peers get scoped pi_session_exit.
- These are authenticated peers, so this is **not a new Terminal-auth bypass**. It is a **Pi session-scoping / isolation bypass**. Generic writer-control blocking from TEST turn 10 remains intact, but does not protect output/exit.

**Exact independent reproduction** — disposable Python process using genuine PiSessionRegistry, TerminalManager, WebSocketHub and dispatch, with fake PTYs solely for deterministic input/exit and repository test helper Peer/fixture for setup. No repo changes or real service interaction:

    $py = @'
    import json
    from tests.test_pi_ws_contract import PiWsContractTests, Peer
    t=PiWsContractTests('test_session_switch_and_two_session_isolation')
    t.setUp()
    try:
        pa,pb,un=Peer(),Peer(),Peer()
        ar=t.attach(pa,t.a)
        br=t.attach(pb,t.b)
        t.hub.add(un)
        ta=t.a['terminalId'];sa=t.a['sessionId']
        assert ar['role']=='writer' and br['role']=='writer'
        t.spawned[ta].emit('PRIVATE-A-1')
        assert not any(x.get('data')=='PRIVATE-A-1' for x in pb.messages)
        t.op(pb,{'type':'terminal_subscribe','terminalId':ta})
        initial=[x for x in pb.messages if x.get('type')=='terminal_replay' and x.get('terminalId')==ta]
        assert len(initial)==1 and 'PRIVATE-A-1' in initial[0]['output']
        t.spawned[ta].emit('PRIVATE-A-2')
        output=[x for x in pb.messages if x.get('type')=='terminal_output' and x.get('terminalId')==ta and x.get('data')=='PRIVATE-A-2']
        assert len(output)==1
        t.spawned[ta].on_exit(23)
        scoped_exit=[x for x in pa.messages if x.get('type')=='pi_session_exit' and x.get('sessionId')==sa]
        b_generic_exit=[x for x in pb.messages if x.get('type')=='terminal_exit' and x.get('terminalId')==ta]
        un_generic_exit=[x for x in un.messages if x.get('type')=='terminal_exit' and x.get('terminalId')==ta]
        assert len(scoped_exit)==1 and len(b_generic_exit)==1 and len(un_generic_exit)==1
        assert pb not in t.hub.pi_routes[sa]['peers'] and un not in t.hub.pi_routes[sa]['peers']
        assert t.registry.get(t.b['sessionId'])['running']
        print(json.dumps({'A_scoped_exit':scoped_exit,'B_generic_subscribe_A_replay':initial[0],'B_generic_A_output':output,'B_generic_A_exit':b_generic_exit,'unattached_generic_A_exit':un_generic_exit,'B_remains_attached_to_B':True},sort_keys=True))
    finally:
        t.tearDown()
    '@
    $py | uv run python -
    $rc=$LASTEXITCODE
    Write-Output ('PI_SCOPING_CROSS_SESSION_PROBE_EXIT='+$rc)
    exit $rc

Expected by contract: B cannot acquire A's Pi output/replay through generic subscription, and neither B nor unattached peer U receives A terminal exit; A's attached peer receives one correct scoped event. **Actual**: PI_SCOPING_CROSS_SESSION_PROBE_EXIT=0 (means the *bug assertions* all succeeded, not acceptance PASS):

- A first output PRIVATE-A-1 was initially isolated correctly from B.
- B's generic terminal_subscribe for A immediately received terminal_replay with output PRIVATE-A-1, A internal terminalId pi:sessA, generation, cwd and terminal metadata.
- A subsequent output PRIVATE-A-2 was delivered to B as generic terminal_output with A internal ID, original seq=2 and bytes unchanged.
- When A exited with code 23, A's attached peer got its correct scoped pi_session_exit; **B**, though Pi-attached only to session B, also got generic terminal_exit for A; completely unattached authorized peer U also got generic terminal_exit for A.
- B remained attached to live session B. These are not duplicate events from B's own session.

The output printed independently includes:

    "B_generic_A_output":[{"data":"PRIVATE-A-2","seq":2,"terminalId":"pi:sessA","type":"terminal_output",...}]
    "B_generic_A_exit":[{"exitCode":23,"terminalId":"pi:sessA","type":"terminal_exit",...}]
    "unattached_generic_A_exit":[{"exitCode":23,"terminalId":"pi:sessA","type":"terminal_exit",...}]
    "B_remains_attached_to_B":true

This contradicts the required session-output/exit scoping despite the 16 currently passing contract tests.

DEV fix scope: preserve ordinary Terminal subscriptions/exit behavior, reuse existing Pi-owned identity plus generation (including delayed old-generation events after same-ID replacement), and prevent generic terminal_subscribe/replay and generic output/exit delivery from disclosing a Pi-owned generation to nonattached Pi peers. Do not simply hide terminalId; authorization/scoping must hold even when it is already known via terminal_list. Add real TerminalManager/Hub/dispatch regression for: B attached only to B and a separate unattached authenticated peer; A replay/output/exit cannot escape, while A attached peers still receive exactly one correct scoped event and unrelated ordinary terminal subscribe/exit remains unchanged. Keep R25 old-generation delayed output/exit delivery and replacement isolation intact; do not expand into LAN auth policy, browser/UI, PI-T007, Markdown, persistence or a new state owner.

## Other acceptance checks executed (all independently)

1. Enabled PI-T006 contract:

    uv run python -m unittest -v tests.test_pi_ws_contract
    $rc=$LASTEXITCODE; Write-Output ('PI_T006_EXIT='+$rc); exit $rc

Expected: all 16 actual tests run (no gate/skips). Actual **16 run, 16 OK, 1.046s, exit 0**. Existing tests cover attach/writer/viewer, owner epoch, takeover, stopped-session/stale generations, generic writer-control guard, publish windows, previous R19-R25 races and replacement generation, but not T11-1 cross-session generic subscribe and exit.

2. Targeted R25/R24/R20 and generic writer-control regression:

    uv run python -m unittest -v tests.test_pi_ws_contract.PiWsContractTests.test_old_generation_output_survives_terminal_id_replacement_before_broadcast tests.test_pi_ws_contract.PiWsContractTests.test_old_generation_exit_survives_terminal_id_replacement_before_broadcast tests.test_pi_ws_contract.PiWsContractTests.test_replacement_generation_rejects_old_attachment_without_touching_new_pty tests.test_pi_ws_contract.PiWsContractTests.test_takeover_rejects_exit_between_registry_view_and_ownership_change tests.test_pi_ws_contract.PiWsContractTests.test_generic_terminal_controls_cannot_bypass_pi_writer_or_destroy_session

Expected five targeted tests pass; actual **5 OK, 0.023s, exit 0**. Delayed old-generation output/exit and previously reported generic-control bypass remain corrected in their tested cases. The new T11-1 flaw is additional.

3. Related PI registry/Terminal/auth/LAN regressions:

    uv run python -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_terminal_auth tests.test_lan_multi_perf
    uv run python -m py_compile lantern/pi_sessions.py lantern/terminal.py lantern/ws.py tests/test_pi_sessions.py tests/test_terminal_scm.py tests/test_pi_ws_contract.py
    git diff --check

Expected all green. Actual **63 tests OK, 11.670s, exit 0**; Python syntax exit 0; git diff check exit 0. Test fixture may print "Terminal password ... YAML. Restart Lantern to apply", but TEST did not restart Lantern or modify live service.

4. Full ordinary unittest discovery, independent retained device process:

    uv run python -m unittest discover -s tests -q

Expected ordinary suite green with physical/native opted-in cases skipped, no skip counted as acceptance. Actual **390 tests, OK, skipped=134, 53.750s, retained process exit 0 (54.71s runtime)**. Existing HTTPError/closed-socket ResourceWarning cleanup lines appeared; no suite failure. 134 skipped tests are INCOMPLETE/NOT_MEASURED for their own gates.

## Acceptance classification and route

**PI-T006: FAIL / NOT ACCEPTED, route DEV for reproducible T11-1 session-scoping defect.** The corrected R22 generic input/resize owner fence and R25 delayed output/exit generation-tagging are independently regression-green, but generic Terminal subscribe/replay and exit routing still cross the expressly required Pi attachment boundary. The new failure is material even without browser/runtime integration and must not be silently deferred to PI-T008.

PI-T004 registry, PI-T005 native structured spawn, PI-T003 Phase-0 replay are previously accepted. Spec 001 T1 accepted, T0-C physical >=50-attempt four-channel evidence NOT_MEASURED/deferred, T2 BLOCKED; no IME fix. PI-T007+ not authorized. Browser F5/live WS/reconnect, restart persistence, physical FJP UniKey/IME/AltGr/image paste, real POSIX execution, model/goal/extension parity and long-run CPU/RSS/latency remain INCOMPLETE/NOT_MEASURED. Overall objective NOT DONE.

**ROUTE DEV.** Preserve the six-file PI-T006 candidate and unrelated work; no live Lantern 9999/CDPA action; independent REVIEW/TEST needed after correction.
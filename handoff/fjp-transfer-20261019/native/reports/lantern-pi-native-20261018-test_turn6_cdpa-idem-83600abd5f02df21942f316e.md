# TEST turn 6: PI-T003 independent acceptance

Task: cdpa-idem-83600abd5f02df21942f316e
Handoff: review_turn13
Role: TEST
Disposition: **ROUTE PLAN**. PI-T003 is a PASS candidate at its bounded, same-geometry replay-continuity proof gate. Browser F5/release acceptance remains NOT_MEASURED. No implementation changes by TEST.

## Verified environment and preservation

Device desktop-b5e4iue-87cea2af, DESKTOP-B5E4IUE, Windows NT 10.0.26100.0; working directory E:\git-project\lantern\.wt\lantern-bot (device broker resolved). uv 0.11.8; Node v22.22.2; Python 3.14.1. Observation 2026-10-19 02:30-02:34 JST. Branch feat/lantern-bot; HEAD 69214a799c4708b785136462fa2ce126df88d186; main 44b65ff5aac4bffa015385bbed3d0ce8643484c9; main...HEAD = 0 left / 3 right. Only six tracked dirty paths: lantern/terminal.py, lantern/ws.py, static/terminal_scm.js, tests/test_pi_reconnect_e2e.py, tests/test_terminal_scm.py, tests/test_terminal_ui.py. No Markdown/vendor/dependency/LAN-security or other production files dirty. git diff --check exit 0; no reset/stash/clean/rebase/merge/push or live Lantern 9999/CDPA action.

Hashes independently verified by certutil SHA256: tests/test_pi_reconnect_e2e.py = 826536dcb1a9270aeb61b2615f8886c0065d63bbf666a552deb9fc188d715032; static/vendor/xterm.js = f68403f92e5552d69fab42d98571c8e16b6f03cba3e5233b4c8a99d3eb9d4653; native capture pi-t002-g6-winconpty-raw.txt = 8daa712a72788923fa36830b819410e72f54048a477be5083bc67f30ab3c0747.

Environment/repository commands (all in verified working directory):
```powershell
Get-Location; hostname; [System.Environment]::OSVersion.VersionString
Get-Date -Format o; uv --version; node --version; uv run python --version
git branch --show-current; git rev-parse HEAD; git rev-parse main
git merge-base main HEAD; git rev-list --left-right --count main...HEAD
git status --short; git diff --stat; git diff --name-only; git diff --check
git log --oneline HEAD..main; git log --oneline main..HEAD
certutil -hashfile tests/test_pi_reconnect_e2e.py SHA256
certutil -hashfile static/vendor/xterm.js SHA256
certutil -hashfile .plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty-raw.txt SHA256
```

## Enabled PI-T003 acceptance

Command:
```powershell
$env:LANTERN_PI_REPLAY_E2E='1'
uv run python -m unittest -v tests.test_pi_reconnect_e2e
$code=$LASTEXITCODE
Write-Output ('PI_T003_PROOF_EXIT='+$code)
exit $code
```

Expected: seven actually executed acceptance tests, all passing their positive and explicitly negative assertions. Actual **7 run, 7 OK, 0 skips, 15.886 seconds, exit 0**. Exact test names:
- test_current_raw_tail_replay_is_not_lossless: PASS as proof raw-tail replay is NOT LOSSLESS.
- test_upstream_serializer_is_lossless_for_tested_same_geometry_state: PASS for narrow synthetic same-geometry states only.
- test_real_pi_headless_serializer_mismatch_is_preserved: PASS as proof server-headless->vendored browser is NOT EQUIVALENT.
- test_real_pi_exact_client_snapshot_round_trips: PASS for byte-faithful native Pi exact-client full oracle, 120x40.
- test_public_watermark_restores_real_pi_short_detach_exactly_once: PASS for public S, 9 ordered Unicode-bearing chunks, no input resend, accepted S==start and S==end.
- test_public_ws_watermark_rejects_manager_and_display_cap_gaps: PASS for rejection of both gap types before partial restoration.
- test_manager_detach_replay_orders_output_without_resending_input: PASS for narrow deterministic manager seq/input fixture.

Independent direct browser-oracle commands:
```powershell
uv run python -c "from tests import test_pi_reconnect_e2e as t; r=t._real_pi_exact_client_results(); print('native_provenance',r['provenance']); print('snapshot',r['browser']); print('delta',r['delta'])"
uv run python -c "from tests import test_pi_reconnect_e2e as t; r=t._real_pi_headless_cross_stack_results(); print('native_provenance',r['provenance']); print('versions',r['versions']); print('headless_to_vendor',r['browser'])"
```
Both exit 0. Native provenance captureByteExact/offline/nativePiCli/nativeUiMarkers all true. Exact vendored browser reference/restoration at 120x40 equal=true under full cells/attributes/cursor/buffer/mode/geometry comparison; both normal buffer cursor (0,35), base/view 16/16. Correct artifact length **6130 UTF-8 bytes**, **5708 UTF-16 code units**. Ordered nine-chunk delta equal=true, both normal cursor (18,1), base/view 16/16. Server-headless serializer remains unequal: reference cursor (0,35), base/view 16/16; reconstruction (3,35), 20/20; versions headless 6.0.0 / serialize 0.14.0. Different-width replay still false.

## Production public-continuity verification

Inspected actual diffs. TerminalEntry retains one bounded output buffer; retained_start_utf8 / stream_end_utf8 reflect UTF-8 lengths of respectively dropped exact prefix and all emitted data, with zero defaults for new generations. replay_view returns atomic meta/output/seq/start/end and replay_one preserves its old 3-tuple. WS terminal_subscribe captures under manager lock and computes an extra UTF-8 offset when display cap slices output, sending replayStartUtf8/replayEndUtf8 for actual displayed string alongside old seq/generation/truncated. Browser TextEncoder helper and safe-integer continuity check are minimal bookkeeping; ordinary replay still reset+write, no snapshot consumer or Pi-specific protocol introduced.

Independent disposable Python + Node UTF-8 matrix used real TerminalManager, WebSocketHub and WS dispatch with fake PTYs: 20 deterministic samples (ASCII, Japanese, Vietnamese, emoji, combining, ANSI/CRLF, and seeded mixed strings) x 5 manager character caps (1,3,8,17,60) x 4 WS display caps (1,2,5,100). Each sample was emitted in two separate chunks. Expected/actual for **all 400 public replay payloads**: seq=2; replayEndUtf8 = len(full_stream.encode('utf-8')); replayStartUtf8 = end - len(actual_sent_output.encode('utf-8')); end-start equals actual sent UTF-8 length; truncated exactly reflects extra WS cap; manager replay_one remains compatible. Node TextEncoder UTF-8 sizes matched Python on all 20 samples; new-generation replay interval 0/0. Corrected probe result: `{"samples":20,"replay_cases":400,"python_vs_node_utf8":"MATCH","manager_vs_ws_payload":"MATCH","new_generation":"ZERO"}`; process exit 0.

First attempt at the *extra* matrix probe passed raw Unicode through Windows CP1252 subprocess stdin and raised a diagnostic-harness UnicodeEncodeError, then hit the 28-second tool timeout (NOT acceptance evidence). Corrected by JSON ASCII escape transport with `json.dumps(samples,ensure_ascii=True)`; the corrected 400-case matrix passed. No implementation defect or edit arose from that failed diagnostic attempt.

## Regression commands and results

```powershell
Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
uv run python -m unittest discover -s tests -p test_terminal_ui.py -q
uv run python -m unittest -q tests.test_lan_multi_perf
uv run python -m py_compile tests/test_pi_reconnect_e2e.py lantern/terminal.py lantern/ws.py
node --check static/terminal_scm.js
git diff --check
```
Expected focused regression/syntax green. Actual terminal SCM 17 OK in 5.050s; terminal UI 13 OK in 2.511s; LAN multi-client 19 OK in 5.912s; Python, Node syntax, git diff check each exit 0.

Full suite run independently via retained device process:
```powershell
Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
uv run python -m unittest discover -s tests -q
$code=$LASTEXITCODE
Write-Output ('FULL_SUITE_EXIT='+$code)
exit $code
```
Expected ordinary test suite green without claiming gated replay acceptance. Actual **357 tests, OK, skipped=132, 54.263s, exit 0**; known ResourceWarning HTTPError cleanup only. Skips NOT PASS.

## Classification / route

Narrow PI-T003 PASS candidate: native real-Pi exact-vendored-client snapshot and complete ordered short-detach delta at 120x40; cross-runtime UTF-8 public replay interval; both manager retention and display-cap gap detectable and rejected; no input resend; backward-compatible ordinary terminal path. Previous raw-tail, headless-to-browser, cross-width NEGATIVE representations remain negative. No reproducible implementation defect found.

**NOT_MEASURED/INCOMPLETE**: browser F5/live WS reconnect and snapshot persistence, FJP physical IME/UniKey/AltGr/image paste, live model/goal/extensions parity, cursor visibility beyond exposed oracle, multiview one-writer/takeover/resize isolation, long-run CPU/RSS/latency/performance and full release. Spec 001 T1 accepted; T0-C physical >=50 attempts NOT_MEASURED/deferred; T2 BLOCKED, no IME fix. PI-T004/005/006 have not begun. Overall objective NOT DONE.

**ROUTE PLAN** to decide PI-T003 gate and dependency-ordered next slice. No downstream feature authorization by TEST. Preserve six-file candidate and unrelated work.

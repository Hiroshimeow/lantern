# TEST Turn 3 — exact Foundation performance closure measurements

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: TEST turn 3  
Date: 2026-10-18 JST  
Workspace: G6 E:\git-project\lantern  
Branch: main  
Tested HEAD: ffe3decb4469cff36bb98f8afd6ba8e9e89af089  
Incoming REVIEW: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn4_cdpa-idem-382a709ae8895eae9ec134d4.md

## 1. Boundary and safety

This TEST turn followed REVIEW Turn 4's narrow instruction only:
1. measure Preview with an exact 100 KiB Markdown fixture;
2. measure an exact 200 KiB terminal replay through the existing retained-tail + WS dispatch/serialization path.

No product/source implementation file was edited. Verification artifacts live only under ignored .plan/lantern-markdown-main-20261018/.

Loaded verification-before-completion and webapp-testing skills. No terminal/PTY/WS source edits, no :9999 restart/use, no CDPA mutation, no reset/stash/clean, no .pi edit.

Initial repo identity:
- branch: main
- HEAD: ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- status: only ?? .pi/subagents.json

A detached baseline worktree was created at repository-approved .wt/test-foundation-baseline-turn3 at pre-Foundation SHA 1b5939357bfd3748a1c56b5e491bc55026b0368b, used read-only for paired measurements, verified clean, then removed.

Final repository state:
- HEAD unchanged: ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- git diff --check: exit 0
- status: only ?? .pi/subagents.json
- only root main + unrelated .wt/lantern-bot remain.

## 2. Contract confirmed before measurement

Spec 002 requires:
- latency/CPU/RSS for listing, Markdown Preview 100 KiB, and terminal replay;
- tasks.md fixes the terminal replay workload at 200 KiB;
- SC-FND-05 proposes <=20% p95 and <=25% RSS degradation, but explicitly requires review/owner approval rather than automatic PASS.

Current replay implementation facts used for the read-only benchmark:
- lantern/terminal.py MAX_OUTPUT = 200 * 1024;
- TerminalManager.replay_one() returns retained output + seq under the terminal lock;
- lantern/ws.py terminal_subscribe captures replay_one(), subscribes the peer, and sends terminal_replay;
- baseline-to-HEAD diff in lantern/terminal.py changes only a pywinpty error-message command example; lantern/ws.py has no relevant Foundation change.

## 3. Exact 100 KiB Markdown Preview — MEASURED

Verification artifacts:
- .plan/lantern-markdown-main-20261018/test_turn3_exact_perf.py
- .plan/lantern-markdown-main-20261018/test_turn3_exact_perf.json
- .plan/lantern-markdown-main-20261018/test_turn3_exact_perf.log
- .plan/lantern-markdown-main-20261018/test_turn3_preview_repeats.py
- .plan/lantern-markdown-main-20261018/test_turn3_preview_repeats.json
- .plan/lantern-markdown-main-20261018/test_turn3_preview_repeats.log

Environment/control:
- same G6;
- same Python 3.13.9;
- baseline 1b5939357... lan_drive.py and HEAD ffe3decb... main.py;
- both servers resident concurrently on ephemeral loopback ports;
- identical temporary root/config/cache model;
- deterministic file length exactly 102,400 bytes;
- warmed before sampling;
- alternating request order;
- p50/p95 wall latency, process CPU, recursively sampled process-tree RSS;
- body length checked for parity.

### Initial exact run

Command:
C:\Users\admin\miniconda3\python.exe .plan/lantern-markdown-main-20261018/test_turn3_exact_perf.py

Exact fixture:
- 102,400 bytes
- 80 requests per side
- response body parity: PASS, both 190,330 bytes

Initial result:
- baseline median 451.10 ms; p95 1002.99 ms
- HEAD median 404.88 ms; p95 1247.83 ms
- ratios: median 0.898, p95 1.244, CPU 1.018, RSS 0.872

The single p95 ratio 1.244 exceeds the proposed 20% review threshold. Because both distributions were visibly noisy with >1 s outliers and REVIEW explicitly requires evidence rather than one-run inference, this was not promoted directly to a regression claim.

### Reproducibility check — three fresh exact-100KiB rounds

Three fresh paired rounds were run with fresh servers; launch order alternated.

Round 1:
- baseline median/p95: 334.01 / 485.53 ms
- HEAD median/p95: 322.09 / 510.07 ms
- ratios: median 0.964; p95 1.051; CPU 1.050; RSS 0.875

Round 2, reversed server launch order:
- baseline median/p95: 315.42 / 508.15 ms
- HEAD median/p95: 313.59 / 477.36 ms
- ratios: median 0.994; p95 0.939; CPU 0.942; RSS 0.870

Round 3:
- baseline median/p95: 338.62 / 570.59 ms
- HEAD median/p95: 316.64 / 540.06 ms
- ratios: median 0.935; p95 0.946; CPU 0.887; RSS 0.876

Across these three repeat rounds:
- p95 ratios: 1.051, 0.939, 0.946
- median p95 ratio: 0.946
- response body parity: PASS every round, both sides 223,609 bytes in the repeat fixture
- all repeat-round p95 ratios are within the proposed <=1.20 degradation budget
- HEAD RSS is consistently lower by ~12–13%.

Classification:
- exact 100 KiB Preview measurement: PASS as measured/comparable;
- a reproducible >20% p95 regression was NOT reproduced;
- the first run demonstrates material host/process jitter and must remain in the evidence packet rather than be discarded;
- universal performance equivalence is NOT claimed.

## 4. Exact 200 KiB terminal replay — MEASURED

Verification artifacts:
- .plan/lantern-markdown-main-20261018/test_turn3_terminal_replay_worker.py
- terminal replay section of test_turn3_exact_perf.json/log

Measured path:
1. create TerminalManager with a fake PTY only to avoid native terminal lifecycle/spawn instability;
2. retain exactly 200 * 1024 = 204,800 bytes through TerminalManager's normal output-retention path;
3. execute the real lantern.ws dispatch() terminal_subscribe path;
4. execute terminal.replay_one(), WebSocket subscription, terminal_replay dict creation, JSON serialization and WS frame construction;
5. verify replay output stays exactly 204,800 bytes and seq remains 1.

This is a read-only deterministic replay-path benchmark. It deliberately does not benchmark native ConPTY spawn/input lifecycle, whose known E2E failure was already proven pre-existing and is outside this team's product-edit boundary.

Two runs per revision, 400 measured iterations each, 25 warmups each; run order:
baseline -> HEAD -> HEAD -> baseline.

Aggregate results, 800 iterations per revision:

Baseline 1b5939357...:
- median: 1.54405 ms
- p95: 34.1714 ms
- mean: 5.13179 ms
- CPU total: 3.125 s
- peak process-tree RSS: 29,057,024 bytes
- encoded WS frame: 205,128 bytes
- retained payload: 204,800 bytes

HEAD ffe3decb...:
- median: 1.74305 ms
- p95: 32.5141 ms
- mean: 4.72832 ms
- CPU total: 3.3125 s
- peak process-tree RSS: 28,889,088 bytes
- encoded WS frame: 205,128 bytes
- retained payload: 204,800 bytes

HEAD / baseline ratios:
- median: 1.129
- p95: 0.952
- CPU: 1.060
- RSS: 0.994

Classification:
- exact 200 KiB terminal replay path: PASS as measured/comparable;
- p95 and RSS are within the proposed Foundation review budget;
- CPU is ~6% higher across these short synthetic loops;
- retained bytes and framed bytes are identical;
- native PTY lifecycle correctness remains a separate pre-existing failing behavior, not converted to PASS by this benchmark.

## 5. F-T012 disposition from TEST

The two exact measurements requested by REVIEW Turn 4 are now present.

100 KiB Preview:
- MEASURED with exact 102,400-byte fixtures;
- body parity proven;
- first run showed noisy p95 ratio 1.244, but three fresh repeats did not reproduce that regression and produced p95 ratios 1.051 / 0.939 / 0.946;
- no reproducible Foundation performance regression established.

200 KiB terminal replay:
- MEASURED through retained-output + real WS subscribe/replay serialization path;
- exact 204,800-byte payload;
- p95 ratio 0.952, CPU 1.060, RSS 0.994;
- no measured replay performance blocker.

TEST does not sign the proposed <=20% p95 / <=25% RSS budget on behalf of REVIEW/owner. It only establishes the requested data and reproducibility limits.

Linux smoke, manual/live acceptance, owner budget/sign-off and broader release gates remain INCOMPLETE exactly as REVIEW Turn 4 stated. They were not broadened into this TEST slice.

## 6. Route

Both explicit measurable gaps from REVIEW Turn 4 are now closed with comparable baseline/HEAD evidence.

No new reproducible 002-owned implementation defect was found. The one initial 100KiB p95 over-budget sample did not reproduce across three additional controlled fresh rounds and is retained as variance evidence, not hidden.

Route REVIEW for final F-T012/F-T013 performance/architecture disposition. Do not route DEV from this evidence and do not claim Foundation/release DONE.

# TEST Turn 4 — FJP primary-acceptance Foundation evidence

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4
Role: TEST turn 4
Date: 2026-10-18 JST
Workspace owner repo: G6 E:\git-project\lantern
Incoming REVIEW: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn5_cdpa-idem-382a709ae8895eae9ec134d4.md

## 1. Assigned acceptance boundary

REVIEW Turn 5 required only the missing FJP acceptance slice for Foundation 002:

1. FJP Windows/real Edge parity from a clean detached worktree at runtime-equivalent commit b2ffd886795840f0db570b8c07a913b406e68e80.
2. FJP paired baseline -> b2ffd88 performance for:
   - 1,000-item listing;
   - exact 102,400-byte Markdown Preview;
   - exact 204,800-byte terminal replay.
3. Preserve the dirty FJP main checkout, live :9999/:10099, Pi/native-terminal implementation, CDPA and unrelated work.

No product implementation files were edited in either G6 or FJP.

Loaded verification-before-completion and webapp-testing skills.

## 2. FJP environment and preservation

FJP device:
- device: fjp / LPP00374779A
- repo: C:\Users\DuongNH66\Desktop\git\lantern
- OS: Windows
- Edge: 155.0.4283.45
- uv: 0.11.3
- dirty main HEAD before/after: fb06c40758f406feb70bbb26ccd3cecb6476dacc

Initial FJP root had extensive pre-existing dirty/untracked refactor WIP. TEST did not reset/stash/clean or modify it.

Remote fetch:
- command: git fetch origin main
- purpose: obtain clean remote objects without changing dirty checkout
- origin/main after fetch: b2ffd886795840f0db570b8c07a913b406e68e80
- baseline object 1b5939357bfd3748a1c56b5e491bc55026b0368b available after fetch
- dirty main status remained intact.

Clean detached worktrees created outside dirty main:
- C:\Users\DuongNH66\Desktop\git\lantern-test-head-turn4 @ b2ffd886795840f0db570b8c07a913b406e68e80
- C:\Users\DuongNH66\Desktop\git\lantern-test-base-turn4 @ 1b5939357bfd3748a1c56b5e491bc55026b0368b

Both were clean before testing.

Cleanup:
- both detached worktrees were removed from Git;
- one head directory initially returned Windows Permission denied during removal, was unregistered, then successfully removed with rmdir after processes exited;
- verification helper scripts and FJP-local JSON were deleted after copying raw JSON to G6 .plan;
- final FJP dirty main HEAD/status remained the original WIP shape; no live service restart occurred.

## 3. FJP real-Edge parity — PASS for selected F-T011 scope

Command from clean b2ffd88 worktree:

$env:LANTERN_E2E='1'
uv run --locked --with playwright --with pytest python -m pytest -q   tests/test_lan_multi_e2e.py   tests/test_crop_shared_e2e.py   tests/test_live_markdown_e2e.py   tests/test_run_launcher.py   tests/test_terminal_e2e.py

Environment:
- FJP Windows
- real Microsoft Edge 155.0.4283.45
- uv locked project environment
- disposable roots/ephemeral ports only
- no :9999/:10099 use

Expected:
Selected Foundation browser/WS/Markdown/Crop/launcher/terminal lifecycle scenarios pass on the primary FJP Edge environment.

Actual:
- 23 passed
- 0 failed
- 0 skipped in this selected suite
- pytest time: 125.62s
- process exit: 0

Important terminal disposition:
- Unlike G6, the exact terminal lifecycle E2E passed on FJP in this run.
- Therefore no FJP baseline replay of the failing terminal lifecycle case was required by REVIEW's conditional instruction ("for any terminal failure, compare baseline").
- This does not erase the separately observed G6 pre-existing terminal failure; it means the primary FJP acceptance environment did not reproduce it.

A subsequent optional FJP non-E2E core run:
uv run --locked --with pytest python -m pytest -q tests/test_app_architecture.py tests/test_app_http_contract.py tests/test_repository_upgrade.py tests/test_repo_layout.py
was terminated by the 28-second tool execution ceiling after printing "...". Classification: INCOMPLETE, not PASS. It is not used as acceptance evidence in this turn because the requested FJP slice was the real-Edge parity + paired performance.

## 4. FJP paired performance — raw evidence

Raw JSON copied into the owning G6 report directory:
.plan/lantern-markdown-main-20261018/test_turn4_fjp_perf.json

FJP execution environment:
- Python inside uv locked isolated environment: 3.14.3
- baseline: 1b5939357bfd3748a1c56b5e491bc55026b0368b
- head/runtime-equivalent: b2ffd886795840f0db570b8c07a913b406e68e80
- same machine and same uv environment
- same disposable data root
- separate temporary config/cache/work dirs
- ephemeral loopback ports
- alternating request order
- response body-length parity checked
- CPU and process-tree RSS sampled with psutil
- no live Lantern service interaction.

### 4.1 Listing 1,000 items — MEASURED / within proposed budget

N = 80 per side.

Baseline:
- median 678.4828 ms
- p95 1131.9954 ms
- CPU 50.109375 s
- peak process-tree RSS 51,339,264 bytes
- body length 85,430

b2ffd88:
- median 706.6103 ms
- p95 1255.764 ms
- CPU 50.890625 s
- peak process-tree RSS 42,369,024 bytes
- body length 85,430

HEAD/baseline ratios:
- median 1.0415
- p95 1.1093
- CPU 1.0156
- RSS 0.8253
- body parity: true

Classification:
PASS against the proposed <=20% p95 / <=25% RSS degradation budget. Formal owner approval of that budget remains separate.

### 4.2 Exact 100 KiB Markdown Preview — MEASURED / within proposed budget

Fixture:
- exactly 102,400 bytes

N = 60 per side.

Baseline:
- median 195.27075 ms
- p95 326.0383 ms
- CPU 11.1875 s
- peak process-tree RSS 51,998,720 bytes
- response body 233,905 bytes

b2ffd88:
- median 206.8749 ms
- p95 317.702 ms
- CPU 11.515625 s
- peak process-tree RSS 41,734,144 bytes
- response body 233,905 bytes

HEAD/baseline ratios:
- median 1.0594
- p95 0.9744
- CPU 1.0293
- RSS 0.8026
- body parity: true

Classification:
PASS against the proposed p95/RSS budget. No FJP Preview regression reproduced.

### 4.3 Exact 200 KiB terminal replay — MEASURED / within proposed budget

Measured path:
- TerminalManager retained output;
- exact 204,800-byte tail;
- real lantern.ws dispatch terminal_subscribe path;
- terminal_replay payload creation;
- JSON serialization + WebSocket frame construction;
- fake PTY used only to avoid native spawn lifecycle while timing replay itself.

Two runs per revision, 300 iterations/run.

Baseline aggregate:
- median 1.776575 ms
- p95 2.47855 ms
- CPU total 1.140625 s
- peak RSS 27,840,512 bytes
- encoded frame 205,106 bytes
- retained 204,800 bytes

b2ffd88 aggregate:
- median 1.295675 ms
- p95 1.48710 ms
- CPU total 0.78125 s
- peak RSS 27,918,336 bytes
- encoded frame 205,106 bytes
- retained 204,800 bytes

HEAD/baseline ratios:
- median 0.7293
- p95 0.6000
- CPU 0.6849
- RSS 1.0028

Classification:
PASS for the replay-performance contract. Native PTY lifecycle correctness is a different gate; FJP real-Edge terminal lifecycle also passed in section 3.

## 5. Acceptance classification

FJP primary Windows/Edge acceptance requested by REVIEW Turn 5:
- selected real-Edge Foundation/WS/Markdown/Crop/launcher/terminal suite: PASS, 23/23
- 1k listing p50/p95/CPU/RSS: MEASURED, within proposed budget
- exact 102,400-byte Preview p50/p95/CPU/RSS: MEASURED, within proposed budget
- exact 204,800-byte replay p50/p95/CPU/RSS: MEASURED, within proposed budget
- response/replay payload parity checks: PASS

No new reproducible Foundation-owned defect appeared on FJP.

Still not promoted to PASS:
- Linux smoke: remains INCOMPLETE from earlier verified environment blockers
- manual/live owner acceptance: INCOMPLETE
- formal owner sign-off on the proposed performance budget: INCOMPLETE
- broader 001/003 release gates: outside this narrow turn and remain as previously classified
- optional FJP non-E2E core rerun: INCOMPLETE due tool timeout, not relied on here.

## 6. Route

The specific FJP evidence gap identified by REVIEW Turn 5 is now closed with real FJP Edge and paired baseline/head performance data.

No implementation defect requires DEV from this slice.

Route REVIEW for Foundation F-T011/F-T012/F-T013 disposition and dependency decision for subsequent 003 work. Do not route DONE.

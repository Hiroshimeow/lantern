# TEST turn 1 — independent G6 verification (2026-10-18)

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role TEST | handoff from PLAN turn 1.

## Identity and safety
- Connected through owned MD G6 device `desktop-b5e4iue-87cea2af`, PowerShell in `E:\git-project\lantern`, Windows; branch `main`, SHA `b2ffd886795840f0db570b8c07a913b406e68e80`.
- Python `C:\Users\admin\miniconda3\python.exe` 3.13.9; Playwright 1.57.0; Edge 155.0.4283.45.
- Initial and final `git status --short`: solely `?? .pi/`. No tracked implementation files edited, .pi left intact. All E2E applications are separate ephemeral loopback servers with temporary data roots, not port 9999. No reset/stash/clean/restart/CDPA operation.
- Loaded MD skills `verification-before-completion` and `webapp-testing`. Read `AGENTS.md`, PLAN handoff, relevant Spec 001/002/003 spec/plan/tasks/research/audits, 002 historical `verification.md`, frozen oracle test, current E2E sources and 003 source-lag audit. Historical outcomes distinguished from this run.

## Independent evidence / exact reproducible commands

1. **PASS — native full Python without opt-in Edge**, command:
   `& 'C:\Users\admin\miniconda3\python.exe' -m pytest -q`
   - Expected: all enabled tests pass and skip counts explicit.
   - Actual: **208 passed, 108 skipped, 47 subtests passed, exit 0, 81.44s**.
   - Evidence: `.plan/lantern-markdown-main-20261018/test_turn1_full_pytest.log`.
   - LIMIT: 108 skipped means NO implied browser/whole release acceptance. Frozen `tests/test_app_http_contract.py` (15-case oracle) ran in this suite and passed.

2. **FAIL in terminal-owned/out-of-scope E2E; Markdown/Foundation causality NOT ESTABLISHED**, command:
   `$env:LANTERN_E2E='1'; & 'C:\Users\admin\miniconda3\python.exe' -m pytest -q tests/test_lan_multi_e2e.py tests/test_visual_feature_e2e.py tests/test_terminal_e2e.py tests/test_md_mode_switch_e2e.py`
   - Expected: all scheduled Edge scenarios pass on disposable loopback instances.
   - Actual: **33 passed, 4 skipped, 2 subtests passed; 1 failed, exit 1**. Failure `tests/test_terminal_e2e.py::TerminalLifecycleBrowserE2E::test_failed_spawn_then_real_terminal_and_stale_input`, timed out 16 seconds waiting for successful terminal session after deliberately rejected initial spawn at line 71. Repro is terminal/PTY ownership, not authorization to fix terminal in this team. The original 002 report lists 3 pre-existing failing Terminal Edge cases, but exact present failure has NOT been proven old/new identical by a paired replay; cannot mark Foundation parity as unconditional PASS.
   - Evidence: `.plan/lantern-markdown-main-20261018/test_turn1_edge_foundation.log`.

3. **PASS within measured browser runtime subset — Mermaid render/cap/PNG and content-independent network**, command:
   `& 'C:\Users\admin\miniconda3\python.exe' '.plan\lantern-markdown-main-20261018\test_turn1_markdown_runtime.py'`
   - Script itself is a verification-only artifact under ignored `.plan`; starts one disposable app via `main.py --root <temp> --host 127.0.0.1 --port <random> --config <temp> --cache-dir <temp>` and closes it.
   - Edge verified plain Markdown served 200 with **0 Mermaid bundle requests**. Mermaid document (flowchart, sequence, class, state, ER, Gantt, pie) served 200; **7/7 produced real SVG**, one local Mermaid bundle request, **0 external requests**, 0 JS page errors and 0 console errors in that clean render.
   - **7/7 PNG browser downloads** used names `mermaid-7-diagram-1.png` through `-7.png`, were nonempty, decode as images, contain nonwhite content. Image dimensions recorded in JSON.
   - Malformed diagram failed locally and next valid diagram rendered, oversize >60k refused, cap **24 wrappers** despite >24 fences; 24th success.
   - **PDF PARTIAL PASS**: Print action invoked (2 calls observed), headless Edge generated 8-page PDF (61,248 bytes); extracted selectable sentinel and a section title with PyMuPDF. Arrowheads, clipping and every diagram's readability need visual review, so full M-A9 is **INCOMPLETE**. Artifacts `test_turn1_markdown_artifacts/mermaid-seven-print.pdf`, `mermaid-seven-pdf-first.png`, seven PNGs and `mermaid-seven.png`.
   - Evidence: `.plan/lantern-markdown-main-20261018/test_turn1_markdown_runtime.log` and `.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/results.json`.

4. **FAIL — 001 M-A5 exact CSP/WebSocket contract, with important contract conflict**. Same Edge script in *actual Markdown visual preview*:
   - Expected from 001 spec: `connect-src 'none'` and preview-realm WebSocket blocked. Actual: `new WebSocket('ws://'+location.host+'/ws')` returned **opened**. `plugin.py:1273` intentionally selects `connect-src 'self'; worker-src 'self'` for `visual_markdown`, vs `connect-src 'none'` for other preview kinds. This is a real mismatch to 001 M-A5, **but** 003 three-mode Edit/Source and live WS behaviors may need same-origin connectivity. Do **NOT** simply force `connect-src 'none'` and break 003; DEV must isolate safe plain preview from interactive Markdown context or return a documented design contract conflict to PLAN.
   - Script initially checked response **header** CSP and recorded empty header / false `all_nonces_match`. That subcheck is **NOT_MEASURED** as nonce correctness: CSP is emitted as HTML `<meta http-equiv="Content-Security-Policy"> in `plugin.py:1345`, not HTTP header, and the script did not extract this meta correctly. Must rerun valid meta-nonce test. Unnonced same-origin test JS did **not execute** (PASS narrow behavior), not by itself proof for all CSP.
   - Evidence JSON `checks.websocket.result="opened"`; source `plugin.py:1273,1345`. Independent exploitation or live production impact not asserted.

## Gates not measured / closure disposition
- 002 full Edge parity: **INCOMPLETE** (terminal failure; surviving 4 browser skips; no truly paired old/new Edge comparison in this turn). 002 Linux smoke: **INCOMPLETE**, WSL environment blockers historically documented, not re-proved here. 002 F-T012 fresh balanced p95 CPU/RSS and terminal replay memory: **NOT_MEASURED**; retained `.plan/foundation_paired_perf.log` is historical and lacks formal CPU/RSS budget signoff. 002 F-T013 independent architecture review/manual owner acceptance: **INCOMPLETE**; former M365 worker failed before Send.
- 001 M-A1–M-A4 unit parser/security characterization: **PASS within existing automated suite**; M-A5 WebSocket contract **FAIL** (or requires explicit approved interactive-mode exception); M-A6 seven types/network **PASS** in G6 Edge subset; M-A7 cap/isolated failure **PASS** within supplied fixtures; M-A8 PNG 7/7 **PASS for nonempty/nonwhite/download naming** but pixel legibility manual **INCOMPLETE**; M-A9 full PDF visual **INCOMPLETE**; M-A10 runtime CDN **PASS observed subset**, dependency audit not repeated; M-A11 **NOT_MEASURED** (nine fresh FJP Chromium parse/eval attributed task samples, renderer and PNG <=100ms never run); M-A12 prior owner acceptance and LANTERN-SEC-001 reported by PLAN, not re-signed here.
- 003 proof MD-T000/T003, full byte-preserving corpus, CodeMirror POC, exact mapping, 500KB/5MB, UX 390/1280/1920, crop EXIF/GIF etc. **NOT MEASURED**; do not jump to implementation before 002 disposition. Historical `source_lag_ab_results.log` is pre-existing 5,500-line full-backdrop defect, not evidence of Foundation regression.

## Decision and next role
**Route DEV** for the concrete 001 Markdown preview CSP/WebSocket violation as *one bounded investigation/fix slice*, while keeping all terminal/Pi and 9999 untouched. DEV must establish whether spec's restrictive CSP applies to plain preview only versus integrated interactive Markdown and preserve 003 functionality; if mutually incompatible, route design conflict to PLAN rather than make a speculative security change. Minimal regression E2E should check actual **meta** nonce, plain and interactive contexts separately, and assert no unexpected WS for intended restricted scope. REVIEW/TEST afterward. Independently report the inherited terminal E2E failure to its owner without implementation here. 002 closure still **NOT APPROVED**; no DONE or release claim.
# TEST Turn 2 — Foundation 002 closure evidence

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4
Role: TEST turn 2
Date: 2026-10-18 JST
Workspace: G6 E:\git-project\lantern
Branch: main
Tested HEAD: ffe3decb4469cff36bb98f8afd6ba8e9e89af089
Incoming PLAN: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-plan_turn3_cdpa-idem-382a709ae8895eae9ec134d4.md

## 1. Scope, identity, safety

Loaded verification-before-completion, webapp-testing, and systematic-debugging skills. Read the PLAN turn 3 contract and relevant 002 Foundation acceptance material. No implementation file was edited. All new verification code/logs are under ignored .plan/lantern-markdown-main-20261018/.

Initial identity:
- git branch --show-current -> main
- git rev-parse HEAD -> ffe3decb4469cff36bb98f8afd6ba8e9e89af089
- git status --short -> only ?? .pi/
- Python C:\Users\admin\miniconda3\python.exe 3.13.9
- Prior TEST established Edge 155.0.4283.45 and Playwright 1.57.0 on the same G6.
- Live Lantern :9999 was never restarted or targeted; all browser/server tests use temporary roots and ephemeral 127.0.0.1 ports.
- No reset/stash/clean, no CDPA mutation, no Pi/native-terminal source edit.
- A detached baseline worktree was created only at .wt/test-foundation-baseline-turn2, verified clean, used for read-only baseline execution, then removed cleanly.
- Final git status --short -uall -> only ?? .pi/subagents.json.
- Separate .wt/lantern-bot was untouched.

## 2. TEST-A — F-T011 parity

### A1. Frozen HTTP / architecture / launcher core — PASS for measured scope

Command:
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_app_architecture.py tests/test_app_http_contract.py tests/test_run_launcher.py

Expected:
Current main preserves frozen Foundation HTTP behavior, two-instance/lifecycle architecture invariants, and launcher setup contract without touching live service.

Actual:
8 passed, 1 skipped, 21 subtests passed, exit 0, 10.09s.
The one skip is the opt-in real launcher process test; it was exercised separately in A2 with LANTERN_E2E=1.

Evidence:
.plan/lantern-markdown-main-20261018/test_turn2_foundation_core.log

Additional architecture/integration command:
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_app_architecture.py tests/test_repository_upgrade.py tests/test_repo_layout.py
git diff --check
git status --short -uall

Actual:
9 passed, 13 subtests passed, exit 0.
git diff --check exit 0; final tracked tree clean.
main.py is enforced as executable entrypoint by tests. Historical/documentation references to lan_drive.py remain in docs/config comments, so raw grep is not a zero-mention acceptance oracle.

### A2. Disposable Edge / WS / Markdown/Crop / real launcher — PASS for measured scope

Command:
set LANTERN_E2E=1, then:
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_lan_multi_e2e.py tests/test_crop_shared_e2e.py tests/test_live_markdown_e2e.py tests/test_run_launcher.py

Expected:
Real Edge two-context WS/browser contract, shared crop integration, live Markdown write/CAS/external-change behavior, and opt-in real Windows launcher pass using disposable roots/ports/processes.

Actual:
22 passed, exit 0, 55.74s.
No skips or failures in this selected opt-in slice.

Evidence:
.plan/lantern-markdown-main-20261018/test_turn2_foundation_edge.log

### A3. Previously failing terminal lifecycle case — VERIFIED PRE-EXISTING / OUTSIDE THIS TEAM

Baseline existence checks:
git cat-file -e 1b5939357bfd3748a1c56b5e491bc55026b0368b:tests/test_terminal_e2e.py
git diff 1b5939357bfd3748a1c56b5e491bc55026b0368b..HEAD -- tests/test_terminal_e2e.py

Result:
- The same test exists at baseline 1b5939357....
- Semantic test body is unchanged.
- Diff only changes documented uv invocation and server entrypoint from lan_drive.py to main.py.
- Baseline test blob 73e72615d18e1f6ee8c4f50227fd3155d77827ab.
- HEAD test blob 1b322d1a0935578a0cb19b7ba62eb8331acdff60.

Baseline isolated command:
LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_terminal_e2e.py

Baseline actual:
1 failed, exit 1, 21.29s.
Failure boundary: after intentional rejected terminal start, the subsequent normal terminal does not reach !pending && meta.running && meta.generation within 16s.

HEAD same command:
1 failed, exit 1, 20.40s, same line and condition.

Evidence:
.plan/lantern-markdown-main-20261018/test_turn2_terminal_baseline.log
.plan/lantern-markdown-main-20261018/test_turn2_terminal_head.log

Disposition:
The exact F-T011 terminal E2E failure is reproducibly pre-existing before Foundation 002 under the same G6/Python/Edge environment. It is not evidence of a 002 regression. The terminal behavior itself remains a real failing case and is out of scope for this Markdown team. TEST did not modify terminal/PTY/WS code.

### A4. Linux smoke — INCOMPLETE with verified environment blockers

Commands:
wsl.exe --list --verbose
wsl.exe -d Ubuntu-22.04 -- python3 --version
wsl.exe -d Ubuntu-22.04 -- python3 dependency probe
wsl.exe -d Debian -- python3 --version
wsl.exe -d Debian -- python3 dependency probe
Select-String pyproject.toml -Pattern requires-python

Actual:
- Ubuntu-22.04: Python 3.10.12, yaml/PIL/venv present.
- Repository requires Python >=3.12 at pyproject.toml:5, so this distro is unsupported for a valid smoke.
- Debian: Python 3.13.5 and venv present, but PyYAML absent and PIL absent.
- No package/global environment mutation was performed.

Verdict:
INCOMPLETE, not FAIL and not PASS. A compliant isolated Linux runtime with project dependencies is not currently available on G6.

## 3. TEST-B — F-T012 fresh controlled latency / CPU / process-tree RSS

Verification-only script:
.plan/lantern-markdown-main-20261018/test_turn2_perf.py

It launched baseline 1b5939357... using lan_drive.py and HEAD ffe3decb... using main.py concurrently on G6 with:
- same Python 3.13.9
- same 1000-file data root
- same generated 89,403-byte Markdown document
- independent temporary config/cache/work directories
- ephemeral loopback ports
- alternating request order after warmups
- psutil 7.1.3 CPU-time and recursively sampled process-tree RSS
- no live service interaction

Command:
C:\Users\admin\miniconda3\python.exe .plan/lantern-markdown-main-20261018/test_turn2_perf.py

Raw evidence:
.plan/lantern-markdown-main-20261018/test_turn2_perf.json
.plan/lantern-markdown-main-20261018/test_turn2_perf.log

Fresh results:

| Workload | N/side | Baseline median/p95 ms | HEAD median/p95 ms | p95 ratio | CPU ratio | Peak tree RSS ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| list 1000 files | 120 | 383.47 / 561.73 | 392.71 / 571.49 | 1.017 | 1.028 | 0.874 |
| Markdown Preview | 60 | 151.60 / 225.78 | 150.84 / 187.63 | 0.831 | 1.000 | 0.870 |
| /api/info | 120 | 4.61 / 76.28 | 4.16 / 77.56 | 1.017 | 0.586 | 0.854 |

Response body lengths match exactly for list (95,020) and Preview (162,040). /api/info lengths differ (901 vs 893) because paired processes use different temporary path strings; the frozen HTTP oracle independently covers behavior.

Interpretation:
- No measured workload shows >2% p95 degradation at HEAD in this run; Preview is faster.
- List CPU +2.8%; Preview CPU equal; info CPU lower.
- Sampled process-tree RSS is about 12.6–14.6% lower at HEAD.
- This is one controlled paired run, not proof of zero degradation under every load/order/cache state.
- Spec 002 proposes <=20% p95 and <=25% RSS as a review threshold, but explicitly requires approval. TEST records the measurements as PASS against that proposed numeric budget only; formal F-T012 release acceptance remains REVIEW/owner disposition.
- Terminal replay CPU/RSS was NOT_MEASURED because the reproducible terminal lifecycle failure is pre-existing and terminal implementation ownership is excluded from this team.

## 4. F-T013 review-ready architecture facts

Fresh evidence:
- Architecture/repository suite: 9 passed, 13 subtests.
- Frozen HTTP + architecture + launcher setup: 8 passed, 1 skipped, 21 subtests; opt-in launcher/browser slice later passes.
- Disposable Edge/WS/Markdown/Crop/launcher: 22 passed.
- Exact terminal E2E failure reproduces at pre-002 baseline and HEAD; no 002 regression is demonstrated there.
- Route modules import explicit domain owners such as config, filesystem, media, md_editor, working_copy, live_markdown and ws rather than entrypoint code.
- git diff --check PASS; tracked main tree clean; .pi/subagents.json untouched.
- Linux smoke INCOMPLETE for concrete environment reasons.
- Fresh paired G6 latency/CPU/RSS shows no material Foundation regression in measured workloads; formal performance/architecture sign-off remains a REVIEW/owner responsibility.
- Manual live product acceptance and service restart were deliberately not performed.

## 5. Acceptance classification and next dependency

F-T011:
- HTTP/oracle/architecture/two-instance/WS/Markdown/Crop/Windows launcher measured scopes: PASS.
- Exact terminal lifecycle behavior: FAIL, VERIFIED BASELINE / NOT A 002 REGRESSION / OUT-OF-SCOPE OWNER.
- Linux smoke: INCOMPLETE due unsupported Ubuntu Python and missing Debian project dependencies.
- No reproduced 002-owned Windows regression remains from this slice.

F-T012:
- Fresh list/Preview/info p50/p95 + CPU + tree RSS: MEASURED and within proposed p95/RSS budget.
- Terminal replay metric: NOT_MEASURED.
- Formal threshold/sign-off: INCOMPLETE pending REVIEW/owner.

F-T013:
- TEST evidence packet is ready.
- Independent structural/YAGNI/module/perf review: INCOMPLETE — next role REVIEW.
- Manual/live acceptance: INCOMPLETE, not implied.

Scoped 003 production GO/NO-GO:
GO only to independent F-T013 REVIEW and then dependency-ordered 003 work according to that review's disposition.
NO-GO for claiming Foundation fully released/accepted today.
Linux and formal review/manual gates remain open. Phase-0 non-destructive 003 characterization remains lawful.

## 6. Route

No new 002-owned implementation defect was reproduced. The prior terminal failure is now proven pre-existing at baseline and remains outside this team's ownership. Fresh performance evidence is adequate for architecture/performance evaluation, with limitations recorded.

Route REVIEW for F-T013 correctness/YAGNI/module ownership/performance disposition. Do not route DEV for the terminal failure and do not route DONE.

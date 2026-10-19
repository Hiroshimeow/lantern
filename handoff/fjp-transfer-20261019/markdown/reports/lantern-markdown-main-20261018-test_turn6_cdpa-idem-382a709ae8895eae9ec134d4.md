# TEST Turn 6 — independent M-A9 / M-A11 verification

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: TEST turn 6  
Date: 2026-10-18 JST  
Workspace: G6 E:\git-project\lantern  
Incoming DEV: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn5_cdpa-idem-382a709ae8895eae9ec134d4.md

## 1. Boundary, identity, preservation

Assigned boundary from DEV Turn 5 / REVIEW Turn 7:
1. independently re-run and visually judge M-A9 Print / Save as PDF after the Gantt readability correction;
2. independently re-run binding M-A11 nine-fresh-context FJP Google Chrome timing/network acceptance against the committed Tiny runtime.

Loaded verification-before-completion and webapp-testing skills.

G6 initial/current identity:
- branch main
- HEAD 16e538f04a84768eb540bb731d1ccc81e3547fbc
- prior relevant commit 1e3b77cda8d1d7e31019ccc79c38a6f63516817b
- tracked/staged clean; only preserved ?? .pi/subagents.json
- no :9999/:10099 restart/use, no CDPA mutation, no reset/stash/clean, no Pi/native-terminal edit.

FJP dirty main remained untouched. TEST used the pre-existing detached DEV measurement worktree only as a runtime-equivalent verification carrier and did not modify it.

## 2. Source/runtime equivalence used for FJP M-A11

Current G6 runtime hashes:
- static/vendor/mermaid-11.17.2.min.js SHA256 = 9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd
- current helper includes explicit runtime.parse(source) -> yieldUi() -> runtime.render(...).

FJP pre-existing detached worktree:
C:\Users\DuongNH66\Desktop\git\lantern-dev-ma11-turn4b
HEAD b2ffd886795840f0db570b8c07a913b406e68e80 with DEV's uncommitted Tiny/helper verification state.

Independent checks:
- FJP Tiny bundle SHA256 = **9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd**, byte-identical to current committed G6 bundle.
- FJP helper has the same executable parse -> yield -> render sequence. Direct full-file read shows the only difference at that change is the current G6 explanatory comment before the same await runtime.parse(source); no behavioral difference.
- git diff b2ffd88..16e538 on G6 shows plugin.py changes are print-only CSS for M-A9; they do not affect M-A11 loading/initialize/parse/render/PNG timing.

Therefore the FJP worktree is runtime-behavior-equivalent for the M-A11 operations being measured, while current G6 commit 16e538 is the exact M-A9 print source.

No claim is made that the FJP worktree is an exact commit checkout of 16e538; the equivalence boundary above is explicit.

## 3. M-A9 — PASS

### 3.1 Focused source regression

Command:
C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py

Expected:
Focused Markdown/print CSS assertions pass on current committed source.

Actual:
- **28 passed, 5 subtests passed**
- exit 0
- 1.15 s

Evidence:
.plan/lantern-markdown-main-20261018/test_turn6_plugin.log

### 3.2 Fresh served-browser seven-type runtime

Command:
C:\Users\admin\miniconda3\python.exe .plan\lantern-markdown-main-20261018\test_turn1_markdown_runtime.py

Expected:
Actual disposable served Preview renders seven Mermaid types, exports PNGs, preserves lazy/local network behavior, and generates current PDF.

Actual:
- exit 0
- 7/7 types rendered real SVG
- exactly 1 local Mermaid request on Mermaid page
- 0 external requests in seven-type fixture
- 0 page/console errors in the clean seven-type render
- 7/7 PNG downloads nonempty/nonwhite
- malformed/oversized isolation preserved
- cap remains 24 wrappers
- PDF regenerated: **5 pages**, 55,684 bytes
- selectable sentinel/title preserved

Evidence:
.plan/lantern-markdown-main-20261018/test_turn6_runtime.log
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/results.json

### 3.3 All-page PDF visual inspection

Command:
C:\Users\admin\miniconda3\python.exe .plan\lantern-markdown-main-20261018\render_pdf_pages_turn5.py

Actual:
5 current PDF pages rendered to:
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/pdf_pages_turn5/page-01.png ... page-05.png

Fresh visual inspection of all pages:
- page 1: flowchart + sequence complete; labels/connectors/arrowheads readable;
- page 2: class complete on one page; inheritance relation and +bark() readable;
- page 3: state complete on one page; start/end nodes and arrowheads visible;
- page 4: ER complete on one page; CUSTOMER / places / ORDER and cardinality relation visible;
- page 5: Gantt + pie complete; no split, no clipping, no Lantern UI chrome.

Fresh page-5 text metric extraction:
- Gantt date labels: **9.63 pt**
- Task A: **9.63 pt**
- Demo: **9.63 pt**
- Release title: **11.56 pt**

A 4x crop of the printed Gantt was independently inspected; dates, Demo, Task A and Release are visually legible. This is materially different from REVIEW Turn 7's reproduced ~4.8–5.3 pt micro-text failure.

Evidence:
.plan/lantern-markdown-main-20261018/test_turn6_pdf_metrics.py
.plan/lantern-markdown-main-20261018/test_turn6_pdf_metrics.log
.plan/lantern-markdown-main-20261018/test_turn1_markdown_artifacts/test_turn6_gantt_crop.png

**M-A9 classification: PASS for the governed seven-type PDF fixture.**

The pass is fixture-scoped; it does not assert arbitrary Mermaid print content can never overflow.

## 4. M-A11 — INCOMPLETE due FJP host-load blocker; no product FAIL claimed

Contract:
- FJP Playwright Chromium-family harness;
- actual served product Preview HTML;
- nine fresh contexts;
- plain Markdown 0 Mermaid requests;
- Mermaid page at most one local bundle request;
- bundle parse/evaluation median <=300 ms and no sample >500 ms;
- initialize / explicit parse / render / PNG attributable tasks <=100 ms;
- no external requests or unexpected browser errors.

Browser:
- Google Chrome 155.0.8059.79 on FJP.

### 4.1 Independent nine-context run under current FJP load

TEST created an independent verification-only Playwright/CDP harness outside the repository and ran it against the runtime-equivalent FJP Tiny worktree. The harness:
- gated the first product post-bundle yield before initialize/parse/render;
- used CDP ScriptDuration for conservative bundle attribution;
- wrapped real Mermaid initialize/parse/render;
- measured PNG script/toBlob/Long Tasks;
- recorded request ledger, external requests, page errors and console errors.

A raw second run is retained at:
.plan/lantern-markdown-main-20261018/test_turn6_fjp_ma11_heavy.json

Observed under the loaded host:
- bundle median **745.404 ms**
- bundle max **1000.286 ms**
- initialize max ~21.1 ms
- explicit parse max ~88.2 ms
- render max ~257.8 ms
- PNG script max ~4.84 ms
- PNG toBlob max ~30.2 ms
- all plain pages: 0 Mermaid bundle requests
- all Mermaid pages: exactly 1 bundle request
- all external requests: 0
- page errors: 0
- console errors: 0
- all PNG downloads nonempty

These timing values are over budget, but **they are not classified as a reproducible product FAIL** because REVIEW Turn 7 explicitly states the previously observed heavy-host-load slowdown is environment sensitivity and must not alone be used as regression proof.

### 4.2 Controlled-host retry could not legally reach its precondition

To separate product cost from host contention, TEST independently attempted the same nine-context harness with the same control used by the accepted DEV diagnostic:
- wait for FJP total CPU <15% before each fresh context;
- abort instead of cherry-picking if the host does not settle.

Actual:
- controlled harness waited **120 seconds**;
- FJP never settled below 15%;
- controlled run aborted with:
  RuntimeError: host CPU did not settle below 15%, last=64.6

Fresh standalone five-sample CPU probe immediately afterward:
[38.7, 46.8, 37.3, 60.6, 64.7] %

Evidence:
.plan/lantern-markdown-main-20261018/test_turn6_fjp_cpu_blocker.txt

This is a concrete external/environment prerequisite failure. TEST did not stop user processes, terminate unrelated Chrome/apps, alter CDPA, or otherwise manipulate FJP merely to manufacture a passing benchmark.

### M-A11 classification

- lazy/network invariants: **PASS in the loaded-host run** (0 bundle on plain, exactly 1 local bundle on Mermaid, 0 external, 0 browser errors);
- PNG governed main-thread timing: **PASS in the loaded-host run**;
- binding bundle/render performance acceptance: **INCOMPLETE**, because the only fresh independent runs occurred under measured host saturation and the controlled acceptance run could not satisfy its <15% host-load precondition;
- **NOT a product PASS**;
- **NOT a product FAIL** from this turn.

The prior DEV controlled diagnostic remains encouraging but is not substituted for independent TEST.

## 5. Preservation / cleanup

FJP:
- dirty main HEAD/state preserved;
- pre-existing lantern-dev-ma11-turn4b state preserved exactly (its prior modified Tiny/helper files and untracked dev harness remain; TEST added no files inside that worktree);
- TEST-only scripts/results outside the repo were deleted after copying raw evidence to G6;
- no user/global browser/dependency installation.

G6 final:
- HEAD still 16e538f04a84768eb540bb731d1ccc81e3547fbc
- tracked/staged clean
- only ?? .pi/subagents.json
- git diff --check remains clean.

## 6. Disposition / route

Verified:
- **M-A9 PASS** independently on committed 16e538.
- The concrete R7-1 Gantt readability defect is repaired for the governed fixture.
- No new M-A9 implementation defect routes to DEV.

Still unresolved:
- **M-A11 performance = INCOMPLETE** because FJP is currently CPU-saturated and the controlled independent acceptance precondition cannot be met.
- M-A12 personal owner/security acknowledgement remains INCOMPLETE.
- 002 residual owner/manual/Linux gates remain unchanged.
- 003 remains legally actionable and must not be stalled by this external M-A11 measurement condition.

Per TEST role contract, an external/non-implementation evidence gap routes to PLAN rather than inventing PASS/FAIL or looping DEV.

**Route PLAN.** PLAN should preserve M-A9 PASS, keep M-A11 open for a later low-load FJP retry, and continue dependency-ordered legally actionable work (003 Phase 0) without claiming Spec 001 release DONE.

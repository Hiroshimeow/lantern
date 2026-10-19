# PLAN Turn 5 — preserve 001/002 accepted evidence; start 003 Phase-0 proof slice

**Team/task:** `lantern-markdown-main-20261018` / `cdpa-idem-382a709ae8895eae9ec134d4`  
**Role/date:** PLAN turn 5 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-test_turn6_cdpa-idem-382a709ae8895eae9ec134d4.md`  
**Decision:** **ROUTE DEV** for exactly two proof-first Spec-003 tasks: **MD-T000 Source typing/performance characterization** and **MD-T001 exact-byte fidelity corpus/characterization**. Do not begin the Source editor rewrite, CodeMirror integration, mapping engine, Crop changes, or any Pi/native-terminal work in this DEV turn.

## 1. Repository truth re-verified

- Current G6 `main` HEAD: **`16e538f04a84768eb540bb731d1ccc81e3547fbc`**.
- `origin/main`: **`b2ffd886795840f0db570b8c07a913b406e68e80`**; local main is **4 commits ahead / 0 behind**:
  1. `3bfaa2e test(markdown): define typed preview CSP profiles`
  2. `ffe3dec test(markdown): harden preview CSP evidence`
  3. `1e3b77c fix(markdown): bound Mermaid print and render work`
  4. `16e538f fix(markdown): keep Gantt print text readable`
- Tracked/staged tree is clean; `git diff --check` exit 0; only preserved unrelated `?? .pi/subagents.json`.
- Existing worktrees:
  - root/main = current owned Markdown workspace;
  - `.wt/lantern-bot` has independently advanced to `9d39a0f...` and is strictly out of this team's ownership;
  - `.wt/lantern-ma-profile-turn4` is an existing detached profiling worktree. Do **not** delete/clean/rebase it in this slice.
- Re-read `AGENTS.md`: root/main owns Markdown/Preview/Edit/Crop; real `.md` is authoritative; `md_temp` is accepted snapshot; characterize before structural refactor; never guess source positions; no destructive Git or live service operations.
- The required 003 proof files are currently absent:
  - `tests/test_source_typing_perf_e2e.py` = missing;
  - `tests/test_markdown_roundtrip_corpus.py` = missing;
  - `tests/fixtures/md-fidelity/` = missing.
  Therefore MD-T000/T001 are concrete actionable DEV work, not duplicate implementation.

## 2. Spec 001 disposition carried forward

### Accepted / preserve

- **M-A8 PASS** from independent TEST Turn 5 for the governed seven PNG exports:
  - all seven exact PNGs decoded, non-empty/nonwhite, correct filenames;
  - fresh visual inspection found required labels/connectors/arrowheads/cardinality/bar/pie content present.
- **M-A9 PASS** from independent TEST Turn 6 on committed `16e538f`:
  - 7/7 Mermaid types rendered;
  - 5-page Chromium PDF regenerated from actual served Preview;
  - all pages visually inspected;
  - no class/state/ER split, no clipping or Lantern UI chrome;
  - Gantt labels now independently measured at about **9.63 pt** and title **11.56 pt**, materially fixing REVIEW Turn 7's ~4.8–5.3 pt micro-text defect.
- Tiny runtime architecture from `1e3b77c` was independently REVIEWed in Turn 7 as a sound same-version mature upstream substitution:
  - official `@mermaid-js/tiny@11.17.2`;
  - local/offline one-request loading;
  - current SHA-256 `9a04338a4eb73a5bd449461f12becad20311fa75a6ca41f89fce8f055e7c2bfd`;
  - required seven diagram types retained;
  - no custom hand-built tree-shaken runtime.
- Dedicated typed-CSP tests/docs from `3bfaa2e` + `ffe3dec` remain accepted technical evidence. Do not reopen them during 003 Phase 0.

### Still explicitly INCOMPLETE

- **M-A11 binding performance acceptance:** independent TEST Turn 6 correctly refused a false PASS/FAIL.
  - Loaded-host FJP run: bundle median **745.404 ms**, max **1000.286 ms**, render max ~**257.8 ms**, but host was heavily saturated.
  - Controlled retry required FJP CPU <15% and waited 120 s; host never settled, last observed **64.6%**; immediate CPU samples were **38.7–64.7%**.
  - Network/lazy invariants remained green under load: plain 0 Mermaid bundle, Mermaid exactly 1 local bundle, 0 external, 0 page/console errors; PNG governed timing remained within contract.
  - Prior DEV low-load FJP diagnostic was within thresholds but is **not** substituted for independent TEST.
  - Classification: **external/environment measurement blocker; M-A11 remains INCOMPLETE, not product PASS and not product FAIL**. Retry later only when the FJP host can satisfy a controlled low-load precondition; do not kill user processes or manipulate unrelated Chrome/CDPA to manufacture acceptance.
- **M-A12 personal owner/security acknowledgement:** still **INCOMPLETE**. No agent may sign this on the owner's behalf. `LANTERN-SEC-001` remains open.

These two unresolved gates do **not** justify stalling legally actionable 003 proof work.

## 3. Foundation 002 dependency disposition carried forward

REVIEW Turn 6 independently reproduced the primary FJP technical acceptance slice and found no new Foundation-owned regression:

- FJP Edge selected slice **23/23 passed**;
- 1k list p95 ratio **1.1093**, RSS **0.8253**;
- exact 100 KiB Markdown Preview p95 ratio **0.9744**, RSS **0.8026**;
- exact 200 KiB replay p95 ratio **0.6000**, RSS **1.0028**;
- module/lifecycle architecture accepted as lean enough for the approved Foundation boundary.

Therefore 002 is **technically sufficient for dependency progression into 003 proof work**.

Still separate/final gates:
- Linux smoke execution itself remains INCOMPLETE with documented environment blockers;
- manual/live owner acceptance remains INCOMPLETE;
- explicit owner budget approval remains INCOMPLETE;
- no live deployment/restart is authorized.

Do not rerun Foundation loops merely to increase counts and do not modify terminal/PTY/WS code in this team.

## 4. Why DEV now, not TEST/REVIEW/PAUSE

Spec 003 explicitly requires **proof before implementation**. Its Phase-0 MD-T000/T001 files do not exist. Existing historical Source audit already proves a material pre-002 defect:
- current 5,500-line Source p95 previously measured about **132.63 ms**;
- **99,054 backdrop DOM nodes** were added across nine keystrokes;
- `renderSourceDiff` clears and rebuilds the whole backdrop;
- same frontend blob/behavior existed before Foundation 002, so this is a 003 product defect, not a proven Foundation regression.

That historical audit is strong diagnosis but is not the committed repeatable acceptance harness/corpus required by 003. The smallest next role is therefore DEV to lock two characterization artifacts. M-A11 is externally blocked at this moment, but 003 is actionable; PAUSE is not justified.

## 5. DEV Turn 6 — exactly TWO coherent subtasks, proof/test files only

### Subtask 1 — MD-T000: Source typing/performance characterization

**Create:** `tests/test_source_typing_perf_e2e.py`.

Goal: make the current Source defect reproducible with an opt-in disposable Edge harness **before** changing Source implementation.

Required coverage:

1. **Fixtures/workloads**
   - deterministic 900-line and 5,500-line Markdown;
   - deterministic ~500 KB and ~5 MB Markdown;
   - CJK content and composition/IME-oriented input path;
   - wide/30-column table/text fixture.
   Large fixtures should be generated deterministically in test/temp storage rather than committing a 5 MB blob unless there is a concrete reason.
2. **Use actual product Source mode**
   - disposable root/config/cache;
   - ephemeral loopback port;
   - real Edge/Chromium-family browser already available on G6;
   - never live :9999/:10099.
3. **Measure from the end-user typing path**
   - input/keypress-to-next-paint or equivalent browser-observed latency;
   - p50/p95 key wall time with sample count recorded;
   - Long Task/frame evidence where observable;
   - MutationObserver counts;
   - number of DOM nodes added/removed in Source diff/backdrop;
   - main-document navigation count (must expose whether any real reload occurs);
   - `/api/work/write` POST count and relevant state GET count;
   - current real `.md` hash/bytes and `md_temp` hash/bytes before/after typing/short-debounce write.
4. **Invariant classification**
   - write-through must modify real `.md` after the current short debounce;
   - `md_temp` must not silently change without Accept/Save;
   - no focus/caret-reset or main-document navigation may be called PASS if observed;
   - the fixed 5,500-line acceptance target is p95 **<40 ms** and **no full-backdrop rebuild**.
5. **Do not falsify the known baseline**
   - if current 5,500-line Source remains >40 ms/full-rebuild, report it as the expected **acceptance FAIL / characterization success**;
   - do not lengthen debounce, disable diff, reduce fixture size, or weaken the threshold to make the baseline green;
   - 500 KB/5 MB final comparative threshold is not yet fixed until MD-T003 mature-upstream POC; record measurements, memory/DOM behavior and failures without inventing a PASS threshold.
6. **Test-suite hygiene**
   - use the repository's existing opt-in E2E convention so normal native/full tests are not broken solely because a known Phase-0 acceptance defect is intentionally characterized;
   - preserve an explicit machine-readable `within_budget` / defect classification in raw JSON/report, not a misleading green-only assertion;
   - store raw run JSON under this team's ignored `.plan/lantern-markdown-main-20261018/`.

Do **not** edit `static/markdown_visual_shell.js`, CSS, Source renderer, backend store, or add production telemetry in this task. Use browser `MutationObserver`, `PerformanceObserver`, request listeners and existing public APIs. If product-only instrumentation is genuinely unavoidable, stop and route PLAN instead of adding hidden measurement code.

### Subtask 2 — MD-T001: exact-byte fidelity corpus and characterization

**Create:**
- `tests/fixtures/md-fidelity/`
- `tests/test_markdown_roundtrip_corpus.py`

Corpus must minimally cover:
- UTF-8 BOM;
- CRLF;
- mixed CRLF/LF;
- no final newline;
- 30-column table;
- nested lists;
- fenced code;
- raw HTML/comments;
- frontmatter;
- CJK/Unicode;
- repeated identical paragraphs/headings/table cells/rows.

Required evidence:

1. Hash/store **original raw bytes**, not only decoded text.
2. Exercise no-op load/mode-switch and one-block edit paths through current product surfaces that actually write Markdown.
3. For each edit, define the intended changed byte span and hash unaffected prefix/suffix or exact unchanged regions.
4. **PASS only if bytes outside the intended operation remain byte-identical.**
5. Separately record:
   - real `.md` bytes/revision after edit;
   - `md_temp` bytes/revision before Accept/Save;
   - whether no-op causes any write/normalization;
   - Source-mode edit behavior;
   - current Visual/Milkdown one-block serialization behavior where safely exercisable.
6. If Visual serialization changes unrelated whitespace/EOL/BOM/comments/frontmatter, record a concrete **FAIL** fixture and exact byte diff. Do **not** fix serializer/mapping in this turn; that feeds MD-T002/T009.
7. Do not broaden into external-writer/two-tab handling (MD-T005), source-range mapping (MD-T002), one-diff-engine design (MD-T006), or Crop.

Prefer small human-readable checked-in fixtures plus generated large variants; never normalize fixture line endings through Git accidentally. If CRLF/mixed-EOL/BOM bytes require `.gitattributes` fixture protection, add only the narrow fixture-path rule and explain it; do not alter repository-wide EOL behavior.

## 6. Allowed changed files for this DEV slice

Expected tracked scope:
- `tests/test_source_typing_perf_e2e.py`;
- `tests/test_markdown_roundtrip_corpus.py`;
- files under `tests/fixtures/md-fidelity/`;
- optionally a **narrow fixture-only** `.gitattributes` rule if raw-byte preservation demonstrably requires it.

Expected ignored evidence:
- raw JSON/logs/screenshots under `.plan/lantern-markdown-main-20261018/`.

**No product runtime source changes are authorized in this slice.** No package/dependency installation is authorized. No CodeMirror package change yet. No new Markdown serializer/diff engine/store abstraction. No Pi/native-terminal file. No cleanup of unrelated worktrees.

## 7. DEV verification and next route

DEV must:
- run the new benchmark/corpus tests explicitly and retain stdout/exit/raw JSON;
- run the existing focused `tests/test_live_markdown.py` and relevant current Markdown-mode tests to ensure the proof harness itself did not alter semantics;
- run syntax/static checks;
- run default/full native suite if feasible and report skips; do not claim opt-in acceptance from default skips;
- `git diff --check`;
- verify final status preserves only pre-existing unrelated `.pi/subagents.json` plus any known untouched worktrees;
- commit only the two proof-task tracked files/fixtures if the characterization methodology is coherent, even when the product acceptance result is red; the report must distinguish **test harness success** from **product acceptance failure**.

Then route **REVIEW** (or TEST if the team router selects the independent verification role) to challenge:
- benchmark attribution and sample validity;
- false positives/false greens;
- raw-byte fixture integrity;
- YAGNI/test-framework duplication;
- whether any test accidentally encodes implementation details instead of the 003 contract;
- whether the results genuinely justify the next MD-T002/T003 design slice.

## 8. Following dependency order after MD-T000/T001

Do not start these in the same DEV turn.

1. **MD-T002:** prove deterministic source-byte/span -> mdast/ProseMirror mapping on duplicates, tables, fences and CJK; fail visibly on unmapped/ambiguous nodes, never guess.
2. **MD-T003:** isolated CodeMirror 6 merge/unified POC against current environment: inline/gutter hunks, viewport behavior, CRLF/BOM, CJK/IME, deletion widgets, 500 KB, no format mutation. Verify package/version before installing anything; do not infer `@codemirror/merge` availability from the umbrella package.
3. Only after REVIEW/TEST of T002/T003 choose the Source implementation for T007/T017.
4. Then T004–T006 data/CAS/diff contract, T007/T017 Source, T008/T009 Visual mapping/byte-safe strategy, T010/T011 Preview/anchor/paged, T018 UX, T012–T014 Crop, T015/T016 final acceptance/integration.

M-A11 must be retried independently on FJP when host load can satisfy controlled measurement conditions; M-A12/002 owner gates remain final release blockers, not reasons to suspend Phase-0 engineering.

**Turn 5 route = DEV.**

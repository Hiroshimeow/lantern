# REVIEW Turn 5 — Foundation 002 performance/acceptance disposition

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 5 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-test_turn3_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE TEST.** TEST Turn 3 closes the two exact **G6** measurement gaps from REVIEW Turn 4: an exact 102,400-byte Markdown Preview benchmark and an exact 204,800-byte terminal-replay benchmark. The test implementation/evidence is technically acceptable as controlled supporting data, and no 002-owned implementation regression is reproduced.

However, Spec 002 still explicitly requires **FJP Windows/Edge as the primary acceptance environment** and F-T003/F-T011 require the performance baseline and real Edge parity on FJP. All current closure measurements in TEST Turns 2–3 were performed on G6. This is a material acceptance-evidence gap, not a product-code defect. Route TEST for the missing FJP acceptance slice rather than PLAN/DONE.

## Sources and independent verification

Read `AGENTS.md`, TEST Turn 3, REVIEW Turn 4, PLAN Turn 3, Spec 002 `spec.md`, `plan.md`, `tasks.md`, Foundation verification/decision material, exact Turn-3 benchmark scripts and JSON artifacts, and current repository state. Loaded `ponytail-review` and `verification-before-completion`.

Fresh REVIEW checks on G6:

- HEAD remains `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`; tracked/staged tree clean; only unrelated `?? .pi/subagents.json`.
- `git diff --check` -> **exit 0**.
- Turn-3 artifact parse reproduces:
  - exact Preview fixture **102,400 bytes**;
  - initial Preview p95 ratio **1.2441**, CPU **1.0179**, RSS **0.8722**;
  - repeat p95 ratios **1.0505 / 0.9394 / 0.9465**, median **0.9465**, body parity true;
  - terminal replay payload **204,800 bytes**, p95 ratio **0.9515**, CPU **1.060**, RSS **0.9942**, encoded frame parity **205,128 bytes**.
- Fresh current-HEAD replay-worker execution, 120 iterations/10 warmups -> **exit 0**, retained **204,800 bytes**, frame **205,128 bytes**, seq 1, confirming the measured replay path still executes as described. This fresh one-sided run is not a baseline comparison and is not presented as such.
- Current HEAD versus origin/main `b2ffd88` contains only Spec-001 documentation/test changes: no production runtime delta. Thus Foundation runtime behavior at current HEAD is equivalent to the already pushed `b2ffd88` runtime for 002 acceptance.

## Review of Turn-3 benchmark correctness

### Exact 100 KiB Preview

`.plan/.../test_turn3_exact_perf.py:12,38-51,59-126` constructs exactly `100*1024` bytes and asserts the length, runs baseline and HEAD concurrently with identical root/config/cache data, warms both, alternates request order, records latency, process-tree CPU/RSS and response lengths.

The first controlled run had a p95 ratio **1.244**, above the proposed <=1.20 threshold. TEST correctly did **not** hide it. The three fresh-server repeat rounds all fell below 1.20 and reversed launch order in round 2. This is sufficient to classify the first excursion as **not reproducibly attributable to Foundation** under the tested G6 conditions, while retaining the variance as evidence. It does **not** prove universal performance equivalence.

### Exact 200 KiB replay

`.plan/.../test_turn3_terminal_replay_worker.py` retains exactly 204,800 bytes through `TerminalManager`, exercises real `lantern.ws.dispatch(... terminal_subscribe ...)`, serializes the replay and constructs the WS frame. It avoids native ConPTY spawn intentionally.

That scope is acceptable for the specific replay-performance contract: it measures retained-tail retrieval + subscription + serialization/framing without crossing the team's native terminal implementation boundary. It does **not** turn the separately failing native terminal lifecycle E2E into PASS. Baseline→Foundation diff in `lantern/terminal.py` is only the launcher error-message example; `lantern/ws.py` has no Foundation replay behavior change.

## Architecture / YAGNI / ownership / UX / scalability

No new product code was added in this TEST slice. The benchmark scripts live under ignored `.plan` and should remain evidence tooling, not become a permanent second benchmark framework unless future repeated release work justifies it.

- **Over-engineering/YAGNI:** no product abstraction/dependency introduced. The isolated fake-PTY replay worker is proportionate and smaller than standing up native PTY lifecycle merely to time replay serialization.
- **Scope drift:** none in G6 slice; no Pi/native-terminal implementation edits, no :9999, no CDPA, no source-of-truth/Markdown behavior changes.
- **Maintainability/module ownership:** benchmark touches public/current owners `TerminalManager` + `ws.dispatch`; it does not duplicate terminal state or create a second replay implementation.
- **Scalability/extensibility:** process-tree RSS/CPU and exact payload/frame sizes are useful bounded evidence; they are not a capacity model for many terminals or sustained LAN concurrency.
- **Mature upstream alternatives:** no framework change is warranted. Existing Python stdlib/psutil/WS framing path is enough for this characterization.
- **UI/UX:** not exercised by these two synthetic measurements. Manual/live UX remains INCOMPLETE.
- **Regression/performance:** no reproducible G6 Foundation regression is shown in the exact Preview/replay workloads. Performance-budget approval itself remains an owner/reviewer decision.

Ponytail finding: **Lean already for a disposable verification harness; no production simplification requested.**

## Material acceptance gap — FJP has not been proven

This is the blocking review finding for this turn.

### R5-1 — F-T003/F-T011/F-T012 evidence is on the wrong primary acceptance machine

**Contract locations:**
- `specs/002-lantern-foundation/plan.md:12`: **Windows FJP/Edge is the primary acceptance environment**.
- `specs/002-lantern-foundation/tasks.md:8`: F-T003 requires 100 KiB Preview, 1k listing and 200 KiB terminal replay p50/p95/CPU/RSS **on FJP**.
- `tasks.md:20`: F-T011 requires actual **FJP Edge** with the selected E2E suites.
- `spec.md:67`: SC-FND-04 requires **FJP Windows Edge smoke PASS** plus Linux smoke or evidenced blocker.
- `tasks.md:23`: F-T012 compares post-refactor performance against F-T003.

**Evidence:** TEST Turns 2–3 explicitly ran G6. Those numbers are valuable and internally comparable, but they do not satisfy the committed FJP acceptance clauses.

Fresh REVIEW inspection of FJP shows why this was missed but does not waive it:
- FJP repo `C:\Users\DuongNH66\Desktop\git\lantern` is still at `fb06c40758f406feb70bbb26ccd3cecb6476dacc` with extensive unrelated dirty/untracked refactor WIP.
- FJP dirty main was not modified by REVIEW.
- FJP currently does **not** have object `ffe3dec` locally, but `origin/main` is `b2ffd886795840f0db570b8c07a913b406e68e80`.
- G6 independently verifies `b2ffd88..ffe3dec` changes only 001 spec/test files, so `b2ffd88` is production-runtime equivalent for Foundation 002.
- FJP has `uv 0.11.3`; bare `python` is not available on PATH. This is an environment constraint, not proof that FJP acceptance is impossible.

**Required correction:** TEST must perform Foundation acceptance from a **clean FJP detached worktree**, never from or over the dirty FJP main checkout. Fetching remote objects is acceptable only if it does not touch/reset/stash/clean dirty work. Use exact `b2ffd88` (runtime-equivalent to current HEAD for 002) and pre-Foundation `1b593935...` for paired baseline where available. Use `uv --locked`/isolated project environment rather than a global Python install. All servers must use disposable roots/ephemeral ports and must not touch FJP :9999/:10099.

## Linux / manual / owner gates

Linux smoke remains **INCOMPLETE**, with prior concrete blockers (Ubuntu Python below required >=3.12; Debian missing project deps in its existing environment). This is not converted to PASS here.

Manual/live owner acceptance and formal budget sign-off also remain INCOMPLETE. The G6 repeat evidence supports accepting the **proposed** <=20% p95 / <=25% RSS budget as reasonable for the measured workloads, but REVIEW does not impersonate owner sign-off.

## Next TEST slice — only the missing FJP acceptance

1. **FJP Edge parity:** from a clean detached FJP worktree at runtime-equivalent `b2ffd88`, run the selected Foundation Edge/WS/Markdown/Crop/launcher evidence required by F-T011, including the exact terminal lifecycle case. For any terminal failure, compare the same pre-Foundation baseline on FJP and preserve the out-of-scope disposition; do not patch terminal/PTY/WS.
2. **FJP paired performance:** on the same FJP machine, collect comparable baseline→`b2ffd88` p50/p95/CPU/process-tree-RSS for 1k listing, exact 102,400-byte Markdown Preview and exact 204,800-byte replay. Retain noisy/outlier rounds; do not cherry-pick. Use the minimal existing Turn-3 methodology rather than creating another framework.

If FJP clean-worktree/locked-environment setup cannot be made safely without modifying the dirty checkout or global environment, return PLAN with the exact blocker. If measurements complete and no new Foundation-owned regression appears, route REVIEW/PLAN for closure. Do not rerun unrelated G6 suites.

## Preservation

`.pi/subagents.json`, dirty FJP WIP, `.wt/lantern-bot`, Pi/native terminal implementation, live :9999/:10099, Markdown `.md` source truth, `md_temp`, CAS and 003 source/UX work remain untouched.

**Required route: TEST.**

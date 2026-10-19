# REVIEW Turn 4 — Foundation 002 closure review

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 4 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-test_turn2_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE TEST.** No new Foundation-owned product defect is reproduced. The structural refactor is technically reviewable and the measured HTTP performance is not a blocker, but F-T012 still lacks two explicit acceptance measurements required by Spec 002: the exact 100 KiB Markdown workload and the 200 KiB terminal-replay p95/CPU/RSS comparison. Linux/manual/owner gates remain incomplete and must not be promoted to PASS. A repeated broad test sweep is not required; TEST should close only these measurable gaps, then return to REVIEW/PLAN.

## Independent sources and verification

Read `AGENTS.md`, PLAN Turn 3, TEST Turn 2, Foundation `spec.md`, `plan.md`, `tasks.md`, `verification.md`, `decisions.md`, actual `main.py`, `lantern/application.py`, `lantern/http/server.py`, route ownership/imports, `tests/test_app_architecture.py`, performance artifact/script, and the exact pre-002→HEAD terminal E2E diff. Loaded `ponytail-review` and `verification-before-completion`.

Fresh REVIEW run on current G6 HEAD:
- `C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_app_architecture.py tests/test_app_http_contract.py tests/test_repository_upgrade.py tests/test_repo_layout.py` -> **10 passed, 28 subtests passed, 12.06 s, exit 0**.
- Repository state rechecked: branch `main`, HEAD `ffe3dec...`, only unrelated `?? .pi/subagents.json`; no tracked/staged implementation delta after TEST.
- Current Foundation implementation has one canonical five-line `main.py`; `Application` composes per-instance WS/Terminal/Bot/SCM/Markdown/File/Media/View/Crop services; architecture test creates two simultaneous applications and independently verifies root/runtime state.
- Runtime legacy `lan_drive.py` callers are absent. Remaining non-doc occurrences are an old config comment and tests asserting deletion.
- Exact `tests/test_terminal_e2e.py` diff from baseline `1b593935...` to HEAD changes only the documented uv command and server entrypoint `lan_drive.py -> main.py`; test semantics are unchanged. TEST Turn 2's baseline and HEAD runtime failures are therefore credible evidence that this exact lifecycle failure predates the Foundation refactor. REVIEW did not rerun the two 20-second terminal failures, so those runtime results remain attributed to TEST, not a fresh REVIEW run.

## Architecture / ownership / YAGNI review

**No material architectural correction required before proceeding.**

- `main.py` is a true entrypoint, not a compatibility façade.
- `lantern/application.py` is the lifecycle/composition owner; stateful managers are per-application, and fresh two-instance tests pass.
- HTTP route mixins access `self.app`, which is broad coupling, but these files remain HTTP adapters and business behavior is still owned by File/Media/Crop/Markdown/etc. services. FND-003 permits dependencies through a runtime object or concrete references. Reworking all route signatures solely to eliminate `self.app` now would be churn/YAGNI with high regression surface and no acceptance defect demonstrated.
- No new dependency/framework is justified. The existing stdlib HTTP server and explicit domain services satisfy the approved behavior-preservation goal; switching to Flask/FastAPI or adding a DI framework would be scope drift.
- The large `views.py`/files route surface is maintainability debt, but not evidence of duplicate state or parallel ownership introduced by this closure slice. Do not split by line count.
- Pi/native terminal code remains outside this team's product-edit ownership. The pre-existing terminal lifecycle failure should be assigned, not “fixed” here.

Ponytail disposition: **Lean enough for the accepted Foundation boundary; no speculative refactor requested.**

## Performance review

TEST Turn 2's controlled paired script is methodologically useful: both baseline and HEAD servers are resident concurrently on the same G6/Python, use identical data, alternate request order after warmup, sample process-tree CPU/RSS, and record exact response lengths.

Measured HTTP ratios are within the Spec 002 **proposed** review budget:
- list p95 ratio **1.017**, CPU **1.028**, peak tree RSS **0.874**;
- Preview p95 **0.831**, CPU **1.000**, RSS **0.870**;
- info p95 **1.017**, CPU **0.586**, RSS **0.854**.

These measurements do **not** justify universal “no regression” language; they are one paired run and the spec explicitly says thresholds need approval. Historical paired evidence points the same direction, so no measured Foundation HTTP performance defect is reproduced.

### R4-1 — F-T012 exact Markdown benchmark is mismatched

**Contract:** `specs/002-lantern-foundation/spec.md:27,68`; `tasks.md:8,23`. Baseline/perf gate calls for Markdown Preview **100 KiB** and before/after p95/CPU/RSS.

**Evidence:** `.plan/.../test_turn2_perf.json` records `markdown_bytes: 89403` (~87.3 KiB), not 102,400 bytes. The paired result is useful evidence but does not exactly prove the committed 100 KiB workload.

**Required TEST correction:** rerun the paired Preview workload with a deterministic **102,400-byte** Markdown fixture (or explain and formally revise the contract before calling it equivalent). Record p50/p95, CPU, process-tree RSS, body-length/parity and exact SHAs. No product code change.

### R4-2 — F-T012 terminal-replay benchmark remains NOT_MEASURED

**Contract:** same Spec 002 lines require the third workload: terminal replay, with `tasks.md` specifying **200 KiB**.

**Evidence:** TEST Turn 2 explicitly says terminal replay latency/CPU/RSS was not measured because the lifecycle E2E failure is pre-existing/out of scope. That reasoning correctly prevents a product fix, but it does **not** satisfy the read-only benchmark requirement. Foundation changed composition/entrypoint/process ownership even though `lantern/terminal.py` itself changed only an error-message string and `lantern/ws.py` did not change.

**Required TEST correction:** measure an isolated deterministic **200 KiB terminal replay** on baseline and HEAD without editing terminal/PTY/WS implementation. Prefer existing fake-PTY/replay APIs if they can measure the governed replay path comparably; if the acceptance contract specifically requires browser/native PTY replay, use disposable ports/processes and report any comparable-path blocker. Capture p50/p95, CPU and process-tree RSS. A pre-existing lifecycle failure does not authorize marking replay performance PASS without numbers.

## F-T011 / Linux / terminal disposition

- Windows HTTP/oracle/two-instance/WS/Markdown/Crop/launcher measured scopes have substantive independent coverage; fresh architecture/oracle tests above pass.
- The known terminal lifecycle E2E remains a **real baseline failure, not a demonstrated 002 regression**. Do not route DEV in this team for it.
- Linux smoke remains **INCOMPLETE**. REVIEW independently found Debian WSL has Python 3.13.5 and `uv 0.12.12`, and the repo is mounted, but the project dependencies are not already installed. PLAN Turn 3 explicitly limited Linux execution to an already-prepared supported isolated environment and prohibited global installs/WSL mutation. Do not silently provision or convert this into PASS. PLAN/owner must later disposition this gate or authorize a disposable Linux dependency environment.
- Manual/live acceptance is INCOMPLETE; live :9999 must remain untouched.

## Tests actually prove / do not prove

They prove current module importability, single entrypoint, per-instance runtime separation, frozen HTTP behavior in focused coverage, disposable Windows Edge/launcher behavior reported by TEST, and no measured HTTP p95/RSS regression in the paired workloads actually run.

They do **not** prove Linux parity, manual product acceptance, terminal lifecycle correctness, terminal replay performance, exact 100 KiB Preview performance, or a signed performance threshold. Missing evidence remains INCOMPLETE/NOT_MEASURED.

## Preservation / 003 dependency

No edits to `.md` source truth, `md_temp`, CAS, mapping, Milkdown, Crop, Pi/terminal runtime, CDPA, or live 9999 occurred. Source typing lag remains the pre-002 full-backdrop-DOM baseline defect and belongs to 003. Non-destructive 003 Phase-0 characterization remains lawful, but production 003 should not be described as fully Foundation-released until remaining gates are dispositioned.

## Next TEST — narrowly bounded

1. Re-run the paired Preview benchmark at **exactly 100 KiB** with the same baseline/HEAD controls.
2. Add the **200 KiB terminal replay** paired benchmark, read-only and without terminal implementation changes.

Then route REVIEW if both are comparable/measured; route PLAN if terminal replay cannot be made comparable under the ownership/environment boundary. Do not rerun unrelated suites merely to increase counts. Linux/manual/owner approval remains separately incomplete.

**Required route: TEST.**

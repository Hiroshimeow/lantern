# REVIEW Turn 6 — Foundation 002 FJP acceptance disposition

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 6 / 2026-10-18 JST  
**Workspace owner:** G6 `E:\git-project\lantern`, branch `main`, HEAD `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-test_turn4_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE PLAN.** The missing primary FJP acceptance slice from REVIEW Turn 5 is now independently supported. No new 002-owned correctness/performance/module-ownership defect is reproduced. F-T011/F-T012 measured Windows/FJP scope is acceptable for progression. Linux smoke, manual/live owner acceptance and formal budget sign-off remain explicit **INCOMPLETE** gates; this REVIEW does not convert those into PASS and does not declare the whole Foundation/release DONE.

## Independent review work performed

Loaded `ponytail-review` and `verification-before-completion`. Re-read TEST Turn 4, relevant Spec 002 acceptance lines, FJP performance JSON, current G6 repository state, and preserved scope rules.

### G6 repository truth

- G6 branch `main`, HEAD `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- Tracked/staged tree clean; only preserved unrelated `?? .pi/subagents.json`.
- Current HEAD differs from runtime-equivalent `b2ffd886795840f0db570b8c07a913b406e68e80` only in Spec-001 docs/tests, so Foundation product runtime being accepted on FJP at `b2ffd88` is equivalent to current HEAD for 002.

### FJP clean detached review environment

REVIEW independently created a detached clean FJP worktree:
`C:\Users\DuongNH66\Desktop\git\lantern-review-turn6` at exact `b2ffd886795840f0db570b8c07a913b406e68e80`.

The dirty FJP main checkout at `fb06c40758f406feb70bbb26ccd3cecb6476dacc` was not reset/stashed/cleaned/edited. After verification, the detached review worktree was force-removed and FJP main was rechecked: its pre-existing modified/untracked WIP shape remained intact. No live :9999/:10099 service, Pi/native-terminal implementation or CDPA state was touched.

## Fresh independent FJP Edge verification

### Terminal lifecycle

Command from clean detached `b2ffd88` worktree:
`LANTERN_E2E=1 uv run --locked --with playwright --with pytest python -m pytest -q tests/test_terminal_e2e.py`

Fresh result:
- **1 passed**
- **13.15 s**
- **exit 0**

This independently confirms the exact terminal lifecycle case that is flaky/failing on G6 passes on the primary FJP acceptance environment. It does not erase the G6 pre-existing failure; it establishes no FJP Foundation regression.

### Remaining selected F-T011 Edge/WS/Markdown/Crop/launcher slice

Command:
`LANTERN_E2E=1 uv run --locked --with playwright --with pytest python -m pytest -q tests/test_lan_multi_e2e.py tests/test_crop_shared_e2e.py tests/test_live_markdown_e2e.py tests/test_run_launcher.py`

Fresh result:
- **22 passed**
- **74.91 s**
- **exit 0**

Combined with the terminal rerun above, REVIEW independently reproduced **23/23 passed** for the exact selected FJP real-Edge Foundation slice reported by TEST Turn 4.

## FJP performance evidence review

Reviewed `.plan/lantern-markdown-main-20261018/test_turn4_fjp_perf.json` directly.

### 1k listing

Baseline -> runtime-equivalent head:
- p95: **1131.9954 -> 1255.764 ms**, ratio **1.1093**
- CPU ratio **1.0156**
- RSS ratio **0.8253**
- response length parity true

No >20% p95 or >25% RSS degradation under the proposed review budget.

### Exact 100 KiB Markdown Preview

Fixture: **102,400 bytes**.
- p95: **326.0383 -> 317.702 ms**, ratio **0.9744**
- CPU ratio **1.0293**
- RSS ratio **0.8026**
- body-length parity true

No FJP Preview degradation reproduced.

### Exact 200 KiB terminal replay

Payload: **204,800 bytes**.
- p95: **2.47855 -> 1.48710 ms**, ratio **0.6000**
- CPU ratio **0.6849**
- RSS ratio **1.0028**
- retained payload parity: 204,800 bytes
- framed payload parity: 205,106 bytes

Replay path is within proposed Foundation budget. The fake PTY is appropriate for timing replay/serialization without crossing native spawn ownership; native terminal lifecycle was separately exercised with real Edge above.

## F-T011 / F-T012 / F-T013 disposition

### F-T011

**Accepted for measured FJP Windows/Edge scope.**
- Real FJP Edge selected suite independently rerun: 23/23 pass.
- No new unowned JS/browser failure reproduced.
- Dirty FJP main and live service remained untouched.

Linux remains **INCOMPLETE with evidenced environment blockers** from prior TEST/REVIEW:
- Ubuntu WSL Python 3.10 < project minimum >=3.12.
- Debian has supported Python but existing environment lacks project dependencies.
- No global install/WSL mutation was authorized.

The spec explicitly permits Linux smoke PASS **or evidenced blocker before merge**; that blocker is documented. Therefore Linux incompleteness is not a new implementation defect requiring DEV.

### F-T012

**Technically accepted for measured baseline/head workloads.**

Both G6 and now FJP controlled measurements exist. FJP primary-environment data is within the proposed <=20% p95 / <=25% RSS budget for listing, exact 100 KiB Preview and exact 200 KiB replay, with CPU and parity data recorded.

Formal owner approval of the proposed budget remains **INCOMPLETE**; REVIEW does not impersonate owner sign-off. The evidence is sufficient for PLAN to decide dependency progression without further benchmark repetition.

### F-T013

This REVIEW provides the required independent architecture/performance disposition for current Foundation scope:
- single canonical entrypoint and per-instance lifecycle already reviewed in Turn 4;
- module owners are acceptable and no speculative DI/framework split is warranted;
- current selected FJP acceptance and performance are now independently corroborated;
- no actionable Foundation-owned regression is reproduced.

Manual/live owner acceptance and live deployment remain separate and **INCOMPLETE**.

## Over-engineering / scope / ownership / UX / scalability

- **YAGNI:** no additional refactor requested. Splitting route mixins or adding a DI/web framework would be churn without acceptance value.
- **Module ownership:** composition/lifecycle remains centralized in `Application`; HTTP remains adapter-level; Markdown/file/media/crop/terminal owners stay separated.
- **Scope drift:** none in TEST/REVIEW FJP verification. No product code changes were made.
- **Maintainability:** detached-worktree/uv-locked verification is repeatable and does not create a second product path.
- **Scalability/performance:** measured 1k list/100KiB Preview/200KiB replay show no primary-environment blocker; they are not universal capacity proofs.
- **UX:** selected browser flows pass, but manual/live end-user acceptance is still separate.
- **Mature upstream:** no alternate framework/editor/runtime is justified by Foundation evidence.

Ponytail disposition: **Lean already for this Foundation closure.**

## Preservation boundaries confirmed

Preserved:
- G6 `.pi/subagents.json`;
- dirty FJP main WIP;
- unrelated FJP worktrees;
- Pi/native terminal source ownership;
- live :9999/:10099;
- Markdown `.md` source-of-truth, `md_temp`, CAS, fidelity/mapping semantics;
- Source lag classification as pre-existing 003 full-backdrop-DOM defect.

## Remaining gates outside this accepted Foundation slice

Still **INCOMPLETE/NOT DONE**:
- Linux smoke execution itself (blocker documented);
- manual/live owner acceptance;
- explicit owner performance-budget sign-off;
- 001 M-A12 personal security-owner acknowledgement;
- remaining 001 export/performance gates;
- 003 MD-T000–T018 proof/implementation/UX/crop/final acceptance.

No new Foundation implementation defect requires DEV or TEST. The next dependency decision belongs to PLAN: mark 002 technical FJP closure evidence accepted with the above explicit residual gates, then continue dependency-ordered owned work (001 remaining acceptance and/or 003 proof-first tasks) without claiming full release.

**Required route: PLAN.**

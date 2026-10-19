# REVIEW Turn 3 — independent CSP evidence gate

**Team:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4. **Role:** REVIEW turn 3. **Date:** 2026-10-18 JST.  
**Workspace:** G6 `E:\git-project\lantern`, `main`, HEAD `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn3_cdpa-idem-382a709ae8895eae9ec134d4.md`.

## Decision: accept the bounded test-only repair; route PLAN

REVIEW Turn 2 identified four concrete ways the CSP acceptance harness could report false positives. Commit `ffe3dec` modifies **only** `tests/test_preview_csp_e2e.py` (+228/-33), resolving these targeted issues without product behavior changes. No remaining reproducible implementation defect in this slice warrants routing DEV. The security release and other spec gates are expressly **not** accepted by this verdict.

### Scope, contract and code audit

Read `AGENTS.md`, incoming DEV Turn 3, earlier PLAN Turn 2/REVIEW Turns 1–2, Spec 001 CSP/M-A5/M-A12 contract, relevant Specs 002/003 docs reviewed in preceding turn, complete updated 427-line E2E and `plugin.py` actual CSP composition. Loaded `ponytail-review` and `verification-before-completion` on G6. Independently inspected HEAD/stat/status and the browser tests; did not rely on DEV's green claims.

- **R2-1 FIX verified:** `tests/test_preview_csp_e2e.py:242-246` confirms `/probe-evil.js` responds 200, JavaScript MIME and expected body before nonce-less injection; `:336-349` checks it remains unexecuted and requires a correlated enforced `script-src[-elem]` violation for its exact URL. A dead 404 URL alone can no longer pass.
- **R2-2 FIX verified:** `:90-130` captures securitypolicyviolation directive/blocked URI/disposition and matches the complete expected set. `:258-261,311-334` assert zero baseline violations and console errors before deliberate probes; `:271-294,346-370` match intentional blocks and reject unexpected non-CSP console errors. A broad `any CSP error` predicate no longer hides unrelated errors.
- **R2-3 FIX verified within browser event scope:** `:236-240,257,310,373-380` log all Playwright-observed page/context requests and WebSocket creation, then reject off-origin URLs; `:132-143` checks the actual disposable origin. `:280-294,352-366` require explicit connect-src violations for external fetch/WS, distinguishing CSP denial from DNS failure. Cross-origin Worker constructor must throw `SecurityError` `:283-286,355-358`, correctly distinguished from a dispatched CSP event.
- **R2-4 FIX verified:** `:158-185,319-332` requires real Worker message result, matching id 991, `ok === true`, positive counts and a nonempty page range. This is functional proof rather than mere constructor completion.

### Fresh reviewer verification, G6

- `LANTERN_E2E=1; C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_preview_csp_e2e`: **2 tests, OK, 8.202 s, process exit 0** on real Edge and disposable loopback server. Opt-in variable removed from reviewer shell after run.
- `C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py`: **26 passed, 5 subtests, 1.39 s, exit 0**.
- `C:\Users\admin\miniconda3\python.exe -m py_compile tests/test_preview_csp_e2e.py tests/test_plugin.py`: **exit 0**.
- `git diff HEAD~1 HEAD --check`: **exit 0**. `git status --short -uall`: solely preexisting `?? .pi/subagents.json`; no tracked/staged changes. Commit `ffe3dec` is atop `3bfaa2e` atop previous baseline `b2ffd88`. 
- DEV reported full native **208 passed / 110 skipped / 47 subtests**; REVIEW did **not independently rerun** the entire suite. Treat full-suite result as inherited.

### Architecture, YAGNI, security, UX, performance, preservation

New code is restricted to the existing opt-in disposable Edge test. The separate event-capture and origin allowlist helpers serve different security invariants, do not duplicate runtime ownership, and reuse Python stdlib plus installed Playwright. Approximately 195 net test lines adds some duplication in WebSocket settle functions, but pruning them without reducing diagnostic precision is not necessary for the current acceptance gate; no additional dependency, configuration layer, or framework is created. Native CSP violations/Worker events and ordinary browser PDF embedding are mature platform primitives. No source-of-truth `.md`, `md_temp`, CAS, Markdown modes, Mermaid runtime, Pi/terminal or service endpoints changed. No 9999 restart, CDPA operation, reset/stash/clean or unrelated-file mutation. Performance/large-document UX untouched and **NOT_MEASURED** in this slice. Existing Source backlog at 5,500 lines remains a proven pre-002 full-backdrop-DOM baseline defect, not a foundation regression.

**Limits:** This verifies tested renderer CSP/profile behaviors and negative probe efficacy, not blanket internet/LAN safety. The allowed data/blob category in request accounting is not evidence of universal file provenance security. Browser PDF request + MIME does not prove legibility. Raw uploaded same-origin HTML/SVG and iframe containment remain risk `LANTERN-SEC-001`. Renewed security owner acceptance for typed Markdown connect/Worker exception is still **INCOMPLETE**; M-A12 not PASS. 001 M-A9 PDF visual, M-A11 nine-context FJP Chromium timing, broader full acceptance; 002 performance/Linux/manual/architecture closure; 003 MD-T000/T001/T002/T003 Source/fidelity/crop/UX remain outstanding.

### Routing and next action

**PLAN:** Record this **bounded test-repair slice accepted**, choose the next dependency-ordered actionable 001/002/003 task (DEV at most two subtasks per slice, then REVIEW/TEST), and avoid claiming all 001 or release gates complete. Continue autonomous legally actionable work even while security-owner risk disposition remains pending. `DONE` is PLAN-only.

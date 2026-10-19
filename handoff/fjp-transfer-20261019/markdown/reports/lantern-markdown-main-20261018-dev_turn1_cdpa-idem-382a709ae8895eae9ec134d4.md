# DEV Turn 1 — Spec 001 CSP contract conflict; product change withheld

Team: lantern-markdown-main-20261018 | task: cdpa-idem-382a709ae8895eae9ec134d4 | 2026-10-18  
Workspace: G6 `E:\git-project\lantern`, `main`, initial HEAD `b2ffd886795840f0db570b8c07a913b406e68e80`.

## Contract inspected
Read `AGENTS.md`, PLAN Turn 1, TEST Turn 1, 001 spec/plan/tasks (Markdown security T3–T7), 002 spec/plan/tasks/research/analysis/decisions/verification/upstream and 003 spec/plan/tasks/research/source-performance audit. Inspected `plugin.py::render_preview_page`, `tests/test_plugin.py`, `lantern/http/routes/plugin.py`, `static/chatbot.js`, `static/markdown_visual_shell.js` and `static/markdown_paged_editor.js`.

**Exact conflict**: 001 spec and T3/T4 mandate `connect-src 'none'` on **every preview kind**. The current interactive Markdown page is **the same document** as Preview/Edit/Source, depends on same-origin `fetch('/api/work...')` (live source/CAS and md_temp), `fetch('/api/info')`, chatbot `ws://.../ws?v=2`, and paged-editor Worker. In `plugin.py:1273`, Markdown intentionally gets `connect-src 'self'; worker-src 'self'` but non-Markdown gets `connect-src 'none'`. `tests/test_plugin.py:491–517` already relaxes the exact CSP assertion to accept self for Markdown, contradicting Spec 001. This is not an implementation oversight safely cured by changing one string; forcing exact 001 CSP destroys required 003 contracts.

## Fresh independent browser reproduction
Probe file: `.plan/lantern-markdown-main-20261018/dev_turn1_csp_contract_probe.py` (ignored diagnostic, **not** product implementation). Output JSON and stdout: `dev_turn1_csp_contract_probe.json`, `dev_turn1_csp_contract_probe.log`.

Execution on G6:
```powershell
& 'C:\Users\admin\miniconda3\python.exe' '.plan\lantern-markdown-main-20261018\dev_turn1_csp_contract_probe.py'
```
Final run: **exit 0**; Edge 155.0.4283.45, Python 3.13.9; separate disposable Lantern process at random loopback port 50397; temp root and config; terminates process. Earlier diagnostic iterations: one timed out because the browser route fixture was checking an HTML-escaped policy against raw quotes; one exit 1 wrongly assumed blocked Worker constructor throws synchronously (browser emitted CSP console violation asynchronously). Diagnostic corrected; neither was a product test regression.

Browser and actual HTML meta CSP:
- Read-only `.txt`: `connect-src 'none'` → WebSocket blocked; `fetch` blocked.
- Interactive `.md`: `connect-src 'self'; worker-src 'self'` → WebSocket **opened**, fetch **ok**, Worker constructed.
- Same `.md` served under probe-only forced exact `connect-src 'none'` (no product file change): WebSocket blocked; `fetch('/api/work')` and `fetch('/api/info')` emit actual CSP violations and are blocked; Worker creation emits a CSP violation due to removal of `worker-src` (its constructor can return before asynchronous failure). Source button remains in DOM but required backing data is unavailable.
- For each actual response, parsed **HTML meta** CSP and matched its token against **all script nonces**, not the absent response header; second server render has a fresh different nonce. This corrects the TEST Turn 1 invalid HTTP-header nonce check.

## Decision required from PLAN (material product/spec conflict)
Choose an **explicit reviewed CSP/realm contract** before DEV alters `plugin.py` or its tests. Either (A) approve scoped exception: interactive `.md` Preview/Edit/Source is an application editor origin with required same-origin fetch/WS/Worker, while read-only preview kinds retain `connect-src 'none'`; update 001 requirements and security-owner residual-risk disposition accordingly; or (B) require strict 001 CSP for genuinely separate read-only Markdown Preview, with a new isolation/navigation design preserving editable modes, source bytes/CAS/md_temp, Mermaid, and the prior owner-approved security risk. (B) is a substantial cross-spec UI/architecture decision, **not** authorized in this DEV slice. Neither is selected implicitly.

Do not blanket-switch Markdown to `connect-src 'none'`, disable chatbot, introduce speculative iframe sandbox/security subsystem, or modify Pi/native terminal ownership. The existing security-owner acceptance of a separate containment risk does not explicitly approve broadening this discrepancy without review.

## Files / changes / checks / risks
- Product files modified: **none**. Commit: **none** — no accepted implementation slice exists; committing arbitrary speculative code would violate PLAN/PRESERVE.
- Added only ignored `.plan` diagnostic script/log/JSON and this required report.
- Verification actually run: disposable Edge CSP/meta/WebSocket/fetch/Worker probe **PASS for observed contract conflict**, not PASS for 001 acceptance. Prior TEST 208-pass Python suite is **referenced, not rerun by DEV**; full E2E/benchmarks/architecture sign-off remain INCOMPLETE/NOT_MEASURED.
- `git status --short` before/after: only `?? .pi/`, unchanged. `git diff --check` (tracked tree) exit 0 before report; no reset, stash, clean, live :9999, CDPA, deployment, or cross-owner edits.
- Residual risks: M-A5 spec conflict still open; 002 structural/manual and CPU/RSS/Linux gates not accepted; the terminal E2E failure remains out of scope; 003 dependent implementation cannot legitimately proceed while this product/security design is unresolved.

**ROUTE: PLAN**, because the current TEST→DEV contract contains mutually incompatible 001 and 003 invariants. PLAN should issue a precise disposition/change-control boundary, then route a max-two-item TDD implementation slice if required, or independent REVIEW of the documented exception. No DONE or PASS claim on unresolved 001 M-A5.

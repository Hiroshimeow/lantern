# DEV Turn 3 — harden CSP Edge evidence against false positives

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed
Executed exactly the two REVIEW Turn 2 subtasks and stopped:
1. Strengthened nonce-less script proof + exact CSP violation classification, including violation-free application baseline before negative probes.
2. Replaced hostname-specific monitoring with all-request/all-WebSocket origin accounting and strengthened Worker reply correlation/payload assertions.

No production runtime source changed. No Spec docs, 002/003 implementation, Pi/native terminal, CDPA, or live `:9999` was touched.

## Changed tracked file
- `tests/test_preview_csp_e2e.py` only.

### R2-1 / R2-2 corrections
- Added `securitypolicyviolation` capture from document initialization.
- Each expected negative probe is matched by exact `effectiveDirective`, blocked URI fragment, and `disposition == "enforce"`; exact violation count rejects unrelated violations.
- Read-only and Markdown pages assert **zero CSP violations and zero console errors before negative probes**, proving app boot / allowed Markdown Worker path is clean before deliberate denials.
- Negative-probe console errors must all identify Content Security Policy; unrelated console errors now fail the test rather than being hidden by one expected CSP message.
- Before injecting the nonce-less script, the harness directly fetches `/probe-evil.js` outside page CSP and asserts HTTP 200, JavaScript content type, and expected payload, so a 404/unserved fixture cannot satisfy the denial test.
- The injected same-origin script remains nonce-less, execution must stay false, and the exact script URL must appear in a `script-src[-elem]` policy violation.

### R2-3 correction
- Context now records **all HTTP(S) requests**, not only `example.invalid`.
- Pages record every WebSocket actually created.
- At the end, every observed request/WebSocket must belong to the disposable Lantern origin (or permitted data/blob category); any non-app origin is a failure.
- Cross-origin fetch and WebSocket probes additionally require explicit `connect-src` violations. This distinguishes CSP denial from DNS/network failure.
- Cross-origin Worker is rejected synchronously with `SecurityError` by the browser's Worker same-origin rule before a CSP violation/network request occurs; the test asserts that exact behavior rather than fabricating a CSP event, and the all-origin network ledger confirms no escape.

### R2-4 correction
The allowed same-origin segmentation Worker must now return:
- `state == "ready"`
- exact message `id == 991`
- `ok is True`
- a real result object with positive `chars`, positive `blocks`, non-empty `pages`, first page starting at 0 and ending >0.

This proves a correlated functional segmentation reply, not merely Worker construction or a generic success flag.

## Red/green characterization during repair
The first strengthened E2E run failed because the newly added init script was supplied as an uninvoked function expression, leaving the capture variable undefined. That test-harness defect was fixed by invoking the initializer.

The next run failed because Chromium emitted two external CSP violations (fetch + WebSocket), not three: a cross-origin Worker constructor throws `SecurityError` from the Worker same-origin rule before a CSP event. The oracle was corrected to assert that browser rule separately while retaining all-origin network escape checks. No production change was made to force a preferred test shape.

Final Edge rerun after all changes is green.

## Verification actually run
1. Real Edge disposable CSP E2E:
   ```
   $env:LANTERN_E2E='1'
   C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_preview_csp_e2e
   ```
   Final result: **2 tests OK, 9.329 s, exit 0**.

2. Focused plugin suite:
   ```
   C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py
   ```
   Result: **26 passed, 5 subtests passed, 0.91 s, exit 0**.

3. Full native suite:
   ```
   C:\Users\admin\miniconda3\python.exe -m pytest -q
   ```
   Result: **208 passed, 110 skipped, 47 subtests passed in 74.82 s, exit 0**.
   Evidence: `.plan/lantern-markdown-main-20261018/dev_turn3_full_pytest.log`.
   The two opt-in Edge tests remain skipped in ordinary full pytest and were executed separately above.

4. Syntax / diff hygiene:
   - `python -m py_compile tests/test_preview_csp_e2e.py` → exit 0.
   - `git diff --check` → exit 0.
   - staged `git diff --cached --check` → exit 0.

## Commit / repository state
Committed the bounded test-only repair:
- **`ffe3decb4469cff36bb98f8afd6ba8e9e89af089`**
- message: `test(markdown): harden preview CSP evidence`

Post-commit `git status --short`: only `?? .pi/`; unrelated `.pi/subagents.json` remains untouched. No reset/stash/clean/push/rebase/restart/deployment.

## Remaining incomplete gates
- Renewed owner/security acknowledgement for typed Markdown same-origin connect/Worker capability is still **INCOMPLETE**; this test repair does not grant release sign-off.
- `LANTERN-SEC-001` raw uploaded HTML/SVG/iframe containment remains open.
- 001 M-A9 PDF visual legibility/arrowheads/clipping remains INCOMPLETE.
- 001 M-A11 nine fresh FJP Chromium timing contexts remain NOT_MEASURED.
- 002 architecture/manual/Linux/CPU-RSS closure remains INCOMPLETE.
- 003 proof-first Source/mapping/crop work remains unstarted in this turn.
- Terminal-owned E2E failure remains outside this DEV ownership.

## Next route
**REVIEW**. The actionable false-positive paths from REVIEW Turn 2 were repaired in one committed test-only slice with fresh Edge/full-suite evidence. Independent REVIEW should now verify the negative-security oracle is neither too weak nor overfitted before the team advances to subsequent dependency-ordered 001/002/003 work.

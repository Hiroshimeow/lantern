# DEV Turn 2 — typed preview CSP contract + regression evidence

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed
Executed exactly the two REVIEW-approved items and stopped:
1. Contract/docs: replaced the obsolete universal preview CSP with explicit server-classified profiles in Spec 001.
2. Regression evidence: tightened static CSP assertions and added one disposable Edge CSP E2E module.

No product runtime change was required. `plugin.py` was inspected but not modified because the existing server-classified behavior already matches the reviewed Option A contract. No Pi/native terminal, CDPA, `:9999`, Foundation 002 runtime, or 003 implementation files were touched.

## Changed tracked files
- `specs/001-terminal-ime-markdown-export/spec.md`
  - Defines strict generic read-only, interactive Markdown, and native PDF iframe CSP profiles.
  - Rewrites M-A5 to distinguish blocked read-only connectivity from allowed same-origin Markdown work/CAS/WS/Worker.
  - Keeps renewed owner/security acknowledgement explicitly **pending**; M-A12 remains INCOMPLETE.
  - Records `CSP-DEC-20261018-01` and keeps `LANTERN-SEC-001` open.
- `specs/001-terminal-ime-markdown-export/plan.md`
  - Replaces universal CSP design with the reviewed typed-profile contract; no new CSP framework/realm.
- `specs/001-terminal-ime-markdown-export/tasks.md`
  - Requires exact per-kind static/browser assertions, actual functional Worker readiness, native PDF frame load, and renewed owner/security sign-off.
- `tests/test_plugin.py`
  - Replaces permissive `connect-src '(none|self)'` + UI-text inference with exact per-kind policies.
  - Covers Markdown, text, CSV, native PDF and PDF text.
  - Verifies all app script nonces and nonce rotation across responses.
- `tests/test_preview_csp_e2e.py` (new)
  - Reuses the existing disposable-main.py + Playwright/Edge style.
  - Strict read-only: same-origin fetch/WS/Worker blocked.
  - Interactive Markdown: same-origin fetch succeeds, WS opens, segmentation Worker returns a real `postMessage` result.
  - Cross-origin fetch/WS/Worker attempts are blocked and no external request escapes.
  - Same-origin uploaded script injected without nonce does not execute.
  - Markdown response nonce rotates.
  - Native PDF policy is `connect-src 'none'; frame-src 'self'` and the raw PDF iframe actually requests `application/pdf`.

## Verification actually run
1. Focused unit:
   ```
   C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py
   ```
   Result: **26 passed, 5 subtests passed, 1.51s, exit 0**.

2. New real Edge E2E on disposable random loopback server:
   ```
   $env:LANTERN_E2E='1'
   C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_preview_csp_e2e
   ```
   Result: **2 tests OK, 8.514s, exit 0**.
   This proves the tested CSP browser behaviors above; it is not owner/security sign-off and not complete M-A5/M-A12 release acceptance.

3. Full native suite:
   ```
   C:\Users\admin\miniconda3\python.exe -m pytest -q
   ```
   Result: **208 passed, 110 skipped, 47 subtests passed in 85.01s, exit 0**.
   Evidence: `.plan/lantern-markdown-main-20261018/dev_turn2_full_pytest.log`.
   The skip count increased by the two opt-in tests in the new E2E module; their real Edge run was executed separately above.

4. Syntax / diff hygiene:
   - `python -m py_compile tests/test_preview_csp_e2e.py tests/test_plugin.py` → exit 0.
   - `git diff --check` → exit 0 after removing one Markdown trailing-space issue.
   - staged `git diff --cached --check` → exit 0.
   - no remaining old universal phrases found by targeted `rg`.

## Commit / repository state
Committed the scoped slice:
- **`3bfaa2ec606b2e9d9a5c9667e70ed85df59f8858`**
- message: `test(markdown): define typed preview CSP profiles`

Post-commit `git status --short`: only `?? .pi/`; unrelated `.pi/subagents.json` remains untouched. No reset/stash/clean/push/rebase/restart/deployment was performed.

## TDD / characterization note
This turn changes the acceptance contract and regression tests, not product behavior. The new exact unit and Edge tests pass against the already-existing runtime by design; there was no production change to drive RED→GREEN. The previous TEST/DEV counterfactual already established that forcing the old universal `connect-src 'none'` onto Markdown breaks required editor functionality. Do not misreport these characterization tests as a product bugfix RED→GREEN cycle.

## Remaining risks / incomplete evidence
- **Owner/security acknowledgement is still pending.** DEV/REVIEW cannot impersonate it; M-A12 remains INCOMPLETE.
- The broader same-origin raw uploaded HTML/SVG containment remains tracked by `LANTERN-SEC-001`.
- M-A9 PDF visual legibility/arrowheads/clipping remains INCOMPLETE.
- M-A11 nine fresh FJP Chromium timing contexts remain NOT_MEASURED.
- Foundation 002 architecture/manual/Linux/CPU-RSS closure remains INCOMPLETE.
- 003 proof-first work (MD-T000/T001/T002/T003 etc.) has not started in this turn.
- Existing terminal-owned Edge failure remains out of this DEV ownership and is not declared resolved.

## Next route
**REVIEW**. The bounded doc/test slice is committed and has fresh unit/full-suite/Edge evidence, but needs independent review of correctness, security-contract wording, YAGNI/scope, test sufficiency and whether the E2E truly proves the revised M-A5 acceptance before the team advances to later 001/002/003 work.

# REVIEW Turn 9 — stabilized Phase-0 characterization acceptance

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 9 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn7_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE PLAN.** REVIEW Turn 8's two concrete harness defects are fixed. Fresh independent runs of both opt-in characterization suites now complete successfully with revision/file/request quiescence, while preserving the expected product-red classifications. No remaining actionable defect in this harness-only slice warrants DEV. The next dependency decision belongs to PLAN: accept MD-T000/MD-T001 characterization evidence and advance to MD-T002 mapping proof plus MD-T003 mature Source-editor POC in a bounded next slice.

This does **not** mean Spec 003 is complete. It means the Phase-0 evidence is now sufficiently stable to drive design.

## Independent repository and diff review

Loaded `ponytail-review` and `verification-before-completion`. Inspected HEAD, full diff, new settlement helper, both characterization modules and current git state.

Repository facts:
- HEAD `25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`.
- Commit changes only:
  - `tests/_markdown_characterization_settle.py`
  - `tests/test_source_typing_perf_e2e.py`
  - `tests/test_markdown_roundtrip_corpus.py`
- `git diff HEAD~1 HEAD --check`: exit 0.
- Final tree after REVIEW runs: only preserved `?? .pi/subagents.json`.
- No product runtime source, Pi/native terminal, Crop, CDPA or live :9999/:10099 operation occurred.

## R8-1 fix verification — MD-T000 stable settlement

The new helper no longer treats one matching poll as terminal. It requires a stable signature across a 600 ms quiet window and correlates:
- browser editor == expected final content;
- `lastSaved` == expected content;
- browser `currentVersion` == real-file SHA;
- browser `workHash` == real-file SHA;
- accepted/saved revision remains the original `md_temp` version;
- no saving/loading/conflict;
- real-file SHA unchanged;
- write POST count unchanged;
- browser revision/version/hash unchanged.

After the quiet window it performs a final `/api/work` fetch, browser re-sample, file re-read and POST recount before returning one coherent final state.

Fresh REVIEW command:

`LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_source_typing_perf_e2e`

Result:
- **1 test OK**
- **45.121 s**
- exit 0

Fresh independent measurements:
- 900 lines: p95 **17.078 ms**, full backdrop rebuild true, settled 691 ms.
- 5,500 lines: p95 **138.682 ms**, input→paint p95 **46.9 ms**, **20 Long Tasks**, **99,018 added + 99,018 removed backdrop nodes**, max add/remove **5,501**, full backdrop rebuild true, 0 navigation, stable 707 ms.
- ~500 KB: p95 **19.163 ms**, full backdrop rebuild true, stable 702 ms.
- ~5 MB: p95 **939.006 ms**, input→paint p95 **109.2 ms**, **50 Long Tasks**, full backdrop rebuild true, stable 630 ms.
- CJK synthetic composition: p95 **13.401 ms**, stable 711 ms.
- 30-col: p95 **17.532 ms**, stable 697 ms.

Crucially, the ~5 MB case now returns:
- `write_settled=true`;
- final `current_real_version == real_after.sha256`;
- unchanged accepted `md_temp`;
- later CJK/table workloads run after it without exposing a late write.

The exact defect from REVIEW Turn 8 is therefore independently closed.

## R8-2 fix verification — MD-T001 stable settlement

Fresh REVIEW command:

`LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_markdown_roundtrip_corpus`

Result:
- **2 tests OK**
- **24.018 s**
- exit 0

All edit cases now require the same stable browser/server/file correlation rather than merely “workHash exists + sleep”.

Fresh product-level classifications remain:

### Source
- BOM+CRLF: PASS.
- constructs: PASS.
- duplicates: PASS.
- no-final-newline: PASS.
- 30-column table: PASS.
- mixed EOL/no-final-newline: **FAIL**
  - expected 106 bytes;
  - actual 102 bytes;
  - prefix changed;
  - suffix unchanged;
  - first unexpected diff offset 11;
  - stable quiet **702.107 ms**.

### Visual
- constructs one-block edit after explicit conversion approval: **FAIL**
  - expected 655 bytes;
  - actual 690 bytes;
  - prefix and suffix changed;
  - stable quiet **697.741 ms**.
- 30-column table one-block edit: **FAIL**
  - expected 861 bytes;
  - actual 1,521 bytes;
  - prefix changed;
  - stable quiet **701.401 ms**.

Every reproduced edit has:
- `write_settled=true`;
- final real-file SHA == server currentVersion;
- accepted `md_temp` revision/hash unchanged.

Thus the fidelity failures are no longer reasonably attributable to the prior weak settlement oracle.

## Review of helper design / YAGNI

The helper is test-only and shared by the two exact characterization suites that need the same invariant. This is justified reuse rather than a product abstraction.

One minor complexity observation: at ~182 lines the helper is verbose, but the checks are individually tied to false-positive pathways already reproduced. Collapsing the browser/server/file correlation into a shorter “sleep then hash” implementation would lose correctness. No cut is recommended in this slice.

**Ponytail:** Lean already for the required fail-closed evidence helper. Ship this test-only slice.

## Acceptance interpretation

### MD-T000

Accepted as a repeatable Phase-0 characterization harness.

It proves:
- current 5,500-line Source violates the fixed acceptance criterion;
- the violation is independently reproduced both by latency and by complete-backdrop regeneration;
- no main-document reload/navigation occurred;
- focus/caret ownership remains stable in these probes;
- real `.md` write-through and `md_temp` snapshot semantics are preserved;
- large-file behavior is expensive but remains **MEASURED**, not assigned an invented formal threshold before MD-T003.

The 5,500-line product acceptance remains **FAIL**, as intended. Green harness != green product.

### MD-T001

Accepted as a repeatable exact-byte characterization corpus.

It proves:
- Source can preserve bytes for several cases but fails mixed-EOL local-edit fidelity;
- Visual no-op does not persist;
- Visual serialization for complex/table edits changes bytes outside the intended edit even after explicit conversion review;
- `md_temp` remains unchanged until Accept/Save.

These are direct inputs to MD-T002/MD-T009 design.

## UI/UX / performance / scalability / ownership

- **UX:** Source full-backdrop rebuild remains a material user-facing lag mechanism; no page reload is observed.
- **Performance:** 5,500-line failure is robust enough to drive MD-T017. ~5 MB is clearly expensive, but no final threshold is yet authorized.
- **Scalability:** current backdrop approach scales with document line count and redraw frequency; evidence supports evaluating a virtualized mature editor.
- **Module ownership:** no product ownership changed. Source/Visual/CAS remain with their existing owners.
- **Mature upstream alternatives:** no CodeMirror choice has been prematurely encoded. MD-T003 should now test CM6 MergeView/unified or equivalent before architecture selection.
- **Maintainability:** raw-byte fixtures and machine-readable evidence are appropriate regression assets.
- **Scope drift:** none; no MD-T002/T003/Crop implementation was started.

## Remaining product-red evidence that must not be lost

1. Source 5,500-line p95 remains above <40 ms and full backdrop rebuild remains true.
2. Mixed-EOL Source edit mutates unrelated bytes.
3. Visual complex and wide-table local edits reserialize unrelated source.
4. Large 5 MB Source path is operationally expensive.
5. CJK evidence is synthetic composition coverage only, not full native Windows IME acceptance.

These are expected inputs to later work, not defects in this test-only commit.

## Remaining external/final gates

Unchanged and still incomplete:
- Spec 001 M-A11 controlled low-load independent FJP performance acceptance.
- Spec 001 M-A12 personal owner/security acknowledgement.
- Foundation 002 Linux/manual/owner budget residual gates.
- Spec 003 implementation/UX/Crop/final acceptance tasks.

No DONE claim.

## Next PLAN recommendation

Accept MD-T000 + MD-T001 as complete Phase-0 characterization tasks and schedule the next dependency-ordered slice, at most two coherent subtasks:

1. **MD-T002** — deterministic source-byte/span → mdast/ProseMirror mapping proof on duplicates, tables, fences and CJK; fail visibly when ambiguous/unmapped, never guess.
2. **MD-T003** — isolated mature CodeMirror 6 MergeView/unified POC against current environment: CRLF/BOM, CJK/IME, deletion widget/hunks, viewport behavior, 500 KB/5 MB, no formatting mutation; verify package/version before any package change.

Do not yet implement the full Source replacement, Visual write strategy, diff engine or Crop in the same slice.

**Required route: PLAN.**

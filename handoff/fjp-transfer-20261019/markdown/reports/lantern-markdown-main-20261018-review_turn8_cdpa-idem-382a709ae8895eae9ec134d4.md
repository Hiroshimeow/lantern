# REVIEW Turn 8 — Spec 003 Phase-0 characterization review

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 8 / 2026-10-18 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `247480b244c1023aac1ec654e34a208df3e89d81`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn6_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE DEV.** The Phase-0 corpus is useful and the product-level red findings are credible, but MD-T000 is **not yet a repeatable acceptance harness**: a fresh independent run failed on the ~5 MB case because a late real-file write occurred after the harness had already declared `write_settled=true`. The recorded `current_real_version` then no longer matched the actual file SHA.

This is a concrete, independently reproduced **test-harness settlement defect**, not a reason to edit product Source/Visual code. Fix the characterization oracle first; otherwise MD-T000 can emit internally contradictory JSON and can fail/pass depending on write timing.

## Repository / scope verification

- HEAD: `247480b244c1023aac1ec654e34a208df3e89d81`.
- Commit scope is proof-only: two test modules, six raw-byte fixtures, and one fixture-only `.gitattributes` rule.
- No production runtime source is changed by this commit.
- `git diff HEAD~1 HEAD --check`: exit 0.
- Current tree after REVIEW runs: only preserved `?? .pi/subagents.json`.
- No :9999/:10099, Pi/native terminal, CDPA, reset/stash/clean or unrelated worktree mutation.

Loaded `ponytail-review` and `verification-before-completion`.

## Independent fresh verification

### MD-T001 fidelity corpus

Fresh command:

`LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_markdown_roundtrip_corpus`

Result:
- **2 tests OK**
- **21.018 s**
- exit 0

Fresh product classifications reproduced:
- Source BOM+CRLF edit: byte-preserving PASS.
- Source constructs: byte-preserving PASS.
- Source duplicates: byte-preserving PASS.
- Source no-final-newline: PASS.
- Source wide table: PASS.
- Source mixed-EOL/no-final-newline: **FAIL**, unrelated prefix bytes changed; first unexpected byte offset 11.
- Visual constructs one-block edit after explicit format-review approval: **FAIL**, actual 690 bytes vs expected 655, prefix and suffix both changed.
- Visual 30-column table edit: **FAIL**, actual 1,521 bytes vs expected 861, prefix changed.
- In every reproduced case `md_temp` remained at the original accepted bytes/version without Accept/Ctrl+S.

These failures are useful design inputs for MD-T002/T009; they are not accidental test failures because the characterization intentionally records red product states while preserving harness success.

### MD-T000 Source performance

Fresh command:

`LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_source_typing_perf_e2e`

Result:
- **FAILED**
- one assertion failure after all six workload probes
- runtime ~47 s

Fresh 5,500-line evidence still reproduces the core product defect strongly:
- key-wall p95 **204.048 ms** in this run;
- input→next-paint p95 **41.9 ms**;
- **20 Long Tasks**;
- **93,517 backdrop nodes added and 93,517 removed**;
- max add/remove in one mutation record = **5,501 / 5,501**;
- `full_backdrop_rebuild=true`;
- 0 main-document navigations;
- focus preserved;
- real file write-through occurred;
- `md_temp` remained unchanged.

Thus the known Source full-backdrop defect is independently reproduced and does not depend on Foundation 002.

However, the harness itself failed on the ~5 MB workload:
- it recorded `write_settled=true`;
- returned `current_real_version = 83dba775...`;
- but the later `real_after.sha256 = f51d2ca2...`;
- final assertion at `tests/test_source_typing_perf_e2e.py:468` correctly caught the mismatch.

## Concrete findings

### R8-1 — MD-T000 settlement oracle can declare success before the write stream is quiescent

**Location:** `tests/test_source_typing_perf_e2e.py:286-313`.

Current logic:
1. polls `/api/work`;
2. sees one moment where server content equals textarea and `currentVersion` equals the real-file SHA;
3. immediately sets `settled_state` and exits;
4. computes `write_settled=true`;
5. then waits another 150 ms;
6. only afterward snapshots `real_after`.

On the independent ~5 MB run, another delayed write landed during/after that final wait. Therefore the JSON said `write_settled=true` while its own final version/file hashes disagreed.

**Violated contract:** MD-T000 must be repeatable and must accurately record real `.md`, revision, request counts and final state. A transient equality is not a stable terminal condition.

**Required correction:** wait for a **quiescent stable end state**, not a single matching poll. At minimum require:
- textarea final value == server work/saved content;
- server `currentVersion` == real-file SHA;
- no observed real-file SHA/currentVersion/request-count change across an explicit quiet window long enough to cover current 90/110/120 ms timers and outstanding POST completion;
- final snapshot and returned version/hash taken from the same stable sample.

Do not “fix” by adding a large arbitrary sleep. Prefer bounded repeated identical samples / request-quiescence. Preserve actual product timing and do not reduce workload.

### R8-2 — MD-T001 uses the same weak “workHash exists + 300 ms” settlement assumption

**Locations:**
- Source case `tests/test_markdown_roundtrip_corpus.py:266-274`.
- Visual case `:365-375`.

`window.__lanternMdVisual.state.workHash` is already truthy before the edit in normal pending-work state, so waiting for “workHash exists” is not evidence that the current edit reached disk. The fixed 300 ms delay happened to be sufficient in the fresh small-fixture run, but it is not a revision-correlated completion condition.

This has not produced a wrong classification in the fresh corpus run, but it is the same false-settlement pattern that just failed MD-T000.

**Required correction:** use the same small reusable test-local stable-state poll for Source and Visual corpus edits:
- expected edited browser content / expected serialized content;
- real-file SHA == server `currentVersion`;
- stable across a bounded quiet interval;
- `md_temp` revision remains the original until Accept/Save.

Keep it in test code; do not add product instrumentation.

## What is accepted from this slice

### Fixture integrity

The fixture-only `.gitattributes` rule is appropriate:
- `tests/fixtures/md-fidelity/*.md: text unset`;
- `whitespace=-trailing-space`.

Fresh fixture checks confirm the working-tree corpus retains BOM/CRLF/mixed-EOL/no-final-newline bytes. The rule is narrowly scoped and does not alter repository-wide EOL behavior.

### Corpus coverage

The committed corpus covers the required Phase-0 categories:
- BOM;
- CRLF;
- mixed EOL;
- no final newline;
- frontmatter;
- raw HTML/comments;
- nested lists;
- fenced code;
- CJK/Unicode;
- repeated headings/paragraphs/table cells/rows;
- 30-column table.

Each fixture has one unambiguous marker for the intended edit, while duplicate surrounding structures remain available for later mapping tests.

### Product findings that remain credible

Even though MD-T000 settlement needs repair, two core observations are independently strong:

1. **Source backdrop implementation rebuilds the complete line layer.** Fresh MutationObserver evidence on 5,500 lines shows 5,501-node single-record replacement and tens of thousands of node additions/removals across the typing sequence. This directly matches current `renderSourceDiff`, which clears `sourceBackdrop.textContent` and rebuilds every line.
2. **Exact-byte fidelity defects exist today.** Fresh MD-T001 rerun reproduced mixed-EOL Source normalization and broad Visual reserialization on complex/table fixtures.

These are sufficient to justify continuing the proof/design program after the harness settlement is corrected. They are **not** authorization to skip MD-T002/T003.

## Benchmark interpretation / false-green review

The 5,500-line failure does not hinge solely on the wall-time number:
- sample count is only nine typed characters, matching the historical audit pattern but not broad statistical proof;
- `page.keyboard.type` wall time includes browser/Playwright scheduling and is not identical to the browser's own input→paint measurement;
- current 120 ms diff / 110 ms write timers mean post-input work can occur after the immediate input event.

Therefore future comparison should preserve **both** key-wall and browser-observed input→paint/Long Task/DOM metrics and compare the same harness before/after MD-T017. Do not claim one nine-sample p95 is a universal latency distribution.

The acceptance still clearly fails today because **“no full-backdrop rebuild” is independently violated**, regardless of timer attribution.

CJK/composition evidence is correctly labelled synthetic composition-event coverage, not full Windows Japanese/Vietnamese IME acceptance.

## YAGNI / maintainability / module separation / upstream alternatives

- Two ~475-line Phase-0 test modules are large but justified by disposable server/browser setup plus raw byte and perf evidence. Do not create a new production framework.
- There is some duplicated test setup/polling. After R8-1/R8-2, a **small test-only helper** for stable work-state settlement is justified because both modules need exactly the same revision/file quiescence invariant. Do not build a generic E2E framework.
- No product ownership duplication is introduced.
- No CodeMirror dependency or serializer rewrite is prematurely chosen.
- Mature-upstream evaluation remains correctly deferred to MD-T003.

Ponytail disposition: the only worthwhile reduction is to share the settlement helper narrowly between the two characterization paths if it reduces duplicated polling; otherwise leave the harness structure alone. No production lines should be added for measurement.

## UI/UX / scalability / performance disposition

- Current Source UX at 5,500 lines remains unacceptable: full backdrop regeneration and many Long Tasks are reproduced.
- ~5 MB behavior is clearly expensive in the fresh run, but no final 5 MB threshold is defined before the mature-editor POC, so keep it **MEASURED**, not a formal threshold FAIL.
- No page navigation/reload was observed; the “reload-like” user symptom remains a rendering/workload issue, not proven F5/navigation.
- Current Visual format-review UI prevents silent no-op persistence, but accepting conversion still permits unrelated byte changes; this must feed exact-write strategy design.

## Boundaries preserved

No changes to:
- real `.md` source-of-truth semantics;
- `md_temp` accepted snapshot semantics;
- CAS/store implementation;
- mapping engine;
- Crop;
- Pi/native terminal;
- live services;
- M-A11/M-A12/002 residual gates.

## Next DEV slice — test-harness correction only

At most two coherent items:

1. Repair MD-T000 final-write settlement/quiescence so the ~5 MB workload cannot report `write_settled=true` and later disagree with its own file/revision snapshot. Re-run the full six-workload opt-in harness and preserve red product classifications.
2. Apply the same revision-correlated stable-settlement rule to MD-T001 Source/Visual edits; rerun the corpus and prove the existing mixed-EOL/Visual FAILs remain reproducible rather than timing artifacts.

No product Source/Visual implementation change in this DEV turn. No MD-T002/T003 yet.

After the harness is stable and fresh runs pass as **characterization harnesses** while preserving the expected product-red evidence, route REVIEW. Only then should PLAN advance to MD-T002 mapping proof + MD-T003 mature CodeMirror merge/unified POC.

**Required route: DEV.**

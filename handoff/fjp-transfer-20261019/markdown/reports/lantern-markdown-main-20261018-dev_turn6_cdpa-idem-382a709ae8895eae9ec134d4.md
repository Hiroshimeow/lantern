# DEV Turn 6 — Spec 003 Phase-0 characterization (MD-T000 + MD-T001)

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18 JST  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed

Executed exactly the two PLAN Turn 5 proof tasks and stopped:

1. **MD-T000** — repeatable opt-in Edge Source typing/performance characterization.
2. **MD-T001** — exact-byte Markdown fidelity corpus + Source/Visual characterization.

No product runtime source was changed. No Source rewrite, CodeMirror, mapping engine, serializer fix, Crop, Pi/native terminal, CDPA, package/dependency install, live `:9999/:10099`, reset/stash/clean, or unrelated worktree operation occurred. `.pi/subagents.json` remains untouched.

## Commit / tracked scope

Committed:
- **`247480b244c1023aac1ec654e34a208df3e89d81`**
- `test(markdown): characterize source performance and fidelity`

Tracked files:
- `.gitattributes` — one fixture-only rule:
  `tests/fixtures/md-fidelity/*.md -text whitespace=-trailing-space`
- `tests/test_source_typing_perf_e2e.py`
- `tests/test_markdown_roundtrip_corpus.py`
- `tests/fixtures/md-fidelity/bom-crlf.md`
- `tests/fixtures/md-fidelity/mixed-eol-no-final.md`
- `tests/fixtures/md-fidelity/no-final-newline.md`
- `tests/fixtures/md-fidelity/constructs.md`
- `tests/fixtures/md-fidelity/duplicates.md`
- `tests/fixtures/md-fidelity/wide-table.md`

Post-commit `git status --short`: only preserved `?? .pi/`.

---

## MD-T000 — Source typing/performance characterization

### Harness method

`tests/test_source_typing_perf_e2e.py` is opt-in via `LANTERN_E2E=1` and uses:
- disposable root/config/cache/work state;
- ephemeral loopback Lantern server;
- real G6 Edge, never live Lantern;
- actual Preview → **Source** UI and real `/api/work/write`;
- browser `MutationObserver` on `.md-source-diff-backdrop-content`;
- `PerformanceObserver(type='longtask')`;
- input event → next `requestAnimationFrame` timing;
- end-user Playwright keyboard wall timing;
- composition-event path for the CJK/IME-oriented case;
- main-frame navigation listener;
- request ledger for `/api/work/write` and `/api/work`;
- focus/caret checks;
- raw real-`.md` and `md_temp` byte SHA-256/size before and after;
- server revision hashes from `/api/work`;
- final write settlement is polled against both real-file SHA and server work content, avoiding a false race on browser ACK state.

The harness stores raw machine-readable evidence at:
`.plan/lantern-markdown-main-20261018/dev_turn6_source_typing_perf.json`.

**Harness result:** one opt-in unittest **OK**.  
**Product acceptance result:** deliberately not all green.

### Final measured cases

Final successful run, Edge, six deterministic workloads:

| Case | Lines / bytes | Key p50 | Key p95 | paint p95 | Long tasks | Backdrop added | Full rebuild | Writes | Nav | Final write settled | md_temp unchanged | Classification |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---|---|
| 900 lines | 900 / 54,805 B | 9.930 ms | **79.566 ms** | 47.3 ms | 0 | 16,218 | yes | 9 | 0 | yes | yes | MEASURED_NO_FIXED_THRESHOLD |
| **5,500 lines** | 5,500 / 335,405 B | 20.078 ms | **116.598 ms** | 15.9 ms | 12 | **99,018** | **yes** | 9 | 0 | yes | yes | **FAIL** |
| ~500 KB | 209 / 500,000 B | 11.093 ms | 12.289 ms | 10.8 ms | 1 | 3,780 | yes | 9 | 0 | yes | yes | MEASURED_NO_FIXED_THRESHOLD |
| ~5 MB | 1,986 / 4,800,000 B | 233.159 ms | **688.916 ms** | **131.8 ms** | 33 | 21,857 | yes | 5 | 0 | yes | yes | MEASURED_NO_FIXED_THRESHOLD |
| CJK/composition | 900 / 52,111 B | 6.462 ms | 7.273 ms | 30.1 ms | 1 | 10,812 | yes | 6 | 0 | yes | yes | MEASURED_NO_FIXED_THRESHOLD |
| 30-col table | 96 / 19,575 B | 7.157 ms | 10.221 ms | 7.6 ms | 0 | 1,746 | yes | 9 | 0 | yes | yes | MEASURED_NO_FIXED_THRESHOLD |

### Binding 5,500-line classification

The fixed acceptance target remains:
- key wall p95 **<40 ms**;
- **no full-backdrop rebuild**.

Actual:
- p95 **116.598 ms**;
- `backdrop_max_added_one_record = 5501`;
- `backdrop_max_removed_one_record = 5501`;
- 99,018 backdrop nodes added across the nine typed inputs;
- `full_backdrop_rebuild = true`.

Therefore:
- `within_budget = false`;
- `acceptance = "FAIL"`;
- the **characterization harness succeeds while the product acceptance fails**, exactly as required.

This independently locks the same defect class as the historical audit without calling it a Foundation regression. There were **zero main-document navigations**, so the observed lag is not evidence of literal F5/reload.

### Preserved Source invariants observed

Across all six cases:
- real `.md` eventually changed through the product write-through path;
- final server work content and real-file SHA settled consistently;
- `md_temp` raw SHA and saved revision remained unchanged without Ctrl+S/Accept;
- focus remained on `.md-source-area`;
- no page errors;
- no main-document navigation.

The ~5 MB path coalesced nine inputs into five write POSTs but settled to the final textarea content. No fixed 500 KB/5 MB pass threshold is invented before MD-T003.

CJK evidence uses browser composition events to exercise the composition-oriented input path; it is **not claimed as full native Windows IME acceptance**.

---

## MD-T001 — exact-byte fidelity corpus

### Corpus

The checked-in corpus covers:
- UTF-8 BOM + CRLF;
- mixed CRLF/LF + no final newline;
- LF + no final newline;
- frontmatter;
- raw HTML and HTML comments;
- nested lists;
- fenced code;
- CJK/Unicode/emoji;
- repeated identical headings/paragraphs/table rows/cells;
- 30-column table.

Every fixture has one unambiguous `EDIT_TARGET` for the intended byte-span operation.

The narrow `.gitattributes` rule is required because CRLF/mixed-EOL/BOM are literal test bytes, not source formatting. Post-commit verification confirmed every working fixture blob hash equals its `HEAD` blob hash; Git is not normalizing the corpus.

### Source characterization

For every fixture the harness performs:
1. actual Preview → Source;
2. no-op Source → Preview → Source;
3. verifies zero no-op `/api/work/write` POSTs and exact real/md_temp bytes;
4. performs one Source edit `EDIT_TARGET -> EDIT_TARGET_SRC`;
5. computes exact expected raw bytes;
6. hashes/checks unchanged prefix and suffix;
7. records real revision and md_temp revision.

Results:

- **BOM + CRLF:** no-op PASS, edit **PASS**; untouched bytes remain identical.
- **constructs:** no-op PASS, edit **PASS**; frontmatter/comments/raw HTML/fence/CJK/duplicates outside edit remain exact.
- **duplicates:** no-op PASS, edit **PASS**; duplicate text does not confuse this direct Source operation.
- **no-final-newline:** no-op PASS, edit **PASS**; final-newline absence remains intact.
- **30-col table:** no-op PASS, edit **PASS**.
- **mixed CRLF/LF + no-final-newline:** no-op PASS, edit **FAIL**.

Concrete mixed-EOL failure:
- original: **102 bytes**;
- exact intended replacement should produce **106 bytes**;
- actual: **102 bytes**;
- untouched prefix hash changed, suffix stayed identical;
- first unexpected byte diff: offset **11**;
- `md_temp` remained byte-identical to the original.

This proves current Source write-through normalizes unrelated mixed-EOL bytes during an otherwise local edit. It is characterization only; no text/CAS serializer fix was made in this turn.

### Visual/Milkdown characterization

Two safe representative fixtures are exercised through the actual Visual surface:
- complex constructs;
- 30-column table.

No-op opening Visual:
- real `.md` and `md_temp` bytes remain unchanged;
- zero write POSTs;
- **PASS for no-op byte preservation**;
- however both report `roundtripSafe = false` and the Milkdown serialization already differs from decoded source.

One-block Visual edit:
- exact intended operation is `EDIT_TARGET -> EDIT_TARGET_VIS`;
- current product correctly shows the existing **format review** dialog;
- harness explicitly approves conversion to characterize what would be persisted;
- `md_temp` remains unchanged because no Accept/Ctrl+S is performed.

Concrete failures:
- **constructs:** expected 655 bytes, actual **690 bytes**; prefix **and suffix** differ; first unexpected diff at offset **0**; **FAIL**.
- **wide table:** expected 861 bytes, actual **1,521 bytes**; prefix differs, suffix remains identical; first unexpected diff at offset **25**; **FAIL**.

These are intentional red product classifications feeding MD-T002/T009. The harness does not treat the format-review UI as byte fidelity and does not fix serializer/mapping behavior in this turn.

Raw evidence:
`.plan/lantern-markdown-main-20261018/dev_turn6_markdown_roundtrip.json`.

---

## Verification actually run

### New Source benchmark
```
$env:LANTERN_E2E='1'
C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_source_typing_perf_e2e
```
Final result: **1 test OK in 35.082 s**, exit 0.  
Raw/log:
- `dev_turn6_source_typing_perf.json`
- `dev_turn6_source_perf.log`

Again: unittest OK means the characterization/oracle worked; 5,500-line product acceptance is explicitly **FAIL**.

### Fidelity corpus/browser characterization
```
$env:LANTERN_E2E='1'
C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_markdown_roundtrip_corpus
```
Final result: **2 tests OK in 18.956 s**, exit 0.  
Raw/log:
- `dev_turn6_markdown_roundtrip.json`
- `dev_turn6_fidelity.log`

The product-level per-case FAIL classifications remain preserved in JSON.

### Existing Markdown behavior E2E
Ran:
- `LiveMarkdownE2E.test_edit_source_real_written_before_accept_and_temp_only_after`
- `MarkdownModesE2E.test_three_modes_preserve_exact_source_and_render_mermaid`

Result: **2 tests OK in 9.437 s**, exit 0.  
Log: `dev_turn6_existing_markdown_e2e.log`.

### Focused native
```
pytest -q tests/test_live_markdown.py tests/test_markdown_draft_diff.py \
  tests/test_markdown_save_only.py tests/test_markdown_toolbar_breaks.py \
  tests/test_markdown_roundtrip_corpus.py tests/test_source_typing_perf_e2e.py
```
Result: **19 passed, 2 skipped in 1.73 s**, exit 0.  
The two skips are the opt-in browser characterizations and are not misreported as acceptance evidence.

### Full native suite
```
C:\Users\admin\miniconda3\python.exe -m pytest -q
```
Final result after the last harness corrections:
- **211 passed**
- **112 skipped**
- **47 subtests passed**
- **64.48 s**
- exit 0.

Log: `.plan/lantern-markdown-main-20261018/dev_turn6_full_pytest.log`.

### Static / Git hygiene
- `python -m py_compile tests/test_source_typing_perf_e2e.py tests/test_markdown_roundtrip_corpus.py` → exit 0.
- staged `git diff --cached --check` → exit 0.
- post-commit `git diff HEAD~1 HEAD --check` → exit 0.
- fixture working blobs == committed HEAD blobs for all six fixtures.
- `git check-attr` confirms `text: unset` and `whitespace: -trailing-space` only for `tests/fixtures/md-fidelity/*.md`.
- final tracked/staged tree clean; only `?? .pi/`.

## Known red evidence / next design inputs

This proof slice establishes, rather than fixes:

1. **Source performance defect:** 5,500-line p95 116.598 ms + full backdrop rebuild; 99,018 added backdrop nodes across nine inputs.
2. **Large Source cost:** ~5 MB p95 688.916 ms and many Long Tasks; no final threshold assigned yet.
3. **Source exact-byte defect:** mixed EOLs are normalized outside the intended byte operation.
4. **Visual exact-byte defect:** representative complex/wide-table one-block edits serialize unrelated source bytes after explicit format-review approval.

These are inputs to later MD-T002/T003/T007/T009. No implementation choice (including CodeMirror) was made here.

## Unchanged external/final gates

- Spec 001 M-A11 remains INCOMPLETE pending a controlled low-load independent FJP run; this turn does not alter Mermaid runtime.
- M-A12 owner/security acknowledgement remains INCOMPLETE; no agent signs it.
- Foundation 002 Linux/manual/owner budget gates remain unchanged.
- No release/DONE claim.

## Route

**REVIEW**. The two requested Phase-0 proof deliverables are committed. Independent REVIEW should now challenge benchmark attribution/sample validity, false-green risk, raw-byte fixture integrity, harness duplication/YAGNI, and whether these results are sufficient inputs for MD-T002/T003 without accidentally encoding implementation details.

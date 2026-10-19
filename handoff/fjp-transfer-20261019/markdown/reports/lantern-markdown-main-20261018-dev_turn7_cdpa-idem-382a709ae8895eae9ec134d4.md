# DEV Turn 7 — stabilize Phase-0 characterization settlement

Team: lantern-markdown-main-20261018 | task cdpa-idem-382a709ae8895eae9ec134d4 | role DEV | 2026-10-18 JST  
Workspace: G6 `E:\git-project\lantern`, branch `main`.

## Scope executed

Executed exactly REVIEW Turn 8's two harness-only corrections and stopped:

1. **R8-1 / MD-T000** — replace transient single-poll Source write settlement with bounded quiescent browser/server/file correlation.
2. **R8-2 / MD-T001** — use the same stable-settlement rule for Source and Visual fidelity edits.

No production Source/Visual code changed. No MD-T002/T003 implementation, CodeMirror POC, CAS/store change, mapping engine, Crop, Pi/native terminal, CDPA, live `:9999/:10099`, reset/stash/clean, package/dependency change, or unrelated worktree mutation.

## Commit

Current accepted commit:
- **`25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`**
- `test(markdown): stabilize characterization settlement`

Tracked scope:
- `tests/_markdown_characterization_settle.py` — narrow test-only settlement helper.
- `tests/test_source_typing_perf_e2e.py`
- `tests/test_markdown_roundtrip_corpus.py`

Post-verification `git status --short`: only preserved `?? .pi/`.

## R8-1 correction — Source performance settlement

The previous oracle could accept one transient equality, wait 150 ms, and then observe a newer real-file write. The replacement does not use a one-shot sleep.

The helper now requires the complete terminal signature to remain unchanged for a bounded quiet window:
- current editor text equals the expected final browser text;
- `view.lastSaved` equals the expected final text;
- browser `currentVersion` equals real-file SHA-256;
- browser `workHash` equals the same real-file SHA-256;
- accepted/saved revision stays at the original `md_temp` version;
- `saving/loading/conflict` are false;
- real-file SHA is unchanged;
- observed `/api/work/write` POST count is unchanged;
- browser revision/version/hash state is unchanged.

Timing contract:
- current product timers are 90/110/120 ms;
- polling interval = **120 ms**;
- required stable quiet interval = **600 ms** (five times the longest product timer);
- timeout remains bounded (30 s MD-T000).

Only after that stable interval does the helper:
1. fetch final `/api/work`;
2. re-read browser state;
3. re-read real file;
4. re-count write POSTs;
5. require all of them to still match the same final content/version/file sample.

The returned `real_after`, `current_real_version`, write count and quiet-window evidence therefore originate from the correlated final state, not from snapshots separated by an arbitrary post-settlement delay.

The helper avoids moving 5 MB editor strings across Playwright on every poll: expected-content equality is checked inside the page; Python polls compact state plus real-file bytes.

## R8-2 correction — fidelity settlement

Both MD-T001 edit paths now use the same helper:

- Source edit:
  - expected text is the exact edited Source textarea value;
  - final real-file bytes are taken from the settled sample;
  - real currentVersion must equal that final file SHA;
  - accepted `md_temp` revision must remain the original version.

- Visual edit:
  - expected text is the actual Milkdown serialization that the format-review path is about to persist;
  - after explicit conversion approval, the helper waits for the same browser/server/file quiescence;
  - final raw bytes and versions are correlated before byte-diff classification.

Per-case JSON now records:
- `write_settled=true`;
- `write_settle_poll_count`;
- `write_settle_quiet_ms`.

The characterization asserts every edit's quiet interval is at least 600 ms.

## Important anti-masking decision

During verification a dirty diagnostic reorder briefly placed the destructive ~5 MB workload last. That would make the original late-write defect harder to expose because no later workload follows it.

That reorder was **not accepted**. It was restored to committed/original order before final verification:

`lines-900 -> lines-5500 -> bytes-500k -> bytes-5m -> cjk-ime -> wide-30col`.

The final binding run therefore proves the ~5 MB case settles correctly **before** subsequent CJK and wide-table probes execute. Final tracked tree is clean apart from preserved `.pi/`.

## Fresh MD-T000 verification on committed/original order

Command:
```powershell
$env:LANTERN_E2E='1'
C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_source_typing_perf_e2e
```

Final result:
- **1 test OK**
- **47.439 s**
- exit 0.

Evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn7_source_perf_original_order.log`
- `.plan/lantern-markdown-main-20261018/dev_turn7_source_typing_perf_original_order.json`

Final correlated cases:

| Case | p95 key wall | Full backdrop rebuild | write POSTs | stable quiet | file/version match | md_temp unchanged | Product classification |
|---|---:|---|---:|---:|---|---|---|
| 900 lines | 31.740 ms | yes | 9 | 704.007 ms | yes | yes | MEASURED |
| **5,500 lines** | **139.778 ms** | **yes** | 8 | 692.779 ms | yes | yes | **FAIL** |
| ~500 KB | 73.623 ms | yes | 9 | 700.789 ms | yes | yes | MEASURED |
| ~5 MB | **1411.426 ms** | yes | 6 | **741.315 ms** | **yes** | **yes** | MEASURED |
| CJK/composition | 12.979 ms | yes | 6 | 693.512 ms | yes | yes | MEASURED |
| 30-col table | 8.586 ms | yes | 9 | 705.424 ms | yes | yes | MEASURED |

The ~5 MB sample no longer reproduces REVIEW's contradictory state:
- `write_settled=true`;
- final `current_real_version == real_after.sha256`;
- stable POST count across the quiet/final correlation;
- CJK and wide-table probes run afterward without a late write from the ~5 MB case corrupting its result.

The product-red findings remain intact:
- 5,500-line p95 is well above the fixed <40 ms budget;
- 5,500-line `full_backdrop_rebuild=true`;
- 93,517 backdrop nodes added and removed across the typed sequence;
- max one-record add/remove = 5,501 / 5,501;
- 20 Long Tasks;
- zero main-document navigations;
- focus preserved;
- `md_temp` unchanged.

~5 MB remains **MEASURED_NO_FIXED_THRESHOLD**, not promoted to a formal threshold failure. It is still visibly expensive (1411.426 ms key-wall p95, 166.1 ms input-to-next-paint p95, 52 Long Tasks), but MD-T003 owns the future large-file threshold/POC decision.

## Fresh MD-T001 verification

Command:
```powershell
$env:LANTERN_E2E='1'
C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_markdown_roundtrip_corpus
```

Result:
- **2 tests OK**
- **22.216 s**
- exit 0.

Evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn7_fidelity.log`
- `.plan/lantern-markdown-main-20261018/dev_turn6_markdown_roundtrip.json`

All Source/Visual edit cases reached a correlated stable state:
- every `write_settled=true`;
- quiet windows **693.333–738.847 ms**;
- every real `currentVersion` equals the final actual-file SHA;
- every accepted `md_temp` version/hash remains the original.

Product-red classifications are unchanged, proving they are not a timing artifact:

### Source
- BOM+CRLF: PASS.
- constructs: PASS.
- duplicates: PASS.
- no-final-newline: PASS.
- wide table: PASS.
- **mixed EOL/no-final-newline: FAIL**
  - expected 106 bytes;
  - actual 102 bytes;
  - prefix differs;
  - suffix remains identical;
  - first unexpected diff offset 11;
  - stable quiet = 702.048 ms.

### Visual
- **constructs: FAIL**
  - actual 690 vs expected 655 bytes;
  - prefix and suffix both differ;
  - format-review required;
  - stable quiet = 694.255 ms.
- **wide table: FAIL**
  - actual 1,521 vs expected 861 bytes;
  - prefix differs;
  - suffix remains identical;
  - format-review required;
  - stable quiet = 707.998 ms.

No-op cases remain PASS and produce no persistence.

## Other verification actually run

### Focused native
```
python -m pytest -q   tests/test_markdown_roundtrip_corpus.py   tests/test_source_typing_perf_e2e.py   tests/test_live_markdown.py   tests/test_markdown_draft_diff.py   tests/test_markdown_save_only.py   tests/test_markdown_toolbar_breaks.py
```

Result:
- **19 passed, 2 skipped in 1.70 s**
- exit 0.

The two skipped tests are the opt-in browser characterizations; both were executed separately above.

### Full native suite
```
C:\Users\admin\miniconda3\python.exe -m pytest -q
```

Result:
- **211 passed**
- **112 skipped**
- **47 subtests passed**
- **68.00 s**
- exit 0.

Evidence:
- `.plan/lantern-markdown-main-20261018/dev_turn7_full_pytest.log`.

### Static/Git hygiene
- `python -m py_compile` for helper + both characterization modules: exit 0.
- `git diff HEAD~1 HEAD --check`: exit 0.
- current `git diff --check`: exit 0.
- final tracked/staged tree clean.
- only preserved `?? .pi/`.

## Remaining product findings / boundaries

This turn repairs only the measurement oracle. It does **not** repair:
- Source full-backdrop rebuild/performance defect;
- mixed-EOL exact-byte Source defect;
- Visual broad-reserialization fidelity defects.

Those remain inputs to MD-T002/T003/T007/T009 after independent REVIEW accepts the stabilized proof harness.

No claim is made that the nine-character p95 is a universal latency distribution. The same harness/oracles must be retained for before/after comparison, together with input→paint, Long Task and DOM mutation evidence.

Spec 001 M-A11, M-A12, Foundation 002 residual gates, and all external owner/security/manual gates remain unchanged.

## Route

**REVIEW** — R8-1/R8-2 are repaired in test code only, final original-order MD-T000 and MD-T001 runs are stable, the product-red evidence is preserved, and no MD-T002/T003 implementation has begun.

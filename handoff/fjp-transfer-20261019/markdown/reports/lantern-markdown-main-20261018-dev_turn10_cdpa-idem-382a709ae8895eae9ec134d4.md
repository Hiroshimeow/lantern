# DEV Turn 10 — repair MD-T003 transaction/raw-byte and CRLF-edit proof

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: DEV turn 10  
Workspace: `E:\git-project\lantern`  
Incoming REVIEW: `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn10_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Scope

Executed only REVIEW Turn 10 correction R10-1/R10-2:

1. connect the exact-byte POC to a **real CodeMirror document transaction** rather than Python-derived marker offsets;
2. make the CRLF case perform a **real edit** and prove CRLF survives that edit.

No Lantern production Source replacement, persistence adapter, CAS/store, dependency, package-lock, Milkdown mapping implementation, Pi/native terminal code, CDPA, live :9999/:10099, reset/stash/clean, or unrelated work was changed.

MD-T002 was not reimplemented.

## Commit

Accepted correction commit:

- `64ecf5724d7a6ea0dcbd096ec4a926fa3956717e`
- `test(markdown): prove merge transaction byte bridge`

Commit changes exactly one tracked file:

- `tests/test_md_source_merge_e2e.py`

Parent accepted proof commit remains:

- `d593e6753d03087514463e3cdaecc0cbbc73d9b1`

`package.json` and `package-lock.json` remain unchanged.

## TDD evidence

### RED first

The test was strengthened before the POC capture code was added.

Command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Expected RED:

- 1 test ERROR
- failure at the new CRLF edit setup:
  `TypeError: CMPoc.clearCapturedChanges is not a function`
- log:
  `.plan/lantern-markdown-main-20261018/dev_turn10_cm6_red.log`

This proved the previous POC had no real transaction-capture bridge.

### GREEN implementation

The isolated POC update listener now records actual CodeMirror `ViewUpdate.transactions` document changes via `transaction.changes.iterChanges(...)`.

For each captured change the POC records:

- old-document `from`
- old-document `to`
- new-document `fromNew`
- new-document `toNew`
- inserted text

Capture is reset between controlled cases and is exposed only inside the POC harness.

No production editor API or persistence path was added.

## R10-1 — actual CodeMirror transaction now drives raw-byte patch proof

The exact-byte fixture contains:

- UTF-8 BOM;
- CJK text before the edit;
- non-BMP emoji before the edit;
- mixed LF/CRLF line endings;
- no final newline.

The browser performs one real CodeMirror replacement using the selected editor range and `page.keyboard.insert_text("EDIT_TARGET_X")`.

Fresh captured CodeMirror change:

```
from=11
to=22
fromNew=11
toNew=24
inserted="EDIT_TARGET_X"
```

Those captured `from/to/inserted` values — not Python `decoded.index(...)` offsets — are passed to the UTF-16 -> raw UTF-8 patch helper.

Assertions now prove:

- exactly one captured document change;
- captured old range matches the selected editor range;
- captured inserted text is exactly the intended replacement;
- both transaction boundaries are valid UTF-16 boundaries;
- the transaction old range maps to raw bytes containing exactly `EDIT_TARGET`;
- final patched bytes equal the exact expected one-edit byte sequence;
- UTF-8 BOM preserved;
- untouched raw prefix byte-identical;
- untouched raw suffix byte-identical;
- original LF/CRLF token sequence unchanged;
- CJK/non-BMP bytes before the edit unchanged;
- no final newline remains absent;
- no surrogate pair boundary is split.

Fresh machine-readable evidence:

`.plan/lantern-markdown-main-20261018/dev_turn10_md_source_merge.json`

Evidence field:

`byteStrategy.capturedChange = {"from":11,"to":22,"fromNew":11,"toNew":24,"inserted":"EDIT_TARGET_X"}`

The claim is now appropriately narrow: the POC proves a captured CodeMirror transaction range can drive an exact authoritative raw-UTF-8 byte patch for this controlled one-edit contract. It does not claim the production adapter is implemented.

## R10-2 — CRLF now proven after a real edit

The uniform CRLF case now:

1. creates CodeMirror state with `EditorState.lineSeparator.of("\r\n")`;
2. places the caret after `a`;
3. clears prior captured changes;
4. performs a real browser text insertion `X`;
5. reads the current editor document using the configured line separator;
6. inspects the actual captured transaction.

Fresh result:

- current editor text: `aX\r\nb\r\n`
- captured transaction:
  `{"from":1,"to":1,"fromNew":1,"toNew":2,"inserted":"X"}`

Therefore the POC now proves uniform CRLF survives **editing**, not merely initial load/read.

Evidence:

- `functional.uniformCrlfEditPreserved = true`
- `functional.uniformCrlfCapturedChange` contains the transaction above.

## Fresh final verification

### Post-commit MD-T003 POC

Command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Result:

- **1 test OK**
- runtime **10.482 s**
- exit 0
- log:
  `.plan/lantern-markdown-main-20261018/dev_turn10_post_commit_cm6.log`

Final conclusion remains:

- **GO_WITH_CONSTRAINTS**
- fixed 5,500-line POC target: **PASS**

Fresh post-commit performance evidence:

### 5,500 lines

- key-wall p95: **33.563 ms**
- input-to-paint p95: **17.0 ms**
- DOM lines: **61 -> 61**
- max added/removed per mutation record: **1 / 1**
- POC explicit serialization-helper calls during typing: **0**
- focus preserved: true
- navigation count: 0

### 500 KB

- key-wall p95: **28.513 ms**
- input-to-paint p95: **13.3 ms**
- DOM lines: **61 -> 61**
- max added/removed: **1 / 1**

### ~4.8 MB characterization

- key-wall p95: **13.077 ms**
- input-to-paint p95: **15.2 ms**
- DOM lines: **10 -> 10**
- max added/removed: **1 / 1**

No final product threshold is assigned to the ~4.8 MB characterization.

The `serializationCallsDuringTyping=0` metric is intentionally interpreted narrowly: the POC adapter did not call its explicit whole-document serialization helper during typing. It is not claimed as instrumentation of arbitrary internal CodeMirror implementation behavior.

### Syntax / hygiene

Actually run:

- `python -m py_compile tests/test_md_source_merge_e2e.py` — PASS
- `git diff --cached --check` before commit — exit 0
- `git diff HEAD^ HEAD --check` — exit 0
- commit diff for `package.json package-lock.json` — empty
- post-commit `git diff --quiet --` — exit 0

## Working-tree truth

Post-commit HEAD:

- `64ecf5724d7a6ea0dcbd096ec4a926fa3956717e`

No real tracked-content diff remains after the commit.

`git status --short` still reports the six known generated vendor files as modified:

- `static/vendor/lantern-crepe.min.css`
- `static/vendor/lantern-crepe.min.js.LEGAL.txt`
- `static/vendor/lantern-image-crop.min.js`
- `static/vendor/lantern-image-crop.min.js.LEGAL.txt`
- `static/vendor/lantern-large-block.min.js`
- `static/vendor/lantern-md-segment-worker.min.js`

This is the previously reviewed stat/EOL/index noise: `git diff --quiet --` is 0 and these files were not staged or committed in Turn 10.

Preserved unrelated:

- `?? .pi/`

## Remaining limits / not claimed

- Production Source integration with CodeMirror: NOT IMPLEMENTED.
- Production raw-byte transaction adapter: NOT IMPLEMENTED.
- Native Windows IME acceptance: NOT MEASURED.
- Final integrated MD-T017 Source benchmark: NOT RUN.
- Current product Source 5,500-line full-backdrop defect: unchanged baseline failure.
- Current product ~5 MB Source conflict/settlement behavior: unchanged baseline failure.
- Full repository suite: NOT RUN in Turn 10 because REVIEW requested one bounded POC-only correction.
- No claim that the isolated POC benchmark includes Lantern CAS/write-through/persistence costs.

## Route

**REVIEW** — the only requested MD-T003 proof gap is corrected, fresh post-commit POC evidence is green, and no production Source/persistence implementation was introduced.

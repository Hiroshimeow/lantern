# DEV Turn 11 — repair CRLF/mixed-EOL CodeMirror coordinate bridge proof

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: DEV turn 11  
Workspace: `E:\git-project\lantern`  
Incoming REVIEW: `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-review_turn11_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Scope

Executed only REVIEW Turn 11 R11-1:

1. make the MD-T003 POC prove a CodeMirror-normalized document coordinate can be mapped back to the authoritative UTF-16/raw UTF-8 source after preceding CRLF;
2. move the controlled mixed-EOL transaction after prior CRLF + LF + CJK/non-BMP content;
3. move the uniform CRLF edit to line 2 and prove both edited CRLF serialization and raw-byte location after a preceding CRLF.

No production Source implementation, persistence adapter, CAS/store, Milkdown mapping, dependency/package-lock, Pi/native terminal code, live :9999/:10099, CDPA, reset/stash/clean, or unrelated work was changed.

MD-T002 was not changed.

## Commit

Accepted correction commit:

- `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`
- `test(markdown): map normalized merge coordinates`

Commit changes exactly:

- `tests/test_md_source_merge_e2e.py`

Parent:
- `64ecf5724d7a6ea0dcbd096ec4a926fa3956717e`

`package.json` / `package-lock.json`: unchanged.

## TDD evidence

### RED

First, the controlled fixture was moved after a preceding CRLF/LF and the POC was switched from its prior explicit `lineSeparator="\n"` setup to CodeMirror's default line-break parsing so the reviewer's normalized-coordinate case was actually exercised.

Fresh RED:

- `LANTERN_CM_POC=1 python -m unittest -v tests.test_md_source_merge_e2e`
- result: **FAIL**
- concrete assertion:
  - actual raw span: `b'\nEDIT_TARGE'`
  - expected raw span: `b'EDIT_TARGET'`
- runtime: **8.579 s**
- log:
  `.plan/lantern-markdown-main-20261018/dev_turn11_cm6_red2.log`

This reproduced the REVIEW defect in the local POC: directly treating CodeMirror's normalized offset as an authoritative decoded-source offset selects the wrong raw bytes after prior CRLF.

## Correction

### Compact test-only coordinate mapper

Added only a POC helper:

`_cm_to_authoritative_utf16_offset(text, cm_offset)`

Contract:

- input offset = CodeMirror normalized document position;
- output offset = authoritative decoded Markdown UTF-16 position;
- CRLF in authoritative text contributes:
  - 1 CodeMirror logical position;
  - 2 authoritative UTF-16 code units;
- LF contributes 1 -> 1;
- lone CR is treated as one logical break;
- non-BMP code points retain 2 UTF-16 code units;
- an interior surrogate-pair boundary is preserved for explicit rejection rather than rounded.

`_raw_utf8_span(...)` now:

1. maps captured CodeMirror `from/to` through that helper;
2. validates the resulting authoritative UTF-16 boundaries;
3. converts only those authoritative UTF-16 boundaries to raw UTF-8 byte positions;
4. retains explicit BOM +3 handling.

No whole-file normalization or rewrite was introduced.

### Controlled mixed-EOL proof now crosses the offset-shift boundary

Authoritative test text contains, before the edit:

- UTF-8 BOM;
- a prior CRLF;
- CJK;
- non-BMP emoji;
- a later LF;
- then `EDIT_TARGET`;
- later CRLF/LF;
- no final newline.

The POC uses CodeMirror's default line-break parsing for this case.

Fresh captured real CodeMirror transaction:

```
from=20
to=31
fromNew=20
toNew=33
inserted="EDIT_TARGET_X"
```

Mapped authoritative UTF-16 range:

```
from=21
to=32
```

Therefore the proof now explicitly observes the expected +1 coordinate shift caused by the preceding CRLF:

```
normalizedCoordinateShift.from = 1
normalizedCoordinateShift.to   = 1
```

Assertions prove:

- CodeMirror current document is the normalized-line-break representation;
- captured transaction range is from the real editor update;
- normalized CodeMirror positions differ from authoritative positions after prior CRLF;
- mapped authoritative boundaries do not split a surrogate pair;
- mapped raw span contains exactly `EDIT_TARGET`;
- final raw bytes equal the exact expected one-edit byte sequence;
- BOM unchanged;
- untouched raw prefix byte-identical;
- untouched raw suffix byte-identical;
- LF/CRLF token sequence unchanged;
- CJK/non-BMP bytes before the edit unchanged;
- no final newline remains absent.

Fresh evidence:

`.plan/lantern-markdown-main-20261018/dev_turn11_md_source_merge.json`

Relevant evidence payload:

- `capturedChange = {"from":20,"to":31,"fromNew":20,"toNew":33,"inserted":"EDIT_TARGET_X"}`
- `authoritativeUtf16Range = {"from":21,"to":32}`
- `normalizedCoordinateShift = {"from":1,"to":1}`

### Uniform CRLF edit now occurs after a prior CRLF

Uniform CRLF source:

`a\r\nb\r\n`

The edit is now on line 2, after the first CRLF.

Fresh captured transaction:

`{"from":3,"to":3,"fromNew":3,"toNew":4,"inserted":"X"}`

Assertions prove:

- edited `sliceDoc()` = `a\r\nbX\r\n`;
- configured CRLF representation survives the real edit;
- the same normalized-coordinate -> raw-byte helper patches:
  `a\r\nb\r\n -> a\r\nbX\r\n`;
- the raw insertion therefore lands after `b`, not inside the preceding CRLF.

Evidence fields:

- `functional.uniformCrlfEditPreserved = true`
- `functional.uniformCrlfRawPatchPreserved = true`
- `functional.uniformCrlfCapturedChange` contains the transaction above.

## Fresh post-commit verification

### MD-T003 POC

Command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Post-commit result:

- **1 test OK**
- runtime **10.398 s**
- exit 0
- log:
  `.plan/lantern-markdown-main-20261018/dev_turn11_post_commit_cm6.log`

Conclusion remains:

- **GO_WITH_CONSTRAINTS**
- fixed 5,500-line POC target: **PASS**

Fresh post-commit performance:

### 5,500 lines
- key-wall p95: **18.394 ms**
- input->paint p95: **14.4 ms**
- DOM lines: **61 -> 61**
- max add/remove per mutation record: **1 / 1**
- explicit POC serialization-helper calls during typing: **0**
- focus preserved: true
- navigation count: 0

### 500 KB
- key-wall p95: **27.987 ms**
- input->paint p95: **14.3 ms**
- DOM lines: **61 -> 61**

### ~4.8 MB characterization
- key-wall p95: **36.407 ms**
- input->paint p95: **19.1 ms**
- DOM lines: **10 -> 10**

No product pass threshold is claimed for ~4.8 MB.

The serialization metric remains intentionally narrow: it proves this POC adapter did not call its explicit whole-document serialization helper while typing. It does not claim instrumentation of arbitrary internal CodeMirror behavior.

### Syntax / Git hygiene

Actually run:

- `python -m py_compile tests/test_md_source_merge_e2e.py` — PASS
- staged `git diff --cached --check` before commit — exit 0
- `git diff HEAD^ HEAD --check` — exit 0
- Turn 11 commit changes exactly `tests/test_md_source_merge_e2e.py`
- `package.json` / `package-lock.json` commit diff — empty
- post-commit `git diff --quiet --` — exit 0

## Working-tree truth

HEAD:

- `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`

No actual tracked-content diff remains after the commit.

The same six previously reviewed generated vendor paths still appear `M` in `git status --short`, but `git diff --quiet --` is 0. They remain stat/EOL/index noise and were not staged or committed.

Preserved unrelated:

- `?? .pi/`

## Remaining limits / not claimed

- Production CodeMirror Source integration: NOT IMPLEMENTED.
- Production raw-byte persistence adapter: NOT IMPLEMENTED.
- Native Windows IME acceptance: NOT MEASURED.
- Integrated MD-T017 Lantern Source benchmark: NOT RUN.
- Current product Source 5,500-line backdrop defect: unchanged baseline failure.
- Current product ~5 MB Source conflict/settlement behavior: unchanged baseline failure.
- Full repository suite: NOT RUN in this turn because REVIEW requested one bounded POC-only correction.

## Route

**REVIEW** — R11-1 is reproduced RED, corrected with a compact test-only normalized-coordinate -> authoritative UTF-16/raw-byte mapper, and fresh post-commit MD-T003 evidence is green. No integrated Source implementation was started.

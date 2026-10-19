# DEV Turn 9 — MD-T002 mapping proof + MD-T003 CodeMirror merge POC

## Status

COMPLETE for the two PLAN Turn 6 proof subtasks. Source/test work is committed and ready for independent REVIEW.

Commit:
- `d593e6753d03087514463e3cdaecc0cbbc73d9b1`
- `test(markdown): prove source mapping and merge editor viability`

Authoritative workspace:
- `E:\git-project\lantern`
- branch `main`
- parent HEAD at resume: `25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`

No Pi/native terminal implementation, CDPA, Lantern :9999 runtime, CAS/store semantics, dirty-segment writer, Source replacement, or live persistence contract was changed.

## Changed files

Tracked commit contains exactly:
1. `tools/visual_markdown_entry.js`
2. `static/vendor/lantern-crepe.min.js`
3. `static/vendor/lantern-crepe.manifest.json`
4. `tests/test_md_source_mapping.py`
5. `tests/test_md_source_merge_e2e.py`

`package.json` and `package-lock.json` are unchanged.

`.pi/` remains untracked/unmodified by this slice.

## MD-T002 — deterministic source-range mapping proof

### Implementation

Added a narrow, test-visible `debugSourceMap(markdown, metadata)` contract on the existing Visual/Milkdown owner. It reuses the existing:
- remark pipeline from `remarkCtx`,
- Milkdown parser from `parserCtx`,
- ProseMirror view/ranges from `editorViewCtx`,
- existing verified top-level block proof.

It does **not** implement any write path.

Evidence fields distinguish:
- decoded source offsets: JavaScript UTF-16 code units;
- raw source offsets: UTF-8 bytes;
- UTF-8 BOM: explicit +3-byte prefix outside decoded Markdown;
- mdast type/index/source position;
- PM type/range;
- revision/content hash;
- proof classification.

UTF-16 surrogate-pair boundaries are rejected rather than rounded.

### Fail-closed behavior

Mapping is only returned when authoritative Markdown equals the current Milkdown serialization and the existing PM block proof succeeds.

Typed classifications:
- `block-only`
- `stale`
- `unmapped`
- `ambiguous`

No nearest-text, first-match, Nth-occurrence, regex, or positional guess was added.

### Matrix result

Final evidence:
`.plan/lantern-markdown-main-20261018/dev_turn9_md_source_mapping.json`

GO/NO-GO:
- block-level dirty-segment patching: `GO_WITH_EXACT_SOURCE_IDENTITY_ONLY`
- nested table/list/inline patching: `NO_GO_UNPROVED`
- stale/unmapped/ambiguous fallback: `EXACT_SOURCE_MODE_FOR_STALE_UNMAPPED_AMBIGUOUS`

Observed exact block-level mappings:
- canonical ASCII
- CJK + non-BMP emoji
- BOM + LF
- duplicate identical headings/paragraphs
- canonical nested-list outer block

Observed fail-closed stale/source-only cases include:
- existing duplicate/table corpus fixture
- canonical table formatting normalized by Milkdown
- 30-column table
- constructs/frontmatter/raw-HTML/code corpus
- BOM + CRLF
- mixed EOL/no-final-newline
- alternate list marker alias

No cell/list-child/inline identity claim is made.

## MD-T003 — isolated CodeMirror 6 mature-editor POC

### Exact test-only packages

Installed only below ignored `.plan/lantern-markdown-main-20261018/cm6-merge-poc-deps`:
- `@codemirror/merge@6.12.2`
- `codemirror@6.0.2`
- `esbuild@0.28.2`

Merge package:
- license: MIT
- integrity:
  `sha512-V8JvyAPjHbPupqP7BeMcsdsYCbyPij74jxIbaIJDORI+VZzW44zFmon8bF+oxGWvOKhcRmkiUMXd8MxHr3YA2w==`

Product package files remained unchanged.

### Functional result

Final evidence:
`.plan/lantern-markdown-main-20261018/dev_turn9_md_source_merge.json`

`unifiedMergeView({original})` proved:
- add/change/delete and bottom-of-file hunks;
- changed-line / inline / gutter indication;
- removed-text/deleted-chunk affordance;
- keyboard selection;
- Undo/Redo;
- uniform CRLF `sliceDoc()` behavior with line-separator configuration;
- baseline/original update via `originalDocChangeEffect` without replacing current document;
- CJK insertion;
- synthetic composition events, explicitly **not** native Windows IME acceptance;
- viewport virtualization;
- zero POC whole-document serialization calls during typing;
- no main-document navigation while typing.

Split `MergeView` was exercised only as a comparison and duplicates editor surfaces.

### Exact-byte persistence constraint

POC also proved the required adapter strategy:
- CodeMirror transaction positions are decoded UTF-16 ranges;
- authoritative product persistence must patch the original UTF-8 bytes;
- BOM and untouched mixed-EOL bytes can therefore remain exact;
- whole-document CodeMirror serialization is **not** acceptable for mixed-EOL byte fidelity.

No live Lantern write endpoint was connected to the POC.

### Required-host performance on G6

Final G6 POC results:

- 5,500 lines:
  - key wall p95: **23.026 ms**
  - input→paint p95: **12.0 ms**
  - DOM lines: **61 → 61**
  - max nodes added/removed per mutation record: **1 / 1**
  - serialization calls during typing: **0**
  - focus preserved: **true**
  - navigation count: **0**

- 500 KB:
  - key wall p95: **29.282 ms**
  - input→paint p95: **13.5 ms**
  - DOM lines: **61 → 61**
  - serialization calls during typing: **0**

- ~4.8 MB characterization:
  - key wall p95: **23.901 ms**
  - input→paint p95: **13.1 ms**
  - DOM lines: **10 → 10**
  - serialization calls during typing: **0**
  - long-task max: **144 ms**
  - no final 5 MB product pass threshold was invented.

Fixed 5,500-line POC target (<40 ms, no full-document DOM rebuild): **PASS**.

POC conclusion:
- **GO_WITH_CONSTRAINTS**

Constraints:
1. real `.md` bytes remain authoritative;
2. `md_temp` remains accepted snapshot;
3. exact persistence needs a thin UTF-16→raw-UTF-8 patch adapter;
4. mixed EOL must not be persisted by whole-document serialization;
5. synthetic composition is not native Windows IME acceptance.

## Verification actually run

### TDD proof

Recovered initial MD-T002 RED from prior interrupted run:
- `debugSourceMap mapping evidence API missing`
- 1 test, ERROR as expected for missing behavior.

Final MD-T002:
- command: `LANTERN_E2E=1 python -m unittest -v tests.test_md_source_mapping`
- result: **1 test OK**
- runtime: **13.875 s**

Final MD-T003:
- command: `LANTERN_CM_POC=1 python -m unittest -v tests.test_md_source_merge_e2e`
- result: **1 test OK**
- runtime: **8.750 s**

### Build / syntax / hygiene

- `node tools/build_markdown.mjs`: **exit 0**
- `node --check tools/visual_markdown_entry.js`: **exit 0**
- `python -m py_compile tests/test_md_source_mapping.py tests/test_md_source_merge_e2e.py`: **exit 0**
- `git diff --check`: **exit 0**
- staged `git diff --cached --check`: **exit 0**
- package.json/package-lock diff: **none**

### Existing focused tests

`python -m pytest -q tests/test_live_markdown.py tests/test_markdown_roundtrip_corpus.py tests/test_md_source_mapping.py tests/test_md_source_merge_e2e.py`
- **8 passed, 3 skipped**
- skipped items are opt-in E2E/POC when their env flags are absent.

MD-T001 full E2E corpus:
- `tests.test_markdown_roundtrip_corpus`
- **2 tests OK**
- runtime **21.441 s**
- existing characterization still reports the known mixed-EOL Source and Visual normalization failures; the harness itself passes because those are evidence, not falsely promoted to PASS.

Mapping/Visual focused regression:
- deep Preview→Source mapping: **PASS**
- edited Visual caret→Source line: **PASS**
- pending Source edit restored in Visual: **PASS**
- `test_opening_mermaid_and_tables_never_saves_a_normalized_file`: **FAIL**, dirty became true

The last failure was independently reproduced with the **HEAD parent bundle** substituted temporarily:
- same test
- same assertion
- parent bundle also **FAIL**
- therefore it is baseline/pre-existing and is not introduced by the Turn 9 mapping-evidence bundle.

### MD-T000 Source characterization

`tests.test_source_typing_perf_e2e` was run twice.

It remains RED exactly in the already-known baseline Source lane:
- 5,500-line retry key-wall p95: **65.625 ms** (>40 ms target)
- full backdrop rebuild still present
- later ~5 MB case fails to settle due browser state `conflict: true` within 30 s

This Turn 9 slice does not touch the Source editor/write path. The CM6 isolated POC demonstrates a mature upstream candidate that does meet the fixed 5,500-line POC target, but the current product Source remains failing and is **not** claimed fixed.

## Working-tree/integration state

Committed HEAD:
- `d593e6753d03087514463e3cdaecc0cbbc73d9b1`

`git diff --quiet --` after commit: **0** — no actual tracked content difference from HEAD.

`git status --short` still displays six generated vendor files as worktree-modified due the current G6 stat/index behavior, but:
- each raw working-file hash equals its HEAD blob hash;
- `git diff --name-only` reports none of them;
- `git diff --quiet` is 0.

These are stat-only status artifacts, not content changes. They were not staged or committed.

`.pi/` remains untracked and preserved.

## Remaining risks / NOT_MEASURED

- Native Windows IME acceptance: **NOT_MEASURED**.
- Nested table-cell/list-child/inline source identity: **NO_GO_UNPROVED**.
- Product Source replacement with CM6: **NOT IMPLEMENTED**.
- Raw-byte adapter in product persistence: **NOT IMPLEMENTED**.
- Current 5,500-line Source product target: **FAIL**, baseline full-backdrop defect remains.
- Current ~5 MB Source settle behavior: **FAIL/INCOMPLETE** due baseline conflict state.
- Full repository test suite: **NOT RUN** in this turn.
- Final Edge/E2E / benchmark / UX acceptance for the eventual Source implementation remains a later independent gate.

## REVIEW focus requested

Independent REVIEW should explicitly evaluate:
- correctness of the UTF-16 ↔ UTF-8/BOM proof;
- whether any classification accidentally overclaims exact identity;
- fail-closed behavior and duplicate-content handling;
- over-engineering/YAGNI of the debug API and POC harness;
- scope drift versus proof-only ownership;
- maintainability/module ownership;
- mature upstream choice: unified CodeMirror merge vs split comparison;
- UX implications of single-editor unified diff;
- performance methodology and whether tests genuinely prove the stated POC acceptance;
- regression evidence, especially the two independently documented baseline failures.

## Next route

REVIEW.

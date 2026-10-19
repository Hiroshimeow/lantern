# REVIEW Turn 10 — MD-T002 mapping proof + MD-T003 CodeMirror merge POC

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 10 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `d593e6753d03087514463e3cdaecc0cbbc73d9b1`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn9_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE DEV.**

MD-T002 is acceptable as a conservative block-level GO/NO-GO proof, and the isolated CodeMirror 6 unified merge POC is promising on UX/virtualization/performance. However, MD-T003 currently overclaims the most important fidelity bridge: the test says a **CodeMirror transaction UTF-16 range can drive an exact raw-UTF-8 patch**, but it never captures a real CodeMirror transaction range. It manually computes the marker offsets in Python and patches bytes with those manually-derived offsets.

That is a concrete acceptance-proof gap because the eventual Source implementation depends on exactly this adapter boundary. Fix the POC evidence only; do not implement production Source replacement yet.

## Independent review performed

Loaded `ponytail-review` and `verification-before-completion`. Re-read PLAN Turn 6, Spec 003 MD-T002/MD-T003 contracts, commit diff, `tools/visual_markdown_entry.js`, both new tests, generated manifest, package state and current git truth.

Repository facts:
- HEAD `d593e6753d03087514463e3cdaecc0cbbc73d9b1`.
- Commit changes:
  - `tools/visual_markdown_entry.js`
  - rebuilt `static/vendor/lantern-crepe.min.js`
  - `static/vendor/lantern-crepe.manifest.json`
  - `tests/test_md_source_mapping.py`
  - `tests/test_md_source_merge_e2e.py`
- `package.json` / `package-lock.json`: no diff.
- `git diff HEAD~1 HEAD --check`: exit 0.
- Six generated vendor files appear ` M` in `git status`, but REVIEW verified each raw working-file Git hash equals its HEAD blob, `git diff --name-only` is empty and `git diff --quiet` returns 0. Treat these as stat/EOL-index noise, not content changes. Do not stage/reset/clean them merely to cosmetically alter status.
- Preserved unrelated `?? .pi/subagents.json`.

## Fresh independent verification

### MD-T002

Command:

`LANTERN_E2E=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_mapping`

Fresh result:
- **1 test OK**
- **15.320 s**
- exit 0
- Edge 155.0.4283.62

Observed independently:
- canonical ASCII maps block-only;
- CJK/non-BMP maps with UTF-16 source offsets and larger UTF-8 byte spans;
- BOM LF maps with +3 raw-byte offset;
- duplicate headings/paragraphs retain distinct source ranges without text search;
- nested-list outer block can map but nested identity is explicitly `unproved`;
- canonical table, wide table, constructs/frontmatter/raw HTML/code, BOM+CRLF, mixed EOL, alias list and existing duplicate/table fixture fail closed as stale/source-only rather than receiving guessed PM ranges;
- for every returned source unit, the test slices the actual raw fixture bytes at `rawByteStart:rawByteEnd` and proves the decoded slice equals the exact JavaScript UTF-16 source slice;
- test also proves `sourceVersion == rawSha256` in the fixture runtime.

### MD-T003

Command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Fresh result:
- **1 test OK**
- **12.276 s**
- exit 0
- Edge 155.0.4283.62

Fresh POC evidence:
- `@codemirror/merge 6.12.2`, MIT, expected registry integrity;
- `codemirror 6.0.2`;
- `esbuild 0.28.2`;
- no tracked dependency-file mutation;
- unified add/change/delete/bottom hunks render;
- changed-line, deleted-chunk and gutter affordances exist;
- selection + undo/redo work;
- original baseline can update without replacing current doc;
- split comparison duplicates two editor surfaces;
- synthetic composition is correctly labelled non-native IME;
- 5,500-line fresh p95 **22.536 ms**, input→paint p95 **11.3 ms**, 61 DOM lines before/after, max added/removed one node, no navigation;
- exact 500,000-byte fresh p95 **22.914 ms**;
- 4,800,000-byte characterization fresh p95 **30.675 ms**, no final product threshold claimed.

This is strong evidence that the mature unified editor is viable for MD-US6/MD-T017 performance/viewport goals. It is not yet proof of the product persistence adapter.

## MD-T002 disposition — ACCEPTED as Phase-0 proof

The mapping implementation is conservative enough for the stated scope.

### Correctness

`buildSourceEvidence` explicitly separates:
- mdast/decoded offsets = JavaScript UTF-16 code units;
- raw offsets = UTF-8 bytes;
- BOM = explicit +3 raw bytes outside the decoded Markdown;
- revision metadata;
- mdast type/range;
- PM type/range only after block proof.

Surrogate-pair split boundaries are rejected.

`buildSourceMappingEvidence` refuses PM mapping when authoritative Markdown does not equal the current Milkdown serialization and refuses nested identity claims. No regex, nearest-text, first-match or Nth-occurrence algorithm is introduced.

### Duplicate/table/fail-closed behavior

The duplicate corpus contains repeated headings, paragraphs, table cells and rows. The canonical repeated heading/paragraph case proves duplicate textual content can retain distinct exact raw ranges through AST/PM block order. Table-heavy/non-round-trip fixtures fail closed; no cell/row identity is falsely inferred.

Therefore the conclusion is appropriately narrow:
- top-level block dirty-segment design: **GO only with exact revision/source identity**;
- nested table/list/inline identity: **NO-GO / unproved**;
- stale/unmapped representations: exact Source fallback.

### Important semantic limit

The current `stale` label also covers “Milkdown serialization differs from authoritative bytes” cases, not only concurrent-revision staleness. That is acceptable for this debug proof because it fails closed, but later product contracts should avoid interpreting this label as proof of an external concurrent edit. Do not build watcher/CAS semantics from this classification name alone.

## Concrete MD-T003 defect

### R10-1 — raw-byte adapter conclusion is not connected to a real CodeMirror transaction

**Locations:**
- `tests/test_md_source_merge_e2e.py:61-78` — `_raw_patch_utf8`;
- `:89-107` — update listener only counts `docChanged`, does not capture changes;
- `:579-617` — “byteStrategy” proof;
- `:614-615` — report claims `CodeMirror transaction UTF-16 range -> authoritative raw UTF-8 byte patch`.

**Evidence:** the POC computes:

- `marker_chars = decoded.index("EDIT_TARGET")`;
- `marker_start` / `marker_end` by Python UTF-16 encoding;
- passes those manually-computed values to `_raw_patch_utf8`.

There is no use of `update.transactions`, `update.changes`, `ChangeSet.iterChanges()`, or any actual CodeMirror transaction coordinate in this byte-persistence proof. Fresh source grep confirms the only transaction-related runtime logic is `if(update.docChanged) stats.docChanges++`.

Therefore the current test proves:
- the standalone UTF-16→UTF-8 patch arithmetic can preserve BOM/mixed-EOL bytes for a manually-known range;

but it does **not** prove:
- a real CodeMirror edit emits the same `from/to/inserted` contract the product adapter will receive;
- those actual coordinates can be applied to the authoritative raw bytes without touching unrelated bytes.

That distinction is material. The eventual Source writer must consume CodeMirror transactions, not a Python search-derived marker range.

### R10-2 — CRLF test covers load/read, not edit

**Location:** `tests/test_md_source_merge_e2e.py:542-555`.

The test creates a CRLF document with `EditorState.lineSeparator.of("\r\n")` and immediately calls `CMPoc.getDoc()`. It proves configured `sliceDoc()` returns CRLF after loading, but does not type/edit and then re-check the untouched line separators.

PLAN Turn 6 explicitly required “CRLF input without normalization merely by loading/editing”. The load half is proven; the edit half is not.

## Required DEV correction — one bounded POC-only subtask

Do not modify Lantern production persistence yet.

Strengthen the existing MD-T003 POC so a **real CodeMirror edit transaction** is the source of truth for the raw patch proof:

1. In the POC update listener, capture the actual document change set for one controlled edit:
   - old-document `from/to` in CodeMirror positions;
   - inserted text;
   - enough data to prove there is exactly the intended change.
2. Use those captured coordinates, not Python `decoded.index(...)`, to drive the UTF-16→raw-UTF-8 patch helper.
3. Run this against a fixture containing:
   - UTF-8 BOM;
   - mixed LF/CRLF or a separate uniform CRLF edit case;
   - CJK + non-BMP content before the edit;
   - no final newline if convenient.
4. Assert:
   - final raw bytes equal the exact expected one-edit byte sequence;
   - BOM preserved;
   - untouched prefix/suffix byte-identical;
   - untouched CRLF/LF pattern byte-identical;
   - no surrogate boundary is split.
5. For uniform CRLF, perform a real edit and verify the editor view/current doc still returns the configured CRLF representation, rather than only checking immediately after load.

Then rerun the existing MD-T003 POC. No product package dependency, Source replacement, CAS/store or live write endpoint should be added.

## Tests / claims that need narrowing but not another product change

### “zero full-document serialization during typing”

The current `serializationCallsDuringTyping` counter increments only in the POC's own `CMPoc.getDoc()` wrapper. Since typing does not call that wrapper, zero is expected. It validly proves **the POC adapter does not invoke its explicit whole-doc serialization helper while typing**. It does not instrument arbitrary internal CodeMirror implementation calls.

Keep the evidence, but phrase the claim narrowly. Performance/DOM measurements provide the practical evidence that no product-style full-backdrop rebuild occurs.

### Performance methodology

The POC is sufficient as a viability spike, not a final product benchmark:
- nine typed characters at 5,500 lines;
- isolated editor, no Lantern CAS/write-through/diff persistence;
- initialization cost excluded;
- native IME absent.

The fixed 5,500-line POC target is met freshly, but final MD-T017 must run the accepted MD-T000 harness against integrated Source.

## YAGNI / maintainability / ownership / upstream choice

- **Mature upstream:** official CodeMirror 6 unified merge is the correct candidate to continue evaluating. No custom editor is justified.
- **Unified vs split UX:** unified is the better fit because it preserves one Source editing surface; split duplicates editor surfaces and should remain comparison-only.
- **No dependency scope drift:** exact POC packages remain under ignored `.plan`; product package files are unchanged.
- **Debug mapping API:** adding narrow mapping evidence to the existing Milkdown owner is preferable to reimplementing parser/PM mapping in Python. It is acceptable despite increasing the built Crepe bundle by ~2 KB.
- **Large test files:** the POC is long, but most lines are disposable browser/package/perf evidence. Do not create a generic editor framework from it.
- **No product abstraction:** correct. The thin raw-byte adapter remains a design constraint, not production code.

Ponytail disposition: **Lean enough for proof work. No speculative refactor requested.**

## Scope / preservation

No regression fix is requested for:
- current product Source 5,500-line full-backdrop FAIL;
- current ~5 MB Source conflict/settlement behavior;
- the pre-existing “opening Mermaid/table dirty=true” failure already reproduced against the parent Crepe bundle.

Preserve:
- real `.md` as source of truth;
- `md_temp` as accepted snapshot;
- CAS/store ownership;
- Pi/native terminal boundary;
- live :9999/:10099;
- `.pi/subagents.json`;
- unrelated stat-only vendor worktree state.

## Route

**DEV** — repair only the MD-T003 transaction-to-raw-byte/CRLF-edit proof. MD-T002 does not need reimplementation. After fresh green POC evidence, return to REVIEW; if accepted, PLAN may then choose the next product contract/Source implementation slice.


# REVIEW Turn 12 — MD-T003 normalized-coordinate bridge acceptance

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 12 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn11_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE PLAN.**

REVIEW Turn 11's concrete defect is closed: the POC no longer interprets normalized CodeMirror positions as direct offsets into the authoritative mixed-EOL source. Fresh independent tests prove the post-CRLF coordinate shift and the raw-byte patch lands on the intended bytes while preserving BOM, untouched EOL spelling, non-BMP content and no-final-newline state.

No new actionable implementation defect is reproduced in this bounded POC-only slice. MD-T003 can be accepted as **GO_WITH_CONSTRAINTS Phase-0 evidence**. This does **not** authorize treating the test helper as production persistence code or declaring integrated Source/IME/performance complete.

## Sources and scope reviewed

Loaded:
- `ponytail-review`
- `verification-before-completion`

Independently inspected:
- incoming DEV Turn 11 report;
- exact HEAD commit/diff;
- current `tests/test_md_source_merge_e2e.py`;
- Spec 003 MD-T003 / plan / task contract;
- current generated POC evidence;
- package/lock state;
- final git tree.

No reliance on DEV's green claim without rerunning the acceptance command.

## Repository truth

Current G6 facts:

- branch: `main`
- HEAD: `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`
- commit: `test(markdown): map normalized merge coordinates`
- changed tracked file in this slice: exactly `tests/test_md_source_merge_e2e.py`
- `git diff HEAD~1 HEAD --check`: **exit 0**
- `package.json` / `package-lock.json`: no commit diff
- `git diff --quiet --`: **exit 0**
- `git diff --cached --quiet --`: **exit 0**
- preserved unrelated `?? .pi/subagents.json`
- six generated vendor paths remain status-only EOL/index noise already reviewed previously; no content diff was staged or committed

No production Source, CAS/store, Milkdown, Pi/native terminal, CDPA or live :9999/:10099 change occurred.

## Fresh independent verification

### MD-T003 POC

Fresh command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Fresh result:

- **1 test OK**
- **11.295 s**
- exit 0

This proves the current committed POC, not an earlier log.

### Independent coordinate countercase matrix

REVIEW separately exercised the committed helpers with authoritative text containing:

1. BOM + CRLF + Japanese + non-BMP + LF before target;
2. two preceding CRLFs;
3. lone CR + LF before target.

Fresh results:

- case 1: normalized CM offset **7** -> authoritative UTF-16 offset **8** -> selected exact `EDIT_TARGET`
- case 2: normalized CM offset **4** -> authoritative UTF-16 offset **6** -> selected exact `EDIT_TARGET`
- case 3: normalized CM offset **4** -> authoritative offset **4** -> selected exact `EDIT_TARGET`

All selected the exact target raw bytes.

### Independent CodeMirror line-break behavior

Using the exact installed POC `@codemirror/state`, REVIEW checked:

- input `a\rb` -> CodeMirror doc `a\nb`
- input `a\r\nb` -> CodeMirror doc `a\nb`
- input `a\nb` -> CodeMirror doc `a\nb`

This independently confirms the mapper's premise that CodeMirror normalizes CR/CRLF logical line breaks while the authoritative raw Markdown may retain different byte spelling.

## R11-1 correction verification

### Mapping algorithm

The new test-only `_cm_to_authoritative_utf16_offset(text, cm_offset)`:

- walks authoritative decoded text;
- counts CRLF as:
  - one CodeMirror logical position;
  - two authoritative UTF-16 code units;
- counts lone CR/LF as one logical/source unit;
- counts non-BMP characters as two UTF-16 units;
- preserves an interior surrogate boundary so the existing boundary validator rejects it rather than rounding;
- fails on negative/out-of-range offsets.

`_raw_utf8_span` now maps CodeMirror position -> authoritative UTF-16 position -> UTF-8 raw-byte span, adding BOM offset only at the final raw-byte boundary.

This is the correct abstraction boundary for the POC.

### Controlled mixed-EOL transaction now crosses the CRLF shift

Current fixture contains before the edit:

- UTF-8 BOM;
- a prior CRLF;
- CJK;
- non-BMP emoji;
- a later LF.

The real CodeMirror transaction is captured from `transaction.changes.iterChanges`.

Fresh evidence file after REVIEW run records:

- captured CM range: `from=20, to=31`
- authoritative UTF-16 range: `from=21, to=32`
- normalized shift: `+1 / +1`
- inserted text: `EDIT_TARGET_X`

Assertions prove:

- CodeMirror current doc is the normalized-line-break representation;
- the normalized coordinate differs from authoritative coordinate after CRLF;
- mapped raw span is exactly `EDIT_TARGET`;
- final patched bytes equal one exact intended edit;
- BOM preserved;
- untouched prefix/suffix byte-identical;
- original EOL token sequence preserved;
- non-BMP/CJK bytes before the edit unchanged;
- no final newline remains absent.

This directly covers the defect reproduced in Turn 11.

### Uniform CRLF edit now occurs after prior CRLF

Current uniform CRLF proof edits line 2, after the first CRLF.

Captured change:

`from=3, to=3, inserted='X'`

The same mapper patches:

`a\r\nb\r\n -> a\r\nbX\r\n`

and `sliceDoc()` returns the CRLF-preserving edited representation.

Therefore the previous "edit before first CRLF" blind spot is closed.

## MD-T003 acceptance matrix

| Requirement | REVIEW Turn 12 disposition |
|---|---|
| unified merge single-editor candidate | **PROVEN in isolated POC** |
| split comparison | **PROVEN comparison-only** |
| add/change/delete/bottom hunks | **PROVEN** |
| gutter/deletion affordance | **PROVEN** |
| keyboard selection / Undo / Redo | **PROVEN** |
| CRLF load + edit behavior | **PROVEN in POC** |
| BOM preservation strategy | **PROVEN for transaction/raw-byte adapter fixture** |
| mixed-EOL untouched-byte preservation | **PROVEN for controlled transaction** |
| CJK/non-BMP before edit | **PROVEN** |
| synthetic composition | **PROVEN only as synthetic events** |
| native Windows IME | **NOT_MEASURED**, correctly deferred |
| 500 KB characterization | **PROVEN POC viability** |
| ~4.8 MB characterization | **MEASURED, no invented product threshold** |
| 5,500-line <40 ms viability | **PROVEN in isolated POC** |
| bounded viewport DOM / no full backdrop rebuild | **PROVEN in isolated POC** |
| production CAS/write-through integration | **NOT IMPLEMENTED** |
| integrated MD-T017 benchmark | **NOT RUN** |

The POC conclusion **GO_WITH_CONSTRAINTS** is now technically supported.

## Constraints that must carry into product design

These are not defects in the proof slice, but PLAN/DEV must preserve them:

1. **CodeMirror positions are normalized-editor coordinates, not authoritative raw/source offsets.**
   Production persistence must retain an explicit coordinate bridge.
2. **Real `.md` bytes remain authoritative.**
   Do not use whole-document CodeMirror serialization for exact-byte persistence.
3. **BOM/EOL metadata remains part of document state.**
4. **Inserted newline policy still needs an explicit product contract.**
   The current proof uses non-newline inserted text. When the user presses Enter in CRLF/mixed-EOL files, the production adapter must deliberately choose replacement bytes rather than accidentally inheriting editor-normalized `\n`.
5. **The current POC mapper scans from document start.**
   It is acceptable test code. Do not copy this O(document-size)-per-change implementation directly into integrated 5 MB Source without an indexed line/raw-offset strategy and MD-T017 benchmark evidence.
6. **Native Japanese/Vietnamese IME remains final integrated acceptance work.**
7. **Multi-change/multi-cursor transaction persistence is not yet proven.**
   The current one-change bridge is sufficient for the Phase-0 feasibility decision, not final persistence coverage.

## Correctness / performance / UX assessment

### Correctness

The known CRLF coordinate corruption pathway is independently fixed in the proof. No false direct coordinate equivalence remains in the test helper.

### Performance

The isolated POC still demonstrates the mature editor can meet the fixed 5,500-line viability target with bounded viewport DOM. This does not include Lantern write-through/CAS/diff costs; MD-T017 remains the integrated gate.

### UI/UX

Unified MergeView remains the better product candidate than split MergeView because it keeps one editable Source surface while showing inline/gutter diff state. No additional custom diff editor is justified.

### Scalability

CodeMirror viewport behavior is materially better than the existing full-backdrop rebuild. The raw coordinate bridge must be implemented with an efficient indexed representation in product code; the proof's linear scanner is intentionally disposable.

### Maintainability / module ownership

The change remains test-only. No competing document store or editor owner was created. The future adapter should sit at the Source editor <-> existing canonical document/CAS boundary rather than becoming another document truth.

### Mature upstream alternative

Official CodeMirror 6 merge/unified remains a suitable mature upstream primitive. There is no evidence supporting a custom editor implementation.

## Over-engineering / YAGNI

**Ponytail result: Lean already. Ship.**

The added mapper is the minimum POC logic required to prove the exact defect from Turn 11. No generic mapping framework, production persistence service or secondary editor abstraction was added.

The only warning is forward-looking: do not promote the test helper verbatim into product code just because it is green.

## MD-T002 status

Unchanged from REVIEW Turn 10:

- block-level exact mapping under revision/source identity: **GO**
- nested table/list/inline exact identity: **NO-GO / unproved**
- stale/normalized/ambiguous cases: fail closed to exact Source mode
- no text-search guessing

No new MD-T002 action required.

## Preservation verified

Preserved:

- real `.md` source-of-truth semantics;
- `md_temp` accepted-snapshot semantics;
- current CAS/store owner;
- Milkdown production behavior;
- existing Source product baseline failures;
- Pi/native terminal ownership;
- live :9999/:10099;
- CDPA;
- unrelated `.pi/subagents.json`;
- stat-only vendor paths.

## Remaining gates

Still not complete:

- production CodeMirror Source integration;
- raw-byte production persistence adapter;
- MD-T004–T018 implementation chain;
- native IME;
- integrated Source benchmark/UX acceptance;
- Spec 001 M-A11/M-A12 residual gates;
- Foundation residual Linux/manual/owner gates.

No `DONE` claim.

## PLAN handoff recommendation

Accept MD-T002 + MD-T003 Phase-0 proofs and choose the next dependency-ordered implementation slice.

The next implementation should preserve the proof constraints, especially:
- explicit normalized-editor -> authoritative byte coordinate mapping;
- real `.md` bytes as truth;
- `md_temp` snapshot semantics;
- CAS at the existing owner;
- no full-document serialization per keypress;
- no direct copy of the linear POC mapper without performance design.

Per the task graph, PLAN may now advance to the shared data/diff contract sequence (MD-T004/MD-T005 or another dependency-correct bounded pair), while keeping actual Source replacement MD-T007/MD-T017 behind the store/diff contract.

**Required route: PLAN.**

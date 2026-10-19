# REVIEW Turn 11 — MD-T003 transaction/raw-byte bridge review

**Team/task:** lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
**Role/date:** REVIEW turn 11 / 2026-10-19 JST  
**Workspace:** G6 `E:\git-project\lantern`, branch `main`, HEAD `64ecf5724d7a6ea0dcbd096ec4a926fa3956717e`  
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn10_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision

**ROUTE DEV.**

DEV Turn 10 correctly connects the POC to a real CodeMirror transaction and upgrades the CRLF case from load-only to edit coverage. The fresh POC is green. However, REVIEW independently reproduced a **remaining coordinate-system defect** that the new test does not exercise:

> CodeMirror document positions count normalized line breaks as one character, while the authoritative decoded/raw Markdown may contain `\r\n` as two UTF-16 code units / two raw bytes. Passing a real CodeMirror transaction `from/to` directly into the current raw-byte helper is wrong for edits occurring after a preceding CRLF.

The current controlled mixed-EOL edit is intentionally placed **before** its only CRLF, and the uniform CRLF edit is placed **before** the first CRLF. Therefore both tests avoid the exact offset-shift case that the production adapter must solve.

This is a concrete acceptance defect in the POC bridge, not production Source code. Fix the test-only coordinate mapping before PLAN advances to the integrated Source implementation.

## Independent repository review

Loaded `ponytail-review` and `verification-before-completion`. Inspected the complete one-file commit diff and current test code.

Repository facts:
- HEAD: `64ecf5724d7a6ea0dcbd096ec4a926fa3956717e`.
- Commit changes exactly `tests/test_md_source_merge_e2e.py`.
- `git diff HEAD~1 HEAD --check`: exit 0.
- `python -m py_compile tests/test_md_source_merge_e2e.py`: exit 0.
- `package.json` and `package-lock.json`: unchanged.
- final tracked-content diff outside HEAD: none (`git diff --quiet --` exit 0; cached diff exit 0).
- six previously reviewed generated vendor paths still appear modified only as stat/EOL-index noise; no content diff.
- `.pi/subagents.json` remains untracked/preserved.

No product Source/CAS/store/Pi/terminal/live-service implementation was edited.

## Fresh independent POC run

Command:

`LANTERN_CM_POC=1 C:\Users\admin\miniconda3\python.exe -m unittest -v tests.test_md_source_merge_e2e`

Result:
- **1 test OK**
- **10.862 s**
- exit 0

The repaired test does now prove several useful things:

### Real transaction capture is real

The POC update listener iterates actual:
- `ViewUpdate.transactions`;
- `transaction.changes.iterChanges(...)`;

and captures:
- old `from/to`;
- new `fromNew/toNew`;
- inserted text.

The raw-byte proof uses the captured `from/to/inserted`, not Python-computed marker offsets.

### Current controlled byte case

The controlled fixture has:
- UTF-8 BOM;
- Japanese text;
- non-BMP emoji before the edit;
- LF + CRLF mixture;
- no final newline.

The real browser replacement is captured and the helper proves:
- exact marker raw bytes selected;
- patched raw file equals expected one-edit bytes;
- BOM unchanged;
- raw prefix/suffix unchanged;
- EOL token sequence unchanged;
- no final newline added;
- transaction boundaries do not split a surrogate pair.

### Uniform CRLF edit

The test now performs a real edit and verifies `sliceDoc()` yields:
`aX\r\nb\r\n`

with the actual captured insertion transaction.

These are genuine improvements over Turn 10.

## Concrete remaining defect

### R11-1 — CodeMirror positions and authoritative mixed-EOL source positions diverge after CRLF

**Relevant code:**
- `tests/test_md_source_merge_e2e.py:83-101` — `_raw_utf8_span(raw, start_utf16, end_utf16)`
- `:151-169` — captured CodeMirror transaction positions
- `:672-781` — transaction-to-raw-byte proof
- `:615-646` — uniform CRLF edit proof

The helper currently interprets a CodeMirror transaction offset as a UTF-16 offset into the original decoded authoritative source:

`prefix = original_decoded_utf16[: start_utf16 * 2]`

That assumption is false once a CRLF occurs before the edit.

### Fresh independent counterexample — CodeMirror normalizes document line breaks

REVIEW ran the installed POC CodeMirror state directly:

`EditorState.create({doc:'a\r\nb\nEDIT'})`

Fresh output:

- raw JS string length = **9**
- CodeMirror doc length = **8**
- raw string marker index = **5**
- CodeMirror marker index = **4**
- CodeMirror document = `a\nb\nEDIT`

With explicit `EditorState.lineSeparator.of("\r\n")`:

- raw CRLF string marker index = **6**
- CodeMirror document marker index = **4**
- `sliceDoc()` emits CRLF as configured, but the internal document positions still count normalized line breaks as one.

Therefore `lineSeparator` controls serialization, not raw-coordinate identity.

### Fresh independent corruption proof against current helper

REVIEW fed a real-CodeMirror-style normalized position to the current helper for:

`BOM + "a\r\nb\nEDIT_TARGET"`

Using CodeMirror marker position `4` instead of authoritative decoded index `5`, current `_raw_utf8_span` selected:

`b'\nEDIT_TARGE'`

instead of:

`b'EDIT_TARGET'`

and the current patch helper produced:

`BOM + b'a\r\nbEDIT_TARGET_XT'`

which corrupts the surrounding bytes.

This is the exact failure the adapter must prevent.

## Why Turn 10 tests miss this

### Mixed-EOL byte fixture

Current controlled fixture:

`"# T\n" + "日本語 🏮\n" + "EDIT_TARGET\r\n" + ...`

The target is **before** the only CRLF. All preceding EOLs are single-character LF, so CodeMirror position happens to equal the authoritative decoded UTF-16 offset.

Thus the test demonstrates transaction capture but not CRLF-aware coordinate translation.

### Uniform CRLF case

Current edit inserts `X` at position 1 in:

`a\r\nb\r\n`

That position is also before the first CRLF. It verifies edit + CRLF serialization, but again avoids the offset-shift boundary.

## Required correction — one POC-only subtask

Do not implement production Source yet.

### 1. Prove a CRLF-aware CodeMirror-position → raw-byte mapping

The POC must no longer feed CodeMirror absolute positions directly into a helper that assumes original decoded-string offsets.

Use a small test-only mapping contract that explicitly accounts for:
- UTF-8 BOM;
- CodeMirror's normalized line-break coordinate system;
- authoritative LF / CRLF / mixed-EOL byte widths;
- UTF-16/non-BMP boundaries.

A reasonable minimal strategy is to map the normalized CodeMirror offset through the authoritative source by scanning logical line breaks, or use line/column identity plus authoritative raw line starts. Do not normalize/rewrite the entire raw file.

### 2. Move the controlled edit after prior CRLF

Use a fixture where the target occurs after at least:
- one CRLF;
- one LF;
- CJK/non-BMP content.

Example shape only:

`BOM + "head\r\n日本語🏮\nEDIT_TARGET..."`

Then:
- perform a real CodeMirror edit;
- capture actual `transaction.changes.iterChanges` coordinates;
- prove the raw adapter maps those normalized CodeMirror coordinates to the exact intended raw marker bytes;
- prove prefix/suffix/EOL/BOM/no-final-newline byte identity.

The test should fail if CodeMirror coordinates are naively interpreted as authoritative decoded offsets.

### 3. Strengthen uniform CRLF edit position

Place the CRLF edit on line 2 or later, after at least one CRLF, then prove:
- captured CodeMirror transaction coordinate;
- edited `sliceDoc()` retains CRLF;
- if raw-byte mapping is exercised there, it selects the correct raw location after the preceding 2-byte CRLF.

One post-CRLF case is enough; do not build a general persistence framework in the POC.

## MD-T002 disposition

MD-T002 was not changed by this commit. REVIEW Turn 10 already accepted it as a conservative block-level proof:
- UTF-16 vs UTF-8 distinction explicit;
- BOM handled;
- duplicates do not use text matching;
- nested/cell/inline identity remains unproved;
- normalized/stale cases fail closed.

No MD-T002 rework requested.

## MD-T003 disposition

Current status:

- mature upstream choice (CodeMirror unified merge): **GO candidate**
- unified diff UX: **supported in POC**
- viewport/performance viability: **supported in POC**
- transaction capture: **supported**
- uniform CRLF edit serialization: **supported**
- raw-byte patch arithmetic for coordinates already aligned with source: **supported**
- **general CodeMirror normalized-coordinate → authoritative mixed-EOL raw-byte bridge: NOT PROVEN / current naive helper is reproducibly wrong after prior CRLF**
- native Windows IME: **NOT MEASURED**
- integrated Lantern Source/CAS benchmark: **NOT IMPLEMENTED / NOT MEASURED**

Therefore `GO_WITH_CONSTRAINTS` remains plausible architecturally, but MD-T003 should not be accepted as complete until the line-ending coordinate bridge is proven.

## Over-engineering / YAGNI / maintainability

The 199-line test expansion is justified by the byte-contract proof; no production abstraction was added. The new transaction capture API is isolated to the POC.

Do not respond to R11-1 by creating:
- a generic source-map framework;
- a second editor model;
- a new product persistence service;
- a full EOL normalization layer.

A compact test-only normalized-position → raw-byte mapper plus one post-CRLF transaction case is sufficient.

**Ponytail:** lean enough once the coordinate bug is fixed; no unrelated simplification requested.

## Scope / UX / performance / ownership

- **UI/UX:** unified CodeMirror remains preferable to split MergeView because it preserves one Source editing surface.
- **Performance:** fresh POC remains fast enough for viability, but this turn is not final integrated MD-T017 acceptance.
- **Scalability:** viewport DOM remains bounded in the POC; no new concern introduced.
- **Ownership:** real `.md` remains authoritative; `md_temp` remains accepted snapshot; no CAS/store change.
- **Regression:** no product runtime regression introduced by this test-only commit.
- **Mature upstream:** no custom editor is warranted.

## Preservation

Preserve unchanged:
- product Source implementation;
- raw-byte persistence production code;
- Milkdown mapping;
- Pi/native terminal;
- live :9999/:10099;
- CDPA;
- `.pi/subagents.json`;
- stat-only vendor paths.

## Required route

**DEV** — fix only the CRLF/mixed-EOL coordinate bridge proof described above, rerun MD-T003 fresh, and return to REVIEW. Do not start integrated Source replacement in the same turn.


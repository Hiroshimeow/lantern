# DEV Turn 14 — MD-T006 canonical byte/EOL-safe diff contract

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4  
Role: DEV turn 14  
Workspace: `E:\git-project\lantern`  
PLAN: `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-plan_turn8_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Scope

Executed **MD-T006 only**.

No MD-T007/T017 Source integration, CodeMirror product dependency, new Python diff engine, new document store, watcher, Crop, Pi/native-terminal, CDPA, or live :9999/:10099 mutation was started.

Accepted commit:

- `44b65ff5aac4bffa015385bbed3d0ce8643484c9`
- `fix(markdown): preserve exact diff source spans`

Tracked commit scope:

1. `static/markdown_draft_diff.js`
2. `static/markdown_visual_shell.js`
3. `tests/test_md_diff_contract.py`
4. `tests/test_live_markdown_e2e.py`

`package.json` / `package-lock.json`: unchanged.

## Reproduced defect / TDD RED

### Canonical engine RED

Created `tests/test_md_diff_contract.py` first.

Initial run:

`python -m pytest -q tests/test_md_diff_contract.py`

Result:

- **12 failures, 1 pass**
- expected missing behavior included:
  - no `offsetUnit`;
  - no exact `baseSpan` / `draftSpan`;
  - no `applyHunk()`;
  - `merge3()` normalized mixed CRLF/LF to LF.

Concrete reproduced merge failure:

- expected: `A\r\nOURS\nC\r\nTHEIRS`
- actual:   `A\nOURS\nC\nTHEIRS`

### Real Edge hunk RED

Added a mixed-EOL/no-final-newline partial Accept/Undo E2E before changing the view action path.

Initial result:

- stale-external collision case: PASS;
- mixed-EOL partial Accept/Undo: **FAIL**.

Observed accepted `md_temp` after first hunk:

- expected raw bytes kept CRLF/LF mixture;
- actual accepted bytes had whole-document LF normalization.

Log:

`.plan/lantern-markdown-main-20261018/dev_turn14_e2e_red.log`

### Internal separator RED

After the first exact-span implementation, added a focused adjacent-modification case where the replacement editor text was globally LF-normalized.

RED result:

- base: `a\r\nb\r\nc\nD`
- normalized draft logical edits: `A\nB\nc\nD`
- expected applied: `A\r\nB\r\nc\nD`
- actual: `A\nB\r\nc\nD`

This proved a multi-line modification still rewrote an unchanged CRLF *inside* the hunk. The final implementation therefore preserves target line separators for same-cardinality modifications, not only separators outside the hunk.

## Canonical diff implementation

### One logical-line / exact-source model

`static/markdown_draft_diff.js` remains the single browser-side owner.

Logical comparison stays EOL-insensitive, but the engine now builds an exact decoded-source model carrying JavaScript **UTF-16 code-unit offsets** into the original string.

Each hunk retains existing rendering fields:

- `kind`
- `baseStart/baseEnd`
- `draftStart/draftEnd`
- `baseText/draftText`

and now also carries:

- `offsetUnit: "utf16-code-unit"`
- exact `baseSpan {start,end,text}`
- exact `draftSpan {start,end,text}`
- exact draft replacement source slice.

No raw UTF-8 mapper was duplicated from MD-T002.

### Exact application helper

The engine now exports:

`applyHunk(text, hunk, "forward"|"reverse")`

Behavior:

- fail closed if the expected source line/span no longer matches;
- same-cardinality modifications replace line **content only**, preserving every target separator byte-for-byte, including separators between adjacent changed lines;
- structural add/delete hunks use exact boundary spans so beginning/end/trailing-newline changes are represented without whole-document normalization;
- no view reconstructs a mutated document by normalized `split/join`.

### View adapter deduplication

`markdown_visual_shell.js::actionHunk` no longer contains its own:

- `replace(/\r\n?/g,'\n')`
- `split('\n')`
- `join('\n')`

mutation logic.

Both operations now call the canonical engine:

- Accept -> `diff.applyHunk(before, hunk, "forward")`
- Undo -> `diff.applyHunk(real, hunk, "reverse")`

The existing caller-side revision/CAS checks remain unchanged:

- current real version must match;
- accepted version must match;
- Accept posts exact `expectSavedVersion` + `expectCurrentVersion`;
- Undo posts existing work hash + base version.

CAS/file I/O remains owned by `LiveMarkdownStore`.

## Merge3 exactness

`merge3(base, ours, theirs)` no longer reconstructs from normalized line arrays.

It now:

1. computes canonical exact hunks against the exact base string;
2. keeps existing overlap/equivalent conflict classification;
3. applies non-conflicting hunks in descending source order through the same `applyHunk()` contract.

Covered behavior:

- non-overlap ours/theirs;
- identical edit applied once;
- overlapping edits conflict;
- add/add same boundary conflict when different;
- identical add same boundary is not duplicated;
- delete vs modification collision;
- beginning insertion;
- ending deletion;
- trailing newline addition;
- mixed CRLF/LF base;
- no-final-newline;
- CJK/non-BMP;
- globally normalized replacement text without changing untouched target separators.

## Required contract matrix

Fresh post-commit command:

`python -m pytest -q tests/test_md_diff_contract.py tests/test_markdown_draft_diff.py tests/test_live_markdown.py`

Result:

- **25 passed**
- **6 subtests passed**
- exit 0.

`tests/test_md_diff_contract.py` covers:

- add/delete/modify;
- separated hunks;
- adjacent modifications;
- first/last-line boundaries;
- trailing-newline/no-final-newline;
- LF/CRLF/mixed EOL;
- checked-in `mixed-eol-no-final.md` fixture;
- BOM + CRLF logical/source preservation;
- CJK/non-BMP;
- exact forward/reverse hunk application;
- normalized editor text vs target EOL preservation;
- merge non-overlap/identical/overlap/add/delete collisions and structural boundaries.

The existing `tests/test_markdown_draft_diff.py` also remains green; no useful old coverage was deleted.

## Real Edge integration

Fresh **post-commit** focused Edge run:

1. `test_mixed_eol_partial_accept_then_undo_preserves_exact_raw_bytes`
2. `test_stale_external_write_refuses_rendered_hunk_without_corruption`
3. `test_two_hunks_accept_one_undo_other_and_source_inline_rows`
4. `test_two_browser_clients_cannot_blind_overwrite_same_line`
5. `test_visual_hunk_buttons_undo_real_file_without_accepting_others`

Result:

- **5 tests OK**
- **15.166 s**
- exit 0.

Log:

`.plan/lantern-markdown-main-20261018/dev_turn14_post_commit_live.log`

### Mixed-EOL partial Accept / Undo

Fixture bytes in the disposable root contain:

- CRLF;
- LF;
- two separate modified hunks;
- no final newline.

Verified raw-file / `md_temp` sequence:

1. accepted snapshot initially equals exact original bytes;
2. external real file gets two exact source-preserving changes;
3. Accept first hunk:
   - real file remains exact two-change bytes;
   - `md_temp` becomes exact first-change-only bytes;
   - original CRLF/LF spelling remains unchanged;
4. Undo remaining hunk:
   - real file becomes exact first-change-only bytes;
   - `md_temp` remains exact accepted first-change-only bytes;
   - no final newline remains absent.

### Stale external hunk

The stale-hunk E2E renders one hunk, then writes newer authoritative disk bytes before clicking Accept.

Verified:

- newer external bytes remain authoritative;
- accepted `md_temp` remains original;
- action is refused through the existing preflight/409 contract;
- no partial/corrupt write occurs;
- UI reports `File changed elsewhere`.

The oracle intentionally permits either:
- client preflight refusal with no action POST; or
- server 409.

It does **not** claim which of those two branches occurred in the final run.

### Existing adapters

Existing Source partial-hunk, same-line two-browser collision, and Visual hunk Undo remain green with the canonical helper.

## MD-T001 exact-byte corpus

Required corpus rerun:

`LANTERN_E2E=1 python -m unittest -v tests.test_markdown_roundtrip_corpus`

Result:

- **2 tests OK**
- **23.184 s**

The characterization still honestly reports the already-known Phase-0 product reds:

- Source direct typing on `mixed-eol-no-final.md` still normalizes untouched EOL outside the intended edit;
- Visual conversion on complex constructs/wide table still broadly reserializes.

Those are **not** falsely reported fixed by T006. T006 fixes canonical diff/hunk/merge mutation; current textarea Source write-through remains a later MD-T007/T017 integration concern.

BOM+CRLF, ordinary Source fixtures, no-final-newline, duplicate and wide-table Source cases continue to report their prior expected characterization outcomes.

Log:

`.plan/lantern-markdown-main-20261018/dev_turn14_md_t001.log`

## Full native suite

Before commit, after the final product/test implementation:

`C:\Users\admin\miniconda3\python.exe -m pytest -q`

Result:

- **223 passed**
- **123 skipped**
- **53 subtests passed**
- **104.14 s**

Log:

`.plan/lantern-markdown-main-20261018/dev_turn14_full_pytest.log`

Skipped opt-in E2E/POC tests are not reported as PASS; required Edge cases were run explicitly above.

## Syntax / Git hygiene

Fresh/post-commit evidence:

- `node --check static/markdown_draft_diff.js` — exit 0.
- `node --check static/markdown_visual_shell.js` — exit 0.
- staged `git diff --cached --check` before commit — exit 0.
- `git diff HEAD^ HEAD --check` — exit 0.
- Turn 14 commit files are exactly the four listed at the top.
- `package.json` / `package-lock.json` commit diff — empty.
- post-commit `git diff --quiet --` — exit 0.
- post-commit `git diff --cached --quiet` — exit 0.

## Working-tree truth

HEAD:

- `44b65ff5aac4bffa015385bbed3d0ce8643484c9`

No actual tracked-content diff remains after the commit.

The six previously reviewed generated vendor paths still appear `M` in `git status --short` as existing status/index noise and were not staged or committed:

- `static/vendor/lantern-crepe.min.css`
- `static/vendor/lantern-crepe.min.js.LEGAL.txt`
- `static/vendor/lantern-image-crop.min.js`
- `static/vendor/lantern-image-crop.min.js.LEGAL.txt`
- `static/vendor/lantern-large-block.min.js`
- `static/vendor/lantern-md-segment-worker.min.js`

Preserved unrelated:

- `?? .pi/`

## YAGNI / ownership

No second diff engine was created.

No Python diff service, CRDT/OT, rope/piece-table, new merge dependency, event bus, or backend diff owner was added.

The increased code in `markdown_draft_diff.js` is confined to one exact-source line model plus hunk span/application helpers in the existing canonical owner. View mutation logic was reduced rather than duplicated.

## Not claimed

- MD-T007/T017 Source integration: NOT STARTED.
- Existing Source mixed-EOL direct typing bug: still FAIL in MD-T001 characterization.
- Visual broad serialization cases: still FAIL characterization.
- Native Japanese/Vietnamese IME integrated acceptance: NOT MEASURED.
- Final Source 5,500-line product performance: not part of this T006 slice.
- M-A11/M-A12 and Foundation residual gates remain outside this turn.

## Route

**REVIEW** — MD-T006 canonical exact-source hunk/apply/merge contract is implemented and committed; required unit/corpus/Edge/CAS regression evidence was run, and Source integration remains gated behind independent T006 review.

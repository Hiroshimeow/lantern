# REVIEW Turn 15 — MD-T006 canonical exact-source diff contract

Team/task: lantern-markdown-main-20261018 / cdpa-idem-382a709ae8895eae9ec134d4
Role/date: REVIEW turn 15 / 2026-10-19 JST
Workspace: G6 E:\git-project\lantern, branch main, HEAD 44b65ff5aac4bffa015385bbed3d0ce8643484c9
Incoming: .plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-dev_turn14_cdpa-idem-382a709ae8895eae9ec134d4.md

## Decision
ROUTE PLAN.

MD-T006 is acceptable. Fresh independent unit/contract and real Edge verification support the new canonical exact-source hunk/application/merge behavior, and no material correctness/YAGNI/module-ownership defect was reproduced.

This accepts T006 only. Source integration MD-T007/T017 remains gated to the next planned slice.

## Review scope
Loaded ponytail-review and verification-before-completion. Read PLAN Turn 8, Spec 003 T006/FR04/FR07 requirements, complete static/markdown_draft_diff.js, actionHunk adapter changes, new contract tests, and current repository truth.

Repository facts:
- HEAD 44b65ff5aac4bffa015385bbed3d0ce8643484c9
- commit: fix(markdown): preserve exact diff source spans
- files: static/markdown_draft_diff.js, static/markdown_visual_shell.js, tests/test_live_markdown_e2e.py, tests/test_md_diff_contract.py
- git diff HEAD~1 HEAD --check: exit 0
- package/lock unchanged
- known vendor status-only noise and .pi/subagents.json preserved

## Fresh independent contract verification
Command:
python -m pytest -q tests/test_md_diff_contract.py tests/test_markdown_draft_diff.py tests/test_live_markdown.py

Fresh result:
- 25 passed
- 6 subtests passed
- 7.87 s
- exit 0

This independently verifies exact-span metadata, forward/reverse application, mixed EOL, CRLF/BOM/no-final-newline, Unicode/non-BMP, structural boundaries, merge conflict semantics, and existing live Markdown store regressions.

## Fresh independent Edge verification
A first REVIEW Edge run was started in parallel with the Node/unit contract suite. Under that concurrent host load, the first mixed-EOL case timed out waiting for the Source textbox; the next two tests passed. That run is recorded as FAILED and is not treated as acceptance evidence.

REVIEW then reran the failing mixed-EOL case alone:
- 1 test OK
- 6.399 s

Finally REVIEW reran the exact five-case DEV acceptance set sequentially with no parallel test load:

1. mixed-EOL partial Accept/Undo exact raw bytes
2. stale external hunk refuses corruption
3. two hunks: Accept one / Undo another
4. two-browser same-line stale collision
5. Visual hunk Undo without accepting others

Fresh result:
- 5 tests OK
- 14.867 s
- exit 0

The earlier parallel timeout is therefore classified as host/test-load sensitivity, not a reproduced T006 product defect. It should not be hidden, but it does not block this slice.

## Correctness review

### Canonical source model
The engine now compares logical line content while retaining exact decoded-source UTF-16 spans into original strings. Mutation no longer reconstructs whole documents from normalized split/join text.

### Hunk application
applyHunk() is the single mutation primitive for Accept/Undo and merge.

For same-cardinality modifications it replaces line content only and preserves target separators, including internal CRLF/LF separators. Structural add/delete hunks use exact boundary spans.

The helper fails closed when expected source content no longer matches.

### View adapter
markdown_visual_shell.js::actionHunk no longer owns a second normalization/split/join mutation path. It recomputes the canonical hunk from current saved/real text and delegates forward/reverse application to the diff engine while preserving existing CAS/version checks.

This satisfies FR04's single-owner requirement.

### Merge3
merge3 now computes exact hunks against the exact base and applies non-conflicting hunks through the same applyHunk contract in descending source order.

Fresh contract tests cover:
- non-overlap
- identical edit
- overlapping conflict
- add/add same boundary
- delete/modify collision
- beginning/end insertion/deletion
- trailing newline
- mixed CRLF/LF
- no-final-newline

No second merge implementation was introduced.

## Additional adversarial REVIEW probe
REVIEW also ran a small generated round-trip probe over structural single-hunk documents.

For documents using the same EOL spelling, every one-hunk forward/reverse case round-tripped exactly.

Cases differing only in EOL spelling intentionally produce no logical hunk; cases with globally normalized editor text preserve the target document's existing separators rather than reproducing the normalized draft byte-for-byte. This matches PLAN Turn 8's explicit design: logical comparison may be EOL-insensitive while mutation must preserve unchanged source spelling.

No defect is filed from this probe.

## CAS / collision safety
Fresh Edge evidence proves:
- stale external write prevents hunk corruption;
- same-line concurrent browser write cannot silently overwrite;
- partial Accept changes md_temp only;
- partial Undo changes intended real-file content only;
- mixed-EOL/no-final-newline raw bytes remain exact outside the intended operation.

CAS/file I/O stays in LiveMarkdownStore; the diff engine remains pure.

## UI/UX
The current hunk UI retains existing actions and semantics. T006 changes correctness of mutation, not presentation.

Known Source UX/performance defects remain outside this slice:
- current textarea Source still has full-backdrop rebuild;
- mixed-EOL direct typing characterization remains red;
- inline CodeMirror integration is not started.

No false claim that T006 fixes those issues.

## Performance / scalability
The engine grew materially, but complexity is confined to one existing canonical owner. No per-key editor integration changed, so MD-T000 rerun is not required for this slice.

Myers still has a bounded maxDistance fallback; exact-span decoration/application is linear in affected document representation. Final integrated large-file behavior remains MD-T017.

No performance regression was reproduced in the T006 paths tested.

## YAGNI / maintainability
Ponytail: Lean enough; no alternate diff service, CRDT/OT, rope, backend diff owner, or third-party merge dependency was added.

Although markdown_draft_diff.js increased from ~193 to ~364 lines, those lines replace duplicated mutation semantics and encode the exact-source contract in the existing owner. No reduction is recommended before Source integration.

## Mature alternatives
No upstream replacement is needed here. The task is source-fidelity semantics around existing Markdown/CAS behavior; replacing the diff engine with a new dependency would add uncertainty without solving a demonstrated gap.

## Preservation
Confirmed preserved:
- real .md source-of-truth
- md_temp accepted-snapshot semantics
- existing CAS owner
- no CodeMirror production dependency yet
- no watcher/event bus
- no Crop
- no Pi/native terminal
- no live :9999/:10099 mutation
- .pi/subagents.json
- known vendor status noise

## Remaining gates
Still incomplete:
- MD-T007 + MD-T017 Source integration/performance
- MD-T008–T018 remaining UI/fidelity/crop/acceptance chain
- native Japanese/Vietnamese IME integrated proof
- Spec 001 M-A11/M-A12
- Foundation Linux/manual/owner residual gates

No DONE claim.

## PLAN handoff
Accept MD-T006. The next dependency-correct product slice may begin MD-T007 + MD-T017 as one coherent Source integration/performance pair, preserving:
- CodeMirror normalized-position -> authoritative-source bridge
- exact source bytes / EOL metadata
- real .md truth + md_temp snapshot
- existing CAS owner
- canonical T006 diff engine
- no full-document persistence serialization per keypress
- bounded viewport diff DOM
- p95 <40 ms at 5,500 lines
- Undo/Redo, stale CAS and native IME acceptance requirements

Required route: PLAN.

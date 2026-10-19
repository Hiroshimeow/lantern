# DEV Turn 8 — report repair from recovered workspace evidence

## Scope

This report repairs only the missing Turn 8 role-report artifact. It does not replay substantive work or claim unrun verification.

Authoritative workspace: `E:\git-project\lantern`.

Current authoritative HEAD:
- `25e6c8cf0dff983fc4fbdb1bcc17ff7cdc7dd925`

Current `git status --short`:
- `?? .pi/` — preserved unrelated work.
- `?? tests/test_md_source_mapping.py` — uncommitted MD-T002 proof test created during Turn 8.

## Recovered MD-T002 RED evidence

The previously interrupted RED log is present at:

`.plan/lantern-markdown-main-20261018/dev_turn8_mapping_red.log`

Recovered result:
- 1 test ran in 5.028 s.
- Test result: **FAILED (errors=1)**.
- Failure is the intended TDD RED boundary:
  `Page.evaluate: Error: debugSourceMap mapping evidence API missing`.

This proves the new proof harness currently asks for a mapping-evidence API that production does not yet implement. No production mapping implementation was completed in Turn 8.

## Work completed before the disconnect

- Read PLAN Turn 6.
- Inspected the current Markdown mapping owner, including `buildVerifiedBlockMap`, `debugBlockMap`, and Visual editor ownership boundaries.
- Wrote `tests/test_md_source_mapping.py`.
- Started the required real-Edge/disposable-Lantern RED run.
- No production mapping implementation was applied before the disconnect.

## Exploratory findings prepared off-host only

These are design inputs, not authoritative acceptance evidence:

### Mapping
- decoded Markdown offsets must be identified explicitly as JavaScript UTF-16 code-unit offsets;
- raw file offsets must be identified explicitly as UTF-8 byte offsets;
- UTF-8 BOM contributes three raw bytes outside the decoded string;
- CRLF/mixed-EOL and alternate source spellings can make Milkdown serialization stale relative to authoritative source and must fail closed rather than guess;
- nested list/table/inline identity was not proven and must remain NO-GO until independently proven.

A narrow mapping-evidence design was drafted but not applied to authoritative G6 product source.

### CodeMirror 6 merge POC
A disposable ignored FJP POC was used only to validate the proposed MD-T003 harness:
- `@codemirror/merge@6.12.2`, MIT;
- observed npm integrity:
  `sha512-V8JvyAPjHbPupqP7BeMcsdsYCbyPij74jxIbaIJDORI+VZzW44zFmon8bF+oxGWvOKhcRmkiUMXd8MxHr3YA2w==`;
- `codemirror@6.0.2`;
- `esbuild@0.28.2`;
- installation remained under ignored `.plan`; no authoritative `package.json` or `package-lock.json` mutation was accepted.

Exploratory POC observations:
- unified merge exposes changed-line, changed-text, deleted-chunk and gutter primitives;
- split MergeView works but duplicates editor surfaces;
- Undo/Redo and selection behavior work;
- `originalDocChangeEffect` can update baseline without replacing current editor content;
- viewport rendering is virtualized in the exploratory run;
- exact BOM/mixed-EOL persistence still requires a raw-byte patch strategy rather than whole-document serialization;
- synthetic composition-event coverage is not native Windows IME acceptance.

Exploratory FJP performance is not binding because the required G6 run has not occurred and the FJP host was heavily loaded.

## Not completed / not claimed

Turn 8 remains incomplete. The following were not completed:

- MD-T002 production/debug mapping evidence implementation.
- MD-T002 GREEN matrix on authoritative G6.
- Markdown bundle rebuild/syntax verification after any mapping change.
- Authoritative tracked MD-T003 POC harness on G6.
- Authoritative G6 MD-T003 performance run.
- MD-T000/MD-T001 regression reruns after Turn 8 changes.
- Full test suite/build/diff/package-lock hygiene for the completed Turn 8 slice.
- Accepted Turn 8 commit.

No REVIEW-ready or TEST-ready implementation completion is claimed.

## Current prerequisite state

The transient G6 disconnect has cleared: device `desktop-b5e4iue-87cea2af` is online again. Therefore this is **not** a PAUSE condition.

## Route

**DEV** — resume the same Turn 8 slice from the recovered RED state. Preserve `.pi/` and the uncommitted `tests/test_md_source_mapping.py`; do not reset/stash/clean or replay already completed exploratory work. Complete MD-T002 and MD-T003 exactly under PLAN Turn 6, then route to independent REVIEW.

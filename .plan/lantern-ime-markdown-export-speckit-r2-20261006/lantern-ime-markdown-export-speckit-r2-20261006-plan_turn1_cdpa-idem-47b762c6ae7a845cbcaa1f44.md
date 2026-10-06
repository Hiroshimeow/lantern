# PLAN Turn 1 Report

Task: lantern-ime-markdown-export-speckit-r2-20261006
Workspace: C:\Users\DuongNH66\Desktop\git\lantern
Role: PLAN
Turn: 1
Baseline: main at 5ba0ed9c0a29332a219531787d4ee9f6b6c92c45

## Route decision

Route: DEV

Reason: repository truth and implementation contract are sufficiently defined, but the requested terminal IME fix, Markdown enhancements, Mermaid asset/helper, PNG export, PDF print export, and their acceptance evidence do not yet exist. DONE is not legal because acceptance is not satisfied. TEST is premature because implementation is incomplete.

## Verified repository truth

- Initial repository state was clean on branch main at 5ba0ed9c0a29332a219531787d4ee9f6b6c92c45.
- Windows terminal ownership:
  - static/terminal_scm.js opens xterm, installs attachCustomKeyEventHandler, forwards term.onData as terminal_input, and owns browser focus/resize/replay guards.
  - static/vendor/xterm.js registers keydown/keypress/composition/input handlers. Its CompositionHelper has keyCode 229 handling plus deferred textarea-diff behavior.
  - lantern_ws.py forwards terminal_input unchanged and protects reconnect snapshot + peer registration under terminal.lock; TCP_NODELAY is enabled.
  - lantern_terminal.py TerminalManager.input writes data unchanged to the PTY; Windows defaults to pywinpty ConPTY.
- Browser refresh/reconnect survival is in-process TerminalManager + WebSocket snapshot/replay behavior.
- Lantern-process restart persistence is separable and explicitly excluded: lan_drive.py creates an in-memory TerminalManager in main() and calls kill_all() on shutdown.
- Markdown ownership is plugin.py:
  - _render_markdown is a lightweight parser.
  - _md_inline escapes source before formatting.
  - _safe_href blocks javascript:, data:, and vbscript: schemes.
  - render_preview_page builds the preview shell.
- lan_drive.py already serves local /static assets and confines preview targets under CONFIG.root via safe_join.

## Root-cause hypothesis

The reported UniKey/Telex corruption belongs at the browser/xterm input boundary, not the WebSocket or PTY transport.

Supporting evidence:
- Lantern passes xterm onData payloads through unchanged to the PTY.
- The vendored xterm implementation owns both direct keydown encoding and hidden-textarea composition/input handling, including a keyCode 229 deferred textarea-diff path.
- Current upstream xterm issue reports in 2026 describe dropped/duplicated/reordered input around keyCode 229 and textarea processing.
- The exact start -> stsar UniKey event trace was not reproduced during PLAN, so that trace is NOT_MEASURED. DEV must reproduce once on Windows Chromium + UniKey and bind the narrow predicate to the observed sequence.

The plan forbids a general printable-key keydown forwarder because it would bypass or duplicate IME/composition, AltGr/dead-key and browser text behavior.

## Durable outputs created

Only the requested feature docs were created:
- specs/001-terminal-ime-markdown-export/spec.md
- specs/001-terminal-ime-markdown-export/plan.md
- specs/001-terminal-ime-markdown-export/tasks.md

No implementation file, vendor asset, requirements file, commit, or push was changed/performed.

## Scope contract

PRESERVE:
- xterm -> WebSocket -> TerminalManager -> ConPTY architecture.
- Existing terminal latency, reconnect/replay, resize, focus, mobile keys, copy/paste and control-key semantics.
- Raw-HTML escaping, preview size limits, safe_join confinement, local static serving and dependency-light plugin model.

FIX:
- Narrow process-key/IME text ownership in static/terminal_scm.js so committed text is emitted exactly once.
- Markdown preview quality: fence info, tables, task items, images and useful relative resource behavior.

ADD:
- Local vendored Mermaid 11.17.2 during DEV.
- static/markdown_preview.js for strict local Mermaid render, independent diagram failure isolation, per-diagram PNG export and window.print PDF export.
- Focused test_plugin.py plus terminal input regression cases.

Non-goal:
- Terminal persistence across Lantern process restart; separate future feature.

## Dependency decision

- Pin Mermaid 11.17.2. Mermaid 12 is a fresh breaking line with ES2024/Safari 17.4+ and default layout/appearance changes not needed here.
- Do not upgrade xterm as part of this increment; related IME issues still exist upstream, so an upgrade would widen the regression surface without removing the need for a browser-boundary fix.
- No new Python/runtime package is planned.

## Acceptance/testing contract

Terminal acceptance covers:
- repeated UniKey/Telex ASCII start correctness;
- Vietnamese Telex phrase;
- Japanese, Chinese and Korean IME;
- AltGr, dead key, emoji;
- multiline/Unicode paste;
- Ctrl+C selection/no-selection, paste, navigation/control keys;
- browser refresh and reconnect survival;
- no new input debounce or latency path.

Markdown acceptance covers:
- existing syntax and raw-HTML safety;
- tables/tasks/images/fence language;
- relative links/images;
- local/offline Mermaid flowchart, sequence, class, state, ER, Gantt and pie;
- malformed diagram isolation;
- per-diagram PNG;
- browser-native Save as PDF with selectable text and SVG/vector preservation where supported;
- no CDN/network dependency and no Python dependency growth.

## Evidence state

PASS:
- Baseline Python 3.12 unittest suite: 24 tests in 10.714s, OK.
- Baseline static/terminal_scm.js syntax under Node 24.14.1.
- Planning docs non-empty.
- Planning docs contain no TBD/TODO/PLACEHOLDER markers.
- git diff --check is clean.

NOT_MEASURED / INCOMPLETE:
- Exact UniKey event trace and real start -> stsar reproduction in PLAN.
- New terminal IME behavior.
- New Markdown/Mermaid/export behavior.
- Manual Windows IME matrix.
- Offline browser Mermaid/PNG/PDF acceptance.

## DEV execution order

1. Add failing terminal browser-event tests in test_terminal_ui.py.
2. Reproduce UniKey event ordering once and implement only the narrow static/terminal_scm.js input ownership state.
3. Run terminal automated + manual matrix.
4. Add failing Markdown/parser/page tests in new test_plugin.py.
5. Extend plugin.py without framework rewrite.
6. Vendor Mermaid 11.17.2 + license and add static/markdown_preview.js.
7. Run offline browser Mermaid/PNG/PDF acceptance.
8. Run full unittest, node syntax and git diff checks.

## Final repository state for this turn

Expected working tree changes are planning artifacts only:
- untracked specs/001-terminal-ime-markdown-export/
- this .plan report

No implementation or vendor files were modified.

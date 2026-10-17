# Verified upstream techniques — research notes (2026-10-17)
**Mục đích:** Tách sự thật từ tài liệu upstream khỏi các đề xuất Sonnet CHƯA được test trên FJP. Không cài package hoặc mã mới.

## Pi TUI versus RPC
- Pi official RPC Extension UI docs: https://pi.dev/docs/latest/rpc-extension-ui — `custom()` returns undefined, terminal input hooks/no-op, custom headers/editor components unsupported, editor state degraded in RPC. Therefore full Pi extension TUI parity cannot be guaranteed by the current Lantern HTML transcript + RPC. Native interactive TUI is the correct reference.
- Pi TUI official docs: https://pi.dev/docs/latest/tui — `@earendil-works/pi-tui` is Pi native TUI component system. Do not fork/reimplement it; reuse interactive Pi process.
- Pi FJP `pi --help` confirms CLI options session-id/session-dir/session, tui-mode, tools/models/extensions; **semantics of existing ID/resume/collisions still require proof P3**.

## Terminal reconnect mature reference
- xterm.js official README: https://github.com/xtermjs/xterm.js — `@xterm/addon-serialize` serializes screen buffer to VT sequences/HTML and `@xterm/headless` is explicitly recommended as a use case for preserving terminal state and restoring it after reconnect.
- Xterm maintainers say serialize preserves **most** state, not promise exact parity: https://github.com/xtermjs/xterm.js/discussions/4467. Same columns/rows may be required during restoring to prevent artifacts. Historical issue https://github.com/xtermjs/xterm.js/issues/3364 reported cursor visibility omission; confirm selected upstream version's status, not assume resolved.
- Therefore P2 starts by measuring Lantern's existing buffered replay against screen/cursor/mode/scrollback. If it fails, evaluate the official headless+serialize technique, never a newly written ANSI parser.

## Source inline diff reference
- CodeMirror official reference: https://codemirror.net/docs/ref/#merge.unifiedMergeView documents `unifiedMergeView({original})` that highlights changed sections and shows original text as noneditable widgets.
- NOTE: Round 2 Sonnet mentioned an "archived repo" as a potential objection, but **archive status of a historical GitHub sub-repo does not establish that the current CodeMirror 6 package is unsupported**. The official package reference is live; verify actual package maintenance and version compatibility in implementation research, and run EOL/BOM/IME probes.
- Source canonical raw bytes with BOM, EOL and no-trailing-newline must remain in the document store, not blindly delegated to a code editor's string model.

## ProseMirror view diff
- Official ProseMirror documentation: https://github.com/ProseMirror/website/blob/master/markdown/guide/view.md — node/inline/widget Decorations grouped in DecorationSet. They affect view output and do not become actual document content. Correct positioning still requires mapping proof through Milkdown to source offsets.
- Existing Milkdown features already reuse DecorationSet and have `mountImageCrop()`, but this is not evidence of correct source-vs-visual mapping for duplicate nodes.

## Crop image
- Existing FJP CropperJS v2 is in `tools/image_crop_entry.js` and Milkdown's `mountImageCrop` in `tools/visual_markdown_entry.js`. Gaps are Preview crop, additional references/formats, exact URL patch and transaction/revision safety.
- Do not create an alternative canvas/crop engine or reduce format support silently. For animated GIF, do not flatten frames; design decision required.

## Downstream experiments required (NOT YET RUN)
P1: source preserving Visual edits and exact Preview image reference spans (Milkdown/remark/CM6).
P2: xterm buffer/serialize/headless snapshot under ConPTY native Pi incl IME, mouse, paste, alternate screen.
P3: Pi `--session-id` / `--session-dir` semantics with identical/different contexts and concurrent attempts.

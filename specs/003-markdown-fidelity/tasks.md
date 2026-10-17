# Tasks: Markdown Fidelity (DRAFT / KHÔNG THỰC HIỆN)
Spec: specs/003-markdown-fidelity/spec.md. Phụ thuộc nền tảng 002 gate F-T011. Mỗi task: test đỏ trên lỗi thực tế → sửa vào đúng owner → test xanh → review → commit. Không chỉnh test để ẩn hồi quy.

## Phase 0 — Proof-first, blocking
- [ ] **MD-T001 [MD-FR07] Characterize exact bytes.** Tạo `tests/fixtures/md-fidelity/` với BOM/CRLF/mixed EOL/no newline, 30-col, nested lists, code fences, HTML/comments/frontmatter, CJK, repeated paragraphs/tables. `tests/test_markdown_roundtrip_corpus.py` kiểm byte gốc và span hash trên editor no-op, one-block edit. PASS iff unchanged spans byte-identical.
- [ ] **MD-T002 [MD-FR06] Prove source-range mapping.** So sánh Milkdown parser + remark mdast ranges ↔ ProseMirror nodes; duplicate nodes, repeated headings, table cells, source markup aliases. Test `tests/test_md_source_mapping.py` pass/detect unmapped, không 'gần đúng'. GO/NO-GO for dirty-segment design.
- [ ] **MD-T003 [MD-FR05] Source editor merge spike.** Đánh giá CodeMirror 6 MergeView/unified hoặc kỹ thuật upstream tương đương trong environment thử, tests `tests/test_md_source_merge_e2e.py`: hunk inline/gutter, CRLF, CJK IME, deletion widget, 500KB, no formatting mutation. Chưa cài package cho tới khi duyệt. Nếu FAIL phải báo design decision.

## Phase 1 — Shared document data
- [ ] **MD-T004 [MD-FR01/02] .md/md_temp write + accept semantics.** `lantern/live_markdown.py`, `tests/test_live_markdown.py`, `tests/test_working_copy_http.py`. Verify file write immediately and md_temp immutable until Accept, Ctrl+Z after Accept new diff, CAS stale prevents silent overwrite.
- [ ] **MD-T005 [MD-FR03] External file change + echo.** `lantern/markdown_observer.py` chỉ nếu đã duyệt và cần thiết, `tests/test_live_markdown_e2e.py`: VS Code external write, same-path two tabs, watcher does not re-trigger on Lantern write, file delete/rename/large file. Không kéo observer Pi vào module này.
- [ ] **MD-T006 [MD-FR04] One diff engine.** `lantern/md_diff.py` hoặc JS equivalent được chọn sau T001-3, tests `tests/test_md_diff_contract.py`: hunks preserve byte/EOL, consistent revision, edits on different lines, accept/undo partial CAS and no corruption on collision.

## Phase 2 — Source, Visual, Preview independent UI
- [ ] **MD-T007 [MD-FR05] Source inline diff.** `static/markdown_visual_shell.js` + `static/markdown_source_editor.js` (nếu CodeMirror POC đạt) + CSS; E2E `tests/test_md_mode_switch_e2e.py` (change/add/delete same line and bottom, Ctrl+S, gutter, keyboard selection). Drop bottom-only row counter UI.
- [ ] **MD-T008 [MD-FR05/06] Milkdown decorations proof.** `tools/visual_markdown_entry.js`; tests `tests/test_md_visual_e2e.py`: DecorationSet mapped/ghost, repeated text, code/list/table, undo/focus/IME, not serialized into Markdown, fail-visible when unmapped.
- [ ] **MD-T009 [MD-FR07] Exact Visual write strategy.** Choose only after MD-T001/T002 proof: precise dirty-segment original-byte patch; if impossible, preserve source document and route unsafe edits into exact Source mode with explicit warning. E2E test external VS Code + Visual + 30 columns; no untouched byte changes.
- [ ] **MD-T010 [MD-FR04] Preview consistent hunks.** `plugin.py`, `static/markdown_visual_shell.js`, tests `tests/test_md_visual_e2e.py` / `tests/test_plugin.py`. No guessed block position, ghost not part of selectable/editable file content.
- [ ] **MD-T011 [MD-FR11] Scroll/anchor/layout/paged.** `static/markdown_anchor_bridge.js`, `static/markdown_paged_editor.js`, `static/markdown_visual_shell.css`; tests `tests/test_md_paged_e2e.py`, `tests/test_visual_feature_e2e.py` (flash 500ms, viewport 390/1080px, table resize, hunk actions not obscuring edits).

## Phase 3 — Embedded image Crop
- [ ] **MD-T012 [MD-FR08/09] Shared Crop client contract.** Reuse `tools/image_crop_entry.js` and `tools/visual_markdown_entry.js::mountImageCrop`; build `tests/test_md_embedded_crop_e2e.py` with exact node ref, abort mid-dialog, format/pixel test; do not fork Crop engine.
- [ ] **MD-T013 [MD-FR08] Preview exact image-source targeting.** `plugin.py` parser/image anchors + preview adapter, test duplicate identical images and code fenced '![]()', reference-style, URL-encoded spaces, Unicode and ../ path; if mapping ambiguous, disallow Save-copy and preserve document.
- [ ] **MD-T014 [MD-FR08/09] Save-copy & Overwrite lifecycle.** Crop asset CAS+doc token-range CAS, append file and patch ref only when both valid; on race show independent orphan cleanup/recovery; tests `tests/test_md_embedded_crop_e2e.py`, `tests/test_crop_shared_e2e.py` include multiple docs referring same file, 409/423, EXIF, GIF animation refusal.

## Phase 4 — Acceptance & release
- [ ] **MD-T015 [MD-SC01–06] Full regression and performance.** Run `tests/test_md_mode_switch_e2e.py`, `tests/test_md_visual_e2e.py`, `tests/test_live_markdown_e2e.py`, `tests/test_md_paged_e2e.py`, `tests/test_crop_shared_e2e.py`, `tests/test_visual_feature_e2e.py`; Edge live on FJP; benchmark 1KB/100KB/500KB; compare baseline.
- [ ] **MD-T016 [MD-SC01–06] Independent review / rebase main / FF merge.** Reviewer kiểm corpus byte hash, area crop, CRLF, serializer, visual/preview/source parity; approve before merge/push. Không kéo code Pi sang branch MD.

### Dependencies / Parallel
T001–T003 proof gates → T004–T006 → T007–T011 (can parallel by owned frontend files after contract fixed) → T012–T014 → T015/T016.
T012/T013 adapter work độc lập với T007/T008 nếu không cùng chỉnh shared frontend shell.

### Bắt buộc dừng
Sai ByteSpan/PM mapping; tài liệu mất byte; crop ghi sai ảnh; phản hồi stale bị ghi đè; thử nghiệm upstream không đủ bằng chứng; chưa được chủ sở hữu duyệt.

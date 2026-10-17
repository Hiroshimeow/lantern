# Research — Markdown/Preview/Edit/Source/Crop (read-only)
## Existing implementations to REUSE
- `lantern/live_markdown.py`: raw file/snapshot boundary with CAS `get/write/save/accept_partial/discard`. Existing contract must be retested for BOM, CRLF/mixed EOL; text-mode normalization is NOT assumed safe.
- `tools/visual_markdown_entry.js`: Milkdown/Crepe, ProseMirror DecorationSet via current diff plugin, image crop selection UI `mountImageCrop()` already exists; currently filters same-origin png/jpeg/webp/bmp, uploads cropped copy and changes exactly selected PM image node when `node.eq` still holds. Do not rebuild it.
- `tools/image_crop_entry.js`: CropperJS v2, canvas/selection, transform/clamp and blob output. Reuse from standalone and Markdown.
- `plugin.py`: Preview Markdown renders inline images but the user-facing Preview has not been shown to expose the same crop controls. Source range of referenced image must be proven, not selected by identical URL/Nth occurrence.
- `static/markdown_visual_shell.js`: hunk actions, source-diff backdrop plus deletion list, Preview/Visual decorations; user still reports Source/Visual fidelity issues. Existing tests passed in earlier session but not every real-world case.
- `static/markdown_paged_editor.js`: large-file path; must obey original .md + md_temp contract.

## Mature upstream
- ProseMirror view decorations/DecorationSet widgets/inline: https://github.com/ProseMirror/website/blob/master/markdown/guide/view.md
- Milkdown Crepe feature model: https://milkdown.dev/docs/api/crepe
- CropperJS 2 image transform/change (cancelable): https://github.com/fengyuanchen/cropperjs/blob/main/docs/api/cropper-image.md
- CodeMirror 6 merge/unified diff: investigate against installed version/actual package docs before choosing; EOL-sensitive behavior NOT YET VERIFIED.
- remark/mdast source offsets and parser GFM: research only; exact source spans through PM nodes NOT YET VERIFIED.
- Sonnet Round 2: raw bytes canonical, possible dirty-segment patches only AFTER measurable E1–E4. Do not treat reserialization of a full document as acceptable without evidence.

## Counterexamples / implementation proof gates
1. Different Markdown source but identical rendered doc (CRLF, table spacing, escapes, fenced code markup): ProseMirror parsed-doc diff cannot be canonical.
2. Duplicate paragraphs/images: searching by text or ordinal may highlight/rewrite wrong node.
3. BOM/no-final-newline/mixed EOL: Python newline translation and CM6 document transforms can modify bytes.
4. Animated GIF: non-frame-aware Cropper export silently flattens animation; should refuse or require separately approved per-frame processing.
5. Image URL relative ../, spaces, Unicode/% escapes/reference definitions/raw HTML: source token identity required.
6. Concurrent asset/document edits: two-file save-copy is not atomic by filesystem default; explicit rollback/recovery strategy required.
7. Milkdown visual may normalize entire document on every keystroke. Dirty-span patch is a candidate but its correctness must be established before implementation.

## Status taxonomy
Existing but unverified: Crop in Milkdown Edit, PM decoration, LiveMarkdownStore CAS, Source diff backdrop. Reported gap: Preview Crop parity, Visual precise inline diff, Source inline hunk representation, scroll/anchor. Proof pending: large corpus, byte preservation, mapping, mixed EOL, GIF/EXIF.

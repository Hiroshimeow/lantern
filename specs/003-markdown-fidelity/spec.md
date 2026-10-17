# Feature Specification: Markdown Fidelity / Preview–Edit–Source / Crop
**Ngày:** 2026-10-17 | **Nhánh triển khai:** main | **Trạng thái:** DRAFT / CHỜ DUYỆT
**Base:** kiến trúc nền tảng 002 đã được nghiệm thu, không triển khai trước.
**Nguồn dữ liệu:** file .md gốc; md_temp chỉ là snapshot được người dùng chấp nhận.

## User Stories & Acceptance
### MD-US1 / P1 — Sửa đồng thời bằng Lantern, LanternBot và VS Code
- AC1: gõ trong Source hoặc Edit làm file .md gốc đổi đúng nội dung ngay khi đồng bộ; không phải chờ Ctrl+S mới ra đĩa.
- AC2: md_temp không đổi cho đến khi Ctrl+S; Ctrl+S sao chép phiên bản .md gốc hiện tại vào md_temp và xóa diff; vẫn sửa tiếp được.
- AC3: Ctrl+Z sau Ctrl+S là thao tác edit tiếp trên file gốc; diff trở lại. F5 giữ snapshot/nhật ký so sánh, không tự chấp nhận.
- AC4: VS Code sửa file gốc khi Lantern mở -> Lantern quan sát thay đổi, diff cộng dồn trong .md so với md_temp; không khóa editor vô lý, cũng không ghi đè phiên bản mới bởi nội dung tab cũ.
- AC5: 2 tab cùng sửa một file: thao tác stale bị phát hiện từ phiên bản/hash và giữ draft để người dùng xử lý; không silently overwrite.

### MD-US2 / P1 — Diff trực quan đúng ở cả ba chế độ
- AC1: Preview: thêm màu xanh, sửa màu vàng, xóa ghost mờ đỏ gạch ngang; không có nhãn giải thích thừa.
- AC2: Edit Milkdown: decoration ở đúng nội dung/cell/block, độc lập dữ liệu Markdown; nút Accept/Undo không che hình/bảng và không vô tình đổi vị trí lựa chọn; mapping không chứng minh được thì hiện trạng thái 'chưa ánh xạ được' thay vì highlight sai.
- AC3: Source: tô diff tại đúng dòng/gutter trong editor, bao gồm đoạn xóa và hunk controls; KHÔNG chỉ có danh sách row/hunk ở bên dưới.
- AC4: bấm Accept của hunk cập nhật md_temp ở đúng hunk, Undo cập nhật .md gốc ở đúng hunk bằng CAS; các hunk khác giữ nguyên. Thất bại giao dịch không làm mất diff.
- AC5: mode Preview ↔ Edit ↔ Source giữ scroll và selection/anchor chính xác, khi từ Preview chuyển Edit sáng vị trí liên quan trong 500 ms; với duplicate text không nhảy sai.

### MD-US3 / P1 — Không làm hỏng định dạng Markdown người dùng
- AC1: sửa một đoạn bằng Milkdown không tái định dạng hay thay byte các đoạn còn lại (CRLF, bảng 30 cột, list, dấu cách, comments/frontmatter, code fences, Unicode/CJK).
- AC2: ảnh URL, link và thuộc tính alt/title được giữ khi không sửa ảnh.
- AC3: đối với cú pháp mà Visual không thể round-trip giữ nguyên, KHÔNG ghi toàn tài liệu bằng serializer rồi tự coi là đúng; báo hạn chế/fallback chính xác, không mất sửa.
- AC4: tài liệu trên ngưỡng paged-editor, duplicate headings/paragraphs, bảng rộng, Mermaid, paste ảnh không degrade.

### MD-US4 / P1 — Crop ảnh nhúng trong Markdown
- AC1: ảnh nhúng nằm trong file Markdown có thể Crop từ Preview và Edit; không cần mở File Manager; crop UI/encoder dùng chung với CropperJS 2 hiện tại.
- AC2: khi mở Crop, khung phủ trọn ảnh thực; kéo/resize/zoom không vượt biên ảnh, tính đúng EXIF rotation, CSS scale và devicePixelRatio.
- AC3: lựa chọn 'Save cropped copy' tạo asset mới và thay chính xác tham chiếu ảnh được chọn (không dùng Nth occurrence); 'Overwrite original' chỉ có khi có quyền sửa được tài nguyên, ảnh không đổi từ lúc mở và người dùng xác nhận.
- AC4: đường dẫn ảnh ./, ../ (trong root), assets/, tên Unicode/space/%-encoding được phân giải nhất quán; link relative giữ đúng khi viết lại.
- AC5: từ Preview nếu tài liệu có duplicate ảnh, xác định duy nhất vị trí tham chiếu được click; không chắc chắn thì không sửa Markdown.
- AC6: đối với ảnh được nhiều Markdown khác cùng tham chiếu, Overwrite cảnh báo tác động; GIF animation không được tự biến thành ảnh tĩnh; ảnh remote/read-only/ngoài root thông báo rõ tính năng bị giới hạn.
- AC7: Crop lỗi/huỷ không tạo asset mồ côi hay sửa document; ảnh ngoài vẫn tồn tại nguyên vẹn khi Delete reference.

### MD-US5 / P2 — Giao diện nhất quán
- AC1: Preview/Edit/Source căn về trái, tận dụng chiều rộng hợp lý khi panel chat mở; không còn khoảng trống trái gây vùng tài liệu bị bot che.
- AC2: bảng dài/rộng thao tác thêm/xóa và resize đúng cột cuối, mobile viewport 390px không mất nút; diff action không phủ ô.
- AC3: popup và badge chọn vị trí khi đổi mode có thể nhìn trong 0.5 s, không gây nhảy lên đầu trang.

## UX/performance acceptance — bổ sung từ đối chứng 2026-10-17
- **Nguồn:** [SOURCE_UX_PERFORMANCE_AUDIT_2026-10-17.md](SOURCE_UX_PERFORMANCE_AUDIT_2026-10-17.md). A/B Edge chứng minh Source lag đã tồn tại trước refactor, không phải hồi quy nền tảng 002.
- **MD-US6 / P1 — Gõ Source mượt, không “reload giả”.** Với 5.500 dòng, p95 thao tác gõ < 40 ms, không dựng lại toàn bộ dòng trong backdrop mỗi phím; không navigation/nhảy caret/focus. POC CodeMirror 6 trưởng thành bắt buộc trước quyết định kỹ thuật. Với 500 KB và 5 MB, chỉ chốt ngưỡng sau POC và không kém reference đã duyệt.
- **MD-FR13:** diff Source trình bày bằng editor/decorations theo vùng nhìn thấy và hunks liên quan; không làm diff toàn văn bản + tái tạo DOM vô điều kiện khi gõ. ACK từ lần ghi của chính mình không gây vòng render thứ hai nếu revision không thay đổi.
- **MD-FR14:** giữ write-through vào file .md sau debounce ngắn, md_temp chỉ cập nhật bằng Accept/Save. Không loại bỏ hunk/đổi semantics để tăng tốc. Phải giữ keyboard input, Undo/Redo, IME tiếng Nhật/Việt, clipboard, VS Code concurrency và Preview/Edit.
- **MD-SC07:** kiểm trên Edge với 900 / 5.500 dòng + 500 KB / 5 MB; ghi input→paint, p95 key wall time, DOM nodes, số navigation, file writes và checksum. Baseline/bản mới chạy cùng fixture; không diễn giải 1 lượt đo là chứng minh thống kê tổng quát.

## Functional Requirements
- MD-FR01: Dữ liệu bản gốc trên đĩa là nguồn sửa và so sánh; md_temp immutable giữa hai lần Accept/Save.
- MD-FR02: Ghi dùng CAS revision; phản hồi stale bảo tồn dữ liệu người dùng và nêu đúng nguồn xung đột.
- MD-FR03: Có cơ chế quan sát thay đổi ngoài Lantern và bỏ qua echo từ ghi của Lantern; ghi từ Pi qua file-system vẫn được quan sát.
- MD-FR04: Diff engine trả hunks độc lập editor; View adapters chỉ render; không lưu hai nguồn trạng thái cạnh tranh.
- MD-FR05: Visual uses ProseMirror DecorationSet/plugin; Source uses proven line-diff editor mechanics, không đếm row thủ công. Không serialize decoration.
- MD-FR06: Hợp đồng mapping source↔visual phải có bằng chứng deterministic; mapping fail-visible thay vì đoán; thumbnail/image identity qua node và revision.
- MD-FR07: Không tái tuần tự hóa byte nguyên bản ngoài vùng sửa; nghiên cứu+test chứng minh trước khi chọn Milkdown write strategy, không được giảm độ trung thực để né chi phí.
- MD-FR08: Crop service nhận image identity, target asset revision, crop geometry theo pixel gốc, chế độ Save As/Overwrite, callback sửa reference; không phụ thuộc riêng File Manager hay Milkdown.
- MD-FR09: Xử lý định dạng ảnh và asset references nhất quán giữa standalone/Preview/Edit, bao gồm trường hợp không hỗ trợ được phản hồi đúng.
- MD-FR10: Paged editor và Editor/Source đều dùng file revision+snapshot contract; không khoá bot chỉ vì Edit đang mở.
- MD-FR11: Giữ vị trí, bảng, scroll, anchor, focus/IME/clipboard đã có.
- MD-FR12: Không thêm subsystem security trong giai đoạn này.

## Tình trạng hiện có cần phân biệt
- ĐÃ CÓ mã: LiveMarkdownStore CAS/md_temp, Milkdown ProseMirror plugin diff, Source backdrop + danh sách deletions, CropperJS standalone; Milkdown Edit đã có `mountImageCrop` chọn inline image rồi upload copy/đổi node.
- NGƯỜI DÙNG VẪN BÁO LỖI: crop ảnh nhúng không có UX đủ (đặc biệt Preview), diff trực quan Edit và Source chưa đúng, mapping chính xác, bảng rộng, bố cục/anchor.
- CHƯA CHỨNG MINH: giữ byte gốc khi Milkdown serializes toàn tài liệu; các tình huống CJK, CRLF, frontmatter, code fences, duplicate nodes; crop GIF animation/EXIF/multi references.
- Không ghi 'chưa triển khai' cho tính năng đã có mã; phải tái hiện lỗi cụ thể bằng test.

## Edge Cases
- File bị đổi hoặc bị xóa sau khi mở Crop/Save; hai tab crop cùng asset; asset upload hoàn tất nhưng chỉnh node thất bại.
- Markdown nguồn có HTML, comments, raw MD custom, non-UTF8 hoặc UTF-8 BOM; text mixed EOL.
- Tập ảnh liên kết chéo; URL escaped parentheses; GIF nhiều frame; EXIF orientation; icon zoom/resize trên Retina.
- Một hunk bao gồm bảng, list nested, code block, hai đoạn trùng nhau, dòng trống cuối.
- Editor scroll nhanh qua 500KB; F5 giữa Save; tab B thay file trong lúc tab A đang đổi mode.

## Success Criteria
- MD-SC01: 100% contract tests write-through/Accept/Undo/external/multi-tab PASS trên Windows/Edge.
- MD-SC02: Bộ corpus byte preservation có hash theo vùng; 0 byte bị sửa bên ngoài vùng thao tác được xác nhận. Nếu editor không đáp ứng, không merge feature đó.
- MD-SC03: 0 ánh xạ nhầm trên bộ thử duplicate text, list/table/code, CJK, 30-col; các hunk không map được được hiển thị trung thực.
- MD-SC04: Crop synthetic quadrant pixel test + relative-path/reference-rewrite + stale asset/passive watcher PASS; GIF không mất animation ngầm.
- MD-SC05: End-to-end Source/Preview/Edit navigation, anchor flash 500ms, layout with chat, mobile 390px PASS.
- MD-SC06: Thời gian mở/edit/save tài liệu lớn được benchmark vs baseline, không degrade vô cớ.

## Ngoài phạm vi
Không thay Pi TUI runtime, không triển khai bảo mật LAN, không thay parser/render engine chỉ vì 'ít code hơn'. Việc thay Milkdown hoặc dùng một parser/merge khác phải dựa vào POC parity và phê duyệt thiết kế.

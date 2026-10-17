# Hiến chương Lantern (dự thảo để duyệt)
Ngày: 2026-10-17. Áp dụng cho nền tảng, Markdown, Pi TUI. KHÔNG cho phép triển khai sản phẩm trước khi chủ sở hữu duyệt.

## Thứ tự ưu tiên bất biến
1. Hành vi đúng, tiêu chí nghiệm thu khách quan.
2. Tham khảo kỹ thuật và thư viện upstream trưởng thành.
3. Tương đương chức năng sản phẩm tham chiếu.
4. Độ ổn định, độ trễ, UX, hiệu năng, bảo trì.
5. Tái sử dụng kỹ thuật đã chứng minh.
6. Đơn giản hóa sau khi đạt 1–5.
7. Công triển khai, token, thời gian thấp nhất.

## Quy tắc kiến trúc
- Localhost-first. Dành điểm mở rộng cho chính sách LAN nhưng KHÔNG triển khai bảo mật/phân quyền mới trước phê duyệt riêng.
- Một chủ sở hữu cho mỗi trạng thái: file .md gốc là dữ liệu đang làm việc, md_temp là snapshot đối chiếu; Pi quản lý lịch sử hội thoại; terminal quản lý PTY; composition root quản lý vòng đời dịch vụ.
- Chia module theo trách nhiệm và lý do thay đổi, không chia máy móc theo số dòng, không tạo service locator chứa mọi thứ.
- Sau chuyển đổi chính thức, duy nhất main.py là entrypoint. Không giữ lan_drive.py, wrapper/alias/shim tương thích, server song song hay trạng thái trùng lặp.
- Không giả vị trí dòng, node hay hình ảnh khi không chứng minh được; fail-visible và bảo toàn dữ liệu.
- Trước khi tự viết giải pháp, đọc upstream và đánh giá đầy đủ edge cases, các tính năng có thể suy giảm.
- Ưu tiên hành vi thực tế, test độc lập và benchmark. Không thay đổi oracle cùng lúc với refactor để tự chứng minh bản mới.
- Trước khi phát triển nhánh: fetch/rebase trên main đã sạch; trước merge: rebase, chạy đủ contract/E2E, review độc lập, fast-forward.
- Pi TUI nguyên bản, không xây trình dựng tin nhắn /commands/extension song song bằng HTML.
- Trợ lý bảo trì tự động là giai đoạn sau: chỉ dành hợp đồng sự kiện, không tự triển khai sửa ứng dụng.
- Mọi bản nháp legacy và WIP Git phải giữ nguyên cho tới khi người dùng chọn cách xử lý; không reset/stash/clean/xóa ngầm.

## Các gate nghiệm thu
G0: Phê duyệt spec, plan, tasks và quyết định mở.
G1: Characterization được ghi từ HEAD sạch fb06c40, bất biến và chạy lại trên bản refactor; parity HTTP/WS/file/terminal/Markdown.
G2: Không có import cycle, import-time process, module singleton chạy ngầm; dependency direction rõ; thử khởi động tắt/mở hai instance độc lập.
G3: .md, md_temp, Markdown Diff, Crop, tệp ngoài và hai client được nghiệm thu trên fixture độc lập.
G4: Pi native TUI và extension thật, nhiều phiên, reconnect/resize, Ctrl/IME/clipboard được đo trực tiếp.
G5: Benchmark không suy giảm đáng kể so với baseline hoặc thay đổi đó phải được giải thích và phê duyệt.
G6: FJP Edge Windows, Linux smoke, bàn giao sạch; không merge/push khi chưa được duyệt.

# LANTERN — FULL FEATURE & QA REGRESSION CHECKLIST

Thực hiện các kiểm tra trên máy chủ Lantern riêng với tệp mẫu có thể thay đổi. Ghi lại phiên bản Lantern, hệ điều hành, phiên bản trình duyệt và kết quả của mỗi nhóm. Xem [quy trình kiểm thử CDP](../checklists/UNIVERSAL_CDP_RULES.md) và [checklist nền tảng](../checklists/v8.2_baseline.md) để biết cách chạy và đối chiếu.

## PHẦN 1: MARKDOWN PREVIEW

- [ ] Mở cùng một tệp trong `Preview`, `Edit visually` và `Source`. Kiểm tra nội dung và vị trí tương ứng qua các lần chuyển chế độ.
- [ ] Trong `Preview`, chuột phải vào chữ hoặc ảnh để mở menu mặc định của trình duyệt. Trong `Edit visually`, chuột phải để mở `Source` tại dòng tương ứng.
- [ ] Sửa hai đoạn riêng biệt từ trình duyệt và Pi. Kiểm tra cả hai thay đổi cùng xuất hiện. Dùng bản mẫu CRLF để kiểm tra kiểu xuống dòng sau khi gộp.
- [ ] Kiểm tra chấp nhận và hoàn tác từng thay đổi, giữ đúng nội dung bản gốc, bản nháp người dùng và bản đã chấp nhận.

[Chức năng lõi](../checklists/v9.0_v9.21_core.md) · [Checklist Markdown v9.24](../checklists/v9.24_release.md)

## PHẦN 2: LANBOT CHATBOT

- [ ] Mở `#bot1` và `#bot2`, chọn Provider/Model khác nhau rồi chuyển tab trong khi một phản hồi đang chạy. Kiểm tra trạng thái mỗi tab và mở lại phiên đã lưu.
- [ ] Chạy subagent nền. Kiểm tra trạng thái chuyển từ đang chạy sang hoàn tất, các bước trước đó còn hiển thị và phần tóm tắt `[skill]` chỉ xuất hiện một dòng.
- [ ] Xuất hội thoại từ phiên đang mở rồi đối chiếu tên phiên và nội dung xuất với transcript.

[Checklist Lanbot v9.22](../checklists/v9.22_release.md) · [Cấu hình Lanbot](LANTERNBOT_CONFIG.md)

## PHẦN 3: FILE MANAGER

- [ ] Duyệt cây thư mục, tìm kiếm đệ quy, bật/tắt hiển thị tệp ẩn và đổi chế độ hiển thị. Kiểm tra mục đang chọn và thư mục đích sau khi dùng Back/Forward.
- [ ] Sửa nội dung thư mục từ bên ngoài khi danh sách đã tải nhiều trang. Làm mới và kiểm tra danh sách, vị trí cuộn và lựa chọn.
- [ ] Thử tải tệp nhỏ và tải theo từng khối, xung đột tên, hủy trước khi ghi tệp và hủy sau khi máy chủ đã ghi xong. Đối chiếu thông báo với tệp trên đĩa.
- [ ] Dùng Crop để lưu bản sao và ghi đè ảnh mẫu. Kiểm tra đường dẫn, kích thước, ảnh thu nhỏ và từ chối ghi đè khi ảnh đã đổi từ bên ngoài.

[Checklist Gallery và Explorer v9.25](../checklists/v9.25_release.md) · [Hướng dẫn Crop](IMAGE_CROP.md)

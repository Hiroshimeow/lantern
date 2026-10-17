# LanternBot — kiểm toán UX nghiêm khắc trước feature Native Pi

**Ngày:** 2026-10-17 · **Đầu vào:** ảnh chat do người dùng cung cấp (một vùng cắt nhỏ) + `static/chatbot.js`, `static/chatbot.css` tại `cbc9286` · **Phạm vi:** panel chat hiện tại; không coi đây là đánh giá mỹ thuật toàn bộ ứng dụng.

## Kết luận

Panel hiện tại là giao diện HTML tự dựng lại trạng thái Pi, chưa phải một harness/TUI hoàn chỉnh. Cách hiển thị gây phân tán mục tiêu chính: người dùng đang đọc/sửa tài liệu nhưng bot có thể chiếm một góc, tool log xuất hiện với độ ưu tiên thị giác tương đương câu trả lời, còn khu vực mã nguồn co lại. Đây là **nợ UX hiện có**, không phát sinh từ refactor 002: Git SHA của `static/chatbot.js` và `static/chatbot.css` trước/sau refactor trùng nhau.

Không nên đầu tư vá lịch sử chat HTML này nếu feature 004 sẽ chuyển sang Pi TUI bản địa. Chỉ sửa riêng nếu một lỗi mới của refactor được tái hiện bằng A/B.

## Quan sát được và giới hạn bằng chứng

- Trong ảnh, một lời nhắn `hi`, lời gọi tool `read` với đối số JSON và câu trả lời `Hi! How can I help you today?` hiển thị như ba thành phần gần ngang hàng; người dùng phải tự suy luận đâu là nội dung đối thoại, đâu là vết kỹ thuật. **Thứ tự trong ảnh là user → tool → assistant**, không được gọi đây là bằng chứng đảo thứ tự.
- `static/chatbot.css`: panel `position:fixed; width:min(440px,92vw)` chiếm vùng bên phải; `.content` được thêm padding bên phải. Ở màn hình hẹp panel biến thành tấm trượt chiếm tới 72% chiều cao.
- `static/chatbot.js`: `renderToolStart` tạo dòng tool chứa tên và JSON arguments, giới hạn 260 ký tự; `S.assistant = null` ép phản hồi kế tiếp nằm sau tool. Lịch sử UI được tự snapshot tới `sessionStorage` và phục hồi theo người dùng cuối cùng; đó không phải trạng thái TUI thực của Pi.
- Ảnh được cắt nhỏ, không thể xác nhận khả năng tiếp cận, kích thước toàn trang, keyboard navigation, tất cả tooltip, hoặc khả năng F5 bằng mắt. Các mục này là **yêu cầu cần thử**, không khẳng định là lỗi đã tái hiện.

## UX review theo Hallmark + nguyên tắc khả dụng

**Chấm riêng panel chat hiện tại** (1 yếu → 5 tốt; dựa trên CSS/JS và ảnh giới hạn):

| Tiêu chí | Điểm | Nhận định |
|---|---:|---|
| Triết lý sản phẩm | 3/5 | Bot nằm cạnh tài liệu đúng mục tiêu, nhưng lại tự mô phỏng Pi thay vì kế thừa hành vi Pi |
| Phân cấp thông tin | 2/5 | Transcript, tool log và trạng thái vận hành chưa có phân cấp rõ |
| Độ hoàn thiện | 2/5 | Chật đối với output terminal, bảng, picker; lịch sử UI có cơ chế snapshot song song |
| Đặc thù sản phẩm | 3/5 | Đã gắn path/kind nhưng thiếu nhấn mạnh quan hệ session↔tài liệu đối với người mới |
| Tiết chế | 2/5 | Việc đẩy đối số tool dạng JSON vào transcript gây nhiễu |
| Nhất quán | 2/5 | HTML bubble và terminal Pi có mô hình tương tác khác nhau; chuyển ngữ cảnh dễ đứt mạch |

Điểm số là **đánh giá thiết kế có phạm vi**, không phải kết quả nghiên cứu định lượng với người dùng.

## Vấn đề ưu tiên theo hành trình người dùng

| Mức | Hành trình | Mục tiêu UX |
|---|---|---|
| P0 | Đang sửa Source, mở bot hỏi/sửa tài liệu | Editor không bị che; vùng làm việc đủ rộng và con trỏ không đổi vị trí |
| P0 | Pi đang tool-call, F5 hoặc đổi tab rồi trở lại | Thấy đúng session/turn, không mất output/khởi động lại/sắp sai thứ tự |
| P1 | Dùng `/model`, `/goal`, skill và extension | Các lệnh/Pi custom TUI dùng được như ở terminal, không bị hạn chế do UI HTML |
| P1 | Xem kết quả lẫn nhiều tool call | Câu trả lời dễ đọc; trạng thái hiện tại dễ nhận; tool detail không lấn át nội dung chính |
| P1 | Tab A file A, tab B file B | Session A/B tách biệt, header/context dễ hiểu; không đổi kind/path khi tab kia nhận response |
| P2 | Người mới lần đầu | Hiểu cách mở/đóng/rộng/fullscreen, quay về editor và tiếp tục công việc bằng bàn phím |

## Design brief cho feature 004 (không implement hiện tại)

1. **Một transcript/screen owner:** Pi interactive TUI là nguồn hiển thị chuẩn; panel Lantern chỉ sở hữu shell: session switcher, path/kind, connect/running state, nút mở rộng/toàn màn hình. Không tạo lại các bubble/tool list từ RPC như hệ thống thứ hai.
2. **Không gian làm việc ưu tiên editor:** desktop có thể dock/collapse hoặc mở fullscreen Pi; chat không che điểm chèn, diff controls, cột cuối bảng. Nếu không thể hiển thị hai cột hữu dụng, chuyển sang layout luân phiên thay vì giữ một panel 440 px che nội dung.
3. **Typography, màu sắc, spacing:** tách bậc rõ cho tiêu đề, path/session, trạng thái và terminal text. Chỉ dùng màu cho trạng thái có ý nghĩa; đảm bảo focus ring, tương phản đọc được trong dark mode, văn bản CJK/monospace và scrollback.
4. **Phản hồi và điều khiển:** native Pi /commands, providers, selectors, extensions không bị chuyển thành nút giả. Người dùng cần nhận biết session đang trả lời, ngắt hay mất kết nối mà không đoán qua thời điểm tool log xuất hiện.
5. **Thử với end-user trước khi merge:** (i) mở doc và nhờ Pi sửa, tiếp tục edit/đọc diff; (ii) chạy Pi, F5 giữa một tool call, quay lại không lặp lệnh; (iii) mở A/B hai path, đổi model/session mà không sai context. Ghi thời gian tìm nút, số thao tác sai, điểm nghẽn về chiều rộng, khả năng đọc 30 dòng output.

## Tiêu chí nghiệm thu gắn với spec 004

- Pi native TUI qua PTY/xterm với đầy đủ slash command/extension; không cần `sessionStorage` để giả phục hồi tool log sau F5.
- 100% sự kiện đầu ra của cùng session có thứ tự thực tế; không lặp, đảo hay ghép từ tab B; các tool/response giữ hình thức Pi bản địa.
- Có các trạng thái session `ready/running/reconnecting/finished/error` và context path/kind nhìn thấy, không có 2 nguồn sự thật.
- Ba kích thước 390 / 1280 / 1920 px, cả mở và đóng bot: không che vùng chỉnh sửa đang có focus; full-width/dock có thể thao tác bằng bàn phím; tất cả control có nhãn rõ.
- Kiểm tra tương phản, focus visible, reduced motion, IME/AltGr/CJK, phím tắt Pi, screen reader labels của toolbar; không phá ordinary terminal.
- Không phát triển hệ thống bảo mật, hạn mức LAN, auto-maintenance mới trong feature này khi chưa duyệt riêng.

**Handoff:** `spec.md`, `plan.md`, `tasks.md` của feature 004. Đây là chuẩn đánh giá cho thiết kế TUI kế tiếp, không yêu cầu giữ giao diện chatbot cũ.

# Feature Specification: LanternBot Native Pi Harness
**Ngày:** 2026-10-17 | **Nhánh triển khai:** feat/lantern-bot (rebase sau khi nền tảng được duyệt)
**Trạng thái:** DRAFT / CHỜ DUYỆT. **Mục tiêu:** Pi thật dưới giao diện Lantern, không bot giả Pi.

## User Stories & Acceptance
### PI-US1 / P1 — Truy cập đầy đủ Pi bản địa từ khung LanternBot
- AC1: giao diện bot mở Pi interactive TUI thật qua PTY/ConPTY và xterm.js; sử dụng /help, /model, /settings, skills, extensions, /goal, model provider, picker, editor, Ctrl/Alt/IME, paste và màn hình tùy biến của extension như khi chạy pi trong terminal FJP.
- AC2: cập nhật Pi/extension đã cài vẫn được sử dụng khi khởi tạo phiên mới; Lantern KHÔNG bảo trì danh mục /command/model riêng hoặc đưa lệnh Pi qua lớp prompt XML.
- AC3: thực hiện lệnh terminal đúng trên local với shell/tools Pi đã cài; không chặn bot vì đang ở trang Milkdown Edit.
- AC4: panel có thể tăng độ rộng/fullscreen theo nhu cầu Pi TUI, không bắt buộc cột 360px khiến picker/table sai định dạng.

### PI-US2 / P1 — Nhiều tab, nhiều phiên độc lập
- AC1: tab A gắn sessionA tới documentA.md, tab B gắn sessionB tới documentB.md; B xuất hiện trong lúc A đang trả lời không đổi context path/kind/turn/model của A.
- AC2: tab B có thể gửi lệnh tới B đồng thời A chạy; Stop/New chat/Model của B không tác động tới A.
- AC3: mở hai tab cùng session được hỗ trợ dưới chính sách 1 writer/size owner, viewers chỉ xem; chọn chuyển quyền rõ; không trộn PTY bytes giữa sessions.
- AC4: F5/đóng tab không giết Pi đang chạy; reconnect nhận screen/history phù hợp và không gửi lại Enter/prompt.
- AC5: một app restart có thể mở lại lịch sử từ session file Pi; tiến trình đang chạy khi restart có thể mất nếu chưa có supervisor (cần xác định rõ quy tắc trước khi merge). Không tự kill phiên chỉ vì không còn browser tab; mặc định giữ tới thao tác Stop/Close rõ ràng, cần thống kê tài nguyên và quyết định người dùng trước release.

### PI-US3 / P1 — Ngữ cảnh tài liệu đúng và không phá TUI
- AC1: session được tạo với sessionId duy nhất, cwd hợp lý, contextRef gồm kind/path/selected range có version; bot hiểu file đang làm việc qua kênh chính thức của Pi, KHÔNG chèn phím vào PTY và không đóng khung tất cả /commands như prompt văn bản.
- AC2: đổi file trong tab không âm thầm đổi context của session đang chạy; hệ thống hỏi attach/create/switch hoặc tạo session mới theo quy tắc được chọn.
- AC3: bot sửa file .md gốc bằng tools Pi; Markdown diff hệ thống file md_temp quan sát thay đổi, không phải bot phải gọi api save riêng.
- AC4: mọi trạng thái tương tác khi bot đang response được hiển thị trong TUI bản địa, không dựng lại từ RPC và mất log khi F5.

### PI-US4 / P2 — Pi là người bạn đồng hành, nền tảng cho bảo trì tương lai
- AC1: thiết kế hợp đồng nhận ứng dụng đang mở tài liệu, thao tác, lỗi, trạng thái module; có định danh app event, path và revision.
- AC2: CHỈ định nghĩa giao diện gắn một extension Pi tùy chọn/nguồn ngữ cảnh (không ghi vào vùng editor bằng PTY), không cài background agent/memory/monitor bảo trì ở giai đoạn này.
- AC3: người dùng vẫn dùng Pi tự nhiên, không bị Lantern bắt khai báo lại skills/providers/extensions toàn cục.

### PI-US5 / P2 — Phạm vi localhost/LAN
- AC1: localhost mặc định được hưởng nguyên khả năng Pi CLI đã cài, không whitelist model/tool ngầm, không hardcode provider.
- AC2: LAN model/provider whitelist/blacklist, tools, token/call ngân sách là yêu cầu tương lai; bản thiết kế có điểm kiểm soát lúc spawn và trước provider/tool boundary. KHÔNG tuyên bố system prompt hoặc Pi --models chỉ là cơ chế hạn mức an toàn.
- AC3: KHÔNG triển khai cơ chế bảo mật mới trong thay đổi này. Nếu native TUI không thể hạn chế LAN đúng yêu cầu khi chưa có boundary thực thi, không đưa native bot ra LAN trước một quyết định riêng.

## UX acceptance — bổ sung từ ảnh và audit 2026-10-17
- [CHAT_UX_AUDIT_2026-10-17.md](CHAT_UX_AUDIT_2026-10-17.md) đánh giá panel cũ theo Hallmark và hành trình end-user, phân biệt quan sát với giả thuyết. HTML chatbot trước/sau refactor 002 trùng SHA, không phải nhiệm vụ hotfix.
- **PI-US6 / P1 — Pi là workspace cạnh editor, không phải bubble chat giả.** Session/context rõ ràng, native TUI đầy đủ, tool/response đúng thứ tự, không che vùng gõ/diff. Panel dock/expand/fullscreen, trạng thái và focus/IME dễ hiểu; viewport hẹp phải chuyển layout thay vì đè lên Source.
- **PI-FR13:** không phục hồi transcript/tool call qua snapshot HTML sessionStorage thứ hai; native PTY/Pi session giữ output, thứ tự, trạng thái và reconnect. Shell chỉ hiển thị session/kind/path và điều khiển.
- **PI-SC07:** ba luồng: Pi sửa doc và quan sát diff không che editor; F5 giữa tool call không lặp output/nhập lại; hai tab A/B giữ session/context độc lập. Kiểm 390/1280/1920 px, focus, contrast, reduced motion, CJK/IME, keyboard shortcuts.

## Functional Requirements
- PI-FR01: Có một PiSessionRegistry sở hữu Pi process/PTYS và metadata, keyed by sessionId; mỗi session có Pi-native session file. Tab/view chỉ attach.
- PI-FR02: Pi chạy interactive (không rpc), trên cwd của dự án đang làm việc; truyền provider/model bằng CLI Pi hiện hành khi người dùng thực sự chọn, mặc định tôn trọng config Pi.
- PI-FR03: Tái dùng TerminalManager, WS framing và xterm.js đã có, không tạo một PTY/terminal protocol khác cho bot.
- PI-FR04: WS event/output/replay phải route theo sessionId và generation, reject stale request, idempotent attach, không broadcast nội dung Pi đến mọi tab.
- PI-FR05: Một writer/resize owner cho mỗi session; nhiều viewers được xem trạng thái theo đúng generation và history.
- PI-FR06: F5 là detach/re-attach; Pi session không tự restart/mất lượt, không tự động resend prompt.
- PI-FR07: ngữ cảnh tài liệu gắn session hoặc gắn lượt qua Pi-native extension hook khi phù hợp, không qua giả lập bàn phím.
- PI-FR08: không tự động sao chép text/thinking/tool logs sang lịch sử HTML thứ hai; Pi TUI nắm giao diện, trạng thái bản địa.
- PI-FR09: dùng CLI --session-id/--session-dir/--tui-mode regular (đã thấy ở phiên bản Pi FJP), không tự định nghĩa serialization lịch sử.
- PI-FR10: điểm mở rộng typed AppContextEvent và SessionPolicySpec chỉ là contract thiết kế, không bắt đầu xử lý bảo trì tự động.
- PI-FR11: server restart có trạng thái rõ: reopen session Pi từ file, không ngầm coi turn cũ vẫn đang chạy; nếu yêu cầu in-flight survival phải duyệt supervisor riêng.
- PI-FR12: không làm đổi terminal bình thường, IME/keyboard, scrollback/resize, SCM trong Lantern.

## Các trường hợp biên
- Pi extension có prompt UI/select/custom TUI component; không phải mọi ANSI frame có thể khôi phục chỉ bằng nối chunks văn bản.
- Tab F5 khi tool đang chạy; Pi xuất hiện ở hai cửa sổ với kích thước khác nhau; một tab resize liên tục.
- Windows ConPTY + Unicode/UniKey/AltGr/emoji, bracketed paste, clipboard ảnh, Ctrl+C khi đang stream.
- Pi tự mở session khác bằng /new, /fork; sessionId/file của Lantern cần cập nhật từ Pi-native identity, không đoán.
- Pi thay model/provider ngay trong TUI; file context change; cwd khác; extension reload; Pi version nâng cấp.
- Pi process bị kill/host restart; lịch sử tồn tại nhưng tool call chưa hoàn tất.

## Success Criteria
- PI-SC01: Bảng parity kiểm thử >=12 thao tác thật Pi (slash, model, extension UI, skills, /goal, tool output, IME, paste, Ctrl+C, Ctrl+P, /new, resume) PASS trên FJP.
- PI-SC02: 2 phiên/tab khác path chạy đồng thời, context và stop/model cô lập; attach cùng session không xáo trộn màn hình.
- PI-SC03: reload không mất session running; reconnect/replay không lặp input; restart tách bạch lịch sử và in-flight.
- PI-SC04: không còn cơ chế chatbot dựng transcript và prompt wrapper thừa; giao diện mới không degrade Terminal thường.
- PI-SC05: config Pi có model/extension mới được hưởng lợi mà không phải cập nhật danh mục Lantern.
- PI-SC06: không triển khai LAN policy/security cho tới khi người dùng phê duyệt độc lập.

## Ngoài phạm vi
Tái tạo một chatbot HTML/RPC hoàn chỉnh, AI tự bảo trì liên tục, memory cross-device, policy engine LAN, sandbox, provider gateway, agent orchestration.

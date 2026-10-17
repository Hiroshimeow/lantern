# Feature Specification: Lantern Platform Foundation
**Branch thiết kế:** spec/lantern-platform-20261017
**Ngày:** 2026-10-17
**Trạng thái:** DRAFT / CHỜ PHÊ DUYỆT
**Baseline mã vận hành:** fb06c40758f406feb70bbb26ccd3cecb6476dacc
**Phạm vi:** refactor nền tảng, KHÔNG triển khai Markdown mới, bot mới hay chính sách bảo mật.

## Mục tiêu
Biến Lantern từ ứng dụng có entrypoint hỗn hợp ~3.749 dòng thành nền tảng có module theo trách nhiệm, cho phép hai agent phát triển Markdown và Pi TUI song song, nhưng KHÔNG giảm bất kỳ hành vi ổn định nào đã có.

## User Scenarios & Testing
### US1 / P1 — Chạy Lantern đầy đủ với một entrypoint chuẩn
- Người dùng khởi chạy trực tiếp hoặc bằng run.bat/install.ps1 trên Windows hay Linux; nhìn thấy cùng file browser, Preview, Terminal, Markdown, Crop, PDF/Media, Git/SCM và WebSocket.
- AC1: start trên cổng riêng, root chỉ định; GET /api/info, /api/list, /api/plugin/preview, static assets có status/content-type/header, response bytes phù hợp baseline.
- AC2: phiên terminal có thể tạo, gõ, replay, resize, kết nối lại; các luồng Markdown và bot không bị đổi hành vi chỉ vì refactor.
- AC3: chỉ có main.py làm entrypoint, không còn lan_drive.py hoặc shim dẫn về mã cũ.

### US2 / P1 — Module độc lập theo chức năng
- Người phát triển tìm được owner rõ của file operations, media/crop, Preview/Markdown, terminal/Pi, route HTTP và config.
- AC1: mỗi miền có contract/unit tests và có thể dùng temp root hoặc fake port để test; import không khởi chạy server/process.
- AC2: hai Lantern app instance trong một interpreter có trạng thái riêng, không chia sẻ singleton manager/cache nhầm.
- AC3: thay đổi Markdown không buộc chỉnh sửa terminal; thay đổi Pi không buộc sửa parser Markdown.

### US3 / P1 — Refactor không gây degrade
- AC1: test characterization bản HEAD fb06c40 được khóa trước refactor, chạy trên mã mới KHÔNG sửa kỳ vọng.
- AC2: HTTP method/route/status/header/stream/range, WebSocket framing/event/replay, terminal IME, file operations (rename, concurrent upload, zip, symlink) giữ tương đương.
- AC3: đo latency/CPU/RSS của 3 kịch bản: listing, Preview Markdown 100 KiB, terminal replay; nếu suy giảm vượt ngân sách được duyệt, không merge.

### US4 / P2 — Bàn giao không mất dữ liệu
- AC1: các bản nháp .lantern/work cũ được kiểm kê và hiển thị khác biệt rõ ràng; KHÔNG tự ghi đè file .md gốc.
- AC2: cấu hình máy cũ và dữ liệu Pi/Terminal/md_temp không bị xóa do thay entrypoint; không thay tên config mà không có quyết định cụ thể.
- AC3: có kế hoạch dọn WIP refactor chưa commit hiện ở main bằng một quyết định riêng, không âm thầm reset/stash/clean.

## Functional Requirements
- FND-001: main.py chỉ parse args và gọi composition root, không chứa HTTP business logic hoặc mã renderer.
- FND-002: composition root là nơi duy nhất khởi tạo/đóng tài nguyên có trạng thái (server, WS, terminal, Pi, Markdown, filesystem watcher nếu được duyệt sau).
- FND-003: request handler được cấp các dependency cần dùng qua đối tượng runtime hoặc các tham chiếu cụ thể; business service không phụ thuộc HTTP và không import entrypoint.
- FND-004: mỗi module chỉ có một owner: config, path/file, media/crop, preview, Markdown edits, terminal transport, Pi session; đặt cạnh code thay đổi cùng nhau.
- FND-005: một cơ chế phân giải đường dẫn có root rõ và thông báo lỗi có kiểu; không nhân bản logic phân giải ở các module.
- FND-006: hợp đồng HTTP/WS và giao diện người dùng giữ nguyên, trừ thay đổi đã định nghĩa ở các spec tính năng khác.
- FND-007: startup, launcher, installer, README, test runner và CI cùng chỉ về main.py; không giữ code tương thích tạm.
- FND-008: module có thể import và test bằng temp root, fake emitter, fake PTY mà không tạo process/network ngoài ý muốn.
- FND-009: giữ cấu hình YAML hiện dùng, không đổi nghĩa khóa mà chưa có migration được duyệt.
- FND-010: không triển khai auth/policy LAN mới; chỉ xác định owner và giao diện có thể thêm chính sách khi được phép.
- FND-011: công việc trên main và feature worktree phải rebase từ main trước phát triển/merge và chạy lại characterization.
- FND-012: WIP hiện có chưa được xem là baseline đúng; không sửa golden test để hợp thức hóa refactor.

## Entities / Contract
- AppConfig: cấu hình đã validate của một instance.
- Application: vòng đời, các service được cấp rõ trách nhiệm; có close() idempotent.
- RootPathResolver: tệp nằm trong root, hỗ trợ Unicode/Windows drive, trả canonical path hoặc lỗi rõ.
- FileRevision: bằng chứng content/hash + stat cho CAS khi ghi.
- DomainEvent (chỉ contract): metadata nguồn đổi tệp/cập nhật trạng thái phiên; chưa xây hệ thống event bus mới.
- HTTP/WS Adapter: giao thức, mã trạng thái, replay/backpressure; KHÔNG làm nơi sở hữu nội dung tệp.

## Rủi ro và trường hợp biên
- Chia file máy móc tạo import cycle, đổi cwd, path của asset, relative URL hoặc HTTP order.
- Import main.py bằng hai tên khác nhau làm nhân đôi terminal/Pi singleton.
- Root là Unicode/UNC/short Windows path; symlink/đường dẫn ../; tệp lớn/Range requests.
- Nhiều client cùng upload, xóa/move/rename folder; cảnh báo cũ biến thành lỗi câm.
- Two-instance cùng process/cổng riêng; shutdown không dừng session của instance còn lại.

## Success Criteria / Gates
- SC-FND-01: 100% characterization fixtures ghi từ fb06c40 PASS mà không chỉnh expected values.
- SC-FND-02: không còn mã thực thi lan_drive.py hoặc shim sau cutover cuối; CLI/installer chạy main.py.
- SC-FND-03: có kiểm tra import graph không vòng và không import-time side effects trong các module tách.
- SC-FND-04: unit + HTTP/WS + FJP Windows Edge smoke PASS; Linux smoke PASS hoặc nêu blocker thực chứng trước merge.
- SC-FND-05: benchmark p95/CPU/RSS được ghi trước/sau trên cùng máy; ngưỡng suy giảm cần ký duyệt (đề xuất <=20% p95, <=25% RSS, không mặc định coi PASS nếu thiếu số).
- SC-FND-06: Git tree sạch, không thay đổi dữ liệu người dùng trong quá trình migration, branch review signoff.

## Ranh giới
Bao gồm nền tảng và contract. KHÔNG bao gồm tính năng mới Milkdown/Crop, Pi TUI, cơ chế chính sách LAN, auto maintenance. Những phần đó được đặc tả độc lập.

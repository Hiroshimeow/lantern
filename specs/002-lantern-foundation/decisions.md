# Lantern architecture decision log (DRAFT — requires owner approval)
**Ngày:** 2026-10-17
**Reviewer:** Sonnet 5.5 on FJP M365 via existing Worker; same conversation [181fd168-...](https://m365.cloud.microsoft/chat/conversation/181fd168-316e-4e07-bd5d-e99097960384).
**Turns:** Round 1 `61686840-m365-worker-20261017-091358-6eb724d8`; Round 2 `61686840-m365-worker-20261017-091843-30a32a56`; Round 3 `61686840-m365-worker-20261017-092311-95b77bfa`.
Three-round technical consensus is **conditional on proof gates**, not authorization to implement.

## Settled as architectural consensus (not yet owner-approved)
| ID | Quyết định | Phản ví dụ đã cân nhắc |
|---|---|---|
| D1 | Baseline từ clean fb06c40, golden black-box HTTP/WS/GUI bằng cổng và thư mục tạm, expected không sửa để đạt PASS | Test oracle viết lại cùng code có thể che mất degrade |
| D2 | Atomic cutover duy nhất sang main.py, xóa lan_drive.py, không shim hoặc server cũ; module refactor theo trách nhiệm, chỉ phát hành sau full gate | Phân tách AST máy móc thay import nhưng vẫn giữ singleton/god-context |
| D3 | Byte file .md thật + md_temp là nguồn diff duy nhất; line endings/BOM/no final newline là dữ liệu, không dùng parsed ProseMirror text làm chuẩn | Hai chuỗi Markdown khác nhau có thể render cùng một PM doc |
| D4 | Pi native TUI qua PTY/ConPTY + WS + xterm.js hiện có; không RPC HTML transcript clone, không observer JSONL | RPC không đảm bảo extension custom TUI parity |
| D5 | Pi sessionId opaque là định danh chính; cwd/context/path là metadata; hai Pi session có thể cùng file; một PTY/session; explicit attach role | Key theo path ngăn nhiều phiên trên một file và retarget không mong muốn |
| D6 | Embedded Crop reuse CropperJS 2 + existing mountImageCrop, Preview thêm reference targeting có chứng cứ | Reimplement Crop tạo drift; Nth image URL có thể sửa nhầm |
| D7 | Không viết bảo mật/LAN quota/bot maintenance automation mới cho tới chủ sở hữu phê duyệt riêng | Lệnh Pi --models/prompt không thực thi quota và tool boundary |
| D8 | Không chọn headless screen mirror hoặc custom segment parser trước khi proof. Đọc upstream/đo bản hiện có trước | Cơ chế mới tự chế có thể mất replay, normalized Markdown |

## Contingent go/no-go decisions — proof required
| ID | Cần chứng minh | Nếu chưa qua |
|---|---|---|
| P1 | 100% dữ liệu corpus được edit trong Visual không thay byte ngoài span edit, CRLF/BOM/GFM/Unicode; nguồn range map chính xác, duplicate table/code | Không triển khai chiến lược patch Visual mới; yêu cầu review/đổi thiết kế, **không mặc định hạ Visual thành chỉ đọc** |
| P2 | Pi ConPTY native full command + IME + bracketed paste + replay snapshots/cursor/modes/scrollback trên nhiều kích thước, không replay keyboard/query | Không phát hành native bot pane; đánh giá upstream xterm serialize/tmux-style proof trước |
| P3 | Exact Pi --session-id/--session-dir resume/collision và Preview image URL token source ranges; Crop không sửa nhầm hình | Tách work riêng, không nhận chức năng tương ứng vào release |

## No-code, no-WIP mutation rule
- WIP mechanical refactor hiện có trên main đang **DIRTY** (gồm staged deletion lan_drive.py). Không giả đó là baseline chuẩn; không reset/stash/clean/commit WIP khi đang duyệt.
- Toàn bộ tài liệu nằm trong worktree spec/lantern-platform-20261017; không thay sản phẩm 9999 và không sửa feat/lantern-bot.
- Không làm proof spike, cài dependency, chạy refactor/implementation, test sửa golden hoặc merge/push trước phê duyệt.

## Owner sign-off (đề xuất lựa chọn)
- **S1.** Có phê duyệt 3 proof spikes P1–P3 sau khi phê duyệt tài liệu, và task nào không qua phải quay lại design thay vì hạ chất lượng? **Khuyến nghị Có.**
- **S2.** Pi idle: giữ process khi không còn tab, chỉ Stop/Close thủ công; nhiều session cùng file cho phép? **Khuyến nghị Có**, với hiển thị active sessions và giới hạn tài nguyên cần bàn trong spec (không âm thầm giết phiên).
- **S3.** Milkdown 'Tier 2' có normalization nội bộ: không được phép tái định dạng phần không sửa; với phần sửa, phải báo trước/trực quan để user accept? **Khuyến nghị Có**; nếu không bảo toàn khả năng Edit, quay lại thiết kế, không ship Visual read-only tự động.
- **S4.** Animated GIF: từ chối Crop cho tới khi có engine per-frame được duyệt; giữ nguyên ảnh động? **Khuyến nghị Có.**
- **S5.** Xử lý WIP dirty main: giữ nguyên tới khi user xem inventory; sau đó quyết định riêng (không reset/stash ngầm). **Khuyến nghị Có.**
- **S6.** Bảo mật LAN/quota: chỉ đưa vào tài liệu interface và bản phân tích khả thi, không triển khai? **Khuyến nghị Có.** Nếu yêu cầu public LAN native Pi trong release này phải thiết kế boundary mới và xin phê duyệt riêng.
- **S7.** Sau khi 002 được nghiệm thu mới mở 003/004 song song, rebase main sạch trước khi dev/merge? **Khuyến nghị Có.**

## Giới hạn tri thức
Sonnet tham gia với bản mô tả và bằng chứng mã do caller kiểm tra, **không trực tiếp đọc repo FJP**. Mọi gợi ý kỹ thuật như source-ranged dirty patches hoặc xterm replay mirror là giả thuyết cần POC, không phải chứng minh thực nghiệm.

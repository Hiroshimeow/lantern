# Lantern — Đề xuất kiến trúc cho người duyệt (17/10/2026)

**TÌNH TRẠNG: DỰ THẢO — CHƯA ĐƯỢC PHÉP IMPLEMENT.** Kết quả 3 vòng tranh luận độc lập với Sonnet M365 trên FJP; đồng thuận về kiến trúc/tiêu chí, chưa có bằng chứng cho các kỹ thuật cần thử.

**Tài liệu:** [upstream verification](upstream-verification.md) · [constitution](constitution.md) · [foundation spec](spec.md) · [foundation plan](plan.md) · [foundation tasks](tasks.md) · [Markdown spec](../003-markdown-fidelity/spec.md) · [Markdown plan](../003-markdown-fidelity/plan.md) · [Markdown tasks](../003-markdown-fidelity/tasks.md) · [Pi spec](../004-pi-native-harness/spec.md) · [Pi plan](../004-pi-native-harness/plan.md) · [Pi tasks](../004-pi-native-harness/tasks.md) · [Decision record](decisions.md) · [Requirements matrix](analysis.md).

## Tại sao cần kiến trúc này?
- Cùng một file .md có thể sửa từ Edit, Source, VS Code, Pi mà không mất nội dung. .md_temp chỉ là ảnh chụp so sánh, Ctrl+S chấp nhận diff.
- Pi chạy đúng native interactive TUI: command /, extension, skill, provider, /goal và custom UI. Không tạo một chat renderer RPC riêng phải đuổi theo Pi upstream.
- Mỗi Pi session có id bền vững riêng, không phụ thuộc tab, path hay browser WS. Hai phiên có thể cùng gắn một file nhưng không thao tác nhầm nhau.
- Module theo trách nhiệm, baseline parity trước refactor, không nợ kỹ thuật do wrapper/migration vĩnh viễn.

## Architecture / module ownership
```mermaid
flowchart TB
  UI["Lantern browser<br/>Files / Preview / Edit / Source / Pi TUI"]
  MAIN["main.py<br/>CLI only"]
  APP["Application<br/>single composition / lifecycle"]
  HTTP["HTTP + WebSocket adapters"]
  FS["Root / File services<br/>revisions & events"]
  MD["Markdown domain<br/>.md original + md_temp + diff"]
  IMG["Crop / Media services<br/>pixels + asset version"]
  TERMINAL["Existing terminal PTY<br/>ConPTY / Unix PTY + xterm.js"]
  PI["Pi session registry<br/>native Pi TUI processes"]
  UI <--> HTTP
  MAIN --> APP
  APP --> HTTP
  APP --> FS
  APP --> MD
  APP --> IMG
  APP --> TERMINAL
  APP --> PI
  HTTP --> FS
  HTTP --> MD
  HTTP --> IMG
  HTTP --> TERMINAL
  HTTP --> PI
  PI --> TERMINAL
  PI -. "ordinary file writes" .-> FS
  FS -. "file change observed" .-> MD
```
**Giới hạn:** Markdown và Pi không import nhau. HTTP adapter không giữ nội dung hoặc phiên. Không tạo event bus/policy engine mới khi chưa có consumer. Security/LAN nâng cấp cần phê duyệt riêng.

## Luồng Markdown — file gốc & snapshot
```mermaid
flowchart LR
  EDIT["User / VS Code / Pi<br/>Edit / Source"] -->|"write original + version"| REAL["Document.md<br/>current bytes"]
  REAL -->|"revision"| DIFF{"Byte/line hunk diff"}
  TEMP["md_temp<br/>accepted bytes"] --> DIFF
  DIFF --> P["Preview<br/>decorations"]
  DIFF --> V["Milkdown Edit<br/>ProseMirror decorations"]
  DIFF --> S["Source<br/>inline line diff"]
  REAL -->|"Ctrl+S: copy bytes"| TEMP
  CROP["CropperJS 2<br/>Preview or Edit"] -->|"asset CAS"| IMAGE["Image asset"]
  CROP -->|"exact URL token patch, if copy"| REAL
```
Không có ghi tự động vào md_temp. Undo sau Save được xem là một edit mới. Không dùng vị trí được đoán hoặc normalize nội dung ngoài vùng sửa.

## Hai tab Pi độc lập và cùng một phiên
```mermaid
flowchart TD
  A["Tab A: file A"] --> A1["Pi session alpha"]
  B["Tab B: file B"] --> B1["Pi session beta"]
  C["Tab C: file A"] --> PICK{"New / Attach existing?"}
  PICK -->|"New"| C1["Pi session gamma<br/>same file A, independent"]
  PICK -->|"Attach alpha"| A1
  A1 --> P1["one PTY alpha<br/>single writer & size owner"]
  B1 --> P2["one PTY beta"]
  C1 --> P3["one PTY gamma"]
  P1 -. "file writes" .-> DOC["file A on disk"]
  P3 -. "file writes" .-> DOC
```
Đóng tab hoặc F5 không giết phiên đang chạy; server restart có thể mở lại lịch sử Pi, **không** được giả lượt đang chạy vẫn tiếp tục nếu process đã dừng. Trạng thái idle/cleanup do người dùng quyết định.

## Gói Spec-Kit độc lập
| Gói | Phạm vi | Phụ thuộc | Triển khai |
|---|---|---|---|
| **002 — Foundation** | main.py, composition, modules, HTTP/WS parity, installers | Baseline fb06c40 + ký duyệt | Worktree riêng → atomic cutover, merge main sau gate |
| **003 — Markdown Fidelity** | Original/md_temp, Diff ba chế độ, Crop ảnh nhúng, byte preservation | 002 đạt nghiệm thu | main (owner của Markdown) |
| **004 — Native Pi Harness** | interactive Pi TUI, session registry, xterm replay, multi-tab | 002 đạt nghiệm thu | feat/lantern-bot, rebase trước dev và trước merge |

003 và 004 có thể làm **song song sau 002** vì không cùng sửa một owner. Test / review theo package, không khóa merge chỉ vì độ đơn giản hay thời gian.

## Trạng thái / bằng chứng
| Nhận định | Mức chứng minh |
|---|---|
| Main HEAD fb06c40; 9999 hiện chạy bản commit cũ | Đã kiểm FJP |
| Main có uncommitted refactor dở; không đủ gate để merge | Đã kiểm FJP |
| Milkdown Edit có mountImageCrop và DecorationSet | Đã đọc source, chưa nghiệm thu đủ UX |
| Preview Crop chưa ngang bằng Edit, Source/Visual diff còn lỗi reported | Có báo cáo người dùng, cần E2E tái hiện |
| Pi TUI native đủ tốt dưới ConPTY + reconnect/replay | **Chưa chứng minh — proof spike** |
| Milkdown giữ byte ngoài vùng sửa bằng patch đúng | **Chưa chứng minh — proof spike** |
| 3 vòng tranh luận Sonnet đồng ý baseline và gate | Đã lấy phản hồi M365 thực tế, xem decisions.md |

## Yêu cầu phê duyệt
Chấp thuận **thiết kế và các proof-spike sau khi phê duyệt**, không có nghĩa chấp nhận kết quả chưa đo. Không cho phép thay Milkdown bằng Visual chỉ đọc hoặc hạ chuẩn nhập liệu nếu không được phê duyệt riêng. Không cài bảo mật mới.

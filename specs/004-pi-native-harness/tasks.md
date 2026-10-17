# Tasks: LanternBot Native Pi TUI (DRAFT / KHÔNG THỰC HIỆN)
Nguồn: specs/004-pi-native-harness/spec.md và plan.md. Phụ thuộc gói nền tảng 002 được duyệt/merge. Owner worktree: feat/lantern-bot.

## Phase 0: Characterization & feasibility (blocking)
- [ ] **PI-T000 [PI-US6/FR13] UX baseline và native shell review.** Dùng [CHAT_UX_AUDIT](CHAT_UX_AUDIT_2026-10-17.md) và ảnh hiện trạng, kiểm hành trình người dùng thực trên desktop/mobile; chụp 390/1280/1920px, trạng thái toolbar/session/path, focus/caret/scroll khi bot mở. Thiết kế panel dock/expand/fullscreen chứa Pi native terminal, không đầu tư HTML transcript cũ.
- [ ] **PI-T001 [PI-FR02] Exact Pi CLI reference baseline.** Trên FJP, ghi `pi --version`/`pi --help` và cấu hình extension ở chế độ chỉ đọc; không gửi prompt AI/không cài package; lập parity matrix trong docs, xác minh /model,/settings,/goal, shell, skills, extensions, custom UI.
- [ ] **PI-T002 [PI-FR03] PTY native parity POC.** Sử dụng `lantern/terminal.py` hiện có để spawn Pi interactive trên cwd tạm; E2E test WinConPty xterm.js với 12 thao tác native, Ctrl/IME/paste/image/Alt, assert screen/cursor. Test file `tests/test_pi_tui_e2e.py`; không viết ANSI emulator mới.
- [ ] **PI-T003 [PI-FR04/06] Lossless replay proof.** `tests/test_pi_reconnect_e2e.py`: stream, alternate screen, F5 during tool, reconnect, two window widths, clipboard/input echo, sequences broken at chunk boundary; compare snapshot screen cell/cursor/modes before/after. Đánh giá xterm serialize/screen model upstream; STOP nếu không đạt.

## Phase 1: Session ownership
- [ ] **PI-T004 [PI-FR01/09] Durable PiSessionRegistry.** `lantern/pi_sessions.py` (chỉ khi 002 owner cho phép), sessionId opaque độc lập path/tab; cwd, Pi-native sessionDir, metadata contextRef, status/attach generations. `tests/test_pi_sessions.py`: two sessions same file independent; two docs independent.
- [ ] **PI-T005 [PI-FR03] Reuse TerminalManager for Pi spawning.** `lantern/terminal.py` constructor cho argv/cwd/env (không shell-string injection/quoting), tests Windows/Linux; không tạo PTY factory riêng chỉ cho bot.
- [ ] **PI-T006 [PI-FR04/05] Scoped WS and one writer.** `lantern/ws.py` + `tests/test_pi_ws_contract.py`: attach sessionId/generation, sequence/ack/replay, exclusive input + resize owner, explicit takeover, viewer no input; tab B không nhận raw data của A.
- [ ] **PI-T007 [PI-FR06/11] Reload and restart lifecycle.** `lantern/pi_sessions.py`, `tests/test_pi_reconnect_e2e.py`: tab detach không kill Pi; restart Lantern reload session history từ Pi file, interrupted turn không bị giả 'running'; process close không để orphan.

## Phase 2: Bot UI native, not HTML clone
- [ ] **PI-T008 [PI-FR08] Replace custom HTML conversation layer with TUI host.** `static/chatbot.js`, `static/chatbot.css` (hoặc frontend module đã được domain tách sau 002): bot pane + xterm native, session toolbar and expand/fullscreen. Không sao chép thinking/tool/response lịch sử bằng DOM.
- [ ] **PI-T009 [PI-FR02/08] Native slash and extension parity.** Test `tests/test_pi_tui_e2e.py`: /help,/model,/new,/fork,/goal, Ctrl+P, custom selectors, notification, project/global extensions; Pi upgraded model list appears automatically. Không hardcode list trong Lantern.
- [ ] **PI-T010 [PI-FR01/03] Multi-tab context and session selection.** UI New Session, Attach Existing, Switch, explicit pathContext at creation; `tests/test_pi_multitab_e2e.py`: tab A responding+tab B opened, B sends B, Stop/New/model isolated; two sessions on same file possible, tab navigation does not retarget.
- [ ] **PI-T011 [PI-FR03/07] Pi-native document context.** Nếu yêu cầu có evidence, dùng session initial cwd/file context/hook upstream, không fake terminal keystroke. Test exact selected path with UTF-8 spaces/special chars, intentional context refresh, no mutation of A by B. Bot edits real .md, Markdown diff tests see changed bytes.

## Phase 3: Regression/acceptance
- [ ] **PI-T012 [PI-SC04/05] Remove old duplicated bot runtime only after full replacement passes.** Kiểm chứng `lantern/pi_chat.py` RPC process, `static/chatbot.js` manual tool-log handling no longer active or retained; no compatibility shims. Regression `tests/test_chat_ui.py`, normal terminal/SCM and Markdown E2E.
- [ ] **PI-T013 [PI-US4/US5] Document future seam only.** Lưu docs hợp đồng AppContextEvent/SessionPolicySpec và LAN limitations; KHÔNG tạo PolicyGate code, auto-maintenance extension, observer, new network/auth/proxy.
- [ ] **PI-T014 [PI-SC01–06] Live FJP/Edge and resource acceptance.** Kiểm replay, resizing, Unicode/UniKey/AltGr, paste image, CLI parity and unchanged ordinary terminal; latency/CPU/RSS; fail if uncertain claims.
- [ ] **PI-T016 [PI-US6/SC07] UX/accessibility release gate.** End-user phải hoàn thành 3 flow: bot sửa file và tiếp tục Source không bị che, F5 giữa tool call đúng thứ tự không lặp, tab A/B không trộn path/session. Kiểm 390/1280/1920, tabindex/focus, CJK/IME/AltGr, reduced motion/contrast, output dài/picker/30-col và không HTML replay; lưu ảnh/video + lỗi ưu tiên và sign-off.
- [ ] **PI-T015 [PI-SC01–06] Independent review, rebase and FF.** trước coding và trước merge rebase main; only feature files, no code Markdown; commit meaningful checkpoints; push/merge chỉ khi user approve.

## Dependency graph
PI-T001–T003 proof → PI-T004–T007 session foundation → PI-T008–T011 UI/context → PI-T012–T015.
Pi session and Markdown owner KHÔNG phụ thuộc trực tiếp nhau: thông qua file gốc và giao thức đường dẫn.

## Explicit deferrals
LAN strict whitelist/blacklist, giới hạn token/call/tool, auth/sandbox, auto maintenance, cross-device memory; cần bộ spec/phê duyệt riêng. Không đưa mô phỏng bảo mật vào system prompt.

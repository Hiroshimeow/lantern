# Tasks: Lantern Platform Foundation — DRAFT / KHÔNG THỰC HIỆN
Nguồn: [spec.md](spec.md), [plan.md](plan.md), [constitution.md](constitution.md).
Thực hiện sau khi chủ sở hữu duyệt. Mỗi task có kiểm thử độc lập và commit riêng trên worktree triển khai; KHÔNG áp dụng lên main đang bẩn.

## Phase 0 — Baseline và dọn đường (blocking)
- [ ] **F-T001 [FND-012] Kiểm kê WIP main và quyết định xử lý.** Đối chiếu `git status`, `git diff --cached`, untracked modules trước refactor; lập báo cáo từng thay đổi trong specs/002-lantern-foundation/WIP_DISPOSITION.md, có quyết định giữ/bỏ từng phần. Không reset/stash/clean trước phê duyệt. Gate: giữ đủ dữ liệu, main không bị biến đổi do task nghiên cứu.
- [ ] **F-T002 [FND-006/SC01] Ghi characterization oracle từ HEAD fb06c40 sạch.** Thêm `tests/test_http_contract_snapshot.py`, `tests/test_ws_contract_snapshot.py` và fixtures/traces theo request. Cases: GET info/list/plugin preview/thumbnail/range, POST file CRUD/md work, lỗi 400/403/404/409/413/423, WebSocket subscribe/replay/close. Chụp output của server ephemeral root và lưu mask manifest các fields thật sự bất định (port/date/ETag), review riêng. Gate: tests PASS trên baseline, bất biến khi refactor.
- [ ] **F-T003 [FND-008/SC05] Baseline performance.** `tests/test_lan_multi_perf.py`, `tools/benchmark_md_visual.py`: cố định tài liệu 100KiB, 30-col table, 1k directory items, terminal replay 200KiB; đo p50/p95, CPU, RSS trên FJP và ghi máy/Python/browser versions trong specs/002-lantern-foundation/research.md. Gate: số đo có thể lặp lại; không bịa số.
- [ ] **F-T004 [FND-003/SC03] Kiểm tra sơ đồ phụ thuộc.** Ghi modules/tham chiếu toàn cục, path resolution, plugin/media, startup; tạo `tests/test_app_architecture.py` để bắt import cycle, import-time service, double init. Gate: test FAIL khi cố ý làm duplicate singleton.

## Phase 1 — Ranh giới module (chỉ bắt đầu sau F-T001..4)
- [ ] **F-T005 [FND-001/002] Tạo composition root có lifecycle.** Files: `main.py`, `lantern/application.py`, `lantern/config.py`; test `tests/test_app_architecture.py` với 2 instance root/port riêng, close idempotent, không tạo service khi import. Gate: main.py --help + 2-instance PASS, không module singleton.
- [ ] **F-T006 [FND-004/005] Root + file services.** `lantern/filesystem.py`, tiêu chí: Unicode/UNC/short path, traversal, root confinement, rename/copy/move/delete, concurrent CAS; tests `tests/test_security.py`, `tests/test_upload_atomic.py`, `tests/test_terminal_auth.py` + oracle F-T002. Gate: không đổi bất kỳ file/status/header unintended.
- [ ] **F-T007 [FND-004] Media & Crop asset service.** `lantern/media.py`, `lantern/crop.py`; ảnh thumbnail/cache, video info, image overwrite CAS, GIF policy hiện hành; tests `tests/test_image_cache_e2e.py`, `tests/test_crop_overwrite.py`, `tests/test_crop_shared_e2e.py`; gate: pixel format/header/cache parity.
- [ ] **F-T008 [FND-003/006] Tách HTTP route groups.** `lantern/http/server.py`, `lantern/http/routes/files.py`, `markdown.py`, `media.py`, `app.py`; contract mỗi nhóm chỉ nhận service cần thiết. Tests `tests/test_http_contract_snapshot.py`, `tests/test_lan_multi_e2e.py`. Gate: response/order/headers preserved.
- [ ] **F-T009 [FND-008] Ghép runtime hiện tại qua sở hữu duy nhất.** `lantern/terminal.py`, `lantern/ws.py`, `lantern/scm.py`, `lantern/live_markdown.py`, `lantern/pi_chat.py` chỉ thay constructor/lifecycle cần thiết; không đổi logic feature. Test terminal/SCM, markdown endpoints, 2 app instances, WS backpressure. Gate: G1/G2.

## Phase 2 — Cutover dứt điểm
- [ ] **F-T010 [FND-007/SC02] One-entrypoint cutover.** Cùng commit: sửa `run.bat`, `tools/run_lantern.ps1`, `install.ps1`, README, subprocess tests; xóa `lan_drive.py`; tất cả khởi động `main.py`. Không giữ shims/alias. Test `tests/test_run_launcher.py`, `test_repository_upgrade.py`, `test_repo_layout.py`, tìm `git grep lan_drive.py` chỉ còn tài liệu lịch sử, không caller runtime. Gate: launcher CLI + installer dry-run.
- [ ] **F-T011 [FND-006/SC04] End-to-end parity và Linux.** Chạy Python suite, HTTP+WS golden, `tests/test_md_mode_switch_e2e.py`, `tests/test_terminal_e2e.py`, `tests/test_crop_shared_e2e.py` với LANTERN_E2E=1; thực tế FJP Edge (cổng thử, không can thiệp 9999/10099), Linux smoke. Gate: 0 sai lệch vô chủ, trình duyệt không JS exception.

## Phase 3 — Review và release gate
- [ ] **F-T012 [SC05] Benchmark sau refactor + so với F-T003.** Lưu p95/CPU/RSS, giải trình sai lệch và không chấp nhận suy giảm không duyệt.
- [ ] **F-T013 [FND-011/SC06] Independent review và main sync.** Review import graph/module owners/nhật ký deviations, rebase branch refactor lên main sạch và chạy lại G1–G5, ff merge/push chỉ sau phê duyệt. Gate: main sạch, artifacts/HEAD chính xác, dịch vụ thật chỉ restart khi được phép.

### Quan hệ
F-T001–4 → F-T005 → (F-T006 và F-T007) → F-T008 → F-T009 → F-T010 → F-T011 → F-T012 → F-T013.
Nhánh Pi và Markdown không bắt đầu merge riêng cho tới khi F-T010/011 được nghiệm thu.

### Stop conditions
Dừng, hỏi người duyệt khi oracle không đúng trên bản sạch; cần đổi HTTP behavior; phát hiện unsaved draft; parser/crop mất chức năng; hoặc Linux/FJP parity không thể chứng minh.

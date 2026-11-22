# Quy Chuẩn Chung Cho AI Agent Khi Test End-User Qua CDP (`v1.0`)

Khi bạn nhận được yêu cầu từ người dùng dạng:
```text
Đây là các chức năng mới phát triển: <mô tả tính năng>
Hãy chạy bộ workflow CI test này.
```

## Quy trình 4 bước bắt buộc cho AI Agent

1. **Đọc Checklist tương ứng trong thư mục `checklists/`**:
   - `checklists/v8.2_baseline.md`: Các tính năng nền tảng của Lantern (File Explorer, Image Audit, Archive Zip, Terminal, Đa tab).
   - `checklists/v9.0_v9.21_core.md`: Các tính năng Markdown 3-Way Diff (Case A/B/C), Source CodeMirror 6, Lanbot Core Pi Subagent Wake-up & Stream.
   - `checklists/v9.22_release.md`: Các tính năng mới của bản v9.22 (3 Mode `Preview` / `Edit visually` DOCX Hybrid Option 1+3 không Milkdown / `Source`, bỏ `Todo` mode, `[skill]` gọn 1 dòng, mỗi tab `#bot1`/`#bot2` giữ độc lập Model và chuyển tab liên tục không lỗi).
   - `checklists/NEW_FEATURE_TEMPLATE.md`: Nơi ghi nhận và bổ sung checklist cho tính năng mới phát triển.
2. **Nếu có tính năng mới phát triển**:
   - Ghi bổ sung tiêu chí nghiệm thu vào `checklists/NEW_FEATURE_TEMPLATE.md`.
   - Thêm 1 hàm kiểm thử ngắn (10–15 dòng) vào cuối file `lantern_checks.py` (sử dụng thao tác người thật `await tab.human_click()`, `await tab.human_type()`, `await tab.select_text_in()`, `await tab.press_key()`).
3. **Chạy bộ test CDP End-User trên trình duyệt Chromium thật**:
   ```bash
   # Tự động bật server từ thư mục code bất kỳ (v8.2, v9.0, v9.21, v9.22...) và chạy CDP:
   python3 run_ci.py --app-dir /path/to/lantern

   # Hoặc test trực tiếp trên server localhost/LAN đang chạy sẵn:
   python3 run_ci.py --base-url http://127.0.0.1:9999
   ```
4. **Kiểm tra Báo cáo & Bằng chứng ảnh chụp màn hình**:
   - Đọc `reports/cdp_report.json` và `reports/cdp_report.html`.
   - Kiểm tra ảnh chụp từng bước trong `reports/screenshots/<GATE_ID>.png`.
   - Chỉ kết luận hoàn tất khi **100% Gate cũ và mới đều PASS**, `0` lỗi Console/Uncaught JS Exception, và `0` lỗi HTTP 5xx.

# Checklist Chức Năng Mới Phát Triển (Dành Cho AI Agent Tự Động Cập Nhật)

Khi người dùng cung cấp danh sách chức năng mới phát triển:
```text
Đây là các chức năng mới phát triển: <mô tả>
Hãy chạy bộ workflow CI test này.
```

AI Agent hãy:
1. Ghi mục checklist mới vào bên dưới.
2. Thêm hàm kiểm thử tương ứng vào khu vực `CUSTOM_NEW_FEATURE_GATES` ở cuối file `lantern_checks.py`.
3. Chạy `python3 run_ci.py --app-dir <đường_dẫn_repo_lantern>` để kiểm증 cả chức năng mới lẫn toàn bộ chức năng cũ.

## Danh sách Chức năng mới cần kiểm tra
- [x] *(Mẫu)* Kiểm tra tính năng mới qua thao tác chuột/phím thật trên trình duyệt Chromium CDP.

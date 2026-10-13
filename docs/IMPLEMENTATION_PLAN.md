# Kế hoạch triển khai Lovira-Facebook Manager (IMPLEMENTATION_PLAN.md)

Tài liệu này chi tiết hóa toàn bộ các mốc phát triển theo lộ trình trong đặc tả kỹ thuật, gắn kết trực tiếp với các yêu cầu nghiệp vụ (BR-01 đến BR-13) và 44 tiêu chí nghiệm thu (AC-01 đến AC-44).

---

## Danh sách Chức năng & Trạng thái

| ID | Giai đoạn | Chức năng chi tiết | Yêu cầu BR | Tiêu chí AC | Trạng thái |
|---|---|---|---|---|---|
| **F-01** | Phase 1: Nền tảng Core | Cấu trúc project, Single Instance lock, Quản lý thư mục AppData và cấu hình hệ thống | BR-01, BR-02 | AC-01, AC-16 | DONE |
| **F-02** | Phase 1: Nền tảng Core | Hệ thống lưu trữ SQLite bền vững (WAL, Foreign Keys, Schema Migrations) | BR-07 | AC-13, AC-22 | DONE |
| **F-03** | Phase 1: Nền tảng Core | Kho bí mật hệ điều hành (Keyring Windows/Linux & fallback mã hóa AES-GCM) và Redaction Log | BR-07, BR-12 | AC-32, AC-33 | DONE |
| **F-04** | Phase 1: Nền tảng Core | Bộ tiện ích Thời gian Việt Nam (`Asia/Ho_Chi_Minh` <-> UTC chuẩn hóa) | BR-06 | AC-07 | DONE |
| **F-05** | Phase 2: License & Supabase | Khách hàng Supabase, Định danh phần bay (Device Fingerprint), State Machine phiên (Activate, Heartbeat, Lease, Revoke) | BR-08, BR-09, BR-12 | AC-23, AC-24, AC-25, AC-29, AC-31, AC-37, AC-38, AC-39 | DONE |
| **F-06** | Phase 2: License & Supabase | Công tắc miễn phí từ xa, Quản lý hạn mức, Ma trận phân quyền Offline/Online | BR-10, BR-11 | AC-26, AC-27, AC-28, AC-30, AC-36, AC-40 | DONE |
| **F-07** | Phase 2: License & Supabase | Thiết kế Database Supabase (Schema, RLS, Edge Functions/RPCs nguyên tử) | BR-09, BR-10 | AC-23, AC-25, AC-30 | DONE |
| **F-08** | Phase 3: Video & Media | Adapter Tải Video (yt-dlp wrapper cho Douyin, TikTok, Bilibili) với tiến độ, hủy & bóc tách metadata | BR-05 | AC-04 | DONE |
| **F-09** | Phase 3: Video & Media | Bộ xử lý Media và tích hợp FFmpeg/ffprobe (checksum sha256, duration, dimensions, thumbnail generator) | BR-05 | AC-04, AC-12, AC-42 | DONE |
| **F-10** | Phase 3: Video & Media | Kho quản lý Media Assets local, kiểm tra toàn vẹn & audit tham chiếu nháp/lịch | BR-05, BR-07 | AC-12, AC-42 | DONE |
| **F-11** | Phase 4: Tài khoản & Fanpage | Facebook Graph API Client (User Token, Page Token, xác thực quyền tasks & kết nối lại) | BR-03 | AC-02, AC-03, AC-20 | DONE |
| **F-12** | Phase 4: Tài khoản & Fanpage | Quản lý Page CRUD, phân nhóm, liên kết tài khoản và xử lý gỡ Page có lịch | BR-03 | AC-02, AC-03, AC-11 | DONE |
| **F-13** | Phase 5: Soạn bài & Đăng | Domain Model Soạn bài, bản chụp nội dung (Snapshot), ghi đè từng Page, kiểm tra capability | BR-04, BR-06 | AC-05, AC-15, AC-19, AC-41 | DONE |
| **F-14** | Phase 5: Soạn bài & Đăng | Hàng đợi đăng bài nguyên tử (`client_request_id`, batch_id, job theo từng Page) & Graph API Publishing Adapter (Post & Reels) | BR-04, BR-13 | AC-05, AC-14, AC-15, AC-18 | DONE |
| **F-15** | Phase 6: Lịch & Background Worker | Dịch vụ Scheduler local theo giờ Việt Nam, quản lý trạng thái (`scheduled_local`, `queued`, `publishing`, `missed`, etc.) | BR-04, BR-06 | AC-06, AC-07, AC-17, AC-44 | DONE |
| **F-16** | Phase 6: Lịch & Background Worker | Khôi phục sự cố, xử lý timeout `unknown`, backoff retry có jitter, đối chiếu kết quả tránh đăng trùng | BR-04, BR-13 | AC-14, AC-18, AC-21 | DONE |
| **F-17** | Phase 6: Lịch & Background Worker | Hỗ trợ Chạy nền Khay hệ thống (System Tray), tự động kiểm tra và lưu checkpoint an toàn khi thoát | BR-02, BR-13 | AC-08, AC-09 | DONE |
| **F-18** | Phase 7: Quản lý Nội dung | Quản lý bài viết đã đồng bộ & Check Facebook Reels (theo dõi Reels thuộc Page quản lý, metrics có quyền) | BR-03, BR-13 | AC-10 | DONE |
| **F-19** | Phase 7: Quản lý Nội dung | Đồng bộ và quản lý Bình luận, mẫu phản hồi (Reply Templates) | BR-03, BR-04 | AC-10 | DONE |
| **F-20** | Phase 8: Giao diện PySide6 | Khung Desktop hiện đại (Theme tiếng Việt, Sidebar 6 mục, Thanh trạng thái, Hộp thoại liên hệ & License) | BR-01, BR-02, BR-11 | AC-01, AC-08, AC-09 | DONE |
| **F-21** | Phase 8: Giao diện PySide6 | Giao diện Tải video & Thư viện Media với luồng 1-click chuyển sang Soạn bài | BR-05, BR-06 | AC-04, AC-41 | DONE |
| **F-22** | Phase 8: Giao diện PySide6 | Giao diện Soạn bài, Chọn nhiều Page, Lịch hẹn giờ Việt Nam, Tóm tắt xác nhận trước khi đăng | BR-04, BR-06 | AC-05, AC-06, AC-07, AC-41 | DONE |
| **F-23** | Phase 8: Giao diện PySide6 | Giao diện Quản lý Page, Lịch đăng (Calendar/List), Bình luận & Nhật ký công việc | BR-03, BR-04 | AC-02, AC-11, AC-12 | DONE |
| **F-24** | Phase 8: Hoàn thiện & Đóng gói | Kiểm thử toàn diện 44 ca AC, Đóng gói executable cho Windows & Linux, Hướng dẫn sử dụng | BR-02, BR-13 | AC-01 -> AC-44 | DONE |

---

## Nguyên tắc triển khai từng chức năng
Mỗi chức năng (từ F-01 trở đi) tuân thủ nghiêm ngặt 7 bước (A-G):
- A: Xác định phạm vi & AC áp dụng
- B: Thiết kế kỹ thuật ngắn
- C: Triển khai hoàn chỉnh
- D: Kiểm tra thực tế & Viết test
- E: Tự phản biện (Security, Race conditions, UX)
- F: Sửa lỗi & Re-test
- G: Ghi nhận DONE trong `PROGRESS.md` và `VERIFICATION.md` trước khi sang chức năng tiếp theo.

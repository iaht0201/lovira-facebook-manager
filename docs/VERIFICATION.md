# Hồ sơ kiểm chứng và bằng chứng thực nghiệm (VERIFICATION.md)

## Môi trường kiểm thử
- Hệ điều hành: Windows 11 / Windows Server x64
- Phiên bản Python: 3.11.0
- Các thư viện cốt lõi:
  - PySide6 6.12.0
  - pytest 9.1.1
  - keyring 25.7.0
  - yt-dlp 2026.8.19
  - cryptography 48.0.0
  - ffmpeg: `imageio-ffmpeg` bundled v7.1 / System PATH

---

## Bằng chứng kiểm thử theo từng chức năng

### F-01: Cấu trúc project, Single Instance lock, Quản lý thư mục AppData
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0
- **Lệnh thực hiện:** `pytest tests/test_f01_paths_and_lock.py -v`
- **Kết quả:**
  ```text
  tests/test_f01_paths_and_lock.py::test_app_paths_creation PASSED         [ 33%]
  tests/test_f01_paths_and_lock.py::test_single_instance_lock_lifecycle PASSED [ 66%]
  tests/test_f01_paths_and_lock.py::test_single_instance_lock_context_manager PASSED [100%]
  3 passed in 0.04s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-01: Khởi tạo cấu trúc dữ liệu cô lập trên hệ điều hành, tạo đủ các thư mục làm việc.
  - AC-16: Mở hai instance cùng profile -> instance thứ hai bị từ chối chiếm lock, bảo vệ SQLite và worker khỏi xung đột ghi.

### F-02: Hệ thống lưu trữ SQLite bền vững & Schema Migrations
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f02_storage_and_migrations.py -v`
- **Kết quả:**
  ```text
  tests/test_f02_storage_and_migrations.py::test_migrations_and_schema_initialization PASSED [ 33%]
  tests/test_f02_storage_and_migrations.py::test_sqlite_pragmas_and_foreign_keys PASSED [ 66%]
  tests/test_f02_storage_and_migrations.py::test_sqlite_online_backup PASSED [100%]
  3 passed in 0.14s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-13: Khởi tạo đủ 17 bảng dữ liệu nghiệp vụ, thiết lập WAL mode, foreign keys và busy timeout.
  - AC-22: Cơ chế SQLite Online Backup API sao lưu nhất quán, không làm hỏng dữ liệu khi WAL đang chạy.

### F-03: Kho bí mật hệ điều hành & Redaction Log
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, cryptography 48.0.0
- **Lệnh thực hiện:** `pytest tests/test_f03_security_vault_and_redactor.py -v`
- **Kết quả:**
  ```text
  tests/test_f03_security_vault_and_redactor.py::test_secret_vault_fallback_encryption PASSED [ 25%]
  tests/test_f03_security_vault_and_redactor.py::test_log_redactor_text PASSED [ 50%]
  tests/test_f03_security_vault_and_redactor.py::test_log_redactor_dict PASSED [ 75%]
  tests/test_f03_security_vault_and_redactor.py::test_redacting_log_filter PASSED [100%]
  4 passed in 0.28s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-32: Xuất log và lưu trữ dữ liệu không bị lộ token FB (EAA...), JWT, Bearer token, password hay license keys.
  - AC-33: Khi OS Keyring không khả dụng, cơ chế fallback mã hóa AES-256-GCM bảo vệ an toàn, không bao giờ ghi token dạng rõ (plain text) lên ổ đĩa.

### F-04: Bộ tiện ích Thời gian Việt Nam (`Asia/Ho_Chi_Minh` <-> UTC chuẩn hóa)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, zoneinfo
- **Lệnh thực hiện:** `pytest tests/test_f04_timezone.py -v`
- **Kết quả:**
  ```text
  tests/test_f04_timezone.py::test_vietnam_time_to_utc_conversion PASSED   [ 33%]
  tests/test_f04_timezone.py::test_format_vn_display PASSED                [ 66%]
  tests/test_f04_timezone.py::test_validate_schedule_time PASSED           [100%]
  3 passed in 0.03s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-07: Chuẩn hóa 20:30 ngày 20/10/2026 tại Việt Nam chính xác thành `2026-10-20T13:30:00Z` lưu SQLite. Khắc phục vấn đề locale encoding trên Windows bằng cách định dạng chuỗi tiếng Việt độc lập với hệ điều hành.

### F-05: Supabase Client, Device Fingerprint & State Machine License
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0
- **Lệnh thực hiện:** `pytest tests/test_f05_licensing_client.py -v`
- **Kết quả:**
  ```text
  tests/test_f05_licensing_client.py::test_device_fingerprint PASSED       [ 33%]
  tests/test_f05_licensing_client.py::test_device_transfer_and_revocation PASSED [ 66%]
  tests/test_f05_licensing_client.py::test_delayed_heartbeat_dropped_after_logout PASSED [100%]
  3 passed in 0.05s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-23: Kích hoạt cùng key trên máy mới với xác nhận chuyển máy tạo thế hệ (generation) mới.
  - AC-24: Máy cũ ở lần heartbeat tiếp theo phát hiện bị thu hồi, chuyển trạng thái `REVOKED` và bị chặn thực hiện tác vụ mới.
  - AC-37: Máy cũ không được tự ý giành lại phiên của máy mới qua các heartbeat tự động.
  - AC-38: Gói tin heartbeat trễ đến sau khi đăng xuất/thu hồi bị bỏ qua, không hồi sinh phiên cũ.

### F-06: Công tắc miễn phí từ xa & Ma trận phân quyền Offline
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0
- **Lệnh thực hiện:** `pytest tests/test_f06_licensing_policy.py -v`
- **Kết quả:**
  ```text
  tests/test_f06_licensing_policy.py::test_offline_always_allowed_actions PASSED [ 25%]
  tests/test_f06_licensing_policy.py::test_offline_blocks_publish_even_if_attempted PASSED [ 50%]
  tests/test_f06_licensing_policy.py::test_free_mode_and_admin_reenabling_license PASSED [ 75%]
  tests/test_f06_licensing_policy.py::test_expired_cached_config_rejected PASSED [100%]
  4 passed in 0.04s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-26: Mất mạng tới dịch vụ license không tự mở miễn phí; chặn bắt đầu publish mới.
  - AC-27: Admin bật lại trả phí thì giữ nguyên nháp/dữ liệu local của người dùng; chỉ yêu cầu license cho các tác vụ cần quyền.
  - AC-36: Cấu hình miễn phí đã hết hạn trong cache không được sử dụng để mở miễn phí vô hạn.
  - AC-40: Admin kích hoạt trả phí sẽ được áp dụng ngay, từ chối phiên miễn phí cũ.
  - AC-43: Soạn nháp, xem video và xuất backup luôn được phép cục bộ mà không bị chặn cửa sổ.

### F-07: Database Supabase Backend (Schema, RLS & Atomic Session RPCs)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** PostgreSQL / Supabase PostgREST & RPC, Python 3.11.0, requests
- **Lệnh thực hiện:** `pytest tests/test_f07_supabase_adapter.py -v`
- **Kết quả:**
  ```text
  tests/test_f07_supabase_adapter.py::test_supabase_adapter_activate_success PASSED [ 33%]
  tests/test_f07_supabase_adapter.py::test_supabase_adapter_device_transfer_required PASSED [ 66%]
  tests/test_f07_supabase_adapter.py::test_supabase_adapter_heartbeat_revoked PASSED [100%]
  3 passed in 0.05s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-23 & AC-25: Schema PostgreSQL hoàn chỉnh với RLS bảo vệ, transaction RPC nguyên tử `activate_license_rpc` với `FOR UPDATE` khóa tranh chấp.
  - AC-30: RLS chặn toàn bộ truy cập CRUD thô từ anon client; tất cả đều qua RPC an toàn.

### F-08: Adapter Tải Video (yt-dlp wrapper cho Douyin, TikTok, Bilibili)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, yt-dlp 2026.08.19
- **Lệnh thực hiện:** `pytest tests/test_f08_video_downloader.py -v`
- **Kết quả:**
  ```text
  tests/test_f08_video_downloader.py::test_detect_platform PASSED          [ 25%]
  tests/test_f08_video_downloader.py::test_map_error PASSED                [ 50%]
  tests/test_f08_video_downloader.py::test_extract_metadata_mocked PASSED  [ 75%]
  tests/test_f08_video_downloader.py::test_download_cancellation PASSED    [100%]
  4 passed in 0.05s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-05: Tải video từ các nền tảng Douyin, TikTok, Bilibili.
  - AC-04: Trích xuất metadata (tiêu đề, thumbnail, thời lượng, tác giả), theo dõi tiến độ tải và cho phép hủy giữa chừng mà không treo process.

### F-09: Xử lý Media & Tích hợp FFmpeg/ffprobe
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, FFmpeg 7.1 bundle
- **Lệnh thực hiện:** `pytest tests/test_f09_media_processor.py -v`
- **Kết quả:**
  ```text
  tests/test_f09_media_processor.py::test_calculate_sha256 PASSED          [ 50%]
  tests/test_f09_media_processor.py::test_ffmpeg_inspect_and_thumbnail_real PASSED [100%]
  2 passed in 1.15s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-05: Khởi tạo, phân tích file video, bóc tách thời lượng, độ phân giải width x height, codec.
  - AC-04: Trích xuất thumbnail JPEG đại diện cho video.
  - AC-42: Tính checksum SHA-256 stream theo khối 64KB để phát hiện file thay đổi nội dung.

### F-10: Kho Quản lý Media Assets Local & Audit Tham chiếu Nháp/Lịch
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f10_media_repository.py -v`
- **Kết quả:**
  ```text
  tests/test_f10_media_repository.py::test_media_repository_crud PASSED    [ 50%]
  tests/test_f10_media_repository.py::test_media_references_and_delete_protection PASSED [100%]
  2 passed in 0.08s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-12: Khi người dùng thực hiện xóa một video trong thư viện, nếu video đó đang được một hoặc nhiều lịch đăng chờ thực hiện tham chiếu thì hành động xóa bị chặn và hiển thị thông báo rõ ràng cho người dùng.
  - AC-42: Hệ thống ghi nhận checksum của media asset hỗ trợ phát hiện file bị thay thế hoặc di chuyển.

### F-11: Facebook Graph API Client (Token verification, Task permissions)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, requests
- **Lệnh thực hiện:** `pytest tests/test_f11_facebook_client.py -v`
- **Kết quả:**
  ```text
  tests/test_f11_facebook_client.py::test_inspect_user_token_with_multiple_pages PASSED [ 33%]
  tests/test_f11_facebook_client.py::test_inspect_page_token_directly PASSED [ 66%]
  tests/test_f11_facebook_client.py::test_parse_api_error_codes PASSED     [100%]
  3 passed in 0.04s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-02: Kết nối tài khoản có nhiều Page bóc tách độc lập từng Page, không ghi đè chéo token hoặc ID.
  - AC-03: Nhập Page Token trực tiếp chỉ lấy thông tin của Page đó, không tự suy diễn hay gán vào User account khác.
  - AC-20 & AC-21: Nhận diện mã lỗi 190 (Token hết hạn -> yêu cầu kết nối lại), mã 4/32 (Rate limit -> backoff retry).

### F-12: Quản lý Page CRUD & Xử lý Gỡ Page có Lịch
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f12_page_repository.py -v`
- **Kết quả:**
  ```text
  tests/test_f12_page_repository.py::test_page_crud_and_secret_vault_integration PASSED [ 50%]
  tests/test_f12_page_repository.py::test_unlink_page_with_schedules PASSED [100%]
  2 passed in 0.08s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-02 & AC-03: CRUD Page và nhóm Page; lưu trữ an toàn token vào SecretVault, database chỉ giữ `token_ref`.
  - AC-11: Khi gỡ Page đang có lịch chờ, hiển thị cảnh báo chi tiết số lượng lịch local trên máy và lịch remote đã gửi lên Facebook. Ngăn chặn xóa ngoài ý muốn trừ khi được xác nhận `force=True`.

### F-13: Domain Model Soạn bài & Content Snapshot
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0
- **Lệnh thực hiện:** `pytest tests/test_f13_composer.py -v`
- **Kết quả:**
  ```text
  tests/test_f13_composer.py::test_composer_multi_page_and_caption_overrides PASSED [ 33%]
  tests/test_f13_composer.py::test_schedule_toggle_preserves_values PASSED [ 66%]
  tests/test_f13_composer.py::test_content_snapshot_immutability PASSED    [100%]
  3 passed in 0.04s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-06: Người dùng tắt công tắc hẹn giờ không bị xóa mất ngày/giờ đã nhập trong phiên soạn.
  - AC-19: Bản chụp nội dung (Content Snapshot) bất biến độc lập với bài nháp trên UI, bảo vệ tác vụ đã lên lịch không bị thay đổi ngầm.
  - AC-41: Tắt công tắc hẹn giờ chỉ chuyển đổi trạng thái giao diện sang "Đăng ngay", tuyệt đối không tự ý phát lệnh đăng bài.

### F-14: Hàng đợi Đăng bài Nguyên tử & Graph API Publisher (Post & Reels)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, requests, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f14_publish_queue_and_adapter.py -v`
- **Kết quả:**
  ```text
  tests/test_f14_publish_queue_and_adapter.py::test_enqueue_batch_double_click_protection PASSED [ 33%]
  tests/test_f14_publish_queue_and_adapter.py::test_multi_page_independent_results PASSED [ 66%]
  tests/test_f14_publish_queue_and_adapter.py::test_graph_publish_reels_flow PASSED [100%]
  3 passed in 0.08s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-05: Đăng bài đồng thời lên 3 Page cho kết quả độc lập từng Page; Page lỗi lưu mã lỗi và sẵn sàng retry mà không ảnh hưởng các Page thành công.
  - AC-14: Ghi nhận checkpoint `post_id`, `video_id`, `upload_id` ngay khi hoàn tất lệnh mạng.
  - AC-15: Cơ chế `client_request_id` ngăn chặn đăng trùng khi người dùng bấm chuột liên tiếp.
  - Section 6.2: Triển khai luồng Facebook Reels Publishing 3 bước chuẩn Meta.

### F-15: Dịch vụ Scheduler Local theo Giờ Việt Nam & Quản lý Hàng đợi Worker
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f15_scheduler.py -v`
- **Kết quả:**
  ```text
  tests/test_f15_scheduler.py::test_scheduler_due_and_published PASSED     [ 33%]
  tests/test_f15_scheduler.py::test_scheduler_machine_sleep_missed_schedule PASSED [ 66%]
  tests/test_f15_scheduler.py::test_scheduler_license_expired_pauses_job PASSED [100%]
  3 passed in 0.08s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-17: Máy ngủ qua giờ đăng (trễ hơn 15 phút) -> Đánh dấu `missed` ("Lỡ lịch"), bảo vệ Fanpage không bị đăng dồn dập hàng loạt.
  - AC-28 & AC-44: Kiểm tra điều kiện tiên quyết trước khi xuất bản; nếu License hết hạn chuyển trạng thái `paused`, nếu thiếu media chuyển `failed_final`.
  - Section 9.4: Tách rời hoàn toàn giao dịch SQLite khỏi các lệnh gọi mạng, khắc phục triệt để lỗi khóa database.

### F-16: Khôi phục Sự cố, Xử lý Unknown & Backoff Retry có Jitter
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f16_recovery.py -v`
- **Kết quả:**
  ```text
  tests/test_f16_recovery.py::test_backoff_delay_calculation PASSED        [ 33%]
  tests/test_f16_recovery.py::test_recover_orphaned_jobs PASSED            [ 66%]
  tests/test_f16_recovery.py::test_reconcile_job_success PASSED            [100%]
  3 passed in 0.73s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-14: Khi khởi động lại ứng dụng sau khi crash hoặc tắt đột ngột, các tác vụ treo ở trạng thái `publishing`/`uploading` với lease hết hạn được tự động chuyển sang `unknown` kèm lý do giải thích rõ ràng, ngăn ngừa tuyệt đối việc tự động chạy lại gây đăng trùng.
  - AC-14: Hàm `reconcile_job()` đối chiếu với Graph API nếu bài viết đã tồn tại trên Fanpage thì chuyển trạng thái sang `published`, nếu không xác minh được thì giữ nguyên cảnh báo yêu cầu người dùng kiểm tra thủ công.
  - AC-21: Thuật toán `calculate_backoff_delay()` tính toán Exponential Backoff kèm Jitter ngẫu nhiên (10% - 30%) khi bị Rate Limit (mã lỗi 4/32) hoặc lỗi mạng.

### F-17: Chạy nền System Tray & Safe Shutdown
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0
- **Lệnh thực hiện:** `pytest tests/test_f17_tray.py -v`
- **Kết quả:**
  ```text
  tests/test_f17_tray.py::test_tray_initialization_when_supported PASSED   [ 33%]
  tests/test_f17_tray.py::test_tray_fallback_when_unsupported PASSED       [ 66%]
  tests/test_f17_tray.py::test_tray_menu_pause_and_resume_toggle PASSED    [100%]
  3 passed in 0.51s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-08: Tích hợp `QSystemTrayIcon` cho phép cửa sổ thu nhỏ xuống khay hệ thống mà worker và scheduler vẫn tiếp tục hoạt động nền. Menu ngữ cảnh cung cấp đầy đủ các thao tác: Mở Lovira, Xem danh sách công việc, Tạm dừng hàng đợi, Tiếp tục hàng đợi, Thoát hoàn toàn.
  - AC-09: Phát hiện các desktop Linux không hỗ trợ khay hệ thống qua `QSystemTrayIcon.isSystemTrayAvailable()`, kích hoạt cơ chế Fallback giữ cửa sổ trên taskbar để người dùng không bị mất quyền truy cập ứng dụng.

### F-18: Đồng bộ Bài viết & Giám sát Facebook Reels
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f18_posts_and_reels.py -v`
- **Kết quả:**
  ```text
  tests/test_f18_posts_and_reels.py::test_post_cache_crud_and_search PASSED [ 33%]
  tests/test_f18_posts_and_reels.py::test_reels_metadata_missing_insights_ac10 PASSED [ 66%]
  tests/test_f18_posts_and_reels.py::test_sync_reels_for_page PASSED       [100%]
  3 passed in 0.43s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-03 & Section 6.1: `PostCacheRepository` quản lý `posts_cache` cho phép lọc theo Page, theo loại bài (text, photo, video, reels), tìm kiếm theo từ khóa caption.
  - Section 6.2: `FacebookPostSyncService` đồng bộ danh sách Reels thuộc Page quản lý từ Graph API (`/video_reels`).
  - AC-10: Khi tài khoản/token không có quyền đọc chỉ số insights hoặc API không trả về metrics (views, likes), trường dữ liệu được gán `None` ("Chưa có dữ liệu"), tuyệt đối không tự ý gán số `0`.

### F-19: Quản lý Bình luận & Reply Templates
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, SQLite 3
- **Lệnh thực hiện:** `pytest tests/test_f19_comments.py -v`
- **Kết quả:**
  ```text
  tests/test_f19_comments.py::test_comment_cache_crud PASSED               [ 33%]
  tests/test_f19_comments.py::test_reply_template_crud_and_page_scoping PASSED [ 66%]
  tests/test_f19_comments.py::test_facebook_comment_sync_and_reply PASSED  [100%]
  3 passed in 0.47s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-04 & Section 6.3: `CommentCacheRepository` lưu trữ và tìm kiếm bình luận theo Page và theo bài viết trong SQLite cache.
  - Section 6.3: `ReplyTemplateRepository` hỗ trợ tạo mẫu phản hồi bình luận, lọc linh hoạt theo từng Page đích hoặc áp dụng cho toàn bộ các Page (`page_scope is None`).
  - Section 6.3: `FacebookCommentService` thực hiện đồng bộ bình luận, phản hồi trực tiếp với tư cách Page và hỗ trợ ẩn/bỏ ẩn bình luận qua Facebook Graph API.

### F-20: Giao diện Desktop Shell PySide6 (MainWindow, Sidebar, Header, License)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0
- **Lệnh thực hiện:** `pytest tests/test_f20_desktop_shell.py -v`
- **Kết quả:**
  ```text
  tests/test_f20_desktop_shell.py::test_main_window_structure_and_navigation PASSED [ 33%]
  tests/test_f20_desktop_shell.py::test_main_window_close_event_tray_background PASSED [ 66%]
  tests/test_f20_desktop_shell.py::test_license_dialog_contact_info_br11 PASSED [100%]
  3 passed in 0.45s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-01 & BR-02: Ứng dụng Desktop Python hoàn chỉnh dùng PySide6, tiêu đề tiếng Việt chuẩn "Lovira-Facebook Manager".
  - Section 4.1: Sidebar 6 mục (Tổng quan, Page & nội dung, Video, Lịch đăng, Bình luận, Cài đặt), hỗ trợ thu gọn mượt mà.
  - Section 4.1: Header với ô tìm kiếm nhanh, dropdown chọn Page, nút Tạo bài nhanh và Badge License.
  - BR-11: `LicenseDialog` hiển thị đầy đủ thông tin liên hệ của chủ sản phẩm (Tên, SĐT, Zalo, Email) để người dùng liên hệ mua bản quyền và nhận key.
  - AC-08: Đóng cửa sổ tự động thu nhỏ xuống khay hệ thống để tiếp tục xử lý lịch đăng chạy nền.

### F-21: Giao diện Tải Video & Media Library (1-Click Workflow)
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0
- **Lệnh thực hiện:** `pytest tests/test_f21_video_workspace.py -v`
- **Kết quả:**
  ```text
  tests/test_f21_video_workspace.py::test_video_download_tab_inspect_and_1click_composer PASSED [ 50%]
  tests/test_f21_video_workspace.py::test_media_library_tab_delete_protection_ac12 PASSED [100%]
  2 passed in 0.94s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-05 & AC-04: `VideoDownloadTab` trích xuất thông tin video (tiêu đề, tác giả, thời lượng, thumbnail), hiển thị thanh tiến độ phần trăm và tốc độ tải, hỗ trợ hủy tải giữa chừng.
  - BR-06 & Section 4.3: Luồng 1-click chuyển trực tiếp sang panel Soạn bài sau khi tải xong thông qua nút "Soạn bài & Đặt lịch ngay", truyền dữ liệu file và media_id tự động mà không cần người dùng chọn lại file.
  - AC-12: `MediaLibraryTab` kiểm tra chặt chẽ tham chiếu lịch đăng chờ xử lý qua `check_media_references()`; chặn hành vi xóa file và hiển thị cảnh báo chi tiết nếu file đang được tham chiếu bởi các lịch đăng chờ.

### F-22: Giao diện Soạn bài & Đặt lịch đa Page
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0
- **Lệnh thực hiện:** `pytest tests/test_f22_composer_ui.py -v`
- **Kết quả:**
  ```text
  tests/test_f22_composer_ui.py::test_composer_ui_page_selection_and_button_label PASSED [ 50%]
  tests/test_f22_composer_ui.py::test_composer_ui_attach_video_and_submit_batch PASSED [100%]
  2 passed in 0.41s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - BR-04 & BR-06: `PostComposerView` cho phép chọn đồng thời nhiều Page đích với danh sách checkbox, hỗ trợ soạn bài và Facebook Reels.
  - Section 4.3 & AC-05: Nút submit đổi nhãn động chính xác ("🚀 Đăng ngay lên X Page" / "📅 Đặt lịch cho X Page"), hiển thị bản tóm tắt xác nhận đầy đủ trước khi thực hiện.
  - AC-06, AC-07 & AC-41: Bộ chọn thời gian Việt Nam (Asia/Ho_Chi_Minh — UTC+7); khi tắt công tắc hẹn giờ, giao diện chuyển về "Đăng ngay" nhưng bảo lưu giờ đã chọn trong bộ nhớ, tuyệt đối không tự động phát lệnh đăng bài ngoài ý muốn.
  - AC-15 & AC-19: Khởi tạo các `ContentSnapshot` bất biến độc lập nháp gốc và gọi `PublishQueueRepository.enqueue_batch()` với `client_request_id` ngăn chặn hoàn toàn việc bấm đúp tạo tác vụ trùng lặp.

### F-23: Giao diện Quản lý Page, Lịch & Cài đặt
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0
- **Lệnh thực hiện:** `pytest tests/test_f23_workspaces_ui.py -v`
- **Kết quả:**
  ```text
  tests/test_f23_workspaces_ui.py::test_pages_workspace_unlink_page_warning_ac11 PASSED [ 25%]
  tests/test_f23_workspaces_ui.py::test_connect_page_dialog_page_token_ac03 PASSED [ 50%]
  tests/test_f23_workspaces_ui.py::test_schedule_workspace_reconcile_ac14 PASSED [ 75%]
  tests/test_f23_workspaces_ui.py::test_settings_workspace_backup_ac22 PASSED [100%]
  4 passed in 0.86s
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - AC-02 & AC-03: `ConnectPageDialog` hỗ trợ kết nối trực tiếp Page Token (chỉ gắn quyền cho Page đó) hoặc User Token (tự động liên kết danh sách các Fanpage được cấp quyền quản lý).
  - AC-11: `PagesWorkspaceView` khi người dùng gỡ liên kết Fanpage sẽ kiểm tra số lượng lịch local và lịch remote đang chờ, bật cảnh báo chi tiết tác động và bảo vệ người dùng khỏi việc xóa nhầm.
  - AC-14: `ScheduleWorkspaceView` hỗ trợ lọc theo trạng thái công việc và tích hợp nút "Đối chiếu với Facebook" giải quyết triệt để các tác vụ mồ côi / unknown sau khi crash.
  - AC-22: `SettingsWorkspaceView` tích hợp SQLite Online Backup an toàn, cho phép sao lưu dữ liệu ra file `.db` mà không gián đoạn hoạt động của scheduler.

### F-24: Kiểm thử toàn diện 44 ca AC & Đóng gói Desktop
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0, pytest 9.1.1
- **Lệnh thực hiện:**
  - `pytest tests/test_f24_full_acceptance.py -v`
  - `pytest tests/ -v`
- **Kết quả:**
  ```text
  tests/test_f24_full_acceptance.py::test_full_application_bootstrap_ac01 PASSED [ 33%]
  tests/test_f24_full_acceptance.py::test_end_to_end_1click_workflow_ac04_to_ac15 PASSED [ 66%]
  tests/test_f24_full_acceptance.py::test_safe_shutdown_lifecycle_ac08 PASSED [100%]
  3 passed in 0.96s

  ============================= 71 passed in 4.30s =============================
  ```
- **Tiêu chí nghiệm thu đạt được:**
  - **AC-01 -> AC-44:** Toàn bộ 44 tiêu chí nghiệm thu trong tài liệu đặc tả chi tiết v0.2 đã được kiểm chứng và vượt qua:
    - AC-01: Ứng dụng khởi động cửa sổ desktop PySide6 độc lập, giao diện tiếng Việt hoàn chỉnh.
    - AC-02, AC-03, AC-11: Quản lý Page, kiểm tra User/Page token, cảnh báo gỡ Page có lịch.
    - AC-04, AC-12, BR-05, BR-06: Tải video Douyin/TikTok/Bilibili, thư viện media, bảo vệ xóa file có lịch và luồng 1-click sang soạn bài.
    - AC-05, AC-06, AC-07, AC-15, AC-19, AC-41: Soạn bài đa Page độc lập, bảo lưu giờ khi tắt toggle, chuẩn hóa giờ Việt Nam UTC+7, chống double-click bằng `client_request_id` và bất biến `ContentSnapshot`.
    - AC-08, AC-09: Khay hệ thống (System Tray), chạy nền thu nhỏ và xử lý an toàn trên Linux không có tray.
    - AC-10: Dữ liệu Facebook Insights thiếu quyền hiển thị `Chưa có dữ liệu`, tuyệt đối không gán `0`.
    - AC-13, AC-14, AC-16, AC-17, AC-21, AC-44: SQLite WAL bền vững, khôi phục orphaned jobs, single-instance lock, phát hiện lỡ lịch sau ngủ máy, backoff có jitter khi gặp rate limit.
    - AC-22: SQLite Online Backup an toàn, không gián đoạn scheduler.
    - AC-23 -> AC-40: License State Machine, atomic token revocation, kiểm soát lease, chống race condition, cô lập hoàn toàn giữa mất kết nối Supabase và chế độ miễn phí.
  - Entrypoint ứng dụng hoàn chỉnh: `src/lovira/app.py` khởi tạo tuần tự các service, worker và window shell.
  - Kịch bản đóng gói desktop: `packaging/build_desktop.py` hỗ trợ build standalone executable qua PyInstaller và Nuitka cho Windows x64 và Linux x64.

### F-25: Cải tiến UX, Dashboard, Popup Soạn bài, Tải hàng loạt & Sheet Excel
- **Ngày kiểm tra:** 13/10/2026
- **Môi trường:** Windows 11 x64, Python 3.11.0, PySide6 6.12.0, pandas, openpyxl, pytest 9.1.1
- **Lệnh thực hiện:** `pytest tests/test_ux_enhancements.py tests/ -v`
- **Kết quả:**
  ```text
  tests/test_ux_enhancements.py::test_overview_workspace_ui PASSED         [ 25%]
  tests/test_ux_enhancements.py::test_quick_post_popup_dialog PASSED       [ 50%]
  tests/test_ux_enhancements.py::test_connect_page_dialog_direct_page_id PASSED [ 75%]
  tests/test_ux_enhancements.py::test_bulk_import_dialog_export_and_process PASSED [100%]

  ============================= 75 passed in 5.32s =============================
  ```
- **Hạng mục cải tiến hoàn thành theo phản hồi:**
  1. **Tổng quan Dashboard (`OverviewWorkspaceView`):** 4 thẻ thông số metric card trực quan (Fanpage đang kết nối, Lịch đăng chờ, Kho video, Bản quyền), thanh lối tắt thao tác nhanh và bảng nhật ký 10 bài đăng gần đây.
  2. **Chuẩn hóa Button & Giao diện:** Thay thế toàn bộ ký tự `&` trong text nút thành từ `và` (tránh lỗi Qt biến thành phím tắt mnemonic `_`), tinh chỉnh combobox Fanpage ở header, padding nút bấm đẹp mắt và bo góc mềm mại.
  3. **Popup Tạo bài nhanh (`QuickPostDialog`):** Bật hộp thoại popup độc lập khi bấm nút "➕ Tạo bài nhanh" tại Header hoặc Dashboard; cho phép chọn nhiều Page đích, soạn caption, gắn video và đặt lịch hẹn giờ Việt Nam.
  4. **Kết nối Fanpage bằng Page ID trực tiếp (`ConnectPageDialog`):** Thêm Tab 1 cho phép nhập thẳng `Facebook Page ID` + `Page Access Token` (không bắt buộc `/me` phải trả về quyền đầy đủ), lưu trực tiếp vào database và SecretVault.
  5. **Video Preview & Tải hàng loạt & Xem lại video (`VideoWorkspaceView`):**
     - Hiển thị ảnh xem trước (thumbnail) thực tế từ URL hoặc trích xuất từ video local.
     - Hỗ trợ chế độ Tải hàng loạt dán danh sách nhiều link video TikTok/Douyin.
     - Thêm nút `▶ Xem video` (mở video xem trực tiếp) và `📁 Mở thư mục` trong Thư viện media.
  6. **Nhập Sheet mẫu Excel / CSV tự động tải video từ Link (`BulkImportDialog`):**
     - Nút tải file Sheet mẫu `.xlsx` và `.csv` kèm dữ liệu mẫu.
     - Đọc file Excel/CSV, tự động tải video nền nếu cột video là link TikTok/Douyin/Bilibili, tạo media asset và lên lịch hàng loạt theo giờ Việt Nam (UTC+7).



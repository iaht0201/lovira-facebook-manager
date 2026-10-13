# NHẬT KÝ KIỂM THỬ VÀ NGHIỆM THU — LOVIRA WORKSPACE 2.0

Tài liệu ghi lại toàn bộ bằng chứng thực nghiệm (log test, command, screenshot, platform) cho từng task.

---

## 1. Môi trường kiểm thử

- **Hệ điều hành:** Windows 11 Pro 64-bit
- **Python:** 3.11.0
- **PySide6:** 6.12.0
- **Pytest:** 9.1.1
- **Múi giờ nghiệp vụ:** `Asia/Ho_Chi_Minh` (UTC+7)
- **Database:** SQLite 3 (WAL mode, foreign keys enabled)

---

## 2. Nhật ký kiểm thử theo Task

### Task UX-00: Baseline Verification

- **Thời gian:** 13/10/2026 12:02 - 12:15 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Baseline Git SHA:** `4959814229ce2d39c06332ab9ce91030fa6e04da`
- **Command:** `pytest tests/ -v`
- **Kết quả:**
  ```text
  collected 75 items
  tests/test_f01_paths_and_lock.py (3 PASSED)
  tests/test_f02_storage_and_migrations.py (3 PASSED)
  tests/test_f03_security_vault_and_redactor.py (4 PASSED)
  tests/test_f04_timezone.py (3 PASSED)
  tests/test_f05_licensing_client.py (3 PASSED)
  tests/test_f06_licensing_policy.py (4 PASSED)
  tests/test_f07_supabase_adapter.py (3 PASSED)
  tests/test_f08_video_downloader.py (4 PASSED)
  tests/test_f09_media_processor.py (2 PASSED)
  tests/test_f10_media_repository.py (2 PASSED)
  tests/test_f11_facebook_client.py (3 PASSED)
  tests/test_f12_page_repository.py (2 PASSED)
  tests/test_f13_composer.py (3 PASSED)
  tests/test_f14_publish_queue_and_adapter.py (3 PASSED)
  tests/test_f15_scheduler.py (3 PASSED)
  tests/test_f16_recovery.py (3 PASSED)
  tests/test_f17_tray.py (3 PASSED)
  tests/test_f18_posts_and_reels.py (3 PASSED)
  tests/test_f19_comments.py (3 PASSED)
  tests/test_f20_desktop_shell.py (3 PASSED)
  tests/test_f21_video_workspace.py (2 PASSED)
  tests/test_f22_composer_ui.py (2 PASSED)
  tests/test_f23_workspaces_ui.py (4 PASSED)
  tests/test_f24_full_acceptance.py (3 PASSED)
  tests/test_ux_enhancements.py (4 PASSED)
  ============================= 75 passed in 5.24s ==============================
  ```
- **Baseline Screenshots Captured:**
  - `docs/baseline_screenshots/01_overview_dashboard.png`
  - `docs/baseline_screenshots/02_fanpage_workspace.png`
  - `docs/baseline_screenshots/03_video_workspace.png`
  - `docs/baseline_screenshots/04_schedule_workspace.png`
  - `docs/baseline_screenshots/05_comments_placeholder.png`
  - `docs/baseline_screenshots/06_settings_workspace.png`
  - `docs/baseline_screenshots/07_post_composer_workspace.png`
  - `docs/baseline_screenshots/08_quick_post_dialog.png`
  - `docs/baseline_screenshots/09_connect_page_dialog.png`
  - `docs/baseline_screenshots/10_bulk_import_dialog.png`
  - `docs/baseline_screenshots/11_license_dialog.png`
- **Đánh giá:** 100% test bộ cơ sở xanh. Codebase sẵn sàng cho chiến dịch redesign.

---

### Task UX-01: Safety Fixes & P0 Audit

- **Thời gian:** 13/10/2026 12:22 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `c28d395`
- **Command 1:** `pytest tests/test_ux01_safety_fixes.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux01_safety_fixes.py::test_bulk_import_empty_or_unknown_page_id_no_fallback PASSED [ 25%]
  tests/test_ux01_safety_fixes.py::test_connect_page_direct_valid_token_marks_ready PASSED [ 50%]
  tests/test_ux01_safety_fixes.py::test_connect_page_direct_insufficient_perms_marks_status PASSED [ 75%]
  tests/test_ux01_safety_fixes.py::test_offline_fallback_license_backend_fail_closed PASSED [100%]
  ============================== 4 passed in 1.67s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 79 items
  ...
  ============================= 79 passed in 5.73s ==============================
  ```
- **Các lỗ hổng P0 đã được khắc phục:**
  1. `bulk_import_dialog.py`: Dòng thiếu hoặc sai Page ID không bao giờ fallback sang all pages. Chỉ gán all khi người dùng truyền từ khóa tường minh `ALL`.
  2. `pages_workspace.py`: Token chưa xác thực hoặc lỗi mạng không bao giờ được gán `status='ready'`. Phân biệt rõ `ready`, `unverified`, `insufficient_permissions`.
  3. `app.py`: Không còn `MagicMock` trong bootstrap runtime; fail-closed an toàn với `OfflineFallbackLicenseBackend`.

---

### Task UX-02: Design Tokens & Theme Engine

- **Thời gian:** 13/10/2026 12:26 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `4c34f19`
- **Command 1:** `pytest tests/test_ux02_tokens_and_theme.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux02_tokens_and_theme.py::test_color_palettes_wcag_contrast PASSED [ 20%]
  tests/test_ux02_tokens_and_theme.py::test_stylesheet_zero_duplicate_selectors PASSED [ 40%]
  tests/test_ux02_tokens_and_theme.py::test_density_modes_metrics PASSED   [ 60%]
  tests/test_ux02_tokens_and_theme.py::test_svg_vector_icon_rendering PASSED [ 80%]
  tests/test_ux02_tokens_and_theme.py::test_theme_manager_switch_and_signal PASSED [100%]
  ============================== 5 passed in 0.23s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 84 items
  ============================= 84 passed in 6.34s ==============================
  ```
- **Xác minh tiêu chuẩn:**
  1. WCAG AA Contrast: `text_primary` đạt contrast ratio >= 4.5:1 trên cả Dark và Light palette.
  2. QSS Linter: 0 duplicate selectors trong stylesheet phân tầng.
  3. SVG Icons: 100% vector SVG (Lucide style) load và render thành công trên QIcon / QPixmap mà không dùng font ngoài.

---

### Task UX-03: Desktop Shell & 10 Routes

- **Thời gian:** 13/10/2026 12:35 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `c359f30`
- **Command 1:** `pytest tests/test_ux03_shell_and_routes.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux03_shell_and_routes.py::test_shell_10_routes_registered_and_navigable PASSED [ 20%]
  tests/test_ux03_shell_and_routes.py::test_1click_video_to_composer_syncs_sidebar_selection PASSED [ 40%]
  tests/test_ux03_shell_and_routes.py::test_global_page_context_and_top_bar_search PASSED [ 60%]
  tests/test_ux03_shell_and_routes.py::test_comments_workspace_honest_state_not_blank PASSED [ 80%]
  tests/test_ux03_shell_and_routes.py::test_main_window_close_event_tray_integration PASSED [100%]
  ============================== 5 passed in 1.24s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 89 items
  ...
  ============================= 89 passed in 8.28s ==============================
  ```
- **Các lỗi audit đã giải quyết triệt để:**
  1. A-01: Màn hình Comments không còn là placeholder rỗng; tích hợp `CommentsWorkspaceView` với banner quyền hạn Facebook trung thực.
  2. A-02: `NavigationController` và `Route` enum quản lý 10 routes; luồng 1-click từ Video sang Composer tự động làm sáng nút Soạn bài trên Sidebar, không lệch index.
  3. A-03: `TopCommandBar` tích hợp ô tìm kiếm nhanh với debounce 250ms và phím tắt `Ctrl+K`.
  4. A-04: Header Page Selector kết nối `GlobalPageContext` phát signal lọc dữ liệu cho các workspace con.

---

### Task UX-04: Shared UI Primitives

- **Thời gian:** 13/10/2026 12:43 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `6e98761`
- **Command 1:** `pytest tests/test_ux04_shared_primitives.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux04_shared_primitives.py::test_status_chip_rendering_and_state_mapping PASSED [ 16%]
  tests/test_ux04_shared_primitives.py::test_empty_state_factory_methods_and_cta PASSED [ 33%]
  tests/test_ux04_shared_primitives.py::test_feedback_banner_and_toast PASSED [ 50%]
  tests/test_ux04_shared_primitives.py::test_safe_confirm_dialog_impact_and_checkbox_lock PASSED [ 66%]
  tests/test_ux04_shared_primitives.py::test_datetime_picker_vn_timezone_and_validation PASSED [ 83%]
  tests/test_ux04_shared_primitives.py::test_media_thumbnail_card_signals PASSED [100%]
  ============================== 6 passed in 0.24s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 95 items
  ...
  ============================= 95 passed in 8.29s ==============================
  ```
- **Bằng chứng nghiệp vụ xác minh:**
  1. `StatusChip`: 12 trạng thái DB/API được ánh xạ chuẩn xác tiếng Việt, màu sắc phân biệt theo chuẩn WCAG AA, có tooltip và hỗ trợ cập nhật động `update_status`.
  2. `EmptyState`: Khắc phục lỗi A-09 (màn hình rỗng 600px). Có đầy đủ 4 preset (`no_pages`, `no_schedules`, `no_media`, `search_not_found`) với icon minh họa và CTA signal.
  3. `FeedbackBanner` & `ToastNotification` & `InlineError`: Cung cấp 3 cấp độ phản hồi người dùng (banner tĩnh, nhãn lỗi trường nhập, toast nổi thoáng qua có timer tự đóng).
  4. `SafeConfirmDialog`: Khóa an toàn nút hành động nguy hiểm cho đến khi tích checkbox xác nhận; liệt kê danh sách tác động cụ thể (impact items).
  5. `DateTimePickerVN`: Bảo đảm múi giờ nghiệp vụ Việt Nam (UTC+7), độc lập hoàn toàn với OS, chuyển đổi ISO UTC chuẩn hóa SQLite và kiểm tra tính hợp lệ trong tương lai.
  6. `MediaThumbnailCard`: Khung xem trước 16:9, overlay thời lượng, badge TikTok/Douyin/FB, nút bấm phát signal gửi thẳng vào Composer.

---

### Task UX-05: Dashboard 2.0 (`overview_workspace.py`)

- **Thời gian:** 13/10/2026 12:51 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `652c7fe`
- **Visual Snapshot:** `docs/redesign_screenshots/01_dashboard_v2.png` (113 KB, chuẩn thiết kế mockup `01_tong_quan.png`).
- **Command 1:** `pytest tests/test_ux05_dashboard.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux05_dashboard.py::test_metric_card_click_through PASSED      [ 20%]
  tests/test_ux05_dashboard.py::test_dashboard_empty_states PASSED         [ 40%]
  tests/test_ux05_dashboard.py::test_dashboard_alert_banner_and_status_chips PASSED [ 60%]
  tests/test_ux05_dashboard.py::test_dashboard_7day_schedule_timeline PASSED [ 80%]
  tests/test_ux05_dashboard.py::test_dashboard_global_page_context_filtering PASSED [100%]
  ============================== 5 passed in 0.76s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 100 items
  ...
  ============================= 100 passed in 9.13s =============================
  ```
- **Bằng chứng nghiệp vụ xác minh:**
  1. `MetricCard Click-Through`: Cả 4 thẻ metric (Fanpage, Lịch hôm nay, Kho video, Bản quyền) hỗ trợ click phát tín hiệu điều hướng kèm con trỏ tay chỉ `PointingHandCursor` và biểu tượng chuyển tiếp.
  2. `Actionable Alert Banner`: Tự động kiểm tra Fanpage token hết hạn hoặc bài viết gặp lỗi để hiển thị banner cảnh báo thông minh, ẩn hoàn toàn khi hệ thống an toàn.
  3. `ScheduleTimelineWidget`: Phân bổ dải 7 ngày trực quan theo giờ Việt Nam (`Asia/Ho_Chi_Minh`), đếm chính xác số bài lên lịch và tóm tắt tổng số bài.
  4. `Onboarding & EmptyState`: Tự động chuyển đổi giữa Bảng tác vụ và `EmptyState` (`no_pages` khi 0 fanpage, `no_schedules` khi chưa có bài viết).
  5. `StatusChip Integration`: Bảng các tác vụ gần đây gắn chip trạng thái nhiều màu sắc chuẩn WCAG AA và hiển thị giờ đăng Việt Nam chuẩn xác.
  6. `GlobalPageContext Filtering`: Khi người dùng chuyển đổi Fanpage trên TopBar, Dashboard lập tức lọc và cập nhật toàn bộ số liệu thẻ metric và bảng tác vụ theo Page đó.

---

### Task UX-06: Fanpage Workspace 2.0 (`pages_workspace.py`)

- **Thời gian:** 13/10/2026 12:56 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `ad415ff`
- **Visual Snapshot:** `docs/redesign_screenshots/02_fanpage_v2.png` (90 KB, chuẩn thiết kế mockup `02_fanpage.png`).
- **Command 1:** `pytest tests/test_ux06_pages_workspace.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux06_pages_workspace.py::test_pages_workspace_empty_state_and_table_switch PASSED [ 25%]
  tests/test_ux06_pages_workspace.py::test_pages_workspace_search_filter PASSED [ 50%]
  tests/test_ux06_pages_workspace.py::test_pages_workspace_verify_token_health PASSED [ 75%]
  tests/test_ux06_pages_workspace.py::test_pages_workspace_unlink_page_warning PASSED [100%]
  ============================== 4 passed in 1.49s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 104 items
  ...
  ============================= 104 passed in 9.57s =============================
  ```
- **Bằng chứng nghiệp vụ xác minh:**
  1. `ConnectPageDialog 2.0`: Tách 2 Tab trực quan rõ ràng; xác thực chặt chẽ token và quyền `CREATE_CONTENT` (khắc phục dứt điểm A-06).
  2. `StatusChip`: Bảng Fanpage hiển thị rõ ràng 4 trạng thái (`ready`, `token_expired`, `unverified`, `insufficient_permissions`) kèm màu sắc đạt chuẩn WCAG AA và tooltip.
  3. `Live Search Filter`: Ô tìm kiếm nhanh cho phép lọc tức thì danh sách Fanpage theo cả Tên gợi nhớ và Facebook Page ID.
  4. `Verify Token Health`: Nút kiểm tra sức khỏe token trực tiếp cập nhật trạng thái động của Page vào SQLite và UI mà không cần kết nối lại.
  5. `EmptyState Onboarding`: Tự động hiển thị thẻ EmptyState hướng dẫn kết nối khi chưa có Fanpage nào trong cơ sở dữ liệu.
  6. `Guard AC-11 Unlink Page`: Đảm bảo không silent delete; hiển thị chi tiết số lượng lịch hẹn giờ trên máy và lịch trên Facebook.

---

### Task UX-07: Unified Post Composer 2.0 (`post_composer.py`)

- **Thời gian:** 13/10/2026 13:02 VN
- **Branch:** `feature/uiux-redesign-v2`
- **Commit:** `096f166`
- **Visual Snapshot:** `docs/redesign_screenshots/03_composer_v2.png` (131 KB, chuẩn thiết kế mockup `03_soan_bai.png`).
- **Command 1:** `pytest tests/test_ux07_unified_composer.py -v`
- **Kết quả Command 1:**
  ```text
  tests/test_ux07_unified_composer.py::test_composer_live_mobile_preview PASSED [ 33%]
  tests/test_ux07_unified_composer.py::test_composer_select_all_and_hashtag_tools PASSED [ 66%]
  tests/test_ux07_unified_composer.py::test_composer_schedule_invariants_preserved PASSED [100%]
  ============================== 3 passed in 0.94s ==============================
  ```
- **Command 2 (Full Gate):** `pytest tests/ -v`
- **Kết quả Command 2:**
  ```text
  collected 107 items
  ...
  ============================ 107 passed in 10.27s =============================
  ```
- **Bằng chứng nghiệp vụ xác minh:**
  1. `Live Mobile Simulated Preview`: Khung xem trước mô phỏng chuẩn xác giao diện Facebook Reels trên di động, đồng bộ trực tiếp khi người dùng gõ caption, chọn Page đích hoặc gắn video.
  2. `Multi-Page Selector Tools`: Nút chọn nhanh tất cả hoặc bỏ chọn tất cả Fanpage trong danh sách; hiển thị đúng số lượng Page trên nút hành động cuối.
  3. `Caption Helpers`: Thanh công cụ gợi ý hashtag nhanh, bộ đếm số lượng ký tự và số lượng hashtag tức thời.
  4. `Schedule Invariants (AC-06/AC-41)`: Kiểm tra công tắc hẹn giờ; khi tắt công tắc ngày giờ đã chọn vẫn được bảo toàn nguyên vẹn, không bao giờ tự động đăng bài khi chưa người dùng xác nhận.
  5. `Idempotent ContentSnapshot (AC-15/AC-19)`: Đóng gói ContentSnapshot bất biến cho từng Page đích độc lập, chống bấm đúp với `client_request_id`.
  6. `Thread Safety Enhancement`: Giải quyết triệt để xung đột bộ nhớ khi hủy dialog worker trong môi trường Windows.

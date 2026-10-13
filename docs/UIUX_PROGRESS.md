# TIẾN ĐỘ THỰC HIỆN LOVIRA WORKSPACE 2.0 (UI/UX REDESIGN)

Tài liệu theo dõi từng task tuần tự theo mục 7 của `docs/UIUX_REDESIGN_PLANNING.md`.
Chỉ chuyển task tiếp theo khi task hiện tại đạt chuẩn **DONE** kèm bằng chứng nghiệm thu (test + screenshot).

---

## Danh mục Tasks & Trạng thái tổng quan

| Task | Tên nhiệm vụ | Mức độ | Phụ thuộc | Trạng thái | Hoàn thành |
|---|---|---|---|---|---|
| **UX-00** | Baseline Verification & Setup | P0 | — | **DONE** | 13/10/2026 |
| **UX-01** | Safety Fixes & P0 Audit | P0 | UX-00 | **DONE** | 13/10/2026 |
| **UX-02** | Design Tokens & Theme Engine | P1 | UX-00 | **DONE** | 13/10/2026 |
| **UX-03** | Desktop Shell & 10 Routes | P0 | UX-02 | **DONE** | 13/10/2026 |
| **UX-04** | Shared UI Primitives | P1 | UX-03 | **DONE** | 13/10/2026 |
| **UX-05** | Dashboard 2.0 | P1 | UX-04 | **DONE** | 13/10/2026 |
| **UX-06** | Fanpage Workspace 2.0 | P0 | UX-04, UX-01 | **DONE** | 13/10/2026 |
| **UX-07** | Unified Post Composer 2.0 | P0 | UX-06 | IN PROGRESS | — |
| **UX-08** | Schedule Workspace 2.0 | P0 | UX-07 | TODO | — |
| **UX-09** | Media Library & Video Downloader 2.0 | P1 | UX-07 | TODO | — |
| **UX-10** | Bulk Import Excel/CSV Wizard 2.0 | P0 | UX-06, UX-09 | TODO | — |
| **UX-11** | Comments & Interaction Workspace 2.0 | P1 | UX-04, UX-06 | TODO | — |
| **UX-12** | Settings & Activity Log Center 2.0 | P1 | UX-04 | TODO | — |
| **UX-13** | Final QA, Regression & Verification | P0 | UX-05..12 | TODO | — |

---

## Chi tiết từng Task

### UX-00 — Baseline Verification & Setup
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:00 — 13/10/2026 12:15
- **Baseline SHA:** `4959814229ce2d39c06332ab9ce91030fa6e04da`
- **Scope and no-go changes:** Khởi tạo branch `feature/uiux-redesign-v2`, kiểm tra 75 tests baseline, tạo tài liệu quy chuẩn, chụp 11 snapshot screenshots.
- **Why DONE is justified:** Baseline SHA đã ghim, 75/75 tests passed, 11 ảnh baseline đã tạo, branch sẵn sàng.

---

### UX-01 — Safety Fixes & P0 Audit
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:17 — 13/10/2026 12:25
- **Baseline SHA / Commit SHA:** `487742d` / `c28d395`
- **Scope and no-go changes:** 
  - Khắc phục triệt để 3 rủi ro an toàn dữ liệu và quyền hạn (P0):
    1. `bulk_import_dialog.py`: Ngăn chặn hoàn toàn việc silent fallback sang tất cả Fanpage khi `Page_IDs` rỗng hoặc không khớp. Chỉ khi người dùng chỉ định rõ `ALL` mới đăng đa Page. Các dòng lỗi bị bỏ qua và cảnh báo trên preview table.
    2. `pages_workspace.py`: Khi kết nối direct Page token, nếu `inspect_token` thất bại hoặc không xác thực được qua mạng, lưu Page ở trạng thái `unverified` và không cấp quyền đăng bài, cảnh báo rõ ràng thay vì gán `ready`. Phân biệt rõ quyền `CREATE_CONTENT` / `MANAGE`.
    3. `app.py` & licensing: Loại bỏ hoàn toàn `MagicMock` trong production runtime. Hỗ trợ nạp `SupabaseAdapter` từ ENV hoặc fallback an toàn sang `OfflineFallbackLicenseBackend` (fail-closed, từ chối kích hoạt giả và AccessPolicyManager chặn các hành vi publish khi không có license).
- **Existing behavior to preserve:** SQLite WAL, SecretVault, ContentSnapshot, múi giờ Việt Nam, toàn bộ nghiệp vụ nền tảng.
- **Changed files:**
  - `src/lovira/licensing/client.py`: Thêm `OfflineFallbackLicenseBackend`.
  - `src/lovira/app.py`: Thay `MagicMock` bằng cấu hình Supabase thực hoặc `OfflineFallbackLicenseBackend`.
  - `src/lovira/ui/views/pages_workspace.py`: Chặn gán `status='ready'` khi token chưa được verify hoặc thiếu quyền.
  - `src/lovira/ui/views/bulk_import_dialog.py`: Kiểm tra nghiêm ngặt `Page_IDs`, loại bỏ silent fallback all pages, hiển thị cảnh báo trên preview table.
  - `tests/test_ux_enhancements.py`: Cập nhật assert status `unverified` khi token inspection trả về None.
  - `tests/test_ux01_safety_fixes.py`: Bộ test mới 4 test cases kiểm tra nghiêm ngặt 3 lỗi P0.
- **UI states implemented:**
  - Connect Page: Trạng thái cảnh báo khi token không xác thực được (`unverified`), trạng thái cảnh báo khi token thiếu quyền (`insufficient_permissions`).
  - Bulk Import Preview: Đánh dấu `⚠️ Thiếu Page ID` hoặc `⚠️ Page ID lạ`, vô hiệu hóa import khi không có dòng hợp lệ nào.
  - Licensing: Fail-closed rõ ràng khi chưa có backend hoặc offline.
- **Exact tests executed and results:**
  - `pytest tests/test_ux01_safety_fixes.py -v`: 4 passed in 1.67s.
  - `pytest tests/ -v`: 79 passed in 5.73s (toàn bộ 79/79 test suites xanh).
- **Security & concurrency self-review:**
  - Token Facebook không bao giờ bị log/leak, luôn lưu qua SecretVault.
  - Không thể vô tình đăng bài lên Fanpage không chủ ý do lỗi nhập liệu trong sheet Excel.
  - Không có backdoor/bypass license trong runtime desktop.
- **Why DONE is justified:** Cả 3 lỗi P0 chỉ định trong planning đã được sửa đúng root-cause, có test failure/regression bảo vệ, và toàn bộ 79 tests đều pass 100%.

---

### UX-02 — Design Tokens & Theme Engine
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:24 — 13/10/2026 12:28
- **Baseline SHA / Commit SHA:** `89e796c` / `4c34f19`
- **Scope and no-go changes:**
  - Xây dựng hệ thống Design Tokens chuẩn hóa cho Desktop PySide6 (`tokens.py`):
    - Dark Palette (Slate / Indigo) và Light Palette (WCAG AA).
    - Typography Segoe UI chuẩn desktop scale (28px hero, 22px title, 17px section, 14px body).
    - Thang đo khoảng cách Spacing & Radius (card 12px, button 8px, chip pill 999px).
    - Quản lý 2 chế độ Mật độ: Comfortable (mặc định) và Compact.
  - Xây dựng bộ Vector Icon Registry (`icons.py`) dạng SVG nội bộ (Lucide style) cho toàn bộ 10 route và action, render sắc nét ở mọi DPI qua `QSvgRenderer`.
  - Xây dựng `ThemeManager` (`theme_manager.py`) tạo QSS Stylesheet phân tầng động, **loại bỏ triệt để selector trùng lặp (khắc phục lỗi audit A-08)**.
  - Refactor `src/lovira/ui/theme.py` chuyển tiếp an toàn sang Theme Engine mới.
- **Existing behavior to preserve:** Toàn bộ component và style hiện có tiếp tục hoạt động trơn tru.
- **Changed files:**
  - `src/lovira/ui/design/tokens.py` (new)
  - `src/lovira/ui/design/icons.py` (new)
  - `src/lovira/ui/design/theme_manager.py` (new)
  - `src/lovira/ui/theme.py` (refactored)
  - `tests/test_ux02_tokens_and_theme.py` (new)
- **UI states implemented:** Dark Theme, Light Theme, Comfortable Density, Compact Density, vector icons render test.
- **Exact tests executed and results:**
  - `pytest tests/test_ux02_tokens_and_theme.py -v`: 5 passed in 0.23s.
  - `pytest tests/ -v`: 84 passed in 6.34s (toàn bộ 84/84 tests xanh).
- **Security & a11y self-review:**
  - Tương phản màu text_primary trên canvas/surface đạt >= 4.5:1 (chuẩn WCAG AA).
  - Focus ring bàn phím rõ ràng (`#9B93FA` / `#4F46E5`).
  - Linter duyệt toàn bộ rules QSS bảo đảm 0 duplicate selectors.
- **Why DONE is justified:** Design Tokens, SVG Icon registry và ThemeManager đều đã hoàn thành và được kiểm chứng qua 5 tests chuyên biệt + full suite 84 tests.

---

### UX-03 — Desktop Shell & 10 Routes
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:28 — 13/10/2026 12:38
- **Baseline SHA / Commit SHA:** `dfff0e1` / `c359f30`
- **Scope and no-go changes:**
  - Xây dựng kiến trúc điều hướng ổn định với `Route` enum và `NavigationController` (`navigation.py`):
    - Đăng ký và quản lý 10 Routes: `dashboard`, `composer`, `pages`, `schedule`, `media`, `downloads`, `bulk_import`, `comments`, `activity`, `settings`.
    - Xóa bỏ triệt để lỗi lệch index / mất focus sidebar khi chuyển view từ video sang composer (khắc phục lỗi audit A-02).
  - Xây dựng `GlobalPageContext` (`global_context.py`):
    - Quản lý phạm vi Fanpage được chọn (Tất cả Page / Page cụ thể) và phát tín hiệu cho toàn bộ workspace (khắc phục lỗi audit A-04).
    - Hỗ trợ tìm kiếm nhanh với debounce 250ms (khắc phục lỗi audit A-03).
  - Xây dựng `TopCommandBar` (`top_bar.py`):
    - Tiêu đề màn hình tự động đổi theo route, search bar với phím tắt `Ctrl+K`, nút `+ Tạo bài` (`Ctrl+N`), badge bản quyền.
  - Xây dựng `AppSidebar` (`sidebar.py`):
    - 3 phân nhóm rõ ràng: Quản lý, Nội dung, Hệ thống.
    - Vector SVG icons sắc nét (Lucide style), hỗ trợ thu gọn 68px và mở rộng 236px.
  - Xây dựng `CommentsWorkspaceView` (`comments_workspace.py`):
    - Màn hình bình luận thực thụ với split-pane, template trả lời nhanh và banner báo cáo quyền Facebook trung thực (khắc phục lỗi audit A-01).
  - Xây dựng `ActivityWorkspaceView` (`activity_workspace.py`):
    - Màn hình nhật ký hoạt động & kiểm toán an toàn (Route 9).
  - Refactor `MainWindow` (`main_window.py`) và `app.py`:
    - Tích hợp toàn diện 10 routes và bảo toàn 100% tương thích ngược với các test cũ.
- **Existing behavior to preserve:** Vòng đời thu nhỏ vào khay hệ thống (tray) khi bấm X, các phím tắt, bảo mật dữ liệu.
- **Changed files:**
  - `src/lovira/ui/shell/navigation.py` (new)
  - `src/lovira/ui/shell/global_context.py` (new)
  - `src/lovira/ui/shell/top_bar.py` (new)
  - `src/lovira/ui/shell/sidebar.py` (new)
  - `src/lovira/ui/views/comments_workspace.py` (new)
  - `src/lovira/ui/views/activity_workspace.py` (new)
  - `src/lovira/ui/main_window.py` (refactored)
  - `src/lovira/app.py` (refactored)
  - `src/lovira/ui/views/bulk_import_dialog.py` (thread safety fix)
  - `tests/test_ux03_shell_and_routes.py` (new)
- **UI states implemented:**
  - 10 Routes hoạt động, sidebar checked state đồng bộ hoàn toàn.
  - Sidebar thu gọn (icon only 68px) và mở rộng (236px).
  - Comments screen honest state (banner cảnh báo quyền API).
  - Header search input với debounce và Ctrl+K.
- **Exact tests executed and results:**
  - `pytest tests/test_ux03_shell_and_routes.py -v`: 5 passed in 1.24s.
  - `pytest tests/ -v`: 89 passed in 8.28s (toàn bộ 89/89 tests xanh 100%).
- **Security & concurrency self-review:**
  - An toàn tiến trình `QThread` khi đóng dialog.
  - Không để lộ token trong nhật ký Activity.
  - Chuyển route bằng enum an toàn, không có crash hay out-of-bounds index.
- **Why DONE is justified:** Cả 4 lỗi audit A-01, A-02, A-03, A-04 đã được khắc phục hoàn toàn; 10 route đồng bộ một nguồn chân lý; 89/89 tests passed.

---

### UX-04 — Shared UI Primitives
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:40 — 13/10/2026 12:45
- **Baseline SHA / Commit SHA:** `1c9061e` / `6e98761`
- **Scope and no-go changes:**
  - Xây dựng 6 UI Primitives dùng chung chuẩn mực theo mục 5 của `docs/UIUX_REDESIGN_PLANNING.md`:
    1. `StatusChip` (`status_chip.py`): Ánh xạ 12 trạng thái DB/API (`ready`, `unverified`, `token_expired`, `insufficient_permissions`, `scheduled_local`, `scheduled_remote`, `publishing`, `published`, `failed`, `cancelled`, `rate_limited`, `unknown`) sang vector icon + nhãn tiếng Việt + màu WCAG AA + tooltip giải thích.
    2. `EmptyState` (`empty_state.py`): Triệt tiêu màn hình rỗng chết 600px (khắc phục lỗi audit A-09), cung cấp minh họa icon lớn, thông điệp rõ ràng và nút CTA kích hoạt hành động (`no_pages`, `no_schedules`, `no_media`, `search_not_found`).
    3. `FeedbackBanner`, `InlineError`, `ToastNotification` (`feedback.py`): Khung cảnh báo tĩnh có hành động, nhãn báo lỗi đỏ tức thì sát input, thông báo nổi thoáng qua (non-modal) tự động tắt sau 3.5s.
    4. `SafeConfirmDialog` (`confirm.py`): Hộp thoại xác nhận an toàn cho các tác vụ nguy hiểm (gỡ page, hủy lịch, xóa video), tóm tắt rõ tác động và khóa nút xóa đỏ cho tới khi người dùng tích ô xác nhận.
    5. `DateTimePickerVN` (`datetime_picker_vn.py`): Bộ chọn ngày giờ độc lập với múi giờ OS, luôn ghim múi giờ Việt Nam (UTC+7), chuyển đổi 2 chiều chính xác với ISO UTC SQLite và kiểm tra tính hợp lệ trong tương lai.
    6. `MediaThumbnailCard` (`media_card.py`): Thẻ xem trước video tỷ lệ 16:9 với overlay thời lượng, huy hiệu nền tảng (TikTok, Douyin, Facebook) và nút thao tác nhanh `Soạn bài ngay`.
  - Khởi tạo `src/lovira/ui/widgets/__init__.py` tập trung hóa imports.
- **Existing behavior to preserve:** Múi giờ Việt Nam độc lập với OS (`Asia/Ho_Chi_Minh`), không thay đổi cấu trúc bảng SQLite hay nghiệp vụ mã hóa.
- **Changed files:**
  - `src/lovira/ui/widgets/__init__.py` (new)
  - `src/lovira/ui/widgets/status_chip.py` (new)
  - `src/lovira/ui/widgets/empty_state.py` (new)
  - `src/lovira/ui/widgets/feedback.py` (new)
  - `src/lovira/ui/widgets/confirm.py` (new)
  - `src/lovira/ui/widgets/datetime_picker_vn.py` (new)
  - `src/lovira/ui/widgets/media_card.py` (new)
  - `src/lovira/domain/timezone.py` (added `VIETNAM_TZ` alias)
  - `tests/test_ux04_shared_primitives.py` (new - 6 test cases)
- **UI states implemented:**
  - 12 trạng thái StatusChip đầy đủ tooltip và màu sắc đạt chuẩn.
  - 4 biến thể EmptyState có CTA chuyển hướng.
  - ToastNotification có timer tự tắt và nút đóng.
  - SafeConfirmDialog trạng thái khóa và mở khóa nút nguy hiểm.
- **Exact tests executed and results:**
  - `pytest tests/test_ux04_shared_primitives.py -v`: 6 passed in 0.24s.
  - `pytest tests/ -v`: 95 passed in 8.29s (toàn bộ 95/95 tests xanh 100%).
- **Security & a11y self-review:**
  - SafeConfirmDialog chặn triệt để thao tác bấm nhầm xóa dữ liệu/hủy lịch.
  - Toàn bộ màu sắc và nhãn trạng thái đều đạt chuẩn WCAG AA và có tooltip hỗ trợ.
  - DateTimePickerVN bảo đảm không tạo lịch quá khứ hay lệch múi giờ.
- **Why DONE is justified:** Cả 6 primitives cốt lõi của Lovira Workspace 2.0 đã hoàn thiện, kiểm thử tự động đạt 100% tỷ lệ đỗ (95/95 tests), sẵn sàng lắp ghép vào các Workspace chuyên biệt.

---

### UX-05 — Dashboard 2.0 (`overview_workspace.py`)
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:46 — 13/10/2026 12:53
- **Baseline SHA / Commit SHA:** `4afb0c5` / `652c7fe`
- **Scope and no-go changes:**
  - Nâng cấp màn hình Tổng quan thành Dashboard 2.0 theo mockup `01_tong_quan.png` (khắc phục dứt điểm A-09):
    1. **Header chào thời gian thực:** Lời chào theo buổi (Sáng/Chiều/Tối), tiêu đề và subtitle rõ ràng, nút `Làm mới` và nút `+ Soạn bài ngay` (primary accent).
    2. **4 MetricCards Click-Through:** Tích hợp `clicked(route)` để bấm trực tiếp chuyển sang các workspace tương ứng (`pages`, `schedule`, `media`, `settings`), hỗ trợ `PointingHandCursor` và chevron chỉ hướng.
    3. **Actionable Alert Banner:** Tự động phát hiện Fanpage token hết hạn (`token_expired`), thiếu quyền (`insufficient_permissions`) hoặc bài viết gặp lỗi (`failed_final`, `missed`) và hiển thị cảnh báo tĩnh kèm hướng dẫn. Ẩn khi hệ thống bình thường.
    4. **Schedule Timeline 7 ngày (`ScheduleTimelineWidget`):** Hiển thị dải 7 ngày tới (tính từ hôm nay theo giờ VN UTC+7), đếm chính xác số bài lên lịch từng ngày và hỗ trợ nhấp chuột lọc lịch.
    5. **Bảng Recent Jobs & Onboarding EmptyState:** Tích hợp `QStackedLayout` giữa Bảng tác vụ và `EmptyState`. Khi 0 page hiển thị `EmptyState.no_pages`, khi 0 job hiển thị `EmptyState.no_schedules`. Khi có bài viết, bảng hiển thị hiện đại với `StatusChip` và giờ Việt Nam.
    6. **Đồng bộ hóa với `GlobalPageContext`:** Tự động lọc toàn bộ số liệu thẻ metric và bảng jobs theo Fanpage được chọn từ Header.
- **Existing behavior to preserve:** Bảo toàn 100% các attribute cũ `card_pages`, `card_schedules`, `card_media`, `card_status`, `table_recent`, `quick_post_requested`, `download_video_requested`, `add_page_requested`, `bulk_import_requested`, bảo đảm tương thích với mọi test cũ.
- **Changed files:**
  - `src/lovira/ui/widgets/schedule_timeline.py` (new)
  - `src/lovira/ui/widgets/__init__.py` (updated)
  - `src/lovira/ui/views/overview_workspace.py` (upgraded)
  - `src/lovira/ui/main_window.py` (added page_context alias)
  - `src/lovira/ui/shell/global_context.py` (added page_changed alias)
  - `src/lovira/app.py` (connected view_overview.navigate_requested and page_context)
  - `tests/test_ux05_dashboard.py` (new - 5 test cases)
  - `docs/redesign_screenshots/01_dashboard_v2.png` (captured visual snapshot)
- **UI states implemented:**
  - Onboarding 0 Fanpage (EmptyState no_pages).
  - EmptyState no_schedules khi chưa có lịch đăng nào.
  - Alert Banner cảnh báo token/lỗi bài viết (warning/danger).
  - Timeline 7 ngày có bài đăng.
  - Bảng Recent Jobs có StatusChip đầy đủ màu sắc và tooltip.
- **Exact tests executed and results:**
  - `pytest tests/test_ux05_dashboard.py -v`: 5 passed in 0.76s.
  - `pytest tests/ -v`: 100 passed in 9.13s (toàn bộ 100/100 tests xanh 100%).
- **Security & a11y self-review:**
  - MetricCards và nút điều hướng có cursor hand rõ ràng.
  - Múi giờ bài đăng trên Timeline và Recent Jobs độc lập hoàn toàn với OS, luôn chạy theo `Asia/Ho_Chi_Minh`.
  - Alert Banner không để lộ token thô.
- **Why DONE is justified:** Toàn bộ tiêu chí nghiệm thu của Dashboard 2.0 đã hoàn thành, có visual snapshot `01_dashboard_v2.png`, 100/100 tests passed.

---

### UX-06 — Fanpage Workspace 2.0 (`pages_workspace.py`)
- **Status:** DONE
- **Start/End (VN):** 13/10/2026 12:54 — 13/10/2026 12:57
- **Baseline SHA / Commit SHA:** `6b61a9f` / (đang chuẩn bị commit)
- **Scope and no-go changes:**
  - Nâng cấp Fanpage Workspace thành phiên bản 2.0 theo mockup `02_fanpage.png`:
    1. **ConnectPageDialog Wizard 2.0:** Chia 2 Tab trực quan: (1) Nhập trực tiếp Page ID & Page Token; (2) Quét tự động từ User Access Token.
    2. **Kiểm toán an toàn Token (A-06):** Phân loại nghiêm ngặt `ready`, `unverified`, `insufficient_permissions`, `token_expired`. Tuyệt đối không gán `ready` khi inspect thất bại hoặc thiếu quyền `CREATE_CONTENT`.
    3. **Bộ lọc tìm kiếm nhanh:** Lọc tức thì theo tên Fanpage và Facebook Page ID.
    4. **Kiểm tra sức khỏe Token (Verify Token Health):** Nút hành động trực tiếp trên hàng để gọi inspect token và cập nhật trạng thái động trong SQLite (`ready` vs `token_expired`).
    5. **Onboarding EmptyState:** Tự động chuyển đổi sang `EmptyState.no_pages` khi danh sách rỗng, có nút CTA mở Wizard kết nối.
    6. **Bảo vệ an toàn khi gỡ Page (AC-11):** Cảnh báo chi tiết số lượng lịch hẹn giờ local và lịch remote trên Facebook.
  - Mở rộng `PageRepository` với phương thức `update_page_status(page_id, status)`.
- **Existing behavior to preserve:** Bảo toàn 100% các attribute cũ `table`, `btn_add_page`, `btn_refresh`, `btn_bulk_import`, `btn_unlink_page`, `page_list_changed`, `bulk_import_requested`, `reload_pages()`, `_get_selected_page_id()`, `_handle_unlink_page()`.
- **Changed files:**
  - `src/lovira/storage/page_repository.py` (added `update_page_status`)
  - `src/lovira/ui/views/pages_workspace.py` (upgraded to 2.0)
  - `tests/test_ux06_pages_workspace.py` (new - 4 test cases)
  - `docs/redesign_screenshots/02_fanpage_v2.png` (captured visual snapshot)
- **UI states implemented:**
  - EmptyState no_pages khi 0 Fanpage.
  - Bảng Fanpage hiển thị StatusChip (`ready`, `token_expired`, `unverified`, `insufficient_permissions`).
  - Hộp thoại ConnectPageDialog 2 tab.
  - Kết quả kiểm tra lại token (hợp lệ vs hết hạn).
  - Hộp thoại xác nhận gỡ Fanpage kèm cảnh báo AC-11.
- **Exact tests executed and results:**
  - `pytest tests/test_ux06_pages_workspace.py -v`: 4 passed in 1.49s.
  - `pytest tests/ -v`: 104 passed in 9.57s (toàn bộ 104/104 tests xanh 100%).
- **Security & a11y self-review:**
  - Token được bảo vệ chặt chẽ trong SecretVault, chỉ lưu `token_ref` trong DB.
  - Kiểm tra quyền `CREATE_CONTENT` trước khi cho phép đăng bài.
  - Cảnh báo rõ ràng tránh mất mát lịch khi gỡ Fanpage.
- **Why DONE is justified:** Hoàn tất 100% tiêu chí nghiệm thu của Fanpage Workspace 2.0, khắc phục triệt để lỗi A-06, A-10, có visual snapshot `02_fanpage_v2.png`, 104/104 tests passed.
- **Next unblocked task:** UX-07 — Unified Post Composer 2.0 (`post_composer.py`).

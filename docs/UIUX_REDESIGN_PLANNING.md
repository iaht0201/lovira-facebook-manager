# LOVIRA MANAGER — UI/UX REDESIGN & IMPLEMENTATION PLANNING

> **Bản đặc tả thực thi:** 1.0 | **Ngày:** 13/10/2026 | **Nền tảng:** Python desktop / PySide6 (KHÔNG phải web)
>
> **Repository khảo sát:** `https://github.com/iaht0201/lovira-facebook-manager` — nhánh `main`, tree `4959814229ce2d39c06332ab9ce91030fa6e04da`.
>
> **Phạm vi tài liệu:** UX audit theo source + ảnh hiện trạng; thiết kế thông tin, hệ thống giao diện, đặc tả màn hình & luồng tương tác; lịch triển khai theo từng đầu việc; tiêu chí nghiệm thu; self-review. **Đây là bản kế hoạch, chưa phải bản sửa source.**

---

## 0. Mục tiêu, nguyên tắc và ranh giới

### 0.1. North star

Lovira là **công cụ desktop dành cho người quản lý một hoặc nhiều Fanpage**, tập trung vào 4 công việc: (1) quản lý kết nối Page; (2) chuẩn bị nội dung và media; (3) đăng ngay / lập lịch đa Page; (4) theo dõi kết quả, xử lý lỗi, bình luận. Thời gian Việt Nam UTC+7 phải hiển thị rõ, người dùng luôn hiểu **lịch đang nằm trên máy** hay **đã được Facebook nhận**.

### 0.2. Quy tắc bắt buộc

1. Tiếp tục dùng Python + PySide6/Qt Widgets; không chuyển web, React, Electron, WebView, QML nếu chưa có phê duyệt và đánh giá chuyển đổi.
2. Không viết lại các tầng `storage`, `domain`, `workers`, `integrations`, `licensing` chỉ vì đổi UI. Bảo lưu SQLite, queue atomic/idempotent, recovery, keyring, lịch local, tray.
3. Nghiệp vụ chưa hỗ trợ thật phải ghi **Chưa hỗ trợ**, không tạo nút đẹp nhưng vô dụng và không tạo dữ liệu giả trong bản production.
4. Giữ tương thích: `client_request_id`, `batch_id`, `ContentSnapshot`, UTC ISO time, `Asia/Ho_Chi_Minh`, job state machine và quy trình backup.
5. Không kết luận `DONE` chỉ vì test UI kiểm tra tồn tại widget; phải có test trạng thái thực, tương tác bàn phím, async UI, regression và demo thực tế.
6. Không sửa production configuration/license logic để 'đẹp mắt'. Mock chỉ được dùng trong tests hoặc chế độ demo có banner rõ ràng.
7. Bất cứ thay đổi schema/logic nào có thể ảnh hưởng dữ liệu đều phải backup và migration forward-only, không xóa DB local.
8. Tất cả UI chính viết bằng tiếng Việt tự nhiên; Graph API, SQLite, technical codes chỉ hiển thị ở chi tiết/log dành cho nâng cao.

### 0.3. Phạm vi và ngoài phạm vi

**Trong phạm vi:** IA/navigation, visual design system, 10 workspace, responsive desktop, compositional widgets, screen state, error handling, secure prompts, keyboard, accessibility, dark/light, settings, tests, performance, UI integration, bugfix bắt buộc để luồng UI đúng.

**Ngoài phạm vi redesign:** thay backend Facebook bằng scraping/cookie automation, cloud scheduler mới, Instagram, login tài khoản Meta bằng trình duyệt nhúng, mua license online mới, hệ thống CRM/bot ngoài API hiện có. Mở rộng chức năng phải tạo issue riêng.

---

## 1. Hiện trạng repository: bằng chứng đã đọc

### 1.1. Kiến trúc quan sát được

- `src/lovira/app.py`: composition root/DI, khởi động SQLite, scheduler, tray; nối các workspace.
- `src/lovira/ui/main_window.py`: QMainWindow, sidebar 6 mục, header tìm kiếm/Page, badge license, QStackedWidget.
- `src/lovira/ui/theme.py`: stylesheet QSS toàn cục với màu Slate/Indigo.
- `src/lovira/ui/quick_post_dialog.py`: popup chọn nhiều Page, caption, video, bật hẹn giờ.
- `src/lovira/ui/views/post_composer.py`: editor/compose workspace đầy đủ hơn popup (type, media, caption, schedule, summary).
- `src/lovira/ui/views/overview_workspace.py`: 4 metric card, quick actions, bảng job.
- `src/lovira/ui/views/pages_workspace.py`: bảng Page và dialog nhập Page ID/token hoặc user-token scan.
- `src/lovira/ui/views/video_workspace.py`: tải 1/hàng loạt, media library, xem video, gửi video sang composer.
- `src/lovira/ui/views/schedule_workspace.py`: job list/filter/reconcile/pause/cancel.
- `src/lovira/ui/views/bulk_import_dialog.py`: xem trước import Excel/CSV, worker download video và enqueue.
- `src/lovira/ui/views/settings_workspace.py`: backup SQLite và thông tin thiết bị/license.
- `src/lovira/ui/license_dialog.py`: màn hình kích hoạt license.
- `src/lovira/storage/*`, `domain/*`, `workers/*`, `integrations/*`, `security/*`, `licensing/*`: tầng dữ liệu & nghiệp vụ cần tránh regression.
- `docs/DECISIONS.md`, `docs/PROGRESS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/VERIFICATION.md`: quyết định, tiến độ, quy tắc AC ban đầu.

### 1.2. Kết quả audit: sai sót cụ thể

| ID | Mức | Vị trí | Bằng chứng / nguy cơ | Biện pháp |
|---|---|---|---|---|
| A-01 | P0 | `app.py` vùng QStackedWidget | `view_comments` placeholder không được thay bằng view thật => màn Bình luận trống | Xây CommentsWorkspace hoặc trạng thái trung thực khi chưa đủ backend; gắn nav chuẩn |
| A-02 | P0 | `main_window.py`, `app.py` | sidebar 6 index trong khi `view_composer` được `addWidget` cuối stack nhưng không có nav; video->composer gọi `setCurrentWidget` => sidebar sai selection | `NavigationController` route enum ID ổn định, one source of truth, addComposer entry |
| A-03 | P0 | `main_window.py` | `search_input` được tạo nhưng không có handler search | SearchController có kết quả, scope, loading/empty/errors và debounce |
| A-04 | P0 | `app.py` | `page_selector` chỉ được populate/refresh; chưa nối `currentIndexChanged` tới workspace model | `GlobalPageContext` + filter observable; khóa scope khi chỉnh sửa bản nháp |
| A-05 | P0 | `app.py` dòng khởi tạo licensing | `MagicMock` làm backend license trong composition root | kiểm toán chế độ free/demo và Supabase adapter thật, fail-closed khi publish |
| A-06 | P0 | `pages_workspace.py` direct Page token | nếu `inspect_token()` không xác nhận hợp lệ, vẫn `upsert_page(... status='ready')` | không gán Ready khi chưa verify; hiển thị error/unknown, cho retry; xử lý network & permission riêng |
| A-07 | P0 | `bulk_import_dialog.py` worker | `Page_IDs` nhập không khớp map => fallback **toàn bộ Page** | tuyệt đối không tự mở rộng đối tượng đăng; preview block invalid rows; yêu cầu user sửa |
| A-08 | P1 | `theme.py` | CSS QSS `#primaryButton`, `#successButton`, `#dangerButton` định nghĩa lặp | tokens + stylesheet phân tầng; linter duplicate selectors |
| A-09 | P1 | `overview_workspace.py` | bố cục 4 card + thanh quick action + bảng đầy chiều cao | card click-through, recent activity compact, schedule timeline, actionable alerts, empty-states |
| A-10 | P1 | `pages_workspace.py`, `schedule_workspace.py` | bảng ID dài và trạng thái kiểu `SCHEDULED_LOCAL` bị cắt | show name first, ellipsis tooltip/copy, contextual row actions, native localized status chips |
| A-11 | P1 | `post_composer.py`, `quick_post_dialog.py` | 2 luồng compose trùng chức năng nhưng khác validation/UX | một `ComposerState`/`ComposerService`, full editor + quick mode cùng business layer |
| A-12 | P1 | `video_workspace.py` | bảng quá nhiều cột, video không được ưu tiên thumbnail | media card grid/list switch, per-item progress, retry and inspect metadata |
| A-13 | P1 | `settings_workspace.py` | hiển thị raw Device ID và thuật ngữ migration trong UI thường | sections: Chung / Đăng bài / Media / Backup / License / Chẩn đoán |
| A-14 | P1 | nhiều dialogs | các thao tác Graph API inspect, scan từ dialog đồng bộ | background worker (QThreadPool/QRunnable hoặc QThread) + timeout/cancel/lifecycle |
| A-15 | P2 | toàn bộ UI | Emoji hệ thống, chữ nhỏ 11–13px, uppercase nhiều | icon vector, typography scale, helper text con người đọc được |
| A-16 | P2 | `main_window.py` | `setMinimumSize(960,640)` và fixed widths | responsive Qt layouts + high-DPI testing |
| A-17 | P1 | license/tray/status | badge license chưa giải thích rõ ảnh hưởng đến publish | actionable status + in-app alerts + blocker banner, confirm exit |
| A-18 | P1 | tests | test hiện có thiên về hợp đồng chức năng | pytest-qt, GUI snapshot/functional tests, workflow e2e với fake network |

---

## 2. Navigation, Routing & Architecture Target

10 Routes chuẩn:
1. `dashboard`: Tổng quan (Overview)
2. `composer`: Soạn bài mới (Full Post Composer)
3. `pages`: Quản lý Fanpage
4. `schedule`: Lịch đăng
5. `media`: Thư viện media
6. `downloads`: Tải video
7. `bulk_import`: Nhập hàng loạt (Excel/CSV)
8. `comments`: Bình luận & Phản hồi
9. `activity`: Nhật ký hoạt động
10. `settings`: Cài đặt & Bản quyền

---

## 3. Lịch triển khai theo thứ tự (UX-00 -> UX-13)

- **UX-00 Baseline:** Setup branch, baseline verification, snapshot tests & UI screenshots.
- **UX-01 Safety fixes:** P0 Audit & fix: License mock vs fail-closed, Token verification fallback fix, Bulk import Page IDs fallback fix.
- **UX-02 Design tokens & Themes:** Design tokens, theme manager (Dark/Light), typography, local SVG icons.
- **UX-03 Desktop shell & Navigation:** AppShell, AppSidebar (10 routes), TopCommandBar, GlobalPageContext, Route registry.
- **UX-04 Shared UI Primitives:** StatusChip, DataTable, EmptyState, Feedback/Toasts, ConfirmDialog, MediaThumbnail, DateTimePickerVN.
- **UX-05 Dashboard:** Overview Workspace 2.0 (MetricCards, 7-day timeline, actionable alerts, recent jobs).
- **UX-06 Page Management:** Fanpage Workspace 2.0 (Connect wizard, permission health, async verify, unlink impact guard).
- **UX-07 Unified Composer:** Post Composer 2.0 (Multi-page selector, caption overrides, live simulated preview, quick-post alignment, idempotency).
- **UX-08 Schedule Workspace:** Schedule 2.0 (List/Calendar view, local vs remote status, reconcile drawer, safe retry).
- **UX-09 Media & Downloads:** Video Library & Downloader 2.0 (Card grid, single/batch progress, cancellation, media player integration).
- **UX-10 Bulk Import Wizard:** Excel/CSV Import 2.0 (Validation grid, strict Page ID matching, download & enqueue pipeline, error report).
- **UX-11 Comments Workspace:** Comments 2.0 (Split pane, thread view, template quick-reply, honest empty/permission states).
- **UX-12 Settings & Activity Log:** Settings 2.0 & Activity Center (Grouped preferences, SQLite safe backup, audit trail with sanitized logs).
- **UX-13 Final QA & Packaging:** Full regression suite, multi-resolution check (960x640 up to 1080p, 125-200% DPI), release documentation.

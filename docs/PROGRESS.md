# Báo cáo tiến độ (PROGRESS.md)

## Tổng quan
- Phiên bản: 0.1.0-alpha
- Thời gian bắt đầu: 13/10/2026
- Chức năng hiện tại đang thực hiện: **Hoàn tất 24/24 chức năng (F-01 đến F-24)**
- Tổng số chức năng: 24 (F-01 đến F-24)
- Số chức năng hoàn thành: 24 / 24 (100%)

---

## Chi tiết trạng thái các chức năng

| ID | Tên chức năng | Trạng thái | Ghi chú & Lỗi còn lại |
|---|---|---|---|
| F-01 | Cấu trúc project, Single Instance lock, Quản lý thư mục AppData | DONE | Đã hoàn thành cấu trúc `src/lovira`, `AppPaths`, `SingleInstanceLock` đạt AC-01, AC-16 |
| F-02 | Hệ thống lưu trữ SQLite bền vững & Schema Migrations | DONE | DatabaseManager với WAL, Foreign Keys, Schema Migrations và SQLite Online Backup đạt AC-13, AC-22 |
| F-03 | Kho bí mật hệ điều hành & Redaction Log | DONE | SecretVault (Keyring & AES-256-GCM fallback) và LogRedactor đạt AC-32, AC-33 |
| F-04 | Bộ tiện ích Thời gian Việt Nam (UTC <-> VN) | DONE | Timezone converter chuẩn hóa `Asia/Ho_Chi_Minh` <-> UTC ISO-8601 đạt AC-07 |
| F-05 | Supabase Client & State Machine License | DONE | Device Fingerprint, LicenseClient với generation tracking, device transfer và atomic revocation đạt AC-23, AC-24, AC-37, AC-38 |
| F-06 | Công tắc miễn phí & Ma trận phân quyền Offline | DONE | AccessPolicyManager với RemoteAppConfig, Free Mode toggle, Offline action evaluation đạt AC-26, AC-27, AC-36, AC-40, AC-43 |
| F-07 | Database Supabase (Schema, RLS, Edge Functions) | DONE | Supabase SQL schema, RLS policies, atomic RPCs (`activate_license_rpc`, `heartbeat_session_rpc`) và SupabaseAdapter đạt AC-23, AC-25, AC-30 |
| F-08 | Adapter Tải Video (yt-dlp wrapper) | DONE | VideoDownloader tích hợp yt-dlp cho Douyin, TikTok, Bilibili; metadata extraction; progress tracking và cancellation đạt BR-05, AC-04 |
| F-09 | Xử lý Media & FFmpeg/ffprobe integration | DONE | MediaProcessor tính SHA-256 stream, đọc duration/dimensions/codec, trích xuất thumbnail JPEG đạt BR-05, AC-04, AC-42 |
| F-10 | Kho Media Assets local & Audit tham chiếu | DONE | MediaRepository quản lý media_assets, tìm kiếm và bảo vệ xóa file có lịch chờ tham chiếu đạt AC-12, AC-42 |
| F-11 | Facebook Graph API Client | DONE | FacebookGraphClient v21.0, bóc tách User/Page tokens độc lập, phân tích lỗi (190 expired, rate limit, permission) đạt AC-02, AC-03, AC-20, AC-21 |
| F-12 | Quản lý Page CRUD & Xử lý gỡ Page có lịch | DONE | PageRepository với phân nhóm, SecretVault token storage, audit lịch local/remote khi gỡ Page đạt AC-02, AC-03, AC-11 |
| F-13 | Domain Model Soạn bài & Content Snapshot | DONE | PostComposerState, multi-page overrides, bảo lưu giờ hẹn, bất biến ContentSnapshot đạt AC-06, AC-19, AC-41 |
| F-14 | Hàng đợi Đăng bài nguyên tử & Graph API Publisher | DONE | PublishQueueRepository (client_request_id idempotent batch), GraphPublishAdapter (Post & Reels 3 bước) đạt AC-05, AC-14, AC-15 |
| F-15 | Dịch vụ Scheduler local theo giờ VN | DONE | LocalSchedulerService quét hàng đợi SQLite bền vững, tách rời transaction, xử lý missed và lease timeout đạt AC-17, AC-44 |
| F-16 | Khôi phục sự cố, xử lý Unknown, Backoff Retry | DONE | RecoveryManager xử lý orphaned jobs thành unknown (AC-14), đối chiếu Graph API, backoff có jitter (AC-21) |
| F-17 | Chạy nền System Tray & Safe Shutdown | DONE | SystemTrayManager với QSystemTrayIcon, menu khay hệ thống, fallback Linux không có tray (AC-08, AC-09) |
| F-18 | Đồng bộ bài viết & Giám sát Facebook Reels | DONE | PostCacheRepository & FacebookPostSyncService, lọc bài viết, reels tracking, xử lý thiếu quyền gán missing data không gán 0 (BR-03, AC-10) |
| F-19 | Quản lý Bình luận & Reply Templates | DONE | CommentCacheRepository & ReplyTemplateRepository, FacebookCommentService (reply, hide/unhide) đạt BR-04, AC-10 |
| F-20 | Giao diện Desktop Shell PySide6 | DONE | MainWindow, Sidebar 6 mục, Header, Theme Dark hiện đại, Status Bar, LicenseDialog (BR-01, BR-02, BR-11, AC-01) |
| F-21 | Giao diện Tải Video & Media Library | DONE | VideoWorkspaceView (Tab Tải video, Tab Thư viện media, 1-click sang Soạn bài) (BR-05, BR-06, AC-04, AC-12) |
| F-22 | Giao diện Soạn bài & Đặt lịch đa Page | DONE | PostComposerView (Đa Page checkbox, caption override, QDateTimeEdit VN UTC+7, bảo lưu giờ khi tắt toggle, bảng tóm tắt xác nhận) (BR-04, BR-06, AC-05, AC-06, AC-07, AC-15, AC-41) |
| F-23 | Giao diện Quản lý Page, Lịch & Nhật ký | DONE | PagesWorkspaceView (AC-02, AC-03, AC-11), ScheduleWorkspaceView (AC-14), SettingsWorkspaceView (AC-22) |
| F-24 | Kiểm thử toàn diện 44 ca AC & Đóng gói | DONE | Hoàn thiện entrypoint `src/lovira/app.py`, kịch bản đóng gói `packaging/build_desktop.py`, 71/71 unit & integration tests vượt qua 100% |
| F-25 | Cải tiến UX, Dashboard, Popup Soạn bài, Tải hàng loạt, Sheet Excel | DONE | Bổ sung Overview Dashboard (F-25.1), Popup Tạo bài nhanh (F-25.2), Kết nối Page ID trực tiếp (F-25.3), Video preview & Tải hàng loạt & Xem lại (F-25.4), Nhập Sheet mẫu Excel/CSV tự động tải video từ link (F-25.5). Đạt 75/75 tests PASSED |


"""
Lovira-Facebook Manager
Điểm Khởi chạy Chính của Ứng dụng Desktop (Application Entrypoint)
- Khởi tạo SingleInstanceLock bảo đảm chỉ 1 instance chạy trên cùng hồ sơ (AC-16)
- Tự động áp dụng Migration SQLite, kích hoạt WAL mode và SecretVault an toàn
- Quét khôi phục các tác vụ mồ côi (orphaned jobs) sang trạng thái unknown (AC-14)
- Khởi động LocalSchedulerService và SystemTrayManager chạy nền (AC-08, AC-09)
- Nối các tín hiệu điều hướng: 1-click từ Video Workspace sang Post Composer (BR-06)
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QIcon

from src.lovira.config.paths import AppPaths
from src.lovira.app_lock import SingleInstanceLock
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.security.redactor import RedactingLogFilter
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.post_repository import PostCacheRepository, FacebookPostSyncService
from src.lovira.storage.comment_repository import CommentCacheRepository, ReplyTemplateRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.integrations.facebook.publisher import GraphPublishAdapter
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.fingerprint import get_or_create_device_id, get_device_fingerprint
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.workers.scheduler import LocalSchedulerService
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.ui.tray import SystemTrayManager
from src.lovira.ui.main_window import MainWindow
from src.lovira.ui.views.video_workspace import VideoWorkspaceView
from src.lovira.ui.views.post_composer import PostComposerView
from src.lovira.ui.views.pages_workspace import PagesWorkspaceView
from src.lovira.ui.views.schedule_workspace import ScheduleWorkspaceView
from src.lovira.ui.views.settings_workspace import SettingsWorkspaceView


def setup_logging(logs_dir: Path) -> None:
    """Cấu hình logging có bộ lọc che thông tin nhạy cảm (AC-32)."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "lovira_app.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingLogFilter())
    root_logger.addHandler(file_handler)

    # Stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactingLogFilter())
    root_logger.addHandler(console_handler)


def create_application() -> MainWindow:
    """Khởi tạo và cấu hình toàn bộ dependency của ứng dụng."""
    paths = AppPaths()
    paths.ensure_directories()
    setup_logging(paths.logs_dir)

    logger = logging.getLogger("lovira.app")
    logger.info("Đang khởi động Lovira-Facebook Manager (v0.1.0-alpha)...")

    # 1. Cơ sở dữ liệu SQLite & Migrations
    db_manager = DatabaseManager(paths.db_path)
    migration_runner = MigrationRunner(db_manager)
    migration_runner.apply_all()

    # 2. Kho bí mật SecretVault
    vault = SecretVault(fallback_vault_dir=paths.vault_dir)

    # 3. Repositories & Clients
    page_repo = PageRepository(db_manager, vault)
    media_repo = MediaRepository(db_manager)
    queue_repo = PublishQueueRepository(db_manager)
    post_repo = PostCacheRepository(db_manager)
    comment_repo = CommentCacheRepository(db_manager)
    reply_repo = ReplyTemplateRepository(db_manager)

    fb_client = FacebookGraphClient()
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    # 4. License & Policy (UX-01: An toàn sản phẩm, không dùng MagicMock trong runtime)
    device_id = get_or_create_device_id(paths.config_dir)
    fingerprint = get_device_fingerprint(device_id)

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()

    if supabase_url and supabase_key:
        from src.lovira.licensing.supabase_adapter import SupabaseAdapter
        license_backend = SupabaseAdapter(supabase_url=supabase_url, anon_key=supabase_key)
        logger.info("Đã cấu hình Supabase License Backend từ biến môi trường.")
    else:
        from src.lovira.licensing.client import OfflineFallbackLicenseBackend
        license_backend = OfflineFallbackLicenseBackend()
        logger.info("Chưa có cấu hình Supabase Server; khởi động chế độ Offline/Cục bộ an toàn.")

    license_client = LicenseClient(
        backend=license_backend,
        device_id=device_id,
        fingerprint=fingerprint,
    )
    policy_manager = AccessPolicyManager()

    # 5. Khôi phục tác vụ mồ côi sau crash (AC-14)
    recovery_manager = RecoveryManager(db_manager, queue_repo, page_repo, fb_client)
    recovery_manager.recover_orphaned_jobs()

    # 6. Khởi động LocalSchedulerService
    publisher = GraphPublishAdapter(timeout=60.0)
    scheduler_service = LocalSchedulerService(
        db_manager=db_manager,
        queue_repo=queue_repo,
        page_repo=page_repo,
        media_repo=media_repo,
        publisher=publisher,
        policy_manager=policy_manager,
    )
    scheduler_service.start(poll_interval_seconds=15.0)

    # 7. Khởi tạo khay hệ thống (AC-08, AC-09)
    tray_manager = SystemTrayManager()

    # 8. Khởi tạo MainWindow
    main_window = MainWindow(
        db_manager=db_manager,
        license_client=license_client,
        policy_manager=policy_manager,
        tray_manager=tray_manager,
    )

    # 9. Khởi tạo các Views chuyên biệt và tích hợp vào MainWindow.nav_controller
    from src.lovira.ui.shell.navigation import Route
    from src.lovira.ui.views.overview_workspace import OverviewWorkspaceView
    from src.lovira.ui.quick_post_dialog import QuickPostDialog
    from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog
    from src.lovira.ui.views.pages_workspace import ConnectPageDialog
    from src.lovira.ui.views.comments_workspace import CommentsWorkspaceView
    from src.lovira.ui.views.activity_workspace import ActivityWorkspaceView

    view_overview = OverviewWorkspaceView(
        db_manager=db_manager,
        page_repo=page_repo,
        media_repo=media_repo,
        queue_repo=queue_repo,
        license_client=license_client,
        policy_manager=policy_manager,
        page_context=main_window.page_context,
    )
    view_pages = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)
    view_video = VideoWorkspaceView(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=paths.downloads_dir,
        page_repo=page_repo,
        queue_repo=queue_repo,
    )
    view_composer = PostComposerView(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=paths.downloads_dir,
    )

    view_schedule = ScheduleWorkspaceView(
        db_manager=db_manager,
        queue_repo=queue_repo,
        recovery_manager=recovery_manager,
    )
    view_comments = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )
    view_activity = ActivityWorkspaceView(db_manager=db_manager)
    view_settings = SettingsWorkspaceView(
        db_manager=db_manager,
        license_client=license_client,
    )

    # Thay thế các placeholder widget ban đầu bằng view thật để giữ đúng index (0..5) và Composer ở cuối
    main_window.stacked_widget.removeWidget(main_window.view_dashboard)
    main_window.stacked_widget.removeWidget(main_window.view_pages)
    main_window.stacked_widget.removeWidget(main_window.view_video)
    main_window.stacked_widget.removeWidget(main_window.view_schedule)
    main_window.stacked_widget.removeWidget(main_window.view_comments)
    main_window.stacked_widget.removeWidget(main_window.view_settings)

    main_window.stacked_widget.insertWidget(0, view_overview)
    main_window.stacked_widget.insertWidget(1, view_pages)
    main_window.stacked_widget.insertWidget(2, view_video)
    main_window.stacked_widget.insertWidget(3, view_schedule)
    main_window.stacked_widget.insertWidget(4, view_comments)
    main_window.stacked_widget.insertWidget(5, view_settings)

    main_window.stacked_widget.addWidget(view_activity)
    view_bulk_placeholder = QWidget()
    main_window.stacked_widget.addWidget(view_bulk_placeholder)
    main_window.stacked_widget.addWidget(view_composer)

    # Đăng ký 10 Routes vào NavigationController
    nav = main_window.nav_controller
    sb = main_window.sidebar

    nav.register_route(Route.DASHBOARD, view_overview, sb.get_button(Route.DASHBOARD))
    nav.register_route(Route.PAGES, view_pages, sb.get_button(Route.PAGES))
    nav.register_route(Route.SCHEDULE, view_schedule, sb.get_button(Route.SCHEDULE))
    nav.register_route(Route.MEDIA, view_video, sb.get_button(Route.MEDIA))
    nav.register_route(Route.DOWNLOADS, view_video, sb.get_button(Route.DOWNLOADS))
    nav.register_route(Route.BULK_IMPORT, view_bulk_placeholder, sb.get_button(Route.BULK_IMPORT))
    nav.register_route(Route.COMMENTS, view_comments, sb.get_button(Route.COMMENTS))
    nav.register_route(Route.ACTIVITY, view_activity, sb.get_button(Route.ACTIVITY))
    nav.register_route(Route.SETTINGS, view_settings, sb.get_button(Route.SETTINGS))
    nav.register_route(Route.COMPOSER, view_composer, sb.get_button(Route.COMPOSER))

    # Cập nhật danh sách Page vào Header combobox
    def refresh_header_page_selector():
        pages = page_repo.list_pages()
        main_window.top_bar.populate_pages(pages)

    refresh_header_page_selector()
    view_pages.page_list_changed.connect(refresh_header_page_selector)
    view_pages.page_list_changed.connect(view_overview.reload_dashboard_data)

    # Popup Tạo bài nhanh (Modal QDialog)
    def open_quick_post_popup():
        dlg = QuickPostDialog(page_repo=page_repo, queue_repo=queue_repo, media_repo=media_repo, parent=main_window)
        dlg.post_created.connect(view_schedule.reload_schedules)
        dlg.post_created.connect(view_overview.reload_dashboard_data)
        dlg.exec()

    # Popup Nhập Sheet Excel/CSV Hàng loạt
    def open_bulk_import_popup():
        dlg = BulkImportDialog(
            page_repo=page_repo,
            queue_repo=queue_repo,
            media_repo=media_repo,
            downloader=downloader,
            media_processor=media_processor,
            download_dir=paths.downloads_dir,
            parent=main_window,
        )
        dlg.import_completed.connect(view_schedule.reload_schedules)
        dlg.import_completed.connect(view_overview.reload_dashboard_data)
        dlg.exec()

    # Nhấn Route BULK_IMPORT từ sidebar thì mở popup Bulk Import
    sb.get_button(Route.BULK_IMPORT).clicked.connect(open_bulk_import_popup)

    # Nối tín hiệu từ Overview Dashboard
    def handle_overview_navigate(route_key: str):
        route_map = {
            "pages": Route.PAGES,
            "schedule": Route.SCHEDULE,
            "media": Route.MEDIA,
            "downloads": Route.DOWNLOADS,
            "settings": Route.SETTINGS,
            "composer": Route.COMPOSER,
            "activity": Route.ACTIVITY,
        }
        if route_key in route_map:
            nav.navigate_to(route_map[route_key])

    view_overview.navigate_requested.connect(handle_overview_navigate)
    view_overview.quick_post_requested.connect(open_quick_post_popup)
    view_overview.download_video_requested.connect(lambda: nav.navigate_to(Route.DOWNLOADS))
    view_overview.add_page_requested.connect(lambda: (ConnectPageDialog(fb_client, page_repo, main_window).exec(), view_pages.reload_pages()))
    view_overview.bulk_import_requested.connect(open_bulk_import_popup)
    view_pages.bulk_import_requested.connect(open_bulk_import_popup)

    # Nối tín hiệu nút Tạo bài nhanh ở Header
    main_window.top_bar.quick_create_clicked.disconnect()
    main_window.top_bar.quick_create_clicked.connect(open_quick_post_popup)

    # Luồng 1-click: Nhận tín hiệu từ Video Workspace -> Chuyển trực tiếp sang Post Composer (BR-06, A-02)
    def on_video_sent_to_composer(data: dict) -> None:
        view_composer.attach_video_data(data)
        nav.navigate_to(Route.COMPOSER)

    view_video.send_to_composer.connect(on_video_sent_to_composer)
    view_video.batch_schedule_created.connect(lambda _: view_schedule.reload_schedules())
    view_video.batch_schedule_created.connect(lambda _: view_overview.reload_dashboard_data())
    view_video.tab_download.media_downloaded.connect(view_overview.reload_dashboard_data)

    # Khi có bài viết được thêm vào hàng đợi -> Làm mới danh sách lịch và dashboard
    view_composer.publish_enqueued.connect(lambda _: view_schedule.reload_schedules())
    view_composer.publish_enqueued.connect(lambda _: view_overview.reload_dashboard_data())

    # Khôi phục workspace đang làm việc gần nhất (hoặc mặc định Tổng quan)
    initial_route = Route.DASHBOARD
    last_route_file = paths.root / "last_route.txt"
    if last_route_file.exists():
        try:
            saved_route_val = last_route_file.read_text(encoding="utf-8").strip()
            for r in Route:
                if r.value == saved_route_val:
                    initial_route = r
                    break
        except Exception:
            pass
    nav.navigate_to(initial_route)

    def _save_last_route(route_val: str) -> None:
        try:
            last_route_file.write_text(route_val, encoding="utf-8")
        except Exception:
            pass

    nav.route_changed.connect(_save_last_route)

    # Tín hiệu khay hệ thống
    tray_manager.open_requested.connect(main_window.show)
    tray_manager.open_requested.connect(main_window.activateWindow)
    tray_manager.exit_requested.connect(lambda: _safe_exit(scheduler_service, tray_manager))
    tray_manager.pause_queue_requested.connect(scheduler_service.pause_queue)
    tray_manager.resume_queue_requested.connect(scheduler_service.resume_queue)

    logger.info("Khởi tạo ứng dụng hoàn tất.")
    return main_window


def _safe_exit(scheduler: LocalSchedulerService, tray: SystemTrayManager) -> None:
    """Tắt ứng dụng an toàn."""
    scheduler.stop()
    tray.hide()
    QApplication.quit()


def main() -> int:
    """Hàm main thực thi chính."""
    paths = AppPaths()
    lock = SingleInstanceLock(paths.lock_file)

    if not lock.acquire():
        print("CẢNH BÁO: Đã có một phiên bản Lovira-Facebook Manager đang hoạt động trên máy tính này!")
        return 1

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    try:
        window = create_application()
        window.show()
        return app.exec()
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())

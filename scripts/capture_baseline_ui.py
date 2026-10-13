"""
Script chụp ảnh giao diện baseline hiện tại của Lovira Facebook Manager.
Lưu ảnh vào docs/baseline_screenshots/ để phục vụ đối chiếu và nghiệm thu UX-00.
"""

import sys
import os
from pathlib import Path

# Thêm root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize

# Đặt biến môi trường offscreen để chạy mượt mà không nhấp nháy cửa sổ
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.ui.tray import SystemTrayManager
from src.lovira.ui.main_window import MainWindow
from src.lovira.ui.views.overview_workspace import OverviewWorkspaceView
from src.lovira.ui.views.pages_workspace import PagesWorkspaceView, ConnectPageDialog
from src.lovira.ui.views.video_workspace import VideoWorkspaceView
from src.lovira.ui.views.post_composer import PostComposerView
from src.lovira.ui.views.schedule_workspace import ScheduleWorkspaceView
from src.lovira.ui.views.settings_workspace import SettingsWorkspaceView
from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog
from src.lovira.ui.quick_post_dialog import QuickPostDialog
from src.lovira.ui.license_dialog import LicenseDialog
from unittest.mock import MagicMock


def capture_all():
    app = QApplication.instance() or QApplication(sys.argv)
    output_dir = Path("docs/baseline_screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Khởi tạo DB tạm
    temp_db_path = output_dir / "temp_baseline.db"
    if temp_db_path.exists():
        temp_db_path.unlink()

    db_manager = DatabaseManager(temp_db_path)
    MigrationRunner(db_manager).apply_all()
    vault = SecretVault()
    page_repo = PageRepository(db_manager, vault)
    media_repo = MediaRepository(db_manager)
    queue_repo = PublishQueueRepository(db_manager)
    fb_client = FacebookGraphClient()
    downloader = VideoDownloader()
    media_processor = MediaProcessor()
    license_client = LicenseClient(
        backend=MagicMock(),
        device_id="DEV-TEST-BASELINE",
        fingerprint="FINGERPRINT-TEST",
    )
    policy_manager = AccessPolicyManager()
    tray_manager = SystemTrayManager()

    # Tạo MainWindow
    win = MainWindow(db_manager, license_client, policy_manager, tray_manager)
    win.resize(1366, 768)

    # Thêm các view đúng như app.py hiện hữu
    view_overview = OverviewWorkspaceView(
        db_manager, page_repo, media_repo, queue_repo, license_client, policy_manager
    )
    view_pages = PagesWorkspaceView(page_repo, fb_client)
    view_video = VideoWorkspaceView(downloader, media_repo, media_processor, output_dir)
    view_schedule = ScheduleWorkspaceView(db_manager, queue_repo)
    view_settings = SettingsWorkspaceView(db_manager, license_client)
    view_composer = PostComposerView(page_repo, queue_repo)

    # Thay các placeholder trong stacked_widget
    win.stacked_widget.removeWidget(win.stacked_widget.widget(0))
    win.stacked_widget.insertWidget(0, view_overview)

    win.stacked_widget.removeWidget(win.stacked_widget.widget(1))
    win.stacked_widget.insertWidget(1, view_pages)

    win.stacked_widget.removeWidget(win.stacked_widget.widget(2))
    win.stacked_widget.insertWidget(2, view_video)

    win.stacked_widget.removeWidget(win.stacked_widget.widget(3))
    win.stacked_widget.insertWidget(3, view_schedule)

    # index 4 là view_comments (hiện là QLabel placeholder)
    win.stacked_widget.removeWidget(win.stacked_widget.widget(5))
    win.stacked_widget.insertWidget(5, view_settings)

    # view_composer được app.py add cuối stack
    win.stacked_widget.addWidget(view_composer)

    win.show()

    tabs = [
        (0, "01_overview_dashboard.png"),
        (1, "02_fanpage_workspace.png"),
        (2, "03_video_workspace.png"),
        (3, "04_schedule_workspace.png"),
        (4, "05_comments_placeholder.png"),
        (5, "06_settings_workspace.png"),
        (6, "07_post_composer_workspace.png"),
    ]

    for idx, filename in tabs:
        win.stacked_widget.setCurrentIndex(idx)
        app.processEvents()
        pixmap = win.grab()
        pixmap.save(str(output_dir / filename))
        print(f"Captured: {filename}")

    # Chụp các dialog popup
    # Quick post dialog
    dlg_quick = QuickPostDialog(page_repo, queue_repo, media_repo, parent=win)
    dlg_quick.resize(650, 680)
    dlg_quick.show()
    app.processEvents()
    dlg_quick.grab().save(str(output_dir / "08_quick_post_dialog.png"))
    dlg_quick.close()
    print("Captured: 08_quick_post_dialog.png")

    # Connect page dialog
    dlg_connect = ConnectPageDialog(fb_client, page_repo, parent=win)
    dlg_connect.resize(520, 480)
    dlg_connect.show()
    app.processEvents()
    dlg_connect.grab().save(str(output_dir / "09_connect_page_dialog.png"))
    dlg_connect.close()
    print("Captured: 09_connect_page_dialog.png")

    # Bulk import dialog
    dlg_bulk = BulkImportDialog(
        page_repo, queue_repo, media_repo, downloader, media_processor, output_dir, parent=win
    )
    dlg_bulk.resize(750, 600)
    dlg_bulk.show()
    app.processEvents()
    dlg_bulk.grab().save(str(output_dir / "10_bulk_import_dialog.png"))
    dlg_bulk.close()
    print("Captured: 10_bulk_import_dialog.png")

    # License dialog
    dlg_license = LicenseDialog(license_client, parent=win)
    dlg_license.resize(460, 420)
    dlg_license.show()
    app.processEvents()
    dlg_license.grab().save(str(output_dir / "11_license_dialog.png"))
    dlg_license.close()
    print("Captured: 11_license_dialog.png")

    win.close()
    if temp_db_path.exists():
        try:
            temp_db_path.unlink()
        except Exception:
            pass
    print("Baseline screen capture complete.")


if __name__ == "__main__":
    capture_all()

"""
Chụp cả 2 tab: Thư viện media (05_media_library_v2.png) và Tải video (08_video_download_v2.png).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.media.processor import MediaProcessor
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.ui.views.video_workspace import VideoWorkspaceView
from src.lovira.ui.design.theme_manager import ThemeManager


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(["lovira_snapshot"])
    app.setFont(QFont("Segoe UI", 10))

    db_path = Path("tmp_media_snap.db")
    if db_path.exists():
        db_path.unlink()

    db_manager = DatabaseManager(db_path)
    runner = MigrationRunner(db_manager)
    runner.apply_all()

    media_repo = MediaRepository(db_manager)

    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    workspace = VideoWorkspaceView(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=Path("C:/Lovira/Downloads"),
    )

    theme_mgr = ThemeManager.get_instance()
    theme_mgr.apply_theme(app)
    workspace.resize(1180, 740)

    out_dir = Path("docs/redesign_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Chụp Tab Tải video (08_video_download_v2.png)
    workspace.show_download_tab()
    workspace.tab_download.url_input.setText("https://www.tiktok.com/@lovira_official/video/739281729182718")
    workspace.tab_download.lbl_meta_title.setText("Tiêu đề: BST Áo Dài Cách Tân Lovira Tết 2026 #aodai #lovira")
    workspace.tab_download.lbl_meta_platform.setText("Nền tảng: TIKTOK")
    workspace.tab_download.lbl_meta_author.setText("Tác giả: lovira_official")
    workspace.tab_download.lbl_meta_duration.setText("Thời lượng: 00:48")
    workspace.tab_download.progress_bar.setValue(100)
    workspace.tab_download.lbl_progress_status.setText("✅ Tải video thành công! (1.8 MB/s)")
    workspace.tab_download.btn_watch_downloaded.setVisible(True)
    workspace.tab_download.btn_open_folder.setVisible(True)
    workspace.tab_download.btn_compose_now.setVisible(True)

    workspace.show()
    app.processEvents()

    p1 = workspace.grab()
    p1.save(str(out_dir / "08_video_download_v2.png"), "PNG")
    print(f"Saved 08_video_download_v2.png ({p1.size()})")

    if db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    main()

"""
Script chụp ảnh màn hình giao diện Media Library & Video Downloader 2.0 (UX-09).
Lưu tại: docs/redesign_screenshots/05_media_library_v2.png
"""

import sys
from pathlib import Path

# Thêm project root vào sys.path
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

    # Thêm một số media mẫu
    sample_videos = [
        ("tiktok_reels_fashion_01.mp4", "tiktok", 45.0, 14.5 * 1024 * 1024, "https://www.tiktok.com/@lovira/video/71234567"),
        ("douyin_skincare_routine_02.mp4", "douyin", 62.0, 28.2 * 1024 * 1024, "https://www.douyin.com/video/72345678"),
        ("bilibili_tech_review_03.mp4", "bilibili", 185.0, 95.8 * 1024 * 1024, "https://www.bilibili.com/video/BV123456"),
        ("tiktok_viral_dance_trend_04.mp4", "tiktok", 18.0, 6.2 * 1024 * 1024, "https://www.tiktok.com/@trending/video/73456789"),
        ("douyin_autumn_outfit_05.mp4", "douyin", 55.0, 22.1 * 1024 * 1024, "https://www.douyin.com/video/74567890"),
    ]

    for filename, platform, dur, size, url in sample_videos:
        media_repo.add_media_asset(
            local_path=Path(f"C:/Lovira/Downloads/{filename}"),
            checksum=f"chk_{filename}",
            size_bytes=int(size),
            duration=dur,
            source_platform=platform,
            source_url=url,
        )

    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    workspace = VideoWorkspaceView(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=Path("C:/Lovira/Downloads"),
    )

    # Chuyển sang Tab 1: Thư viện Media
    workspace.show_library_tab()

    theme_mgr = ThemeManager.get_instance()
    theme_mgr.apply_theme(app)
    workspace.resize(1180, 740)
    workspace.show()
    app.processEvents()

    out_dir = Path("docs/redesign_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "05_media_library_v2.png"

    pixmap = workspace.grab()
    pixmap.save(str(out_path), "PNG")
    print(f"Snapshot saved to: {out_path} ({out_path.stat().st_size} bytes)")

    if db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    main()

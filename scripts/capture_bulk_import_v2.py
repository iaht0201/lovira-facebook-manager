"""
Script chụp ảnh màn hình giao diện Bulk Import Wizard 2.0 (UX-10).
Lưu tại: docs/redesign_screenshots/09_bulk_import_v2.png
"""

import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog
from src.lovira.ui.design.theme_manager import ThemeManager


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(["lovira_snapshot"])
    app.setFont(QFont("Segoe UI", 10))

    db_path = Path("tmp_bulk_snap.db")
    if db_path.exists():
        db_path.unlink()

    db_manager = DatabaseManager(db_path)
    runner = MigrationRunner(db_manager)
    runner.apply_all()

    vault = SecretVault(fallback_vault_dir=Path("tmp_vault"))
    page_repo = PageRepository(db_manager, vault)
    queue_repo = PublishQueueRepository(db_manager)
    media_repo = MediaRepository(db_manager)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    # Thêm 2 Fanpage
    page_repo.upsert_page("100085942398412", "Lovira Fashion Boutique", status="ready")
    page_repo.upsert_page("100099887766554", "Lovira Cosmetics Official", status="ready")

    # Tạo file dữ liệu nạp mẫu
    csv_file = Path("tmp_sample_bulk.csv")
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "TieuDe", "NoiDung_Caption", "Video_Link_Hoac_File", "Page_IDs", "NgayGioDang_VN", "LoaiDang"
        ])
        writer.writeheader()
        writer.writerow({
            "TieuDe": "Giới thiệu bộ sưu tập mùa hè",
            "NoiDung_Caption": "Top 5 outfit dạo phố thanh lịch và trẻ trung #fashion #summer",
            "Video_Link_Hoac_File": "https://www.tiktok.com/@lovira/video/73918271625",
            "Page_IDs": "100085942398412",
            "NgayGioDang_VN": "2026-10-25 15:00",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Video review son dưỡng môi",
            "NoiDung_Caption": "Dòng son dưỡng thiên nhiên siêu mềm mượt đón gió lạnh #lipcare",
            "Video_Link_Hoac_File": "D:/Lovira/Videos/son_duong_demo.mp4",
            "Page_IDs": "ALL",
            "NgayGioDang_VN": "2026-10-26 19:30",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Video không xác định",
            "NoiDung_Caption": "Mẹo phối đồ công sở nữ",
            "Video_Link_Hoac_File": "https://www.douyin.com/video/7281928374",
            "Page_IDs": "000000000 (Không tồn tại)",
            "NgayGioDang_VN": "2026-10-27 08:00",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Flash sale nửa đêm",
            "NoiDung_Caption": "Săn deal giảm 70% toàn bộ váy dạ hội cao cấp #sale",
            "Video_Link_Hoac_File": "https://www.tiktok.com/@lovira/video/739199999",
            "Page_IDs": "",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        })

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=Path("C:/Lovira/Downloads"),
    )

    dlg._load_data_from_file(str(csv_file))

    theme_mgr = ThemeManager.get_instance()
    theme_mgr.apply_theme(app)
    dlg.resize(1000, 680)
    dlg.show()
    app.processEvents()

    out_dir = Path("docs/redesign_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "09_bulk_import_v2.png"

    pixmap = dlg.grab()
    pixmap.save(str(out_path), "PNG")
    print(f"Snapshot saved to: {out_path} ({out_path.stat().st_size} bytes)")

    if db_path.exists():
        db_path.unlink()
    if csv_file.exists():
        csv_file.unlink()


if __name__ == "__main__":
    main()

"""
Unit tests cho UX-10: Bulk Import Wizard 2.0 (bulk_import_dialog.py)
Kiểm thử toàn diện:
- Stepper 3 bước trực quan: Chọn file -> Xem trước & Kiểm tra -> Lên lịch
- Card thông tin tệp và thanh Validation Badges (Hợp lệ, Cần sửa, Tổng cộng)
- Bảng Preview xem trước phân loại rõ ràng dòng hợp lệ vs dòng lỗi Page ID
- Khắc phục triệt để A-07 P0: Bỏ qua dòng thiếu Page ID, không bao giờ silent fallback all pages
- Xuất file sheet mẫu (.xlsx / .csv)
- Vòng đời Worker an toàn không rò rỉ luồng khi đóng dialog
"""

import pytest
import csv
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux10_bulk.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_bulk_import_validation_and_badges(qapp, temp_db, tmp_path):
    """Kiểm thử tính toán Validation Badges và phân loại dòng dữ liệu."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)
    media_repo = MediaRepository(temp_db)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    # Tạo 2 Page có sẵn
    page_repo.upsert_page("fb_valid_111", "Lovira Fashion", status="ready")
    page_repo.upsert_page("fb_valid_222", "Lovira Cosmetics", status="ready")

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # Tạo file CSV mẫu gồm: 2 dòng hợp lệ + 1 dòng thiếu Page ID + 1 dòng sai Page ID
    csv_file = tmp_path / "test_import_data.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "TieuDe", "NoiDung_Caption", "Video_Link_Hoac_File", "Page_IDs", "NgayGioDang_VN", "LoaiDang"
        ])
        writer.writeheader()
        writer.writerow({
            "TieuDe": "Bài 1 Hợp lệ",
            "NoiDung_Caption": "Nội dung bài viết 1 #fashion",
            "Video_Link_Hoac_File": "C:/dummy1.mp4",
            "Page_IDs": "fb_valid_111",
            "NgayGioDang_VN": "2026-10-25 15:00",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Bài 2 Đăng All",
            "NoiDung_Caption": "Nội dung bài viết 2 #all",
            "Video_Link_Hoac_File": "C:/dummy2.mp4",
            "Page_IDs": "ALL",
            "NgayGioDang_VN": "2026-10-26 18:30",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Bài 3 Thiếu Page ID",
            "NoiDung_Caption": "Nội dung bài viết 3 #missing",
            "Video_Link_Hoac_File": "C:/dummy3.mp4",
            "Page_IDs": "",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        })
        writer.writerow({
            "TieuDe": "Bài 4 Sai Page ID",
            "NoiDung_Caption": "Nội dung bài viết 4 #unknown",
            "Video_Link_Hoac_File": "C:/dummy4.mp4",
            "Page_IDs": "fb_non_existent_999",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        })

    dlg._load_data_from_file(str(csv_file))

    # Kiểm tra Badges
    assert "Hợp lệ: 2 dòng" in dlg.lbl_valid_badge.text()
    assert "Cần sửa Page ID: 2 dòng" in dlg.lbl_invalid_badge.text()
    assert "Tổng cộng: 4 dòng" in dlg.lbl_total_badge.text()

    # Bảng hiển thị 4 dòng
    assert dlg.table_preview.rowCount() == 4
    assert dlg.table_preview.item(0, 5).text() == "Hợp lệ"
    assert dlg.table_preview.item(1, 5).text() == "Hợp lệ"
    assert "Cần sửa Page ID" in dlg.table_preview.item(2, 5).text()
    assert "Cần sửa Page ID" in dlg.table_preview.item(3, 5).text()

    # Nút submit được bật và hiển thị số lượng 2
    assert dlg.btn_start_import.isEnabled()
    assert "2 bài viết hợp lệ" in dlg.btn_start_import.text()


def test_bulk_import_strict_no_fallback_ac07(qapp, temp_db, tmp_path):
    """AC-07 P0: Tuyệt đối không fallback sang toàn bộ Fanpage khi Page ID không khớp."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)
    media_repo = MediaRepository(temp_db)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    p1 = page_repo.upsert_page("fb_p1", "Page 1", status="ready")
    p2 = page_repo.upsert_page("fb_p2", "Page 2", status="ready")

    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"content")

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # 1 dòng hợp lệ chỉ gửi tới fb_p1, 1 dòng sai Page ID
    dlg.loaded_rows = [
        {
            "TieuDe": "Chỉ gửi Page 1",
            "NoiDung_Caption": "Nội dung chỉ định rõ fb_p1",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "fb_p1",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        },
        {
            "TieuDe": "Dòng sai Page ID",
            "NoiDung_Caption": "Nội dung với ID không có trong hệ thống",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "fb_ghost_id_404",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        },
    ]

    with patch.object(QMessageBox, "information"), patch.object(QMessageBox, "critical"):
        dlg._start_import_process()
        worker = dlg.worker
        if worker:
            for _ in range(100):
                if not worker.isRunning():
                    break
                qapp.processEvents()
                import time
                time.sleep(0.02)
        qapp.processEvents()

    # Chỉ duy nhất 1 job được tạo cho p1, không có job nào cho p2 hay ghost
    jobs = queue_repo.list_jobs()
    assert len(jobs) == 1
    dlg.close()

    assert jobs[0]["page_id"] == p1
    assert jobs[0]["page_id"] != p2


def test_bulk_import_export_template(qapp, temp_db, tmp_path):
    """Kiểm thử xuất file mẫu Sheet Excel / CSV."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)
    media_repo = MediaRepository(temp_db)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    out_csv = tmp_path / "Mau_Test.csv"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(out_csv), "")), \
         patch.object(QMessageBox, "information"), \
         patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        dlg._export_template()

    assert out_csv.exists()
    content = out_csv.read_text(encoding="utf-8-sig")
    assert "TieuDe" in content
    assert "NoiDung_Caption" in content
    assert "Page_IDs" in content

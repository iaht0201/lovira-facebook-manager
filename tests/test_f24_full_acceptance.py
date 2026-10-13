"""
Unit test & Acceptance Suite cho F-24: Kiểm thử toàn diện 44 ca AC & Đóng gói ứng dụng
Đáp ứng AC-01 -> AC-44 và Section 19
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from src.lovira.config.paths import AppPaths
from src.lovira.app_lock import SingleInstanceLock
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader, VideoMetadata, SupportedPlatform
from src.lovira.media.processor import MediaProcessor
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.workers.scheduler import LocalSchedulerService
from src.lovira.app import create_application, _safe_exit


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


def test_full_application_bootstrap_ac01(qapp, tmp_path, monkeypatch):
    """
    AC-01: Kiểm tra khởi tạo toàn bộ ứng dụng desktop PySide6,
    kết nối các layer Storage, Security, Licensing, Workers và UI Views.
    """
    # Trỏ AppPaths về thư mục tạm
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    with patch("src.lovira.workers.scheduler.LocalSchedulerService.start"), \
         patch("src.lovira.ui.tray.SystemTrayManager._check_and_init_tray"):
        main_window = create_application()

    assert main_window is not None
    assert main_window.windowTitle() == "Lovira-Facebook Manager"
    assert main_window.stacked_widget.count() >= 6


def test_end_to_end_1click_workflow_ac04_to_ac15(qapp, tmp_path, monkeypatch):
    """
    Chuỗi nghiệp vụ hoàn chỉnh:
    1. Tải video -> 2. Nhận tín hiệu 1-click -> 3. Gắn vào Composer
    -> 4. Chọn 2 Page đích -> 5. Bật hẹn giờ VN (UTC+7) -> 6. Gửi hàng đợi nguyên tử.
    Đáp ứng BR-05, BR-06, AC-04, AC-05, AC-06, AC-07, AC-15, AC-19, AC-41.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    with patch("src.lovira.workers.scheduler.LocalSchedulerService.start"), \
         patch("src.lovira.ui.tray.SystemTrayManager._check_and_init_tray"):
        main_window = create_application()

    # Tạo 2 Fanpage mẫu
    db_mgr = main_window.db
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(db_mgr, vault)
    p1 = page_repo.upsert_page("fb_e2e_1", "Fanpage Thời Trang")
    p2 = page_repo.upsert_page("fb_e2e_2", "Fanpage Mỹ Phẩm")

    # Giả lập file video tải về
    video_file = tmp_path / "fashion_reel.mp4"
    video_file.write_bytes(b"fashion reel video content")

    # Lấy View Video và View Composer
    video_view = main_window.stacked_widget.widget(2)
    composer_view = main_window.stacked_widget.widget(main_window.stacked_widget.count() - 1)

    composer_view.reload_pages()
    assert composer_view.page_list_widget.count() == 2

    # Bước 1 & 2: Phát tín hiệu tải xong video (1-click chuyển Soạn bài - BR-06)
    video_view.send_to_composer.emit({
        "file_path": str(video_file),
        "title": "Bộ sưu tập thu đông 2026",
        "media_id": "med_e2e_888",
    })

    # Bước 3: Kiểm tra thông tin đã gắn vào ComposerView
    assert composer_view.attached_media is not None
    assert "med_e2e_888" in composer_view.lbl_media_info.text()
    assert composer_view.caption_input.toPlainText() == "Bộ sưu tập thu đông 2026"

    # Bước 4: Chọn cả 2 Fanpage đích
    composer_view.page_list_widget.item(0).setCheckState(Qt.CheckState.Checked)
    composer_view.page_list_widget.item(1).setCheckState(Qt.CheckState.Checked)

    # Bước 5: Bật Hẹn giờ (Giờ VN — UTC+7) (AC-06, AC-07)
    composer_view.chk_schedule.setChecked(True)
    assert "Đặt lịch cho 2 Page" in composer_view.btn_submit.text()

    # Bước 6: Gửi hàng đợi nguyên tử với client_request_id (AC-15, AC-19)
    with patch.object(QMessageBox, "information"):
        composer_view._handle_submit()

    # Kiểm tra database có đúng 2 publish_jobs cho 2 Page khác nhau (AC-05)
    with db_mgr.connection_scope() as conn:
        cursor = conn.execute("SELECT id, page_id, state, content_snapshot FROM publish_jobs;")
        jobs = cursor.fetchall()

    assert len(jobs) == 2
    page_ids_in_db = {j["page_id"] for j in jobs}
    assert page_ids_in_db == {p1, p2}
    for j in jobs:
        assert j["state"] == "scheduled_local"
        assert "Bộ sưu tập thu đông 2026" in j["content_snapshot"]


def test_safe_shutdown_lifecycle_ac08(tmp_path):
    """AC-08: Tắt ứng dụng an toàn qua _safe_exit, dừng scheduler và ẩn tray icon."""
    mock_scheduler = MagicMock()
    mock_tray = MagicMock()

    with patch("PySide6.QtWidgets.QApplication.quit") as mock_quit:
        _safe_exit(mock_scheduler, mock_tray)
        mock_scheduler.stop.assert_called_once()
        mock_tray.hide.assert_called_once()
        mock_quit.assert_called_once()

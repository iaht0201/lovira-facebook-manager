"""
Lovira-Facebook Manager
Kiểm thử các Cải tiến UX & Nghiệp vụ Mới:
1. Dashboard Tổng quan (OverviewWorkspaceView)
2. Popup Tạo bài nhanh (QuickPostDialog)
3. Kết nối Fanpage qua Page ID & Token (ConnectPageDialog)
4. Tải video hàng loạt & Xem lại video đã tải (VideoWorkspaceView)
5. Nhập Lịch đăng từ Sheet mẫu Excel / CSV (BulkImportDialog)
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager, RemoteAppConfig
from src.lovira.integrations.facebook.client import FacebookGraphClient, FBTokenInfo
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader, VideoMetadata
from src.lovira.media.processor import MediaProcessor

from src.lovira.ui.views.overview_workspace import OverviewWorkspaceView
from src.lovira.ui.quick_post_dialog import QuickPostDialog
from src.lovira.ui.views.pages_workspace import ConnectPageDialog
from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog


from src.lovira.storage.migrations import MigrationRunner

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux.db"
    db = DatabaseManager(db_file)
    MigrationRunner(db).apply_all()
    return db


def test_overview_workspace_ui(qapp, temp_db, tmp_path):
    """Kiểm tra Dashboard Tổng quan: hiển thị các thông số metric và nạp tác vụ gần đây."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    media_repo = MediaRepository(temp_db)
    queue_repo = PublishQueueRepository(temp_db)

    # Thêm 2 page
    page_repo.upsert_page("p1", "Fanpage 1", status="ready")
    page_repo.upsert_page("p2", "Fanpage 2", status="ready")

    # Mock license
    client = MagicMock(spec=LicenseClient)
    client.is_active = True
    client.current_session = MagicMock(session_id="sess_123456789")
    policy = AccessPolicyManager(RemoteAppConfig(license_required=True))

    view = OverviewWorkspaceView(temp_db, page_repo, media_repo, queue_repo, client, policy)
    assert view.card_pages.lbl_val.text() == "2"
    assert "2 Fanpage" in view.card_pages.lbl_sub.text()
    assert view.card_status.lbl_val.text() == "Đã kích hoạt"


def test_quick_post_popup_dialog(qapp, temp_db, tmp_path):
    """Kiểm tra QuickPostDialog: chọn page, nhập caption, đính kèm video và enqueue."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)

    pid = page_repo.upsert_page("fb_100", "Page Ban Hang", status="ready")

    dummy_video = tmp_path / "test_reels.mp4"
    dummy_video.write_bytes(b"dummy mp4")

    dlg = QuickPostDialog(page_repo, queue_repo)
    dlg.caption_edit.setPlainText("Caption test bai viet nhanh #reels")
    dlg.attach_video(str(dummy_video), media_id="med_test_1")

    with patch.object(QMessageBox, "information"):
        dlg._handle_submit()

    # Kiểm tra job trong database
    jobs = queue_repo.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["page_id"] == pid
    assert "Caption test bai viet" in jobs[0]["snapshot_caption"]


def test_connect_page_dialog_direct_page_id(qapp, temp_db, tmp_path):
    """Kiểm tra ConnectPageDialog Tab 1: Kết nối trực tiếp Page ID và Page Token."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    dialog = ConnectPageDialog(fb_client, page_repo)
    dialog.tab_widget.setCurrentIndex(0)
    dialog.input_page_id.setText("9988776655")
    dialog.input_page_name.setText("Lovira Page Truc Tiep")
    dialog.input_page_token.setText("EAAB_test_page_token")

    with patch.object(fb_client, "inspect_token", return_value=None), \
         patch.object(QMessageBox, "warning"), \
         patch.object(QMessageBox, "information"):
        dialog._handle_connect()

    pages = page_repo.list_pages()
    assert len(pages) == 1
    assert pages[0]["facebook_page_id"] == "9988776655"
    assert pages[0]["name"] == "Lovira Page Truc Tiep"
    assert pages[0]["status"] == "unverified"


def test_bulk_import_dialog_export_and_process(qapp, temp_db, tmp_path):
    """Kiểm tra BulkImportDialog: Đọc dòng dữ liệu CSV/Excel và enqueue batch."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)
    media_repo = MediaRepository(temp_db)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    pid = page_repo.upsert_page("100085942398412", "Lovira Media", status="ready")

    dummy_video = tmp_path / "import_video.mp4"
    dummy_video.write_bytes(b"dummy video data for import")

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # Nạp 1 dòng dữ liệu giả lập
    dlg.loaded_rows = [
        {
            "TieuDe": "Video Import Test",
            "NoiDung_Caption": "Caption từ file Excel #import",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "100085942398412",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        }
    ]

    with patch.object(QMessageBox, "information"):
        dlg._start_import_process()
        worker = dlg.worker
        if worker:
            worker.wait(5000)
        qapp.processEvents()

    # Kiểm tra job trong database
    jobs = queue_repo.list_jobs()
    assert len(jobs) >= 1
    assert "Caption từ file Excel" in jobs[0]["snapshot_caption"]

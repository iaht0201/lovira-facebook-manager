"""
Kiểm thử chuyên biệt cho Task UX-01: Safety Fixes & P0 Audit (DoD Compliance)
- Kiểm tra cơ chế fail-safe: Cột Page_IDs rỗng hoặc sai trong Bulk Import không bao giờ fallback sang all pages.
- Kiểm tra Page Connection: Token không được xác thực không bao giờ được gán status='ready'.
- Kiểm tra License Backend: OfflineFallbackLicenseBackend fail-closed và chặn publish khi không có license.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication, QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.security.vault import SecretVault
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.integrations.facebook.client import FacebookGraphClient, FBTokenInfo
from src.lovira.integrations.downloaders.video_downloader import VideoDownloader
from src.lovira.media.processor import MediaProcessor
from src.lovira.licensing.client import LicenseClient, OfflineFallbackLicenseBackend
from src.lovira.licensing.models import LicenseErrorCode
from src.lovira.licensing.policy import AccessPolicyManager, RemoteAppConfig
from src.lovira.ui.views.bulk_import_dialog import BulkImportDialog
from src.lovira.ui.views.pages_workspace import ConnectPageDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux01.db"
    db_manager = DatabaseManager(db_file)
    MigrationRunner(db_manager).apply_all()
    return db_manager


def test_bulk_import_empty_or_unknown_page_id_no_fallback(qapp, temp_db, tmp_path):
    """DoD UX-01: Cột Page_IDs rỗng hoặc chứa ID không tồn tại TUYỆT ĐỐI không fallback sang all pages."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)
    media_repo = MediaRepository(temp_db)
    downloader = VideoDownloader()
    media_processor = MediaProcessor()

    # Tạo 2 Fanpage sẵn có
    p1 = page_repo.upsert_page("111111", "Page One", status="ready")
    p2 = page_repo.upsert_page("222222", "Page Two", status="ready")

    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"dummy")

    dlg = BulkImportDialog(
        page_repo=page_repo,
        queue_repo=queue_repo,
        media_repo=media_repo,
        downloader=downloader,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # 1. Thử nghiệm với Page_IDs rỗng
    dlg.loaded_rows = [
        {
            "TieuDe": "Bai viet rong Page ID",
            "NoiDung_Caption": "Test caption",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        }
    ]

    with patch.object(QMessageBox, "information"):
        dlg._start_import_process()
        if dlg.worker:
            dlg.worker.wait(5000)

    # Không được tạo bất kỳ job nào!
    jobs = queue_repo.list_jobs()
    assert len(jobs) == 0, "LỖI P0: Dòng thiếu Page_IDs đã tự động fallback sang all pages!"

    # 2. Thử nghiệm với Page_IDs lạ không tồn tại trong hệ thống
    dlg.loaded_rows = [
        {
            "TieuDe": "Bai viet ID la",
            "NoiDung_Caption": "Test caption 2",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "999999999_UNKNOWN",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        }
    ]

    with patch.object(QMessageBox, "information"):
        dlg._start_import_process()
        if dlg.worker:
            dlg.worker.wait(5000)

    # Vẫn không được tạo bất kỳ job nào!
    jobs = queue_repo.list_jobs()
    assert len(jobs) == 0, "LỖI P0: Dòng chứa Page ID lạ đã tự động fallback sang all pages!"

    # 3. Thử nghiệm với từ khóa ALL tường minh -> Lúc này mới đăng cho cả 2 Page
    dlg.loaded_rows = [
        {
            "TieuDe": "Bai viet dang ALL",
            "NoiDung_Caption": "Test caption all",
            "Video_Link_Hoac_File": str(dummy_video),
            "Page_IDs": "ALL",
            "NgayGioDang_VN": "",
            "LoaiDang": "reels",
        }
    ]

    with patch.object(QMessageBox, "information"):
        dlg._start_import_process()
        if dlg.worker:
            dlg.worker.wait(5000)

    jobs = queue_repo.list_jobs()
    assert len(jobs) == 2, "Từ khóa ALL tường minh phải tạo job cho cả 2 Page."


def test_connect_page_direct_valid_token_marks_ready(qapp, temp_db, tmp_path):
    """DoD UX-01: Nhập Page Token hợp lệ có quyền CREATE_CONTENT được gán status='ready'."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    dialog = ConnectPageDialog(fb_client, page_repo)
    dialog.tab_widget.setCurrentIndex(0)
    dialog.input_page_id.setText("888777666")
    dialog.input_page_name.setText("Lovira Valid Page")
    dialog.input_page_token.setText("EAAB_valid_page_token")

    mock_info = FBTokenInfo(
        is_valid=True,
        token_type="PAGE",
        id="888777666",
        name="Lovira Valid Page",
        tasks=["MANAGE", "CREATE_CONTENT"],
    )

    with patch.object(fb_client, "inspect_token", return_value=mock_info), \
         patch.object(QMessageBox, "information"):
        dialog._handle_connect()

    pages = page_repo.list_pages()
    assert len(pages) == 1
    assert pages[0]["facebook_page_id"] == "888777666"
    assert pages[0]["status"] == "ready"


def test_connect_page_direct_insufficient_perms_marks_status(qapp, temp_db, tmp_path):
    """DoD UX-01: Token hợp lệ nhưng thiếu quyền CREATE_CONTENT được gán status='insufficient_permissions'."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    dialog = ConnectPageDialog(fb_client, page_repo)
    dialog.tab_widget.setCurrentIndex(0)
    dialog.input_page_id.setText("555444333")
    dialog.input_page_name.setText("ReadOnly Page")
    dialog.input_page_token.setText("EAAB_read_only_token")

    mock_info = FBTokenInfo(
        is_valid=True,
        token_type="PAGE",
        id="555444333",
        name="ReadOnly Page",
        tasks=["ANALYZE"],  # Không có CREATE_CONTENT hay MANAGE
    )

    with patch.object(fb_client, "inspect_token", return_value=mock_info), \
         patch.object(QMessageBox, "warning"):
        dialog._handle_connect()

    pages = page_repo.list_pages()
    assert len(pages) == 1
    assert pages[0]["status"] == "insufficient_permissions"


def test_offline_fallback_license_backend_fail_closed():
    """DoD UX-01: OfflineFallbackLicenseBackend fail-closed và AccessPolicyManager chặn publish."""
    backend = OfflineFallbackLicenseBackend()
    res = backend.activate("KEY-1234", "DEV-1", "FP-1", "0.1.0", False)
    assert not res.success
    assert res.error_code == LicenseErrorCode.NETWORK_ERROR

    client = LicenseClient(backend, "DEV-1", "FP-1")
    assert not client.is_active

    # Cấu hình còn hạn nhưng license_required=True và không có session -> chặn publish
    config = RemoteAppConfig(
        license_required=True,
        expires_at_utc="2099-01-01T00:00:00Z",
    )
    policy = AccessPolicyManager(config)
    allowed, msg = policy.evaluate_action("publish_post", client.current_session, is_online=True)
    assert not allowed
    assert "Yêu cầu kích hoạt License Key" in msg

    # Các thao tác local vẫn được bảo vệ
    local_allowed, _ = policy.evaluate_action("view_local_data", client.current_session, is_online=False)
    assert local_allowed

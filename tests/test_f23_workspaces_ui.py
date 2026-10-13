"""
Unit test cho F-23: Giao diện Quản lý Page, Lịch & Nhật ký
Đáp ứng BR-03, BR-04, AC-02, AC-03, AC-11, AC-14, AC-20, AC-22
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QFileDialog
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault
from src.lovira.integrations.facebook.client import FacebookGraphClient, FBTokenInfo
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.licensing.client import LicenseClient
from src.lovira.ui.views.pages_workspace import PagesWorkspaceView, ConnectPageDialog
from src.lovira.ui.views.schedule_workspace import ScheduleWorkspaceView
from src.lovira.ui.views.settings_workspace import SettingsWorkspaceView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_workspaces.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_pages_workspace_unlink_page_warning_ac11(qapp, temp_db, tmp_path):
    """AC-11: Gỡ Page đang có lịch local và remote hiển thị cảnh báo tác động."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p_id = page_repo.upsert_page("fb_warn_1", "Fanpage Có Lịch")

    # Tạo lịch local và remote
    with temp_db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_local_1', 'b1', 'req1', ?, '{"final_caption": "Test"}', 'scheduled_local', '2026-10-20T10:00:00Z');
            """,
            (p_id,),
        )
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_remote_1', 'b2', 'req2', ?, '{"final_caption": "Test"}', 'scheduled_remote', '2026-10-20T10:00:00Z');
            """,
            (p_id,),
        )

    fb_client = FacebookGraphClient()
    view = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)
    assert view.table.rowCount() == 1

    view.table.selectRow(0)

    # Giả lập bấm Gỡ Fanpage -> Phải hiển thị cảnh báo AC-11 với số lượng lịch
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:
        view._handle_unlink_page()
        mock_q.assert_called_once()
        warn_text = mock_q.call_args[0][2]
        assert "AC-11" in mock_q.call_args[0][1]
        assert "1 lịch hẹn giờ trên máy" in warn_text
        assert "1 lịch Facebook đã nhận" in warn_text


def test_connect_page_dialog_page_token_ac03(qapp, temp_db, tmp_path):
    """AC-03: Nhập Page Token trực tiếp chỉ lấy thông tin Page đó."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    mock_info = FBTokenInfo(
        is_valid=True,
        token_type="PAGE",
        id="fb_direct_999",
        name="Direct Connected Page",
        tasks=["CREATE_CONTENT"],
    )

    dialog = ConnectPageDialog(fb_client, page_repo)
    dialog.token_input.setText("EAAB_valid_page_token")

    with patch.object(fb_client, "inspect_token", return_value=mock_info), \
         patch.object(QMessageBox, "information"):
        dialog._handle_connect()

    pages = page_repo.list_pages()
    assert len(pages) == 1
    assert pages[0]["facebook_page_id"] == "fb_direct_999"


def test_schedule_workspace_reconcile_ac14(qapp, temp_db):
    """AC-14: Đối chiếu tác vụ unknown qua RecoveryManager."""
    queue = PublishQueueRepository(temp_db)
    recovery_mock = MagicMock(spec=RecoveryManager)
    recovery_mock.reconcile_job.return_value = (True, "Đối chiếu thành công: Bài viết đã xuất hiện trên Facebook.")

    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p1', 'fb1', 'Page 1');")
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_unknown_1', 'b1', 'req1', 'p1', '{"final_caption": "Test"}', 'unknown', '2026-10-20T10:00:00Z');
            """
        )

    view = ScheduleWorkspaceView(db_manager=temp_db, queue_repo=queue, recovery_manager=recovery_mock)
    assert view.table.rowCount() == 1

    view.table.selectRow(0)

    with patch.object(QMessageBox, "information") as mock_info:
        view._handle_reconcile()
        mock_info.assert_called_once()
        recovery_mock.reconcile_job.assert_called_with("job_unknown_1")


def test_settings_workspace_backup_ac22(qapp, temp_db, tmp_path):
    """AC-22: Sao lưu online database an toàn."""
    mock_client = MagicMock(spec=LicenseClient)
    mock_client.device_id = "test_device_123"

    view = SettingsWorkspaceView(db_manager=temp_db, license_client=mock_client)
    backup_file = tmp_path / "backup_out.db"

    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(backup_file), "")), \
         patch.object(QMessageBox, "information"):
        view._handle_backup()

    assert backup_file.exists()

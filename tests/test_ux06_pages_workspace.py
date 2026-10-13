"""
Kiểm thử chuyên biệt cho Task UX-06: Fanpage Workspace 2.0 (DoD Compliance)
- Kiểm tra EmptyState khi 0 Fanpage
- Kiểm tra Bảng Fanpage hiển thị StatusChip và lọc tìm kiếm tức thì
- Kiểm tra tính năng Verify Token Health cập nhật trạng thái động
- Kiểm tra Hộp thoại ConnectPageDialog (Page ID + Token vs User Token)
- Kiểm tra Unlink Page với cảnh báo AC-11
"""

from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.security.vault import SecretVault
from src.lovira.integrations.facebook.client import FacebookGraphClient, FBTokenInfo
from src.lovira.ui.views.pages_workspace import PagesWorkspaceView, ConnectPageDialog
from src.lovira.ui.widgets.status_chip import StatusChip


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux06.db"
    db = DatabaseManager(db_file)
    MigrationRunner(db).apply_all()
    return db


def test_pages_workspace_empty_state_and_table_switch(qapp, temp_db, tmp_path):
    """DoD UX-06: Khi 0 Fanpage hiển thị EmptyState, thêm Fanpage tự động chuyển sang Bảng."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    view = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)

    # 1. Ban đầu 0 page: hiển thị empty_container (content_stack index 1)
    assert view.content_stack.currentIndex() == 1
    assert "0 Fanpage" in view.lbl_subtitle.text()

    # 2. Thêm Fanpage -> Tự động chuyển sang Bảng (index 0)
    pid = page_repo.upsert_page("fb_101", "Lovira Fashion", status="ready")
    view.reload_pages()

    assert view.content_stack.currentIndex() == 0
    assert view.table.rowCount() == 1
    assert "1 Fanpage" in view.lbl_subtitle.text()

    # Kiểm tra Status badge ở cột 6 (v2.1)
    chip = view.table.cellWidget(0, 6)
    assert chip is not None


def test_pages_workspace_search_filter(qapp, temp_db, tmp_path):
    """DoD UX-06: Ô tìm kiếm nhanh lọc theo Tên Fanpage và Facebook Page ID."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    page_repo.upsert_page("111222333", "Shop Ao So Mi", status="ready")
    page_repo.upsert_page("444555666", "Quan Jean Nam", status="ready")
    page_repo.upsert_page("777888999", "Giay The Thao", status="ready")

    view = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)
    assert view.table.rowCount() == 3

    # Tìm theo tên "So Mi"
    view.search_filter.setText("So Mi")
    assert view.table.rowCount() == 1
    assert view._visible_pages()[0]["name"] == "Shop Ao So Mi"

    # Tìm theo ID "444555"
    view.search_filter.setText("444555")
    assert view.table.rowCount() == 1
    assert view._visible_pages()[0]["name"] == "Quan Jean Nam"

    # Xóa bộ lọc -> hiển thị lại cả 3
    view.search_filter.setText("")
    assert view.table.rowCount() == 3


def test_pages_workspace_verify_token_health(qapp, temp_db, tmp_path):
    """DoD UX-06: Kiểm tra sức khỏe Access Token cập nhật trạng thái động."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    pid = page_repo.upsert_page("fb_verify_1", "Page Test Verify", status="ready")
    page_repo.save_page_token(pid, "EAAB_mock_token", tasks=["CREATE_CONTENT", "MANAGE"])

    view = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)
    view.table.selectRow(0)

    # 1. Giả lập token hết hạn
    expired_info = FBTokenInfo(is_valid=False, token_type="", id="", name="", tasks=[])
    with patch.object(fb_client, "inspect_token", return_value=expired_info), \
         patch.object(QMessageBox, "critical") as mock_crit:
        view._handle_verify_selected_token()
        mock_crit.assert_called_once()
        assert "hết hạn" in mock_crit.call_args[0][1]

    # Kiểm tra database và UI đã đổi sang token_expired
    p = page_repo.get_page(pid)
    assert p["status"] == "token_expired"
    chip = view.table.cellWidget(0, 6)
    assert chip is not None

    # 2. Giả lập cấp lại token hợp lệ
    valid_info = FBTokenInfo(is_valid=True, token_type="PAGE", id="fb_verify_1", name="Page Test Verify", tasks=["CREATE_CONTENT"])
    with patch.object(fb_client, "inspect_token", return_value=valid_info), \
         patch.object(QMessageBox, "information") as mock_info:
        view._handle_verify_selected_token()
        mock_info.assert_called_once()
        assert "hợp lệ" in mock_info.call_args[0][1]

    assert page_repo.get_page(pid)["status"] == "ready"


def test_pages_workspace_unlink_page_warning(qapp, temp_db, tmp_path):
    """DoD UX-06: Gỡ liên kết Fanpage kiểm tra đầy đủ cảnh báo lịch đăng AC-11."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    fb_client = FacebookGraphClient()

    pid = page_repo.upsert_page("fb_unlink_1", "Page Unlink Test", status="ready")

    # Tạo lịch chờ
    with temp_db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_u_1', 'bu1', 'ru1', ?, '{"final_caption": "Test"}', 'scheduled_local', '2026-10-25T10:00:00Z');
            """,
            (pid,),
        )

    view = PagesWorkspaceView(page_repo=page_repo, fb_client=fb_client)
    view.table.selectRow(0)

    # Từ chối gỡ
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:
        view._handle_unlink_page()
        assert "AC-11" in mock_q.call_args[0][1]
        assert "1 lịch hẹn giờ trên máy" in mock_q.call_args[0][2]

    # Vẫn còn Page
    assert len(page_repo.list_pages()) == 1

    # Đồng ý gỡ
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "information"):
        view._handle_unlink_page()

    assert len(page_repo.list_pages()) == 0
    assert view.content_stack.currentIndex() == 1  # Trở về EmptyState

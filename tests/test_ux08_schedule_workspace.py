"""
Unit tests cho UX-08: Schedule Workspace 2.0 (schedule_workspace.py)
Kiểm thử toàn diện:
- KPI Strip 4 chỉ số (Lịch trên máy, FB đã nhận, Đã đăng, Sự cố)
- Bảng lịch 6 cột tích hợp StatusChip & format giờ VN (UTC+7)
- Bộ lọc combobox trạng thái & Live search filter theo Job ID / Caption
- Chuyển đổi linh hoạt giữa QTableWidget và EmptyState onboarding
- Thao tác: Tạm dừng / Tiếp tục, Thử lại tác vụ lỗi, Hủy lịch, Đối chiếu AC-14
- Tương thích GlobalPageContext
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.views.schedule_workspace import ScheduleWorkspaceView
from src.lovira.ui.widgets.status_chip import StatusChip


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux08_schedule.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


@pytest.fixture
def seed_jobs(temp_db):
    """Tạo dữ liệu mẫu gồm nhiều trạng thái khác nhau."""
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p1', 'fb_p1', 'Lovira Fashion');")
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p2', 'fb_p2', 'Lovira Cosmetics');")

        jobs = [
            (
                "job_local_01", "p1",
                json.dumps({"final_caption": "Bộ sưu tập mùa đông mới nhất 2026 #fashion"}),
                "scheduled_local", "2026-10-25T08:00:00Z", None, None
            ),
            (
                "job_remote_02", "p1",
                json.dumps({"final_caption": "Áo khoác dạ cao cấp phong cách Hàn Quốc"}),
                "scheduled_remote", "2026-10-26T09:30:00Z", None, None
            ),
            (
                "job_pub_03", "p2",
                json.dumps({"final_caption": "Son kem lì Lovira Matte Red siêu dưỡng"}),
                "published", "2026-10-20T12:00:00Z", None, None
            ),
            (
                "job_err_04", "p2",
                json.dumps({"final_caption": "Kem chống nắng phổ rộng SPF 50+"}),
                "failed_retryable", "2026-10-21T03:00:00Z", "Network timeout during upload", "ERR_NET_TIMEOUT"
            ),
            (
                "job_missed_05", "p1",
                json.dumps({"final_caption": "Flash sale nửa đêm"}),
                "missed", "2026-10-15T17:00:00Z", "Máy tắt khi đến lịch hẹn", "ERR_MACHINE_OFFLINE"
            ),
            (
                "job_unknown_06", "p2",
                json.dumps({"final_caption": "Serum phục hồi B5"}),
                "unknown", "2026-10-22T05:00:00Z", "Mất kết nối giữa chừng", "ERR_UNKNOWN_STATE"
            ),
        ]

        for j_id, p_id, snap, st, sched_time, reason, err_code in jobs:
            conn.execute(
                """
                INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc, blocked_reason, last_error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (j_id, f"batch_{j_id}", f"req_{j_id}", p_id, snap, st, sched_time, reason, err_code)
            )


def test_schedule_workspace_kpi_and_display(qapp, temp_db, seed_jobs):
    """Kiểm thử tính toán KPI Strip và hiển thị bảng với StatusChip."""
    queue = PublishQueueRepository(temp_db)
    view = ScheduleWorkspaceView(db_manager=temp_db, queue_repo=queue)

    # 1. Kiểm tra KPI strip
    # local: 1 (job_local_01)
    # remote: 1 (job_remote_02)
    # pub: 1 (job_pub_03)
    # issues: missed (1) + unknown (1) = 2
    assert "Lịch trên máy: 1" in view.lbl_kpi_local.text()
    assert "Facebook đã nhận: 1" in view.lbl_kpi_remote.text()
    assert "Đã đăng thành công: 1" in view.lbl_kpi_published.text()
    assert "Sự cố / Cần xử lý: 2" in view.lbl_kpi_issues.text()

    # 2. Bảng hiển thị 6 dòng
    assert view.content_stack.currentIndex() == 0  # Table view active
    assert view.table.rowCount() == 6
    assert view.table.columnCount() == 6

    # 3. Kiểm tra StatusChip ở cột 4
    chip_row0 = view.table.cellWidget(0, 4)
    assert isinstance(chip_row0, StatusChip)


def test_schedule_workspace_filter_and_search(qapp, temp_db, seed_jobs):
    """Kiểm thử lọc trạng thái và tìm kiếm thời gian thực."""
    queue = PublishQueueRepository(temp_db)
    view = ScheduleWorkspaceView(db_manager=temp_db, queue_repo=queue)

    # Lọc theo 'scheduled_local'
    idx = view.cb_filter_state.findText("Đã lên lịch máy (scheduled_local)")
    assert idx >= 0
    view.cb_filter_state.setCurrentIndex(idx)
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "job_local_01"

    # Trả lại 'Tất cả'
    view.cb_filter_state.setCurrentIndex(0)
    assert view.table.rowCount() == 6

    # Tìm kiếm theo từ khóa trong caption
    view.search_filter.setText("Son kem lì")
    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == "job_pub_03"

    # Tìm kiếm từ khóa không tồn tại -> Chuyển sang EmptyState
    view.search_filter.setText("xyz_not_exist_query_1234")
    assert view.content_stack.currentIndex() == 1  # EmptyState view active

    # Xóa tìm kiếm -> Quay lại bảng
    view.search_filter.clear()
    assert view.content_stack.currentIndex() == 0
    assert view.table.rowCount() == 6


def test_schedule_workspace_pause_and_retry(qapp, temp_db, seed_jobs):
    """Kiểm thử tạm dừng/tiếp tục và thử lại tác vụ lỗi."""
    queue = PublishQueueRepository(temp_db)
    view = ScheduleWorkspaceView(db_manager=temp_db, queue_repo=queue)

    # 1. Tạm dừng job_local_01
    # Tìm dòng chứa job_local_01
    target_row = -1
    for r in range(view.table.rowCount()):
        if view.table.item(r, 0).text() == "job_local_01":
            target_row = r
            break
    assert target_row >= 0
    view.table.selectRow(target_row)

    view._handle_pause_toggle()
    job_updated = queue.get_job("job_local_01")
    assert job_updated["state"] == "paused"

    # Tiếp tục lại
    view._handle_pause_toggle()
    job_resumed = queue.get_job("job_local_01")
    assert job_resumed["state"] == "scheduled_local"

    # 2. Thử lại job_err_04 (đang failed_retryable)
    for r in range(view.table.rowCount()):
        if view.table.item(r, 0).text() == "job_err_04":
            target_row = r
            break
    view.table.selectRow(target_row)

    with patch.object(QMessageBox, "information") as mock_info:
        view._handle_retry_job()
        mock_info.assert_called_once()

    job_retried = queue.get_job("job_err_04")
    assert job_retried["state"] == "scheduled_local"


def test_schedule_workspace_cancel_and_global_context(qapp, temp_db, seed_jobs):
    """Kiểm thử hủy lịch và đồng bộ hóa với GlobalPageContext."""
    queue = PublishQueueRepository(temp_db)
    context = GlobalPageContext()
    view = ScheduleWorkspaceView(db_manager=temp_db, queue_repo=queue, page_context=context)

    # Ban đầu có 6 jobs
    assert view.table.rowCount() == 6

    # Đổi phạm vi GlobalPageContext sang 'p1' (Lovira Fashion)
    context.set_selected_page("p1")
    # p1 có 3 jobs: job_local_01, job_remote_02, job_missed_05
    assert view.table.rowCount() == 3

    # Hủy một job của p1
    view.table.selectRow(0)
    cancelled_job_id = view.table.item(0, 0).text()

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view._handle_cancel_job()

    job = queue.get_job(cancelled_job_id)
    assert job["state"] == "cancelled"

    # Trả về Tất cả Fanpage (page_id = None)
    context.set_selected_page(None)
    assert view.table.rowCount() == 6

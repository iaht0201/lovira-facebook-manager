"""
Lovira-Facebook Manager
Màn hình Quản lý Lịch đăng & Xử lý Khôi phục (ScheduleWorkspaceView)
- Hiển thị danh sách lịch đăng local và remote theo giờ Việt Nam (Section 9.3)
- Lọc theo trạng thái: scheduled_local, published, missed, unknown, failed_retryable
- Thao tác: Hủy lịch, Tạm dừng, Đối chiếu trạng thái Unknown qua Graph API (AC-14)
"""

import json
import logging
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QComboBox,
    QMessageBox,
)
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.domain.timezone import format_vn_display
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ScheduleWorkspaceView(QWidget):
    """Màn hình Quản lý Danh sách Lịch đăng bài."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        queue_repo: PublishQueueRepository,
        recovery_manager: Optional[RecoveryManager] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.queue = queue_repo
        self.recovery = recovery_manager

        self._init_ui()
        self.reload_schedules()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Thanh công cụ lọc
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Trạng thái:"))
        self.cb_filter_state = QComboBox()
        self.cb_filter_state.addItems([
            "Tất cả",
            "Đã lên lịch máy (scheduled_local)",
            "Đang chờ (queued)",
            "Đã đăng thành công (published)",
            "Lỡ lịch hẹn (missed)",
            "Cần đối chiếu (unknown)",
            "Tạm dừng (paused)",
            "Lỗi có thể thử lại (failed_retryable)",
        ])
        self.cb_filter_state.currentTextChanged.connect(self.reload_schedules)
        toolbar.addWidget(self.cb_filter_state)

        toolbar.addStretch()

        self.btn_refresh = QPushButton("🔄 Tải lại")
        self.btn_refresh.clicked.connect(self.reload_schedules)
        toolbar.addWidget(self.btn_refresh)

        layout.addLayout(toolbar)

        # Bảng danh sách công việc
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Mã Job", "Page", "Nội dung", "Thời điểm đăng (Giờ VN)", "Trạng thái", "Lý do / Lỗi"
        ])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Nút thao tác
        action_row = QHBoxLayout()
        self.btn_reconcile = QPushButton("🔍 Đối chiếu với Facebook (AC-14)")
        self.btn_reconcile.clicked.connect(self._handle_reconcile)
        action_row.addWidget(self.btn_reconcile)

        self.btn_pause_toggle = QPushButton("⏸ Tạm dừng / Tiếp tục")
        self.btn_pause_toggle.clicked.connect(self._handle_pause_toggle)
        action_row.addWidget(self.btn_pause_toggle)

        action_row.addStretch()

        self.btn_cancel_job = QPushButton("✖ Hủy lịch đăng")
        self.btn_cancel_job.setObjectName("dangerButton")
        self.btn_cancel_job.clicked.connect(self._handle_cancel_job)
        action_row.addWidget(self.btn_cancel_job)

        layout.addLayout(action_row)

    def reload_schedules(self) -> None:
        state_text = self.cb_filter_state.currentText()
        state_filter = None
        if "(" in state_text and ")" in state_text:
            state_filter = state_text.split("(")[1].split(")")[0]

        query = """
            SELECT j.id, j.batch_id, j.page_id, p.name as page_name, j.content_snapshot,
                   j.state, j.scheduled_at_utc, j.blocked_reason, j.last_error_code
            FROM publish_jobs j
            LEFT JOIN pages p ON j.page_id = p.id
        """
        params: List[Any] = []
        if state_filter:
            query += " WHERE j.state = ?"
            params.append(state_filter)

        query += " ORDER BY j.scheduled_at_utc DESC LIMIT 100;"

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        self.table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            self.table.setItem(row_idx, 0, QTableWidgetItem(r["id"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(r["page_name"] or r["page_id"]))

            # Parse caption
            caption_str = ""
            if r["content_snapshot"]:
                try:
                    snap = json.loads(r["content_snapshot"])
                    caption_str = snap.get("final_caption", "")[:60]
                except Exception:
                    pass
            self.table.setItem(row_idx, 2, QTableWidgetItem(caption_str))

            # Format UTC to VN
            vn_time_str = r["scheduled_at_utc"]
            try:
                dt_utc = datetime.fromisoformat(r["scheduled_at_utc"].replace("Z", "+00:00"))
                vn_time_str = format_vn_display(dt_utc)
            except Exception:
                pass
            self.table.setItem(row_idx, 3, QTableWidgetItem(vn_time_str))

            # State
            self.table.setItem(row_idx, 4, QTableWidgetItem(r["state"].upper()))
            reason = r["blocked_reason"] or r["last_error_code"] or ""
            self.table.setItem(row_idx, 5, QTableWidgetItem(reason))

    def _get_selected_job_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self.table.item(row, 0).text()

    def _handle_reconcile(self) -> None:
        """AC-14: Đối chiếu trạng thái Unknown với Facebook."""
        job_id = self._get_selected_job_id()
        if not job_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn tác vụ cần đối chiếu trong bảng.")
            return

        if not self.recovery:
            QMessageBox.warning(self, "Thông báo", "Bộ điều phối đối chiếu chưa được khởi tạo.")
            return

        success, msg = self.recovery.reconcile_job(job_id)
        if success:
            QMessageBox.information(self, "Đối chiếu thành công (AC-14)", msg)
        else:
            QMessageBox.warning(self, "Chưa xác minh được", msg)
        self.reload_schedules()

    def _handle_pause_toggle(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn tác vụ.")
            return

        job = self.queue.get_job(job_id)
        if not job:
            return

        new_state = "scheduled_local" if job["state"] == "paused" else "paused"
        self.queue.update_job_outcome(job_id, state=new_state)
        self.reload_schedules()

    def _handle_cancel_job(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn tác vụ cần hủy.")
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận hủy lịch",
            "Bạn có chắc chắn muốn hủy lịch đăng này không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.queue.update_job_outcome(job_id, state="cancelled")
            self.reload_schedules()

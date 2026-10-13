"""
Lovira Workspace 2.0 — Schedule Workspace (schedule_workspace.py)
Màn hình Quản lý Lịch đăng & Điều phối tác vụ tự động 2.0 (Mockup 04_lich_dang.png):
- Phân biệt minh bạch Lịch trên máy (SCHEDULED_LOCAL) và Facebook đã nhận (SCHEDULED_REMOTE)
- Thống kê phân loại trạng thái: Chờ đăng, Thành công, Tạm dừng, Lỗi, Cần đối chiếu
- Bảng lịch đăng hiện đại tích hợp StatusChip, sao chép ID và EmptyState onboarding
- Thao tác an toàn: Đối chiếu trạng thái (AC-14 Reconcile), Tạm dừng/Tiếp tục, Thử lại, Hủy lịch
- Đồng bộ hóa theo GlobalPageContext và múi giờ Việt Nam (UTC+7)
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
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
    QLineEdit,
    QMessageBox,
    QFrame,
    QStackedLayout,
)
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.domain.timezone import format_vn_display
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.shell.global_context import GlobalPageContext

logger = logging.getLogger(__name__)


class ScheduleWorkspaceView(QWidget):
    """Màn hình Quản lý Danh sách Lịch đăng bài 2.0."""

    create_schedule_requested = Signal()

    def __init__(
        self,
        db_manager: DatabaseManager,
        queue_repo: PublishQueueRepository,
        recovery_manager: Optional[RecoveryManager] = None,
        page_context: Optional[GlobalPageContext] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.queue = queue_repo
        self.recovery = recovery_manager
        self.page_context = page_context
        self._current_page_filter: Optional[str] = None
        self._cached_rows: List[Dict[str, Any]] = []

        self._init_ui()

        if self.page_context:
            self.page_context.page_scope_changed.connect(self._on_page_scope_changed)

        self.reload_schedules()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # 1. Header Toolbar
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title_lbl = QLabel("QUẢN LÝ LỊCH ĐĂNG BÀI (REELS & POST)")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #F3F6FC;")

        self.lbl_subtitle = QLabel(
            "Theo dõi hàng đợi tự động theo giờ Việt Nam (UTC+7) — Phân biệt Lịch trên máy & Facebook đã nhận"
        )
        self.lbl_subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        header_box.addWidget(title_lbl)
        header_box.addWidget(self.lbl_subtitle)
        header_row.addLayout(header_box)

        header_row.addStretch()

        self.btn_refresh = QPushButton(" Làm mới")
        self.btn_refresh.setIcon(get_icon("refresh_cw", "#A9B8CF", 14))
        self.btn_refresh.clicked.connect(self.reload_schedules)
        header_row.addWidget(self.btn_refresh)

        btn_new_schedule = QPushButton(" + Lên lịch bài mới")
        btn_new_schedule.setObjectName("primaryButton")
        btn_new_schedule.setIcon(get_icon("plus", "#FFFFFF", 16))
        btn_new_schedule.clicked.connect(self.create_schedule_requested.emit)
        header_row.addWidget(btn_new_schedule)

        layout.addLayout(header_row)

        # 2. Khung thống kê nhanh 4 chỉ số (KPI Strip)
        kpi_frame = QFrame()
        kpi_frame.setObjectName("cardFrame")
        kpi_layout = QHBoxLayout(kpi_frame)
        kpi_layout.setContentsMargins(16, 12, 16, 12)
        kpi_layout.setSpacing(16)

        self.lbl_kpi_local = QLabel("📅 Lịch trên máy: 0")
        self.lbl_kpi_local.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        self.lbl_kpi_remote = QLabel("🌐 Facebook đã nhận: 0")
        self.lbl_kpi_remote.setStyleSheet("font-size: 12px; font-weight: 700; color: #38BDF8;")
        self.lbl_kpi_published = QLabel("✅ Đã đăng thành công: 0")
        self.lbl_kpi_published.setStyleSheet("font-size: 12px; font-weight: 700; color: #24C89A;")
        self.lbl_kpi_issues = QLabel("⚠️ Sự cố / Cần xử lý: 0")
        self.lbl_kpi_issues.setStyleSheet("font-size: 12px; font-weight: 700; color: #F0707B;")

        kpi_layout.addWidget(self.lbl_kpi_local)
        kpi_layout.addWidget(self.lbl_kpi_remote)
        kpi_layout.addWidget(self.lbl_kpi_published)
        kpi_layout.addWidget(self.lbl_kpi_issues)
        kpi_layout.addStretch()

        layout.addWidget(kpi_frame)

        # 3. Thanh công cụ lọc & tìm kiếm nhanh
        filter_frame = QFrame()
        filter_frame.setObjectName("cardFrame")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)

        filter_layout.addWidget(QLabel("Trạng thái:"))
        self.cb_filter_state = QComboBox()
        self.cb_filter_state.addItems([
            "Tất cả",
            "Đã lên lịch máy (scheduled_local)",
            "Facebook đã nhận (scheduled_remote)",
            "Đang chờ (queued)",
            "Đã đăng thành công (published)",
            "Lỡ lịch hẹn (missed)",
            "Cần đối chiếu (unknown)",
            "Tạm dừng (paused)",
            "Lỗi có thể thử lại (failed_retryable)",
        ])
        self.cb_filter_state.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.cb_filter_state)

        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("🔍 Tìm theo Mã Job hoặc nội dung caption...")
        self.search_filter.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_filter, stretch=1)

        layout.addWidget(filter_frame)

        # 4. Vùng hiển thị: QStackedLayout giữa Bảng danh sách và EmptyState
        self.content_stack = QStackedLayout()

        # View 1: Bảng danh sách công việc
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(10)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Mã Job", "Page", "Nội dung", "Thời điểm đăng (Giờ VN)", "Trạng thái", "Lý do / Lỗi"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(42)
        table_layout.addWidget(self.table)

        # Thanh nút hành động
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.btn_reconcile = QPushButton("🔍 Đối chiếu với Facebook (AC-14)")
        self.btn_reconcile.clicked.connect(self._handle_reconcile)
        action_row.addWidget(self.btn_reconcile)

        self.btn_pause_toggle = QPushButton("⏸ Tạm dừng / Tiếp tục")
        self.btn_pause_toggle.clicked.connect(self._handle_pause_toggle)
        action_row.addWidget(self.btn_pause_toggle)

        self.btn_retry_job = QPushButton("🔄 Thử lại ngay")
        self.btn_retry_job.clicked.connect(self._handle_retry_job)
        action_row.addWidget(self.btn_retry_job)

        action_row.addStretch()

        self.btn_cancel_job = QPushButton("✖ Hủy lịch đăng")
        self.btn_cancel_job.setObjectName("dangerButton")
        self.btn_cancel_job.clicked.connect(self._handle_cancel_job)
        action_row.addWidget(self.btn_cancel_job)

        table_layout.addLayout(action_row)
        self.content_stack.addWidget(table_container)

        # View 2: EmptyState Container
        self.empty_container = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_container)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_state = EmptyState.no_schedules(on_create=self.create_schedule_requested.emit)
        self.empty_layout.addWidget(self.empty_state)
        self.content_stack.addWidget(self.empty_container)

        layout.addLayout(self.content_stack, stretch=1)

    def _on_page_scope_changed(self, page_id: Optional[str]) -> None:
        """Lọc danh sách khi người dùng đổi Fanpage từ Header."""
        self._current_page_filter = page_id
        self.reload_schedules()

    def reload_schedules(self) -> None:
        """Đọc danh sách tác vụ từ SQLite và lưu vào cache."""
        query = """
            SELECT j.id, j.batch_id, j.page_id, p.name as page_name, j.content_snapshot,
                   j.state, j.scheduled_at_utc, j.blocked_reason, j.last_error_code
            FROM publish_jobs j
            LEFT JOIN pages p ON j.page_id = p.id
        """
        params: List[Any] = []
        if self._current_page_filter:
            query += " WHERE j.page_id = ?"
            params.append(self._current_page_filter)

        query += " ORDER BY j.scheduled_at_utc DESC LIMIT 200;"

        with self.db.connection_scope() as conn:
            cursor = conn.execute(query, tuple(params))
            self._cached_rows = [dict(r) for r in cursor.fetchall()]

        # Cập nhật số liệu trên KPI Strip
        local_cnt = sum(1 for r in self._cached_rows if r["state"] == "scheduled_local")
        remote_cnt = sum(1 for r in self._cached_rows if r["state"] == "scheduled_remote")
        pub_cnt = sum(1 for r in self._cached_rows if r["state"] == "published")
        issues_cnt = sum(1 for r in self._cached_rows if r["state"] in ("failed_final", "missed", "unknown"))

        self.lbl_kpi_local.setText(f"📅 Lịch trên máy: {local_cnt}")
        self.lbl_kpi_remote.setText(f"🌐 Facebook đã nhận: {remote_cnt}")
        self.lbl_kpi_published.setText(f"✅ Đã đăng thành công: {pub_cnt}")
        self.lbl_kpi_issues.setText(f"⚠️ Sự cố / Cần xử lý: {issues_cnt}")

        self._apply_filters()

    def _apply_filters(self) -> None:
        """Lọc và cập nhật hiển thị bảng theo trạng thái và từ khóa."""
        state_text = self.cb_filter_state.currentText()
        state_filter = None
        if "(" in state_text and ")" in state_text:
            state_filter = state_text.split("(")[1].split(")")[0]

        search_query = self.search_filter.text().strip().lower()

        filtered_rows = []
        for r in self._cached_rows:
            st = r.get("state", "")
            if state_filter and st != state_filter:
                continue

            caption_str = ""
            if r.get("content_snapshot"):
                try:
                    snap = json.loads(r["content_snapshot"])
                    caption_str = snap.get("final_caption", "").lower()
                except Exception:
                    pass

            job_id = r.get("id", "").lower()
            page_name = (r.get("page_name") or r.get("page_id") or "").lower()

            if search_query:
                if (search_query not in job_id) and (search_query not in caption_str) and (search_query not in page_name):
                    continue

            filtered_rows.append(r)

        if not filtered_rows:
            self.content_stack.setCurrentIndex(1)
            return

        self.content_stack.setCurrentIndex(0)
        self.table.setRowCount(len(filtered_rows))

        for row_idx, r in enumerate(filtered_rows):
            # Cột 0: Mã Job
            self.table.setItem(row_idx, 0, QTableWidgetItem(r["id"]))

            # Cột 1: Tên Page
            self.table.setItem(row_idx, 1, QTableWidgetItem(r.get("page_name") or r.get("page_id", "")))

            # Cột 2: Nội dung Caption
            caption_str = ""
            if r.get("content_snapshot"):
                try:
                    snap = json.loads(r["content_snapshot"])
                    caption_str = snap.get("final_caption", "")[:65]
                except Exception:
                    pass
            self.table.setItem(row_idx, 2, QTableWidgetItem(caption_str or "(Reels Video)"))

            # Cột 3: Giờ đăng VN
            vn_time_str = r.get("scheduled_at_utc", "")
            if vn_time_str:
                try:
                    dt_utc = datetime.fromisoformat(vn_time_str.replace("Z", "+00:00"))
                    vn_time_str = format_vn_display(dt_utc)
                except Exception:
                    pass
            self.table.setItem(row_idx, 3, QTableWidgetItem(vn_time_str))

            # Cột 4: StatusChip hiện đại + QTableWidgetItem tương thích
            st = r.get("state", "unknown")
            self.table.setItem(row_idx, 4, QTableWidgetItem(st.upper()))
            chip = StatusChip(st)
            self.table.setCellWidget(row_idx, 4, chip)

            # Cột 5: Lý do / Lỗi
            reason = r.get("blocked_reason") or r.get("last_error_code") or ""
            self.table.setItem(row_idx, 5, QTableWidgetItem(reason))

    def _get_selected_job_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, 0)
        return item.text() if item else None

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
        """Tạm dừng hoặc tiếp tục lịch hẹn giờ trên máy."""
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

    def _handle_retry_job(self) -> None:
        """Thử lại an toàn cho tác vụ lỗi."""
        job_id = self._get_selected_job_id()
        if not job_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn tác vụ cần thử lại.")
            return

        job = self.queue.get_job(job_id)
        if not job:
            return

        if job["state"] not in ("failed_retryable", "failed_final", "missed"):
            QMessageBox.information(self, "Thông báo", f"Tác vụ đang ở trạng thái '{job['state']}', không cần thử lại.")
            return

        self.queue.update_job_outcome(job_id, state="scheduled_local")
        QMessageBox.information(self, "Đã đặt lại lịch", f"Tác vụ {job_id[:12]} đã được chuyển về hàng đợi để thử lại.")
        self.reload_schedules()

    def _handle_cancel_job(self) -> None:
        """Hủy lịch đăng bài."""
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

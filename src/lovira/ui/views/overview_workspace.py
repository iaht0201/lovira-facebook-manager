"""
Lovira Workspace 2.0 — Overview Workspace (Dashboard 2.0)
Màn hình Tổng quan Dashboard chuyên nghiệp (Mockup 01_tong_quan.png, A-09):
- Header chào ngày mới & nút Soạn bài nổi bật
- 4 Thẻ Metric thông minh hỗ trợ click-through điều hướng
- Actionable Alert Banner thông báo token/job lỗi thời gian thực
- Schedule Timeline 7 ngày trực quan hóa mật độ bài đăng
- Bảng công việc gần đây với StatusChip và EmptyState onboarding
- Đồng bộ với GlobalPageContext khi người dùng đổi Fanpage
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QFrame,
    QStackedLayout,
)

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.domain.timezone import format_vn_display, vn_now
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.feedback import FeedbackBanner
from src.lovira.ui.widgets.schedule_timeline import ScheduleTimelineWidget


class MetricCard(QFrame):
    """Thẻ thông số thống kê tương tác cao (Click-through)."""

    clicked = Signal(str)  # Phát route đích khi click

    def __init__(
        self,
        icon: str,
        title: str,
        value: str,
        subtext: str,
        target_route: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.target_route = target_route
        self.setObjectName("cardFrame")
        self.setCursor(Qt.CursorShape.PointingHandCursor if target_route else Qt.CursorShape.ArrowCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        # 1. Hàng trên: Icon + Tiêu đề
        top_row = QHBoxLayout()
        self.lbl_icon = QLabel(icon)
        self.lbl_icon.setStyleSheet("font-size: 22px;")
        top_row.addWidget(self.lbl_icon)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        if self.target_route:
            lbl_arrow = QLabel()
            lbl_arrow.setPixmap(get_icon("chevron_right", "#64748B", 14).pixmap(14, 14))
            top_row.addWidget(lbl_arrow)

        layout.addLayout(top_row)

        # 2. Giá trị số nổi bật
        self.lbl_val = QLabel(value)
        self.lbl_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #F8FAFC; margin-top: 4px;")
        layout.addWidget(self.lbl_val)

        # 3. Phụ đề mô tả
        self.lbl_sub = QLabel(subtext)
        self.lbl_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(self.lbl_sub)

    def update_data(self, value: str, subtext: str) -> None:
        self.lbl_val.setText(value)
        self.lbl_sub.setText(subtext)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.target_route:
            self.clicked.emit(self.target_route)
        super().mousePressEvent(event)


class OverviewWorkspaceView(QWidget):
    """Màn hình Tổng quan Dashboard 2.0."""

    quick_post_requested = Signal()
    download_video_requested = Signal()
    add_page_requested = Signal()
    bulk_import_requested = Signal()
    navigate_requested = Signal(str)

    def __init__(
        self,
        db_manager: DatabaseManager,
        page_repo: PageRepository,
        media_repo: MediaRepository,
        queue_repo: PublishQueueRepository,
        license_client: LicenseClient,
        policy_manager: AccessPolicyManager,
        page_context: Optional[GlobalPageContext] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.page_repo = page_repo
        self.media_repo = media_repo
        self.queue_repo = queue_repo
        self.license_client = license_client
        self.policy_manager = policy_manager
        self.page_context = page_context
        self._current_page_filter: Optional[str] = None

        self._init_ui()

        if self.page_context:
            self.page_context.page_changed.connect(self._on_page_scope_changed)

        self.reload_dashboard_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # 1. Header chào ngày mới và Thao tác nhanh
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        welcome_box = QVBoxLayout()
        welcome_box.setSpacing(4)

        now_vn = vn_now()
        greeting = "Chào buổi sáng" if now_vn.hour < 12 else ("Chào buổi chiều" if now_vn.hour < 18 else "Chào buổi tối")
        self.lbl_greeting = QLabel(f"{greeting}, Quản trị viên")
        self.lbl_greeting.setStyleSheet("font-size: 20px; font-weight: 800; color: #F3F6FC;")

        self.lbl_subtitle = QLabel(
            "Trung tâm chỉ huy phát hành nội dung Reels & Fanpage theo múi giờ Việt Nam (UTC+7)"
        )
        self.lbl_subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        welcome_box.addWidget(self.lbl_greeting)
        welcome_box.addWidget(self.lbl_subtitle)

        header_row.addLayout(welcome_box)
        header_row.addStretch()

        # Nút Làm mới
        btn_refresh = QPushButton(" Làm mới")
        btn_refresh.setIcon(get_icon("refresh_cw", "#A9B8CF", 14))
        btn_refresh.clicked.connect(self.reload_dashboard_data)
        header_row.addWidget(btn_refresh)

        # Nút Soạn bài nổi bật
        btn_compose = QPushButton(" + Soạn bài ngay")
        btn_compose.setObjectName("primaryButton")
        btn_compose.setIcon(get_icon("plus", "#FFFFFF", 16))
        btn_compose.clicked.connect(self.quick_post_requested.emit)
        header_row.addWidget(btn_compose)

        layout.addLayout(header_row)

        # 2. Actionable Alert Banner (Ẩn/Hiện động khi có cảnh báo)
        self.alert_banner = FeedbackBanner(level="warning", message="", parent=self)
        self.alert_banner.setVisible(False)
        layout.addWidget(self.alert_banner)

        # 3. Bốn Metric Cards hỗ trợ Click-through
        cards_layout = QGridLayout()
        cards_layout.setSpacing(14)

        self.card_pages = MetricCard("📑", "FANPAGE ĐANG KẾT NỐI", "0", "Chưa có Fanpage nào", target_route="pages")
        self.card_schedules = MetricCard("📅", "LỊCH ĐĂNG HÔM NAY", "0", "Hôm nay: 0 bài", target_route="schedule")
        self.card_media = MetricCard("🎬", "KHO VIDEO MEDIA", "0", "0 MB lưu trữ", target_route="media")
        self.card_status = MetricCard("🛡️", "TRẠNG THÁI BẢN QUYỀN", "Kiểm tra...", "Lease: 180s", target_route="settings")

        self.card_pages.clicked.connect(self.navigate_requested.emit)
        self.card_schedules.clicked.connect(self.navigate_requested.emit)
        self.card_media.clicked.connect(self.navigate_requested.emit)
        self.card_status.clicked.connect(self.navigate_requested.emit)

        cards_layout.addWidget(self.card_pages, 0, 0)
        cards_layout.addWidget(self.card_schedules, 0, 1)
        cards_layout.addWidget(self.card_media, 0, 2)
        cards_layout.addWidget(self.card_status, 0, 3)
        layout.addLayout(cards_layout)

        # 4. Schedule Timeline 7 ngày
        self.timeline = ScheduleTimelineWidget(self)
        self.timeline.day_selected.connect(lambda dt: self.navigate_requested.emit("schedule"))
        layout.addWidget(self.timeline)

        # 5. Khung Công việc gần đây (Recent Jobs)
        recent_frame = QFrame()
        recent_frame.setObjectName("cardFrame")
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(18, 16, 18, 16)
        recent_layout.setSpacing(12)

        recent_header = QHBoxLayout()
        lbl_recent = QLabel("CÁC TÁC VỤ ĐĂNG BÀI GẦN ĐÂY")
        lbl_recent.setStyleSheet("font-size: 13px; font-weight: 700; color: #818CF8; letter-spacing: 0.5px;")
        recent_header.addWidget(lbl_recent)
        recent_header.addStretch()

        btn_view_all = QPushButton("Xem tất cả lịch đăng →")
        btn_view_all.setStyleSheet("background: transparent; border: none; color: #6258E8; font-weight: 600; font-size: 12px;")
        btn_view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view_all.clicked.connect(lambda: self.navigate_requested.emit("schedule"))
        recent_header.addWidget(btn_view_all)
        recent_layout.addLayout(recent_header)

        # Container chuyển đổi giữa Bảng và EmptyState
        self.content_stack = QStackedLayout()

        # View 1: Bảng Jobs
        self.table_recent = QTableWidget()
        self.table_recent.setColumnCount(5)
        self.table_recent.setHorizontalHeaderLabels([
            "Mã Tác vụ", "Page Đích", "Nội dung tóm tắt", "Giờ Đăng (Giờ VN)", "Trạng thái"
        ])
        self.table_recent.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_recent.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_recent.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_recent.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_recent.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_recent.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_recent.verticalHeader().setDefaultSectionSize(40)
        self.content_stack.addWidget(self.table_recent)

        # View 2: Empty State Container
        self.empty_container = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_container)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.content_stack.addWidget(self.empty_container)

        recent_layout.addLayout(self.content_stack)
        layout.addWidget(recent_frame, stretch=1)

    def _on_page_scope_changed(self, page_id: Optional[str]) -> None:
        """Lọc dữ liệu Dashboard theo Page được chọn trên thanh tiêu đề."""
        self._current_page_filter = page_id
        self.reload_dashboard_data()

    def reload_dashboard_data(self) -> None:
        """Nạp dữ liệu thời gian thực từ Database SQLite."""
        # 1. Thống kê Page
        all_pages = self.page_repo.list_pages()
        ready_pages = [p for p in all_pages if p.get("status") == "ready"]
        problem_pages = [p for p in all_pages if p.get("status") in ("token_expired", "insufficient_permissions")]

        if self._current_page_filter:
            target_pages = [p for p in all_pages if p["id"] == self._current_page_filter]
        else:
            target_pages = all_pages

        self.card_pages.update_data(
            value=str(len(target_pages)),
            subtext=f"{len(ready_pages)} Fanpage sẵn sàng hoạt động",
        )

        # 2. Thống kê Lịch đăng & Bài hôm nay
        all_jobs = self.queue_repo.list_jobs(limit=200)

        # Lọc theo Page nếu có filter
        if self._current_page_filter:
            scoped_jobs = [j for j in all_jobs if j.get("page_id") == self._current_page_filter]
        else:
            scoped_jobs = all_jobs

        now_vn = vn_now()
        today_date = now_vn.date()

        # Đếm số bài đăng hôm nay theo giờ VN
        today_jobs_count = 0
        from src.lovira.domain.timezone import utc_iso_to_vn_datetime
        for j in scoped_jobs:
            sched_str = j.get("scheduled_at_utc")
            if sched_str:
                try:
                    dt = utc_iso_to_vn_datetime(sched_str)
                    if dt.date() == today_date:
                        today_jobs_count += 1
                except Exception:
                    pass

        pending_jobs = [j for j in scoped_jobs if j["state"] in ("scheduled_local", "queued", "uploading", "processing")]
        self.card_schedules.update_data(
            value=str(len(pending_jobs)),
            subtext=f"Hôm nay: {today_jobs_count} bài (Tổng {len(scoped_jobs)} tác vụ)",
        )

        # 3. Thống kê Media
        assets = self.media_repo.list_media_assets(limit=500)
        total_bytes = sum(a.get("size_bytes", 0) or 0 for a in assets)
        size_mb = total_bytes / (1024 * 1024)
        self.card_media.update_data(
            value=str(len(assets)),
            subtext=f"{size_mb:.1f} MB lưu trữ trên máy",
        )

        # 4. Thống kê License
        if not self.policy_manager.config.license_required:
            self.card_status.update_data("Miễn phí", "Chế độ mở tự do toàn hệ thống")
        elif self.license_client.is_active:
            sess_id = getattr(self.license_client.current_session, "session_id", "active")
            self.card_status.update_data("Đã kích hoạt", f"Session: {sess_id[:8]}...")
        else:
            self.card_status.update_data("Chưa có Key", "Vui lòng nhập License Key")

        # 5. Cập nhật Alert Banner
        failed_jobs = [j for j in scoped_jobs if j["state"] in ("failed_final", "missed")]
        if problem_pages:
            self.alert_banner.setVisible(True)
            self.alert_banner.level = "warning"
            self.alert_banner.set_message(
                f"Phát hiện {len(problem_pages)} Fanpage cần cấp lại quyền hoặc token đã hết hạn."
            )
        elif failed_jobs:
            self.alert_banner.setVisible(True)
            self.alert_banner.level = "danger"
            self.alert_banner.set_message(
                f"Có {len(failed_jobs)} tác vụ đăng bài gặp sự cố hoặc lỡ lịch. Vui lòng kiểm tra."
            )
        else:
            self.alert_banner.setVisible(False)

        # 6. Cập nhật Timeline 7 ngày
        self.timeline.update_with_jobs(scoped_jobs)

        # 7. Cập nhật Danh sách tác vụ gần đây & Trạng thái rỗng
        recent_jobs = scoped_jobs[:10]

        if not recent_jobs:
            # Dọn dẹp empty layout
            while self.empty_layout.count():
                item = self.empty_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            if len(all_pages) == 0:
                empty = EmptyState.no_pages(on_add=self.add_page_requested.emit)
            else:
                empty = EmptyState.no_schedules(on_create=self.quick_post_requested.emit)

            self.empty_layout.addWidget(empty)
            self.content_stack.setCurrentIndex(1)
        else:
            self.content_stack.setCurrentIndex(0)
            self.table_recent.setRowCount(len(recent_jobs))

            state_labels = {
                "scheduled_local": "📅 Đã lưu lịch",
                "queued": "⏳ Đang chờ",
                "uploading": "📤 Đang upload",
                "processing": "⚙️ FB đang xử lý",
                "published": "✅ Đã đăng thành công",
                "missed": "⚠️ Lỡ lịch",
                "paused": "⏸️ Tạm dừng",
                "failed_retryable": "🔄 Chờ thử lại",
                "failed_final": "❌ Lỗi",
                "unknown": "❓ Cần đối chiếu",
            }

            for row, job in enumerate(recent_jobs):
                # Cột 0: Mã tác vụ
                self.table_recent.setItem(row, 0, QTableWidgetItem(job["id"][:12]))

                # Cột 1: Page Đích
                self.table_recent.setItem(row, 1, QTableWidgetItem(job.get("page_name") or job.get("page_id", "")))

                # Cột 2: Nội dung
                caption = job.get("snapshot_caption", "")
                short_caption = (caption[:45] + "...") if len(caption) > 45 else caption
                self.table_recent.setItem(row, 2, QTableWidgetItem(short_caption or "(Video Reels)"))

                # Cột 3: Giờ đăng VN
                sched_utc = job.get("scheduled_at_utc")
                if sched_utc:
                    vn_str = format_vn_display(sched_utc)
                else:
                    vn_str = "Đăng ngay"
                self.table_recent.setItem(row, 3, QTableWidgetItem(vn_str))

                # Cột 4: StatusChip hiện đại kèm QTableWidgetItem tương thích
                st = job.get("state", "unknown")
                self.table_recent.setItem(row, 4, QTableWidgetItem(state_labels.get(st, st)))
                chip = StatusChip(st)
                self.table_recent.setCellWidget(row, 4, chip)

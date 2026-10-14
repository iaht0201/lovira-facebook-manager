
"""
Lovira Workspace 2.0 - Compact Overview Dashboard
Native PySide6 | Dashboard nhỏ gọn, hiện đại.

- Metric cards cao 105px
- Timeline tối đa 140px
- Bảng công việc compact
- Responsive 4 / 2 / 1 cột
- Global Page Filter
- StatusChip, EmptyState, FeedbackBanner
- Giữ nguyên signals và API hiện tại
"""

import json
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, QEvent, QTimer
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
    QScrollArea,
    QSizePolicy,
    QAbstractItemView,
)

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.queue_repository import PublishQueueRepository

from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.domain.timezone import vn_now, utc_iso_to_vn_datetime

from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.global_context import GlobalPageContext

from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.feedback import FeedbackBanner
from src.lovira.ui.widgets.schedule_timeline import ScheduleTimelineWidget


# ==========================================================
# COMPACT DASHBOARD DESIGN SYSTEM
# ==========================================================

DASHBOARD_QSS = """
QWidget#overviewWorkspace {
    background-color: #0D1627;
}

QWidget#overviewCanvas {
    background: transparent;
}

QScrollArea#overviewScroll {
    background: transparent;
    border: none;
}

QScrollArea#overviewScroll > QWidget > QWidget {
    background: transparent;
}

/* Header */
QLabel#overviewGreeting {
    background: transparent;
    color: #F3F6FC;
    font-size: 17px;
    font-weight: 700;
    padding: 2px 0px;
}

QLabel#overviewSubtitle {
    background: transparent;
    color: #9AAAC1;
    font-size: 11px;
}

/* Actions */
QPushButton#overviewRefresh,
QPushButton#overviewCompose {
    min-height: 34px;
    max-height: 34px;
    border-radius: 9px;
    padding: 0 13px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#overviewRefresh {
    background: #202F47;
    color: #DCE6F5;
    border: 1px solid #354763;
}

QPushButton#overviewRefresh:hover {
    background: #2B3C56;
}

QPushButton#overviewCompose {
    background: #6257E8;
    color: white;
    border: 1px solid #746AF0;
}

QPushButton#overviewCompose:hover {
    background: #756AF0;
}

/* Metric cards */
QFrame#metricCard {
    background: #1A2940;
    border: 1px solid #2D405D;
    border-radius: 12px;
}

QFrame#metricCard:hover {
    border-color: #6257E8;
    background: #1E304C;
}

QLabel#metricIcon,
QLabel#metricTitle,
QLabel#metricValue,
QLabel#metricSubtitle,
QLabel#metricArrow {
    background: transparent;
    border: none;
}

QLabel#metricIcon {
    font-size: 17px;
}

QLabel#metricTitle {
    color: #AAB9CE;
    font-size: 11px;
    font-weight: 600;
}

QLabel#metricValue {
    color: #F6F8FF;
    font-size: 23px;
    font-weight: 700;
}

QLabel#metricSubtitle {
    color: #8B9CB6;
    font-size: 10px;
}

/* Recent jobs */
QFrame#overviewRecentCard {
    background: #17243A;
    border: 1px solid #2B3C56;
    border-radius: 12px;
}

QLabel#overviewRecentTitle {
    background: transparent;
    color: #E6EBFF;
    font-weight: 700;
    font-size: 12px;
}

QPushButton#overviewViewAll {
    background: transparent;
    color: #ABA5FF;
    border: 0;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 7px;
}

QPushButton#overviewViewAll:hover {
    color: white;
}

/* Table */
QTableWidget#overviewJobs {
    background: #17243A;
    alternate-background-color: #1B2A41;
    color: #E5EDFA;
    border: 0;
    gridline-color: #2C3D57;
    font-size: 11px;
    selection-background-color: #343265;
}

QTableWidget#overviewJobs QTableCornerButton::section {
    background: #111D30;
    border: none;
}

QTableWidget#overviewJobs QHeaderView::section {
    background: #111D30;
    color: #AEBED4;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 8px;
    border: 0;
    border-bottom: 1px solid #2C3D57;
}
"""


# ==========================================================
# COMPACT METRIC CARD
# ==========================================================

class MetricCard(QFrame):
    """Thẻ thống kê nhỏ gọn, hỗ trợ điều hướng."""

    clicked = Signal(str)

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
        self.setObjectName("metricCard")
        self.setFixedHeight(105)
        self.setMinimumWidth(0)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        if target_route:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        content = QVBoxLayout(self)
        content.setContentsMargins(13, 10, 13, 10)
        content.setSpacing(4)

        # Icon + title
        head = QHBoxLayout()
        head.setSpacing(7)

        self.lbl_icon = QLabel(icon)
        self.lbl_icon.setObjectName("metricIcon")
        head.addWidget(self.lbl_icon)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("metricTitle")
        head.addWidget(self.lbl_title, 1)

        if target_route:
            arrow = QLabel()
            arrow.setObjectName("metricArrow")
            arrow.setPixmap(
                get_icon(
                    "chevron_right",
                    "#8B9CB6",
                    13
                ).pixmap(13, 13)
            )
            head.addWidget(arrow)

        content.addLayout(head)

        # Value
        self.lbl_val = QLabel(value)
        self.lbl_val.setObjectName("metricValue")
        content.addWidget(self.lbl_val)

        # Subtitle
        self.lbl_sub = QLabel(subtext)
        self.lbl_sub.setObjectName("metricSubtitle")
        self.lbl_sub.setToolTip(subtext)
        content.addWidget(self.lbl_sub)

        # Click toàn bộ card, không chỉ khoảng trống
        for label in (
            self.lbl_icon,
            self.lbl_title,
            self.lbl_val,
            self.lbl_sub,
        ):
            label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )
            label.setMinimumWidth(0)

        if target_route:
            arrow.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                True,
            )

    def update_data(self, value: str, subtext: str) -> None:
        self.lbl_val.setText(value)
        self.lbl_sub.setText(subtext)
        self.lbl_sub.setToolTip(subtext)

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.target_route
        ):
            self.clicked.emit(self.target_route)

        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        keys = (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        )

        if self.target_route and event.key() in keys:
            self.clicked.emit(self.target_route)
            event.accept()
            return

        super().keyPressEvent(event)


# ==========================================================
# OVERVIEW DASHBOARD
# ==========================================================

class OverviewWorkspaceView(QWidget):
    """Lovira Dashboard 2.0 - Compact UI."""

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
        self._empty_kind: Optional[str] = None
        self._card_columns = 0

        self.setObjectName("overviewWorkspace")
        self.setStyleSheet(DASHBOARD_QSS)

        self._init_ui()

        if self.page_context:
            self.page_context.page_changed.connect(
                self._on_page_scope_changed
            )

        self.reload_dashboard_data()

    # ======================================================
    # BUILD UI
    # ======================================================

    def _init_ui(self) -> None:

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Scroll only when necessary
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("overviewScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        root.addWidget(self.scroll_area)

        canvas = QWidget()
        canvas.setObjectName("overviewCanvas")

        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.scroll_area.setWidget(canvas)
        if self.scroll_area.viewport():
            self.scroll_area.viewport().installEventFilter(self)

        # ----------------------------------------------
        # 1. COMPACT HEADER
        # ----------------------------------------------

        header = QHBoxLayout()
        header.setSpacing(8)

        heading = QVBoxLayout()
        heading.setSpacing(2)

        self.lbl_greeting = QLabel()
        self.lbl_greeting.setObjectName("overviewGreeting")

        self.lbl_subtitle = QLabel(
            "Quản lý Fanpage, Reels và lịch đăng - Giờ Việt Nam (UTC+7)"
        )
        self.lbl_subtitle.setObjectName("overviewSubtitle")

        heading.addWidget(self.lbl_greeting)
        heading.addWidget(self.lbl_subtitle)

        header.addLayout(heading, 1)

        self.btn_refresh = QPushButton("Làm mới")
        self.btn_refresh.setObjectName("overviewRefresh")
        self.btn_refresh.setIcon(
            get_icon("refresh_cw", "#DCE6F5", 14)
        )
        self.btn_refresh.clicked.connect(
            self.reload_dashboard_data
        )
        header.addWidget(self.btn_refresh)

        self.btn_compose = QPushButton("Soạn bài")
        self.btn_compose.setObjectName("overviewCompose")
        self.btn_compose.setIcon(
            get_icon("plus", "#FFFFFF", 14)
        )
        self.btn_compose.clicked.connect(
            self.quick_post_requested.emit
        )
        header.addWidget(self.btn_compose)

        layout.addLayout(header)

        # ----------------------------------------------
        # 2. ALERT BANNER
        # ----------------------------------------------

        self.alert_banner = FeedbackBanner(
            level="warning",
            message="",
            parent=self,
        )
        self.alert_banner.hide()
        layout.addWidget(self.alert_banner)

        # ----------------------------------------------
        # 3. FOUR METRIC CARDS
        # ----------------------------------------------

        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(10)
        self.cards_layout.setVerticalSpacing(10)

        self.card_pages = MetricCard(
            "▣",
            "Fanpage kết nối",
            "0",
            "Chưa có Fanpage",
            "pages",
        )

        self.card_schedules = MetricCard(
            "▦",
            "Bài đăng hôm nay",
            "0",
            "Chưa có lịch đăng",
            "schedule",
        )

        self.card_media = MetricCard(
            "▶",
            "Thư viện media",
            "0",
            "0 MB lưu trữ",
            "media",
        )

        self.card_status = MetricCard(
            "◆",
            "Bản quyền",
            "Đang kiểm tra",
            "Trạng thái License",
            "settings",
        )

        self._cards = [
            self.card_pages,
            self.card_schedules,
            self.card_media,
            self.card_status,
        ]

        for card in self._cards:
            card.clicked.connect(
                self.navigate_requested.emit
            )

        layout.addLayout(self.cards_layout)
        self._reflow_cards(force=True)

        # ----------------------------------------------
        # 4. COMPACT SEVEN-DAY TIMELINE
        # ----------------------------------------------

        self.timeline = ScheduleTimelineWidget(self)

        self.timeline.setMinimumHeight(112)
        self.timeline.setMaximumHeight(140)

        self.timeline.day_selected.connect(
            lambda _day: self.navigate_requested.emit("schedule")
        )

        layout.addWidget(self.timeline)

        # ----------------------------------------------
        # 5. RECENT TASKS
        # ----------------------------------------------

        recent = QFrame()
        recent.setObjectName("overviewRecentCard")
        recent.setMinimumHeight(205)

        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(12, 10, 12, 10)
        recent_layout.setSpacing(8)

        recent_head = QHBoxLayout()

        recent_title = QLabel(
            "Công việc đăng bài gần đây"
        )
        recent_title.setObjectName("overviewRecentTitle")

        recent_head.addWidget(recent_title)
        recent_head.addStretch()

        btn_all = QPushButton("Xem tất cả  →")
        btn_all.setObjectName("overviewViewAll")
        btn_all.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        btn_all.clicked.connect(
            lambda: self.navigate_requested.emit("schedule")
        )
        recent_head.addWidget(btn_all)

        recent_layout.addLayout(recent_head)

        # Table / EmptyState
        self.content_stack = QStackedLayout()

        self.table_recent = QTableWidget(0, 5)
        self.table_recent.setObjectName("overviewJobs")

        self.table_recent.setHorizontalHeaderLabels([
            "Mã tác vụ",
            "Fanpage",
            "Nội dung",
            "Giờ đăng (VN)",
            "Trạng thái",
        ])

        self.table_recent.setAlternatingRowColors(True)
        self.table_recent.verticalHeader().hide()
        self.table_recent.verticalHeader().setDefaultSectionSize(36)
        self.table_recent.horizontalHeader().setFixedHeight(32)

        table_header = self.table_recent.horizontalHeader()

        table_header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table_recent.setColumnWidth(0, 105)

        table_header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        self.table_recent.setColumnWidth(1, 150)

        table_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

        table_header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.Fixed
        )
        self.table_recent.setColumnWidth(3, 142)

        table_header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.table_recent.setColumnWidth(4, 142)

        self.table_recent.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_recent.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_recent.setShowGrid(False)

        self.content_stack.addWidget(self.table_recent)

        self.empty_container = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_container)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.content_stack.addWidget(self.empty_container)

        recent_layout.addLayout(self.content_stack, 1)

        layout.addWidget(recent, 1)

    # ======================================================
    # RESPONSIVE METRIC GRID
    # ======================================================

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "scroll_area") and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(0)
        # Kích hoạt reflow ngay sau khi widget được render trên màn hình
        QTimer.singleShot(0, lambda: self._reflow_cards(force=True))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_cards"):
            self._reflow_cards()

    def eventFilter(self, watched, event):
        if (
            hasattr(self, "scroll_area")
            and watched == self.scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._reflow_cards()
        return super().eventFilter(watched, event)

    def _reflow_cards(self, force: bool = False) -> None:
        width = 0
        if hasattr(self, "scroll_area") and self.scroll_area.viewport():
            width = self.scroll_area.viewport().width()
        if width <= 0:
            width = self.width()

        # Khi mới khởi tạo trong bộ nhớ hoặc chưa layout thực tế,
        # viewport().width() thường <= 100. Cần ước tính từ cửa sổ cha hoặc fallback hợp lý.
        if width < 300:
            win = self.window()
            if win and win.width() > 300:
                width = win.width() - 250
            else:
                width = 800

        if width >= 1050:
            columns = 4
        elif width >= 570:
            columns = 2
        else:
            columns = 1

        if columns == self._card_columns and not force:
            return

        self._card_columns = columns

        for card in self._cards:
            self.cards_layout.removeWidget(card)

        for i, card in enumerate(self._cards):
            self.cards_layout.addWidget(
                card,
                i // columns,
                i % columns,
            )

    # ======================================================
    # PAGE CONTEXT
    # ======================================================

    def _on_page_scope_changed(
        self,
        page_id: Optional[str],
    ) -> None:
        self._current_page_filter = page_id
        self.reload_dashboard_data()

    # ======================================================
    # DATA HELPERS
    # ======================================================

    @staticmethod
    def _date_vn(job: Dict[str, Any]):
        value = job.get("scheduled_at_utc")

        if not value:
            return None

        try:
            return utc_iso_to_vn_datetime(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _caption(job: Dict[str, Any]) -> str:
        caption = job.get("snapshot_caption") or ""

        if not caption:
            snapshot = job.get("content_snapshot")

            try:
                if isinstance(snapshot, str):
                    data = json.loads(snapshot)
                else:
                    data = snapshot or {}

                if isinstance(data, dict):
                    caption = data.get("final_caption", "")

            except (ValueError, TypeError):
                caption = ""

        return (
            str(caption).replace("\n", " ").strip()
            or "(Không có caption)"
        )

    def _show_empty(self, kind: str) -> None:
        if kind != self._empty_kind:
            while self.empty_layout.count():
                item = self.empty_layout.takeAt(0)

                if item.widget():
                    item.widget().deleteLater()

            if kind == "pages":
                empty = EmptyState.no_pages(
                    on_add=self.add_page_requested.emit
                )
            else:
                empty = EmptyState.no_schedules(
                    on_create=self.quick_post_requested.emit
                )

            self.empty_layout.addWidget(empty)
            self._empty_kind = kind

        self.content_stack.setCurrentIndex(1)

    # ======================================================
    # RELOAD DASHBOARD DATA
    # ======================================================

    def reload_dashboard_data(self) -> None:
        now = vn_now()

        if now.hour < 12:
            greeting = "Chào buổi sáng"
        elif now.hour < 18:
            greeting = "Chào buổi chiều"
        else:
            greeting = "Chào buổi tối"

        self.lbl_greeting.setText(
            f"{greeting}, Quản trị viên"
        )

        # ----------------------------------------------
        # FANPAGE
        # ----------------------------------------------

        all_pages = self.page_repo.list_pages()

        page_ids = {
            p["id"] for p in all_pages
        }

        if self._current_page_filter is not None:
            scoped_pages = [
                p for p in all_pages
                if p["id"] == self._current_page_filter
            ]
        else:
            scoped_pages = all_pages

        ready_count = sum(
            p.get("status") in ("ready", "unverified")
            for p in scoped_pages
        )

        problem_count = sum(
            p.get("status") in (
                "token_expired",
                "insufficient_permissions",
            )
            for p in scoped_pages
        )

        self.card_pages.update_data(
            str(len(scoped_pages)),
            f"{ready_count} Fanpage sẵn sàng",
        )

        # ----------------------------------------------
        # SCHEDULES
        # ----------------------------------------------

        jobs = self.queue_repo.list_jobs(limit=200)

        if self._current_page_filter:
            scoped_jobs = [
                j for j in jobs
                if j.get("page_id") == self._current_page_filter
            ]
        else:
            scoped_jobs = jobs

        today_count = 0

        for job in scoped_jobs:
            dt = self._date_vn(job)

            if dt is not None and dt.date() == now.date():
                today_count += 1

        pending = sum(
            j.get("state") in (
                "scheduled_local",
                "queued",
                "uploading",
                "processing",
            )
            for j in scoped_jobs
        )

        self.card_schedules.update_data(
            str(today_count),
            f"Đang chờ xử lý: {pending}",
        )

        # ----------------------------------------------
        # MEDIA
        # ----------------------------------------------

        assets = self.media_repo.list_media_assets(limit=500)

        bytes_total = sum(
            a.get("size_bytes", 0) or 0
            for a in assets
        )

        self.card_media.update_data(
            str(len(assets)),
            f"{bytes_total / 1048576:.1f} MB trên máy",
        )

        # ----------------------------------------------
        # LICENSE
        # ----------------------------------------------

        if not self.policy_manager.config.license_required:
            self.card_status.update_data(
                "Miễn phí",
                "Chế độ miễn phí",
            )

        elif self.license_client.is_active:
            self.card_status.update_data(
                "Đã kích hoạt",
                "Bản quyền đang hoạt động",
            )

        else:
            self.card_status.update_data(
                "Chưa có Key",
                "Cần kích hoạt bản quyền",
            )

        # ----------------------------------------------
        # WARNINGS
        # ----------------------------------------------

        failures = sum(
            j.get("state") in (
                "failed_final",
                "missed",
            )
            for j in scoped_jobs
        )

        if problem_count:
            self.alert_banner.level = "warning"
            self.alert_banner.set_message(
                f"{problem_count} Fanpage cần kiểm tra "
                "token hoặc quyền truy cập."
            )
            self.alert_banner.show()

        elif failures:
            self.alert_banner.level = "danger"
            self.alert_banner.set_message(
                f"{failures} tác vụ lỗi hoặc lỡ lịch. "
                "Mở Lịch đăng để xử lý."
            )
            self.alert_banner.show()

        else:
            self.alert_banner.hide()

        # ----------------------------------------------
        # TIMELINE
        # ----------------------------------------------

        self.timeline.update_with_jobs(scoped_jobs)

        # ----------------------------------------------
        # RECENT JOBS
        # ----------------------------------------------

        recent_jobs = scoped_jobs[:10]

        if not recent_jobs:
            self.table_recent.setRowCount(0)

            self._show_empty(
                "pages" if not page_ids else "schedules"
            )
            return

        self.content_stack.setCurrentIndex(0)

        # Xóa các StatusChip cũ trước khi tải lại
        self.table_recent.setRowCount(0)
        self.table_recent.setRowCount(len(recent_jobs))

        statuses = {
            "scheduled_local": "Đã lên lịch",
            "queued": "Đang chờ",
            "uploading": "Đang tải lên",
            "processing": "Đang xử lý",
            "published": "Đã đăng",
            "missed": "Lỡ lịch",
            "paused": "Tạm dừng",
            "failed_retryable": "Chờ thử lại",
            "failed_final": "Thất bại",
            "unknown": "Cần đối chiếu",
        }

        for row, job in enumerate(recent_jobs):
            stamp = self._date_vn(job)

            values = (
                str(job.get("id", ""))[:12],
                str(
                    job.get("page_name")
                    or job.get("page_id")
                    or ""
                ),
                self._caption(job),
                (
                    stamp.strftime("%H:%M %d/%m/%Y")
                    if stamp else "Đăng ngay"
                ),
                statuses.get(
                    job.get("state", "unknown"),
                    "Không xác định",
                ),
            )

            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table_recent.setItem(
                    row, col, cell
                )

            self.table_recent.setCellWidget(
                row,
                4,
                StatusChip(
                    job.get("state", "unknown")
                ),
            )

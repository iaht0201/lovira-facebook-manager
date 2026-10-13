"""Lovira Workspace 2.2 - responsive visual publishing calendar (native PySide6).

Three synchronized read views: Monthly calendar / Kanban / List.
Calendar day click -> posts for that day, grouped visually by time and Fanpage.
All times are displayed as Vietnam time (UTC+07:00).

Target: src/lovira/ui/views/schedule_workspace.py.
"""

from __future__ import annotations

import calendar
import json
import logging
import hashlib
import shutil
import tempfile
import weakref
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QProcess, QStandardPaths, QUrl
from PySide6.QtGui import QKeyEvent, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QSizePolicy,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.workers.recovery import RecoveryManager
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.widgets.status_chip import StatusChip
from src.lovira.ui.shell.global_context import GlobalPageContext

logger = logging.getLogger(__name__)
VN_TZ = timezone(timedelta(hours=7))
MAX_LIST_ROWS = 500
MAX_MONTH_ROWS = 5000
MAX_VISIBLE_DAY_CARDS = 100
MAX_KANBAN_COLUMN_CARDS = 90
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
CONTENT_TYPES = {"text": "Văn bản", "photo": "Ảnh", "video": "Video", "reels": "Reels"}

STATE_LABELS = {
    "scheduled_local": "Lịch trên máy",
    "scheduled_remote": "Facebook đã nhận",
    "queued": "Đang chờ",
    "publishing": "Đang đăng",
    "published": "Đã đăng",
    "paused": "Tạm dừng",
    "missed": "Lỡ lịch",
    "unknown": "Cần đối chiếu",
    "failed_retryable": "Lỗi - có thể thử lại",
    "failed_final": "Lỗi cuối",
    "cancelled": "Đã hủy",
}
STATE_COLORS = {
    "scheduled_local": "#a78bfa",
    "scheduled_remote": "#60a5fa",
    "queued": "#a78bfa",
    "publishing": "#60a5fa",
    "published": "#34d399",
    "paused": "#fbbf24",
    "missed": "#fb7185",
    "unknown": "#fbbf24",
    "failed_retryable": "#fb7185",
    "failed_final": "#fb7185",
    "cancelled": "#8996ac",
}
KANBAN = (
    ("Chờ đăng", {"scheduled_local", "queued", "publishing"}),
    ("Facebook đã nhận", {"scheduled_remote"}),
    ("Tạm dừng", {"paused"}),
    ("Hoàn tất", {"published", "cancelled"}),
    ("Cần xử lý", {"missed", "unknown", "failed_retryable", "failed_final"}),
)


def _parse_vn(value: Any) -> Optional[datetime]:
    """Parse storage ISO UTC safely; a naive value is assumed UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(VN_TZ)
    except (TypeError, ValueError, OverflowError):
        return None


def _snapshot_data(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def _snapshot_caption(value: Any) -> str:
    snap = _snapshot_data(value)
    return str(snap.get("final_caption") or snap.get("caption") or "")


def _caption(row: Dict[str, Any], max_chars: int = 90) -> str:
    value = (row.get("_caption") or "").replace("\r", " ").replace("\n", " ").strip()
    if not value:
        value = "Bài đăng media (không có chú thích)"
    return value if len(value) <= max_chars else value[: max_chars - 1] + "…"


def _time_label(row: Dict[str, Any]) -> str:
    when = row.get("_when_vn")
    return when.strftime("%H:%M") if when else "--:--"


def _prepare(row: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    snap = _snapshot_data(result.get("content_snapshot"))
    result["_snapshot"] = snap
    result["_when_vn"] = _parse_vn(result.get("scheduled_at_utc"))
    result["_caption"] = str(snap.get("final_caption") or snap.get("caption") or "")
    result["_page_name"] = str(result.get("page_name") or result.get("page_id") or "Không rõ Fanpage")
    result["_type"] = str(snap.get("content_type") or "text").lower()
    result["_media_id"] = str(snap.get("primary_media_id") or "")
    result["_media_path"] = str(snap.get("media_path") or "")
    result["_thumbnail"] = ""
    result["_duration"] = None
    result["_search"] = " ".join(
        str(part).lower() for part in (result.get("id") or "", result.get("page_id") or "",
                                   result["_page_name"], result["_caption"], result["_type"])
    )
    return result


class AvatarLoader(QObject):
    """Optional, non-blocking HTTPS fanpage avatars. No Facebook credentials involved."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.cached: Dict[str, QPixmap] = {}
        self.failed: set[str] = set()
        self.pending: Dict[str, List[Any]] = {}

    def apply(self, url: str, label: QLabel, size: int) -> None:
        if not url.startswith("https://") or url in self.failed:
            return
        if url in self.cached:
            self._set(label, self.cached[url], size)
            return
        if url in self.pending:
            self.pending[url].append((weakref.ref(label), size))
            return
        self.pending[url] = [(weakref.ref(label), size)]
        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(7000)
        reply = self.manager.get(req)
        reply.finished.connect(lambda url=url, reply=reply: self._finished(url, reply))

    @staticmethod
    def _set(label: QLabel, pix: QPixmap, size: int) -> None:
        try:
            label.setPixmap(pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation))
        except RuntimeError:
            pass  # Qt already deleted the label while a request was pending.

    def _finished(self, url: str, reply: QNetworkReply) -> None:
        requests = self.pending.pop(url, [])
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            if len(data) <= 1024 * 1024:
                pix = QPixmap()
                if pix.loadFromData(data) and not pix.isNull():
                    self.cached[url] = pix
                    for ref, size in requests:
                        label = ref()
                        if label is not None:
                            self._set(label, pix, size)
        if url not in self.cached:
            self.failed.add(url)
        reply.deleteLater()


class AvatarLabel(QLabel):
    def __init__(self, row: Dict[str, Any], loader: Optional[AvatarLoader], size: int = 24,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#344969;color:#eef5ff;border:1px solid #496080;"
                           f"border-radius:{size // 2}px;font-size:{max(9, size//3)}px;font-weight:700;")
        name = str(row.get("_page_name") or "P").strip()
        self.setText(name[:1].upper())
        self.setToolTip(name)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        url = str(row.get("page_avatar_url") or "")
        if loader and url:
            loader.apply(url, self, size)


class MediaPreview(QLabel):
    """Draw local image/thumbnail, otherwise a truthful video/photo/text fallback."""

    def __init__(self, row: Dict[str, Any], height: int = 58, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.row = row
        self._image = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(height)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background:#101b2c;border:1px solid #30435c;border-radius:7px;color:#91a9c8;")
        self.set_thumbnail(str(row.get("_thumbnail") or ""))

    def set_thumbnail(self, path: str) -> None:
        pix = QPixmap(path) if path and Path(path).is_file() else QPixmap()
        self._image = pix
        if not pix.isNull():
            self.setText("")
            self._scale()
        else:
            kind = str(self.row.get("_type") or "")
            self.setText("▶ VIDEO" if kind in ("video", "reels") else ("▧ ẢNH" if kind == "photo" else "✎ TEXT"))

    def _scale(self) -> None:
        if not self._image.isNull():
            self.setPixmap(self._image.scaled(max(self.width()-4, 1), max(self.height()-4, 1),
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._scale()


class CalendarDayCell(QFrame):
    """Low minimum cell height ensures every week remains visible without scrolling."""

    clicked = Signal(object)

    def __init__(self, day: date, in_month: bool, jobs: List[Dict[str, Any]], selected: bool,
                 avatar_loader: Optional[AvatarLoader] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.day = day
        self.in_month = in_month
        self.setObjectName("calendarDay")
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if in_month else Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor if in_month else Qt.CursorShape.ArrowCursor)
        bg = "#20324a" if selected else "#131f30"
        border = "#7289ff" if selected else ("#35435a" if day == datetime.now(VN_TZ).date() else "#263447")
        if not in_month:
            bg, border = "#101824", "#182536"
        self.setStyleSheet(f"QFrame#calendarDay {{background:{bg};border:1px solid {border};border-radius:7px;}}")
        inner = QVBoxLayout(self)
        inner.setContentsMargins(5, 5, 5, 3)
        inner.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(3)
        day_lbl = QLabel(str(day.day))
        day_lbl.setStyleSheet("color:" + ("#f8fbff" if in_month else "#677c96") + ";font-size:11px;font-weight:700;border:none;")
        day_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_row.addWidget(day_lbl)
        title_row.addStretch(1)
        if jobs and in_month:
            count = QLabel(f"{len(jobs)} bài")
            count.setStyleSheet("color:#a5c5e6;background:#273952;border:none;border-radius:4px;font-size:9px;padding:1px 3px;")
            count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title_row.addWidget(count)
        inner.addLayout(title_row)
        if in_month and jobs:
            job = jobs[0]
            entry = QHBoxLayout()
            entry.setSpacing(3)
            entry.addWidget(AvatarLabel(job, avatar_loader, 16))
            mark = "▶ " if job.get("_type") in ("video", "reels") else ("▧ " if job.get("_type") == "photo" else "")
            info = QLabel(f"{_time_label(job)} · {mark}{job['_page_name']}")
            info.setStyleSheet(f"color:{STATE_COLORS.get(job.get('state'),'#bbc9dc')};font-size:10px;border:none;")
            info.setMinimumWidth(0)
            info.setTextFormat(Qt.TextFormat.PlainText)
            info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            info.setToolTip(f"{job['_page_name']} · {_caption(job, 180)}")
            entry.addWidget(info, stretch=1)
            inner.addLayout(entry)
        inner.addStretch(1)
        self.setToolTip(f"{day:%d/%m/%Y} · {len(jobs)} bài đăng. Click để xem chi tiết.")

    def mousePressEvent(self, event: Any) -> None:
        if self.in_month and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.day)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.in_month and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.day)
            event.accept()
            return
        super().keyPressEvent(event)


class ScheduleJobCard(QFrame):
    """Small thumbnail + avatar + caption + status, for Kanban and day agenda."""
    clicked = Signal(str)

    def __init__(self, row: Dict[str, Any], selected: bool = False,
                 avatar_loader: Optional[AvatarLoader] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.job = row
        self.job_id = str(row["id"])
        self.setObjectName("postCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"Job ID: {self.job_id}\n{_caption(row, 400)}")
        self._set_style(selected)
        root = QHBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(7)
        media = MediaPreview(row, 58)
        media.setFixedWidth(64)
        root.addWidget(media)
        right = QVBoxLayout()
        right.setSpacing(3)
        page = QHBoxLayout()
        page.setSpacing(5)
        page.addWidget(AvatarLabel(row, avatar_loader, 20))
        name = QLabel(row["_page_name"])
        name.setStyleSheet("color:#f4f6fd;font-size:11px;font-weight:700;border:none;")
        name.setMinimumWidth(0)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        page.addWidget(name, 1)
        hour = QLabel(_time_label(row))
        hour.setStyleSheet("color:#a5b2c6;font-size:10px;border:none;")
        hour.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        page.addWidget(hour)
        right.addLayout(page)
        body = QLabel(_caption(row, 76))
        body.setStyleSheet("color:#bdc9dc;font-size:10px;border:none;")
        body.setWordWrap(True)
        body.setMaximumHeight(31)
        body.setMinimumWidth(0)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        right.addWidget(body)
        color = STATE_COLORS.get(str(row.get("state")), "#9ca3af")
        status = QLabel(f"● {STATE_LABELS.get(str(row.get('state')), str(row.get('state')))}  ·  {CONTENT_TYPES.get(row.get('_type'), 'Bài')}")
        status.setStyleSheet(f"color:{color};font-size:10px;border:none;")
        status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        right.addWidget(status)
        root.addLayout(right, stretch=1)

    def _set_style(self, selected: bool) -> None:
        border = "#8192ff" if selected else "#314057"
        self.setStyleSheet(f"QFrame#postCard {{background:#1b293c;border:1px solid {border};border-radius:8px;}}"
                           "QFrame#postCard:hover {border-color:#7184ad;}")

    def set_selected(self, selected: bool) -> None:
        self._set_style(selected)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.job_id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self.job_id)
            event.accept()
            return
        super().keyPressEvent(event)


class ScheduleWorkspaceView(QWidget):
    """Schedule manager with compact list, month calendar, and read-only Kanban."""

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
        self._current_page_filter: Optional[str] = None  # Header global context
        self._page_filter: Optional[str] = None          # Local dropdown
        self._cached_rows: List[Dict[str, Any]] = []
        self._month_rows: List[Dict[str, Any]] = []
        self._list_truncated = False
        self._month_truncated = False
        self._filtered_list: List[Dict[str, Any]] = []
        self._filtered_month: List[Dict[str, Any]] = []
        self._selected_job_id: Optional[str] = None
        self._cards: List[ScheduleJobCard] = []
        self._selected_day = datetime.now(VN_TZ).date()
        self._month_anchor = self._selected_day.replace(day=1)
        self._avatar_loader = AvatarLoader(self)
        self._video_process: Optional[QProcess] = None
        self._video_target = ""
        self._init_ui()
        if self.page_context:
            self.page_context.page_scope_changed.connect(self._on_page_scope_changed)
        self.reload_schedules()

    def _init_ui(self) -> None:
        self.setObjectName("scheduleRoot")
        self.setStyleSheet("""
            QWidget#scheduleRoot { background: transparent; color: #eaf0fa; }
            QWidget#scheduleRoot QComboBox, QWidget#scheduleRoot QLineEdit {
                min-height: 30px; max-height: 30px; color: #e8eff9; background: #19283b;
                border: 1px solid #36475d; border-radius: 7px; padding: 0px 9px;
            }
            QWidget#scheduleRoot QComboBox QAbstractItemView {
                background: #19283b; color: #e8eff9; selection-background-color: #39496c;
            }
            QWidget#scheduleRoot QPushButton#compactButton,
            QWidget#scheduleRoot QToolButton#compactTool {
                min-height: 30px; max-height: 30px; color: #dce5f4;
                background: #202f44; border: 1px solid #35455c;
                border-radius: 7px; padding: 0px 10px; font-size: 11px;
            }
            QWidget#scheduleRoot QPushButton#compactButton:hover,
            QWidget#scheduleRoot QToolButton#compactTool:hover { background: #31445e; }
            QWidget#scheduleRoot QPushButton#compactButton:disabled { color: #65758b; background: #192536; }
            QWidget#scheduleRoot QPushButton#schedulePrimary {
                min-height: 31px; max-height: 31px; color: white;
                background: #6058db; border: none; border-radius: 7px;
                padding: 0 14px; font-size: 11px; font-weight: 700;
            }
            QWidget#scheduleRoot QPushButton#schedulePrimary:hover { background: #736beb; }
            QWidget#scheduleRoot QTabBar::tab {
                color: #9caec6; background: transparent; padding: 8px 12px;
                min-width: 68px; border: none; border-bottom: 2px solid transparent;
            }
            QWidget#scheduleRoot QTabBar::tab:selected {
                color: #f7faff; border-bottom: 2px solid #8b83ff; font-weight: 700;
            }
            QWidget#scheduleRoot QTableWidget {
                color: #d9e4f5; background: #152235; alternate-background-color: #19273a;
                gridline-color: #26374b; border: 1px solid #2b3a4f;
                selection-background-color: #344565; selection-color: #ffffff;
            }
            QWidget#scheduleRoot QHeaderView::section {
                background: #1d2d42; color: #b0bed2; padding: 8px;
                border: none; border-bottom: 1px solid #34445a; font-size: 11px;
            }
            QWidget#scheduleRoot QScrollArea { border: 0; background: transparent; }
            QWidget#scheduleRoot QMenu {
                color: #e8effa; background: #1d2b40; border: 1px solid #34445c;
            }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 14, 10)
        outer.setSpacing(7)

        # Compact header, no overlong all-caps title.
        header = QHBoxLayout()
        header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Lịch đăng bài")
        title.setStyleSheet("color: #f5f7fd;font-size: 19px;font-weight: 750;")
        self.lbl_subtitle = QLabel("Quản lý lịch Reels & bài viết · Giờ Việt Nam (UTC+7)")
        self.lbl_subtitle.setStyleSheet("color: #94a7bf;font-size: 11px;")
        titles.addWidget(title)
        titles.addWidget(self.lbl_subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.btn_refresh = QToolButton()
        self.btn_refresh.setObjectName("compactTool")
        self.btn_refresh.setIcon(get_icon("refresh_cw", "#c3d0e3", 15))
        self.btn_refresh.setToolTip("Làm mới dữ liệu")
        self.btn_refresh.setFixedWidth(34)
        self.btn_refresh.clicked.connect(lambda _checked=False: self.reload_schedules(refresh_pages=True))
        header.addWidget(self.btn_refresh)
        self.btn_new_schedule = QPushButton("+  Lên lịch")
        self.btn_new_schedule.setObjectName("schedulePrimary")
        self.btn_new_schedule.clicked.connect(self.create_schedule_requested.emit)
        header.addWidget(self.btn_new_schedule)
        outer.addLayout(header)

        # Minimal single-line counters, including paused jobs so summary never shows all zeros with visible content.
        kpi = QFrame()
        kpi.setStyleSheet("QFrame {background: #18283b;border: 1px solid #2b3d53;border-radius: 8px;}")
        kpi_row = QHBoxLayout(kpi)
        kpi_row.setContentsMargins(10, 6, 10, 6)
        kpi_row.setSpacing(0)
        self._kpi_labels = {}
        for index, (key, name, color) in enumerate((
            ("total", "Tổng", "#e0eaff"),
            ("local", "Lịch máy", "#b6a5ff"),
            ("remote", "Facebook nhận", "#7dc7ff"),
            ("paused", "Tạm dừng", "#ffd17d"),
            ("published", "Đã đăng", "#69ddb2"),
            ("issues", "Cần xử lý", "#ff9aa6"),
        )):
            slot = QHBoxLayout()
            slot.setSpacing(5)
            label = QLabel(name)
            label.setStyleSheet("color: #9aacc3;font-size: 11px;border: none;")
            number = QLabel("0")
            number.setStyleSheet(f"color: {color};font-size: 13px;font-weight: 700;border: none;")
            self._kpi_labels[key] = number
            slot.addWidget(label)
            slot.addWidget(number)
            slot.addStretch(1)
            kpi_row.addLayout(slot, stretch=1)
            if index < 5:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.VLine)
                divider.setFixedWidth(1)
                divider.setStyleSheet("background: #35445a;border: none;")
                kpi_row.addWidget(divider)
        kpi.setToolTip("Chỉ số toàn bộ lịch thuộc Fanpage đang chọn, không bị giới hạn 500 dòng hiển thị.")
        outer.addWidget(kpi)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.page_combo = QComboBox()
        self.page_combo.setFixedWidth(182)
        self.page_combo.setToolTip("Lọc theo Fanpage")
        self.page_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.page_combo.setMinimumContentsLength(15)
        self.page_combo.currentIndexChanged.connect(self._on_local_page_changed)
        tools.addWidget(self.page_combo)
        self.cb_filter_state = QComboBox()
        self.cb_filter_state.setFixedWidth(177)
        self.cb_filter_state.addItem("Tất cả trạng thái", None)
        for state, label in STATE_LABELS.items():
            self.cb_filter_state.addItem(label, state)
        self.cb_filter_state.currentIndexChanged.connect(self._apply_filters)
        tools.addWidget(self.cb_filter_state)
        self.search_filter = QLineEdit()
        self.search_filter.setClearButtonEnabled(True)
        self.search_filter.setPlaceholderText("Tìm Fanpage, nội dung hoặc mã Job...")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_filters)
        self.search_filter.textChanged.connect(lambda _text: self._search_timer.start(180))
        tools.addWidget(self.search_filter, stretch=1)
        outer.addLayout(tools)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        self.mode_tabs = QTabBar()
        for text in ("Lịch tháng", "Kanban", "Danh sách"):
            self.mode_tabs.addTab(text)
        self.mode_tabs.currentChanged.connect(self._switch_view)
        tabs_row.addWidget(self.mode_tabs)
        tabs_row.addStretch(1)
        self.lbl_limit = QLabel("")
        self.lbl_limit.setStyleSheet("color: #8ea2ba;font-size: 10px;")
        tabs_row.addWidget(self.lbl_limit)
        outer.addLayout(tabs_row)

        self.view_stack = QStackedWidget()
        self._build_calendar_view()
        self._build_kanban_view()
        self._build_list_view()
        self.content_stack = self.view_stack  # Compatibility alias.
        outer.addWidget(self.view_stack, stretch=1)
        self.mode_tabs.setCurrentIndex(0)
        self.view_stack.setCurrentIndex(0)

        # One contextual action rather than four permanently wide buttons.
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.lbl_selection = QLabel("Chọn một bài để xem chi tiết hoặc thao tác")
        self.lbl_selection.setStyleSheet("color: #9eafc7;font-size: 11px;")
        footer.addWidget(self.lbl_selection, stretch=1)
        self.btn_details = QPushButton("Chi tiết")
        self.btn_details.setObjectName("compactButton")
        self.btn_details.clicked.connect(self._show_job_details)
        footer.addWidget(self.btn_details)
        self.btn_action = QPushButton("Thao tác")
        self.btn_action.setObjectName("compactButton")
        self.btn_action.clicked.connect(self._handle_context_action)
        footer.addWidget(self.btn_action)
        self.btn_more = QToolButton()
        self.btn_more.setObjectName("compactTool")
        self.btn_more.setText("⋯")
        self.btn_more.setToolTip("Thao tác khác")
        self.btn_more.setFixedWidth(34)
        self.btn_more.clicked.connect(self._open_more_menu)
        footer.addWidget(self.btn_more)
        outer.addLayout(footer)
        self._update_selection_actions()

    def _build_list_view(self) -> None:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.list_stack = QStackedWidget()
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(("Giờ đăng · VN", "Fanpage", "Nội dung", "Trạng thái", "Ghi chú"))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 166)
        self.table.setColumnWidth(3, 158)
        self.table.setColumnWidth(4, 148)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(41)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._show_job_details())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self.list_stack.addWidget(self.table)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_message = QLabel("Chưa có lịch đăng")
        self.empty_message.setStyleSheet("color: #cbd7e9;font-size: 14px;font-weight: 700;")
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = QLabel("Tạo bài mới hoặc thay đổi bộ lọc để xem lịch đăng.")
        self.empty_hint.setStyleSheet("color: #8c9db4;font-size: 11px;")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addWidget(self.empty_hint)
        btn_empty_new = QPushButton("+ Lên lịch bài mới")
        btn_empty_new.setObjectName("compactButton")
        btn_empty_new.clicked.connect(self.create_schedule_requested.emit)
        empty_layout.addWidget(btn_empty_new, alignment=Qt.AlignmentFlag.AlignCenter)
        self.list_stack.addWidget(empty)
        layout.addWidget(self.list_stack)
        self.view_stack.addWidget(body)

    def _build_calendar_view(self) -> None:
        body = QWidget()
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(7)
        navigator = QHBoxLayout()
        navigator.setSpacing(7)
        self.btn_prev = self._small_button("‹", "Tháng trước")
        self.btn_prev.clicked.connect(lambda: self._change_month(-1))
        navigator.addWidget(self.btn_prev)
        self.lbl_month = QLabel("")
        self.lbl_month.setStyleSheet("color: #ecf2fb;font-size: 13px;font-weight: 700;")
        navigator.addWidget(self.lbl_month)
        self.btn_next = self._small_button("›", "Tháng sau")
        self.btn_next.clicked.connect(lambda: self._change_month(1))
        navigator.addWidget(self.btn_next)
        btn_today = self._small_button("Hôm nay", "Trở về ngày hôm nay")
        btn_today.clicked.connect(self._go_today)
        navigator.addWidget(btn_today)
        navigator.addStretch(1)
        self.btn_day_mobile = self._small_button("Xem bài trong ngày", "Mở chi tiết ngày đang chọn")
        self.btn_day_mobile.clicked.connect(self._show_day_dialog)
        self.btn_day_mobile.hide()
        navigator.addWidget(self.btn_day_mobile)
        vbox.addLayout(navigator)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)
        self._calendar_splitter = splitter
        # No scroll area: the grid automatically distributes available height over 4-6 weeks.
        self.month_widget = QWidget()
        self.month_widget.setMinimumHeight(0)
        self.days_grid = QGridLayout(self.month_widget)
        self.days_grid.setContentsMargins(0, 0, 3, 0)
        self.days_grid.setHorizontalSpacing(5)
        self.days_grid.setVerticalSpacing(4)
        splitter.addWidget(self.month_widget)

        sidebar = QFrame()
        self.day_sidebar = sidebar
        sidebar.setObjectName("scheduleSidebar")
        sidebar.setStyleSheet("QFrame#scheduleSidebar {background:#152236;border:1px solid #29394e;border-radius:8px;}")
        sidebar.setMinimumWidth(0)
        right = QVBoxLayout(sidebar)
        right.setContentsMargins(10, 9, 10, 9)
        right.setSpacing(6)
        self.lbl_day_title = QLabel("")
        self.lbl_day_title.setStyleSheet("color:#f3f6fd;font-size:12px;font-weight:700;border:none;")
        self.lbl_day_count = QLabel("")
        self.lbl_day_count.setStyleSheet("color:#93a8c2;font-size:10px;border:none;")
        right.addWidget(self.lbl_day_title)
        right.addWidget(self.lbl_day_count)
        self.day_scroll = QScrollArea()
        self.day_scroll.setWidgetResizable(True)
        self.day_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.day_content = QWidget()
        self.day_cards_layout = QVBoxLayout(self.day_content)
        self.day_cards_layout.setContentsMargins(0, 0, 2, 0)
        self.day_cards_layout.setSpacing(6)
        self.day_scroll.setWidget(self.day_content)
        right.addWidget(self.day_scroll, stretch=2)
        # Selected post preview lives directly in the sidebar, not a separate modal.
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_content = QWidget()
        detail_layout = QVBoxLayout(self.detail_content)
        detail_layout.setContentsMargins(1, 4, 2, 2)
        detail_layout.setSpacing(5)
        detail_title = QLabel("XEM TRƯỚC BÀI ĐĂNG")
        detail_title.setStyleSheet("color:#9bb2ce;font-size:10px;font-weight:700;")
        detail_layout.addWidget(detail_title)
        self.preview_image = MediaPreview({}, 112)
        detail_layout.addWidget(self.preview_image)
        page_heading = QHBoxLayout()
        self.preview_page_row = page_heading
        page_heading.setSpacing(7)
        self.preview_avatar = AvatarLabel({}, None, 28)
        page_heading.addWidget(self.preview_avatar)
        self.preview_page = QLabel("Chọn bài để xem chi tiết")
        self.preview_page.setStyleSheet("color:#eef4ff;font-weight:700;font-size:11px;")
        self.preview_page.setWordWrap(True)
        self.preview_page.setTextFormat(Qt.TextFormat.PlainText)
        page_heading.addWidget(self.preview_page, 1)
        detail_layout.addLayout(page_heading)
        self.preview_meta = QLabel("")
        self.preview_meta.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_meta.setWordWrap(True)
        self.preview_meta.setStyleSheet("color:#92a9c4;font-size:10px;")
        detail_layout.addWidget(self.preview_meta)
        self.preview_caption = QLabel("")
        self.preview_caption.setWordWrap(True)
        self.preview_caption.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview_caption.setStyleSheet("color:#d6e3f4;font-size:11px;")
        detail_layout.addWidget(self.preview_caption)
        self.preview_error = QLabel("")
        self.preview_error.setWordWrap(True)
        self.preview_error.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_error.setStyleSheet("color:#ff9cac;font-size:10px;")
        detail_layout.addWidget(self.preview_error)
        detail_actions = QHBoxLayout()
        self.btn_open_media = self._small_button("▶ Mở media", "Mở video/ảnh từ máy (không tự động đăng)")
        self.btn_open_media.clicked.connect(self._open_selected_media)
        detail_actions.addWidget(self.btn_open_media)
        self.btn_detail_full = self._small_button("Chi tiết", "Xem đầy đủ mã tác vụ và nội dung")
        self.btn_detail_full.clicked.connect(self._show_job_details)
        detail_actions.addWidget(self.btn_detail_full)
        detail_actions.addStretch(1)
        detail_layout.addLayout(detail_actions)
        detail_layout.addStretch(1)
        self.detail_scroll.setWidget(self.detail_content)
        right.addWidget(self.detail_scroll, stretch=3)
        splitter.addWidget(sidebar)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([760, 350])
        vbox.addWidget(splitter, stretch=1)
        self.view_stack.addWidget(body)

    def _build_kanban_view(self) -> None:
        self.board_scroll = QScrollArea()
        self.board_scroll.setWidgetResizable(True)
        self.board_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.board_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.board_widget = QWidget()
        self.board_columns = QHBoxLayout(self.board_widget)
        self.board_columns.setContentsMargins(0, 0, 0, 0)
        self.board_columns.setSpacing(8)
        self.board_scroll.setWidget(self.board_widget)
        self.view_stack.addWidget(self.board_scroll)

    def _small_button(self, title: str, tooltip: str) -> QPushButton:
        btn = QPushButton(title)
        btn.setObjectName("compactButton")
        btn.setToolTip(tooltip)
        return btn

    def _switch_view(self, index: int) -> None:
        if index not in (0, 1, 2):
            return
        self.view_stack.setCurrentIndex(index)
        if index == 0:
            self._render_month()
        elif index == 1:
            self._render_kanban()
        else:
            self._render_table()
        self._update_limit_label()

    def _on_page_scope_changed(self, page_id: Optional[str]) -> None:
        self._current_page_filter = str(page_id) if page_id else None
        self._page_filter = None
        self.reload_schedules()

    def _on_local_page_changed(self, _index: int) -> None:
        if self.page_combo.signalsBlocked():
            return
        value = self.page_combo.currentData()
        self._page_filter = str(value) if value else None
        self.reload_schedules(refresh_pages=False)

    def _effective_page_id(self) -> Optional[str]:
        return self._current_page_filter or self._page_filter

    def _update_page_options(self) -> None:
        previous = self._effective_page_id()
        sql = """
            SELECT DISTINCT j.page_id, COALESCE(NULLIF(p.name, ''), j.page_id) AS page_name
            FROM publish_jobs j LEFT JOIN pages p ON p.id = j.page_id
        """
        params: List[Any] = []
        if self._current_page_filter:
            sql += " WHERE j.page_id = ?"
            params.append(self._current_page_filter)
        sql += " ORDER BY page_name COLLATE NOCASE"
        with self.db.connection_scope() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        if not self._current_page_filter:
            self.page_combo.addItem("Tất cả Fanpage", None)
        for rec in rows:
            page_id = str(rec[0])
            self.page_combo.addItem(str(rec[1] or page_id), page_id)
            self.page_combo.setItemData(self.page_combo.count() - 1, str(rec[1] or page_id), Qt.ItemDataRole.ToolTipRole)
        target = self.page_combo.findData(previous)
        if target < 0:
            target = 0 if self.page_combo.count() else -1
        if target >= 0:
            self.page_combo.setCurrentIndex(target)
        self._page_filter = None if self._current_page_filter else (
            str(self.page_combo.currentData()) if self.page_combo.currentData() else None
        )
        self.page_combo.setEnabled(not bool(self._current_page_filter))
        self.page_combo.blockSignals(False)

    def _sql_where(self) -> tuple[str, List[Any]]:
        page_id = self._effective_page_id()
        return (" WHERE j.page_id = ?", [page_id]) if page_id else ("", [])

    def _read_rows(self, month: bool) -> tuple[List[Dict[str, Any]], bool]:
        base = """
            SELECT j.id, j.batch_id, j.page_id, p.name AS page_name,
                   j.content_snapshot, j.state, j.scheduled_at_utc,
                   j.blocked_reason, j.last_error_code, p.avatar_url AS page_avatar_url
            FROM publish_jobs j LEFT JOIN pages p ON p.id = j.page_id
        """
        where, params = self._sql_where()
        if month:
            year, mon = self._month_anchor.year, self._month_anchor.month
            start_vn = datetime(year, mon, 1, tzinfo=VN_TZ)
            end_vn = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=VN_TZ)
            criteria = "julianday(j.scheduled_at_utc) >= julianday(?) AND julianday(j.scheduled_at_utc) < julianday(?)"
            where += (" AND " if where else " WHERE ") + criteria
            params.extend([start_vn.astimezone(timezone.utc).isoformat(), end_vn.astimezone(timezone.utc).isoformat()])
            limit = MAX_MONTH_ROWS
        else:
            limit = MAX_LIST_ROWS
        sql = base + where + " ORDER BY j.scheduled_at_utc DESC, j.id DESC LIMIT ?"
        params.append(limit + 1)
        with self.db.connection_scope() as conn:
            result = conn.execute(sql, tuple(params)).fetchall()
        too_many = len(result) > limit
        prepared = [_prepare(dict(row)) for row in result[:limit]]
        self._enrich_media(prepared)
        return prepared, too_many

    def _enrich_media(self, rows: List[Dict[str, Any]]) -> None:
        """Bulk-read thumbnail/local media paths from the existing media_assets schema."""
        ids = {r["_media_id"] for r in rows if r["_media_id"]}
        assets: Dict[str, Dict[str, Any]] = {}
        if ids:
            with self.db.connection_scope() as conn:
                # SQLite default max variable count can be 999; never send an unbounded IN list.
                sorted_ids = sorted(ids)
                for off in range(0, len(sorted_ids), 400):
                    chunk = sorted_ids[off:off+400]
                    placeholders = ",".join("?" for _ in chunk)
                    sql = f"SELECT id, local_path, thumbnail_path, duration FROM media_assets WHERE id IN ({placeholders})"
                    for asset in conn.execute(sql, chunk):
                        assets[str(asset["id"])] = dict(asset)
        for row in rows:
            asset = assets.get(row["_media_id"], {})
            row["_media_path"] = row["_media_path"] or str(asset.get("local_path") or "")
            thumbnail = str(asset.get("thumbnail_path") or "")
            if thumbnail and Path(thumbnail).is_file():
                row["_thumbnail"] = thumbnail
            elif Path(row["_media_path"]).suffix.lower() in IMAGE_EXTS and Path(row["_media_path"]).is_file():
                row["_thumbnail"] = row["_media_path"]
            row["_duration"] = asset.get("duration")

    def _update_kpis(self) -> None:
        where, params = self._sql_where()
        sql = "SELECT j.state, COUNT(*) AS num FROM publish_jobs j" + where + " GROUP BY j.state"
        with self.db.connection_scope() as conn:
            counts = {str(r[0]): int(r[1]) for r in conn.execute(sql, tuple(params)).fetchall()}
        self._kpi_labels["total"].setText(str(sum(counts.values())))
        self._kpi_labels["paused"].setText(str(counts.get("paused", 0)))
        self._kpi_labels["local"].setText(str(counts.get("scheduled_local", 0)))
        self._kpi_labels["remote"].setText(str(counts.get("scheduled_remote", 0)))
        self._kpi_labels["published"].setText(str(counts.get("published", 0)))
        self._kpi_labels["issues"].setText(str(sum(counts.get(k, 0) for k in (
            "unknown", "missed", "failed_retryable", "failed_final"
        ))))

    def reload_schedules(self, refresh_pages: bool = True) -> None:
        """Reload query-scoped views; monthly rows are independent of the recent list cap."""
        try:
            if refresh_pages:
                self._update_page_options()
            self._cached_rows, self._list_truncated = self._read_rows(month=False)
            self._month_rows, self._month_truncated = self._read_rows(month=True)
            self._update_kpis()
            self._apply_filters()
        except Exception as exc:
            logger.exception("Unable to load scheduled jobs")
            QMessageBox.warning(self, "Không tải được lịch", f"Không thể đọc dữ liệu lịch đăng:\n{exc}")

    def _filtered(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        state_filter = self.cb_filter_state.currentData()
        needle = self.search_filter.text().strip().lower()
        return [r for r in rows if (not state_filter or r.get("state") == state_filter)
                and (not needle or needle in r["_search"])]

    def _apply_filters(self, *_args: Any) -> None:
        self._filtered_list = self._filtered(self._cached_rows)
        self._filtered_month = self._filtered(self._month_rows)
        index = self.mode_tabs.currentIndex()
        if index == 0:
            self._render_month()
        elif index == 1:
            self._render_kanban()
        else:
            self._render_table()
        self._update_limit_label()
        self._update_selection_actions()

    def _update_limit_label(self) -> None:
        index = self.mode_tabs.currentIndex()
        if index == 0:
            self.lbl_limit.setText("Giới hạn 5.000 bài/tháng" if self._month_truncated else "")
        else:
            self.lbl_limit.setText("500 lịch gần nhất · Hãy lọc Fanpage nếu cần" if self._list_truncated else "")

    def _render_table(self) -> None:
        rows = self._filtered_list
        if not rows:
            self.empty_message.setText("Chưa có lịch đăng" if not self._cached_rows else "Không có bài phù hợp")
            self.list_stack.setCurrentIndex(1)
            self.table.setRowCount(0)
            return
        self.list_stack.setCurrentIndex(0)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        current_row = -1
        for i, r in enumerate(rows):
            when = r.get("_when_vn")
            when_text = when.strftime("%d/%m/%Y · %H:%M") if when else "Chưa định giờ"
            first = QTableWidgetItem(when_text)
            first.setData(Qt.ItemDataRole.UserRole, str(r["id"]))
            first.setToolTip("Mã tác vụ: " + str(r["id"]))
            self.table.setItem(i, 0, first)
            page_item = QTableWidgetItem(r["_page_name"])
            page_item.setToolTip(r["_page_name"])
            self.table.setItem(i, 1, page_item)
            body_item = QTableWidgetItem(_caption(r, 160))
            body_item.setToolTip(r.get("_caption") or "")
            self.table.setItem(i, 2, body_item)
            state = str(r.get("state") or "unknown")
            self.table.setItem(i, 3, QTableWidgetItem(STATE_LABELS.get(state, state)))
            self.table.setCellWidget(i, 3, StatusChip(state))
            note = str(r.get("blocked_reason") or r.get("last_error_code") or "")
            note_item = QTableWidgetItem(note)
            note_item.setToolTip(note)
            self.table.setItem(i, 4, note_item)
            if str(r["id"]) == self._selected_job_id:
                current_row = i
        if current_row >= 0:
            self.table.selectRow(current_row)
        self.table.blockSignals(False)

    def _render_month(self) -> None:
        self.lbl_month.setText(f"Tháng {self._month_anchor.month:02d}/{self._month_anchor.year}")
        while self.days_grid.count():
            item = self.days_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for col, name in enumerate(("T2", "T3", "T4", "T5", "T6", "T7", "CN")):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(20)
            lbl.setStyleSheet("color: #8fa4c0;font-size: 11px;font-weight: 700;")
            self.days_grid.addWidget(lbl, 0, col)
            self.days_grid.setColumnStretch(col, 1)
        by_day: Dict[date, List[Dict[str, Any]]] = defaultdict(list)
        for r in self._filtered_month:
            when = r.get("_when_vn")
            if when:
                by_day[when.date()].append(r)
        for jobs in by_day.values():
            jobs.sort(key=lambda j: (j.get("_when_vn") or datetime.max.replace(tzinfo=VN_TZ), str(j["id"])))
        for row_num in range(1, 7):
            self.days_grid.setRowStretch(row_num, 0)
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            self._month_anchor.year, self._month_anchor.month
        )
        for week_i, week in enumerate(weeks, 1):
            self.days_grid.setRowStretch(week_i, 1)
            for col, day in enumerate(week):
                in_month = day.month == self._month_anchor.month and day.year == self._month_anchor.year
                cell = CalendarDayCell(day, in_month, by_day.get(day, []), day == self._selected_day,
                                       self._avatar_loader)
                cell.clicked.connect(self._select_day)
                self.days_grid.addWidget(cell, week_i, col)
        self._render_day_panel()

    def _render_day_panel(self) -> None:
        day = self._selected_day
        self.lbl_day_title.setText(f"{day.strftime('%d/%m/%Y')} · Lịch trong ngày")
        rows = self._jobs_of_selected_day()
        pages = len({r.get("page_id") for r in rows})
        self.lbl_day_count.setText(f"{len(rows)} bài đăng  ·  {pages} Fanpage")
        self._clear_layout(self.day_cards_layout)
        self._cards = [card for card in self._cards if card.parent() is not self.day_content]
        if not rows:
            label = QLabel("Không có bài nào trong ngày này.\nHãy chọn ngày khác hoặc thay đổi bộ lọc.")
            label.setWordWrap(True)
            label.setStyleSheet("color: #93a6c1;font-size: 11px;border: none;")
            self.day_cards_layout.addWidget(label)
        for row in rows[:MAX_VISIBLE_DAY_CARDS]:
            card = ScheduleJobCard(row, str(row["id"]) == self._selected_job_id, self._avatar_loader)
            card.clicked.connect(self._select_job)
            self.day_cards_layout.addWidget(card)
            self._cards.append(card)
        if len(rows) > MAX_VISIBLE_DAY_CARDS:
            note = QLabel(f"Hiển thị {MAX_VISIBLE_DAY_CARDS}/{len(rows)} bài. Lọc Fanpage để xem thêm.")
            note.setStyleSheet("color:#9daec4;font-size:10px;")
            note.setWordWrap(True)
            self.day_cards_layout.addWidget(note)
        self.day_cards_layout.addStretch(1)
        # Automatically show the first scheduled post in the preview when a day is opened.
        if rows and not any(str(r["id"]) == self._selected_job_id for r in rows):
            self._selected_job_id = str(rows[0]["id"])
        elif not rows:
            self._selected_job_id = None
        for card in self._cards:
            card.set_selected(card.job_id == self._selected_job_id)
        self._render_post_preview()
        self._update_selection_actions()

    def _render_kanban(self) -> None:
        self._clear_layout(self.board_columns)
        self._cards = [card for card in self._cards if card.parent() is self.day_content]
        for title, states in KANBAN:
            rows = [row for row in self._filtered_list if row.get("state") in states]
            column = QFrame()
            column.setMinimumWidth(200)
            column.setMaximumWidth(280)
            column.setStyleSheet("QFrame {background: #152337;border: 1px solid #2b3c53;border-radius: 8px;}")
            stack = QVBoxLayout(column)
            stack.setContentsMargins(9, 9, 9, 9)
            stack.setSpacing(8)
            visible = rows[:MAX_KANBAN_COLUMN_CARDS]
            header = QLabel(f"{title}    {len(rows)}")
            header.setStyleSheet("color: #eef3fc;font-size: 12px;font-weight: 700;border: none;")
            stack.addWidget(header)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            cards_layout = QVBoxLayout(content)
            cards_layout.setContentsMargins(0, 0, 0, 0)
            cards_layout.setSpacing(7)
            for row in visible:
                card = ScheduleJobCard(row, str(row["id"]) == self._selected_job_id, self._avatar_loader)
                card.clicked.connect(self._select_job)
                cards_layout.addWidget(card)
                self._cards.append(card)
            if len(rows) > len(visible):
                info = QLabel(f"{len(visible)}/{len(rows)} bài — dùng bộ lọc để thu hẹp")
                info.setWordWrap(True)
                info.setStyleSheet("color:#9cafc8;font-size:10px;")
                cards_layout.addWidget(info)
            cards_layout.addStretch(1)
            scroll.setWidget(content)
            stack.addWidget(scroll, stretch=1)
            self.board_columns.addWidget(column, stretch=1)
        self.board_columns.addStretch(1)

    @staticmethod
    def _clear_layout(layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                ScheduleWorkspaceView._clear_layout(item.layout())

    def _change_month(self, delta: int) -> None:
        year = self._month_anchor.year
        month = self._month_anchor.month + delta
        year += (month - 1) // 12
        month = (month - 1) % 12 + 1
        self._month_anchor = date(year, month, 1)
        self._selected_day = self._month_anchor
        self.reload_schedules(refresh_pages=False)

    def _go_today(self) -> None:
        self._selected_day = datetime.now(VN_TZ).date()
        self._month_anchor = self._selected_day.replace(day=1)
        self.reload_schedules(refresh_pages=False)

    def _select_day(self, day: date) -> None:
        if day != self._selected_day:
            self._selected_job_id = None
            self._update_selection_actions()
        self._selected_day = day
        self._render_month()
        if self.width() < 970:
            self._show_day_dialog()

    def _on_table_selection(self) -> None:
        index = self.table.currentRow()
        item = self.table.item(index, 0) if index >= 0 else None
        if item:
            job_id = item.data(Qt.ItemDataRole.UserRole)
            self._select_job(str(job_id))

    def _select_job(self, job_id: str) -> None:
        self._selected_job_id = job_id
        # Keep selection visually consistent when switching List / Calendar / Kanban.
        target = -1
        for row_num in range(self.table.rowCount()):
            item = self.table.item(row_num, 0)
            if item and str(item.data(Qt.ItemDataRole.UserRole)) == job_id:
                target = row_num
                break
        self.table.blockSignals(True)
        if target >= 0:
            self.table.selectRow(target)
        else:
            self.table.clearSelection()
        self.table.blockSignals(False)
        for card in self._cards:
            card.set_selected(card.job_id == job_id)
        self._update_selection_actions()
        self._render_post_preview()

    def _selected_job(self) -> Optional[Dict[str, Any]]:
        if not self._selected_job_id:
            return None
        for item in self._cached_rows + self._month_rows:
            if str(item["id"]) == self._selected_job_id:
                return item
        return None

    def _get_selected_job_id(self) -> Optional[str]:
        return self._selected_job_id if self._selected_job() is not None else None

    def _update_selection_actions(self) -> None:
        row = self._selected_job()
        self.btn_details.setEnabled(row is not None)
        self.btn_more.setEnabled(row is not None)
        if row is None:
            self.lbl_selection.setText("Chọn một bài để xem chi tiết hoặc thao tác")
            self.btn_action.setVisible(False)
            return
        self.lbl_selection.setText(f"{row['_page_name']}  ·  {_time_label(row)}  ·  {_caption(row, 43)}")
        state = str(row.get("state") or "")
        action = {
            "scheduled_local": "Tạm dừng",
            "paused": "Tiếp tục",
            "unknown": "Đối chiếu",
            "failed_retryable": "Thử lại",
        }.get(state)
        self.btn_action.setVisible(bool(action))
        if action:
            self.btn_action.setText(action)
            if state == "unknown" and not self.recovery:
                self.btn_action.setEnabled(False)
                self.btn_action.setToolTip("Chưa cấu hình RecoveryManager")
            else:
                self.btn_action.setEnabled(True)
                self.btn_action.setToolTip(action)

    def _handle_context_action(self) -> None:
        row = self._selected_job()
        if not row:
            return
        state = row.get("state")
        if state in ("scheduled_local", "paused"):
            self._handle_pause_toggle()
        elif state == "unknown":
            self._handle_reconcile()
        elif state == "failed_retryable":
            self._handle_retry_job()

    def _open_more_menu(self) -> None:
        row = self._selected_job()
        if not row:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Sao chép mã Job")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(str(row["id"])))
        cancel = menu.addAction("Hủy lịch trên máy")
        cancel.setEnabled(row.get("state") in ("scheduled_local", "paused", "queued"))
        if not cancel.isEnabled():
            cancel.setToolTip("Không thể hủy lịch Facebook hoặc tác vụ đang xử lý từ màn hình này")
        cancel.triggered.connect(self._handle_cancel_job)
        menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomRight()))

    def _show_table_context_menu(self, point: Any) -> None:
        index = self.table.indexAt(point)
        if not index.isValid():
            return
        item = self.table.item(index.row(), 0)
        if item:
            self._select_job(str(item.data(Qt.ItemDataRole.UserRole)))
            self._open_more_menu()

    def _render_post_preview(self) -> None:
        row = self._selected_job()
        if row is None:
            self.preview_page.setText("Chọn bài trong ngày để xem chi tiết")
            self.preview_image.row = {}
            self.preview_image.set_thumbnail("")
            self.preview_caption.setText("")
            self.preview_meta.setText("")
            self.preview_error.setText("")
            self.btn_open_media.setEnabled(False)
            self.btn_detail_full.setEnabled(False)
            return
        self.btn_detail_full.setEnabled(True)
        when = row.get("_when_vn")
        color_name = STATE_LABELS.get(str(row.get("state")), str(row.get("state")))
        self.preview_page.setText(row["_page_name"])
        old_avatar = self.preview_avatar
        self.preview_avatar = AvatarLabel(row, self._avatar_loader, 28)
        self.preview_page_row.replaceWidget(old_avatar, self.preview_avatar)
        old_avatar.hide()
        old_avatar.deleteLater()
        self.preview_meta.setText(f"{when:%d/%m/%Y  %H:%M} (UTC+7)" if when else "Chưa định giờ")
        self.preview_meta.setText(self.preview_meta.text() + "  ·  " + CONTENT_TYPES.get(row.get("_type"), "Bài đăng") + "  ·  " + color_name)
        media_path = row.get("_media_path") or ""
        duration = row.get("_duration")
        if media_path:
            self.preview_meta.setText(self.preview_meta.text() + "\n" + Path(media_path).name
                                      + (f" · {round(float(duration))} giây" if duration else ""))
        self.preview_caption.setText(_caption(row, 700))
        self.preview_error.setText(str(row.get("blocked_reason") or row.get("last_error_code") or ""))
        self.preview_image.row = row
        self.preview_image.set_thumbnail(str(row.get("_thumbnail") or ""))
        self.btn_open_media.setEnabled(bool(media_path and Path(media_path).is_file()))
        if not row.get("_thumbnail") and Path(media_path).suffix.lower() in VIDEO_EXTS:
            self._request_video_thumbnail(row)

    def _open_selected_media(self) -> None:
        row = self._selected_job()
        if not row:
            return
        path = Path(str(row.get("_media_path") or ""))
        if not path.is_file():
            QMessageBox.information(self, "Media không tồn tại", "File đã bị di chuyển hoặc xóa khỏi máy.")
            return
        if path.suffix.lower() in VIDEO_EXTS:
            try:
                from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
                from PySide6.QtMultimediaWidgets import QVideoWidget
            except ImportError:
                pass  # Some installations ship without QtMultimedia: use OS player.
            else:
                dialog = QDialog(self)
                dialog.setWindowTitle("Xem video · " + path.name)
                dialog.resize(min(860, max(self.width() - 80, 480)), min(580, max(self.height() - 70, 360)))
                vertical = QVBoxLayout(dialog)
                player_widget = QVideoWidget(dialog)
                vertical.addWidget(player_widget, 1)
                player = QMediaPlayer(dialog)
                audio = QAudioOutput(dialog)
                player.setAudioOutput(audio)
                player.setVideoOutput(player_widget)
                control = QHBoxLayout()
                play = self._small_button("▶ Phát", "Phát video")
                pause = self._small_button("Ⅱ Tạm dừng", "Dừng hình")
                play.clicked.connect(player.play)
                pause.clicked.connect(player.pause)
                control.addWidget(play)
                control.addWidget(pause)
                control.addStretch(1)
                vertical.addLayout(control)
                player.setSource(QUrl.fromLocalFile(str(path.resolve())))
                player.play()
                dialog.exec()
                player.stop()
                return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "Không mở được media", "Không tìm thấy ứng dụng xem file tương thích.")

    def _request_video_thumbnail(self, row: Dict[str, Any]) -> None:
        """Optionally use installed ffmpeg to extract one frame asynchronously."""
        video_path = str(row.get("_media_path") or "")
        if not Path(video_path).is_file() or not shutil.which("ffmpeg"):
            return
        try:
            stat = Path(video_path).stat()
            unique = f"{video_path}:{stat.st_mtime_ns}:{stat.st_size}"
            key = hashlib.sha256(unique.encode("utf-8")).hexdigest()[:24]
            cache_base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
            folder = Path(cache_base or tempfile.gettempdir()) / "lovira-schedule-thumbs"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (key + ".jpg")
        except OSError:
            return
        if target.is_file():
            row["_thumbnail"] = str(target)
            self.preview_image.set_thumbnail(str(target))
            return
        if self._video_process and self._video_process.state() != QProcess.ProcessState.NotRunning:
            return
        process = QProcess(self)
        self._video_process = process
        self._video_target = str(row["id"])
        process.setProgram(shutil.which("ffmpeg") or "ffmpeg")
        process.setArguments(["-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                              "-ss", "00:00:01", "-i", video_path, "-frames:v", "1",
                              "-vf", "scale=480:-2", str(target)])
        process.finished.connect(lambda _code, _status, row=row, target=target: self._video_thumbnail_ready(row, target))
        process.start()
        QTimer.singleShot(8000, lambda process=process: process.kill()
                          if process.state() != QProcess.ProcessState.NotRunning else None)

    def _video_thumbnail_ready(self, row: Dict[str, Any], target: Path) -> None:
        self._video_process = None
        if target.is_file() and target.stat().st_size:
            row["_thumbnail"] = str(target)
            if self._selected_job_id == str(row["id"]):
                self.preview_image.set_thumbnail(str(target))

    def _show_day_dialog(self) -> None:
        """Narrow window: show selected day's agenda rather than forcing a 7-column scroll."""
        rows = self._jobs_of_selected_day()
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Lịch đăng ngày {self._selected_day:%d/%m/%Y}")
        dlg.resize(min(600, max(self.width()-50, 350)), min(620, max(self.height()-50, 400)))
        layout = QVBoxLayout(dlg)
        label = QLabel(f"{len(rows)} bài · {len({r['page_id'] for r in rows})} Fanpage")
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        stack = QVBoxLayout(content)
        for r in rows:
            card = ScheduleJobCard(r, str(r["id"]) == self._selected_job_id, self._avatar_loader)
            card.clicked.connect(lambda job_id, dlg=dlg: (self._select_job(job_id), dlg.accept(), self._show_job_details()))
            stack.addWidget(card)
        if not rows:
            stack.addWidget(QLabel("Ngày này chưa có bài đăng."))
        stack.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dlg.reject)
        layout.addWidget(close)
        dlg.exec()

    def _jobs_of_selected_day(self) -> List[Dict[str, Any]]:
        rows = [r for r in self._filtered_month if r.get("_when_vn")
                and r["_when_vn"].date() == self._selected_day]
        return sorted(rows, key=lambda r: (r["_when_vn"], r["_page_name"]))

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, "day_sidebar"):
            narrow = self.width() < 970
            if self.day_sidebar.isVisible() == narrow or self.btn_day_mobile.isVisible() != narrow:
                self.day_sidebar.setVisible(not narrow)
                self.btn_day_mobile.setVisible(narrow)

    def _show_job_details(self) -> None:
        row = self._selected_job()
        if row is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Chi tiết lịch đăng")
        dialog.setMinimumWidth(460)
        dialog.resize(560, 540)
        layout = QVBoxLayout(dialog)
        preview = MediaPreview(row, 165)
        layout.addWidget(preview)
        layout.setSpacing(9)
        when = row.get("_when_vn")
        for key, val in (
            ("Fanpage", row["_page_name"]),
            ("Loại nội dung", CONTENT_TYPES.get(row.get("_type"), "Bài đăng")),
            ("Media", row.get("_media_path") or "Không có"),
            ("Thời gian (VN)", when.strftime("%d/%m/%Y %H:%M") if when else "Chưa định giờ"),
            ("Trạng thái", STATE_LABELS.get(str(row.get("state")), str(row.get("state")))),
            ("Mã tác vụ", row["id"]),
            ("Mã nhóm", row.get("batch_id") or "—"),
            ("Lỗi / Lý do", row.get("blocked_reason") or row.get("last_error_code") or "Không có"),
        ):
            line = QLabel(f"{key}: {val}")
            line.setTextFormat(Qt.TextFormat.PlainText)
            line.setWordWrap(True)
            layout.addWidget(line)
        layout.addWidget(QLabel("Nội dung bài viết"))
        caption_field = QPlainTextEdit()
        caption_field.setReadOnly(True)
        caption_field.setPlainText(row.get("_caption") or "(Bài không có chú thích)")
        caption_field.setMinimumHeight(140)
        layout.addWidget(caption_field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _perform_transition(self, job_id: str, new_state: str) -> bool:
        """Legacy repository transition; core worker must also enforce atomic state guards."""
        try:
            self.queue.update_job_outcome(job_id, state=new_state)
            self.reload_schedules(refresh_pages=False)
            return True
        except Exception as exc:
            logger.exception("Job transition failed: %s -> %s", job_id, new_state)
            QMessageBox.warning(self, "Thao tác thất bại", str(exc))
            return False

    def _handle_reconcile(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            return
        job = self.queue.get_job(job_id)
        if not job or job.get("state") != "unknown":
            QMessageBox.information(self, "Không áp dụng", "Chỉ đối chiếu bài có trạng thái Cần đối chiếu.")
            return
        if not self.recovery:
            QMessageBox.warning(self, "Chưa sẵn sàng", "Chưa kết nối bộ đối chiếu trạng thái.")
            return
        try:
            success, message = self.recovery.reconcile_job(job_id)
        except Exception as exc:
            logger.exception("Reconcile failed")
            QMessageBox.warning(self, "Lỗi đối chiếu", str(exc))
            return
        (QMessageBox.information if success else QMessageBox.warning)(
            self, "Kết quả đối chiếu", message
        )
        self.reload_schedules(refresh_pages=False)

    def _handle_pause_toggle(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            return
        job = self.queue.get_job(job_id)
        if not job or job.get("state") not in ("scheduled_local", "paused"):
            QMessageBox.information(self, "Không áp dụng", "Chỉ tạm dừng/tiếp tục lịch lưu trên máy.")
            return
        new_state = "paused" if job["state"] == "scheduled_local" else "scheduled_local"
        if new_state == "scheduled_local":
            when = _parse_vn(job.get("scheduled_at_utc"))
            if when is not None and when <= datetime.now(VN_TZ):
                QMessageBox.warning(
                    self, "Lịch đã quá giờ",
                    "Không thể tiếp tục lịch có thời điểm đăng trong quá khứ. "
                    "Cần đặt lại thời gian đăng từ chức năng soạn bài trước khi tiếp tục.",
                )
                return
        self._perform_transition(job_id, new_state)

    def _handle_retry_job(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            return
        job = self.queue.get_job(job_id)
        if not job or job.get("state") != "failed_retryable":
            QMessageBox.information(self, "Không áp dụng", "Chỉ cho phép thử lại lỗi có thể phục hồi.")
            return
        answer = QMessageBox.question(
            self, "Xác nhận thử lại",
            "Chỉ thử lại sau khi đã kiểm tra bài chưa được đăng trên Facebook, "
            "để tránh bài trùng. Bạn muốn tiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._perform_transition(job_id, "scheduled_local")

    def _handle_cancel_job(self) -> None:
        job_id = self._get_selected_job_id()
        if not job_id:
            return
        job = self.queue.get_job(job_id)
        if not job or job.get("state") not in ("scheduled_local", "paused", "queued"):
            QMessageBox.warning(
                self, "Không thể hủy tại đây",
                "Chỉ hủy lịch đang chờ trên máy. Nếu Facebook đã nhận lịch, "
                "cần hủy trên Facebook hoặc tích hợp API hủy lịch từ xa.",
            )
            return
        answer = QMessageBox.question(
            self, "Hủy lịch trên máy",
            "Hủy tác vụ trên máy tính? Hành động này không thu hồi bài đã gửi Facebook.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._perform_transition(job_id, "cancelled")

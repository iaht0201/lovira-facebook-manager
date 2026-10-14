"""
Lovira Workspace 2.0 — Video Workspace & Media Library (video_workspace.py)
Màn hình Làm việc Video & Thư viện Media 2.0 (Grid UX Refactor):
- Native PySide6 Desktop Dark Theme, không nhúng WebView
- Tab 1 (Tải video): Tải 1 link & Tải hàng loạt danh sách từ Douyin, TikTok, Bilibili
- Tab 2 (Thư viện media): Thumbnail Grid trực quan (QListView IconMode + QAbstractListModel + QStyledItemDelegate)
- Card 16:9 thumbnail, thời lượng, nguồn nền tảng, nút play, checkbox, tên đặt dưới ảnh, chip trạng thái
- Bộ lọc đa chiều: Tìm kiếm tức thời, Nền tảng, Trạng thái bài đăng, Sắp xếp, Chuyển đổi Lưới / Danh sách
- Contextual Toolbar ở đáy màn hình: Ẩn khi chưa chọn, hiện khi chọn >= 1 video
- Dropdown Fanpage đích popup đa chọn có ô tìm kiếm & kiểm tra quyền kết nối
- Soạn bài & Đặt lịch hàng loạt (N video x M Fanpage) với hộp thoại xác nhận chi tiết
- Bảo vệ an toàn tham chiếu AC-12 & AC-42 chặn xóa video đang có lịch chờ thực thi
- Phân biệt rõ giữa Bỏ khỏi thư viện (giữ file ổ đĩa) và Xóa vĩnh viễn trên ổ đĩa
- Tương thích ngược toàn diện với Route.MEDIA, Route.DOWNLOADS và các unit test
"""

import os
import re
import json
import uuid
import logging
import subprocess
import requests
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple

from PySide6.QtCore import (
    Qt,
    Signal,
    QThread,
    QUrl,
    QSize,
    QPoint,
    QRect,
    QRectF,
    QAbstractListModel,
    QModelIndex,
    QItemSelectionModel,
    QItemSelection,
    QDateTime,
    QDate,
    QTime,
    QEvent,
)
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QDesktopServices,
    QIcon,
    QPainterPath,
    QLinearGradient,
    QCursor,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QFrame,
    QMessageBox,
    QStackedLayout,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QAbstractItemView,
    QDialog,
    QScrollArea,
    QCheckBox,
    QMenu,
    QDateTimeEdit,
    QCalendarWidget,
    QSpinBox,
    QButtonGroup,
    QToolButton,
    QApplication,
)

from src.lovira.integrations.downloaders.video_downloader import (
    VideoDownloader,
    VideoMetadata,
    DownloadProgress,
)
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.media.processor import MediaProcessor
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.widgets.empty_state import EmptyState

logger = logging.getLogger(__name__)


def _detect_platform(url: str) -> str:
    """Xác định nền tảng nguồn từ URL video hoặc đoạn văn bản chia sẻ."""
    u = VideoDownloader.clean_url(url).lower()
    if "douyin" in u or "iesdouyin" in u:
        return "douyin"
    if "tiktok" in u:
        return "tiktok"
    if "bilibili" in u or "b23.tv" in u:
        return "bilibili"
    return "other"


# =========================================================================
# THUMBNAIL CACHE
# =========================================================================

class ThumbnailCache:
    """Bộ nhớ đệm hình ảnh thumbnail trong RAM giúp cuộn mượt mà không đọc đĩa liên tục."""

    _instance: Optional["ThumbnailCache"] = None

    def __init__(self, max_items: int = 400):
        self._cache: Dict[str, QPixmap] = {}
        self._max_items = max_items

    @classmethod
    def get_instance(cls) -> "ThumbnailCache":
        if cls._instance is None:
            cls._instance = ThumbnailCache()
        return cls._instance

    def get(self, key: str, path: Optional[str], target_w: int, target_h: int) -> Optional[QPixmap]:
        if not path:
            return None
        cache_key = f"{key}_{target_w}x{target_h}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not os.path.exists(path):
            return None

        try:
            pix = QPixmap(path)
            if not pix.isNull():
                scaled = pix.scaled(
                    target_w,
                    target_h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if len(self._cache) >= self._max_items:
                    # Dọn dẹp bớt 60 item cũ nhất
                    for k in list(self._cache.keys())[:60]:
                        self._cache.pop(k, None)
                self._cache[cache_key] = scaled
                return scaled
        except Exception as e:
            logger.debug(f"Lỗi đọc thumbnail {path}: {e}")
        return None


# =========================================================================
# WORKERS TẢI VIDEO
# =========================================================================

class VideoDownloadWorker(QThread):
    """Worker luồng riêng thực hiện tải 1 video tránh làm đơ giao diện."""

    progress_updated = Signal(dict)
    finished_success = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, downloader: VideoDownloader, url: str, output_dir: Path, platform: str = "other"):
        super().__init__()
        self.downloader = downloader
        self.url = url
        self.output_dir = output_dir
        self.platform = platform
        self._is_cancelled = False

    def run(self) -> None:
        def on_progress(p: DownloadProgress):
            speed_kb = (p.speed_bytes_sec / 1024) if p.speed_bytes_sec else 0
            self.progress_updated.emit({
                "percent": p.percent,
                "speed": f"{speed_kb:.1f} KB/s",
                "status": p.status,
            })

        try:
            self._is_cancelled = False
            saved_path = self.downloader.download(
                url=self.url,
                output_dir=self.output_dir,
                progress_callback=on_progress,
                is_cancelled=lambda: self._is_cancelled,
            )
            detected = _detect_platform(self.url)
            self.finished_success.emit({
                "file_path": str(saved_path),
                "title": Path(saved_path).stem,
                "platform": detected if detected != "other" else self.platform,
                "url": self.url,
            })
        except Exception as e:
            self.finished_error.emit(str(e))


class BatchDownloadWorker(QThread):
    """Worker tải hàng loạt danh sách video theo danh sách link."""

    progress_updated = Signal(int, int, str, int)  # current, total, url, percent
    item_downloaded = Signal(dict)
    finished_all = Signal(int, int)

    def __init__(self, downloader: VideoDownloader, urls: List[str], output_dir: Path):
        super().__init__()
        self.downloader = downloader
        self.urls = urls
        self.output_dir = output_dir
        self._is_cancelled = False

    def run(self) -> None:
        success = 0
        total = len(self.urls)

        for idx, url in enumerate(self.urls, start=1):
            if self._is_cancelled:
                break

            self.progress_updated.emit(idx, total, url, 0)

            def on_progress(p: DownloadProgress):
                self.progress_updated.emit(idx, total, url, p.percent)

            try:
                saved_path = self.downloader.download(
                    url=url,
                    output_dir=self.output_dir,
                    progress_callback=on_progress,
                    is_cancelled=lambda: self._is_cancelled,
                )
                success += 1
                detected = _detect_platform(url)
                self.item_downloaded.emit({
                    "url": url,
                    "file_path": str(saved_path),
                    "title": Path(saved_path).stem,
                    "platform": detected,
                })
            except Exception as e:
                logger.error(f"Lỗi tải link {url}: {e}")

        self.finished_all.emit(success, total)


# =========================================================================
# TAB 1: TẢI VIDEO (GIỮ NGUYÊN CHỨC NĂNG & NÂNG CẤP INGEST THUMBNAIL)
# =========================================================================

# =========================================================================
# MODEL & DELEGATE CHO DOWNLOAD TASK GRID VIEW (V2)
# =========================================================================

ROLE_TASK_ID = Qt.ItemDataRole.UserRole + 20
ROLE_TASK_URL = Qt.ItemDataRole.UserRole + 21
ROLE_TASK_TITLE = Qt.ItemDataRole.UserRole + 22
ROLE_TASK_PLATFORM = Qt.ItemDataRole.UserRole + 23
ROLE_TASK_THUMB_PATH = Qt.ItemDataRole.UserRole + 24
ROLE_TASK_DURATION_STR = Qt.ItemDataRole.UserRole + 25
ROLE_TASK_STATE = Qt.ItemDataRole.UserRole + 26
ROLE_TASK_PROGRESS = Qt.ItemDataRole.UserRole + 27
ROLE_TASK_SPEED = Qt.ItemDataRole.UserRole + 28
ROLE_TASK_ERROR = Qt.ItemDataRole.UserRole + 29
ROLE_TASK_IS_SELECTED = Qt.ItemDataRole.UserRole + 30
ROLE_RAW_TASK = Qt.ItemDataRole.UserRole + 31


@dataclass
class DownloadTask:
    task_id: str
    source_url: str
    normalized_url: str
    source_platform: str = "other"
    title: str = ""
    duration_sec: float = 0.0
    thumbnail_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    state: str = "READY"  # ANALYZING, READY, QUEUED, DOWNLOADING, PROCESSING, COMPLETED, FAILED, CANCELLED
    progress_percent: int = 0
    speed_text: str = ""
    local_file_path: Optional[str] = None
    media_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def duration_str(self) -> str:
        if not self.duration_sec or self.duration_sec <= 0:
            return "00:00"
        m, s = divmod(int(self.duration_sec), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


class DownloadTaskListModel(QAbstractListModel):
    """Model danh sách các tác vụ tải video phục vụ hiển thị Grid."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tasks: List[DownloadTask] = []
        self._filtered_tasks: List[DownloadTask] = []
        self._selected_ids: Set[str] = set()
        self._filter_key: str = "all"  # all, ready, downloading, completed, failed
        self._sort_key: str = "newest"  # newest, oldest, title, platform

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._filtered_tasks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._filtered_tasks)):
            return None

        task = self._filtered_tasks[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return task.title or task.source_url

        if role == ROLE_TASK_ID:
            return task.task_id

        if role == ROLE_TASK_URL:
            return task.source_url

        if role == ROLE_TASK_TITLE:
            return task.title or task.source_url

        if role == ROLE_TASK_PLATFORM:
            return task.source_platform.upper()

        if role == ROLE_TASK_THUMB_PATH:
            return task.thumbnail_path

        if role == ROLE_TASK_DURATION_STR:
            return task.duration_str

        if role == ROLE_TASK_STATE:
            return task.state

        if role == ROLE_TASK_PROGRESS:
            return task.progress_percent

        if role == ROLE_TASK_SPEED:
            return task.speed_text

        if role == ROLE_TASK_ERROR:
            return task.error_message

        if role == ROLE_TASK_IS_SELECTED:
            return task.task_id in self._selected_ids

        if role == ROLE_RAW_TASK:
            return task

        return None

    def add_task(self, task: DownloadTask) -> None:
        for idx, t in enumerate(self._tasks):
            if t.normalized_url == task.normalized_url:
                self._tasks[idx] = task
                self._apply_filter_and_sort()
                return
        self._tasks.insert(0, task)
        self._apply_filter_and_sort()

    def update_task(self, task_id: str, **kwargs) -> None:
        for t in self._tasks:
            if t.task_id == task_id:
                for k, v in kwargs.items():
                    if hasattr(t, k):
                        setattr(t, k, v)
                break
        self._apply_filter_and_sort()

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        for t in self._tasks:
            if t.task_id == task_id:
                return t
        return None

    def remove_task(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.task_id != task_id]
        self._selected_ids.discard(task_id)
        self._apply_filter_and_sort()

    def clear_all(self) -> None:
        self.beginResetModel()
        self._tasks.clear()
        self._filtered_tasks.clear()
        self._selected_ids.clear()
        self.endResetModel()

    def set_filter(self, filter_key: str) -> None:
        self._filter_key = filter_key
        self._apply_filter_and_sort()

    def set_sort(self, sort_key: str) -> None:
        self._sort_key = sort_key
        self._apply_filter_and_sort()

    def toggle_select(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if not task or task.state != "COMPLETED":
            return
        if task_id in self._selected_ids:
            self._selected_ids.remove(task_id)
        else:
            self._selected_ids.add(task_id)
        self._refresh_indexes()

    def select_all_completed(self) -> None:
        for t in self._filtered_tasks:
            if t.state == "COMPLETED":
                self._selected_ids.add(t.task_id)
        self._refresh_indexes()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        self._refresh_indexes()

    def get_selected_completed_tasks(self) -> List[DownloadTask]:
        return [t for t in self._tasks if t.task_id in self._selected_ids and t.state == "COMPLETED"]

    def counts_by_state(self) -> Dict[str, int]:
        counts = {"all": len(self._tasks), "ready": 0, "downloading": 0, "completed": 0, "failed": 0}
        for t in self._tasks:
            if t.state in ("READY", "QUEUED"):
                counts["ready"] += 1
            elif t.state in ("DOWNLOADING", "ANALYZING", "PROCESSING"):
                counts["downloading"] += 1
            elif t.state == "COMPLETED":
                counts["completed"] += 1
            elif t.state in ("FAILED", "META_FAILED"):
                counts["failed"] += 1
        return counts

    def _apply_filter_and_sort(self) -> None:
        self.beginResetModel()
        items = list(self._tasks)

        if self._filter_key == "ready":
            items = [t for t in items if t.state in ("READY", "QUEUED")]
        elif self._filter_key == "downloading":
            items = [t for t in items if t.state in ("DOWNLOADING", "ANALYZING", "PROCESSING")]
        elif self._filter_key == "completed":
            items = [t for t in items if t.state == "COMPLETED"]
        elif self._filter_key == "failed":
            items = [t for t in items if t.state in ("FAILED", "META_FAILED")]

        if self._sort_key == "newest":
            items.sort(key=lambda t: t.created_at, reverse=True)
        elif self._sort_key == "oldest":
            items.sort(key=lambda t: t.created_at)
        elif self._sort_key == "title":
            items.sort(key=lambda t: (t.title or "").lower())
        elif self._sort_key == "platform":
            items.sort(key=lambda t: (t.source_platform or "").lower())

        self._filtered_tasks = items
        self.endResetModel()

    def _refresh_indexes(self) -> None:
        if self._filtered_tasks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._filtered_tasks) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [ROLE_TASK_IS_SELECTED])


class DownloadCardDelegate(QStyledItemDelegate):
    """
    Delegate vẽ từng Card tiến trình tải video:
    - Kích thước ~224x252px, thumbnail 16:9 đồng nhất Media Library
    - Checkbox ở góc trên trái thumbnail cho các video hoàn tất
    - Badge thời lượng và platform chip trên thumbnail
    - Thanh progress bar và tốc độ tải bên trong card
    - Các nút tác vụ nhanh: Tải ngay, Hủy, Thử lại, Xem, Mở thư mục
    """

    checkbox_clicked = Signal(str)
    action_download = Signal(str)
    action_cancel = Signal(str)
    action_retry = Signal(str)
    action_view = Signal(str)
    action_folder = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.thumb_cache = ThumbnailCache.get_instance()
        self.card_size = QSize(224, 252)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return self.card_size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = option.rect.adjusted(4, 4, -4, -4)
        is_selected = index.data(ROLE_TASK_IS_SELECTED) or False
        is_hover = bool(option.state & option.state.State_MouseOver)
        state = index.data(ROLE_TASK_STATE) or "READY"

        # 1. Nền & viền Card
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(rect), 10, 10)

        if is_selected:
            bg_color = QColor("#18233C")
            border_color = QColor("#6258E8")
            border_width = 2.0
        elif is_hover:
            bg_color = QColor("#17243B")
            border_color = QColor("#2E4366")
            border_width = 1.0
        else:
            bg_color = QColor("#131D2E")
            border_color = QColor("#1E2D47")
            border_width = 1.0

        painter.fillPath(card_path, QBrush(bg_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawPath(card_path)

        # 2. Thumbnail 16:9
        pad = 8
        thumb_w = rect.width() - (pad * 2)
        thumb_h = int(thumb_w * 9 / 16)
        thumb_rect = QRect(rect.left() + pad, rect.top() + pad, thumb_w, thumb_h)

        thumb_path = QPainterPath()
        thumb_path.addRoundedRect(QRectF(thumb_rect), 6, 6)

        painter.save()
        painter.setClipPath(thumb_path)

        task_id = index.data(ROLE_TASK_ID) or ""
        t_path = index.data(ROLE_TASK_THUMB_PATH)
        pix = self.thumb_cache.get(task_id, t_path, thumb_w, thumb_h)

        if pix and not pix.isNull():
            src_x = (pix.width() - thumb_w) // 2
            src_y = (pix.height() - thumb_h) // 2
            painter.drawPixmap(thumb_rect.left(), thumb_rect.top(), pix, max(0, src_x), max(0, src_y), thumb_w, thumb_h)
        else:
            grad = QLinearGradient(thumb_rect.topLeft(), thumb_rect.bottomRight())
            grad.setColorAt(0.0, QColor("#0B111D"))
            grad.setColorAt(1.0, QColor("#162235"))
            painter.fillRect(thumb_rect, grad)

        # Biểu tượng trung tâm
        if state == "COMPLETED":
            play_size = 28
            play_rect = QRect(
                thumb_rect.center().x() - play_size // 2,
                thumb_rect.center().y() - play_size // 2,
                play_size,
                play_size,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 23, 42, 170))
            painter.drawEllipse(play_rect)

            triangle = QPainterPath()
            tx = play_rect.left() + 11
            ty = play_rect.top() + 8
            triangle.moveTo(tx, ty)
            triangle.lineTo(tx + 9, ty + 6)
            triangle.lineTo(tx, ty + 12)
            triangle.closeSubpath()
            painter.setBrush(QColor(241, 245, 249, 210))
            painter.drawPath(triangle)

        painter.restore()

        # 3. Checkbox góc trên trái (cho video COMPLETED hoặc khi đang hover)
        if state == "COMPLETED" or is_selected:
            chk_size = 18
            chk_rect = QRect(thumb_rect.left() + 6, thumb_rect.top() + 6, chk_size, chk_size)
            chk_path = QPainterPath()
            chk_path.addRoundedRect(QRectF(chk_rect), 4, 4)

            if is_selected:
                painter.fillPath(chk_path, QBrush(QColor("#6258E8")))
                painter.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                check_p = QPainterPath()
                check_p.moveTo(chk_rect.left() + 4.5, chk_rect.top() + 9.5)
                check_p.lineTo(chk_rect.left() + 7.5, chk_rect.top() + 13.0)
                check_p.lineTo(chk_rect.left() + 13.5, chk_rect.top() + 5.5)
                painter.drawPath(check_p)
            else:
                painter.fillPath(chk_path, QBrush(QColor(15, 23, 42, 180)))
                painter.setPen(QPen(QColor("#475569"), 1.2))
                painter.drawPath(chk_path)

        # 4. Thời lượng video ở góc trên phải
        dur_str = index.data(ROLE_TASK_DURATION_STR) or "00:00"
        font_badge = QFont(painter.font())
        font_badge.setPointSize(9)
        font_badge.setBold(True)
        painter.setFont(font_badge)

        fm = QFontMetrics(font_badge)
        dur_w = fm.horizontalAdvance(dur_str) + 10
        dur_rect = QRect(thumb_rect.right() - dur_w - 6, thumb_rect.top() + 6, dur_w, 18)

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(dur_rect), 4, 4)
        painter.fillPath(badge_path, QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(dur_rect, Qt.AlignmentFlag.AlignCenter, dur_str)

        # 5. Nhãn Nền tảng (Platform) ở góc dưới phải thumbnail
        platform_str = index.data(ROLE_TASK_PLATFORM) or "VIDEO"
        font_plat = QFont(painter.font())
        font_plat.setPointSize(8)
        font_plat.setBold(True)
        painter.setFont(font_plat)
        plat_fm = QFontMetrics(font_plat)
        plat_w = plat_fm.horizontalAdvance(platform_str) + 8
        plat_rect = QRect(thumb_rect.right() - plat_w - 6, thumb_rect.bottom() - 18 - 4, plat_w, 16)

        pbadge = QPainterPath()
        pbadge.addRoundedRect(QRectF(plat_rect), 3, 3)
        painter.fillPath(pbadge, QBrush(QColor(0, 0, 0, 160)))
        painter.setPen(QColor("#CBD5E1"))
        painter.drawText(plat_rect, Qt.AlignmentFlag.AlignCenter, platform_str)

        # 6. Tiêu đề video dưới thumbnail
        content_top = thumb_rect.bottom() + 6
        title_str = index.data(ROLE_TASK_TITLE) or "Video không tên"
        font_title = QFont(painter.font())
        font_title.setPointSize(10)
        font_title.setBold(True)
        painter.setFont(font_title)
        painter.setPen(QColor("#F1F5F9"))

        title_rect = QRect(rect.left() + pad, content_top, rect.width() - (pad * 2), 32)
        fm_title = QFontMetrics(font_title)
        elided_title = fm_title.elidedText(title_str, Qt.TextElideMode.ElideRight, title_rect.width() * 2)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, elided_title)

        # 7. Trạng thái & Thanh Progress
        progress_val = index.data(ROLE_TASK_PROGRESS) or 0
        speed_str = index.data(ROLE_TASK_SPEED) or ""
        font_sub = QFont(painter.font())
        font_sub.setPointSize(9)
        painter.setFont(font_sub)

        status_y = content_top + 36
        if state == "DOWNLOADING":
            # Thanh progress mỏng
            p_bar_rect = QRect(rect.left() + pad, status_y, rect.width() - (pad * 2), 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1E2D47"))
            painter.drawRoundedRect(p_bar_rect, 2, 2)

            fill_w = max(4, int(p_bar_rect.width() * (progress_val / 100.0)))
            fill_rect = QRect(p_bar_rect.left(), p_bar_rect.top(), fill_w, p_bar_rect.height())
            painter.setBrush(QColor("#6258E8"))
            painter.drawRoundedRect(fill_rect, 2, 2)

            painter.setPen(QColor("#60A5FA"))
            txt_rect = QRect(rect.left() + pad, status_y + 6, rect.width() - (pad * 2), 16)
            s_label = f"Đang tải {progress_val}%"
            if speed_str:
                s_label += f" • {speed_str}"
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, s_label)
        elif state == "ANALYZING":
            painter.setPen(QColor("#FBBF24"))
            txt_rect = QRect(rect.left() + pad, status_y + 4, rect.width() - (pad * 2), 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "⏳ Đang phân tích...")
        elif state == "READY":
            painter.setPen(QColor("#818CF8"))
            txt_rect = QRect(rect.left() + pad, status_y + 4, rect.width() - (pad * 2), 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, " Sẵn sàng tải")
        elif state == "QUEUED":
            painter.setPen(QColor("#94A3B8"))
            txt_rect = QRect(rect.left() + pad, status_y + 4, rect.width() - (pad * 2), 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "⌛ Đang chờ tải...")
        elif state == "PROCESSING":
            painter.setPen(QColor("#38BDF8"))
            txt_rect = QRect(rect.left() + pad, status_y + 4, rect.width() - (pad * 2), 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "⚙ Đang trích xuất & lưu...")
        elif state == "COMPLETED":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#10B981"))
            painter.drawEllipse(rect.left() + pad + 2, status_y + 8, 7, 7)
            painter.setPen(QColor("#34D399"))
            txt_rect = QRect(rect.left() + pad + 14, status_y + 4, rect.width() - (pad * 2) - 14, 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✓ Hoàn tất")
        elif state in ("FAILED", "META_FAILED"):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#EF4444"))
            painter.drawEllipse(rect.left() + pad + 2, status_y + 8, 7, 7)
            painter.setPen(QColor("#F87171"))
            txt_rect = QRect(rect.left() + pad + 14, status_y + 4, rect.width() - (pad * 2) - 14, 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✕ Lỗi tải video")
        else:
            painter.setPen(QColor("#94A3B8"))
            txt_rect = QRect(rect.left() + pad, status_y + 4, rect.width() - (pad * 2), 16)
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "⊘ Đã hủy")

        # 8. Action button ở đáy Card
        btn_y = rect.bottom() - 26
        btn_h = 22
        font_btn = QFont(painter.font())
        font_btn.setPointSize(8)
        font_btn.setBold(True)
        painter.setFont(font_btn)

        if state == "READY":
            b_rect = QRect(rect.left() + pad, btn_y, rect.width() - (pad * 2), btn_h)
            b_path = QPainterPath()
            b_path.addRoundedRect(QRectF(b_rect), 4, 4)
            painter.fillPath(b_path, QBrush(QColor("#6258E8")))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, "⬇ Bắt đầu tải")
        elif state in ("DOWNLOADING", "QUEUED"):
            b_rect = QRect(rect.left() + pad, btn_y, rect.width() - (pad * 2), btn_h)
            b_path = QPainterPath()
            b_path.addRoundedRect(QRectF(b_rect), 4, 4)
            painter.fillPath(b_path, QBrush(QColor("#334155")))
            painter.setPen(QColor("#F1F5F9"))
            painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, "✕ Hủy tải")
        elif state in ("FAILED", "META_FAILED"):
            b_rect = QRect(rect.left() + pad, btn_y, rect.width() - (pad * 2), btn_h)
            b_path = QPainterPath()
            b_path.addRoundedRect(QRectF(b_rect), 4, 4)
            painter.fillPath(b_path, QBrush(QColor("#3F1D24")))
            painter.setPen(QColor("#F87171"))
            painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, "↻ Thử lại")
        elif state == "COMPLETED":
            w1 = 70
            w2 = 90
            b1_rect = QRect(rect.left() + pad, btn_y, w1, btn_h)
            b2_rect = QRect(rect.left() + pad + w1 + 8, btn_y, w2, btn_h)

            p1 = QPainterPath()
            p1.addRoundedRect(QRectF(b1_rect), 4, 4)
            painter.fillPath(p1, QBrush(QColor("#1E293B")))
            painter.setPen(QColor("#E2E8F0"))
            painter.drawText(b1_rect, Qt.AlignmentFlag.AlignCenter, "▶ Xem")

            p2 = QPainterPath()
            p2.addRoundedRect(QRectF(b2_rect), 4, 4)
            painter.fillPath(p2, QBrush(QColor("#1E293B")))
            painter.setPen(QColor("#CBD5E1"))
            painter.drawText(b2_rect, Qt.AlignmentFlag.AlignCenter, "📁 Thư mục")

        painter.restore()

    def editorEvent(self, event: QEvent, model: QAbstractListModel, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            pos = event.pos()
            rect = option.rect.adjusted(4, 4, -4, -4)
            pad = 8
            task_id = index.data(ROLE_TASK_ID) or ""
            state = index.data(ROLE_TASK_STATE) or "READY"

            thumb_w = rect.width() - (pad * 2)
            thumb_h = int(thumb_w * 9 / 16)
            thumb_rect = QRect(rect.left() + pad, rect.top() + pad, thumb_w, thumb_h)

            # Checkbox hit-test
            chk_rect = QRect(thumb_rect.left() + 2, thumb_rect.top() + 2, 26, 26)
            if chk_rect.contains(pos) and state == "COMPLETED":
                self.checkbox_clicked.emit(task_id)
                return True

            # Action button hit-test
            btn_y = rect.bottom() - 26
            btn_h = 22
            btn_full = QRect(rect.left() + pad, btn_y, rect.width() - (pad * 2), btn_h)

            if state == "READY" and btn_full.contains(pos):
                self.action_download.emit(task_id)
                return True
            elif state in ("DOWNLOADING", "QUEUED") and btn_full.contains(pos):
                self.action_cancel.emit(task_id)
                return True
            elif state in ("FAILED", "META_FAILED") and btn_full.contains(pos):
                self.action_retry.emit(task_id)
                return True
            elif state == "COMPLETED":
                w1 = 70
                w2 = 90
                b1_rect = QRect(rect.left() + pad, btn_y, w1, btn_h)
                b2_rect = QRect(rect.left() + pad + w1 + 8, btn_y, w2, btn_h)

                if b1_rect.contains(pos) or thumb_rect.contains(pos):
                    self.action_view.emit(task_id)
                    return True
                elif b2_rect.contains(pos):
                    self.action_folder.emit(task_id)
                    return True

        return super().editorEvent(event, model, option, index)


class DownloadGridView(QListView):
    """QListView IconMode tùy biến cho Download Task Grid."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(12)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QListView {
                background-color: transparent;
                border: none;
                outline: none;
                padding: 4px;
            }
            QListView::item {
                border: none;
                background: transparent;
            }
        """)


class MetadataWorker(QThread):
    """Worker luồng riêng lấy metadata video tránh làm treo GUI."""

    metadata_ready = Signal(str, dict)
    metadata_error = Signal(str, str)

    def __init__(self, downloader: VideoDownloader, task_id: str, url: str):
        super().__init__()
        self.downloader = downloader
        self.task_id = task_id
        self.url = url

    def run(self) -> None:
        try:
            meta = self.downloader.extract_metadata(self.url)
            if not meta:
                self.metadata_error.emit(self.task_id, "Không thể lấy thông tin video. Vui lòng kiểm tra lại đường link.")
                return

            thumb_local_path = None
            if meta.thumbnail_url:
                try:
                    resp = requests.get(meta.thumbnail_url, timeout=5)
                    if resp.status_code == 200:
                        temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "lovira_thumbs"
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        t_file = temp_dir / f"meta_{self.task_id}.jpg"
                        t_file.write_bytes(resp.content)
                        thumb_local_path = str(t_file)
                except Exception as ex:
                    logger.debug(f"Không thể tải thumbnail từ URL: {ex}")

            platform_str = meta.source_platform.value.lower() if meta.source_platform else _detect_platform(self.url)
            self.metadata_ready.emit(self.task_id, {
                "title": meta.title or "Video không tên",
                "duration": meta.duration or 0.0,
                "uploader": meta.uploader or "",
                "thumbnail_url": meta.thumbnail_url,
                "thumbnail_path": thumb_local_path,
                "platform": platform_str,
            })
        except Exception as e:
            self.metadata_error.emit(self.task_id, str(e))


class SingleTaskDownloadWorker(QThread):
    """Worker luồng riêng tải 1 video cụ thể theo task_id."""

    progress_updated = Signal(str, int, str)
    finished_success = Signal(str, str, str)
    finished_error = Signal(str, str)

    def __init__(self, downloader: VideoDownloader, task_id: str, url: str, output_dir: Path):
        super().__init__()
        self.downloader = downloader
        self.task_id = task_id
        self.url = url
        self.output_dir = output_dir
        self._is_cancelled = False

    def run(self) -> None:
        def on_progress(p: DownloadProgress):
            speed_kb = (p.speed_bytes_sec / 1024) if p.speed_bytes_sec else 0
            if speed_kb >= 1024:
                speed_str = f"{speed_kb / 1024:.1f} MB/s"
            else:
                speed_str = f"{speed_kb:.0f} KB/s"
            self.progress_updated.emit(self.task_id, int(p.percent), speed_str)

        try:
            self._is_cancelled = False
            saved_path = self.downloader.download(
                url=self.url,
                output_dir=self.output_dir,
                progress_callback=on_progress,
                is_cancelled=lambda: self._is_cancelled,
            )
            detected = _detect_platform(self.url)
            self.finished_success.emit(self.task_id, str(saved_path), detected)
        except Exception as e:
            if self._is_cancelled:
                self.finished_error.emit(self.task_id, "Đã hủy bởi người dùng")
            else:
                self.finished_error.emit(self.task_id, str(e))


# =========================================================================
# TAB 1: TẢI VIDEO 2.0 (UNIFIED INTAKE & TASK GRID UX REFACTOR)
# =========================================================================

class VideoDownloadTab(QWidget):
    """
    Tab Tải Video 2.0 (Download Grid UX Refactor):
    - 1 Đầu vào link duy nhất (LinkIntakePanel) dán 1 hoặc N link
    - Grid tác vụ trực quan (Thumbnail 16:9, progress bar trong card, status chip)
    - Concurrency giới hạn 2-3 tác vụ chạy đồng thời
    - Metadata chạy background ngoài GUI thread
    - Bulk selection video hoàn tất, chọn Fanpage đích & chuyển sang Soạn bài / Đặt lịch
    - Tương thích ngược toàn diện với test suite
    """

    send_to_composer = Signal(dict)
    media_downloaded = Signal()
    batch_schedule_created = Signal(list)

    def __init__(
        self,
        downloader: VideoDownloader,
        media_repo: MediaRepository,
        media_processor: MediaProcessor,
        download_dir: Path,
        page_repo: Optional[Any] = None,
        queue_repo: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.downloader = downloader
        self.media_repo = media_repo
        self.media_processor = media_processor
        self.download_dir = download_dir
        self.page_repo = page_repo
        self.queue_repo = queue_repo

        # Quản lý Worker & Queue
        self.download_queue: List[str] = []
        self.active_workers: Dict[str, SingleTaskDownloadWorker] = {}
        self.metadata_workers: Dict[str, MetadataWorker] = {}
        self.max_concurrent_downloads: int = 2
        self.selected_fanpage_ids: Set[str] = set()

        # Tương thích ngược
        self.current_worker: Optional[VideoDownloadWorker] = None
        self.batch_worker: Optional[BatchDownloadWorker] = None
        self.last_downloaded_data: Optional[Dict[str, Any]] = None
        self._inspected_platform: str = "other"

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 1. Header Tiêu đề
        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        title_lbl = QLabel("TẢI VIDEO DOUYIN / TIKTOK / BILIBILI")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #F3F6FC;")
        sub_lbl = QLabel("TikTok · Douyin · Bilibili — Dán một hoặc nhiều liên kết để tải video chất lượng cao không watermark")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        header_box.addWidget(title_lbl)
        header_box.addWidget(sub_lbl)
        main_layout.addLayout(header_box)

        # 2. Link Intake Panel (Hợp nhất 1 & N link)
        intake_frame = QFrame()
        intake_frame.setObjectName("cardFrame")
        intake_frame.setStyleSheet("""
            QFrame#cardFrame {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 8px;
            }
        """)
        intake_layout = QVBoxLayout(intake_frame)
        intake_layout.setContentsMargins(14, 12, 14, 12)
        intake_layout.setSpacing(8)

        lbl_intake_title = QLabel("🔗 LIÊN KẾT VIDEO CẦN TẢI")
        lbl_intake_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        intake_layout.addWidget(lbl_intake_title)

        self.link_text_edit = QTextEdit()
        self.link_text_edit.setPlaceholderText(
            "Dán liên kết video TikTok, Douyin hoặc Bilibili vào đây...\n"
            "Hỗ trợ dán 1 link hoặc nhiều link (mỗi dòng 1 link hoặc link kèm văn bản chia sẻ)"
        )
        self.link_text_edit.setFixedHeight(72)
        self.link_text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0B111D;
                border: 1px solid #24344D;
                border-radius: 6px;
                color: #F1F5F9;
                font-size: 12px;
                padding: 6px 8px;
            }
            QTextEdit:focus {
                border: 1px solid #6258E8;
            }
        """)
        self.link_text_edit.textChanged.connect(self._on_intake_text_changed)
        intake_layout.addWidget(self.link_text_edit)

        intake_action_row = QHBoxLayout()
        intake_action_row.setSpacing(10)

        self.lbl_intake_summary = QLabel("Chưa có liên kết nào.")
        self.lbl_intake_summary.setStyleSheet("color: #64748B; font-size: 12px;")
        intake_action_row.addWidget(self.lbl_intake_summary)
        intake_action_row.addStretch()

        self.btn_clear_input = QPushButton("✕ Xóa ô nhập")
        self.btn_clear_input.setFixedHeight(32)
        self.btn_clear_input.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #FFFFFF;
            }
        """)
        self.btn_clear_input.clicked.connect(self._clear_input)
        intake_action_row.addWidget(self.btn_clear_input)

        self.btn_analyze_links = QPushButton("🔍 Phân tích link")
        self.btn_analyze_links.setFixedHeight(34)
        self.btn_analyze_links.setStyleSheet("""
            QPushButton {
                background-color: #6258E8;
                border: none;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #5346E0;
            }
            QPushButton:disabled {
                background-color: #2D3748;
                color: #718096;
            }
        """)
        self.btn_analyze_links.clicked.connect(self._analyze_input_links)
        intake_action_row.addWidget(self.btn_analyze_links)

        intake_layout.addLayout(intake_action_row)
        main_layout.addWidget(intake_frame)

        # 3. Queue Controls & Filters Header
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self.lbl_queue_heading = QLabel("Danh sách tải xuống • 0 video")
        self.lbl_queue_heading.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9;")
        ctrl_row.addWidget(self.lbl_queue_heading)

        ctrl_row.addSpacing(8)

        # Filter Segment Chips
        self.filter_btn_group = QButtonGroup(self)
        self.btn_f_all = self._create_filter_button("Tất cả (0)", "all", True)
        self.btn_f_ready = self._create_filter_button("Chờ tải (0)", "ready", False)
        self.btn_f_down = self._create_filter_button("Đang tải (0)", "downloading", False)
        self.btn_f_comp = self._create_filter_button("Hoàn tất (0)", "completed", False)
        self.btn_f_fail = self._create_filter_button("Lỗi (0)", "failed", False)

        for btn in [self.btn_f_all, self.btn_f_ready, self.btn_f_down, self.btn_f_comp, self.btn_f_fail]:
            ctrl_row.addWidget(btn)

        ctrl_row.addStretch()

        # Sort combo
        self.cb_sort = QComboBox()
        self.cb_sort.setFixedHeight(32)
        self.cb_sort.addItems(["Mới nhất", "Cũ nhất", "Tiêu đề", "Nền tảng"])
        self.cb_sort.setStyleSheet("""
            QComboBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 12px;
                padding: 0 10px;
            }
        """)
        self.cb_sort.currentIndexChanged.connect(self._on_sort_changed)
        ctrl_row.addWidget(self.cb_sort)

        self.btn_download_all = QPushButton("▶ Tải tất cả")
        self.btn_download_all.setFixedHeight(34)
        self.btn_download_all.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                border: none;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #64748B;
            }
        """)
        self.btn_download_all.clicked.connect(self._start_download_all)
        ctrl_row.addWidget(self.btn_download_all)

        self.btn_select_completed_quick = QPushButton("☑ Chọn video đã tải")
        self.btn_select_completed_quick.setFixedHeight(32)
        self.btn_select_completed_quick.setStyleSheet("""
            QPushButton {
                background-color: #17243B;
                border: 1px solid #2B3D59;
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #24354F;
                color: #FFFFFF;
                border-color: #6258E8;
            }
        """)
        self.btn_select_completed_quick.clicked.connect(self._select_all_completed)
        ctrl_row.addWidget(self.btn_select_completed_quick)

        self.btn_clear_queue = QPushButton("✕ Xóa danh sách")
        self.btn_clear_queue.setFixedHeight(32)
        self.btn_clear_queue.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #94A3B8;
                font-size: 12px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #EF4444;
                color: #FFFFFF;
                border-color: #EF4444;
            }
        """)
        self.btn_clear_queue.clicked.connect(self._clear_queue)
        ctrl_row.addWidget(self.btn_clear_queue)

        main_layout.addLayout(ctrl_row)

        # 4. Vùng Task Grid View (QStackedLayout giữa Grid và EmptyState)
        self.content_stack = QStackedLayout()

        # Model & Delegate
        self.model = DownloadTaskListModel(self)
        self.delegate = DownloadCardDelegate(self)
        self.delegate.checkbox_clicked.connect(self._on_card_checkbox_clicked)
        self.delegate.action_download.connect(self._start_download_task)
        self.delegate.action_cancel.connect(self._cancel_download_task)
        self.delegate.action_retry.connect(self._retry_task)
        self.delegate.action_view.connect(self._watch_task)
        self.delegate.action_folder.connect(self._open_task_folder)

        self.grid_view = DownloadGridView(self)
        self.grid_view.setModel(self.model)
        self.grid_view.setItemDelegate(self.delegate)
        self.content_stack.addWidget(self.grid_view)

        self.empty_state = EmptyState(
            title="Chưa có video nào trong danh sách",
            description="Dán liên kết TikTok, Douyin hoặc Bilibili vào ô trên và bấm 'Phân tích link' để bắt đầu.",
            icon_name="downloads",
        )
        self.content_stack.addWidget(self.empty_state)
        main_layout.addLayout(self.content_stack, stretch=1)

        # 5. Contextual Bottom Bar (Bulk Selection)
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("bottomBar")
        self.bottom_bar.setFixedHeight(50)
        self.bottom_bar.setStyleSheet("""
            QFrame#bottomBar {
                background-color: #0E1726;
                border: 1px solid #2A3C58;
                border-radius: 8px;
            }
        """)
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(16, 8, 16, 8)
        bottom_layout.setSpacing(12)

        self.lbl_selected_summary = QLabel("☑ 0 video hoàn tất được chọn")
        self.lbl_selected_summary.setStyleSheet("font-size: 12px; font-weight: 700; color: #F1F5F9;")
        bottom_layout.addWidget(self.lbl_selected_summary)

        self.btn_select_all_completed = QPushButton("Chọn tất cả video")
        self.btn_select_all_completed.setFixedHeight(30)
        self.btn_select_all_completed.setStyleSheet("""
            QPushButton {
                background-color: #17243B;
                border: 1px solid #2B3D59;
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #24354F;
                color: #FFFFFF;
                border-color: #6258E8;
            }
        """)
        self.btn_select_all_completed.clicked.connect(self._select_all_completed)
        bottom_layout.addWidget(self.btn_select_all_completed)

        bottom_layout.addStretch()

        self.btn_select_fanpage = QPushButton("Fanpage đích ▾")
        self.btn_select_fanpage.setFixedHeight(34)
        self.btn_select_fanpage.setStyleSheet("""
            QPushButton {
                background-color: #131D2E;
                border: 1px solid #2B3D59;
                border-radius: 6px;
                color: #F1F5F9;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                border-color: #6258E8;
            }
        """)
        self.btn_select_fanpage.clicked.connect(self._open_fanpage_picker)
        bottom_layout.addWidget(self.btn_select_fanpage)

        self.btn_bulk_compose = QPushButton("🎬 Soạn bài")
        self.btn_bulk_compose.setFixedHeight(34)
        self.btn_bulk_compose.setStyleSheet("""
            QPushButton {
                background-color: #6258E8;
                border: none;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #5346E0;
            }
        """)
        self.btn_bulk_compose.clicked.connect(self._on_bulk_compose)
        bottom_layout.addWidget(self.btn_bulk_compose)

        self.btn_bulk_schedule = QPushButton("📅 Đặt lịch")
        self.btn_bulk_schedule.setFixedHeight(34)
        self.btn_bulk_schedule.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                border: none;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_bulk_schedule.clicked.connect(self._on_bulk_schedule)
        bottom_layout.addWidget(self.btn_bulk_schedule)

        self.btn_clear_selection = QPushButton("✕ Bỏ chọn")
        self.btn_clear_selection.setFixedHeight(32)
        self.btn_clear_selection.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #94A3B8;
                font-size: 12px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #1E293B;
                color: #FFFFFF;
            }
        """)
        self.btn_clear_selection.clicked.connect(self._clear_selection)
        bottom_layout.addWidget(self.btn_clear_selection)

        self.bottom_bar.setVisible(False)
        main_layout.addWidget(self.bottom_bar)

        # 6. Các Widget tương thích ngược (đảm bảo unit test không lỗi)
        self._init_backward_compatibility_widgets()
        self._update_ui_state()

    def _create_filter_button(self, text: str, filter_key: str, is_active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setCheckable(True)
        btn.setChecked(is_active)
        btn.setProperty("filter_key", filter_key)
        self._style_filter_button(btn, is_active)
        btn.clicked.connect(lambda: self._on_filter_button_clicked(btn, filter_key))
        self.filter_btn_group.addButton(btn)
        return btn

    def _style_filter_button(self, btn: QPushButton, is_active: bool) -> None:
        if is_active:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #6258E8;
                    border: none;
                    border-radius: 6px;
                    color: #FFFFFF;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0 10px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #131D2E;
                    border: 1px solid #1E2D47;
                    border-radius: 6px;
                    color: #94A3B8;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background-color: #1E293B;
                    color: #F1F5F9;
                }
            """)

    def _init_backward_compatibility_widgets(self) -> None:
        self.url_input = QLineEdit()
        self.btn_inspect = QPushButton(" Lấy thông tin")
        self.btn_inspect.clicked.connect(self._inspect_video)

        self.lbl_meta_title = QLabel("Tiêu đề: —")
        self.lbl_meta_platform = QLabel("Nền tảng: —")
        self.lbl_meta_author = QLabel("Tác giả: —")
        self.lbl_meta_duration = QLabel("Thời lượng: —")
        self.thumb_label = QLabel()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.lbl_progress_status = QLabel("Trạng thái: Sẵn sàng")

        self.btn_download = QPushButton("⬇ Bắt đầu tải video")
        self.btn_download.clicked.connect(self._start_download)
        self.btn_cancel = QPushButton("✖ Hủy tải")
        self.btn_cancel.clicked.connect(self._cancel_download)
        self.btn_watch_downloaded = QPushButton("▶ Xem video")
        self.btn_watch_downloaded.clicked.connect(self._watch_last_downloaded)
        self.btn_open_folder = QPushButton("📁 Mở thư mục")
        self.btn_open_folder.clicked.connect(self._open_download_folder)
        self.btn_compose_now = QPushButton("🎬 Soạn bài & Đặt lịch ngay")
        self.btn_compose_now.setVisible(False)
        self.btn_compose_now.clicked.connect(self._on_compose_now_clicked)

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setVisible(False)
        self.table_batch_results = QTableWidget()
        self.table_batch_results.setVisible(False)
        self.batch_text_edit = QTextEdit()
        self.batch_text_edit.setVisible(False)
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        self.lbl_batch_status = QLabel("Sẵn sàng tải hàng loạt.")
        self.btn_start_batch = QPushButton("🚀 Bắt đầu Tải hàng loạt")
        self.btn_cancel_batch = QPushButton("✖ Dừng tải hàng loạt")

    # --- INTAKE & PARSING LOGIC ---
    def _extract_urls(self, text: str) -> List[str]:
        urls: List[str] = []
        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            clean = VideoDownloader.clean_url(line_str)
            if clean and (clean.startswith("http://") or clean.startswith("https://")):
                if clean not in urls:
                    urls.append(clean)
        return urls

    def _on_intake_text_changed(self) -> None:
        raw = self.link_text_edit.toPlainText().strip()
        if not raw:
            self.lbl_intake_summary.setText("Chưa có liên kết nào.")
            self.lbl_intake_summary.setStyleSheet("color: #64748B; font-size: 12px;")
            return
        urls = self._extract_urls(raw)
        valid = [u for u in urls if _detect_platform(u) != "other" or "http" in u]
        self.lbl_intake_summary.setText(f"💡 Phát hiện {len(valid)} liên kết hợp lệ.")
        self.lbl_intake_summary.setStyleSheet("color: #38BDF8; font-size: 12px;")

    def _clear_input(self) -> None:
        self.link_text_edit.clear()
        self.lbl_intake_summary.setText("Đã xóa nội dung ô nhập.")
        self.lbl_intake_summary.setStyleSheet("color: #64748B; font-size: 12px;")

    def _analyze_input_links(self) -> None:
        raw = self.link_text_edit.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, "Thiếu liên kết", "Vui lòng dán ít nhất 1 liên kết video vào ô nhập.")
            return

        urls = self._extract_urls(raw)
        if not urls:
            QMessageBox.warning(self, "Không tìm thấy link", "Không nhận diện được liên kết video hợp lệ nào.")
            return

        added_count = 0
        for u in urls:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            detected = _detect_platform(u)
            task = DownloadTask(
                task_id=task_id,
                source_url=u,
                normalized_url=u,
                source_platform=detected,
                title="Đang lấy thông tin...",
                state="ANALYZING",
            )
            self.model.add_task(task)
            added_count += 1

            # Khởi tạo Worker phân tích metadata
            w = MetadataWorker(self.downloader, task_id, u)
            w.metadata_ready.connect(self._on_metadata_ready)
            w.metadata_error.connect(self._on_metadata_error)
            self.metadata_workers[task_id] = w
            w.start()

        self._update_ui_state()

    def _on_metadata_ready(self, task_id: str, meta: dict) -> None:
        worker = self.metadata_workers.pop(task_id, None)
        if worker:
            worker.wait(100)
        self.model.update_task(
            task_id,
            title=meta.get("title", "Video không tên"),
            duration_sec=meta.get("duration", 0.0),
            source_platform=meta.get("platform", "other"),
            thumbnail_url=meta.get("thumbnail_url"),
            thumbnail_path=meta.get("thumbnail_path"),
            state="READY",
        )
        self._update_ui_state()

    def _on_metadata_error(self, task_id: str, err: str) -> None:
        worker = self.metadata_workers.pop(task_id, None)
        if worker:
            worker.wait(100)
        self.model.update_task(
            task_id,
            state="META_FAILED",
            error_message=err,
            title="Không thể lấy thông tin",
        )
        self._update_ui_state()

    # --- QUEUE & DOWNLOAD CONTROLLER ---
    def _start_download_task(self, task_id: str) -> None:
        task = self.model.get_task(task_id)
        if not task:
            return

        if task.state == "DOWNLOADING" or task_id in self.active_workers:
            return

        self.model.update_task(task_id, state="QUEUED", progress_percent=0, speed_text="")
        if task_id not in self.download_queue:
            self.download_queue.append(task_id)

        self._pump_queue()
        self._update_ui_state()

    def _start_download_all(self) -> None:
        tasks_to_start = [t for t in self.model._tasks if t.state in ("READY", "FAILED", "META_FAILED", "CANCELLED")]
        if not tasks_to_start:
            return
        for t in tasks_to_start:
            self._start_download_task(t.task_id)

    def _cancel_download_task(self, task_id: str) -> None:
        if task_id in self.active_workers:
            worker = self.active_workers.pop(task_id)
            worker._is_cancelled = True
        if task_id in self.download_queue:
            self.download_queue.remove(task_id)

        self.model.update_task(task_id, state="CANCELLED", speed_text="")
        self._pump_queue()
        self._update_ui_state()

    def _retry_task(self, task_id: str) -> None:
        task = self.model.get_task(task_id)
        if not task:
            return
        if task.state == "META_FAILED":
            self.model.update_task(task_id, state="ANALYZING")
            w = MetadataWorker(self.downloader, task_id, task.source_url)
            w.metadata_ready.connect(self._on_metadata_ready)
            w.metadata_error.connect(self._on_metadata_error)
            self.metadata_workers[task_id] = w
            w.start()
        else:
            self._start_download_task(task_id)

    def _pump_queue(self) -> None:
        while len(self.active_workers) < self.max_concurrent_downloads and self.download_queue:
            next_id = self.download_queue.pop(0)
            task = self.model.get_task(next_id)
            if not task or task.state != "QUEUED":
                continue

            self.model.update_task(next_id, state="DOWNLOADING", progress_percent=0, speed_text="0 KB/s")
            w = SingleTaskDownloadWorker(self.downloader, next_id, task.source_url, self.download_dir)
            w.progress_updated.connect(self._on_worker_progress)
            w.finished_success.connect(self._on_worker_success)
            w.finished_error.connect(self._on_worker_error)
            self.active_workers[next_id] = w
            w.start()

    def _on_worker_progress(self, task_id: str, percent: int, speed: str) -> None:
        self.model.update_task(task_id, progress_percent=percent, speed_text=speed)

    def _on_worker_success(self, task_id: str, file_path: str, detected_platform: str) -> None:
        worker = self.active_workers.pop(task_id, None)
        if worker:
            worker.wait(100)
        task = self.model.get_task(task_id)
        if not task:
            self._pump_queue()
            return

        self.model.update_task(task_id, state="PROCESSING", progress_percent=100, speed_text="")

        thumb_path = Path(file_path).with_suffix(".thumb.jpg")
        try:
            self.media_processor.extract_thumbnail(Path(file_path), thumb_path, timestamp_sec=3.0)
        except Exception as e:
            logger.debug(f"Không thể trích xuất thumbnail: {e}")

        media_id = None
        try:
            probe = self.media_processor.inspect_video(Path(file_path))
            checksum = self.media_processor.calculate_sha256(Path(file_path))
            platform_final = detected_platform if detected_platform != "other" else task.source_platform
            
            raw_title = task.title or ""
            found_hashtags = re.findall(r"#\S+", raw_title)
            hashtags_str = " ".join(found_hashtags)
            clean_title = re.sub(r"#\S+", "", raw_title).strip() or raw_title

            media_id = self.media_repo.add_media_asset(
                local_path=Path(file_path),
                checksum=checksum,
                size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                duration=probe.duration if probe else task.duration_sec,
                source_platform=platform_final,
                source_url=task.source_url,
                width=probe.width if probe else 0,
                height=probe.height if probe else 0,
                thumbnail_path=thumb_path if thumb_path.exists() else None,
                tags=raw_title,
                title=clean_title,
                hashtags=hashtags_str,
            )
        except Exception as e:
            logger.error(f"Lỗi khi thêm media asset: {e}")

        self.model.update_task(
            task_id,
            state="COMPLETED",
            local_file_path=file_path,
            media_id=media_id,
            thumbnail_path=str(thumb_path) if thumb_path.exists() else task.thumbnail_path,
            progress_percent=100,
            speed_text="",
        )

        self.last_downloaded_data = {
            "file_path": file_path,
            "title": task.title,
            "platform": detected_platform,
            "media_id": media_id,
            "url": task.source_url,
        }
        self.media_downloaded.emit()
        self._pump_queue()
        self._update_ui_state()

    def _on_worker_error(self, task_id: str, err: str) -> None:
        worker = self.active_workers.pop(task_id, None)
        if worker:
            worker.wait(100)
        self.model.update_task(task_id, state="FAILED", error_message=err, speed_text="")
        self._pump_queue()
        self._update_ui_state()

    # --- THAO TÁC TRÊN CARD & SELECTION ---
    def _on_card_checkbox_clicked(self, task_id: str) -> None:
        self.model.toggle_select(task_id)
        self._update_ui_state()

    def _watch_task(self, task_id: str) -> None:
        task = self.model.get_task(task_id)
        if task and task.local_file_path and os.path.exists(task.local_file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(task.local_file_path))

    def _open_task_folder(self, task_id: str) -> None:
        task = self.model.get_task(task_id)
        if task and task.local_file_path:
            folder = str(Path(task.local_file_path).parent)
            if os.name == "nt":
                os.startfile(folder)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _clear_queue(self) -> None:
        if self.active_workers:
            reply = QMessageBox.question(
                self,
                "Xác nhận dừng và xóa",
                "Đang có tác vụ đang tải. Bạn có chắc muốn hủy tất cả và xóa danh sách?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        for w in list(self.active_workers.values()):
            w._is_cancelled = True
        self.active_workers.clear()
        self.download_queue.clear()
        self.model.clear_all()
        self._update_ui_state()

    def _clear_selection(self) -> None:
        self.model.clear_selection()
        self._update_ui_state()

    def _select_all_completed(self) -> None:
        self.model.select_all_completed()
        self._update_ui_state()

    # --- FILTER & SORT ---
    def _on_filter_button_clicked(self, clicked_btn: QPushButton, filter_key: str) -> None:
        for btn in self.filter_btn_group.buttons():
            is_active = (btn == clicked_btn)
            self._style_filter_button(btn, is_active)
        self.model.set_filter(filter_key)
        self._update_ui_state()

    def _on_sort_changed(self) -> None:
        idx = self.cb_sort.currentIndex()
        mapping = {0: "newest", 1: "oldest", 2: "title", 3: "platform"}
        self.model.set_sort(mapping.get(idx, "newest"))

    def _update_ui_state(self) -> None:
        counts = self.model.counts_by_state()
        self.btn_f_all.setText(f"Tất cả ({counts['all']})")
        self.btn_f_ready.setText(f"Chờ tải ({counts['ready']})")
        self.btn_f_down.setText(f"Đang tải ({counts['downloading']})")
        self.btn_f_comp.setText(f"Hoàn tất ({counts['completed']})")
        self.btn_f_fail.setText(f"Lỗi ({counts['failed']})")

        self.lbl_queue_heading.setText(f"Danh sách tải xuống • {counts['all']} video")
        self.btn_download_all.setEnabled(counts["ready"] > 0 or counts["failed"] > 0)

        # Chuyển đổi hiển thị Empty state vs Grid
        if self.model.rowCount() == 0 and len(self.model._tasks) == 0:
            self.content_stack.setCurrentIndex(1)
        else:
            self.content_stack.setCurrentIndex(0)

        # Thanh tác vụ ngữ cảnh Bottom Bar
        selected = self.model.get_selected_completed_tasks()
        if selected:
            self.bottom_bar.setVisible(True)
            self.lbl_selected_summary.setText(f"☑ {len(selected)} video hoàn tất được chọn")
        else:
            self.bottom_bar.setVisible(False)

    # --- FANPAGE PICKER & COMPOSER HANDOFF ---
    def _open_fanpage_picker(self) -> None:
        fanpages = []
        if self.page_repo:
            try:
                if hasattr(self.page_repo, "list_pages"):
                    fanpages = self.page_repo.list_pages()
                elif hasattr(self.page_repo, "get_all_pages"):
                    fanpages = self.page_repo.get_all_pages()
            except Exception as e:
                logger.error(f"Không thể lấy danh sách Fanpage: {e}")

        if not fanpages:
            QMessageBox.information(
                self,
                "Chưa có Fanpage",
                "Chưa có Fanpage nào được kết nối trong hệ thống.\nVui lòng vào mục 'Quản lý Fanpage' để kết nối trang.",
            )
            return

        popup = FanpagePickerPopup(fanpages, list(self.selected_fanpage_ids), parent=self)
        popup.pages_selected.connect(self._on_fanpages_selected)
        btn_pos = self.btn_select_fanpage.mapToGlobal(QPoint(0, 0))
        popup.move(btn_pos.x(), max(10, btn_pos.y() - popup.height() - 6))
        popup.exec()

    def _on_fanpages_selected(self, page_ids: List[str]) -> None:
        self.selected_fanpage_ids = set(page_ids)
        if self.selected_fanpage_ids:
            self.btn_select_fanpage.setText(f"Fanpage ({len(self.selected_fanpage_ids)}) ▾")
        else:
            self.btn_select_fanpage.setText("Fanpage đích ▾")

    def _on_bulk_compose(self) -> None:
        selected = self.model.get_selected_completed_tasks()
        if not selected:
            return

        if len(selected) == 1:
            t = selected[0]
            self.send_to_composer.emit({
                "file_path": t.local_file_path,
                "media_id": t.media_id,
                "title": t.title,
                "caption": t.title,
                "platform": t.source_platform,
                "url": t.source_url,
                "page_ids": list(self.selected_fanpage_ids),
            })
        else:
            self._open_batch_dialog("compose")

    def _on_bulk_schedule(self) -> None:
        self._open_batch_dialog("schedule")

    def _open_batch_dialog(self, mode: str) -> None:
        selected = self.model.get_selected_completed_tasks()
        if not selected:
            return

        media_items = []
        for t in selected:
            media_items.append({
                "id": t.media_id,
                "media_id": t.media_id,
                "title": t.title,
                "caption": t.title,
                "local_path": t.local_file_path,
                "thumbnail_path": t.thumbnail_path,
                "duration": t.duration_sec,
                "platform": t.source_platform,
            })

        fanpages = []
        if self.page_repo:
            try:
                if hasattr(self.page_repo, "list_pages"):
                    fanpages = self.page_repo.list_pages()
                elif hasattr(self.page_repo, "get_all_pages"):
                    fanpages = self.page_repo.get_all_pages()
            except Exception as e:
                logger.error(f"Lỗi lấy danh sách Fanpage: {e}")

        dlg = BatchComposeDialog(
            media_items=media_items,
            fanpages=fanpages,
            initial_selected_page_ids=list(self.selected_fanpage_ids),
            initial_mode=mode,
            parent=self,
        )
        dlg.batch_confirmed.connect(self._on_batch_confirmed)
        dlg.exec()

    def _on_batch_confirmed(self, payload: dict) -> None:
        media_items = payload.get("media_items", [])
        fanpages = payload.get("fanpages", [])
        caption = payload.get("caption", "")
        use_original_titles = payload.get("use_original_titles", True)
        start_time = payload.get("start_datetime")
        interval_min = payload.get("interval_minutes", 15)

        if not fanpages:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Vui lòng chọn ít nhất một Fanpage đích.")
            return

        selected_pids = payload.get("selected_page_ids", [str(p.get("id") or p.get("page_id")) for p in fanpages])
        self.selected_fanpage_ids = set(selected_pids)
        if self.selected_fanpage_ids:
            self.btn_select_fanpage.setText(f"Fanpage ({len(self.selected_fanpage_ids)}) ▾")

        if not self.queue_repo:
            if hasattr(self, "batch_schedule_created"):
                self.batch_schedule_created.emit([payload])
            return

        from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
        from src.lovira.domain.timezone import vn_datetime_to_utc_iso
        import uuid

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        snapshots = []
        curr_dt = start_time or datetime.now()

        for m in media_items:
            final_cap = m.get("title") if use_original_titles and m.get("title") else caption
            if not final_cap:
                final_cap = Path(m["local_path"]).stem
            for p in fanpages:
                pid = str(p.get("id") or p.get("page_id") or p.get("facebook_page_id"))
                scheduled_utc = vn_datetime_to_utc_iso(curr_dt) if curr_dt else None
                snapshots.append(
                    ContentSnapshot(
                        batch_id=batch_id,
                        page_id=pid,
                        content_type=ContentType.REELS,
                        final_caption=final_cap,
                        primary_media_id=m.get("id") or m.get("media_id"),
                        media_checksum=m.get("checksum"),
                        media_path=m["local_path"],
                        scheduled_at_utc=scheduled_utc,
                        schedule_mode=ScheduleMode.LOCAL,
                    )
                )
                curr_dt += timedelta(minutes=interval_min)

        try:
            jobs = self.queue_repo.enqueue_batch(request_id, snapshots)
            if hasattr(self, "batch_schedule_created"):
                self.batch_schedule_created.emit(jobs)
            QMessageBox.information(
                self,
                "Đặt lịch thành công",
                f"Đã tạo thành công {len(jobs)} bài đăng vào hàng đợi lịch!\n"
                "Bạn có thể theo dõi tiến độ chi tiết tại mục 'Lịch đăng'.",
            )
            self._clear_selection()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi tạo lịch hàng loạt", f"Không thể lưu các tác vụ:\n{e}")

    # --- CÁC HÀM TƯƠNG THÍCH NGƯỢC (TEST SUITE COMPATIBILITY) ---
    def _inspect_video(self) -> None:
        raw_url = self.url_input.text().strip()
        if not raw_url:
            raw_url = self.link_text_edit.toPlainText().strip()
        url = VideoDownloader.clean_url(raw_url)
        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập liên kết video.")
            return

        if url != raw_url:
            self.url_input.setText(url)

        self.btn_inspect.setEnabled(False)
        self.btn_inspect.setText("Đang phân tích...")

        meta = self.downloader.extract_metadata(url)
        self.btn_inspect.setEnabled(True)
        self.btn_inspect.setText(" Lấy thông tin")

        if not meta:
            QMessageBox.critical(self, "Lỗi phân tích", "Không thể lấy thông tin video. Vui lòng kiểm tra lại đường link.")
            return

        self._inspected_platform = meta.source_platform.value.lower() if meta.source_platform else _detect_platform(url)
        self.lbl_meta_title.setText(f"Tiêu đề: {meta.title}")
        self.lbl_meta_platform.setText(f"Nền tảng: {self._inspected_platform.upper()}")
        self.lbl_meta_author.setText(f"Tác giả: {meta.uploader}")
        m, s = divmod(int(meta.duration), 60)
        self.lbl_meta_duration.setText(f"Thời lượng: {m:02d}:{s:02d}")

        thumb_local_path = None
        if meta.thumbnail_url:
            try:
                resp = requests.get(meta.thumbnail_url, timeout=5)
                if resp.status_code == 200:
                    temp_dir = Path(os.environ.get("TEMP", "/tmp")) / "lovira_thumbs"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    t_file = temp_dir / f"meta_inspect_{int(datetime.now().timestamp())}.jpg"
                    t_file.write_bytes(resp.content)
                    thumb_local_path = str(t_file)
                    pixmap = QPixmap()
                    pixmap.loadFromData(resp.content)
                    self.thumb_label.setPixmap(pixmap)
            except Exception as e:
                logger.debug(f"Lỗi preview thumbnail: {e}")

        # Đồng bộ tạo DownloadTask vào Grid
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = DownloadTask(
            task_id=task_id,
            source_url=url,
            normalized_url=url,
            source_platform=self._inspected_platform,
            title=meta.title or "Video không tên",
            duration_sec=meta.duration or 0.0,
            thumbnail_url=meta.thumbnail_url,
            thumbnail_path=thumb_local_path,
            state="READY",
        )
        self.model.add_task(task)
        self._update_ui_state()

    def _start_download(self) -> None:
        raw_url = self.url_input.text().strip()
        url = VideoDownloader.clean_url(raw_url)
        if not url:
            return
        task = None
        for t in self.model._tasks:
            if t.normalized_url == url:
                task = t
                break
        if not task:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            task = DownloadTask(task_id=task_id, source_url=url, normalized_url=url, state="READY")
            self.model.add_task(task)
        self._start_download_task(task.task_id)

    def _cancel_download(self) -> None:
        for tid in list(self.active_workers.keys()):
            self._cancel_download_task(tid)

    def _on_download_success(self, data: dict) -> None:
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)
        self.lbl_progress_status.setText("✅ Tải video thành công!")

        file_path = data["file_path"]
        thumb_path = Path(file_path).with_suffix(".thumb.jpg")
        try:
            self.media_processor.extract_thumbnail(Path(file_path), thumb_path, timestamp_sec=3.0)
            if thumb_path.exists():
                pixmap = QPixmap(str(thumb_path))
                self.thumb_label.setPixmap(pixmap)
        except Exception as e:
            logger.debug(f"Lỗi trích xuất thumbnail: {e}")

        try:
            checksum = self.media_processor.calculate_sha256(Path(file_path))
            probe = self.media_processor.inspect_video(Path(file_path))
            detected_platform = data.get("platform") or _detect_platform(self.url_input.text())
            media_id = self.media_repo.add_media_asset(
                local_path=Path(file_path),
                checksum=checksum,
                size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                duration=probe.duration if probe else data.get("duration", 0.0),
                source_platform=detected_platform,
                source_url=self.url_input.text().strip() or data.get("url", ""),
                width=probe.width if probe else 0,
                height=probe.height if probe else 0,
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )
            data["media_id"] = media_id
        except Exception as e:
            logger.error(f"Lỗi khi thêm media asset: {e}")

        self.last_downloaded_data = data
        self.btn_watch_downloaded.setVisible(True)
        self.btn_open_folder.setVisible(True)
        self.btn_compose_now.setVisible(True)
        self.media_downloaded.emit()

        url = data.get("url") or self.url_input.text().strip()
        task = None
        for t in self.model._tasks:
            if t.normalized_url == url or (t.local_file_path and t.local_file_path == file_path):
                task = t
                break
        if task:
            self.model.update_task(
                task.task_id,
                state="COMPLETED",
                progress_percent=100,
                local_file_path=file_path,
                media_id=data.get("media_id"),
                thumbnail_path=str(thumb_path) if thumb_path.exists() else task.thumbnail_path,
            )
        else:
            task = DownloadTask(
                task_id=f"task_{uuid.uuid4().hex[:8]}",
                source_url=url,
                normalized_url=url,
                source_platform=data.get("platform", "other"),
                title=data.get("title") or Path(file_path).stem,
                duration_sec=data.get("duration", 0.0),
                thumbnail_path=str(thumb_path) if thumb_path.exists() else None,
                state="COMPLETED",
                progress_percent=100,
                local_file_path=file_path,
                media_id=data.get("media_id"),
            )
            self.model.add_task(task)
        self._update_ui_state()

    def _watch_last_downloaded(self) -> None:
        if self.last_downloaded_data and "file_path" in self.last_downloaded_data:
            fp = self.last_downloaded_data["file_path"]
            if os.path.exists(fp):
                QDesktopServices.openUrl(QUrl.fromLocalFile(fp))

    def _open_download_folder(self) -> None:
        if self.last_downloaded_data and "file_path" in self.last_downloaded_data:
            folder = str(Path(self.last_downloaded_data["file_path"]).parent)
            if os.name == "nt":
                os.startfile(folder)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_compose_now_clicked(self) -> None:
        if self.last_downloaded_data:
            self.send_to_composer.emit(self.last_downloaded_data)

    def _start_batch_download(self) -> None:
        self._analyze_input_links()

    def _cancel_batch_download(self) -> None:
        self._cancel_download()



# =========================================================================
# MODEL & DELEGATE CHO MEDIA GRID VIEW (P1)
# =========================================================================

ROLE_MEDIA_ID = Qt.ItemDataRole.UserRole + 1
ROLE_TITLE = Qt.ItemDataRole.UserRole + 2
ROLE_LOCAL_PATH = Qt.ItemDataRole.UserRole + 3
ROLE_THUMB_PATH = Qt.ItemDataRole.UserRole + 4
ROLE_DURATION_STR = Qt.ItemDataRole.UserRole + 5
ROLE_SIZE_STR = Qt.ItemDataRole.UserRole + 6
ROLE_PLATFORM = Qt.ItemDataRole.UserRole + 7
ROLE_STATUS_KEY = Qt.ItemDataRole.UserRole + 8
ROLE_STATUS_TEXT = Qt.ItemDataRole.UserRole + 9
ROLE_FILE_EXISTS = Qt.ItemDataRole.UserRole + 10
ROLE_RAW_ITEM = Qt.ItemDataRole.UserRole + 11
ROLE_VIDEO_TITLE = Qt.ItemDataRole.UserRole + 12
ROLE_HASHTAGS = Qt.ItemDataRole.UserRole + 13
ROLE_TARGET_PAGE_ID = Qt.ItemDataRole.UserRole + 14
ROLE_TARGET_PAGE_NAME = Qt.ItemDataRole.UserRole + 15
ROLE_CAPTION = Qt.ItemDataRole.UserRole + 16
ROLE_FIRST_COMMENT = Qt.ItemDataRole.UserRole + 17


class MediaAssetListModel(QAbstractListModel):
    """Model danh sách media asset phục vụ hiển thị Thumbnail Grid trên QListView."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: List[Dict[str, Any]] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        item = self._items[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("display_title") or Path(item.get("local_path", "")).stem

        if role == ROLE_MEDIA_ID:
            return item.get("id")

        if role == ROLE_TITLE:
            return item.get("display_title") or Path(item.get("local_path", "")).stem

        if role == ROLE_LOCAL_PATH:
            return item.get("local_path", "")

        if role == ROLE_THUMB_PATH:
            tp = item.get("thumbnail_path")
            if tp and os.path.exists(tp):
                return tp
            # Fallback sang .thumb.jpg cạnh video
            lp = item.get("local_path", "")
            if lp:
                fallback = str(Path(lp).with_suffix(".thumb.jpg"))
                if os.path.exists(fallback):
                    return fallback
            return None

        if role == ROLE_DURATION_STR:
            dur = int(item.get("duration", 0) or 0)
            m, s = divmod(dur, 60)
            return f"{m:02d}:{s:02d}"

        if role == ROLE_SIZE_STR:
            sz_mb = (item.get("size_bytes", 0) or 0) / (1024 * 1024)
            return f"{sz_mb:.1f} MB"

        if role == ROLE_PLATFORM:
            p = (item.get("source_platform") or "other").capitalize()
            return p

        if role == ROLE_STATUS_KEY:
            return item.get("ui_status_key", "unused")

        if role == ROLE_STATUS_TEXT:
            return item.get("ui_status_text", "Chưa sử dụng")

        if role == ROLE_FILE_EXISTS:
            lp = item.get("local_path", "")
            return os.path.exists(lp) if lp else False

        if role == ROLE_RAW_ITEM:
            return item

        if role == ROLE_VIDEO_TITLE:
            return item.get("title") or item.get("display_title") or ""

        if role == ROLE_HASHTAGS:
            return item.get("hashtags") or ""

        if role == ROLE_TARGET_PAGE_ID:
            return item.get("target_page_id") or ""

        if role == ROLE_TARGET_PAGE_NAME:
            return item.get("target_page_name") or ""

        if role == ROLE_CAPTION:
            return item.get("caption") or ""

        if role == ROLE_FIRST_COMMENT:
            return item.get("first_comment") or ""

        return None

    def set_assets(self, assets: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._items = list(assets)
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def get_media_id_at(self, row: int) -> Optional[str]:
        if 0 <= row < len(self._items):
            return self._items[row].get("id")
        return None


class MediaCardDelegate(QStyledItemDelegate):
    """
    Delegate vẽ từng Card video theo phong cách hiện đại Lovira:
    - 16:9 Thumbnail, checkbox góc trên trái, thời lượng góc trên phải, biểu tượng play ở giữa
    - Nhãn nền tảng ở góc dưới phải của thumbnail
    - Mã / Tên video nằm dưới ảnh, dung lượng file
    - Tiêu đề & Hashtags trích xuất lúc tải video
    - Dropdown chọn Fanpage đích trực tiếp trên Card
    - Viền tím phát sáng khi được chọn, hover nhẹ khi di chuột
    """

    checkbox_clicked = Signal(QModelIndex)
    page_picker_clicked = Signal(QModelIndex)
    edit_post_clicked = Signal(QModelIndex)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.thumb_cache = ThumbnailCache.get_instance()
        self.card_size = QSize(228, 298)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return self.card_size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = option.rect.adjusted(4, 4, -4, -4)
        is_selected = bool(option.state & option.state.State_Selected)
        is_hover = bool(option.state & option.state.State_MouseOver)

        # 1. Vẽ nền và viền thẻ (Card Container)
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(rect), 10, 10)

        if is_selected:
            bg_color = QColor("#18233C")
            border_color = QColor("#6258E8")
            border_width = 2.0
        elif is_hover:
            bg_color = QColor("#17243B")
            border_color = QColor("#2E4366")
            border_width = 1.0
        else:
            bg_color = QColor("#131D2E")
            border_color = QColor("#1E2D47")
            border_width = 1.0

        painter.fillPath(card_path, QBrush(bg_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawPath(card_path)

        # 2. Vùng Thumbnail 16:9
        pad = 8
        thumb_w = rect.width() - (pad * 2)
        thumb_h = int(thumb_w * 9 / 16)
        thumb_rect = QRect(rect.left() + pad, rect.top() + pad, thumb_w, thumb_h)

        thumb_path = QPainterPath()
        thumb_path.addRoundedRect(QRectF(thumb_rect), 6, 6)

        painter.save()
        painter.setClipPath(thumb_path)

        # Vẽ ảnh thumbnail hoặc nền tối fallback
        asset_id = index.data(ROLE_MEDIA_ID) or ""
        t_path = index.data(ROLE_THUMB_PATH)
        pix = self.thumb_cache.get(asset_id, t_path, thumb_w, thumb_h)

        if pix and not pix.isNull():
            src_x = (pix.width() - thumb_w) // 2
            src_y = (pix.height() - thumb_h) // 2
            painter.drawPixmap(thumb_rect.left(), thumb_rect.top(), pix, max(0, src_x), max(0, src_y), thumb_w, thumb_h)
        else:
            grad = QLinearGradient(thumb_rect.topLeft(), thumb_rect.bottomRight())
            grad.setColorAt(0.0, QColor("#0B111D"))
            grad.setColorAt(1.0, QColor("#162235"))
            painter.fillRect(thumb_rect, grad)

        # Biểu tượng Play mờ ở trung tâm thumbnail
        play_size = 28
        play_rect = QRect(
            thumb_rect.center().x() - play_size // 2,
            thumb_rect.center().y() - play_size // 2,
            play_size,
            play_size,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 170))
        painter.drawEllipse(play_rect)

        triangle = QPainterPath()
        tx = play_rect.left() + 11
        ty = play_rect.top() + 8
        triangle.moveTo(tx, ty)
        triangle.lineTo(tx + 9, ty + 6)
        triangle.lineTo(tx, ty + 12)
        triangle.closeSubpath()
        painter.setBrush(QColor(241, 245, 249, 210))
        painter.drawPath(triangle)

        painter.restore()  # Hết clip thumbnail

        # 3. Checkbox ở góc trên trái của Thumbnail
        chk_size = 18
        chk_rect = QRect(thumb_rect.left() + 6, thumb_rect.top() + 6, chk_size, chk_size)
        chk_path = QPainterPath()
        chk_path.addRoundedRect(QRectF(chk_rect), 4, 4)

        if is_selected:
            painter.fillPath(chk_path, QBrush(QColor("#6258E8")))
            painter.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            check_p = QPainterPath()
            check_p.moveTo(chk_rect.left() + 4.5, chk_rect.top() + 9.5)
            check_p.lineTo(chk_rect.left() + 7.5, chk_rect.top() + 13.0)
            check_p.lineTo(chk_rect.left() + 13.5, chk_rect.top() + 5.5)
            painter.drawPath(check_p)
        else:
            painter.fillPath(chk_path, QBrush(QColor(15, 23, 42, 180)))
            painter.setPen(QPen(QColor("#475569"), 1.2))
            painter.drawPath(chk_path)

        # 4. Thời lượng video ở góc trên phải
        dur_str = index.data(ROLE_DURATION_STR) or "00:00"
        font_badge = QFont(painter.font())
        font_badge.setPointSize(9)
        font_badge.setBold(True)
        painter.setFont(font_badge)

        fm = QFontMetrics(font_badge)
        dur_w = fm.horizontalAdvance(dur_str) + 10
        dur_rect = QRect(thumb_rect.right() - dur_w - 6, thumb_rect.top() + 6, dur_w, 18)

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(dur_rect), 4, 4)
        painter.fillPath(badge_path, QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(dur_rect, Qt.AlignmentFlag.AlignCenter, dur_str)

        # 5. Nhãn Nền tảng (Platform) ở góc dưới phải thumbnail
        platform_str = index.data(ROLE_PLATFORM) or "Video"
        font_plat = QFont(painter.font())
        font_plat.setPointSize(8)
        font_plat.setBold(True)
        painter.setFont(font_plat)
        plat_fm = QFontMetrics(font_plat)
        plat_w = plat_fm.horizontalAdvance(platform_str) + 8
        plat_rect = QRect(thumb_rect.right() - plat_w - 6, thumb_rect.bottom() - 18 - 4, plat_w, 16)

        pbadge = QPainterPath()
        pbadge.addRoundedRect(QRectF(plat_rect), 3, 3)
        painter.fillPath(pbadge, QBrush(QColor(0, 0, 0, 160)))
        painter.setPen(QColor("#CBD5E1"))
        painter.drawText(plat_rect, Qt.AlignmentFlag.AlignCenter, platform_str)

        # 6. Tên tệp / Mã video dưới Thumbnail
        content_top = thumb_rect.bottom() + 6
        file_name_str = index.data(ROLE_TITLE) or "Video không tên"
        font_fname = QFont(painter.font())
        font_fname.setPointSize(9)
        font_fname.setBold(True)
        painter.setFont(font_fname)
        painter.setPen(QColor("#F1F5F9"))

        fname_rect = QRect(rect.left() + pad, content_top, rect.width() - (pad * 2), 15)
        fm_fname = QFontMetrics(font_fname)
        elided_fname = fm_fname.elidedText(file_name_str, Qt.TextElideMode.ElideRight, fname_rect.width())
        painter.drawText(fname_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_fname)

        # 7. Dung lượng file
        size_top = content_top + 16
        size_str = index.data(ROLE_SIZE_STR) or "—"
        font_sub = QFont(painter.font())
        font_sub.setPointSize(8)
        painter.setFont(font_sub)
        painter.setPen(QColor("#8E9EB5"))

        size_rect = QRect(rect.left() + pad, size_top, rect.width() - (pad * 2), 14)
        painter.drawText(size_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, size_str)

        # 8. Tiêu đề video lúc tải
        vtitle_top = size_top + 15
        raw_vtitle = index.data(ROLE_VIDEO_TITLE)
        video_title = raw_vtitle if raw_vtitle else "(Chưa có tiêu đề)"
        font_vt = QFont(painter.font())
        font_vt.setPointSize(8)
        painter.setFont(font_vt)
        painter.setPen(QColor("#CBD5E1") if raw_vtitle else QColor("#475569"))

        vtitle_rect = QRect(rect.left() + pad, vtitle_top, rect.width() - (pad * 2), 24)
        fm_vt = QFontMetrics(font_vt)
        elided_vt = fm_vt.elidedText(video_title, Qt.TextElideMode.ElideRight, vtitle_rect.width() * 2)
        painter.drawText(vtitle_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, elided_vt)

        # 9. Hashtags của video lúc tải
        tag_top = vtitle_top + 25
        raw_tags = index.data(ROLE_HASHTAGS)
        hashtags_str = raw_tags if raw_tags else "(Chưa có hashtag)"
        font_tag = QFont(painter.font())
        font_tag.setPointSize(8)
        font_tag.setBold(bool(raw_tags))
        painter.setFont(font_tag)
        painter.setPen(QColor("#A78BFA") if raw_tags else QColor("#334155"))

        tag_rect = QRect(rect.left() + pad, tag_top, rect.width() - (pad * 2), 14)
        fm_tag = QFontMetrics(font_tag)
        elided_tag = fm_tag.elidedText(hashtags_str, Qt.TextElideMode.ElideRight, tag_rect.width())
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_tag)

        # 10. Dropdown chọn Fanpage đích
        combo_top = tag_top + 17
        combo_rect = QRect(rect.left() + pad, combo_top, rect.width() - (pad * 2), 24)

        c_path = QPainterPath()
        c_path.addRoundedRect(QRectF(combo_rect), 5, 5)
        painter.fillPath(c_path, QBrush(QColor("#162338")))
        painter.setPen(QPen(QColor("#2C4263"), 1.0))
        painter.drawPath(c_path)

        target_pname = index.data(ROLE_TARGET_PAGE_NAME)
        font_combo = QFont(painter.font())
        font_combo.setPointSize(8)
        font_combo.setBold(bool(target_pname))
        painter.setFont(font_combo)
        fm_c = QFontMetrics(font_combo)

        if target_pname:
            painter.setPen(QColor("#E2E8F0"))
            combo_text = f"📄 {target_pname}"
        else:
            painter.setPen(QColor("#94A3B8"))
            combo_text = "📄 Chọn Fanpage đích"

        text_rect = QRect(combo_rect.left() + 6, combo_rect.top(), combo_rect.width() - 22, combo_rect.height())
        elided_c = fm_c.elidedText(combo_text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_c)

        arrow_rect = QRect(combo_rect.right() - 16, combo_rect.top(), 12, combo_rect.height())
        painter.setPen(QColor("#818CF8"))
        painter.drawText(arrow_rect, Qt.AlignmentFlag.AlignCenter, "▾")

        # 11. Nút Chỉnh sửa & Đăng
        edit_btn_top = combo_top + 28
        edit_btn_rect = QRect(rect.left() + pad, edit_btn_top, rect.width() - (pad * 2), 24)

        eb_path = QPainterPath()
        eb_path.addRoundedRect(QRectF(edit_btn_rect), 5, 5)
        painter.fillPath(eb_path, QBrush(QColor("#1E1B4B")))
        painter.setPen(QPen(QColor("#4F46E5"), 1.0))
        painter.drawPath(eb_path)

        icon_pix = get_icon("composer", "#A5B4FC", 12).pixmap(12, 12)
        font_eb = QFont(painter.font())
        font_eb.setPointSize(8)
        font_eb.setBold(True)
        painter.setFont(font_eb)
        fm_eb = QFontMetrics(font_eb)
        btn_text = "Chỉnh sửa & Đăng"
        text_w = fm_eb.horizontalAdvance(btn_text)
        total_w = 12 + 6 + text_w
        start_x = edit_btn_rect.center().x() - total_w // 2

        if not icon_pix.isNull():
            painter.drawPixmap(start_x, edit_btn_rect.center().y() - 6, icon_pix)
        painter.setPen(QColor("#E0E7FF"))
        painter.drawText(
            QRect(start_x + 18, edit_btn_rect.top(), text_w + 4, edit_btn_rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            btn_text,
        )

        # 12. Chip Trạng thái ở đáy Card
        status_top = edit_btn_top + 28
        status_key = index.data(ROLE_STATUS_KEY) or "unused"
        status_text = index.data(ROLE_STATUS_TEXT) or "Chưa sử dụng"
        file_exists = index.data(ROLE_FILE_EXISTS)

        if not file_exists:
            dot_color = QColor("#F59E0B")
            text_color = QColor("#FBBF24")
            status_text = "File thất lạc"
        elif status_key == "failed":
            dot_color = QColor("#EF4444")
            text_color = QColor("#F87171")
        elif status_key == "scheduled":
            dot_color = QColor("#818CF8")
            text_color = QColor("#A5B4FC")
        elif status_key == "published":
            dot_color = QColor("#10B981")
            text_color = QColor("#34D399")
        else:
            dot_color = QColor("#64748B")
            text_color = QColor("#94A3B8")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(rect.left() + pad + 2, status_top + 4, 7, 7)

        font_status = QFont(painter.font())
        font_status.setPointSize(8)
        painter.setFont(font_status)
        painter.setPen(text_color)
        status_rect = QRect(rect.left() + pad + 14, status_top, rect.width() - (pad * 2) - 14, 16)
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status_text)

        painter.restore()

    def editorEvent(self, event: QEvent, model: QAbstractListModel, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        """Xử lý nhấp chuột vào ô Checkbox, Dropdown chọn Fanpage đích và Nút Chỉnh sửa."""
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            rect = option.rect.adjusted(4, 4, -4, -4)
            pad = 8
            thumb_w = rect.width() - (pad * 2)
            thumb_h = int(thumb_w * 9 / 16)
            thumb_rect = QRect(rect.left() + pad, rect.top() + pad, thumb_w, thumb_h)

            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

            # Checkbox hit-test (nới rộng hitbox để click góc thumbnail cực nhạy)
            chk_rect = QRect(thumb_rect.left(), thumb_rect.top(), 36, 36)
            if chk_rect.contains(pos):
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.checkbox_clicked.emit(index)
                return True

            # Dropdown Fanpage đích hit-test
            content_top = thumb_rect.bottom() + 6
            size_top = content_top + 16
            vtitle_top = size_top + 15
            tag_top = vtitle_top + 25
            combo_top = tag_top + 17
            combo_rect = QRect(rect.left() + pad, combo_top - 2, rect.width() - (pad * 2), 28)
            if combo_rect.contains(pos):
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.page_picker_clicked.emit(index)
                return True

            # Nút Chỉnh sửa & Đăng hit-test
            edit_btn_top = combo_top + 28
            edit_btn_rect = QRect(rect.left() + pad, edit_btn_top - 2, rect.width() - (pad * 2), 28)
            if edit_btn_rect.contains(pos):
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.edit_post_clicked.emit(index)
                return True

        return super().editorEvent(event, model, option, index)


class MediaGridView(QListView):
    """QListView ở chế độ IconMode cho phép chọn nhiều, responsive và hỗ trợ bàn phím."""

    item_double_clicked_preview = Signal(str)
    delete_pressed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.setSpacing(10)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QListView {
                background-color: #0D1627;
                border: none;
                outline: none;
                padding: 6px;
            }
            QListView::item {
                border: none;
                margin: 2px;
            }
        """)

        self.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index: QModelIndex) -> None:
        media_id = index.data(ROLE_MEDIA_ID)
        if media_id:
            self.item_double_clicked_preview.emit(media_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_A and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.clearSelection()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            selected = self.selectionModel().selectedIndexes()
            if selected:
                media_id = selected[0].data(ROLE_MEDIA_ID)
                if media_id:
                    self.item_double_clicked_preview.emit(media_id)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# =========================================================================
# POPUP CHỌN FANPAGE ĐÍCH (SECTION 4)
# =========================================================================

class FanpagePickerPopup(QDialog):
    """
    Popup dropdown chọn Fanpage đích dạng searchable multi-select:
    - Tìm kiếm nhanh theo tên hoặc ID
    - Chọn tất cả trang khả dụng
    - Hiển thị trạng thái kết nối / token
    - Không lộ token
    """

    pages_selected = Signal(list)

    def __init__(self, pages: List[Dict[str, Any]], initial_selected_ids: Optional[List[str]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.pages = pages
        self.selected_ids: Set[str] = set(initial_selected_ids or [])

        self.setFixedWidth(320)
        self.setFixedHeight(360)
        self.setStyleSheet("""
            QDialog {
                background-color: #131D2E;
                border: 1px solid #2B3D59;
                border-radius: 8px;
            }
            QLineEdit {
                background-color: #0B111D;
                border: 1px solid #24344D;
                border-radius: 6px;
                padding: 6px 10px;
                color: #F1F5F9;
                font-size: 12px;
            }
            QCheckBox {
                color: #E2E8F0;
                font-size: 12px;
                spacing: 8px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QPushButton#applyBtn {
                background-color: #6258E8;
                color: #FFFFFF;
                border-radius: 6px;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton#applyBtn:hover {
                background-color: #5348D6;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header title
        title_lbl = QLabel("CHỌN FANPAGE ĐÍCH")
        title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #818CF8; letter-spacing: 0.5px;")
        layout.addWidget(title_lbl)

        # Ô tìm kiếm
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tìm theo tên / Page ID...")
        self.search_input.textChanged.connect(self._filter_pages)
        layout.addWidget(self.search_input)

        # Checkbox chọn tất cả
        self.cb_select_all = QCheckBox("Chọn tất cả trang khả dụng")
        self.cb_select_all.clicked.connect(self._toggle_select_all)
        layout.addWidget(self.cb_select_all)

        # Đường kẻ phân cách
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1E2D47; max-height: 1px;")
        layout.addWidget(sep)

        # Danh sách Fanpage dạng cuộn
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(6)

        # Footer
        footer = QHBoxLayout()
        self.lbl_count = QLabel(f"Đã chọn {len(self.selected_ids)}")
        self.lbl_count.setStyleSheet("color: #94A3B8; font-size: 12px;")
        footer.addWidget(self.lbl_count)
        footer.addStretch()

        btn_apply = QPushButton("Áp dụng")
        btn_apply.setObjectName("applyBtn")
        btn_apply.clicked.connect(self._apply_and_close)
        footer.addWidget(btn_apply)

        self.checkbox_map: Dict[str, QCheckBox] = {}
        self._populate_list()

        self.scroll_area.setWidget(self.list_widget)
        layout.addWidget(self.scroll_area, stretch=1)
        layout.addLayout(footer)

    def _populate_list(self) -> None:
        # Xóa các widget cũ
        while self.list_layout.count():
            w = self.list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.checkbox_map.clear()

        for page in self.pages:
            pid = str(page.get("id") or page.get("page_id") or page.get("facebook_page_id"))
            pname = page.get("name") or page.get("page_name") or f"Page {pid}"
            status = str(page.get("status") or "ready")
            is_valid = status not in ("token_expired", "expired")

            row_frame = QFrame()
            row_frame.setStyleSheet("""
                QFrame {
                    background-color: #17243B;
                    border: 1px solid #24354F;
                    border-radius: 6px;
                }
                QFrame:hover {
                    background-color: #1E2D47;
                    border-color: #384F73;
                }
            """)
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(8)

            cb = QCheckBox(pname)
            cb.setChecked(pid in self.selected_ids and is_valid)
            cb.setToolTip(f"ID: {pid}")
            cb.setCursor(Qt.CursorShape.PointingHandCursor if is_valid else Qt.CursorShape.ForbiddenCursor)

            if not is_valid:
                cb.setEnabled(False)
                lbl_status = QLabel("! Token hết hạn")
                lbl_status.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 700;")
            else:
                lbl_status = QLabel("● Sẵn sàng")
                lbl_status.setStyleSheet("color: #10B981; font-size: 11px;")

            cb.stateChanged.connect(lambda state, p_id=pid: self._on_item_checked(p_id, state))

            row_layout.addWidget(cb, stretch=1)
            row_layout.addWidget(lbl_status)

            self.list_layout.addWidget(row_frame)
            self.checkbox_map[pid] = cb

        self.list_layout.addStretch()
        self._update_count_label()

    def _on_item_checked(self, pid: str, state: int) -> None:
        if state == Qt.CheckState.Checked.value:
            self.selected_ids.add(pid)
        else:
            self.selected_ids.discard(pid)
        self._update_count_label()

    def _toggle_select_all(self, checked: bool) -> None:
        for pid, cb in self.checkbox_map.items():
            if cb.isEnabled():
                cb.setChecked(checked)
                if checked:
                    self.selected_ids.add(pid)
                else:
                    self.selected_ids.discard(pid)
        self._update_count_label()

    def _filter_pages(self, query: str) -> None:
        q = query.strip().lower()
        for page in self.pages:
            pid = str(page.get("id") or page.get("page_id"))
            pname = (page.get("name") or page.get("page_name") or "").lower()
            if pid in self.checkbox_map:
                cb = self.checkbox_map[pid]
                parent_frame = cb.parentWidget()
                if parent_frame:
                    parent_frame.setVisible(not q or q in pname or q in pid.lower())

    def _update_count_label(self) -> None:
        self.lbl_count.setText(f"Đã chọn {len(self.selected_ids)}")

    def _apply_and_close(self) -> None:
        self.pages_selected.emit(list(self.selected_ids))
        self.accept()


# =========================================================================
# HỘP THOẠI XÁC NHẬN TẠO BÀI & ĐẶT LỊCH HÀNG LOẠT (SECTION 6)
# =========================================================================

class BatchComposeDialog(QDialog):
    """
    Hộp thoại tạo bài viết & Lên lịch đăng hàng loạt:
    - Chọn Fanpage đích trực quan ngay trong popup (Có tìm kiếm + Chọn tất cả + Hiển thị số lượng)
    - Tự động lấy Title & Hashtag của video đã tải điền vào Caption
    - Tùy chọn giữ nguyên Title/Hashtag riêng từng video hoặc dùng Caption chung
    - Cài đặt thời gian bắt đầu (múi giờ VN UTC+7) và khoảng cách giữa các bài
    - Bảng xem trước phân bổ lịch trực quan
    - Tạo và lưu lịch đăng trực tiếp vào hàng đợi
    """

    batch_confirmed = Signal(dict)

    def __init__(
        self,
        media_items: List[Dict[str, Any]],
        fanpages: List[Dict[str, Any]],
        initial_selected_page_ids: Optional[List[str]] = None,
        initial_mode: str = "schedule",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.media_items = media_items
        self.fanpages = fanpages
        self.mode = initial_mode
        self.selected_page_ids: Set[str] = set(initial_selected_page_ids or [])

        # Nếu chưa chọn page nào từ ngoài, tự động chọn tất cả page khả dụng
        if not self.selected_page_ids:
            for p in self.fanpages:
                st = str(p.get("status") or "ready")
                if st not in ("token_expired", "expired"):
                    pid = str(p.get("id") or p.get("page_id") or p.get("facebook_page_id"))
                    self.selected_page_ids.add(pid)

        self.setWindowTitle("Xác nhận Đặt lịch / Tạo bài đăng")
        self.resize(680, 720)
        self.setMinimumSize(600, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #0D1627;
                color: #F1F5F9;
            }
            QFrame#cardBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 8px;
            }
            QLabel {
                color: #F1F5F9;
            }
            QTextEdit, QLineEdit, QDateTimeEdit, QSpinBox {
                background-color: #0B111D;
                border: 1px solid #24344D;
                border-radius: 6px;
                padding: 6px;
                color: #F1F5F9;
                font-size: 12px;
            }
            QTextEdit:focus, QLineEdit:focus, QDateTimeEdit:focus, QSpinBox:focus {
                border-color: #6258E8;
            }
            QTableWidget {
                background-color: #0B111D;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                color: #E2E8F0;
                gridline-color: #1E2D47;
            }
            QHeaderView::section {
                background-color: #131D2E;
                color: #94A3B8;
                font-weight: 700;
                font-size: 11px;
                border: none;
                padding: 4px;
            }
            /* QCalendarWidget Dark Styling */
            QCalendarWidget {
                background-color: #0B111D;
                border: 1px solid #2B3D59;
                border-radius: 8px;
            }
            QCalendarWidget QWidget {
                alternate-background-color: #131D2E;
                background-color: #0B111D;
                color: #F1F5F9;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: #131D2E;
                border-bottom: 1px solid #1E2D47;
                min-height: 36px;
            }
            QCalendarWidget QToolButton {
                color: #F1F5F9;
                background-color: transparent;
                border-radius: 4px;
                font-weight: 700;
                font-size: 12px;
                padding: 4px 8px;
                margin: 2px;
            }
            QCalendarWidget QToolButton:hover {
                background-color: #1E2D47;
            }
            QCalendarWidget QMenu {
                background-color: #131D2E;
                color: #F1F5F9;
                border: 1px solid #24344D;
                border-radius: 6px;
                padding: 4px;
            }
            QCalendarWidget QSpinBox {
                background-color: #0B111D;
                color: #F1F5F9;
                border: 1px solid #24344D;
                border-radius: 4px;
                padding: 2px 4px;
            }
            QCalendarWidget QTableView {
                background-color: #0B111D;
                selection-background-color: #6258E8;
                selection-color: #FFFFFF;
                color: #F1F5F9;
                font-size: 12px;
                outline: none;
                border: none;
            }
            QCalendarWidget QAbstractItemView:enabled {
                color: #F1F5F9;
                background-color: #0B111D;
                selection-background-color: #6258E8;
                selection-color: #FFFFFF;
            }
            QCalendarWidget QAbstractItemView:disabled {
                color: #475569;
            }
            QCalendarWidget QHeaderView::section {
                background-color: #131D2E;
                color: #818CF8;
                font-weight: 700;
                font-size: 11px;
                border: none;
                padding: 4px 0px;
            }
            QPushButton#primaryBtn {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                padding: 9px 18px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #5348D6;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #2D3748;
                color: #718096;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Tiêu đề
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel("TẠO BÀI VIẾT & LÊN LỊCH ĐĂNG")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #818CF8;")
        sub_lbl = QLabel(f"Phát hành tự động {len(self.media_items)} video đã chọn sang nhiều Fanpage Facebook.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        main_layout.addLayout(title_box)

        # Scroll area bao bọc nội dung
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        # 1. Card CHỌN FANPAGE ĐÍCH
        fanpage_box = QFrame()
        fanpage_box.setObjectName("cardBox")
        fb_layout = QVBoxLayout(fanpage_box)
        fb_layout.setContentsMargins(14, 12, 14, 12)
        fb_layout.setSpacing(8)

        fb_head = QHBoxLayout()
        self.lbl_fb_title = QLabel("1. FANPAGE ĐÍCH")
        self.lbl_fb_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        fb_head.addWidget(self.lbl_fb_title)
        fb_head.addStretch()

        self.lbl_pages_counter = QLabel(f"Đã chọn: {len(self.selected_page_ids)} trang")
        self.lbl_pages_counter.setStyleSheet("color: #10B981; font-weight: 700; font-size: 12px;")
        fb_head.addWidget(self.lbl_pages_counter)
        fb_layout.addLayout(fb_head)

        # Ô tìm kiếm trang & Chọn tất cả
        fp_tool_row = QHBoxLayout()
        self.input_search_pages = QLineEdit()
        self.input_search_pages.setPlaceholderText("🔍 Tìm theo tên trang hoặc ID...")
        self.input_search_pages.textChanged.connect(self._filter_page_rows)
        fp_tool_row.addWidget(self.input_search_pages, stretch=1)

        self.cb_select_all_pages = QCheckBox("Chọn tất cả trang")
        self.cb_select_all_pages.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        self.cb_select_all_pages.clicked.connect(self._toggle_select_all_pages)
        fp_tool_row.addWidget(self.cb_select_all_pages)
        fb_layout.addLayout(fp_tool_row)

        # Danh sách checkboxes cuộn
        pages_scroll = QScrollArea()
        pages_scroll.setFixedHeight(120)
        pages_scroll.setWidgetResizable(True)
        pages_scroll.setStyleSheet("border: 1px solid #1E2D47; border-radius: 6px; background-color: #0B111D;")

        self.pages_container = QWidget()
        self.pages_list_layout = QVBoxLayout(self.pages_container)
        self.pages_list_layout.setContentsMargins(6, 6, 6, 6)
        self.pages_list_layout.setSpacing(4)

        self.page_checkbox_map: Dict[str, Tuple[QCheckBox, QFrame]] = {}
        self._populate_fanpages_list()
        pages_scroll.setWidget(self.pages_container)
        fb_layout.addWidget(pages_scroll)
        layout.addWidget(fanpage_box)

        # 2. Card NỘI DUNG & HASHTAG VIDEO
        content_box = QFrame()
        content_box.setObjectName("cardBox")
        cb_layout = QVBoxLayout(content_box)
        cb_layout.setContentsMargins(14, 12, 14, 12)
        cb_layout.setSpacing(8)

        cb_head = QHBoxLayout()
        cb_title = QLabel("2. TIÊU ĐỀ && HASHTAG BÀI ĐĂNG")
        cb_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        cb_head.addWidget(cb_title)
        cb_head.addStretch()
        cb_layout.addLayout(cb_head)

        self.cb_use_original_titles = QCheckBox("Giữ nguyên Tiêu đề && Hashtag riêng của từng video khi đăng bài (Khuyên dùng)")
        self.cb_use_original_titles.setChecked(True)
        self.cb_use_original_titles.setStyleSheet("color: #10B981; font-weight: 600; font-size: 12px;")
        self.cb_use_original_titles.toggled.connect(self._update_preview_table)
        cb_layout.addWidget(self.cb_use_original_titles)

        # Lấy title / hashtag đầu tiên làm caption mặc định
        first_caption = ""
        if self.media_items:
            first_caption = self.media_items[0].get("caption") or self.media_items[0].get("title") or ""

        self.caption_edit = QTextEdit()
        self.caption_edit.setPlaceholderText("Nhập tiêu đề hoặc hashtag bổ sung chung...")
        self.caption_edit.setFixedHeight(75)
        self.caption_edit.setPlainText(first_caption)
        self.caption_edit.textChanged.connect(self._update_preview_table)
        cb_layout.addWidget(self.caption_edit)
        layout.addWidget(content_box)

        # 3. Card CẤU HÌNH THỜI GIAN LÊN LỊCH
        sched_box = QFrame()
        sched_box.setObjectName("cardBox")
        sb_layout = QVBoxLayout(sched_box)
        sb_layout.setContentsMargins(14, 12, 14, 12)
        sb_layout.setSpacing(10)

        sched_title = QLabel("3. CẤU HÌNH THỜI GIAN LÊN LỊCH (MÚI GIỜ VIỆT NAM UTC+7)")
        sched_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        sb_layout.addWidget(sched_title)

        time_row = QHBoxLayout()
        time_row.setSpacing(12)
        time_row.addWidget(QLabel("Thời gian bắt đầu:"))

        self.start_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(15 * 60))
        self.start_dt.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.start_dt.setCalendarPopup(True)
        cal = self.start_dt.calendarWidget()
        if cal:
            cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        time_row.addWidget(self.start_dt)

        time_row.addWidget(QLabel("Giãn cách giữa các bài:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 1440)
        self.spin_interval.setValue(15)
        self.spin_interval.setSuffix(" phút")
        time_row.addWidget(self.spin_interval)

        sb_layout.addLayout(time_row)
        layout.addWidget(sched_box)

        # 4. Card XEM TRƯỚC PHÂN BỔ LỊCH ĐĂNG
        preview_box = QFrame()
        preview_box.setObjectName("cardBox")
        pb_layout = QVBoxLayout(preview_box)
        pb_layout.setContentsMargins(14, 12, 14, 12)
        pb_layout.setSpacing(8)

        pb_title = QLabel("4. XEM TRƯỚC PHÂN BỔ LỊCH ĐĂNG")
        pb_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        pb_layout.addWidget(pb_title)

        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(3)
        self.table_preview.setHorizontalHeaderLabels(["Video (Tiêu đề / Hashtag)", "Fanpage đích", "Thời gian dự kiến (UTC+7)"])
        self.table_preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_preview.setFixedHeight(130)
        pb_layout.addWidget(self.table_preview)
        layout.addWidget(preview_box)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        # Nối tín hiệu cập nhật bảng preview
        self.start_dt.dateTimeChanged.connect(self._update_preview_table)
        self.spin_interval.valueChanged.connect(self._update_preview_table)

        # Footer Bottom Bar
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.lbl_total_calc = QLabel()
        self.lbl_total_calc.setStyleSheet("font-size: 13px; color: #CBD5E1;")
        footer.addWidget(self.lbl_total_calc)
        footer.addStretch()

        btn_cancel = QPushButton("Hủy bỏ")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        self.btn_confirm = QPushButton("🚀 Xác nhận đặt lịch")
        self.btn_confirm.setObjectName("primaryBtn")
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.clicked.connect(self._on_confirm_clicked)
        footer.addWidget(self.btn_confirm)

        main_layout.addLayout(footer)

        self._update_preview_table()

    def _populate_fanpages_list(self) -> None:
        while self.pages_list_layout.count():
            w = self.pages_list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.page_checkbox_map.clear()

        for page in self.fanpages:
            pid = str(page.get("id") or page.get("page_id") or page.get("facebook_page_id"))
            pname = page.get("name") or page.get("page_name") or f"Page {pid}"
            status = str(page.get("status") or "ready")
            is_valid = status not in ("token_expired", "expired")

            row_frame = QFrame()
            row_frame.setStyleSheet("""
                QFrame {
                    background-color: #131E33;
                    border: 1px solid #1E2D47;
                    border-radius: 4px;
                }
                QFrame:hover {
                    background-color: #1A2942;
                    border-color: #384F73;
                }
            """)
            r_lay = QHBoxLayout(row_frame)
            r_lay.setContentsMargins(6, 4, 6, 4)
            r_lay.setSpacing(8)

            cb = QCheckBox(pname)
            cb.setChecked(pid in self.selected_page_ids and is_valid)
            cb.setEnabled(is_valid)
            cb.setToolTip(f"Page ID: {pid}")
            cb.stateChanged.connect(lambda state, p_id=pid: self._on_page_toggled(p_id, state))

            if not is_valid:
                lbl_st = QLabel("! Hết hạn")
                lbl_st.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 700;")
            else:
                lbl_st = QLabel("● Sẵn sàng")
                lbl_st.setStyleSheet("color: #10B981; font-size: 11px;")

            r_lay.addWidget(cb, stretch=1)
            r_lay.addWidget(lbl_st)

            self.pages_list_layout.addWidget(row_frame)
            self.page_checkbox_map[pid] = (cb, row_frame)

        self.pages_list_layout.addStretch()

    def _on_page_toggled(self, pid: str, state: int) -> None:
        if state == Qt.CheckState.Checked.value:
            self.selected_page_ids.add(pid)
        else:
            self.selected_page_ids.discard(pid)
        self.lbl_pages_counter.setText(f"Đã chọn: {len(self.selected_page_ids)} trang")
        self._update_preview_table()

    def _toggle_select_all_pages(self, checked: bool) -> None:
        for pid, (cb, _) in self.page_checkbox_map.items():
            if cb.isEnabled():
                cb.setChecked(checked)
                if checked:
                    self.selected_page_ids.add(pid)
                else:
                    self.selected_page_ids.discard(pid)
        self.lbl_pages_counter.setText(f"Đã chọn: {len(self.selected_page_ids)} trang")
        self._update_preview_table()

    def _filter_page_rows(self, text: str) -> None:
        q = text.strip().lower()
        for page in self.fanpages:
            pid = str(page.get("id") or page.get("page_id") or page.get("facebook_page_id"))
            pname = (page.get("name") or page.get("page_name") or "").lower()
            if pid in self.page_checkbox_map:
                _, frame = self.page_checkbox_map[pid]
                frame.setVisible(not q or q in pname or q in pid)

    def _update_preview_table(self) -> None:
        self.table_preview.setRowCount(0)
        start_time = self.start_dt.dateTime().toPython()
        interval_min = self.spin_interval.value()

        chosen_pages = [p for p in self.fanpages if str(p.get("id") or p.get("page_id") or p.get("facebook_page_id")) in self.selected_page_ids]

        current_time = start_time
        row = 0
        use_ind = self.cb_use_original_titles.isChecked() if hasattr(self, "cb_use_original_titles") else True
        custom_cap = self.caption_edit.toPlainText().strip()

        for m in self.media_items:
            m_title = m.get("caption") or m.get("title") or Path(m.get("local_path", "")).stem
            v_display = m_title if (use_ind or not custom_cap) else custom_cap
            for p in chosen_pages:
                p_name = p.get("name") or p.get("page_name") or "Fanpage"
                self.table_preview.insertRow(row)
                self.table_preview.setItem(row, 0, QTableWidgetItem(v_display))
                self.table_preview.setItem(row, 1, QTableWidgetItem(p_name))
                self.table_preview.setItem(row, 2, QTableWidgetItem(current_time.strftime("%d/%m/%Y %H:%M")))
                current_time += timedelta(minutes=interval_min)
                row += 1
                if row >= 30:
                    break
            if row >= 30:
                break

        n_vid = len(self.media_items)
        n_page = len(chosen_pages)
        total_posts = n_vid * n_page
        self.btn_confirm.setText(f"🚀 Xác nhận tạo {total_posts} lịch đăng")
        self.btn_confirm.setEnabled(total_posts > 0)
        self.lbl_total_calc.setText(
            f"Đã chọn: <b>{n_vid} video</b> × <b>{n_page} Fanpage</b> = "
            f"<span style='color: #10B981; font-weight: 800; font-size: 14px;'>{total_posts} bài dự kiến</span>"
        )

    def _on_confirm_clicked(self) -> None:
        chosen_pages = [p for p in self.fanpages if str(p.get("id") or p.get("page_id") or p.get("facebook_page_id")) in self.selected_page_ids]
        if not chosen_pages:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Vui lòng chọn ít nhất một Fanpage đích.")
            return

        payload = {
            "media_items": self.media_items,
            "fanpages": chosen_pages,
            "selected_page_ids": list(self.selected_page_ids),
            "caption": self.caption_edit.toPlainText().strip(),
            "use_original_titles": self.cb_use_original_titles.isChecked(),
            "start_datetime": self.start_dt.dateTime().toPython(),
            "interval_minutes": self.spin_interval.value(),
        }
        self.batch_confirmed.emit(payload)
        self.accept()


# =========================================================================
# HỘP THOẠI CHI TIẾT VIDEO & LỊCH SỬ SỬ DỤNG (SECTION 5.4)
# =========================================================================

class MediaDetailDialog(QDialog):
    """Hộp thoại xem chi tiết video, siêu dữ liệu kỹ thuật và lịch sử đăng theo từng Fanpage."""

    compose_requested = Signal(dict)

    def __init__(self, asset: Dict[str, Any], usage_info: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.asset = asset
        self.usage_info = usage_info or {}

        title = asset.get("display_title") or Path(asset.get("local_path", "")).stem
        self.setWindowTitle(f"Chi tiết Video — {title}")
        self.setFixedSize(620, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0D1627;
                color: #F1F5F9;
            }
            QFrame#cardBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 8px;
            }
            QLabel {
                color: #F1F5F9;
            }
            QPushButton#primaryBtn {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                padding: 6px 14px;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Thông tin kỹ thuật
        tech_frame = QFrame()
        tech_frame.setObjectName("cardBox")
        tech_layout = QVBoxLayout(tech_frame)
        tech_layout.setContentsMargins(14, 14, 14, 14)
        tech_layout.setSpacing(8)

        v_title = self.asset.get("display_title") or Path(self.asset.get("local_path", "")).stem
        lbl_title = QLabel(f"<b>{v_title}</b>")
        lbl_title.setStyleSheet("font-size: 15px; color: #818CF8;")
        tech_layout.addWidget(lbl_title)

        lp = self.asset.get("local_path", "")
        dur = int(self.asset.get("duration", 0) or 0)
        m, s = divmod(dur, 60)
        sz_mb = (self.asset.get("size_bytes", 0) or 0) / (1024 * 1024)
        plat = (self.asset.get("source_platform") or "Khác").capitalize()

        info_lines = [
            f"<b>Nền tảng gốc:</b> {plat}",
            f"<b>Thời lượng:</b> {m:02d}:{s:02d} | <b>Dung lượng:</b> {sz_mb:.1f} MB",
            f"<b>Độ phân giải:</b> {self.asset.get('width', 0)} x {self.asset.get('height', 0)}",
            f"<b>Đường dẫn:</b> <span style='color: #94A3B8;'>{lp}</span>",
            f"<b>Checksum:</b> <span style='color: #64748B; font-size: 11px;'>{self.asset.get('checksum', '—')}</span>",
        ]

        for line in info_lines:
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 12px; color: #E2E8F0;")
            tech_layout.addWidget(lbl)

        layout.addWidget(tech_frame)

        # Lịch sử sử dụng trên các Fanpage
        hist_title = QLabel("LỊCH SỬ ĐĂNG & LÊN LỊCH THEO TỪNG FANPAGE")
        hist_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        layout.addWidget(hist_title)

        self.table_hist = QTableWidget()
        self.table_hist.setColumnCount(4)
        self.table_hist.setHorizontalHeaderLabels(["Fanpage", "Trạng thái", "Thời gian", "Tác vụ ID"])
        self.table_hist.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_hist.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_hist.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._populate_history()
        layout.addWidget(self.table_hist, stretch=1)

        # Nút thao tác dưới
        btn_row = QHBoxLayout()
        btn_play = QPushButton("▶ Phát video")
        btn_play.clicked.connect(self._play_video)

        btn_folder = QPushButton("📁 Mở thư mục")
        btn_folder.clicked.connect(self._open_folder)

        btn_compose = QPushButton("🎬 Mở trong trình Soạn bài")
        btn_compose.setObjectName("primaryBtn")
        btn_compose.clicked.connect(self._on_compose_clicked)

        btn_row.addWidget(btn_play)
        btn_row.addWidget(btn_folder)
        btn_row.addStretch()
        btn_row.addWidget(btn_compose)
        layout.addLayout(btn_row)

    def _populate_history(self) -> None:
        self.table_hist.setRowCount(0)
        jobs: List[Dict[str, Any]] = []

        for j in self.usage_info.get("published_jobs", []):
            jobs.append({**j, "status_label": "✅ Đã đăng"})
        for j in self.usage_info.get("scheduled_jobs", []):
            jobs.append({**j, "status_label": "📅 Đang lên lịch"})
        for j in self.usage_info.get("failed_jobs", []):
            jobs.append({**j, "status_label": "❌ Đăng lỗi"})

        if not jobs:
            self.table_hist.setRowCount(1)
            self.table_hist.setItem(0, 0, QTableWidgetItem("Chưa từng được đăng trên Fanpage nào"))
            self.table_hist.setItem(0, 1, QTableWidgetItem("Chưa sử dụng"))
            self.table_hist.setItem(0, 2, QTableWidgetItem("—"))
            self.table_hist.setItem(0, 3, QTableWidgetItem("—"))
            return

        self.table_hist.setRowCount(len(jobs))
        for r, j in enumerate(jobs):
            self.table_hist.setItem(r, 0, QTableWidgetItem(j.get("page_name") or j.get("page_id", "—")))
            self.table_hist.setItem(r, 1, QTableWidgetItem(j.get("status_label", "—")))
            self.table_hist.setItem(r, 2, QTableWidgetItem(j.get("scheduled_at_utc", "—")))
            self.table_hist.setItem(r, 3, QTableWidgetItem(j.get("job_id", "—")))

    def _play_video(self) -> None:
        lp = self.asset.get("local_path", "")
        if os.path.exists(lp):
            QDesktopServices.openUrl(QUrl.fromLocalFile(lp))
        else:
            QMessageBox.critical(self, "Lỗi", f"File không tồn tại trên máy:\n{lp}")

    def _open_folder(self) -> None:
        lp = self.asset.get("local_path", "")
        if os.path.exists(lp):
            folder = str(Path(lp).parent)
            if os.name == "nt":
                os.startfile(folder)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_compose_clicked(self) -> None:
        self.compose_requested.emit({
            "media_id": self.asset["id"],
            "file_path": self.asset["local_path"],
            "duration": self.asset.get("duration", 0),
            "platform": self.asset.get("source_platform", "other"),
        })
        self.accept()


# =========================================================================
# HỘP THOẠI CHỈNH SỬA NỘI DUNG & ĐĂNG NHANH VIDEO
# =========================================================================

class MediaEditPostDialog(QDialog):
    """
    Hộp thoại chỉnh sửa thông tin bài viết & Đăng nhanh video:
    - Chỉnh sửa tiêu đề video, nội dung/caption, hashtags, bình luận đính kèm (first comment)
    - Lựa chọn Fanpage đích từ danh sách kết nối
    - Lựa chọn định dạng đăng (Reels hoặc Video)
    - Lưu thông tin vào DB media_assets hoặc Đăng nhanh đưa vào hàng đợi publish
    """

    post_published = Signal(list)

    def __init__(
        self,
        asset: Dict[str, Any],
        pages: List[Dict[str, Any]],
        queue_repo: Optional[Any] = None,
        media_repo: Optional[MediaRepository] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.asset = asset
        self.pages = pages
        self.queue_repo = queue_repo
        self.media_repo = media_repo

        v_title = asset.get("title") or asset.get("display_title") or Path(asset.get("local_path", "")).stem
        self.setWindowTitle(f"✏ Chỉnh sửa & Đăng video — {v_title}")
        self.resize(650, 700)
        self.setMinimumSize(580, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #0D1627;
                color: #F1F5F9;
            }
            QFrame#cardBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 8px;
            }
            QLabel {
                color: #F1F5F9;
            }
            QLineEdit, QTextEdit, QComboBox, QDateTimeEdit {
                background-color: #0B111D;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                color: #F1F5F9;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
                border: 1px solid #6258E8;
            }
            QPushButton#primaryBtn {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #5348D6;
            }
            QPushButton#quickPublishBtn {
                background-color: #10B981;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton#quickPublishBtn:hover {
                background-color: #059669;
            }
            QPushButton#secondaryBtn {
                background-color: #17243B;
                border: 1px solid #24344D;
                color: #CBD5E1;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #20314F;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        lbl_head = QLabel("✏ Chỉnh sửa nội dung & Đăng video")
        lbl_head.setStyleSheet("font-size: 16px; font-weight: 800; color: #F3F6FC;")
        lbl_sub = QLabel("Tùy chỉnh tiêu đề, nội dung, hashtag, bình luận đầu tiên và đăng nhanh lên Fanpage.")
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        header_layout.addWidget(lbl_head)
        header_layout.addWidget(lbl_sub)
        layout.addLayout(header_layout)

        # 2. Media Preview Card
        media_frame = QFrame()
        media_frame.setObjectName("cardBox")
        mf_layout = QHBoxLayout(media_frame)
        mf_layout.setContentsMargins(12, 10, 12, 10)
        mf_layout.setSpacing(12)

        # Thumbnail or icon
        lbl_thumb = QLabel()
        lbl_thumb.setFixedSize(80, 48)
        lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_thumb.setStyleSheet("background-color: #0B111D; border-radius: 4px; border: 1px solid #1E2D47;")
        t_path = self.asset.get("thumbnail_path")
        if not t_path or not os.path.exists(t_path):
            lp = self.asset.get("local_path", "")
            if lp:
                fb = str(Path(lp).with_suffix(".thumb.jpg"))
                if os.path.exists(fb):
                    t_path = fb
        if t_path and os.path.exists(t_path):
            pix = QPixmap(t_path).scaled(80, 48, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            lbl_thumb.setPixmap(pix)
        else:
            lbl_thumb.setText("🎬 Video")
            lbl_thumb.setStyleSheet("background-color: #0B111D; color: #818CF8; font-weight: 700; border-radius: 4px;")
        mf_layout.addWidget(lbl_thumb)

        # Media metadata info
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(3)
        lp = self.asset.get("local_path", "")
        fname = Path(lp).name if lp else "Video"
        lbl_fname = QLabel(fname)
        lbl_fname.setStyleSheet("font-weight: 700; font-size: 13px; color: #E2E8F0;")
        info_vbox.addWidget(lbl_fname)

        dur = int(self.asset.get("duration", 0) or 0)
        m, s = divmod(dur, 60)
        sz_mb = (self.asset.get("size_bytes", 0) or 0) / (1024 * 1024)
        plat = (self.asset.get("source_platform") or "other").capitalize()
        lbl_minfo = QLabel(f"⏱ {m:02d}:{s:02d} · 💾 {sz_mb:.1f} MB · 🌐 {plat} · 📂 {lp}")
        lbl_minfo.setStyleSheet("font-size: 11px; color: #94A3B8;")
        info_vbox.addWidget(lbl_minfo)
        mf_layout.addLayout(info_vbox, stretch=1)
        layout.addWidget(media_frame)

        # 3. Form chỉnh sửa trong ScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 8, 0)
        form_layout.setSpacing(12)

        # Field 1: Tiêu đề video
        form_layout.addWidget(QLabel("<b>Tiêu đề video:</b>"))
        self.txt_title = QLineEdit()
        init_title = self.asset.get("title") or self.asset.get("display_title") or Path(lp).stem
        self.txt_title.setText(init_title)
        self.txt_title.setPlaceholderText("Nhập tiêu đề video...")
        form_layout.addWidget(self.txt_title)

        # Field 2: Nội dung / Caption bài viết
        lbl_cap_row = QHBoxLayout()
        lbl_cap_row.addWidget(QLabel("<b>Nội dung bài viết (Caption):</b>"))
        lbl_cap_row.addStretch()
        self.lbl_cap_count = QLabel("0 ký tự")
        self.lbl_cap_count.setStyleSheet("font-size: 11px; color: #94A3B8;")
        lbl_cap_row.addWidget(self.lbl_cap_count)
        form_layout.addLayout(lbl_cap_row)

        self.txt_caption = QTextEdit()
        self.txt_caption.setFixedHeight(85)
        init_caption = self.asset.get("caption") or self.asset.get("title") or ""
        self.txt_caption.setPlainText(init_caption)
        self.txt_caption.setPlaceholderText("Nhập lời dẫn, nội dung mô tả cho video khi xuất bản...")
        self.txt_caption.textChanged.connect(self._on_caption_text_changed)
        form_layout.addWidget(self.txt_caption)
        self._on_caption_text_changed()

        # Field 3: Hashtags
        form_layout.addWidget(QLabel("<b>Hashtags (cách nhau bởi dấu cách):</b>"))
        self.txt_hashtags = QLineEdit()
        self.txt_hashtags.setText(self.asset.get("hashtags") or "")
        self.txt_hashtags.setPlaceholderText("Ví dụ: #tiktok #reels #video #viral")
        form_layout.addWidget(self.txt_hashtags)

        # Field 4: Bình luận kèm theo (First Comment)
        cmt_header = QHBoxLayout()
        cmt_header.setSpacing(8)
        lbl_cmt = QLabel("<b>Bình luận kèm theo (First Comment):</b>")
        cmt_header.addWidget(lbl_cmt)
        cmt_header.addStretch()

        self.btn_pick_template = QPushButton("🛍 Chọn nhanh mẫu cmt / SP ▾")
        self.btn_pick_template.setStyleSheet("""
            QPushButton {
                background: #1E2D47;
                color: #A5B4FC;
                border: 1px solid #374B6E;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2A3C59;
                color: #FFFFFF;
                border: 1px solid #6258E8;
            }
        """)
        self.btn_pick_template.clicked.connect(self._open_quick_template_menu)
        cmt_header.addWidget(self.btn_pick_template)

        self.btn_manage_templates = QPushButton("⚙ Quản lý...")
        self.btn_manage_templates.setStyleSheet("""
            QPushButton {
                background: #17243B;
                color: #94A3B8;
                border: 1px solid #2B3D59;
                border-radius: 5px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #20314F;
                color: #E2E8F0;
            }
        """)
        self.btn_manage_templates.clicked.connect(self._open_template_manager)
        cmt_header.addWidget(self.btn_manage_templates)

        form_layout.addLayout(cmt_header)

        self.txt_comment = QTextEdit()
        self.txt_comment.setFixedHeight(65)
        self.txt_comment.setPlainText(self.asset.get("first_comment") or "")
        self.txt_comment.setPlaceholderText("Nhập bình luận sẽ tự động gửi ngay sau khi video được đăng (link affiliate Shopee, câu hỏi tương tác, hashtag bổ sung)...")
        self.txt_comment.textChanged.connect(self._on_comment_text_changed)
        form_layout.addWidget(self.txt_comment)

        # Card xem trước sản phẩm Shopee đính kèm (Live Preview)
        self.product_preview_frame = QFrame()
        self.product_preview_frame.setObjectName("cardBox")
        self.product_preview_frame.setStyleSheet("""
            QFrame#cardBox {
                background: #101B2E;
                border: 1px solid #2C4263;
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        self.product_preview_frame.setVisible(False)
        pv_box = QHBoxLayout(self.product_preview_frame)
        pv_box.setContentsMargins(6, 4, 6, 4)
        pv_box.setSpacing(10)

        self.lbl_cmt_pv_thumb = QLabel()
        self.lbl_cmt_pv_thumb.setFixedSize(44, 44)
        self.lbl_cmt_pv_thumb.setStyleSheet("background: #1E293B; border-radius: 4px;")
        pv_box.addWidget(self.lbl_cmt_pv_thumb)

        pv_info = QVBoxLayout()
        pv_info.setSpacing(2)
        self.lbl_cmt_pv_title = QLabel()
        self.lbl_cmt_pv_title.setStyleSheet("font-weight: 700; color: #F1F5F9; font-size: 12px;")
        self.lbl_cmt_pv_sub = QLabel()
        self.lbl_cmt_pv_sub.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        pv_info.addWidget(self.lbl_cmt_pv_title)
        pv_info.addWidget(self.lbl_cmt_pv_sub)
        pv_box.addLayout(pv_info, stretch=1)

        self.btn_remove_pv = QPushButton("✕ Bỏ")
        self.btn_remove_pv.setToolTip("Ẩn thẻ xem trước này")
        self.btn_remove_pv.setFixedSize(45, 26)
        self.btn_remove_pv.setStyleSheet("background: #334155; color: #E2E8F0; border-radius: 4px; font-size: 11px;")
        self.btn_remove_pv.clicked.connect(self._on_remove_product_preview)
        pv_box.addWidget(self.btn_remove_pv)

        form_layout.addWidget(self.product_preview_frame)

        # Field 5: Cấu hình đăng bài (Fanpage & Định dạng)
        config_frame = QFrame()
        config_frame.setObjectName("cardBox")
        cfg_layout = QVBoxLayout(config_frame)
        cfg_layout.setContentsMargins(12, 12, 12, 12)
        cfg_layout.setSpacing(10)

        lbl_cfg_title = QLabel("⚙ CẤU HÌNH XUẤT BẢN")
        lbl_cfg_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #818CF8;")
        cfg_layout.addWidget(lbl_cfg_title)

        row_cfg = QHBoxLayout()
        row_cfg.setSpacing(12)

        # Fanpage đích
        vbox_p = QVBoxLayout()
        vbox_p.setSpacing(4)
        vbox_p.addWidget(QLabel("Fanpage đích:"))
        self.cb_page = QComboBox()
        self.cb_page.addItem("✕ Chưa chọn Fanpage", "")
        current_target_pid = str(self.asset.get("target_page_id") or "")
        selected_idx = 0

        for idx, p in enumerate(self.pages, start=1):
            pid = str(p.get("id") or p.get("page_id") or p.get("facebook_page_id"))
            pname = p.get("name") or p.get("page_name") or f"Page {pid}"
            status = str(p.get("status") or "ready")
            status_text = " ⚠ (Hết hạn)" if status in ("token_expired", "expired") else ""
            self.cb_page.addItem(f"📄 {pname}{status_text}", pid)
            if pid == current_target_pid:
                selected_idx = idx

        self.cb_page.setCurrentIndex(selected_idx)
        vbox_p.addWidget(self.cb_page)
        row_cfg.addLayout(vbox_p, stretch=1)

        # Loại bài đăng
        vbox_t = QVBoxLayout()
        vbox_t.setSpacing(4)
        vbox_t.addWidget(QLabel("Định dạng đăng:"))
        self.cb_content_type = QComboBox()
        self.cb_content_type.addItem("Facebook Reels (Khuyên dùng)", "reels")
        self.cb_content_type.addItem("Video bài viết thông thường", "video")
        vbox_t.addWidget(self.cb_content_type)
        row_cfg.addLayout(vbox_t, stretch=1)

        cfg_layout.addLayout(row_cfg)
        form_layout.addWidget(config_frame)

        scroll.setWidget(form_widget)
        layout.addWidget(scroll, stretch=1)

        # 4. Footer Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addStretch()

        self.btn_save = QPushButton("💾 Lưu thông tin")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.btn_save)

        self.btn_quick_publish = QPushButton("⚡ Đăng nhanh ngay")
        self.btn_quick_publish.setObjectName("quickPublishBtn")
        self.btn_quick_publish.clicked.connect(self._on_quick_publish_clicked)
        layout.addLayout(btn_row)

        # Tự động kiểm tra và hiển thị xem trước nếu đã có link trong bình luận
        init_cmt = self.asset.get("first_comment") or ""
        if init_cmt:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self._on_comment_text_changed)

    def _open_quick_template_menu(self) -> None:
        """Hiển thị menu chọn nhanh mẫu câu bình luận / sản phẩm Shopee."""
        from src.lovira.storage.comment_repository import ReplyTemplateRepository
        reply_repo = ReplyTemplateRepository.get_instance()
        if not reply_repo and self.media_repo and hasattr(self.media_repo, "db"):
            reply_repo = ReplyTemplateRepository.get_instance(self.media_repo.db)

        templates = reply_repo.list_templates() if reply_repo else []
        if not templates:
            reply = QMessageBox.question(
                self,
                "Chưa có mẫu câu",
                "Thư viện chưa có mẫu câu bình luận hoặc sản phẩm Shopee nào.\nBạn có muốn mở khung quản lý để thêm hoặc nhập danh sách không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_template_manager()
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131D2E;
                border: 1px solid #2B3D59;
                border-radius: 8px;
                padding: 6px;
                color: #F1F5F9;
                font-size: 12px;
                min-width: 260px;
            }
            QMenu::item {
                padding: 8px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #241E5C;
                color: #A5B4FC;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1E2D47;
                margin: 4px 6px;
            }
        """)

        act_manage = menu.addAction("⚙ Quản lý & Nhập danh sách mẫu câu...")
        menu.addSeparator()

        act_map = {}
        for tpl in templates[:30]:
            name = tpl.get("name") or "Mẫu câu"
            price = tpl.get("price")
            prefix = "🛍 " if tpl.get("product_url") else "💬 "
            price_str = f" [{price}]" if price else ""
            act = menu.addAction(f"{prefix}{name}{price_str}")
            act_map[act] = tpl

        chosen = menu.exec(QCursor.pos())
        if chosen == act_manage:
            self._open_template_manager()
        elif chosen in act_map:
            self._apply_template(act_map[chosen])

    def _open_template_manager(self) -> None:
        from src.lovira.storage.comment_repository import ReplyTemplateRepository
        from src.lovira.ui.views.comments_workspace import TemplateManagerDialog
        reply_repo = ReplyTemplateRepository.get_instance()
        if not reply_repo and self.media_repo and hasattr(self.media_repo, "db"):
            reply_repo = ReplyTemplateRepository.get_instance(self.media_repo.db)

        if not reply_repo:
            QMessageBox.information(self, "Thông báo", "Cơ sở dữ liệu mẫu câu chưa sẵn sàng.")
            return

        dlg = TemplateManagerDialog(reply_repo, is_picker=True, parent=self)
        dlg.template_selected.connect(self._apply_template)
        dlg.exec()

    def _apply_template(self, tpl: dict) -> None:
        content = tpl.get("content") or ""
        self.txt_comment.setPlainText(content)

        title = tpl.get("name") or ""
        price = tpl.get("price") or ""
        local_img = tpl.get("local_image_path") or ""
        prod_url = tpl.get("product_url") or ""

        if prod_url or local_img or title:
            self._show_product_preview(title=title, price=price, local_image_path=local_img, url=prod_url)

    def _show_product_preview(self, title: str, price: str, local_image_path: str, url: str) -> None:
        self.product_preview_frame.setVisible(True)
        self.lbl_cmt_pv_title.setText(title or url)
        self.lbl_cmt_pv_sub.setText(f"Giá: {price}" if price else "Sản phẩm Shopee đính kèm")

        if local_image_path and os.path.exists(local_image_path):
            pix = QPixmap(local_image_path)
            if not pix.isNull():
                self.lbl_cmt_pv_thumb.setPixmap(
                    pix.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                )

    def _on_comment_text_changed(self) -> None:
        text = self.txt_comment.toPlainText()
        from src.lovira.services.link_preview import LinkPreviewService
        srv = LinkPreviewService.get_instance()
        urls = srv.extract_urls(text)
        if urls and not self.product_preview_frame.isVisible():
            first_url = urls[0]
            if srv.is_shopee_url(first_url):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(400, lambda: self._scan_comment_link(first_url))

    def _scan_comment_link(self, url: str) -> None:
        from src.lovira.services.link_preview import AsyncLinkPreviewWorker
        if hasattr(self, "_active_cmt_worker") and self._active_cmt_worker and self._active_cmt_worker.isRunning():
            self._active_cmt_worker.terminate()
        self._active_cmt_worker = AsyncLinkPreviewWorker(url, parent=self)
        self._active_cmt_worker.preview_ready.connect(self._on_comment_preview_ready)
        self._active_cmt_worker.start()

    def _on_comment_preview_ready(self, data: dict) -> None:
        self._show_product_preview(
            title=data.get("title", ""),
            price=data.get("price", ""),
            local_image_path=data.get("local_image_path", ""),
            url=data.get("url", ""),
        )

    def _on_remove_product_preview(self) -> None:
        self.product_preview_frame.setVisible(False)

    def _on_caption_text_changed(self) -> None:
        text = self.txt_caption.toPlainText()
        self.lbl_cap_count.setText(f"{len(text)} ký tự")

    def _save_to_db(self) -> Tuple[str, str, str, str, Optional[str]]:
        """Lưu toàn bộ thay đổi vào cơ sở dữ liệu media_assets."""
        title = self.txt_title.text().strip()
        caption = self.txt_caption.toPlainText().strip()
        hashtags = self.txt_hashtags.text().strip()
        first_comment = self.txt_comment.toPlainText().strip()
        target_pid = self.cb_page.currentData() or None

        asset_id = self.asset["id"]
        if self.media_repo:
            self.media_repo.update_asset_full_metadata(
                asset_id=asset_id,
                title=title,
                caption=caption,
                hashtags=hashtags,
                first_comment=first_comment,
                target_page_id=target_pid,
            )

        # Cập nhật dict tại chỗ
        self.asset["title"] = title
        self.asset["caption"] = caption
        self.asset["hashtags"] = hashtags
        self.asset["first_comment"] = first_comment
        self.asset["target_page_id"] = target_pid

        return title, caption, hashtags, first_comment, target_pid

    def _on_save_clicked(self) -> None:
        self._save_to_db()
        QMessageBox.information(self, "Đã lưu", "Đã cập nhật thông tin video thành công.")
        self.accept()

    def _on_quick_publish_clicked(self) -> None:
        target_pid = self.cb_page.currentData()
        if not target_pid:
            QMessageBox.warning(self, "Chưa chọn Fanpage", "Vui lòng chọn Fanpage đích để thực hiện đăng nhanh.")
            return

        # Lưu thay đổi trước khi đăng
        title, caption, hashtags, first_comment, target_pid = self._save_to_db()

        # Tạo nội dung hoàn chỉnh
        final_caption = caption or title
        if hashtags and hashtags not in final_caption:
            final_caption = f"{final_caption}\n\n{hashtags}".strip()

        from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
        from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso

        ctype_str = self.cb_content_type.currentData() or "reels"
        content_type = ContentType.REELS if ctype_str == "reels" else ContentType.VIDEO

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        request_id = f"quick_pub_{uuid.uuid4().hex[:8]}"
        scheduled_utc = vn_datetime_to_utc_iso(vn_now())

        snapshot = ContentSnapshot(
            batch_id=batch_id,
            page_id=target_pid,
            content_type=content_type,
            final_caption=final_caption,
            primary_media_id=self.asset.get("id"),
            media_checksum=self.asset.get("checksum"),
            media_path=self.asset.get("local_path"),
            scheduled_at_utc=scheduled_utc,
            schedule_mode=ScheduleMode.LOCAL,
            title=title,
            first_comment=first_comment or None,
        )

        if not self.queue_repo:
            QMessageBox.information(
                self,
                "Đăng nhanh",
                "Đã lưu thông tin video thành công.\n(Hàng đợi xuất bản chưa kết nối trong phiên này).",
            )
            self.accept()
            return

        try:
            jobs = self.queue_repo.enqueue_batch(request_id, [snapshot])
            self.post_published.emit(jobs)
            page_name = self.cb_page.currentText()
            comment_note = "\n• Kèm theo bình luận đầu tiên tự động." if first_comment else ""
            QMessageBox.information(
                self,
                "Đăng nhanh thành công",
                f"⚡ Đã đưa bài đăng vào hàng đợi xuất bản thành công!\n\n"
                f"• Fanpage: {page_name}\n"
                f"• Định dạng: {self.cb_content_type.currentText()}{comment_note}\n\n"
                f"Hệ thống đang tiến hành xử lý và đăng video lên Fanpage.",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đăng nhanh", f"Không thể tạo tác vụ đăng bài:\n{e}")


# =========================================================================
# TAB 2: THƯ VIỆN MEDIA 2.0 (GRID UX REFACTOR)
# =========================================================================

class MediaLibraryTab(QWidget):
    """
    Tab Thư viện Media 2.0 (Grid UX Refactor):
    - Thumbnail Grid trực quan (QListView IconMode + QStyledItemDelegate)
    - Tương thích ngược toàn bộ với tests (giữ self.table, cb_filter_platform, search_filter, content_stack)
    - Thanh tác vụ theo ngữ cảnh ở đáy màn hình (chỉ hiện khi chọn >= 1 video)
    - Dropdown Fanpage popup searchable multi-select
    - Bảo vệ an toàn AC-12/AC-42 chặn xóa video đang có lịch hẹn
    """

    send_to_composer = Signal(dict)
    switch_to_download_requested = Signal()
    batch_schedule_created = Signal(list)

    def __init__(
        self,
        media_repo: MediaRepository,
        page_repo: Optional[Any] = None,
        queue_repo: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.media_repo = media_repo
        self.page_repo = page_repo
        self.queue_repo = queue_repo

        self._cached_assets: List[Dict[str, Any]] = []
        self._filtered_assets: List[Dict[str, Any]] = []
        self._usage_summary_map: Dict[str, Dict[str, Any]] = {}
        self._selected_page_ids: List[str] = []
        self._active_status_filter: Optional[str] = None
        self._is_grid_view_mode: bool = True

        self._init_ui()
        self.reload_media_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. HEADER (TIÊU ĐỀ, SỐ LIỆU TỔNG QUAN, NÚT REFRESH & + TẢI VIDEO)
        # -------------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        self.title_lbl = QLabel("Thư viện Media")
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #F3F6FC;")

        self.subtitle_lbl = QLabel("0 video · 0 đang lên lịch · 0 đã sử dụng")
        self.subtitle_lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")

        header_box.addWidget(self.title_lbl)
        header_box.addWidget(self.subtitle_lbl)
        header_row.addLayout(header_box)
        header_row.addStretch()

        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(get_icon("refresh", "#A9B8CF", 16))
        self.btn_refresh.setToolTip("Làm mới danh sách media")
        self.btn_refresh.setFixedSize(36, 34)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #17243B;
                border: 1px solid #24344D;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #20314F;
            }
        """)
        self.btn_refresh.clicked.connect(self.reload_media_list)
        header_row.addWidget(self.btn_refresh)

        self.btn_go_download = QPushButton(" + Tải video")
        self.btn_go_download.setFixedHeight(34)
        self.btn_go_download.setStyleSheet("""
            QPushButton {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #5348D6;
            }
        """)
        self.btn_go_download.clicked.connect(self.switch_to_download_requested.emit)
        header_row.addWidget(self.btn_go_download)

        layout.addLayout(header_row)

        # -------------------------------------------------------------
        # 2. THANH CÔNG CỤ LỌC & TÌM KIẾM (TOOLBAR GỌN ĐẸP)
        # -------------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        # Ô tìm kiếm
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("🔍 Tìm video theo tên, tác giả, đường dẫn...")
        self.search_filter.setFixedHeight(34)
        self.search_filter.setStyleSheet("""
            QLineEdit {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                padding: 6px 12px;
                color: #F1F5F9;
                font-size: 12px;
            }
            QLineEdit:hover {
                border: 1px solid #2B3D59;
            }
            QLineEdit:focus {
                border: 1px solid #6258E8;
                background-color: #162238;
            }
        """)
        self.search_filter.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_filter, stretch=1)

        combo_qss = """
            QComboBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                padding: 4px 10px;
                color: #E2E8F0;
                font-size: 12px;
                min-width: 95px;
            }
            QComboBox:hover {
                border: 1px solid #2E4366;
            }
            QComboBox:focus {
                border: 1px solid #6258E8;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #94A3B8;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #131D2E;
                border: 1px solid #2B3D59;
                border-radius: 6px;
                selection-background-color: #241E5C;
                selection-color: #FFFFFF;
                color: #F1F5F9;
                padding: 4px;
            }
        """

        # Dropdown Nền tảng
        self.cb_filter_platform = QComboBox()
        self.cb_filter_platform.setFixedHeight(34)
        self.cb_filter_platform.addItems(["Tất cả", "TikTok", "Douyin", "Bilibili", "Khác"])
        self.cb_filter_platform.setStyleSheet(combo_qss)
        self.cb_filter_platform.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cb_filter_platform)

        # Dropdown Trạng thái (ẩn trên UI để tránh trùng lặp với hàng pills bên dưới, giữ biến để tương thích test)
        self.cb_filter_status = QComboBox()
        self.cb_filter_status.setVisible(False)
        self.cb_filter_status.addItems([
            "Trạng thái: Tất cả",
            "Chưa sử dụng",
            "Đã lên lịch",
            "Đã đăng",
            "Có lỗi",
            "File thất lạc",
        ])
        self.cb_filter_status.currentIndexChanged.connect(self._on_status_combo_changed)

        # Dropdown Sắp xếp
        self.cb_sort = QComboBox()
        self.cb_sort.setFixedHeight(34)
        self.cb_sort.addItems(["Mới nhất", "Cũ nhất", "Tên A–Z", "Dung lượng", "Thời lượng"])
        self.cb_sort.setStyleSheet(combo_qss)
        self.cb_sort.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cb_sort)

        # Toggle Lưới [Grid] / Danh sách [List]
        self.btn_view_grid = QPushButton()
        self.btn_view_grid.setToolTip("Chế độ xem dạng lưới (Grid)")
        self.btn_view_grid.setFixedSize(34, 34)
        self.btn_view_grid.setIcon(get_icon("grid", "#FFFFFF", 16))
        self.btn_view_grid.setIconSize(QSize(16, 16))
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setChecked(True)
        self.btn_view_grid.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_view_list = QPushButton()
        self.btn_view_list.setToolTip("Chế độ xem danh sách (List)")
        self.btn_view_list.setFixedSize(34, 34)
        self.btn_view_list.setIcon(get_icon("list", "#64748B", 16))
        self.btn_view_list.setIconSize(QSize(16, 16))
        self.btn_view_list.setCheckable(True)
        self.btn_view_list.setCursor(Qt.CursorShape.PointingHandCursor)

        view_toggle_group = QButtonGroup(self)
        view_toggle_group.addButton(self.btn_view_grid)
        view_toggle_group.addButton(self.btn_view_list)

        toggle_style = """
            QPushButton {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #1E2D47;
                border: 1px solid #334460;
            }
            QPushButton:checked {
                background-color: #241E5C;
                border: 1px solid #6258E8;
            }
        """
        self.btn_view_grid.setStyleSheet(toggle_style)
        self.btn_view_list.setStyleSheet(toggle_style)
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode(True))
        self.btn_view_list.clicked.connect(lambda: self._set_view_mode(False))

        filter_row.addWidget(self.btn_view_grid)
        filter_row.addWidget(self.btn_view_list)

        layout.addLayout(filter_row)

        # -------------------------------------------------------------
        # 3. DÒNG THỐNG KÊ FILTER PILLS / COUNTS SUMMARY (CHIP BADGES HIỆN ĐẠI)
        # -------------------------------------------------------------
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(6)

        self.lbl_pill_all = QLabel("Tất cả (0)")
        self.lbl_pill_unused = QLabel("Chưa sử dụng (0)")
        self.lbl_pill_scheduled = QLabel("Đã lên lịch (0)")
        self.lbl_pill_published = QLabel("Đã đăng (0)")
        self.lbl_pill_failed = QLabel("Có lỗi (0)")

        for lbl in (self.lbl_pill_all, self.lbl_pill_unused, self.lbl_pill_scheduled, self.lbl_pill_published, self.lbl_pill_failed):
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_pill_all.mousePressEvent = lambda _: self._on_pill_clicked(None)
        self.lbl_pill_unused.mousePressEvent = lambda _: self._on_pill_clicked("unused")
        self.lbl_pill_scheduled.mousePressEvent = lambda _: self._on_pill_clicked("scheduled")
        self.lbl_pill_published.mousePressEvent = lambda _: self._on_pill_clicked("published")
        self.lbl_pill_failed.mousePressEvent = lambda _: self._on_pill_clicked("failed")

        self.summary_row.addWidget(self.lbl_pill_all)
        self.summary_row.addWidget(self.lbl_pill_unused)
        self.summary_row.addWidget(self.lbl_pill_scheduled)
        self.summary_row.addWidget(self.lbl_pill_published)
        self.summary_row.addWidget(self.lbl_pill_failed)
        self.summary_row.addStretch()

        self.btn_select_all_top = QPushButton("☑ Chọn tất cả")
        self.btn_select_all_top.setToolTip("Chọn tất cả video trong danh sách hiển thị")
        self.btn_select_all_top.setFixedHeight(28)
        self.btn_select_all_top.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all_top.setStyleSheet("""
            QPushButton {
                background-color: #17243B;
                border: 1px solid #24344D;
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 11px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #20314F;
                color: #FFFFFF;
                border: 1px solid #6258E8;
            }
        """)
        self.btn_select_all_top.clicked.connect(self._select_all_videos)
        self.summary_row.addWidget(self.btn_select_all_top)

        self.btn_clear_top = QPushButton("Bỏ chọn")
        self.btn_clear_top.setToolTip("Bỏ chọn tất cả video")
        self.btn_clear_top.setFixedHeight(28)
        self.btn_clear_top.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_top.setStyleSheet(self.btn_select_all_top.styleSheet())
        self.btn_clear_top.clicked.connect(self._clear_all_selection)
        self.summary_row.addWidget(self.btn_clear_top)

        layout.addLayout(self.summary_row)
        self._update_pill_visuals()

        # -------------------------------------------------------------
        # 4. CONTENT STACK: VIEW CHÍNH & EMPTY STATES
        # -------------------------------------------------------------
        self.content_stack = QStackedLayout()

        # VIEW 1: VÙNG HIỂN THỊ MEDIA (GỒM GRID VÀ LIST VIEW)
        self.content_container = QWidget()
        content_container_layout = QVBoxLayout(self.content_container)
        content_container_layout.setContentsMargins(0, 0, 0, 0)
        content_container_layout.setSpacing(0)

        self.view_stack = QStackedLayout()

        # View 1.1: Grid View (QListView IconMode)
        self.model = MediaAssetListModel(self)
        self.grid_view = MediaGridView(self)
        self.grid_view.setModel(self.model)
        self.delegate = MediaCardDelegate(self)
        self.delegate.checkbox_clicked.connect(self._toggle_checkbox_selection)
        self.delegate.page_picker_clicked.connect(self._on_card_page_picker_clicked)
        self.delegate.edit_post_clicked.connect(self._on_card_edit_clicked)
        self.grid_view.setItemDelegate(self.delegate)
        self.grid_view.item_double_clicked_preview.connect(self._preview_media_id)
        self.grid_view.delete_pressed.connect(self._on_delete_selected)
        self.grid_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid_view.customContextMenuRequested.connect(self._show_grid_context_menu)
        self.grid_view.selectionModel().selectionChanged.connect(self._on_grid_selection_changed)

        self.view_stack.addWidget(self.grid_view)

        # View 1.2: Table View (Giữ nguyên để tương thích ngược hoàn hảo với test)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nền tảng", "Đường dẫn file", "Thời lượng", "Dung lượng", "Ngày tạo", "Thao tác"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 120)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(6, 90)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        self.view_stack.addWidget(self.table)
        content_container_layout.addLayout(self.view_stack, stretch=1)
        self.content_stack.addWidget(self.content_container)

        # VIEW 2: EMPTY STATE
        self.empty_container = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_container)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_state = EmptyState.no_media(on_download=self.switch_to_download_requested.emit)
        self.empty_layout.addWidget(self.empty_state)
        self.content_stack.addWidget(self.empty_container)

        layout.addLayout(self.content_stack, stretch=1)

        # -------------------------------------------------------------
        # 5. THANH THAO TÁC NGỮ CẢNH Ở ĐÁY (CONTEXTUAL TOOLBAR)
        # -------------------------------------------------------------
        self.selection_bar = QFrame()
        self.selection_bar.setObjectName("selectionBar")
        self.selection_bar.setFixedHeight(48)
        self.selection_bar.setStyleSheet("""
            QFrame#selectionBar {
                background-color: #141E33;
                border: 1px solid #24344D;
                border-radius: 8px;
                padding: 0 12px;
            }
            QLabel {
                color: #F1F5F9;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #1E2D47;
                color: #E2E8F0;
                border: 1px solid #334460;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #293B5C;
            }
            QPushButton#primaryAction {
                background-color: #6258E8;
                color: #FFFFFF;
                border: none;
                font-weight: 700;
            }
            QPushButton#primaryAction:hover {
                background-color: #5348D6;
            }
            QPushButton#quickPublishAction {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #F59E0B, stop:1 #D97706);
                color: #FFFFFF;
                border: none;
                font-weight: 700;
            }
            QPushButton#quickPublishAction:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FBBF24, stop:1 #B45309);
            }
        """)

        bar_layout = QHBoxLayout(self.selection_bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(10)

        self.lbl_selected_count = QLabel("Đã chọn 0 video")
        bar_layout.addWidget(self.lbl_selected_count)

        self.btn_select_all = QPushButton("Chọn tất cả")
        self.btn_select_all.clicked.connect(self._select_all_videos)
        bar_layout.addWidget(self.btn_select_all)

        self.btn_clear_selection = QPushButton("Bỏ chọn")
        self.btn_clear_selection.clicked.connect(self._clear_all_selection)
        bar_layout.addWidget(self.btn_clear_selection)

        bar_layout.addStretch()

        # Dropdown chọn Fanpage
        self.btn_fanpage_picker = QPushButton("Fanpage đích: [ Chọn Fanpage ▾ ]")
        self.btn_fanpage_picker.clicked.connect(self._open_fanpage_picker)
        bar_layout.addWidget(self.btn_fanpage_picker)

        # Nút Đăng nhanh
        self.btn_quick_publish_selected = QPushButton("⚡ Đăng nhanh")
        self.btn_quick_publish_selected.setObjectName("quickPublishAction")
        self.btn_quick_publish_selected.clicked.connect(self._on_quick_publish_selected)
        bar_layout.addWidget(self.btn_quick_publish_selected)

        # Nút Soạn bài
        self.btn_compose_selected = QPushButton("🎬 Soạn bài")
        self.btn_compose_selected.setObjectName("primaryAction")
        self.btn_compose_selected.clicked.connect(self._on_compose_selected)
        bar_layout.addWidget(self.btn_compose_selected)

        # Nút Đặt lịch
        self.btn_schedule_selected = QPushButton("📅 Đặt lịch")
        self.btn_schedule_selected.clicked.connect(self._on_schedule_selected)
        bar_layout.addWidget(self.btn_schedule_selected)

        # Nút menu ba chấm (···)
        self.btn_more_actions = QPushButton("···")
        self.btn_more_actions.setFixedWidth(36)
        self.btn_more_actions.clicked.connect(self._show_batch_more_menu)
        bar_layout.addWidget(self.btn_more_actions)

        # Nút Xóa video (Giữ lại tham chiếu tương thích ngược test)
        self.btn_delete_selected = QPushButton("🗑 Xóa video")
        self.btn_delete_selected.setObjectName("dangerButton")
        self.btn_delete_selected.setVisible(False)
        self.btn_delete_selected.clicked.connect(self._on_delete_selected)
        bar_layout.addWidget(self.btn_delete_selected)

        # Ẩn selection bar mặc định khi chưa chọn video nào
        self.selection_bar.setVisible(False)
        layout.addWidget(self.selection_bar)

        # Nút legacy mở rộng để tương thích các unit test
        self.btn_watch = QPushButton()
        self.btn_open_folder = QPushButton()

    # =========================================================================
    # LOGIC NẠP & LỌC DỮ LIỆU
    # =========================================================================

    def reload_media_list(self) -> None:
        """Nạp danh sách media assets từ cơ sở dữ liệu và cập nhật thông tin sử dụng."""
        self._cached_assets = self.media_repo.list_media_assets(platform=None, limit=500)
        asset_ids = [a["id"] for a in self._cached_assets if "id" in a]

        # Lấy danh sách tên page từ page_repo
        page_name_map = {}
        if self.page_repo:
            try:
                pages = self.page_repo.list_pages()
                for p in pages:
                    pid = str(p.get("id") or p.get("page_id") or p.get("facebook_page_id"))
                    pname = p.get("name") or p.get("page_name") or f"Page {pid}"
                    page_name_map[pid] = pname
            except Exception:
                pass

        # Lấy trạng thái tổng hợp bài đăng / lịch / lỗi
        try:
            self._usage_summary_map = self.media_repo.get_media_usage_summary(asset_ids)
        except Exception as e:
            logger.debug(f"Không thể lấy usage summary: {e}")
            self._usage_summary_map = {}

        # Gắn trạng thái hiển thị và thông tin trang/tiêu đề/hashtag vào từng asset
        for item in self._cached_assets:
            aid = item.get("id")
            usage = self._usage_summary_map.get(aid, {})
            lp = item.get("local_path", "")
            file_exists = os.path.exists(lp) if lp else False

            sched_count = len(usage.get("scheduled_jobs", []))
            pub_count = len(usage.get("published_jobs", []))
            fail_count = len(usage.get("failed_jobs", []))
            draft_count = usage.get("draft_count", 0)

            if not file_exists:
                item["ui_status_key"] = "missing"
                item["ui_status_text"] = "File thất lạc"
            elif fail_count > 0:
                item["ui_status_key"] = "failed"
                item["ui_status_text"] = f"Đăng lỗi ({fail_count})"
            elif sched_count > 0:
                item["ui_status_key"] = "scheduled"
                item["ui_status_text"] = f"Đã lên lịch ({sched_count})"
            elif pub_count > 0:
                item["ui_status_key"] = "published"
                item["ui_status_text"] = f"Đã đăng ({pub_count})"
            elif draft_count > 0:
                item["ui_status_key"] = "draft"
                item["ui_status_text"] = "Trong bản nháp"
            else:
                item["ui_status_key"] = "unused"
                item["ui_status_text"] = "Chưa sử dụng"

            # Ánh xạ tên Fanpage đích
            target_pid = str(item.get("target_page_id") or "")
            item["target_page_name"] = page_name_map.get(target_pid, "")

            # Trích xuất tiêu đề & hashtags nếu chưa có
            if not item.get("title") and item.get("tags"):
                raw_tag = item.get("tags", "")
                tags_found = re.findall(r"#\S+", raw_tag)
                item["hashtags"] = " ".join(tags_found)
                item["title"] = re.sub(r"#\S+", "", raw_tag).strip() or raw_tag
            elif not item.get("title") and lp:
                # Kiểm tra xem có caption từ publish jobs không
                for job_list in (usage.get("scheduled_jobs", []), usage.get("published_jobs", [])):
                    if job_list and isinstance(job_list, list):
                        j0 = job_list[0]
                        cap = j0.get("snapshot_caption") or ""
                        if cap:
                            item["hashtags"] = " ".join(re.findall(r"#\S+", cap))
                            item["title"] = re.sub(r"#\S+", "", cap).strip() or cap
                            # Lưu vào db
                            try:
                                self.media_repo.update_metadata(aid, item["title"], item["hashtags"])
                            except Exception:
                                pass
                            break

        self._update_header_stats()
        self._apply_filters()

    def _update_header_stats(self) -> None:
        total = len(self._cached_assets)
        scheduled = sum(1 for a in self._cached_assets if a.get("ui_status_key") == "scheduled")
        published = sum(1 for a in self._cached_assets if a.get("ui_status_key") == "published")
        failed = sum(1 for a in self._cached_assets if a.get("ui_status_key") == "failed")
        unused = sum(1 for a in self._cached_assets if a.get("ui_status_key") == "unused")

        self.subtitle_lbl.setText(f"{total} video · {scheduled} đang lên lịch · {published} đã sử dụng")
        self.lbl_pill_all.setText(f"Tất cả ({total})")
        self.lbl_pill_unused.setText(f"Chưa sử dụng ({unused})")
        self.lbl_pill_scheduled.setText(f"Đã lên lịch ({scheduled})")
        self.lbl_pill_published.setText(f"Đã đăng ({published})")
        self.lbl_pill_failed.setText(f"Có lỗi ({failed})")
        self._update_pill_visuals()

    def _apply_filters(self) -> None:
        platform_filter = self.cb_filter_platform.currentText().lower()
        if platform_filter == "tất cả":
            platform_filter = None

        search_query = self.search_filter.text().strip().lower()

        filtered = []
        for item in self._cached_assets:
            if platform_filter:
                item_platform = (item.get("source_platform") or "").lower()
                if platform_filter != item_platform:
                    continue

            if self._active_status_filter:
                if item.get("ui_status_key") != self._active_status_filter:
                    continue

            if search_query:
                item_id = item.get("id", "").lower()
                item_path = item.get("local_path", "").lower()
                item_title = (item.get("display_title") or Path(item_path).stem).lower()
                item_tags = (item.get("tags") or "").lower()
                if (
                    search_query not in item_id
                    and search_query not in item_path
                    and search_query not in item_title
                    and search_query not in item_tags
                ):
                    continue

            filtered.append(item)

        # Sắp xếp
        sort_mode = self.cb_sort.currentText()
        if sort_mode == "Mới nhất":
            filtered.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        elif sort_mode == "Cũ nhất":
            filtered.sort(key=lambda x: x.get("created_at") or "")
        elif sort_mode == "Tên A–Z":
            filtered.sort(key=lambda x: (x.get("display_title") or Path(x.get("local_path", "")).stem).lower())
        elif sort_mode == "Dung lượng":
            filtered.sort(key=lambda x: x.get("size_bytes", 0) or 0, reverse=True)
        elif sort_mode == "Thời lượng":
            filtered.sort(key=lambda x: x.get("duration", 0) or 0, reverse=True)

        self._filtered_assets = filtered

        # Cập nhật View và EmptyState
        if not filtered:
            self._show_empty_state()
            self.model.set_assets([])
            self.table.setRowCount(0)
            self._update_selection_bar()
            return

        self.content_stack.setCurrentIndex(0)
        self.model.set_assets(filtered)
        self._populate_table(filtered)
        self._update_selection_bar()

    def _show_empty_state(self) -> None:
        self.content_stack.setCurrentIndex(1)
        # Xóa widget cũ trong empty layout
        while self.empty_layout.count():
            w = self.empty_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not self._cached_assets:
            self.empty_state = EmptyState.no_media(on_download=self.switch_to_download_requested.emit)
        else:
            # Có video nhưng filter không có kết quả
            self.empty_state = EmptyState(
                icon_name="search",
                title="Không tìm thấy video nào",
                description="Không có video nào khớp với điều kiện tìm kiếm hoặc bộ lọc hiện tại.",
                action_text="Xóa bộ lọc",
            )
            self.empty_state.action_clicked.connect(self._reset_filters)
        self.empty_layout.addWidget(self.empty_state)

    def _reset_filters(self) -> None:
        self.search_filter.clear()
        self.cb_filter_platform.setCurrentIndex(0)
        self.cb_filter_status.setCurrentIndex(0)
        self._active_status_filter = None
        self._apply_filters()

    def _populate_table(self, filtered: List[Dict[str, Any]]) -> None:
        """Đồng bộ dữ liệu sang QTableWidget để giữ tương thích 100% với các test cũ."""
        self.table.setRowCount(len(filtered))
        for row, item in enumerate(filtered):
            self.table.setItem(row, 0, QTableWidgetItem(item["id"]))
            self.table.setItem(row, 1, QTableWidgetItem((item.get("source_platform") or "other").upper()))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("local_path", "")))

            dur = int(item.get("duration", 0) or 0)
            m, s = divmod(dur, 60)
            self.table.setItem(row, 3, QTableWidgetItem(f"{m:02d}:{s:02d}"))

            size_mb = (item.get("size_bytes", 0) or 0) / (1024 * 1024)
            self.table.setItem(row, 4, QTableWidgetItem(f"{size_mb:.1f} MB"))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("created_at", "")))

            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_play = QPushButton("▶ Xem")
            btn_play.setFixedWidth(62)
            btn_play.setFixedHeight(24)
            file_p = item.get("local_path", "")
            btn_play.clicked.connect(lambda _, fp=file_p: QDesktopServices.openUrl(QUrl.fromLocalFile(fp)))
            cell_layout.addWidget(btn_play)
            self.table.setCellWidget(row, 6, cell_widget)

    def _set_view_mode(self, is_grid: bool) -> None:
        self._is_grid_view_mode = is_grid
        self.btn_view_grid.setChecked(is_grid)
        self.btn_view_list.setChecked(not is_grid)
        self.btn_view_grid.setIcon(get_icon("grid", "#FFFFFF" if is_grid else "#64748B", 16))
        self.btn_view_list.setIcon(get_icon("list", "#64748B" if is_grid else "#FFFFFF", 16))
        self.view_stack.setCurrentIndex(0 if is_grid else 1)

    def _on_status_combo_changed(self, index: int) -> None:
        mapping = {
            0: None,
            1: "unused",
            2: "scheduled",
            3: "published",
            4: "failed",
            5: "missing",
        }
        self._active_status_filter = mapping.get(index)
        self._update_pill_visuals()
        self._apply_filters()

    def _on_pill_clicked(self, status_key: Optional[str]) -> None:
        self._active_status_filter = status_key
        rev_mapping = {
            None: 0,
            "unused": 1,
            "scheduled": 2,
            "published": 3,
            "failed": 4,
            "missing": 5,
        }
        self.cb_filter_status.setCurrentIndex(rev_mapping.get(status_key, 0))
        self._update_pill_visuals()
        self._apply_filters()

    def _update_pill_visuals(self) -> None:
        pills_map = {
            None: self.lbl_pill_all,
            "unused": self.lbl_pill_unused,
            "scheduled": self.lbl_pill_scheduled,
            "published": self.lbl_pill_published,
            "failed": self.lbl_pill_failed,
        }
        for key, lbl in pills_map.items():
            is_active = (self._active_status_filter == key)
            if is_active:
                lbl.setStyleSheet("""
                    QLabel {
                        background-color: #241E5C;
                        border: 1px solid #6258E8;
                        color: #FFFFFF;
                        font-size: 12px;
                        font-weight: 700;
                        padding: 4px 12px;
                        border-radius: 13px;
                    }
                """)
            else:
                lbl.setStyleSheet("""
                    QLabel {
                        background-color: #111A2B;
                        border: 1px solid #1E293B;
                        color: #94A3B8;
                        font-size: 12px;
                        font-weight: 500;
                        padding: 4px 12px;
                        border-radius: 13px;
                    }
                    QLabel:hover {
                        color: #F1F5F9;
                        background-color: #17243B;
                        border: 1px solid #2D3D59;
                    }
                """)

    # =========================================================================
    # SELECTION UX & ĐỒNG BỘ
    # =========================================================================

    def _toggle_checkbox_selection(self, index: QModelIndex) -> None:
        sm = self.grid_view.selectionModel()
        if sm.isSelected(index):
            sm.select(index, QItemSelectionModel.SelectionFlag.Deselect)
        else:
            sm.select(index, QItemSelectionModel.SelectionFlag.Select)
        self.grid_view.viewport().update()

    def _on_grid_selection_changed(self, selected, deselected) -> None:
        # Đồng bộ sang table
        selected_indexes = self.grid_view.selectionModel().selectedIndexes()
        selected_rows = {idx.row() for idx in selected_indexes}

        self.table.blockSignals(True)
        self.table.clearSelection()
        for r in selected_rows:
            self.table.selectRow(r)
        self.table.blockSignals(False)

        self._update_selection_bar()

    def _on_table_selection_changed(self) -> None:
        # Đồng bộ từ table sang grid
        selected_rows = {item.row() for item in self.table.selectedItems()}
        sm = self.grid_view.selectionModel()
        sm.blockSignals(True)
        sm.clearSelection()
        for r in selected_rows:
            idx = self.model.index(r, 0)
            if idx.isValid():
                sm.select(idx, QItemSelectionModel.SelectionFlag.Select)
        sm.blockSignals(False)

        self._update_selection_bar()

    def _select_all_videos(self) -> None:
        """Chọn tất cả video đang hiển thị trong danh sách."""
        if not self._filtered_assets:
            return
        sm = self.grid_view.selectionModel()
        sm.blockSignals(True)
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            if idx.isValid():
                sm.select(idx, QItemSelectionModel.SelectionFlag.Select)
        sm.blockSignals(False)

        self.table.blockSignals(True)
        self.table.selectAll()
        self.table.blockSignals(False)

        self._update_selection_bar()
        self.grid_view.viewport().update()

    def _clear_all_selection(self) -> None:
        self.grid_view.clearSelection()
        self.table.clearSelection()
        self._update_selection_bar()
        self.grid_view.viewport().update()

    def _get_selected_asset_ids(self) -> List[str]:
        # Ưu tiên lấy từ grid view
        selected_indexes = self.grid_view.selectionModel().selectedIndexes()
        ids = []
        for idx in selected_indexes:
            aid = idx.data(ROLE_MEDIA_ID)
            if aid and aid not in ids:
                ids.append(aid)

        if not ids:
            # Fallback table
            for item in self.table.selectedItems():
                row = item.row()
                t_item = self.table.item(row, 0)
                if t_item and t_item.text() not in ids:
                    ids.append(t_item.text())

        return ids

    def _get_selected_asset_id(self) -> Optional[str]:
        ids = self._get_selected_asset_ids()
        return ids[0] if ids else None

    def _get_selected_asset_path(self) -> Optional[str]:
        aid = self._get_selected_asset_id()
        if not aid:
            return None
        asset = self.media_repo.get_media_asset(aid)
        return asset.get("local_path") if asset else None

    def _update_selection_bar(self) -> None:
        count = len(self._get_selected_asset_ids())
        if count == 0:
            self.selection_bar.setVisible(False)
        else:
            self.selection_bar.setVisible(True)
            self.lbl_selected_count.setText(f"☑ Đã chọn {count} video")
            if count == 1:
                self.btn_compose_selected.setText("🎬 Soạn bài")
                self.btn_schedule_selected.setText("📅 Đặt lịch")
            else:
                self.btn_compose_selected.setText("🎬 Tạo bài hàng loạt")
                self.btn_schedule_selected.setText("📅 Lên lịch hàng loạt")

    # =========================================================================
    # FANPAGE PICKER & BATCH COMPOSER (SECTION 4 & 6)
    # =========================================================================

    def _on_card_page_picker_clicked(self, index: QModelIndex) -> None:
        """Hiển thị menu dropdown chọn Fanpage đích ngay trên Card video."""
        media_id = index.data(ROLE_MEDIA_ID)
        if not media_id:
            return

        pages = []
        if self.page_repo:
            try:
                pages = self.page_repo.list_pages()
            except Exception as e:
                logger.error(f"Lỗi lấy danh sách fanpage: {e}")

        if not pages:
            QMessageBox.information(
                self,
                "Chưa có Fanpage",
                "Chưa có Fanpage nào được kết nối trong hệ thống.\nVui lòng vào mục 'Quản lý Fanpage' để kết nối trang.",
            )
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131D2E;
                border: 1px solid #2B3D59;
                border-radius: 8px;
                padding: 6px;
                color: #F1F5F9;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #241E5C;
                color: #A5B4FC;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1E2D47;
                margin: 4px 6px;
            }
        """)

        current_target_id = str(index.data(ROLE_TARGET_PAGE_ID) or "")

        act_none = menu.addAction("✕ Không chọn Fanpage")
        menu.addSeparator()

        act_map = {}
        for p in pages:
            pid = str(p.get("id") or p.get("page_id") or p.get("facebook_page_id"))
            pname = p.get("name") or p.get("page_name") or f"Page {pid}"
            status = str(p.get("status") or "ready")
            status_text = " ⚠ (Hết hạn)" if status in ("token_expired", "expired") else ""
            prefix = "✓ " if pid == current_target_id else "📄 "
            act = menu.addAction(f"{prefix}{pname}{status_text}")
            act_map[act] = pid

        chosen_action = menu.exec(QCursor.pos())
        if chosen_action is None:
            return

        new_pid = None if chosen_action == act_none else act_map.get(chosen_action)

        # Cập nhật DB
        self.media_repo.update_target_page(media_id, new_pid)

        # Tìm tên page
        new_pname = ""
        if new_pid:
            for p in pages:
                if str(p.get("id") or p.get("page_id") or p.get("facebook_page_id")) == new_pid:
                    new_pname = p.get("name") or p.get("page_name") or ""
                    break

        # Cập nhật cache
        for item in self._cached_assets:
            if item.get("id") == media_id:
                item["target_page_id"] = new_pid
                item["target_page_name"] = new_pname
                break

        for item in self._filtered_assets:
            if item.get("id") == media_id:
                item["target_page_id"] = new_pid
                item["target_page_name"] = new_pname
                break

        self.model.set_assets(self._filtered_assets)
        self.grid_view.viewport().update()

    def _on_card_edit_clicked(self, index: QModelIndex) -> None:
        """Mở popup chỉnh sửa thông tin bài viết và đăng nhanh cho video."""
        if not index.isValid():
            return
        media_id = index.data(ROLE_MEDIA_ID)
        if not media_id:
            return

        asset = self.media_repo.get_media_asset(media_id)
        if not asset:
            return

        pages = []
        if self.page_repo:
            try:
                pages = self.page_repo.list_pages()
            except Exception as e:
                logger.error(f"Lỗi lấy danh sách trang: {e}")

        dlg = MediaEditPostDialog(
            asset=asset,
            pages=pages,
            queue_repo=self.queue_repo,
            media_repo=self.media_repo,
            parent=self,
        )
        if hasattr(self, "batch_schedule_created"):
            dlg.post_published.connect(self.batch_schedule_created.emit)
        dlg.post_published.connect(lambda _: self._update_stat_chips() if hasattr(self, "_update_stat_chips") else None)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload_media_list()
            if hasattr(self, "_update_stat_chips"):
                self._update_stat_chips()

    def _open_fanpage_picker(self) -> None:
        pages = []
        if self.page_repo:
            try:
                pages = self.page_repo.list_pages()
            except Exception as e:
                logger.error(f"Lỗi lấy danh sách trang: {e}")

        if not pages:
            QMessageBox.information(
                self,
                "Chưa có Fanpage",
                "Chưa có Fanpage nào được kết nối trong hệ thống.\nVui lòng vào mục 'Quản lý Fanpage' để kết nối trang.",
            )
            return

        popup = FanpagePickerPopup(pages, initial_selected_ids=self._selected_page_ids, parent=self)
        popup.pages_selected.connect(self._on_fanpages_selected)
        # Định vị popup ngay phía trên nút picker
        btn_pos = self.btn_fanpage_picker.mapToGlobal(QPoint(0, 0))
        popup.move(btn_pos.x(), btn_pos.y() - popup.height() - 4)
        popup.exec()

    def _on_fanpages_selected(self, page_ids: List[str]) -> None:
        self._selected_page_ids = page_ids
        if not page_ids:
            self.btn_fanpage_picker.setText("Fanpage đích: [ Chọn Fanpage ▾ ]")
        elif len(page_ids) == 1:
            self.btn_fanpage_picker.setText("Fanpage đích: 1 trang ▾")
        else:
            self.btn_fanpage_picker.setText(f"Fanpage đích: {len(page_ids)} trang ▾")

    def _on_compose_selected(self) -> None:
        selected_ids = self._get_selected_asset_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất một video để soạn bài.")
            return

        if len(selected_ids) == 1:
            # 1 Video -> Soạn bài đơn (tương thích backward)
            asset = self.media_repo.get_media_asset(selected_ids[0])
            if asset:
                # Ưu tiên fanpage đích đã gán trực tiếp cho card
                card_target_page = asset.get("target_page_id")
                chosen_pages = [card_target_page] if card_target_page else self._selected_page_ids
                self.send_to_composer.emit({
                    "media_id": asset["id"],
                    "file_path": asset["local_path"],
                    "duration": asset.get("duration", 0),
                    "platform": asset.get("source_platform", "other"),
                    "page_ids": chosen_pages,
                })
        else:
            # Nhiều video -> Mở hộp thoại Batch Compose
            self._open_batch_dialog(mode="compose")

    def _on_schedule_selected(self) -> None:
        selected_ids = self._get_selected_asset_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất một video để đặt lịch.")
            return

        if not self._selected_page_ids:
            # Nhắc nhở người dùng chọn Fanpage
            reply = QMessageBox.question(
                self,
                "Chưa chọn Fanpage",
                "Bạn chưa chọn Fanpage đích. Bạn có muốn chọn Fanpage ngay bây giờ không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_fanpage_picker()
                if not self._selected_page_ids:
                    return
            else:
                return

        self._open_batch_dialog(mode="schedule")

    def _on_quick_publish_selected(self) -> None:
        """Đăng nhanh ngay các video đã chọn lên Fanpage đích."""
        selected_ids = self._get_selected_asset_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn ít nhất một video để đăng nhanh.")
            return

        # Kiểm tra xem các video đã có fanpage đích chưa
        items = []
        needs_page = False
        for aid in selected_ids:
            asset = self.media_repo.get_media_asset(aid)
            if not asset:
                continue
            pid = asset.get("target_page_id")
            if not pid and self._selected_page_ids:
                pid = self._selected_page_ids[0]
            if not pid:
                needs_page = True
            items.append((asset, pid))

        if not items:
            return

        if needs_page:
            reply = QMessageBox.question(
                self,
                "Chưa chọn Fanpage",
                "Một số video chưa được gán Fanpage đích.\nBạn có muốn chọn Fanpage chung cho các video này ngay bây giờ không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_fanpage_picker()
                if not self._selected_page_ids:
                    return
                fallback_pid = self._selected_page_ids[0]
                updated_items = []
                for asset, pid in items:
                    effective_pid = pid or fallback_pid
                    updated_items.append((asset, effective_pid))
                items = updated_items
            else:
                return

        reply = QMessageBox.question(
            self,
            "Xác nhận Đăng nhanh",
            f"Bạn có chắc chắn muốn đưa {len(items)} video vào hàng đợi Đăng ngay lập tức không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
        from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso
        import uuid

        snapshots = []
        request_id = f"batch_quick_{uuid.uuid4().hex[:8]}"
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        scheduled_utc = vn_datetime_to_utc_iso(vn_now())

        for asset, pid in items:
            title = asset.get("title") or Path(asset.get("local_path", "")).stem
            caption = asset.get("caption") or title
            tags = asset.get("hashtags") or ""
            if tags and tags not in caption:
                caption = f"{caption}\n\n{tags}".strip()
            first_comment = asset.get("first_comment") or None
            item_batch_id = f"batch_{uuid.uuid4().hex[:8]}"

            snap = ContentSnapshot(
                batch_id=item_batch_id,
                page_id=pid,
                content_type=ContentType.REELS,
                final_caption=caption,
                primary_media_id=asset.get("id"),
                media_checksum=asset.get("checksum"),
                media_path=asset.get("local_path"),
                scheduled_at_utc=scheduled_utc,
                schedule_mode=ScheduleMode.LOCAL,
                title=title,
                first_comment=first_comment,
            )
            snapshots.append(snap)

        if not self.queue_repo:
            QMessageBox.information(
                self,
                "Đăng nhanh",
                f"Đã chuẩn bị {len(snapshots)} video để đăng nhanh.\n(Hàng đợi xuất bản chưa kết nối trong phiên này).",
            )
            return

        try:
            jobs = self.queue_repo.enqueue_batch(request_id, snapshots)
            if hasattr(self, "batch_schedule_created"):
                self.batch_schedule_created.emit(jobs)
            if hasattr(self, "_update_stat_chips"):
                self._update_stat_chips()
            QMessageBox.information(
                self,
                "Đăng nhanh thành công",
                f"⚡ Đã đưa {len(jobs)} video vào hàng đợi xuất bản thành công!\n\n"
                f"Hệ thống đang tiến hành xuất bản lần lượt lên các Fanpage đích.",
            )
            self._clear_all_selection()
            self.reload_media_list()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đăng nhanh", f"Không thể tạo tác vụ đăng hàng loạt:\n{e}")

    def _open_batch_dialog(self, mode: str = "schedule") -> None:
        selected_ids = self._get_selected_asset_ids()
        items = [self.media_repo.get_media_asset(aid) for aid in selected_ids if self.media_repo.get_media_asset(aid)]

        # Lọc danh sách Fanpage đã chọn
        pages = []
        if self.page_repo:
            all_pages = self.page_repo.list_pages()
            pages = [p for p in all_pages if str(p.get("id") or p.get("page_id")) in self._selected_page_ids]

        if not pages:
            # Tạo fanpage tạm nếu chưa kết nối
            pages = [{"id": "page_selected", "name": "Fanpage đã chọn"}]

        dlg = BatchComposeDialog(media_items=items, fanpages=pages, initial_mode=mode, parent=self)
        dlg.batch_confirmed.connect(self._handle_batch_submission)
        dlg.exec()

    def _handle_batch_submission(self, payload: dict) -> None:
        """Xử lý tạo tác vụ hàng loạt vào hàng đợi."""
        media_items = payload["media_items"]
        fanpages = payload["fanpages"]
        caption = payload.get("caption", "")
        start_time = payload.get("start_datetime")
        interval_min = payload.get("interval_minutes", 15)

        if not self.queue_repo:
            # Nếu không có queue_repo, chuyển video đầu tiên sang composer
            if media_items:
                m0 = media_items[0]
                self.send_to_composer.emit({
                    "media_id": m0["id"],
                    "file_path": m0["local_path"],
                    "duration": m0.get("duration", 0),
                    "platform": m0.get("source_platform", "other"),
                    "page_ids": [str(p.get("id")) for p in fanpages],
                })
            return

        from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
        from src.lovira.domain.timezone import vn_datetime_to_utc_iso
        import uuid

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        snapshots = []
        curr_dt = start_time or datetime.now()

        for m in media_items:
            for p in fanpages:
                pid = str(p.get("id") or p.get("page_id"))
                scheduled_utc = vn_datetime_to_utc_iso(curr_dt) if curr_dt else None
                snapshots.append(
                    ContentSnapshot(
                        batch_id=batch_id,
                        page_id=pid,
                        content_type=ContentType.REELS,
                        final_caption=caption or Path(m["local_path"]).stem,
                        primary_media_id=m["id"],
                        media_checksum=m.get("checksum"),
                        media_path=m["local_path"],
                        scheduled_at_utc=scheduled_utc,
                        schedule_mode=ScheduleMode.LOCAL,
                    )
                )
                curr_dt += timedelta(minutes=interval_min)

        try:
            jobs = self.queue_repo.enqueue_batch(request_id, snapshots)
            self.batch_schedule_created.emit(jobs)
            QMessageBox.information(
                self,
                "Tạo lịch hàng loạt thành công",
                f"Đã tạo thành công {len(jobs)} bài đăng vào hàng đợi lịch.\n"
                "Bạn có thể theo dõi tiến độ chi tiết tại mục 'Lịch đăng'.",
            )
            self.reload_media_list()
            self._clear_all_selection()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi tạo lịch hàng loạt", f"Không thể lưu các tác vụ:\n{e}")

    # =========================================================================
    # CONTEXT MENUS & PREVIEWS
    # =========================================================================

    def _show_grid_context_menu(self, pos: QPoint) -> None:
        idx = self.grid_view.indexAt(pos)
        if not idx.isValid():
            return

        aid = idx.data(ROLE_MEDIA_ID)
        if not aid:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131D2E;
                border: 1px solid #24344D;
                border-radius: 6px;
                color: #F1F5F9;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #6258E8;
            }
        """)

        act_play = menu.addAction("▶ Xem video")
        act_edit = menu.addAction("✏ Chỉnh sửa & Đăng nhanh...")
        act_detail = menu.addAction("ℹ Xem chi tiết")
        act_folder = menu.addAction("📁 Mở thư mục")
        act_copy_path = menu.addAction("📋 Sao chép đường dẫn")
        menu.addSeparator()
        act_compose = menu.addAction("🎬 Soạn bài với video này")
        menu.addSeparator()
        act_unlink = menu.addAction("🗑 Bỏ khỏi thư viện")
        act_delete_disk = menu.addAction("❌ Xóa vĩnh viễn trên ổ đĩa")

        action = menu.exec(self.grid_view.viewport().mapToGlobal(pos))
        if action == act_play:
            self._preview_media_id(aid)
        elif action == act_edit:
            self._on_card_edit_clicked(idx)
        elif action == act_detail:
            self._show_detail_dialog(aid)
        elif action == act_folder:
            lp = idx.data(ROLE_LOCAL_PATH)
            if lp and os.path.exists(lp):
                folder = str(Path(lp).parent)
                if os.name == "nt":
                    os.startfile(folder)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        elif action == act_copy_path:
            lp = idx.data(ROLE_LOCAL_PATH)
            if lp:
                QApplication.clipboard().setText(lp)
        elif action == act_compose:
            self._on_compose_selected()
        elif action == act_unlink:
            self._delete_asset_safe(aid, remove_file=False)
        elif action == act_delete_disk:
            self._delete_asset_safe(aid, remove_file=True)

    def _show_batch_more_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131D2E;
                border: 1px solid #24344D;
                color: #F1F5F9;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
            }
            QMenu::item:selected {
                background-color: #6258E8;
            }
        """)
        act_play = menu.addAction("▶ Xem video đầu tiên")
        act_folder = menu.addAction("📁 Mở thư mục chứa file")
        act_copy = menu.addAction("📋 Sao chép các đường dẫn")
        menu.addSeparator()
        act_unlink = menu.addAction("🗑 Bỏ các video đã chọn khỏi thư viện")
        act_disk = menu.addAction("❌ Xóa vĩnh viễn các file trên ổ đĩa")

        action = menu.exec(self.btn_more_actions.mapToGlobal(QPoint(0, self.btn_more_actions.height() + 2)))
        aid = self._get_selected_asset_id()
        if not aid:
            return

        if action == act_play:
            self._preview_media_id(aid)
        elif action == act_folder:
            lp = self._get_selected_asset_path()
            if lp and os.path.exists(lp):
                folder = str(Path(lp).parent)
                if os.name == "nt":
                    os.startfile(folder)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        elif action == act_copy:
            paths = []
            for a_id in self._get_selected_asset_ids():
                asset = self.media_repo.get_media_asset(a_id)
                if asset:
                    paths.append(asset.get("local_path", ""))
            QApplication.clipboard().setText("\n".join(paths))
        elif action == act_unlink:
            self._on_delete_selected()
        elif action == act_disk:
            self._delete_batch_disk()

    def _preview_media_id(self, media_id: str) -> None:
        asset = self.media_repo.get_media_asset(media_id)
        if not asset:
            return
        fp = asset.get("local_path")
        if fp and os.path.exists(fp):
            QDesktopServices.openUrl(QUrl.fromLocalFile(fp))
        else:
            QMessageBox.critical(self, "Không tìm thấy file", f"File video không còn tồn tại trên máy:\n{fp}")

    def _show_detail_dialog(self, media_id: str) -> None:
        asset = self.media_repo.get_media_asset(media_id)
        if not asset:
            return
        usage = self._usage_summary_map.get(media_id, {})
        dlg = MediaDetailDialog(asset=asset, usage_info=usage, parent=self)
        dlg.compose_requested.connect(self.send_to_composer.emit)
        dlg.exec()

    # =========================================================================
    # BẢO VỆ XÓA AN TOÀN (AC-12 & AC-42)
    # =========================================================================

    def _on_delete_selected(self) -> None:
        """AC-12: Chặn xóa video nếu đang được một lịch đăng chờ tham chiếu."""
        selected_ids = self._get_selected_asset_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn video cần xóa.")
            return

        # Kiểm tra AC-12 cho từng item
        blocked_items = []
        for aid in selected_ids:
            refs = self.media_repo.check_media_references(aid)
            if refs.get("active_job_count", 0) > 0:
                blocked_items.append((aid, refs["active_job_count"]))

        if blocked_items:
            first_aid, count = blocked_items[0]
            QMessageBox.critical(
                self,
                "Không thể xóa video (AC-12)",
                f"Video này hiện đang được {count} lịch đăng chờ thực hiện tham chiếu.\n"
                "Hành động xóa bị chặn để bảo vệ tính toàn vẹn của lịch đăng.\n"
                "Vui lòng hủy hoặc thay đổi các lịch liên quan trước khi xóa file.",
            )
            return

        n = len(selected_ids)
        msg = (
            f"Bạn có chắc chắn muốn bỏ {n} bản ghi video này khỏi thư viện không?\n\n"
            "LƯU Ý: Thao tác này chỉ xóa bản ghi khỏi thư viện.\n"
            "File video gốc vẫn được GIỮ NGUYÊN trên ổ đĩa máy tính."
            if n > 1
            else "Bạn có chắc chắn muốn xóa bản ghi video này khỏi thư viện không?\n\n"
            "LƯU Ý: File video gốc vẫn được GIỮ NGUYÊN trên ổ đĩa máy tính."
        )

        reply = QMessageBox.question(
            self,
            "Xác nhận bỏ khỏi thư viện",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for aid in selected_ids:
                self.media_repo.delete_media_asset(aid, force=False, remove_file=False)
            self.reload_media_list()
            self._clear_all_selection()

    def _delete_asset_safe(self, asset_id: str, remove_file: bool = False) -> None:
        refs = self.media_repo.check_media_references(asset_id)
        if refs.get("active_job_count", 0) > 0:
            count = refs["active_job_count"]
            QMessageBox.critical(
                self,
                "Không thể xóa video (AC-12)",
                f"Video này hiện đang được {count} lịch đăng chờ thực hiện tham chiếu.\n"
                "Hành động xóa bị chặn để bảo vệ tính toàn vẹn của lịch đăng.\n"
                "Vui lòng hủy hoặc thay đổi các lịch liên quan trước khi xóa file.",
            )
            return

        if remove_file:
            reply = QMessageBox.warning(
                self,
                "CẢNH BÁO XÓA FILE Ổ ĐĨA",
                "Hành động này sẽ XÓA VĨNH VIỄN FILE VIDEO TRÊN Ổ CỨNG của máy tính!\n"
                "Bạn có chắc chắn muốn tiếp tục không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.media_repo.delete_media_asset(asset_id, force=False, remove_file=remove_file)
        self.reload_media_list()
        self._clear_all_selection()

    def _delete_batch_disk(self) -> None:
        selected_ids = self._get_selected_asset_ids()
        if not selected_ids:
            return

        for aid in selected_ids:
            refs = self.media_repo.check_media_references(aid)
            if refs.get("active_job_count", 0) > 0:
                count = refs["active_job_count"]
                QMessageBox.critical(
                    self,
                    "Không thể xóa video (AC-12)",
                    f"Video {aid} đang được {count} lịch đăng chờ tham chiếu.\n"
                    "Thao tác bị chặn toàn bộ để bảo vệ an toàn dữ liệu.",
                )
                return

        reply = QMessageBox.warning(
            self,
            "CẢNH BÁO XÓA FILE HÀNG LOẠT",
            f"Bạn có chắc chắn muốn XÓA VĨNH VIỄN {len(selected_ids)} FILE VIDEO TRÊN Ổ CỨNG không?\n"
            "Dữ liệu đã xóa sẽ không thể phục hồi!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for aid in selected_ids:
                self.media_repo.delete_media_asset(aid, force=False, remove_file=True)
            self.reload_media_list()
            self._clear_all_selection()


# =========================================================================
# VIDEO WORKSPACE VIEW TỔNG HỢP (ROUTE.MEDIA & ROUTE.DOWNLOADS)
# =========================================================================

class VideoWorkspaceView(QWidget):
    """Màn hình làm việc Video tổng hợp 2.0 (gồm 2 tab: Tải video & Thư viện media)."""

    send_to_composer = Signal(dict)
    batch_schedule_created = Signal(list)

    def __init__(
        self,
        downloader: VideoDownloader,
        media_repo: MediaRepository,
        media_processor: MediaProcessor,
        download_dir: Path,
        page_repo: Optional[Any] = None,
        queue_repo: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()

        self.tab_download = VideoDownloadTab(
            downloader=downloader,
            media_repo=media_repo,
            media_processor=media_processor,
            download_dir=download_dir,
            page_repo=page_repo,
            queue_repo=queue_repo,
        )
        self.tab_library = MediaLibraryTab(
            media_repo=media_repo,
            page_repo=page_repo,
            queue_repo=queue_repo,
        )

        # Nối tín hiệu làm mới thư viện khi tải xong
        self.tab_download.media_downloaded.connect(self.tab_library.reload_media_list)

        # Nối tín hiệu 1-click soạn bài từ cả 2 tab
        self.tab_download.send_to_composer.connect(self.send_to_composer.emit)
        self.tab_library.send_to_composer.connect(self.send_to_composer.emit)

        # Nối tín hiệu batch schedule
        self.tab_download.batch_schedule_created.connect(self.batch_schedule_created.emit)
        self.tab_library.batch_schedule_created.connect(self.batch_schedule_created.emit)

        # Nối nút chuyển từ Thư viện sang tab Tải
        self.tab_library.switch_to_download_requested.connect(self.show_download_tab)

        self.tab_widget.addTab(self.tab_download, "📥 Tải video mới (Douyin / TikTok / Bilibili)")
        self.tab_widget.addTab(self.tab_library, "📂 Thư viện media đã tải")

        layout.addWidget(self.tab_widget)

    def show_download_tab(self) -> None:
        """Chuyển sang tab Tải video (Route.DOWNLOADS)."""
        self.tab_widget.setCurrentIndex(0)

    def show_library_tab(self) -> None:
        """Chuyển sang tab Thư viện media (Route.MEDIA)."""
        self.tab_widget.setCurrentIndex(1)
        self.tab_library.reload_media_list()

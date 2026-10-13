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
import json
import logging
import subprocess
import requests
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

class VideoDownloadTab(QWidget):
    """Tab Tải Video 2.0 (Hỗ trợ Tải 1 link & Tải hàng loạt danh sách)."""

    send_to_composer = Signal(dict)
    media_downloaded = Signal()

    def __init__(
        self,
        downloader: VideoDownloader,
        media_repo: MediaRepository,
        media_processor: MediaProcessor,
        download_dir: Path,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.downloader = downloader
        self.media_repo = media_repo
        self.media_processor = media_processor
        self.download_dir = download_dir

        self.current_worker: Optional[VideoDownloadWorker] = None
        self.batch_worker: Optional[BatchDownloadWorker] = None
        self.last_downloaded_data: Optional[Dict[str, Any]] = None
        self._inspected_platform: str = "other"

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Header Title
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title_lbl = QLabel("TẢI VIDEO DOUYIN / TIKTOK / BILIBILI")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #F3F6FC;")
        sub_lbl = QLabel("Tải video độ phân giải cao không watermark, tự động lưu vào Thư viện và chuyển sang Soạn bài")
        sub_lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")
        header_box.addWidget(title_lbl)
        header_box.addWidget(sub_lbl)
        layout.addLayout(header_box)

        # Tab con: [Tải 1 Video] | [Tải Hàng Loạt (Nhiều Link)]
        self.mode_tabs = QTabWidget()

        # --- TAB CON 1: TẢI 1 VIDEO ---
        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        single_layout.setContentsMargins(12, 16, 12, 12)
        single_layout.setSpacing(14)

        input_frame = QFrame()
        input_frame.setObjectName("cardFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 14, 16, 14)
        input_layout.setSpacing(10)

        input_title = QLabel("LIÊN KẾT VIDEO CẦN TẢI")
        input_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #6258E8;")
        input_layout.addWidget(input_title)

        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán liên kết video TikTok, Douyin hoặc Bilibili vào đây...")
        self.btn_inspect = QPushButton(" Lấy thông tin")
        self.btn_inspect.setIcon(get_icon("search", "#A9B8CF", 14))
        self.btn_inspect.clicked.connect(self._inspect_video)

        url_row.addWidget(self.url_input, stretch=1)
        url_row.addWidget(self.btn_inspect)
        input_layout.addLayout(url_row)
        single_layout.addWidget(input_frame)

        # Card Preview thông tin video
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("cardFrame")
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(16)

        self.thumb_label = QLabel("Chưa có ảnh xem trước")
        self.thumb_label.setFixedSize(180, 120)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background-color: #0B101B; border: 1px solid #1E293B; border-radius: 8px; color: #64748B;")
        preview_layout.addWidget(self.thumb_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self.lbl_meta_title = QLabel("Tiêu đề: —")
        self.lbl_meta_title.setWordWrap(True)
        self.lbl_meta_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #F3F6FC;")

        self.lbl_meta_platform = QLabel("Nền tảng: —")
        self.lbl_meta_author = QLabel("Tác giả: —")
        self.lbl_meta_duration = QLabel("Thời lượng: —")

        for lbl in [self.lbl_meta_platform, self.lbl_meta_author, self.lbl_meta_duration]:
            lbl.setStyleSheet("color: #94A3B8; font-size: 13px;")

        info_layout.addWidget(self.lbl_meta_title)
        info_layout.addWidget(self.lbl_meta_platform)
        info_layout.addWidget(self.lbl_meta_author)
        info_layout.addWidget(self.lbl_meta_duration)
        info_layout.addStretch()

        preview_layout.addLayout(info_layout, stretch=1)
        single_layout.addWidget(self.preview_frame)

        # Điều khiển tiến trình tải
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("cardFrame")
        ctrl_layout = QVBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(16, 14, 16, 14)
        ctrl_layout.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        ctrl_layout.addWidget(self.progress_bar)

        self.lbl_progress_status = QLabel("Trạng thái: Sẵn sàng tải")
        self.lbl_progress_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        ctrl_layout.addWidget(self.lbl_progress_status)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_download = QPushButton("⬇ Bắt đầu tải video")
        self.btn_download.setObjectName("primaryButton")
        self.btn_download.setIcon(get_icon("downloads", "#FFFFFF", 16))
        self.btn_download.clicked.connect(self._start_download)

        self.btn_cancel = QPushButton("✖ Hủy tải")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_download)

        self.btn_watch_downloaded = QPushButton("▶ Xem video")
        self.btn_watch_downloaded.setIcon(get_icon("play", "#A9B8CF", 14))
        self.btn_watch_downloaded.setVisible(False)
        self.btn_watch_downloaded.clicked.connect(self._watch_last_downloaded)

        self.btn_open_folder = QPushButton("📁 Mở thư mục")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_download_folder)

        self.btn_compose_now = QPushButton("🎬 Soạn bài & Đặt lịch ngay")
        self.btn_compose_now.setObjectName("successButton")
        self.btn_compose_now.setIcon(get_icon("composer", "#FFFFFF", 16))
        self.btn_compose_now.setVisible(False)
        self.btn_compose_now.clicked.connect(self._on_compose_now_clicked)

        action_row.addWidget(self.btn_download)
        action_row.addWidget(self.btn_cancel)
        action_row.addWidget(self.btn_watch_downloaded)
        action_row.addWidget(self.btn_open_folder)
        action_row.addStretch()
        action_row.addWidget(self.btn_compose_now)

        ctrl_layout.addLayout(action_row)
        single_layout.addWidget(ctrl_frame)
        self.mode_tabs.addTab(single_tab, "📥 Tải 1 Video")

        # --- TAB CON 2: TẢI HÀNG LOẠT (NHIỀU LINK) ---
        batch_tab = QWidget()
        batch_layout = QVBoxLayout(batch_tab)
        batch_layout.setContentsMargins(12, 16, 12, 12)
        batch_layout.setSpacing(14)

        batch_frame = QFrame()
        batch_frame.setObjectName("cardFrame")
        b_frame_layout = QVBoxLayout(batch_frame)
        b_frame_layout.setContentsMargins(16, 14, 16, 14)
        b_frame_layout.setSpacing(8)

        lbl_b_title = QLabel("TẢI HÀNG LOẠT THEO DANH SÁCH LIÊN KẾT")
        lbl_b_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #6258E8;")
        b_frame_layout.addWidget(lbl_b_title)

        lbl_b_sub = QLabel("Dán mỗi dòng 1 link video TikTok / Douyin / Bilibili:")
        lbl_b_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        b_frame_layout.addWidget(lbl_b_sub)

        self.batch_text_edit = QTextEdit()
        self.batch_text_edit.setPlaceholderText(
            "https://www.tiktok.com/@user/video/123456789\nhttps://www.douyin.com/video/987654321\n..."
        )
        self.batch_text_edit.setFixedHeight(110)
        b_frame_layout.addWidget(self.batch_text_edit)

        batch_btn_row = QHBoxLayout()
        batch_btn_row.setSpacing(10)
        self.btn_start_batch = QPushButton("🚀 Bắt đầu Tải hàng loạt")
        self.btn_start_batch.setObjectName("primaryButton")
        self.btn_start_batch.clicked.connect(self._start_batch_download)

        self.btn_cancel_batch = QPushButton("✖ Dừng tải hàng loạt")
        self.btn_cancel_batch.setObjectName("dangerButton")
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.clicked.connect(self._cancel_batch_download)

        batch_btn_row.addWidget(self.btn_start_batch)
        batch_btn_row.addWidget(self.btn_cancel_batch)
        batch_btn_row.addStretch()
        b_frame_layout.addLayout(batch_btn_row)

        batch_layout.addWidget(batch_frame)

        # Tiến độ hàng loạt
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setFixedHeight(8)
        self.batch_progress_bar.setVisible(False)
        batch_layout.addWidget(self.batch_progress_bar)

        self.lbl_batch_status = QLabel("Sẵn sàng tải hàng loạt.")
        self.lbl_batch_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        batch_layout.addWidget(self.lbl_batch_status)

        # Bảng các video vừa tải từ danh sách
        self.table_batch_results = QTableWidget()
        self.table_batch_results.setColumnCount(4)
        self.table_batch_results.setHorizontalHeaderLabels(["STT", "Tiêu đề video", "Đường dẫn file", "Thao tác"])
        self.table_batch_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_batch_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_batch_results.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        batch_layout.addWidget(self.table_batch_results)

        self.mode_tabs.addTab(batch_tab, "📦 Tải Hàng Loạt (Nhiều Link)")
        layout.addWidget(self.mode_tabs)

    def _inspect_video(self) -> None:
        raw_url = self.url_input.text().strip()
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
        self.btn_inspect.setIcon(get_icon("search", "#A9B8CF", 14))

        if not meta:
            QMessageBox.critical(self, "Lỗi phân tích", "Không thể lấy thông tin video. Vui lòng kiểm tra lại đường link.")
            return

        self._inspected_platform = meta.source_platform.value.lower() if meta.source_platform else _detect_platform(url)
        self.lbl_meta_title.setText(f"Tiêu đề: {meta.title}")
        self.lbl_meta_platform.setText(f"Nền tảng: {self._inspected_platform.upper()}")
        self.lbl_meta_author.setText(f"Tác giả: {meta.uploader}")
        m, s = divmod(int(meta.duration), 60)
        self.lbl_meta_duration.setText(f"Thời lượng: {m:02d}:{s:02d}")

        if meta.thumbnail_url:
            try:
                resp = requests.get(meta.thumbnail_url, timeout=5)
                if resp.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(resp.content)
                    self.thumb_label.setPixmap(
                        pixmap.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
            except Exception as e:
                logger.debug(f"Không thể tải thumbnail từ URL: {e}")

    def _start_download(self) -> None:
        raw_url = self.url_input.text().strip()
        url = VideoDownloader.clean_url(raw_url)
        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập liên kết video.")
            return

        if url != raw_url:
            self.url_input.setText(url)

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_compose_now.setVisible(False)
        self.btn_watch_downloaded.setVisible(False)
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Đang khởi tạo tiến trình tải...")

        detected = _detect_platform(url)
        platform = self._inspected_platform if self._inspected_platform != "other" else detected
        self.current_worker = VideoDownloadWorker(self.downloader, url, self.download_dir, platform=platform)
        self.current_worker.progress_updated.connect(self._on_progress_update)
        self.current_worker.finished_success.connect(self._on_download_success)
        self.current_worker.finished_error.connect(self._on_download_error)
        self.current_worker.start()

    def _on_progress_update(self, data: dict) -> None:
        percent = int(data.get("percent", 0))
        speed = data.get("speed", "")
        self.progress_bar.setValue(percent)
        self.lbl_progress_status.setText(f"Đang tải: {percent}% ({speed})")

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
                self.thumb_label.setPixmap(
                    pixmap.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        except Exception as e:
            logger.debug(f"Không thể trích xuất thumbnail: {e}")

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
                source_url=self.url_input.text().strip(),
                width=probe.width if probe else 0,
                height=probe.height if probe else 0,
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )
            data["media_id"] = media_id
        except Exception as e:
            logger.error(f"Lỗi khi ghi nhận media asset: {e}")

        self.last_downloaded_data = data
        self.btn_watch_downloaded.setVisible(True)
        self.btn_open_folder.setVisible(True)
        self.btn_compose_now.setVisible(True)
        self.media_downloaded.emit()

    def _on_download_error(self, err_msg: str) -> None:
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_progress_status.setText("❌ Tải video thất bại.")
        QMessageBox.critical(self, "Lỗi tải video", f"Không thể tải video:\n{err_msg}")

    def _cancel_download(self) -> None:
        if self.current_worker:
            self.current_worker._is_cancelled = True
        self.lbl_progress_status.setText("Đang dừng tiến trình tải...")
        self.btn_cancel.setEnabled(False)

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

    # --- BATCH DOWNLOAD LOGIC ---
    def _start_batch_download(self) -> None:
        raw_text = self.batch_text_edit.toPlainText().strip()
        lines = []
        for line in raw_text.splitlines():
            clean = VideoDownloader.clean_url(line)
            if clean:
                lines.append(clean)

        if not lines:
            QMessageBox.warning(self, "Chưa nhập link", "Vui lòng nhập ít nhất một liên kết video.")
            return

        self.btn_start_batch.setEnabled(False)
        self.btn_cancel_batch.setEnabled(True)
        self.batch_progress_bar.setVisible(True)
        self.batch_progress_bar.setValue(0)
        self.table_batch_results.setRowCount(0)

        self.batch_worker = BatchDownloadWorker(self.downloader, lines, self.download_dir)
        self.batch_worker.progress_updated.connect(self._on_batch_progress)
        self.batch_worker.item_downloaded.connect(self._on_batch_item_downloaded)
        self.batch_worker.finished_all.connect(self._on_batch_finished)
        self.batch_worker.start()

    def _on_batch_progress(self, current: int, total: int, url: str, percent: int) -> None:
        self.batch_progress_bar.setValue(percent)
        self.lbl_batch_status.setText(f"Đang tải {current}/{total}: {url[:40]}... ({percent}%)")

    def _on_batch_item_downloaded(self, data: dict) -> None:
        row = self.table_batch_results.rowCount()
        self.table_batch_results.insertRow(row)
        self.table_batch_results.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table_batch_results.setItem(row, 1, QTableWidgetItem(data["title"]))
        self.table_batch_results.setItem(row, 2, QTableWidgetItem(data["file_path"]))

        btn_view = QPushButton("▶ Xem")
        fp = data["file_path"]
        btn_view.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(fp)))
        self.table_batch_results.setCellWidget(row, 3, btn_view)

        try:
            probe = self.media_processor.inspect_video(Path(fp))
            checksum = self.media_processor.calculate_sha256(Path(fp))
            thumb_path = Path(fp).with_suffix(".thumb.jpg")
            try:
                self.media_processor.extract_thumbnail(Path(fp), thumb_path, timestamp_sec=3.0)
            except Exception:
                pass

            detected_platform = data.get("platform") or _detect_platform(data.get("url", ""))
            self.media_repo.add_media_asset(
                local_path=Path(fp),
                checksum=checksum,
                size_bytes=os.path.getsize(fp) if os.path.exists(fp) else 0,
                duration=probe.duration if probe else 0.0,
                source_platform=detected_platform,
                source_url=data.get("url", ""),
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )
            self.media_downloaded.emit()
        except Exception as e:
            logger.error(f"Lỗi khi thêm media asset từ batch: {e}")

    def _on_batch_finished(self, success: int, total: int) -> None:
        self.btn_start_batch.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        self.batch_progress_bar.setValue(100)
        self.lbl_batch_status.setText(f"✅ Hoàn tất tải hàng loạt: {success}/{total} video thành công.")
        QMessageBox.information(self, "Tải hàng loạt xong", f"Đã tải thành công {success}/{total} video!")

    def _cancel_batch_download(self) -> None:
        if self.batch_worker:
            self.batch_worker._is_cancelled = True
        self.lbl_batch_status.setText("Đang dừng tải hàng loạt...")
        self.btn_cancel_batch.setEnabled(False)


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
    - Tên video nằm dưới ảnh (2 dòng, ellipsis), dung lượng file, trạng thái xuất bản
    - Viền tím phát sáng khi được chọn, hover nhẹ khi di chuột
    """

    checkbox_clicked = Signal(QModelIndex)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.thumb_cache = ThumbnailCache.get_instance()
        self.card_size = QSize(224, 236)

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
            # Căn giữa ảnh trong thumbnail rect
            src_x = (pix.width() - thumb_w) // 2
            src_y = (pix.height() - thumb_h) // 2
            painter.drawPixmap(thumb_rect.left(), thumb_rect.top(), pix, max(0, src_x), max(0, src_y), thumb_w, thumb_h)
        else:
            # Fallback nền tối gradient & biểu tượng video
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

        # Tam giác play
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
            # Vẽ dấu tích
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

        # 6. Thông tin bên dưới Thumbnail: Tiêu đề video (Tối đa 2 dòng, tên dưới ảnh)
        content_top = thumb_rect.bottom() + 8
        title_str = index.data(ROLE_TITLE) or "Video không tên"
        font_title = QFont(painter.font())
        font_title.setPointSize(10)
        font_title.setBold(True)
        painter.setFont(font_title)
        painter.setPen(QColor("#F1F5F9"))

        title_rect = QRect(rect.left() + pad, content_top, rect.width() - (pad * 2), 34)
        fm_title = QFontMetrics(font_title)
        elided_title = fm_title.elidedText(title_str, Qt.TextElideMode.ElideRight, title_rect.width() * 2)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, elided_title)

        # 7. Dung lượng file
        size_str = index.data(ROLE_SIZE_STR) or "—"
        font_sub = QFont(painter.font())
        font_sub.setPointSize(9)
        painter.setFont(font_sub)
        painter.setPen(QColor("#8E9EB5"))

        size_rect = QRect(rect.left() + pad, content_top + 38, rect.width() - (pad * 2), 16)
        painter.drawText(size_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, size_str)

        # 8. Chip Trạng thái ở đáy Card
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

        status_bottom_y = rect.bottom() - 18
        # Vẽ chấm tròn
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(rect.left() + pad + 2, status_bottom_y + 4, 7, 7)

        # Vẽ text trạng thái
        font_status = QFont(painter.font())
        font_status.setPointSize(9)
        painter.setFont(font_status)
        painter.setPen(text_color)
        status_rect = QRect(rect.left() + pad + 14, status_bottom_y, rect.width() - (pad * 2) - 14, 16)
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status_text)

        painter.restore()

    def editorEvent(self, event: QEvent, model: QAbstractListModel, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        """Xử lý nhấp chuột vào ô Checkbox để bật/tắt lựa chọn."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            rect = option.rect.adjusted(4, 4, -4, -4)
            pad = 8
            chk_size = 24  # Mở rộng hit-box một chút
            chk_rect = QRect(rect.left() + pad + 4, rect.top() + pad + 4, chk_size, chk_size)
            if chk_rect.contains(event.pos()):
                self.checkbox_clicked.emit(index)
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
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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
            pid = str(page.get("id") or page.get("page_id"))
            pname = page.get("name") or page.get("page_name") or f"Page {pid}"
            is_valid = bool(page.get("access_token") or page.get("is_valid", True))

            row_frame = QFrame()
            row_frame.setStyleSheet("background-color: #17243B; border-radius: 6px; padding: 4px;")
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(8)

            cb = QCheckBox(pname)
            cb.setChecked(pid in self.selected_ids)
            cb.setToolTip(f"ID: {pid}")

            if not is_valid:
                cb.setEnabled(False)
                lbl_status = QLabel("! Token lỗi")
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
    Hộp thoại tạo bài hoặc lên lịch hàng loạt:
    - Giải thích rõ: N video x M Fanpage = N*M bài dự kiến
    - Cung cấp thời gian bắt đầu, khoảng cách đăng và múi giờ
    - Xem trước lịch đăng theo từng Fanpage
    """

    batch_confirmed = Signal(dict)

    def __init__(
        self,
        media_items: List[Dict[str, Any]],
        fanpages: List[Dict[str, Any]],
        initial_mode: str = "schedule",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.media_items = media_items
        self.fanpages = fanpages
        self.mode = initial_mode

        self.setWindowTitle("Xác nhận Đặt lịch / Tạo bài hàng loạt")
        self.setFixedSize(580, 520)
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
            }
            QPushButton#primaryBtn {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #5348D6;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Tiêu đề
        title_box = QVBoxLayout()
        title_lbl = QLabel("TẠO BÀI VIẾT / LÊN LỊCH HÀNG LOẠT")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #818CF8;")
        sub_lbl = QLabel("Phát hành đa kênh với kiểm soát từng bài đăng riêng biệt")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        layout.addLayout(title_box)

        # Banner tính toán số lượng
        n_videos = len(self.media_items)
        n_pages = len(self.fanpages)
        total_posts = n_videos * n_pages

        banner = QFrame()
        banner.setObjectName("cardBox")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(14, 12, 14, 12)
        banner_layout.setSpacing(6)

        formula_lbl = QLabel(f"📐 <b>Quy tắc gộp mặc định:</b> Mỗi video là một bài viết riêng.")
        formula_lbl.setStyleSheet("font-size: 13px; color: #F1F5F9;")
        detail_lbl = QLabel(f"Đã chọn: <b>{n_videos} video</b> × <b>{n_pages} Fanpage</b> = <span style='color: #10B981; font-weight: 800; font-size: 14px;'>{total_posts} bài dự kiến</span>")
        detail_lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")

        banner_layout.addWidget(formula_lbl)
        banner_layout.addWidget(detail_lbl)
        layout.addWidget(banner)

        # Nội dung / Caption mẫu chung
        caption_box = QVBoxLayout()
        caption_box.setSpacing(6)
        caption_lbl = QLabel("Nội dung bài viết (áp dụng chung cho toàn bộ bài):")
        caption_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1;")
        self.caption_edit = QTextEdit()
        self.caption_edit.setPlaceholderText("Nhập tiêu đề hoặc caption chung...")
        self.caption_edit.setFixedHeight(75)
        caption_box.addWidget(caption_lbl)
        caption_box.addWidget(self.caption_edit)
        layout.addLayout(caption_box)

        # Cấu hình lịch đăng
        sched_frame = QFrame()
        sched_frame.setObjectName("cardBox")
        sched_layout = QVBoxLayout(sched_frame)
        sched_layout.setContentsMargins(14, 12, 14, 12)
        sched_layout.setSpacing(10)

        sched_title = QLabel("CẤU HÌNH THỜI GIAN LÊN LỊCH")
        sched_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #6258E8;")
        sched_layout.addWidget(sched_title)

        time_row = QHBoxLayout()
        time_row.setSpacing(10)
        time_row.addWidget(QLabel("Thời gian bắt đầu:"))

        self.start_dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(15 * 60))
        self.start_dt.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.start_dt.setCalendarPopup(True)
        time_row.addWidget(self.start_dt)

        time_row.addWidget(QLabel("Khoảng cách giữa các bài:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 1440)
        self.spin_interval.setValue(15)
        self.spin_interval.setSuffix(" phút")
        time_row.addWidget(self.spin_interval)

        sched_layout.addLayout(time_row)

        tz_lbl = QLabel("Múi giờ chuẩn: Asia/Ho_Chi_Minh (UTC+7) · Đảm bảo không trùng giờ.")
        tz_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        sched_layout.addWidget(tz_lbl)

        layout.addWidget(sched_frame)

        # Bảng xem trước lịch đăng mẫu
        preview_lbl = QLabel("Xem trước phân bổ lịch:")
        preview_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8;")
        layout.addWidget(preview_lbl)

        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(3)
        self.table_preview.setHorizontalHeaderLabels(["Video", "Fanpage đích", "Thời gian dự kiến (UTC+7)"])
        self.table_preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_preview.setFixedHeight(120)
        layout.addWidget(self.table_preview)

        self._update_preview_table()
        self.start_dt.dateTimeChanged.connect(self._update_preview_table)
        self.spin_interval.valueChanged.connect(self._update_preview_table)

        # Nút xác nhận
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Hủy bỏ")
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton(f"🚀 Xác nhận tạo {total_posts} lịch đăng")
        self.btn_confirm.setObjectName("primaryBtn")
        self.btn_confirm.clicked.connect(self._on_confirm_clicked)

        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_confirm)
        layout.addLayout(btn_row)

    def _update_preview_table(self) -> None:
        self.table_preview.setRowCount(0)
        start_time = self.start_dt.dateTime().toPython()
        interval_min = self.spin_interval.value()

        current_time = start_time
        row = 0
        for m in self.media_items:
            v_name = m.get("display_title") or Path(m.get("local_path", "")).stem
            for p in self.fanpages:
                p_name = p.get("name") or p.get("page_name") or "Fanpage"
                self.table_preview.insertRow(row)
                self.table_preview.setItem(row, 0, QTableWidgetItem(v_name))
                self.table_preview.setItem(row, 1, QTableWidgetItem(p_name))
                self.table_preview.setItem(row, 2, QTableWidgetItem(current_time.strftime("%d/%m/%Y %H:%M")))
                current_time += timedelta(minutes=interval_min)
                row += 1
                if row >= 20:  # Giới hạn hiển thị xem trước
                    break
            if row >= 20:
                break

    def _on_confirm_clicked(self) -> None:
        payload = {
            "media_items": self.media_items,
            "fanpages": self.fanpages,
            "caption": self.caption_edit.toPlainText().strip(),
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
        # 2. THANH CÔNG CỤ LỌC & TÌM KIẾM (TOOLBAR GỌN)
        # -------------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

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
            QLineEdit:focus {
                border: 1px solid #6258E8;
            }
        """)
        self.search_filter.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_filter, stretch=1)

        # Dropdown Nền tảng
        self.cb_filter_platform = QComboBox()
        self.cb_filter_platform.setFixedHeight(34)
        self.cb_filter_platform.addItems(["Tất cả", "TikTok", "Douyin", "Bilibili", "Khác"])
        self.cb_filter_platform.setStyleSheet("""
            QComboBox {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                padding: 4px 10px;
                color: #E2E8F0;
                font-size: 12px;
                min-width: 100px;
            }
        """)
        self.cb_filter_platform.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cb_filter_platform)

        # Dropdown Trạng thái
        self.cb_filter_status = QComboBox()
        self.cb_filter_status.setFixedHeight(34)
        self.cb_filter_status.addItems([
            "Trạng thái: Tất cả",
            "Chưa sử dụng",
            "Đã lên lịch",
            "Đã đăng",
            "Có lỗi",
            "File thất lạc",
        ])
        self.cb_filter_status.setStyleSheet(self.cb_filter_platform.styleSheet())
        self.cb_filter_status.currentIndexChanged.connect(self._on_status_combo_changed)
        filter_row.addWidget(self.cb_filter_status)

        # Dropdown Sắp xếp
        self.cb_sort = QComboBox()
        self.cb_sort.setFixedHeight(34)
        self.cb_sort.addItems(["Mới nhất", "Cũ nhất", "Tên A–Z", "Dung lượng", "Thời lượng"])
        self.cb_sort.setStyleSheet(self.cb_filter_platform.styleSheet())
        self.cb_sort.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.cb_sort)

        # Toggle Lưới [▦] / Danh sách [≡]
        self.btn_view_grid = QPushButton("▦")
        self.btn_view_grid.setToolTip("Chế độ xem dạng lưới (Grid)")
        self.btn_view_grid.setFixedSize(34, 34)
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setChecked(True)

        self.btn_view_list = QPushButton("≡")
        self.btn_view_list.setToolTip("Chế độ xem danh sách (List)")
        self.btn_view_list.setFixedSize(34, 34)
        self.btn_view_list.setCheckable(True)

        view_toggle_group = QButtonGroup(self)
        view_toggle_group.addButton(self.btn_view_grid)
        view_toggle_group.addButton(self.btn_view_list)

        toggle_style = """
            QPushButton {
                background-color: #131D2E;
                border: 1px solid #1E2D47;
                border-radius: 6px;
                color: #94A3B8;
                font-size: 14px;
            }
            QPushButton:checked {
                background-color: #241E5C;
                border: 1px solid #6258E8;
                color: #FFFFFF;
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
        # 3. DÒNG THỐNG KÊ FILTER PILLS / COUNTS SUMMARY
        # -------------------------------------------------------------
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(8)

        self.lbl_pill_all = QLabel("Tất cả (0)")
        self.lbl_pill_unused = QLabel("Chưa sử dụng (0)")
        self.lbl_pill_scheduled = QLabel("Đã lên lịch (0)")
        self.lbl_pill_published = QLabel("Đã đăng (0)")
        self.lbl_pill_failed = QLabel("Có lỗi (0)")

        pill_base_style = """
            QLabel {
                color: #94A3B8;
                font-size: 12px;
                padding: 3px 8px;
                border-radius: 4px;
            }
            QLabel:hover {
                color: #F1F5F9;
                background-color: #17243B;
            }
        """
        for lbl in (self.lbl_pill_all, self.lbl_pill_unused, self.lbl_pill_scheduled, self.lbl_pill_published, self.lbl_pill_failed):
            lbl.setStyleSheet(pill_base_style)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_pill_all.mousePressEvent = lambda _: self._on_pill_clicked(None)
        self.lbl_pill_unused.mousePressEvent = lambda _: self._on_pill_clicked("unused")
        self.lbl_pill_scheduled.mousePressEvent = lambda _: self._on_pill_clicked("scheduled")
        self.lbl_pill_published.mousePressEvent = lambda _: self._on_pill_clicked("published")
        self.lbl_pill_failed.mousePressEvent = lambda _: self._on_pill_clicked("failed")

        self.summary_row.addWidget(self.lbl_pill_all)
        self.summary_row.addWidget(QLabel("·"))
        self.summary_row.addWidget(self.lbl_pill_unused)
        self.summary_row.addWidget(QLabel("·"))
        self.summary_row.addWidget(self.lbl_pill_scheduled)
        self.summary_row.addWidget(QLabel("·"))
        self.summary_row.addWidget(self.lbl_pill_published)
        self.summary_row.addWidget(QLabel("·"))
        self.summary_row.addWidget(self.lbl_pill_failed)
        self.summary_row.addStretch()

        layout.addLayout(self.summary_row)

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
        """)

        bar_layout = QHBoxLayout(self.selection_bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(10)

        self.lbl_selected_count = QLabel("Đã chọn 0 video")
        bar_layout.addWidget(self.lbl_selected_count)

        self.btn_clear_selection = QPushButton("Bỏ chọn")
        self.btn_clear_selection.clicked.connect(self._clear_all_selection)
        bar_layout.addWidget(self.btn_clear_selection)

        bar_layout.addStretch()

        # Dropdown chọn Fanpage
        self.btn_fanpage_picker = QPushButton("Fanpage đích: [ Chọn Fanpage ▾ ]")
        self.btn_fanpage_picker.clicked.connect(self._open_fanpage_picker)
        bar_layout.addWidget(self.btn_fanpage_picker)

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

        # Lấy trạng thái tổng hợp bài đăng / lịch / lỗi
        try:
            self._usage_summary_map = self.media_repo.get_media_usage_summary(asset_ids)
        except Exception as e:
            logger.debug(f"Không thể lấy usage summary: {e}")
            self._usage_summary_map = {}

        # Gắn trạng thái hiển thị vào từng asset
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
        self._apply_filters()

    # =========================================================================
    # SELECTION UX & ĐỒNG BỘ
    # =========================================================================

    def _toggle_checkbox_selection(self, index: QModelIndex) -> None:
        sm = self.grid_view.selectionModel()
        if sm.isSelected(index):
            sm.select(index, QItemSelectionModel.SelectionFlag.Deselect)
        else:
            sm.select(index, QItemSelectionModel.SelectionFlag.Select)

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

    def _clear_all_selection(self) -> None:
        self.grid_view.clearSelection()
        self.table.clearSelection()
        self._update_selection_bar()

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
                self.send_to_composer.emit({
                    "media_id": asset["id"],
                    "file_path": asset["local_path"],
                    "duration": asset.get("duration", 0),
                    "platform": asset.get("source_platform", "other"),
                    "page_ids": self._selected_page_ids,
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
